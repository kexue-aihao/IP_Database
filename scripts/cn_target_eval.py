# -*- coding: utf-8 -*-
"""Evaluate v1 vs v2 on anchors that HIT the MMDB (China-relevant)."""
import csv, sys, io, json, os, math, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import maxminddb
ANCHOR_PATH = r'E:/IP_Database/data/anchor_ips.csv'
V1 = r'E:/IP_Database/output/china_ipv4_high_prec.mmdb'
V2 = r'E:/IP_Database/output/china_ipv4_high_prec_v2.mmdb'
OUT = r'E:/IP_Database/output/cn_target_precision.json'
def to_float(v):
    try:
        if v is None or v == '': return None
        return float(v)
    except: return None
def norm(name):
    if not name: return ''
    name = str(name).strip()
    name = re.sub(r'[省市区]', '', name)
    name = name.replace('壮族自治区','').replace('回族自治区','').replace('维吾尔自治区','')
    name = name.replace('自治区','').replace('特别行政区','')
    # Normalize Taiwan/HK names
    name = name.replace('台湾','台湾').replace('香港','香港')
    return name
# Load ALL anchors with complete location
anchors = []
with open(ANCHOR_PATH, encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for r in reader:
        ip = r.get('ip_range_start','').strip()
        if not ip or ':' in ip: continue
        prov = r.get('province','').strip()
        city = r.get('city','').strip()
        lat = to_float(r.get('lat')); lng = to_float(r.get('lng'))
        if prov and city and lat is not None and lng is not None:
            anchors.append({'ip': ip, 'province': prov, 'city': city, 'lat': lat, 'lng': lng, 'type': r.get('type','')})
print(f'Anchors with complete data: {len(anchors)}')

def evaluate_on_hits(mmdb_path, anchor_list):
    """Evaluate only anchors that hit the MMDB."""
    reader = maxminddb.open_database(mmdb_path)
    results = []
    for a in anchor_list:
        try:
            result = reader.get(a['ip'])
        except: continue
        if not isinstance(result, dict) or not result.get('province'): continue
        db_prov = norm(result.get('province',''))
        anchor_prov = norm(a['province'])
        prov_ok = db_prov and anchor_prov and db_prov == anchor_prov
        db_city = norm(result.get('city',''))
        anchor_city = norm(a['city'])
        city_ok = db_city and anchor_city and (db_city in anchor_city or anchor_city in db_city)
        db_lat = to_float(result.get('latitude'))
        db_lng = to_float(result.get('longitude'))
        dist = None
        if db_lat is not None and db_lng is not None:
            R = 6371.0
            dlat = math.radians(db_lat - a['lat'])
            dlng = math.radians(db_lng - a['lng'])
            aa = math.sin(dlat/2)**2 + math.cos(math.radians(a['lat'])) * math.cos(math.radians(db_lat)) * math.sin(dlng/2)**2
            dist = R * 2 * math.atan2(math.sqrt(aa), math.sqrt(1-aa))
        results.append({'ip': a['ip'], 'type': a['type'],
            'anchor_prov': anchor_prov, 'anchor_city': anchor_city,
            'db_prov': db_prov, 'db_city': db_city,
            'prov_ok': prov_ok, 'city_ok': city_ok,
            'dist': dist, 'dist_ok': dist is not None and dist <= 50.0})
    reader.close()
    total = len(results)
    if total == 0: return None, []
    prov_ok = sum(1 for r in results if r['prov_ok'])
    city_ok = sum(1 for r in results if r['city_ok'])
    dist_ok = sum(1 for r in results if r['dist_ok'])
    dists = sorted([r['dist'] for r in results if r['dist'] is not None])
    # City mismatch samples
    mismatches = [r for r in results if not r['city_ok']][:15]
    return {
        'mmdb_file': os.path.basename(mmdb_path),
        'total_matched': total,
        'province_accuracy_pct': round(prov_ok/total*100, 2),
        'city_accuracy_pct': round(city_ok/total*100, 2),
        'within_50km_pct': round(dist_ok/total*100, 2),
        'median_distance_km': round(dists[len(dists)//2], 2) if dists else None,
        'cn_anchors': sum(1 for r in results if r['anchor_prov']),
    }, mismatches

# First pass: find v1 hits to define the anchor set
reader1 = maxminddb.open_database(V1)
hits = []
for a in anchors:
    try:
        result = reader1.get(a['ip'])
        if isinstance(result, dict) and result.get('province'):
            hits.append(a)
    except: continue
reader1.close()
print(f'Anchors hitting v1 MMDB with province: {len(hits)}')

report = {'anchor_set': len(hits), 'per_mmdb': {}}
all_mism = {}
for name, path in [('china_ipv4_high_prec.mmdb', V1), ('china_ipv4_high_prec_v2.mmdb', V2)]:
    print(f'\nEvaluating {name} on {len(hits)} hit anchors...')
    s, mism = evaluate_on_hits(path, hits)
    if s:
        report['per_mmdb'][name] = s
        all_mism[name] = mism
        print(f'  matched={s["total_matched"]} prov={s["province_accuracy_pct"]}% city={s["city_accuracy_pct"]}% <50km={s["within_50km_pct"]}% median={s["median_distance_km"]}km')
report['city_mismatch_samples'] = all_mism
with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(report, f, ensure_ascii=False, indent=2)
print(f'\n[OK] {OUT}')
print('\nV2 city mismatches sample:')
for m in (all_mism.get('china_ipv4_high_prec_v2.mmdb') or [])[:12]:
    print(f'  {m["ip"]} type={m["type"]} anchor={m["anchor_prov"]}/{m["anchor_city"]} vs db={m["db_prov"]}/{m["db_city"]}')
