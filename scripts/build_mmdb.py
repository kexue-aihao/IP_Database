#!/usr/bin/env python3
"""
Convert China IP SQL database to MaxMind MMDB format.

Reads from output/*.sql files, writes china_ipv4.mmdb and china_ipv6.mmdb.
The resulting MMDB files are standard MaxMind-compatible and can be queried
with any mmdb client library (maxminddb, GeoIP2, etc.)

Output MMDB record fields:
  - province:   Province name (e.g. "广东")
  - city:       City name (e.g. "广州")
  - district:   District name (e.g. "天河区")
  - isp:        ISP name (e.g. "中国电信")
  - latitude:   Latitude (WGS-84, city/district-center)
  - longitude:  Longitude (WGS-84)
  - geo_level:  Coordinate precision (district/city/province)
  - division_code: GB/T 2260 division code (6 digits)

Usage:
  python scripts/build_mmdb.py                   # Convert all SQL files
  python scripts/build_mmdb.py --ipv4-only        # IPv4 only
  python scripts/build_mmdb.py --ipv6-only        # IPv6 only
  python scripts/build_mmdb.py --split            # One MMDB per ISP
  python scripts/build_mmdb.py --idc              # Convert IDC SQL too
"""

import ipaddress
import os
import re
import sys

from netaddr import IPSet, IPNetwork
from mmdb_writer import MMDBWriter

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE, 'output')

BATCH_SIZE = 1000  # rows before flush


def ip_range_to_cidrs(start_ip, end_ip):
    """Convert an IP range to the minimal set of CIDR blocks."""
    try:
        start = ipaddress.IPv4Address(start_ip)
        end = ipaddress.IPv4Address(end_ip)
        return [str(n) for n in ipaddress.summarize_address_range(start, end)]
    except (ValueError, ipaddress.AddressValueError):
        return []


def fast_parse(filepath):
    """Fast parse of our SQL format. Returns (col_names, rows).

    Each data line is:  ('val','val',int,float,...)  or  ,('val','val',...)
    The id column (AUTO_INCREMENT) is NOT in the INSERT.
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Get column names from INSERT INTO line
    m_cols = re.search(r'INSERT INTO\s+`[^`]+`\s*\(([^)]+)\)\s*VALUES', content)
    if not m_cols:
        return None, []

    col_str = m_cols.group(1)
    col_names = [c.strip().strip('`') for c in col_str.split(',')]

    # Extract all value tuples from the VALUES section
    rows = []
    pos = m_cols.end()

    while pos < len(content):
        paren_pos = content.find('(', pos)
        if paren_pos < 0:
            break

        # Find matching closing paren
        depth = 1
        end = paren_pos + 1
        while depth > 0 and end < len(content):
            if content[end] == '(':
                depth += 1
            elif content[end] == ')':
                depth -= 1
            end += 1

        if depth != 0:
            break

        raw = content[paren_pos + 1:end - 1]
        pos = end

        # Parse values
        vals = []
        vcur = ''
        in_q = False
        for ch in raw:
            if ch == "'":
                in_q = not in_q
                vcur += ch
            elif ch == ',' and not in_q:
                vals.append(vcur.strip())
                vcur = ''
            else:
                vcur += ch
        if vcur:
            vals.append(vcur.strip())

        vals = [v.strip("'") for v in vals]
        if len(vals) == len(col_names):
            rows.append(vals)

    return col_names, rows


def write_batch_v4(writer, batch):
    """Write a batch of records to the IPv4 MMDB writer."""
    count = 0
    for rec in batch:
        start_ip = rec.get('start_ip', '')
        end_ip = rec.get('end_ip', '')
        if not start_ip or not end_ip:
            continue

        cidrs = ip_range_to_cidrs(start_ip, end_ip)
        if not cidrs:
            continue

        data = {}
        for field in ('province', 'city', 'district', 'isp',
                      'latitude', 'longitude', 'geo_level',
                      'division_code', 'country', 'idc_vendor'):
            v = rec.get(field, '')
            if v and v != 'NULL' and v != '':
                if field in ('latitude', 'longitude'):
                    try:
                        data[field] = float(v)
                    except ValueError:
                        pass
                else:
                    data[field] = v

        for cidr_str in cidrs:
            try:
                writer.insert_network(IPSet(IPNetwork(cidr_str)), data)
                count += 1
            except Exception:
                pass

    return count


def write_batch_v6(writer, batch):
    """Write a batch of IPv6 records to MMDB."""
    count = 0
    for rec in batch:
        cidr = rec.get('cidr', '')
        if not cidr:
            continue

        data = {}
        for field in ('province', 'city', 'district', 'isp',
                      'latitude', 'longitude', 'geo_level',
                      'division_code', 'country', 'idc_vendor'):
            v = rec.get(field, '')
            if v and v != 'NULL' and v != '':
                if field in ('latitude', 'longitude'):
                    try:
                        data[field] = float(v)
                    except ValueError:
                        pass
                else:
                    data[field] = v

        try:
            writer.insert_network(IPSet(IPNetwork(cidr)), data)
            count += 1
        except Exception:
            pass

    return count


def convert_v4_into(sql_path, writer):
    """Convert IPv4 SQL file, writing data into an existing writer."""
    print(f'  Reading {os.path.basename(sql_path)}...')

    col_names, rows = fast_parse(sql_path)
    if col_names is None or not rows:
        print(f'  [WARN] No data parsed from {sql_path}')
        return 0, 0

    total_cidrs = 0
    batch = []
    for vals in rows:
        data = dict(zip(col_names, vals))
        batch.append(data)
        if len(batch) >= BATCH_SIZE:
            total_cidrs += write_batch_v4(writer, batch)
            batch = []

    if batch:
        total_cidrs += write_batch_v4(writer, batch)

    print(f'    Rows: {len(rows)} -> CIDRs: {total_cidrs}')
    return len(rows), total_cidrs


def convert_v6_into(sql_path, writer):
    """Convert IPv6 SQL file into an existing writer."""
    print(f'  Reading {os.path.basename(sql_path)}...')

    col_names, rows = fast_parse(sql_path)
    if col_names is None or not rows:
        print(f'  [WARN] No data parsed from {sql_path}')
        return 0, 0

    total_cidrs = 0
    batch = []
    for vals in rows:
        data = dict(zip(col_names, vals))
        batch.append(data)
        if len(batch) >= BATCH_SIZE:
            total_cidrs += write_batch_v6(writer, batch)
            batch = []

    if batch:
        total_cidrs += write_batch_v6(writer, batch)

    print(f'    Rows: {len(rows)} -> CIDRs: {total_cidrs}')
    return len(rows), total_cidrs


def _describe(data):
    """Pretty-print MMDB record from reader.get()."""
    if not data:
        return '(not found)'
    parts = []
    for k in ('province', 'city', 'district', 'isp', 'country'):
        v = data.get(k, '')
        if v:
            parts.append(v)
    coord = ''
    if data.get('latitude') and data.get('longitude'):
        coord = f' ({data["latitude"]}, {data["longitude"]})'
    return ' '.join(parts) + coord


def convert_idc_to_mmdb():
    """Convert IDC SQL files to MMDB format (vendor-lookup tables)."""
    idc_files = {
        'china_ipv4_idc.sql': ('china_ipv4_idc.mmdb', 4),
        'china_ipv6_idc.sql': ('china_ipv6_idc.mmdb', 6),
    }

    for sql_name, (mmdb_name, ipv) in idc_files.items():
        sql_path = os.path.join(OUTPUT_DIR, sql_name)
        if not os.path.exists(sql_path):
            print(f'  [WARN] {sql_name} not found, skipping')
            continue

        col_names, rows = fast_parse(sql_path)
        if not rows:
            print(f'  [WARN] No data in {sql_name}')
            continue

        writer = MMDBWriter(
            ip_version=ipv,
            database_type=f'ChinaIDC-IPv{ipv}',
            languages=['zh-CN'],
            description={'zh-CN': '中国IDC/云厂商IP段'}
        )

        count = 0
        for vals in rows:
            data = dict(zip(col_names, vals))
            if ipv == 4:
                cidrs = ip_range_to_cidrs(
                    data.get('start_ip', ''),
                    data.get('end_ip', '')
                )
            else:
                cidrs = [data.get('cidr', data.get('start_ip', ''))]

            for c in cidrs:
                try:
                    writer.insert_network(IPSet(IPNetwork(c)), data)
                    count += 1
                except Exception:
                    pass

        mmdb_path = os.path.join(OUTPUT_DIR, mmdb_name)
        writer.to_db_file(mmdb_path)
        size = os.path.getsize(mmdb_path)
        print(f'  {mmdb_name}: {count} CIDRs ({size/1024:.1f} KB)')


def main():
    ipv4_only = '--ipv4-only' in sys.argv
    ipv6_only = '--ipv6-only' in sys.argv
    split_mode = '--split' in sys.argv
    idc_mode = '--idc' in sys.argv or True  # always convert IDC

    print('=' * 60)
    print('  MMDB Converter -- SQL -> MaxMind MMDB')
    print('=' * 60)

    # ============================================================
    # IDC tables (always converted)
    # ============================================================
    print('\n[0/3] Converting IDC tables...')
    convert_idc_to_mmdb()

    if split_mode:
        # ============================================================
        # Per-ISP split mode
        # ============================================================
        if not ipv6_only:
            print('\n[1/3] Converting IPv4 (per ISP)...')
            v4_isp = ['telecom', 'unicom', 'mobile', 'other']
            for isp in v4_isp:
                sql_path = os.path.join(OUTPUT_DIR, f'china_ipv4_{isp}.sql')
                if not os.path.exists(sql_path):
                    continue
                mmdb_path = os.path.join(OUTPUT_DIR, f'china_ipv4_{isp}.mmdb')
                writer = MMDBWriter(
                    ip_version=4,
                    database_type=f'ChinaIP-{isp}',
                    languages=['zh-CN'],
                    description={'zh-CN': f'中国IPv4{isp}归属地'}
                )
                r, c = convert_v4_into(sql_path, writer)
                writer.to_db_file(mmdb_path)
                print(f'    -> {os.path.basename(mmdb_path)} ({c} CIDRs, '
                      f'{os.path.getsize(mmdb_path)/1024:.1f} KB)')

        if not ipv4_only:
            print('\n[2/3] Converting IPv6 (per ISP)...')
            v6_isp = ['telecom', 'unicom', 'mobile', 'other']
            for isp in v6_isp:
                sql_path = os.path.join(OUTPUT_DIR, f'china_ipv6_{isp}.sql')
                if not os.path.exists(sql_path):
                    continue
                mmdb_path = os.path.join(OUTPUT_DIR, f'china_ipv6_{isp}.mmdb')
                writer = MMDBWriter(
                    ip_version=6,
                    database_type=f'ChinaIP6-{isp}',
                    languages=['zh-CN'],
                    description={'zh-CN': f'中国IPv6{isp}归属地'}
                )
                r, c = convert_v6_into(sql_path, writer)
                writer.to_db_file(mmdb_path)
                print(f'    -> {os.path.basename(mmdb_path)} ({c} CIDRs, '
                      f'{os.path.getsize(mmdb_path)/1024:.1f} KB)')

    else:
        # ============================================================
        # Combined mode (already working)
        # ============================================================
        if not ipv6_only:
            print('\n[1/3] Converting IPv4 (combined)...')
            v4_files = [
                'china_ipv4_telecom.sql',
                'china_ipv4_unicom.sql',
                'china_ipv4_mobile.sql',
                'china_ipv4_other.sql',
            ]
            writer4 = MMDBWriter(
                ip_version=4,
                database_type='ChinaIP-GeoLite',
                languages=['zh-CN'],
                description={'zh-CN': '中国IPv4归属地数据库'}
            )
            total_rows = total_cidrs = 0
            for fname in v4_files:
                path = os.path.join(OUTPUT_DIR, fname)
                if not os.path.exists(path):
                    continue
                r, c = convert_v4_into(path, writer4)
                total_rows += r
                total_cidrs += c
            mmdb_path = os.path.join(OUTPUT_DIR, 'china_ipv4.mmdb')
            writer4.to_db_file(mmdb_path)
            print(f'  IPv4 MMDB: {os.path.basename(mmdb_path)} ({total_cidrs:,} CIDRs, '
                  f'{os.path.getsize(mmdb_path)/1024/1024:.1f} MB)')

        if not ipv4_only:
            print('\n[2/3] Converting IPv6 (combined)...')
            v6_files = [
                'china_ipv6_telecom.sql',
                'china_ipv6_unicom.sql',
                'china_ipv6_mobile.sql',
                'china_ipv6_other.sql',
            ]
            writer6 = MMDBWriter(
                ip_version=6,
                database_type='ChinaIP-GeoLite-IPv6',
                languages=['zh-CN'],
                description={'zh-CN': '中国IPv6归属地数据库'}
            )
            total_rows6 = total_cidrs6 = 0
            for fname in v6_files:
                path = os.path.join(OUTPUT_DIR, fname)
                if not os.path.exists(path):
                    continue
                r, c = convert_v6_into(path, writer6)
                total_rows6 += r
                total_cidrs6 += c
            mmdb_path = os.path.join(OUTPUT_DIR, 'china_ipv6.mmdb')
            writer6.to_db_file(mmdb_path)
            print(f'  IPv6 MMDB: {os.path.basename(mmdb_path)} ({total_cidrs6:,} CIDRs, '
                  f'{os.path.getsize(mmdb_path)/1024/1024:.1f} MB)')

    # ============================================================
    # List all .mmdb files
    # ============================================================
    mmdb_files = sorted(f for f in os.listdir(OUTPUT_DIR) if f.endswith('.mmdb'))
    print(f'\n[3/3] Output files in {OUTPUT_DIR}/')
    for f in mmdb_files:
        sz = os.path.getsize(os.path.join(OUTPUT_DIR, f))
        print(f'  {f:35s} {sz/1024:>10.1f} KB')
    print(f'  {"TOTAL":35s} {sum(os.path.getsize(os.path.join(OUTPUT_DIR,f)) for f in mmdb_files)/1024:>10.1f} KB')

    print(f'\n{"=" * 60}')
    print(f'  Complete!')
    print(f'  Query example:')
    print(f'    python -c "import maxminddb; '
           f'r=maxminddb.open_database(\'output/china_ipv4.mmdb\'); '
           f'print(_describe(r.get(\'1.0.1.0\')))"')
    print(f'{"=" * 60}')


if __name__ == '__main__':
    main()
