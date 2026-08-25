# -*- coding: utf-8 -*-
import csv, sys, io, json, random
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import maxminddb

ANCHOR_PATH = r'E:/IP_Database/data/anchor_ips.csv'
V2 = r'E:/IP_Database/output/china_ipv4_high_prec_v2.mmdb'

def to_float(v):
    try:
        if v is None or v == '': return None
        return float(v)
    except: return None

anchors = []
with open(ANCHOR_PATH, encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for r in reader:
        prov = r.get('province', '').strip()
        city = r.get('city', '').strip()
        lat = to_float(r.get('lat')); lng = to_float(r.get('lng'))
        ip = r.get('ip_range_start', r.get('start_ip', '')).strip()
        if not ip or ':' in ip: continue
        if prov and city and lat is not None and lng is not None:
            anchors.append(r)

print(f'Complete-location anchors: {len(anchors)}')
# Sample types
from collections import Counter
types = Counter(a.get('type','') for a in anchors)
print('Types:', dict(types))

reader = maxminddb.open_database(V2)
# Test 10 random anchors
random.seed(42)
for a in random.sample(anchors, 10):
    ip = a.get('ip_range_start','').strip()
    try:
        result = reader.get(ip)
    except Exception as e:
        result = f'ERR: {e}'
    print(f'  IP={ip} type={a.get("type")} prov={a.get("province")} city={a.get("city")} lat={a.get("lat")} -> {result}')

# Test the top 3 ixp anchors
ixp = [a for a in anchors if a.get('type') == 'ixp_ip']
print(f'\nIXP anchors: {len(ixp)}')
for a in ixp[:5]:
    ip = a.get('ip_range_start','').strip()
    try:
        result = reader.get(ip)
    except Exception as e:
        result = f'ERR: {e}'
    print(f'  IP={ip} prov={a.get("province")} city={a.get("city")} -> {result}')
reader.close()
