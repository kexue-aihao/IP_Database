#!/usr/bin/env python3
"""
Build global (non-China) IPv4/IPv6 geolocation MMDB databases.

Data sources:
  - DB-IP City Lite: global IP geolocation (country/region/city/lat/lng)
  - Cloud provider aggregator: IDC classification

Output (MMDB format):
  output/global_ipv4_idc.mmdb         # Global IPv4 datacenter IPs
  output/global_ipv4_residential.mmdb  # Global IPv4 residential IPs
  output/global_ipv6_idc.mmdb         # Global IPv6 datacenter IPs
  output/global_ipv6_residential.mmdb  # Global IPv6 residential IPs

Excluded: CN, HK, TW, MO IP ranges.
"""

import csv
import gzip
import ipaddress
import json
import os
import sys
import urllib.request
from datetime import datetime
from netaddr import IPSet, IPNetwork
from mmdb_writer import MMDBWriter

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE, 'data')
OUTPUT_DIR = os.path.join(BASE, 'output')

# DB-IP City Lite URL pattern
CURRENT_MONTH = '2026-07'
DBIP_URL = f'https://download.db-ip.com/free/dbip-city-lite-{CURRENT_MONTH}.csv.gz'
DBIP_PATH = os.path.join(DATA_DIR, f'dbip-city-lite-{CURRENT_MONTH}.csv.gz')

# Cloud provider ranges aggregator
CLOUD_RANGES_URL = 'https://raw.githubusercontent.com/tobilg/public-cloud-provider-ip-ranges/main/data/providers/all.json'
CLOUD_RANGES_PATH = os.path.join(DATA_DIR, 'global_cloud_providers.json')

# IPv6 cloud provider data sources (aggregator doesn't include IPv6)
IPV6_CLOUD_SOURCES = [
    ('AWS', 'https://ip-ranges.amazonaws.com/ip-ranges.json', 'json', ['ipv6_prefixes', 'ipv6_prefix']),
    ('Cloudflare', 'https://www.cloudflare.com/ips-v6', 'text', None),
    ('GoogleCloud', 'https://www.gstatic.com/ipranges/cloud.json', 'json', ['prefixes', 'ipv6Prefix']),
]

# Country codes to exclude (China + Hong Kong + Macau + Taiwan)
EXCLUDE_CC = {'CN', 'HK', 'TW', 'MO'}

# Continent mapping (ISO 3166 country code -> continent code)
# Only major country codes needed for the MMDB field
CONTINENT_MAP = {
    # North America
    'US': 'NA', 'CA': 'NA', 'MX': 'NA', 'GL': 'NA', 'BM': 'NA',
    # South America
    'BR': 'SA', 'AR': 'SA', 'CL': 'SA', 'CO': 'SA', 'PE': 'SA', 'UY': 'SA', 'VE': 'SA',
    # Europe
    'GB': 'EU', 'DE': 'EU', 'FR': 'EU', 'IT': 'EU', 'ES': 'EU', 'NL': 'EU',
    'CH': 'EU', 'SE': 'EU', 'NO': 'EU', 'DK': 'EU', 'FI': 'EU', 'RU': 'EU',
    'PL': 'EU', 'AT': 'EU', 'BE': 'EU', 'IE': 'EU', 'PT': 'EU', 'GR': 'EU',
    'CZ': 'EU', 'HU': 'EU', 'RO': 'EU', 'UA': 'EU',
    # Asia
    'JP': 'AS', 'KR': 'AS', 'IN': 'AS', 'SG': 'AS', 'HK': 'AS',
    'TW': 'AS', 'MO': 'AS', 'CN': 'AS',
    # Oceania
    'AU': 'OC', 'NZ': 'OC',
    # Africa
    'ZA': 'AF', 'NG': 'AF', 'KE': 'AF', 'EG': 'AF',
    # Middle East
    'AE': 'AS', 'SA': 'AS', 'IL': 'AS',
    # South America default
    'DEFAULT': 'NA',
}

BATCH_SIZE = 5000  # rows per MMDB writer flush (higher = faster, more memory)


def download_file(url, path, label=''):
    """Download a file if not already cached."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        sz = os.path.getsize(path)
        print(f'  Using cached {label}: {sz / 1048576:.1f} MB' if sz > 1048576
              else f'  Using cached {label}: {sz / 1024:.1f} KB')
        return True

    print(f'  Downloading {label}...')
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0.0.0'
    })
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = resp.read()
        with open(path, 'wb') as f:
            f.write(data)
        print(f'  Downloaded {label}: {len(data) / 1048576:.1f} MB')
        return True
    except Exception as e:
        print(f'  [ERROR] Download failed: {e}')
        return False


def build_idc_blocks():
    """Load pre-optimized cloud provider ranges from data/global_cloud_providers.json.

    Returns two lists: idc_v4, idc_v6  each of (start_int, end_int, vendor).
    If the file doesn't exist, downloads and optimizes it.
    """
    if not os.path.exists(CLOUD_RANGES_PATH):
        # Download raw data
        raw_path = os.path.join(DATA_DIR, 'raw_cloud_providers.json')
        if not download_file(CLOUD_RANGES_URL, raw_path, 'cloud provider ranges'):
            return [], []

        with open(raw_path, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)

        # Parse and merge
        all_blocks = []
        for entry in raw_data:
            cidr_str = entry.get('cidr_block', '')
            provider = entry.get('cloud_provider', 'AWS')
            if not cidr_str:
                continue
            try:
                if ':' in cidr_str:
                    net = ipaddress.IPv6Network(cidr_str, strict=False)
                    all_blocks.append({
                        'v': 6,
                        's': int(net.network_address),
                        'e': int(net.broadcast_address),
                        'p': provider,
                    })
                else:
                    net = ipaddress.IPv4Network(cidr_str, strict=False)
                    all_blocks.append({
                        'v': 4,
                        's': int(net.network_address),
                        'e': int(net.broadcast_address),
                        'p': provider,
                    })
            except Exception:
                pass

        # Sort and merge adjacent from same provider
        all_blocks.sort(key=lambda x: (x['v'], x['s']))

        merged_v4 = []
        merged_v6 = []
        for b in all_blocks:
            target = merged_v6 if b['v'] == 6 else merged_v4
            if target and b['s'] <= target[-1]['e'] + 1 and target[-1]['p'] == b['p']:
                target[-1]['e'] = max(target[-1]['e'], b['e'])
            else:
                target.append(b)

        print(f'  Aggregator data: IPv4={len(merged_v4):,}, IPv6={len(merged_v6):,}')

        # Fetch IPv6 cloud data from individual providers (aggregator has none)
        print(f'  Fetching IPv6 cloud data from individual providers...')
        for provider, url, fmt, path_info in IPV6_CLOUD_SOURCES:
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                resp = urllib.request.urlopen(req, timeout=60)
                count_before = len(merged_v6)

                if fmt == 'text':
                    data = resp.read().decode()
                    for line in data.splitlines():
                        line = line.strip()
                        if line and '/' in line and ':' in line:
                            net = ipaddress.IPv6Network(line, strict=False)
                            merged_v6.append({
                                'v': 6, 's': int(net.network_address),
                                'e': int(net.broadcast_address), 'p': provider,
                            })
                elif fmt == 'json' and path_info:
                    json_data = json.loads(resp.read())
                    items = json_data
                    for key in path_info[:-1]:
                        items = items.get(key, [])
                    cidr_key = path_info[-1]
                    for item in items:
                        cidr = item.get(cidr_key, '') if isinstance(item, dict) else ''
                        if cidr and ':' in cidr:
                            net = ipaddress.IPv6Network(cidr, strict=False)
                            merged_v6.append({
                                'v': 6, 's': int(net.network_address),
                                'e': int(net.broadcast_address), 'p': provider,
                            })

                added = len(merged_v6) - count_before
                print(f'    {provider}: +{added} IPv6 prefixes')
            except Exception as e:
                print(f'    [WARN] {provider} IPv6 fetch failed: {e}')

        # Re-sort and merge IPv6 blocks
        merged_v6.sort(key=lambda x: x['s'])
        merged_v6_compact = []
        for b in merged_v6:
            if merged_v6_compact and b['s'] <= merged_v6_compact[-1]['e'] + 1 and merged_v6_compact[-1]['p'] == b['p']:
                merged_v6_compact[-1]['e'] = max(merged_v6_compact[-1]['e'], b['e'])
            else:
                merged_v6_compact.append(b)
        merged_v6 = merged_v6_compact

        # Save optimized format
        with open(CLOUD_RANGES_PATH, 'w') as f:
            json.dump({
                'v4': [(b['s'], b['e'], b['p']) for b in merged_v4],
                'v6': [(b['s'], b['e'], b['p']) for b in merged_v6],
            }, f)
        print(f'  Optimized: IPv4={len(merged_v4):,} blocks, IPv6={len(merged_v6):,} blocks')

    # Load optimized format
    with open(CLOUD_RANGES_PATH, 'r') as f:
        data = json.load(f)

    v4_blocks = [(s, e, p) for s, e, p in data.get('v4', [])]
    v6_blocks = [(s, e, p) for s, e, p in data.get('v6', [])]

    print(f'  IDC ranges: IPv4={len(v4_blocks):,}, IPv6={len(v6_blocks):,}')
    return v4_blocks, v6_blocks


def is_idc(start_int, end_int, idc_blocks):
    """Check if an IP range falls within any IDC block.

    Uses binary search on sorted IDC ranges.
    """
    import bisect
    start_ints = [b[0] for b in idc_blocks]
    idx = bisect.bisect_right(start_ints, start_int) - 1
    if idx < 0:
        idx = 0

    # Scan nearby entries
    for i in range(max(0, idx - 2), min(len(idc_blocks), idx + 5)):
        s, e, vendor = idc_blocks[i]
        if s <= start_int and e >= end_int:
            return True, vendor
        if s <= end_int and e >= start_int:
            # Partial overlap — still counts as IDC
            return True, vendor
        if s > end_int:
            break

    return False, ''


def ipv6_to_hex(ip_str):
    """Convert an IPv6 string to a 32-char lowercase hex string."""
    return ipaddress.IPv6Address(ip_str).exploded.replace(':', '').lower()


def ip_range_to_cidrs(start_ip, end_ip, version=4):
    """Convert an IP range to the minimal set of CIDR blocks."""
    try:
        if version == 4:
            start = ipaddress.IPv4Address(start_ip)
            end = ipaddress.IPv4Address(end_ip)
        else:
            start = ipaddress.IPv6Address(start_ip)
            end = ipaddress.IPv6Address(end_ip)
        return [str(n) for n in ipaddress.summarize_address_range(start, end)]
    except (ValueError, ipaddress.AddressValueError):
        return []


def get_continent(country_code):
    """Get continent code from country code."""
    return CONTINENT_MAP.get(country_code.upper(), 'NA')


def process_dbip(idc_v4, idc_v6):
    """Download & parse DB-IP CSV, classify, and write MMDB files.

    Streaming process: reads line by line from gzipped CSV,
    accumulates batches, writes to MMDB in chunks.
    """
    if not download_file(DBIP_URL, DBIP_PATH, 'DB-IP City Lite'):
        print('  [ERROR] Cannot acquire DB-IP data.')
        return False

    # Create writers
    writers = {
        'v4_res': MMDBWriter(ip_version=4, database_type='GlobalIP-Residential',
                             languages=['en'], description={'en': 'Global IPv4 Residential IP Geolocation'}),
        'v4_idc': MMDBWriter(ip_version=4, database_type='GlobalIP-IDC',
                             languages=['en'], description={'en': 'Global IPv4 Datacenter IP Geolocation'}),
        'v6_res': MMDBWriter(ip_version=6, database_type='GlobalIPv6-Residential',
                             languages=['en'], description={'en': 'Global IPv6 Residential IP Geolocation'}),
        'v6_idc': MMDBWriter(ip_version=6, database_type='GlobalIPv6-IDC',
                             languages=['en'], description={'en': 'Global IPv6 Datacenter IP Geolocation'}),
    }

    batch_v4_res = []
    batch_v4_idc = []
    batch_v6_res = []
    batch_v6_idc = []

    counts = {'v4_res': 0, 'v4_idc': 0, 'v6_res': 0, 'v6_idc': 0}
    skipped = 0
    total = 0

    print(f'  Parsing {DBIP_PATH}...')

    with gzip.open(DBIP_PATH, 'rt', encoding='utf-8', errors='replace') as f:
        reader = csv.reader(f)
        for row in reader:
            total += 1
            if len(row) < 7:
                continue

            start_ip, end_ip = row[0].strip(), row[1].strip()
            country_code = row[2].strip().upper()

            # Skip China + HK/MO/TW
            if country_code in EXCLUDE_CC:
                skipped += 1
                continue

            # Detect IP version
            is_v6 = ':' in start_ip
            version = 6 if is_v6 else 4

            # Get coordinate data
            stateprov = row[3].strip() if len(row) > 3 else ''
            city = row[4].strip() if len(row) > 4 else ''
            try:
                latitude = float(row[5]) if row[5].strip() else None
            except (ValueError, IndexError):
                latitude = None
            try:
                longitude = float(row[6]) if row[6].strip() else None
            except (ValueError, IndexError):
                longitude = None

            continent = get_continent(country_code)

            data = {
                'country_code': country_code,
                'continent': continent,
            }
            if stateprov:
                data['region'] = stateprov
            if city:
                data['city'] = city
            if latitude is not None:
                data['latitude'] = latitude
            if longitude is not None:
                data['longitude'] = longitude

            # Classify IDC vs residential
            if version == 4:
                try:
                    s_int = int(ipaddress.IPv4Address(start_ip))
                    e_int = int(ipaddress.IPv4Address(end_ip))
                except Exception:
                    continue
                is_idc_flag, vendor = is_idc(s_int, e_int, idc_v4)
                if is_idc_flag:
                    data['vendor'] = vendor
                    batch_v4_idc.append((start_ip, end_ip, data))
                    counts['v4_idc'] += 1
                    if len(batch_v4_idc) >= BATCH_SIZE:
                        _flush_v4(writers['v4_idc'], batch_v4_idc)
                        batch_v4_idc = []
                else:
                    batch_v4_res.append((start_ip, end_ip, data))
                    counts['v4_res'] += 1
                    if len(batch_v4_res) >= BATCH_SIZE:
                        _flush_v4(writers['v4_res'], batch_v4_res)
                        batch_v4_res = []
            else:
                try:
                    s_hex = ipv6_to_hex(start_ip)
                    e_hex = ipv6_to_hex(end_ip)
                    s_int = int(ipaddress.IPv6Address(start_ip))
                    e_int = int(ipaddress.IPv6Address(end_ip))
                except Exception:
                    continue
                is_idc_flag, vendor = is_idc(s_int, e_int, idc_v6)
                if is_idc_flag:
                    data['vendor'] = vendor
                    batch_v6_idc.append((start_ip, end_ip, data))
                    counts['v6_idc'] += 1
                    if len(batch_v6_idc) >= BATCH_SIZE:
                        _flush_v6(writers['v6_idc'], batch_v6_idc)
                        batch_v6_idc = []
                else:
                    batch_v6_res.append((start_ip, end_ip, data))
                    counts['v6_res'] += 1
                    if len(batch_v6_res) >= BATCH_SIZE:
                        _flush_v6(writers['v6_res'], batch_v6_res)
                        batch_v6_res = []

            if total % 500000 == 0:
                print(f'    Progress: {total:,} rows, skipped CN: {skipped:,}')

    # Flush remaining batches
    _flush_v4(writers['v4_idc'], batch_v4_idc)
    _flush_v4(writers['v4_res'], batch_v4_res)
    _flush_v6(writers['v6_idc'], batch_v6_idc)
    _flush_v6(writers['v6_res'], batch_v6_res)

    print(f'  Total rows: {total:,}, skipped (CN/HK/MO/TW): {skipped:,}')
    print(f'  IPv4 residential: {counts["v4_res"]:,}, IPv4 IDC: {counts["v4_idc"]:,}')
    print(f'  IPv6 residential: {counts["v6_res"]:,}, IPv6 IDC: {counts["v6_idc"]:,}')

    # Write MMDB files
    for key, label in [('v4_idc', 'global_ipv4_idc.mmdb'),
                        ('v4_res', 'global_ipv4_residential.mmdb'),
                        ('v6_idc', 'global_ipv6_idc.mmdb'),
                        ('v6_res', 'global_ipv6_residential.mmdb')]:
        path = os.path.join(OUTPUT_DIR, label)
        print(f'  Writing {label}...', end=' ')
        writers[key].to_db_file(path)
        sz = os.path.getsize(path)
        print(f'{sz/1024/1024:.1f} MB')

    return True


def _flush_v4(writer, batch):
    """Flush a batch of IPv4 records to the MMDB writer."""
    for start_ip, end_ip, data in batch:
        cidrs = ip_range_to_cidrs(start_ip, end_ip, 4)
        for c in cidrs:
            try:
                writer.insert_network(IPSet(IPNetwork(c)), data)
            except Exception:
                pass


def _flush_v6(writer, batch):
    """Flush a batch of IPv6 records to the MMDB writer."""
    for start_ip, end_ip, data in batch:
        cidrs = ip_range_to_cidrs(start_ip, end_ip, 6)
        for c in cidrs:
            try:
                writer.insert_network(IPSet(IPNetwork(c)), data)
            except Exception:
                pass


def main():
    print('=' * 60)
    print('  Global IP Geolocation MMDB Builder')
    print(f'  Source: DB-IP City Lite ({CURRENT_MONTH})')
    print('=' * 60)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 1. Build IDC lookup blocks
    print('\n[1/3] Loading cloud provider IDC ranges...')
    idc_v4, idc_v6 = build_idc_blocks()
    print(f'  IDC blocks ready: IPv4={len(idc_v4):,}, IPv6={len(idc_v6):,}')

    # 2. Process DB-IP data
    print('\n[2/3] Processing DB-IP City Lite data...')
    ok = process_dbip(idc_v4, idc_v6)
    if not ok:
        return 1

    # 3. Verify
    print('\n[3/3] Verification...')
    import maxminddb
    test_cases = [
        ('global_ipv4_residential.mmdb', '8.8.8.8', 'US'),
        ('global_ipv4_idc.mmdb', '52.84.0.1', 'AWS'),
        ('global_ipv6_idc.mmdb', '2600:9000::1', 'AWS'),
    ]
    for fname, ip, expected in test_cases:
        path = os.path.join(OUTPUT_DIR, fname)
        if os.path.exists(path):
            reader = maxminddb.open_database(path)
            result = reader.get(ip)
            if result:
                print(f'  {fname:35s} {ip:15s} -> {result.get("country_code","?"):2s} '
                      f'{result.get("region",""):12s} {result.get("city",""):15s} '
                      f'({result.get("latitude","?"):>8}, {result.get("longitude","?")})')
            else:
                print(f'  {fname:35s} {ip:15s} -> NOT FOUND')
            reader.close()

    print(f'\n{"=" * 60}')
    print(f'  Done!')
    print(f'  Output files:')
    for f in sorted(os.listdir(OUTPUT_DIR)):
        if f.startswith('global_ipv') and f.endswith('.mmdb'):
            sz = os.path.getsize(os.path.join(OUTPUT_DIR, f))
            print(f'    {f:40s} {sz/1024/1024:.1f} MB')
    print(f'{"=" * 60}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
