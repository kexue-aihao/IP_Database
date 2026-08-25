#!/usr/bin/env python3
"""
Build China IPv4 geolocation SQL database.

Data source: ip2region v2 (ip.merge.txt)
Enrichment:   GeoCN.mmdb + AreaCity (coordinates, division codes)

Output: output/china_ipv4_{telecom,unicom,mobile,other,idc}.sql
"""

import csv
import os
import sys
import urllib.request
from datetime import datetime

# Add parent to path for common imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.isp_classifier import classify_isp
from common.geo_enricher import enrich_ipv4
from common.sql_writer import SQLWriter, write_idc_table
from common.constants import IDC_IPV4_RANGES

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE, 'data')
OUTPUT_DIR = os.path.join(BASE, 'output')

# ip2region v2 raw data URL (GitHub-hosted mirror)
IP2REGION_PATH = os.path.join(DATA_DIR, 'ip2region_data', 'ipv4_source.txt')

# China region filter keywords
CHINA_KEYWORDS = [
    '中国', 'china', 'cn',
    '香港', 'hong kong', 'hongkong', 'hk',
    '澳门', 'macau', 'macao', 'mo',
    '台湾', 'taiwan', 'tw',
    '北京', '上海', '天津', '重庆',
]

# ISP overrides: some records have ISP in country field instead
CHINA_ISP_OVERRIDES = {
    '中国电信': 'telecom',
    '中国联通': 'unicom',
    '中国移动': 'mobile',
    '中国铁通': 'mobile',
}

# IPv4 table column definition
IPV4_COLUMNS = [
    ('id', 'INT(11) NOT NULL AUTO_INCREMENT', ''),
    ('start_ip', 'VARCHAR(15) NOT NULL', '起始IPv4'),
    ('end_ip', 'VARCHAR(15) NOT NULL', '结束IPv4'),
    ('start_ip_int', 'BIGINT(20) NOT NULL', '起始IP整型'),
    ('end_ip_int', 'BIGINT(20) NOT NULL', '结束IP整型'),
    ('country', "VARCHAR(20) NOT NULL DEFAULT '中国'", '国家/地区'),
    ('province', "VARCHAR(30) NOT NULL DEFAULT ''", '省份'),
    ('city', "VARCHAR(30) NOT NULL DEFAULT ''", '城市'),
    ('district', "VARCHAR(30) NOT NULL DEFAULT ''", '区县'),
    ('isp', "VARCHAR(100) NOT NULL DEFAULT ''", '运营商(原始名称)'),
    ('division_code', "VARCHAR(6) NOT NULL DEFAULT ''", '行政区划代码'),
    ('latitude', 'DECIMAL(10,6) DEFAULT NULL', '纬度(WGS-84)'),
    ('longitude', 'DECIMAL(10,6) DEFAULT NULL', '经度(WGS-84)'),
    ('geo_level', "VARCHAR(12) NOT NULL DEFAULT ''", '精度'),
    ('idc_vendor', "VARCHAR(30) NOT NULL DEFAULT ''", 'IDC/云厂商标记'),
    ('PRIMARY KEY', '(id)', ''),
]


def ip_to_int(ip_str):
    """Convert IPv4 string to 32-bit integer."""
    parts = ip_str.strip().split('.')
    if len(parts) != 4:
        return None
    try:
        return (int(parts[0]) << 24) | (int(parts[1]) << 16) | (int(parts[2]) << 8) | int(parts[3])
    except (ValueError, IndexError):
        return None


def is_china_cc(country_code):
    """Check if a 2-letter country code is China (+HK/MO/TW)."""
    return country_code in ('CN', 'HK', 'TW', 'MO')


def download_ip2region():
    """Check if ipv4_source.txt is present."""
    os.makedirs(os.path.dirname(IP2REGION_PATH), exist_ok=True)
    if os.path.exists(IP2REGION_PATH):
        size = os.path.getsize(IP2REGION_PATH)
        if size > 1_000_000:
            print(f'  Using cached: {IP2REGION_PATH}  ({size / 1_048_576:.1f} MB)')
            return True

    # Try to download from GitHub if not cached
    url = ('https://raw.githubusercontent.com/lionsoul2014/ip2region/master/data/ipv4_source.txt')
    print(f'  Downloading ip2region data...')
    req = urllib.request.Request(
        url,
        headers={'User-Agent': 'Mozilla/5.0'}
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
        with open(IP2REGION_PATH, 'wb') as f:
            f.write(data)
        print(f'  Downloaded: {len(data) / 1_048_576:.1f} MB')
        return True
    except Exception as e:
        print(f'  [ERROR] Download failed: {e}')
        return False


def parse_ip2region():
    """Parse ipv4_source.txt, return list of dicts for China records.

    Format: start_ip|end_ip|country|province|city|isp|country_code
    """
    records = []
    print(f'  Parsing {IP2REGION_PATH}...')

    with open(IP2REGION_PATH, 'r', encoding='utf-8', errors='replace') as f:
        lines_total = 0
        for line in f:
            lines_total += 1
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            parts = line.split('|')
            if len(parts) < 7:
                continue

            country_code = parts[6].strip().upper()

            if not is_china_cc(country_code):
                continue

            country = parts[2].strip()
            province = parts[3].strip() if parts[3].strip() != '0' else ''
            city = parts[4].strip() if parts[4].strip() != '0' else ''
            isp = parts[5].strip() if parts[5].strip() != '0' else ''

            # Some records have ISP-like strings in the country field
            # e.g. "中国电信" instead of "中国"
            if isp == '' and country in CHINA_ISP_OVERRIDES:
                isp = country
                country = '中国'

            rec = {
                'start_ip': parts[0].strip(),
                'end_ip': parts[1].strip(),
                'country': country,
                'province': province,
                'city': city,
                'isp': isp,
            }
            records.append(rec)

            if len(records) % 10000 == 0:
                print(f'    {len(records):,} China records parsed...')

    print(f'  Total lines: {lines_total:,}, China records: {len(records):,}')
    return records


# ============================================================
# ispip.clang.cn supplement (more granular CIDRs)
# ============================================================
ISPIP_ALL_CN_URL = 'https://ispip.clang.cn/all_cn_cidr.txt'
ISPIP_LABELS = {
    'telecom': '电信',
    'unicom':  '联通',
    'cmcc':    '移动',
    'crtc':    '铁通',
    'cernet':  '教育网',
    'other':   '其他',
}


def download_ispip_cidrs():
    """Download ispip all_cn_cidr.txt and find CIDRs not in our database.

    Returns list of (start_ip, end_ip, start_int, end_int, isp_label, isp_group).
    """
    import ipaddress as _ipaddr

    # Build our merged range tree for coverage check
    our_set = set()
    with open(IP2REGION_PATH, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            parts = line.strip().split('|')
            if len(parts) < 7:
                continue
            cc = parts[6].strip().upper()
            if cc not in ('CN', 'HK', 'TW', 'MO'):
                continue
            try:
                s = int(_ipaddr.IPv4Address(parts[0]))
                e = int(_ipaddr.IPv4Address(parts[1]))
                our_set.add((s, e))
            except Exception:
                pass

    our_merged = []
    for s, e in sorted(our_set, key=lambda x: x[0]):
        if our_merged and s <= our_merged[-1][1] + 1:
            our_merged[-1] = (our_merged[-1][0], max(our_merged[-1][1], e))
        else:
            our_merged.append((s, e))

    def in_our_db(start_int, end_int):
        for ms, me in our_merged:
            if ms <= start_int and me >= end_int:
                return True
            if ms > end_int:
                break
        return False

    # Download per-ISP CIDR lists for labeling
    isp_cidr_sets = {}
    for label, url in [
        ('telecom', 'https://ispip.clang.cn/chinatelecom_cidr.txt'),
        ('unicom', 'https://ispip.clang.cn/unicom_cnc_cidr.txt'),
        ('cmcc', 'https://ispip.clang.cn/cmcc_cidr.txt'),
        ('crtc', 'https://ispip.clang.cn/crtc_cidr.txt'),
        ('cernet', 'https://ispip.clang.cn/cernet_cidr.txt'),
        ('other', 'https://ispip.clang.cn/othernet_cidr.txt'),
    ]:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            resp = urllib.request.urlopen(req, timeout=30)
            data = resp.read().decode()
            cidrs = {l.strip() for l in data.splitlines() if l.strip() and '/' in l}
            isp_cidr_sets[label] = cidrs
        except Exception as e:
            print(f'  [WARN] Failed to download {label}: {e}')
            isp_cidr_sets[label] = set()

    # Download all_cn and find missing
    req = urllib.request.Request(ISPIP_ALL_CN_URL, headers={'User-Agent': 'Mozilla/5.0'})
    resp = urllib.request.urlopen(req, timeout=30)
    data = resp.read().decode()
    all_cidrs = [l.strip() for l in data.splitlines() if l.strip() and '/' in l]

    isp_group_map = {
        'telecom': ('telecom', '电信'),
        'unicom':  ('unicom', '联通'),
        'cmcc':    ('mobile', '移动'),
        'crtc':    ('mobile', '铁通'),
        'cernet':  ('other',  '教育网'),
        'other':   ('other',  '其他'),
    }

    new_records = []
    for c in all_cidrs:
        try:
            net = _ipaddr.IPv4Network(c, strict=False)
            s = int(net.network_address)
            e = int(net.broadcast_address)
        except Exception:
            continue

        if in_our_db(s, e):
            continue

        # Determine ISP from per-ISP sets
        group = 'other'
        label = '其他'
        for isp_key, (grp, lbl) in isp_group_map.items():
            if c in isp_cidr_sets.get(isp_key, set()):
                group = grp
                label = lbl
                break

        # The missing CIDR might be a superset of one we already added
        already = False
        for _, _, ns, ne, _, _ in new_records:
            if ns <= s and ne >= e:
                already = True
                break
        if already:
            continue

        new_records.append((
            str(net.network_address),
            str(net.broadcast_address),
            s, e, label, group
        ))

    return new_records


def match_idc(start_int, end_int):
    """Check if an IP range overlaps with known IDC ranges."""
    matched = []
    for vendor, (v_start, v_end) in IDC_IPV4_RANGES:
        if start_int <= v_end and end_int >= v_start:
            matched.append(vendor)
    return '/'.join(sorted(set(matched))) if matched else ''


def main():
    print('=' * 60)
    print('  China IPv4 Database Builder')
    print('=' * 60)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 1. Download + Parse
    print('\n[1/4] Acquiring ip2region data...')
    if not download_ip2region():
        print('[ERROR] Cannot acquire ip2region data.')
        return 1

    records = parse_ip2region()

    # 2. Enrich + Classify
    print('\n[2/4] Enriching with coordinates & ISP classification...')
    groups = {'telecom': [], 'unicom': [], 'mobile': [], 'other': []}
    geo_stats = {'district': 0, 'city': 0, 'province': 0, 'admin_center': 0}

    for i, rec in enumerate(records):
        start_ip = rec['start_ip']
        end_ip = rec['end_ip']

        start_int = ip_to_int(start_ip)
        end_int = ip_to_int(end_ip)

        if start_int is None or end_int is None:
            continue

        # ISP classification
        isp_group = classify_isp(rec['isp'])

        # Coordinate enrichment
        dc, lat, lng, geo_level, enr_prov, enr_city = enrich_ipv4(
            start_ip, rec['province'], rec['city'], rec['country']
        )
        geo_stats[geo_level] = geo_stats.get(geo_level, 0) + 1

        # IDC matching
        idc_vendor = match_idc(start_int, end_int)

        row = (
            start_ip,
            end_ip,
            start_int,
            end_int,
            rec['country'],
            enr_prov or rec['province'],
            enr_city or rec['city'],
            '',
            rec['isp'],
            dc,
            lat,
            lng,
            geo_level,
            idc_vendor,
        )

        groups[isp_group].append((start_int, row))

        if (i + 1) % 5000 == 0:
            print(f'    Processed {i + 1:,}/{len(records):,}')

    # Sort each group by start_ip_int
    for key in groups:
        groups[key].sort(key=lambda x: x[0])

    # 2b. Supplement with ispip.clang.cn CIDRs not already covered
    print('\n[2b/4] Supplementing with ispip.clang.cn CIDRs...')
    try:
        ispip_records = download_ispip_cidrs()
        if ispip_records:
            print(f'  Found {len(ispip_records)} new CIDRs not in our database')
        else:
            print(f'  All ispip CIDRs are already covered')
    except Exception as e:
        print(f'  [WARN] ispip supplement failed: {e}')
        ispip_records = []

    # Add ispip records to other group (no prov/city/coords available)
    ispip_added = 0
    for start_ip, end_ip, start_int, end_int, isp_label, isp_group in ispip_records:
        row = (
            start_ip, end_ip, start_int, end_int,
            '中国', '', '', '',
            isp_label, '',
            None, None,
            'admin_center', '',
        )
        groups[isp_group].append((start_int, row))
        ispip_added += 1

    if ispip_added:
        groups['other'].sort(key=lambda x: x[0])
        print(f'  Added {ispip_added} ispip CIDRs (to other ISP group)')

    # 3. Write SQL files
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

        filename = f'china_ipv4_{isp_group}.sql'
        path = os.path.join(OUTPUT_DIR, filename)
        writer = SQLWriter(
            path,
            f'china_ipv4_{isp_group}',
            IPV4_COLUMNS,
            comment=f'中国 IPv4 归属地 — {isp_labels[isp_group]}',
        )

        for _, row in rows_list:
            writer.add_row(row)

        count = writer.close()
        size = os.path.getsize(path)
        results[isp_group] = count
        print(f'  {filename}: {count:,} rows  ({size / 1_048_576:.1f} MB)')

    # 4. Write IDC table
    print('\n[4/4] Writing IDC reference table...')
    idc_rows = []
    for vendor, (v_start, v_end) in IDC_IPV4_RANGES:
        import ipaddress
        try:
            start_ip = str(ipaddress.IPv4Address(v_start))
            end_ip = str(ipaddress.IPv4Address(v_end))
        except Exception:
            start_ip = ''
            end_ip = ''
        idc_rows.append((vendor, start_ip, end_ip, v_start, v_end, ''))

    idc_path = os.path.join(OUTPUT_DIR, 'china_ipv4_idc.sql')
    idc_count = write_idc_table(idc_path, 'china_ipv4_idc', idc_rows, ip_version=4,
                                comment='中国 IDC/云厂商 IPv4 IP 段')
    idc_size = os.path.getsize(idc_path)
    print(f'  china_ipv4_idc.sql: {idc_count} rows  ({idc_size / 1024:.1f} KB)')

    # Output summary
    print()
    print('=' * 60)
    print('  Build Complete!')
    print('=' * 60)
    total = sum(results.values())
    for g in ['telecom', 'unicom', 'mobile', 'other']:
        c = results.get(g, 0)
        pct = (c / total * 100) if total else 0
        print(f'  {isp_labels[g]:8s}: {c:>8,} rows  ({pct:5.1f}%)')
    print(f'  {"IDC参考":8s}: {idc_count:>8,}')
    print(f'  {"合计":8s}: {total + idc_count:>8,}')

    # Geo stats
    print()
    print('  Coordinate precision:')
    for level in ['district', 'city', 'province', 'admin_center']:
        c = geo_stats.get(level, 0)
        print(f'    {level:12s}: {c:>8,}  ({c / total * 100:5.1f}%)')

    total_with_coords = sum(
        v for k, v in geo_stats.items() if k != 'admin_center'
    )
    print(f'    {"coverage":12s}: {total_with_coords / total * 100:.1f}%')

    # Write VERSION.txt
    version_path = os.path.join(OUTPUT_DIR, 'VERSION.txt')
    with open(version_path, 'w', encoding='utf-8') as f:
        f.write(f'Build time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
        f.write(f'IPv4 records: {total}\n')
        for g in ['telecom', 'unicom', 'mobile', 'other']:
            f.write(f'  {isp_labels[g]}: {results.get(g, 0)}\n')
        f.write(f'IDC records: {idc_count}\n')

    return 0


if __name__ == '__main__':
    sys.exit(main())
