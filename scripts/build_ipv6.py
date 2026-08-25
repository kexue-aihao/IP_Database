#!/usr/bin/env python3
"""
Build China IPv6 geolocation SQL database.

Data sources:
  - ip2region ipv6_source.txt  (ISP + province/city for mainland CN)
  - APNIC delegated file       (standalone HK/TW/MO allocations)
Enrichment:   GeoCN.mmdb + AreaCity (coordinates, division codes)
ISP mapping:  ip2region ISP field + IPv6 prefix fallback

Output: output/china_ipv6_{telecom,unicom,mobile,other,idc}.sql
"""

import ipaddress
import os
import sys
import urllib.request
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.isp_classifier import classify_isp as classify_v4_isp
from common.geo_enricher import enrich_ipv6
from common.sql_writer import SQLWriter, write_idc_table
from common.constants import (
    IPV6_ISP_PREFIXES, IDC_IPV6_PREFIXES, COUNTRY_NAMES,
)

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE, 'data')
OUTPUT_DIR = os.path.join(BASE, 'output')

IP2R_V6_PATH = os.path.join(DATA_DIR, 'ip2region_data', 'ipv6_source.txt')
APNIC_URL = 'https://ftp.apnic.net/pub/stats/apnic/delegated-apnic-latest'
APNIC_PATH = os.path.join(DATA_DIR, 'delegated-apnic-latest')

TARGET_CODES = {'CN', 'HK', 'TW', 'MO'}

IPV6_COLUMNS = [
    ('id', 'INT(11) NOT NULL AUTO_INCREMENT', ''),
    ('start_ip', 'VARCHAR(39) NOT NULL', '起始IPv6'),
    ('end_ip', 'VARCHAR(39) NOT NULL', '结束IPv6'),
    ('cidr', "VARCHAR(43) NOT NULL DEFAULT ''", 'CIDR表示'),
    ('prefix_len', "INT(11) NOT NULL DEFAULT 0", '前缀长度'),
    ('start_ip_hex', "VARCHAR(32) NOT NULL DEFAULT ''", '起始IP十六进制'),
    ('end_ip_hex', "VARCHAR(32) NOT NULL DEFAULT ''", '结束IP十六进制'),
    ('country', "VARCHAR(20) NOT NULL DEFAULT ''", '国家/地区'),
    ('province', "VARCHAR(30) NOT NULL DEFAULT ''", '省份'),
    ('city', "VARCHAR(30) NOT NULL DEFAULT ''", '城市'),
    ('district', "VARCHAR(30) NOT NULL DEFAULT ''", '区县'),
    ('isp', "VARCHAR(100) NOT NULL DEFAULT ''", '运营商'),
    ('division_code', "VARCHAR(6) NOT NULL DEFAULT ''", '行政区划代码'),
    ('latitude', 'DECIMAL(10,6) DEFAULT NULL', '纬度(WGS-84)'),
    ('longitude', 'DECIMAL(10,6) DEFAULT NULL', '经度(WGS-84)'),
    ('geo_level', "VARCHAR(12) NOT NULL DEFAULT ''", '精度'),
    ('idc_vendor', "VARCHAR(30) NOT NULL DEFAULT ''", 'IDC/云厂商标记'),
    ('PRIMARY KEY', '(id)', ''),
]

# ISP overrides for IPv6 (same as IPv4)
CHINA_ISP_OVERRIDES = {
    '中国电信': 'telecom',
    '中国联通': 'unicom',
    '中国移动': 'mobile',
    '中国铁通': 'mobile',
    '中国教育网': 'other',
    '中国科技网': 'other',
}


def ipv6_to_hex(ip_str):
    """Convert an IPv6 string to a 32-char lowercase hex string."""
    return ipaddress.IPv6Address(ip_str).exploded.replace(':', '').lower()


def cidr_to_prefix_len(cidr_str):
    """Extract prefix length from CIDR string, or compute from end_ip."""
    if '/' in cidr_str:
        return int(cidr_str.split('/')[1])
    return 64  # default for non-CIDR ranges


def classify_ipv6_isp(cidr_str, isp_text=''):
    """Classify IPv6 ISP: prefer ip2region ISP field, fallback to prefix.

    Returns (isp_group, isp_name).
    """
    # Try ip2region ISP name first
    if isp_text and isp_text != '0' and isp_text.strip():
        lower = isp_text.strip().lower()
        # Check known CN ISP names
        for kw, group in CHINA_ISP_OVERRIDES.items():
            if kw.lower() in lower:
                return group, isp_text.strip()

        # Check general ISP keyword map
        grp = classify_v4_isp(isp_text)
        if grp != 'other':
            return grp, isp_text.strip()

    # Fallback: match by IPv6 prefix
    if cidr_str and '/' in cidr_str:
        ip_part = cidr_str.split('/')[0].strip()
        hex_addr = ipv6_to_hex(ip_part)
        prefix4 = hex_addr[:4].lower()
        if prefix4 in IPV6_ISP_PREFIXES:
            isp_map = {'telecom': '中国电信', 'unicom': '中国联通', 'mobile': '中国移动'}
            isp = IPV6_ISP_PREFIXES[prefix4]
            return isp, isp_map.get(isp, f'China{isp}')

    return 'other', isp_text.strip() if isp_text and isp_text != '0' else ''


def match_idc_ipv6(ipv6_str, prefix_len):
    """Check if an IPv6 prefix overlaps with known IDC ranges."""
    if not ipv6_str:
        return ''
    hex_addr = ipv6_to_hex(ipv6_str)
    matched = []
    for vendor, prefix_hex, plen in IDC_IPV6_PREFIXES:
        if hex_addr[:len(prefix_hex)] == prefix_hex and prefix_len >= plen:
            matched.append(vendor)
    return '/'.join(sorted(set(matched))) if matched else ''


def download_file(url, path, label=''):
    """Download a file with progress message."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path) and os.path.getsize(path) > 10000:
        size = os.path.getsize(path)
        print(f'  Using cached {label}: {size / 1024:.1f} KB')
        return True

    print(f'  Downloading {label}...')
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read().decode('utf-8', errors='replace')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(data)
        print(f'  Downloaded {label}: {len(data) / 1024:.1f} KB')
        return True
    except Exception as e:
        print(f'  [ERROR] Download {label} failed: {e}')
        return False


def parse_ip2region_v6():
    """Parse ipv6_source.txt for CN/HK/TW/MO IPv6 records with ISP data.

    Format: start_ip|end_ip|country|province|city|isp|country_code
    """
    records = []
    if not os.path.exists(IP2R_V6_PATH):
        print(f'  [WARN] {IP2R_V6_PATH} not found')
        return records

    print(f'  Parsing {IP2R_V6_PATH} for CN/HK/TW/MO...')
    with open(IP2R_V6_PATH, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split('|')
            if len(parts) < 7:
                continue

            cc = parts[6].strip().upper()
            if cc not in TARGET_CODES:
                continue

            country = parts[2].strip()
            province = parts[3].strip() if parts[3].strip() != '0' else ''
            city = parts[4].strip() if parts[4].strip() != '0' else ''
            isp = parts[5].strip() if parts[5].strip() != '0' else ''

            # Some records have ISP in country field
            if not isp and country in CHINA_ISP_OVERRIDES:
                isp = country
                country = '中国'

            start_ip = parts[0].strip()
            end_ip = parts[1].strip()

            # Compute CIDR prefix length from IP range
            try:
                start = ipaddress.IPv6Address(start_ip)
                end = ipaddress.IPv6Address(end_ip)
                networks = list(ipaddress.summarize_address_range(start, end))
                if networks:
                    cidr = str(networks[0])
                else:
                    cidr = f'{start_ip}/64'
            except Exception:
                cidr = f'{start_ip}/64'

            records.append({
                'cc': cc,
                'start_ip': start_ip,
                'end_ip': end_ip,
                'cidr': cidr,
                'prefix_len': int(cidr.split('/')[1]) if '/' in cidr else 64,
                'country_name': COUNTRY_NAMES.get(cc, country),
                'province': province,
                'city': city,
                'isp_text': isp,
            })

    return records


def parse_apnic():
    """Parse APNIC file for CN/HK/TW/MO IPv6 allocations."""
    records = []
    if not os.path.exists(APNIC_PATH):
        return records

    print(f'  Parsing {APNIC_PATH} for CN/HK/TW/MO...')
    with open(APNIC_PATH, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            parts = line.split('|')
            if len(parts) < 7:
                continue

            cc = parts[1].strip().upper()
            rtype = parts[2].strip()
            start = parts[3].strip()
            value = parts[4].strip()

            if cc not in TARGET_CODES or rtype != 'ipv6':
                continue

            try:
                prefix_len = int(value)
            except ValueError:
                continue

            try:
                network = ipaddress.IPv6Network(f'{start}/{prefix_len}', strict=False)
            except (ValueError, ipaddress.AddressValueError):
                continue

            records.append({
                'cc': cc,
                'start_ip': str(network.network_address),
                'end_ip': str(network.broadcast_address),
                'cidr': f'{str(network.network_address)}/{prefix_len}',
                'prefix_len': prefix_len,
                'country_name': COUNTRY_NAMES.get(cc, cc),
                'province': '',
                'city': '',
                'isp_text': '',
            })

    return records


def main():
    print('=' * 60)
    print('  China IPv6 Database Builder')
    print('=' * 60)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 1. Acquire data
    print('\n[1/4] Acquiring IPv6 data sources...')
    records = parse_ip2region_v6()
    if records:
        print(f'  ip2region v6: {len(records):,} records')

    # Also check APNIC for HK/TW/MO coverage
    download_file(APNIC_URL, APNIC_PATH, 'APNIC')
    apnic = parse_apnic()
    if apnic:
        # Merge APNIC records that ip2region doesn't cover
        existing = {(r['start_ip'], r['end_ip']) for r in records}
        for ar in apnic:
            if (ar['start_ip'], ar['end_ip']) not in existing:
                records.append(ar)

        print(f'  APNIC: {len(apnic):,} records ('
              f'{len(apnic) - len([r for r in records if r["cc"] in ["CN"]]):,} new HK/TW/MO)')

    if not records:
        print('[ERROR] No IPv6 records found.')
        return 1

    # 2. Enrich + Classify
    print('\n[2/4] Enriching with ISP classification & coordinates...')
    groups = {'telecom': [], 'unicom': [], 'mobile': [], 'other': []}
    cc_counts = {}
    geo_stats = {'district': 0, 'city': 0, 'province': 0, 'admin_center': 0}

    for i, rec in enumerate(records):
        start_ip = rec['start_ip']
        cidr = rec['cidr']
        prefix_len = rec['prefix_len']
        cc = rec['cc']

        cc_counts[cc] = cc_counts.get(cc, 0) + 1
        country_name = rec.get('country_name', COUNTRY_NAMES.get(cc, cc))

        start_hex = ipv6_to_hex(start_ip)
        end_hex = ipv6_to_hex(rec['end_ip'])

        # ISP classification
        isp_group, isp_name = classify_ipv6_isp(cidr, rec.get('isp_text', ''))

        # Coordinate enrichment
        enr_prov = rec.get('province', '')
        enr_city = rec.get('city', '')
        dc, lat, lng, geo_level, enr_prov, enr_city = enrich_ipv6(
            start_ip, enr_prov, enr_city, country_name
        )
        geo_stats[geo_level] = geo_stats.get(geo_level, 0) + 1

        # IDC matching
        idc_vendor = match_idc_ipv6(start_ip, prefix_len)

        row = (
            start_ip,
            rec['end_ip'],
            cidr,
            prefix_len,
            start_hex,
            end_hex,
            country_name,
            enr_prov,
            enr_city,
            '',
            isp_name,
            dc,
            lat,
            lng,
            geo_level,
            idc_vendor,
        )

        groups[isp_group].append((start_hex, row))

        if (i + 1) % 1000 == 0:
            print(f'    Processed {i + 1:,}/{len(records):,}')

    # Sort by hex
    for key in groups:
        groups[key].sort(key=lambda x: x[0])

    # 3. Write SQL
    print('\n[3/4] Writing SQL files...')
    results = {}
    isp_labels = {
        'telecom': '中国电信',
        'unicom': '中国联通',
        'mobile': '中国移动',
        'other': '其他运营商',
    }

    for isp_group, rows_list in groups.items():
        if not rows_list:
            print(f'  Skipping {isp_group} (no records)')
            continue

        filename = f'china_ipv6_{isp_group}.sql'
        path = os.path.join(OUTPUT_DIR, filename)
        writer = SQLWriter(
            path,
            f'china_ipv6_{isp_group}',
            IPV6_COLUMNS,
            comment=f'中国 IPv6 归属地 — {isp_labels[isp_group]}',
        )

        for _, row in rows_list:
            writer.add_row(row)

        count = writer.close()
        size = os.path.getsize(path)
        results[isp_group] = count
        print(f'  {filename}: {count:,} rows  ({size / 1024:.1f} KB)')

    # 4. Write IDC table
    print('\n[4/4] Writing IDC reference table...')
    idc_rows = []
    for vendor, prefix_hex, plen in IDC_IPV6_PREFIXES:
        try:
            full_hex = prefix_hex.ljust(32, '0')
            start_ip = str(ipaddress.IPv6Address(int(full_hex, 16)))
            end_bits = ('f' * (32 - len(prefix_hex)))
            end_hex = prefix_hex + end_bits
            end_ip = str(ipaddress.IPv6Address(int(end_hex, 16)))
        except Exception:
            start_ip = prefix_hex
            end_ip = ''
        idc_rows.append((vendor, start_ip, end_ip, prefix_hex, end_hex, ''))

    idc_path = os.path.join(OUTPUT_DIR, 'china_ipv6_idc.sql')
    idc_count = write_idc_table(idc_path, 'china_ipv6_idc', idc_rows, ip_version=6,
                                comment='中国 IDC/云厂商 IPv6 IP 段')
    idc_size = os.path.getsize(idc_path)
    print(f'  china_ipv6_idc.sql: {idc_count} rows  ({idc_size / 1024:.1f} KB)')

    # Summary
    print()
    print('=' * 60)
    print('  Build Complete!')
    print('=' * 60)

    total = sum(results.values())
    print(f'  By country:')
    for cc in ['CN', 'HK', 'TW', 'MO']:
        print(f'    {COUNTRY_NAMES.get(cc, cc)}: {cc_counts.get(cc, 0):,}')

    print(f'\n  By ISP:')
    for g in ['telecom', 'unicom', 'mobile', 'other']:
        c = results.get(g, 0)
        pct = (c / total * 100) if total else 0
        print(f'    {isp_labels[g]:8s}: {c:>8,}  ({pct:5.1f}%)')
    print(f'    {"IDC参考":8s}: {idc_count:>8,}')
    print(f'    {"合计":8s}: {total + idc_count:>8,}')

    print(f'\n  Coordinate precision:')
    for level in ['district', 'city', 'province', 'admin_center']:
        c = geo_stats.get(level, 0)
        print(f'    {level:12s}: {c:>8,}')

    return 0


if __name__ == '__main__':
    sys.exit(main())
