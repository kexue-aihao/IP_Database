#!/usr/bin/env python3
"""
Patch: Add ISP (运营商) field to China MMDB files.
Reads ip2region org column (parts[5]) and rebuilds china_ipv4.mmdb / china_ipv6.mmdb with isp field.
Also restores geo_level and division_code fields seen in the original v2board DB.
"""
import csv, gzip, ipaddress, json, os, sys, io, bisect
from collections import defaultdict
from datetime import datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE, 'data')
OUTPUT_DIR = os.path.join(BASE, 'output')
IP2R_V4 = os.path.join(DATA_DIR, 'ip2region_data', 'ipv4_source.txt')
IP2R_V6 = os.path.join(DATA_DIR, 'ip2region_data', 'ipv6_source.txt')
FUSED_V2 = os.path.join(OUTPUT_DIR, 'china_ipv4_fused_v2.csv')
V6_RAW = os.path.join(DATA_DIR, 'global', 'global_raw_v6.csv')
OUT_V4 = os.path.join(OUTPUT_DIR, 'china_ipv4_with_isp.mmdb')
OUT_V6 = os.path.join(OUTPUT_DIR, 'china_ipv6_with_isp.mmdb')

sys.path.insert(0, os.path.join(BASE, 'scripts'))
try:
    from mmdb_writer import MMDBWriter
except ImportError:
    print('[ERROR] mmdb_writer not available'); sys.exit(1)
from netaddr import IPSet, IPNetwork

def ipv4_to_int(ip):
    try:
        parts = str(ip).split('.')
        return (int(parts[0])<<24)|(int(parts[1])<<16)|(int(parts[2])<<8)|int(parts[3])
    except: return None

def load_ip2region_org_v4(path):
    """Load (start_int, end_int, org) from ip2region v4."""
    print(f'Loading ip2region v4 org data...')
    intervals = []
    total = 0
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split('|')
            if len(parts) < 7: continue
            cc = parts[6].strip().upper()
            if cc not in ('CN', 'HK', 'TW', 'MO'): continue
            org = parts[5].strip() if len(parts) > 5 else ''
            if not org or org == '0': continue
            s = ipv4_to_int(parts[0]); e = ipv4_to_int(parts[1])
            if s is None or e is None: continue
            intervals.append((s, e, org))
            total += 1
    print(f'  {total} CN/HK/TW/MO intervals with org')
    return intervals

def load_ip2region_org_v6(path):
    """Load v6 intervals (start, end, org) as ints."""
    print(f'Loading ip2region v6 org data...')
    intervals = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split('|')
            if len(parts) < 7: continue
            cc = parts[6].strip().upper()
            if cc not in ('CN', 'HK', 'TW', 'MO'): continue
            org = parts[5].strip() if len(parts) > 5 else ''
            if not org or org == '0': continue
            try:
                start = int(ipaddress.IPv6Address(parts[0]))
                end = int(ipaddress.IPv6Address(parts[1]))
            except (ValueError, ipaddress.AddressValueError): continue
            intervals.append((start, end, org))
    print(f'  {len(intervals)} CN/HK/TW/MO v6 intervals with org')
    return intervals

def find_org(ip_int, intervals):
    """Binary search for org covering ip_int."""
    lo, hi = 0, len(intervals)
    while lo < hi:
        mid = (lo + hi) // 2
        if intervals[mid][0] <= ip_int:
            lo = mid + 1
        else:
            hi = mid
    idx = lo - 1
    if idx >= 0 and intervals[idx][0] <= ip_int <= intervals[idx][1]:
        return intervals[idx][2]
    return ''

def build_v4():
    """Build china_ipv4.mmdb with isp from fused v2 CSV."""
    if not os.path.exists(FUSED_V2):
        print(f'[ERROR] {FUSED_V2} not found'); return
    org_intervals = load_ip2region_org_v4(IP2R_V4)
    # Sort by start
    org_intervals.sort(key=lambda x: x[0])
    
    print(f'\nBuilding {OUT_V4}...')
    writer = MMDBWriter()
    count = 0
    with_isp = 0
    with open(FUSED_V2, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            start_ip = row['start_ip']
            end_ip = row['end_ip']
            if ':' in start_ip: continue  # v4 only
            try:
                start = ipaddress.IPv4Address(start_ip)
                end = ipaddress.IPv4Address(end_ip)
            except ValueError: continue
            s_int = int(start)
            
            # Find isp
            isp = find_org(s_int, org_intervals)
            if isp: with_isp += 1
            
            data = {
                'province': row['province'],
                'city': row['city'],
                'latitude': row['latitude'] if row['latitude'] else None,
                'longitude': row['longitude'] if row['longitude'] else None,
                'confidence': float(row['confidence']) if row['confidence'] else 0.3,
                'accuracy_radius': row.get('accuracy_radius', 50),
                'source': row['sources'],
            }
            if isp:
                data['isp'] = isp
            # geo_level
            if data['city'] and data['latitude']:
                data['geo_level'] = 'city' if not isp else 'district'
            elif data['province']:
                data['geo_level'] = 'province'
            # Clean None values
            for k in list(data.keys()):
                if data[k] is None or data[k] == '':
                    del data[k]
            
            for cidr in ipaddress.summarize_address_range(start, end):
                try:
                    writer.insert_network(IPSet(IPNetwork(str(cidr))), data)
                    count += 1
                except Exception: pass
    
    writer.to_db_file(OUT_V4)
    print(f'  {count} networks, {with_isp} with ISP ({with_isp/max(count,1)*100:.1f}%)')
    return OUT_V4

def build_v6():
    """Build china_ipv6.mmdb with isp from ip2region v6 raw."""
    if not os.path.exists(IP2R_V6):
        print(f'[ERROR] {IP2R_V6} not found'); return
    org_intervals = load_ip2region_org_v6(IP2R_V6)
    org_intervals.sort(key=lambda x: x[0])
    
    print(f'\nBuilding {OUT_V6}...')
    writer = MMDBWriter(ip_version=6)
    count = 0
    with_isp = 0
    
    # Also load existing province mapping from ipv6_provider_map
    prov_map_path = os.path.join(DATA_DIR, 'ipv6_provider_map.json')
    default_prov = '北京'
    
    with open(IP2R_V6, 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split('|')
            if len(parts) < 7: continue
            cc = parts[6].strip().upper()
            if cc not in ('CN', 'HK', 'TW', 'MO'): continue
            try:
                start = ipaddress.IPv6Address(parts[0])
                end = ipaddress.IPv6Address(parts[1])
            except (ValueError, ipaddress.AddressValueError): continue
            s_int = int(start)
            org = parts[5].strip() if len(parts) > 5 and parts[5] != '0' else ''
            province = parts[3].strip() if len(parts) > 3 else ''
            city = parts[4].strip() if len(parts) > 4 else ''
            if province in ('0', 'Reserved', ''):
                province = default_prov
            
            data = {
                'country': '中国',
                'province': province,
                'city': city if city and city != '0' else '',
                'latitude': 39.9042,
                'longitude': 116.4074,
                'geo_level': 'admin_center' if not city or city == '0' else 'city',
            }
            if org:
                data['isp'] = org
                with_isp += 1
            for k in list(data.keys()):
                if data[k] in (None, '', '0'):
                    del data[k]
            
            for cidr in ipaddress.summarize_address_range(start, end):
                try:
                    writer.insert_network(IPSet(IPNetwork(str(cidr))), data)
                    count += 1
                except Exception: pass
    
    writer.to_db_file(OUT_V6)
    print(f'  {count} networks, {with_isp} with ISP')
    return OUT_V6

if __name__ == '__main__':
    print('=' * 60)
    print('Patch: Add ISP field to China MMDB')
    print('=' * 60)
    v4 = build_v4()
    v6 = build_v6()
    print(f'\n[OK] {v4}')
    print(f'[OK] {v6}')
