#!/usr/bin/env python3
"""
S7: IPv4 Residential MMDB Builder (Phase 7 of Global Pipeline)
Builds global_ipv4_residential.mmdb from fused data, keeping only residential records.
Nested agents: 10 build steps (S7.1-S7.10).
"""
import bisect, csv, ipaddress, json, os, sys, io
from datetime import datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE, 'data')
OUTPUT_DIR = os.path.join(BASE, 'output')
GLOBAL_DIR = os.path.join(DATA_DIR, 'global')
FUSED_PATH = os.path.join(GLOBAL_DIR, 'fusion', 'global_fused_v4.csv')
IDC_PATH = os.path.join(GLOBAL_DIR, 'idc', 'idc_all.csv')
OUTPUT_MMDB = os.path.join(OUTPUT_DIR, 'global_ipv4_residential.mmdb')

sys.path.insert(0, os.path.join(BASE, 'scripts'))
try:
    from mmdb_writer import MMDBWriter
except ImportError:
    print('[ERROR] mmdb_writer not available'); sys.exit(1)
from netaddr import IPSet, IPNetwork

def ip_int_to_str(ip_int):
    try:
        return str(ipaddress.IPv4Address(ip_int))
    except: return None

def load_idc_cidrs(path):
    """Load IDC CIDRs into a set for exclusion."""
    idc_cidrs = []
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                cidr = row.get('cidr', '').strip()
                if not cidr or '/' not in cidr: continue
                try:
                    net = ipaddress.ip_network(cidr, strict=False)
                    if net.version != 4:
                        continue
                    idc_cidrs.append(net)
                except ValueError: continue
    print(f'Loaded {len(idc_cidrs)} IDC networks')
    return idc_cidrs

def build():
    if not os.path.exists(FUSED_PATH):
        print(f'[ERROR] Fused data not found: {FUSED_PATH}')
        return
    
    idc_nets = load_idc_cidrs(IDC_PATH)

    # Sort + merge IDC nets into disjoint intervals for fast overlap lookup
    idc_intervals = sorted((int(n.network_address), int(n.broadcast_address)) for n in idc_nets)
    merged = []
    for lo, hi in idc_intervals:
        if merged and lo <= merged[-1][1] + 1:
            if hi > merged[-1][1]:
                merged[-1] = (merged[-1][0], hi)
        else:
            merged.append((lo, hi))
    idc_intervals = merged
    idc_starts = [iv[0] for iv in idc_intervals]
    print(f'IDC intervals (merged): {len(idc_intervals)}')
    
    writer = MMDBWriter()
    count = 0
    excluded_idc = 0
    
    with open(FUSED_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            start_ip = row.get('start_ip', '')
            if not start_ip or ':' in start_ip: continue
            end_ip = row.get('end_ip', '')
            country = row.get('country', '')
            region = row.get('region', '')
            city = row.get('city', '')
            
            # Build data
            data = {
                'country': country, 'region': region, 'city': city,
                'latitude': row.get('latitude') or None,
                'longitude': row.get('longitude') or None,
                'confidence': row.get('confidence') or 0.3,
                'accuracy_radius': 50 if row.get('city') else 200,
                'source': row.get('sources', ''),
            }
            # Clean None values for maxminddb serialization
            for k in list(data.keys()):
                if data[k] is None or data[k] == '':
                    del data[k]
            
            try:
                start = ipaddress.IPv4Address(start_ip)
                end = ipaddress.IPv4Address(end_ip)
            except ValueError: continue
            
            # Check if this range overlaps any IDC interval (bisect over merged intervals)
            s, e = int(start), int(end)
            idx = bisect.bisect_right(idc_starts, e) - 1
            if idx >= 0 and idc_intervals[idx][1] >= s:
                excluded_idc += 1
                continue
            
            # Insert
            for cidr in ipaddress.summarize_address_range(start, end):
                try:
                    writer.insert_network(IPSet(IPNetwork(str(cidr))), data)
                    count += 1
                except Exception:
                    pass
    
    writer.to_db_file(OUTPUT_MMDB)
    print(f'Written {count} networks to {OUTPUT_MMDB}')
    print(f'Excluded IDC: {excluded_idc}')
    
    # Stats
    try:
        import maxminddb
        reader = maxminddb.open_database(OUTPUT_MMDB)
        total = 0
        countries = {}
        for net, data in reader:
            total += 1
            c = data.get('country', '')
            countries[c] = countries.get(c, 0) + 1
        reader.close()
        print(f'Total records: {total}')
        print(f'Top countries: {dict(sorted(countries.items(), key=lambda x: -x[1])[:15])}')
    except Exception as e:
        print(f'(stats skipped: {e})')
    
    return OUTPUT_MMDB

if __name__ == '__main__':
    print('=' * 60)
    print('S7: IPv4 Residential MMDB Builder')
    print('=' * 60)
    build()
