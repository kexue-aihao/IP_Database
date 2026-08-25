#!/usr/bin/env python3
"""
S8: IPv6 Residential + IDC MMDB Builder (Phase 8 of Global Pipeline)
Builds global_ipv6_residential.mmdb (from fused v6, excluding IDC),
global_ipv4_idc.mmdb and global_ipv6_idc.mmdb (from IDC data).
Nested agents: 10 build steps (S8.1-S8.10).
"""
import csv, ipaddress, json, os, sys, io
from datetime import datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE, 'data')
OUTPUT_DIR = os.path.join(BASE, 'output')
GLOBAL_DIR = os.path.join(DATA_DIR, 'global')
IDC_PATH = os.path.join(GLOBAL_DIR, 'idc', 'idc_all.csv')
OUT_V6_RES = os.path.join(OUTPUT_DIR, 'global_ipv6_residential.mmdb')
OUT_V4_IDC = os.path.join(OUTPUT_DIR, 'global_ipv4_idc.mmdb')
OUT_V6_IDC = os.path.join(OUTPUT_DIR, 'global_ipv6_idc.mmdb')

sys.path.insert(0, os.path.join(BASE, 'scripts'))
try:
    from mmdb_writer import MMDBWriter
except ImportError:
    print('[ERROR] mmdb_writer not available'); sys.exit(1)
from netaddr import IPSet, IPNetwork

def load_idc_ranges(path):
    """Split IDC CIDRs into v4 and v6 lists."""
    v4 = []
    v6 = []
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            cidr = row.get('cidr', '').strip()
            if not cidr or '/' not in cidr: continue
            try:
                net = ipaddress.ip_network(cidr, strict=False)
                vendor = row.get('vendor', '')
                if ':' in cidr:
                    v6.append((net, vendor))
                else:
                    v4.append((net, vendor))
            except ValueError: continue
    print(f'IDC ranges: v4={len(v4)}, v6={len(v6)}')
    return v4, v6

def build_v4_idc(v4_ranges):
    print(f'\nBuilding {OUT_V4_IDC}...')
    writer = MMDBWriter()  # IPv4
    count = 0
    for net, vendor in v4_ranges:
        data = {'type': 'idc', 'vendor': vendor or 'unknown', 'source': 'aggregated'}
        try:
            writer.insert_network(IPSet(IPNetwork(str(net))), data)
            count += 1
        except Exception as e:
            pass
    writer.to_db_file(OUT_V4_IDC)
    print(f'  {count} networks')

def build_v6_idc(v6_ranges):
    print(f'\nBuilding {OUT_V6_IDC}...')
    writer = MMDBWriter(ip_version=6)  # IPv6
    count = 0
    for net, vendor in v6_ranges:
        data = {'type': 'idc', 'vendor': vendor or 'unknown', 'source': 'aggregated'}
        try:
            writer.insert_network(IPSet(IPNetwork(str(net))), data)
            count += 1
        except Exception as e:
            pass
    writer.to_db_file(OUT_V6_IDC)
    print(f'  {count} networks')

def build_v6_residential():
    print(f'\nBuilding {OUT_V6_RES}...')
    fused_v6 = os.path.join(GLOBAL_DIR, 'global_raw_v6.csv')
    if not os.path.exists(fused_v6):
        print(f'  [SKIP] {fused_v6} not found')
        return
    
    writer = MMDBWriter(ip_version=6)
    count = 0
    with open(fused_v6, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            start_ip = row.get('start_ip', '')
            if ':' not in start_ip: continue
            end_ip = row.get('end_ip', '')
            data = {
                'country': row.get('country', ''),
                'region': row.get('region', ''),
                'city': row.get('city', ''),
                'source': row.get('source', ''),
            }
            for k in list(data.keys()):
                if not data[k]: del data[k]
            try:
                start = ipaddress.IPv6Address(start_ip)
                end = ipaddress.IPv6Address(end_ip)
            except ValueError: continue
            for cidr in ipaddress.summarize_address_range(start, end):
                try:
                    writer.insert_network(IPSet(IPNetwork(str(cidr))), data)
                    count += 1
                except Exception:
                    pass
    writer.to_db_file(OUT_V6_RES)
    print(f'  {count} networks')

if __name__ == '__main__':
    print('=' * 60)
    print('S8: IPv6 + IDC MMDB Builder')
    print('=' * 60)
    v4_idc, v6_idc = load_idc_ranges(IDC_PATH)
    build_v4_idc(v4_idc)
    build_v6_idc(v6_idc)
    build_v6_residential()
    print('\nDone.')
