# -*- coding: utf-8 -*-
"""Evaluate v1 vs v2 MMDB on anchors WITH complete location data only."""
import csv, sys, io, json, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import maxminddb

ANCHOR_PATH = r'E:/IP_Database/data/anchor_ips.csv'
V1 = r'E:/IP_Database/output/china_ipv4_high_prec.mmdb'
V2 = r'E:/IP_Database/output/china_ipv4_high_prec_v2.mmdb'
OUT = r'E:/IP_Database/output/filtered_precision.json'

def norm(name):
    import re
    if not name: return ''
    name = str(name).strip()
    name = re.sub(r'[省市区]', '', name)
    name = name.replace('壮族自治区', '').replace('回族自治区', '').replace('维吾尔自治区', '')
    name = name.replace('自治区', '').replace('特别行政区', '')
    return name

def to_float(v):
    try:
        if v is None or v == '': return None
        return float(v)
    except (ValueError, TypeError): return None

# Load anchors with complete location
anchors = []
with open(ANCHOR_PATH, encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for r in reader:
        prov = r.get('province', '').strip()
        city = r.get('city', '').strip()
        lat = to_float(r.get('lat'))
        lng = to_float(r.get('lng'))
        ip = r.get('ip_range_start', r.get('start_ip', '')).strip()
        if not ip: continue
        # IPv4 only for this comparison
        if ':' in ip: continue
        # Must have province AND city AND coords
        if prov and city and lat is not None and lng is not None:
            anchors.append({'ip': ip, 'province': prov, 'city': city, 'lat': lat, 'lng': lng, 'type': r.get('type', '')})
print(f'Anchors with complete location (IPv4): {len(anchors)}')

def evaluate(mmdb_path, anchors):
    reader = maxminddb.open_database(mmdb_path)
    results = []
    for a in anchors:
        try:
            result = reader.get(a['ip'])
        except Exception:
            continue
        if not isinstance(result, dict): continue
        db_prov = norm(result.get('province', ''))
        anchor_prov = norm(a['province'])
        prov_ok = db_prov and anchor_prov and db_prov == anchor_prov
        db_city = norm(result.get('city', ''))
        anchor_city = norm(a['city'])
        city_ok = db_city and anchor_city and db_city in anchor_city or (anchor_city and db_city and anchor_city in db_city)
        # distance
        db_lat = to_float(result.get('latitude'))
        db_lng = to_float(result.get('longitude'))
        dist = None
        if db_lat is not None and db_lng is not None:
            import math
            R = 6371.0
            dlat = math.radians(db_lat - a['lat'])
            dlng = math.radians(db_lng - a['lng'])
            aa = math.sin(dlat/2)**2 + math.cos(math.radians(a['lat'])) * math.cos(math.radians(db_lat)) * math.sin(dlng/2)**2
            dist = R * 2 * math.atan2(math.sqrt(aa), math.sqrt(1-aa))
        results.append({
            'ip': a['ip'], 'type': a['type'],
            'anchor_prov': anchor_prov, 'anchor_city': anchor_city,
            'db_prov': db_prov, 'db_city': db_city,
            'prov_ok': prov_ok, 'city_ok': city_ok,
            'dist': dist, 'dist_ok': dist is not None and dist <= 50.0,
        })
    reader.close()
    total = len(results)
    if total == 0: return None
    prov_ok = sum(1 for r in results if r['prov_ok'])
    city_ok = sum(1 for r in results if r['city_ok'])
    dist_ok = sum(1 for r in results if r['dist_ok'])
    dists = [r['dist'] for r in results if r['dist'] is not None]
    dists.sort()
    return {
        'mmdb_file': os.path.basename(mmdb_path),
        'total_matched': total,
        'province_accuracy_pct': round(prov_ok / total * 100, 2),
        'city_accuracy_pct': round(city_ok / total * 100, 2),
        'within_50km_pct': round(dist_ok / total * 100, 2),
        'median_distance_km': round(dists[len(dists)//2], 2) if dists else None,
        'avg_distance_km': round(sum(dists)/len(dists), 2) if dists else None,
        'type_stats': {},
    }

report = {'anchors_with_location': len(anchors), 'per_mmdb': {}}
for name, path in [('china_ipv4_high_prec.mmdb', V1), ('china_ipv4_high_prec_v2.mmdb', V2)]:
    print(f'\nEvaluating {name}...')
    s = evaluate(path, anchors)
    if s:
        report['per_mmdb'][name] = s
        print(f'  matched={s["total_matched"]} prov={s["province_accuracy_pct"]}% city={s["city_accuracy_pct"]}% <50km={s["within_50km_pct"]}% median={s["median_distance_km"]}km')

with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(report, f, ensure_ascii=False, indent=2)
print(f'\n[OK] {OUT}')
