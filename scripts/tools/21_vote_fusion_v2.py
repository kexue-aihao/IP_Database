#!/usr/bin/env python3
"""
Subagent S8: Vote Fusion Engine v2 — Phase 6.
Upgrades the vote fusion engine to:
  1. Load dynamic EN→CN city mapping from data/city_map_final.json
  2. Add real geofeed data source (weight 0.9) from data/geofeed/china_geofeed_norm.csv
  3. Produce china_ipv4_fused_v2.csv
"""
import csv, gzip, json, os
from collections import Counter, defaultdict
from datetime import datetime
BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE, 'data')
OUTPUT_DIR = os.path.join(BASE, 'output')
IP2R_V4_PATH = os.path.join(DATA_DIR, 'ip2region_data', 'ipv4_source.txt')
DBIP_PATH = os.path.join(DATA_DIR, 'dbip-city-lite-2026-07.csv.gz')
GEOFEED_PATH = os.path.join(DATA_DIR, 'geofeed', 'china_geofeed_norm.csv')
CITY_MAP_PATH = os.path.join(DATA_DIR, 'city_map_final.json')
OUTPUT_V4 = os.path.join(OUTPUT_DIR, 'china_ipv4_fused_v2.csv')
SOURCE_WEIGHTS = {'anchor': 1.0, 'geofeed': 0.9, 'dbip': 0.7, 'ip2region': 0.6, 'geocn': 0.6}
EN_TO_CN_PROV = {
    'Beijing': '北京', 'Tianjin': '天津', 'Shanghai': '上海', 'Chongqing': '重庆',
    'Hebei': '河北', 'Shanxi': '山西', 'Inner Mongolia': '内蒙古',
    'Liaoning': '辽宁', 'Jilin': '吉林', 'Heilongjiang': '黑龙江',
    'Jiangsu': '江苏', 'Zhejiang': '浙江', 'Anhui': '安徽', 'Fujian': '福建',
    'Jiangxi': '江西', 'Shandong': '山东', 'Henan': '河南', 'Hubei': '湖北',
    'Hunan': '湖南', 'Guangdong': '广东', 'Guangxi': '广西', 'Hainan': '海南',
    'Sichuan': '四川', 'Guizhou': '贵州', 'Yunnan': '云南', 'Tibet': '西藏',
    'Shaanxi': '陕西', 'Gansu': '甘肃', 'Qinghai': '青海',
    'Ningxia': '宁夏', 'Xinjiang': '新疆',
    'Hong Kong': '香港', 'Macau': '澳门', 'Macao': '澳门', 'Taiwan': '台湾',
    'Kowloon': '香港', 'Hong Kong Island': '香港', 'New Territories': '香港',
    'Taipei': '台湾', 'New Taipei': '台湾', 'Taoyuan': '台湾',
    'Kaohsiung': '台湾', 'Taichung': '台湾', 'Tainan': '台湾',
}
# Dynamic city map cache
CITY_MAP = {}
def load_city_map():
    global CITY_MAP
    if os.path.exists(CITY_MAP_PATH):
        with open(CITY_MAP_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        CITY_MAP = data.get('mapping', {})
        print(f'  Loaded city map: {len(CITY_MAP)} entries')
    else:
        print(f'  [WARN] City map not found: {CITY_MAP_PATH}')
def norm_prov(p):
    if not p: return ''
    p = p.strip()
    if p in EN_TO_CN_PROV: return EN_TO_CN_PROV[p]
    return p.replace('市', '').replace('省', '')
def norm_city(c):
    if not c: return ''
    c = c.strip()
    # 1. Direct dictionary lookup
    if c in CITY_MAP: return CITY_MAP[c]
    # 2. Case-insensitive
    c_lower = c.lower()
    for k, v in CITY_MAP.items():
        if c_lower == k.lower():
            return v
    # 3. Base name before parentheses
    base = c.split(' (')[0].strip() if ' (' in c else c
    if base and base in CITY_MAP: return CITY_MAP[base]
    # 4. Don't strip '市' blindly - many names are already English
    return c
def ip_to_int(ip_str):
    try:
        parts = ip_str.strip().split('.')
        if len(parts) != 4: return None
        return (int(parts[0]) << 24) | (int(parts[1]) << 16) | (int(parts[2]) << 8) | int(parts[3])
    except (ValueError, IndexError):
        return None
def parse_ip2region(path):
    ranges = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line: continue
            parts = line.split('|')
            if len(parts) < 7: continue
            cc = parts[6]
            if cc not in ('CN', 'HK', 'TW', 'MO'): continue
            province = parts[3] if len(parts) > 3 else ''
            city = parts[4] if len(parts) > 4 else ''
            if not province or province in ('0', 'Reserved', ''): continue
            ranges.append({
                'start': parts[0], 'end': parts[1],
                'province': norm_prov(province), 'city': norm_city(city),
                'source': 'ip2region', 'weight': SOURCE_WEIGHTS['ip2region'],
            })
    return ranges
def parse_dbip(path):
    ranges = []
    if not os.path.exists(path): return ranges
    with gzip.open(path, 'rt', encoding='utf-8') as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 8: continue
            cc = row[3].strip()
            if cc not in ('CN', 'HK', 'TW', 'MO'): continue
            start = row[0].strip(); end = row[1].strip()
            region_en = row[4].strip(chr(34)).strip()
            city_en = row[5].strip(chr(34)).strip()
            try:
                lat = float(row[6].strip()); lng = float(row[7].strip())
            except (ValueError, IndexError): continue
            if lat == 0 and lng == 0: continue
            prov = norm_prov(region_en)
            if not prov: continue
            city = norm_city(city_en)
            ranges.append({
                'start': start, 'end': end, 'province': prov, 'city': city,
                'lat': lat, 'lng': lng, 'source': 'dbip', 'weight': SOURCE_WEIGHTS['dbip'],
            })
    return ranges
def parse_geofeed(path):
    """Parse normalized geofeed data: start_ip,end_ip,prefix,province,city,source"""
    ranges = []
    if not os.path.exists(path): return ranges
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            start = row.get('start_ip', '').strip()
            end = row.get('end_ip', '').strip()
            prov = row.get('province', '').strip()
            city = row.get('city', '').strip()
            if not start or not end: continue
            if not prov: continue  # Only use records with province info
            ranges.append({
                'start': start, 'end': end, 'province': norm_prov(prov),
                'city': norm_city(city),
                'source': 'geofeed', 'weight': SOURCE_WEIGHTS['geofeed'],
            })
    return ranges
def fuse(ranges_list):
    groups = defaultdict(list)
    for r in ranges_list:
        key = (r['start'], r['end'])
        groups[key].append(r)
    fused = []
    for (start, end), sources in groups.items():
        prov_votes = Counter(); city_votes = Counter()
        lat_lngs = []
        for s in sources:
            p = s.get('province', ''); c = s.get('city', ''); w = s.get('weight', 0.5)
            if p: prov_votes[p] += w
            if c and c != '0': city_votes[c] += w
            if s.get('lat') is not None and s.get('lng') is not None:
                try:
                    lat_lngs.append((float(s['lat']), float(s['lng']), w))
                except (ValueError, TypeError): pass
        if not prov_votes: continue
        best_prov = prov_votes.most_common(1)[0][0]
        total_prov = sum(prov_votes.values())
        prov_conf = prov_votes.most_common(1)[0][1] / total_prov if total_prov > 0 else 0
        best_city = ''
        if city_votes: best_city = city_votes.most_common(1)[0][0]
        avg_lat, avg_lng = None, None
        if lat_lngs:
            tw = sum(w for _, _, w in lat_lngs)
            avg_lat = sum(lat * w for lat, _, w in lat_lngs) / tw
            avg_lng = sum(lng * w for _, lng, w in lat_lngs) / tw
        n = len(sources)
        confidence = min(1.0, prov_conf * 0.4 + min(n / 5, 1.0) * 0.3 + (0.3 if lat_lngs else 0.0))
        fused.append({
            'start_ip': start, 'end_ip': end, 'start_ip_int': ip_to_int(start),
            'province': best_prov, 'city': best_city,
            'latitude': round(avg_lat, 6) if avg_lat else '',
            'longitude': round(avg_lng, 6) if avg_lng else '',
            'confidence': round(confidence, 3), 'n_sources': n,
            'sources': ','.join(s['source'] for s in sources),
        })
    return fused
def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print('Vote Fusion Engine v2 — Phase 6')
    print('=' * 50)
    print('Loading city map...')
    load_city_map()
    print()
    print('Loading sources...')
    v4_ip2r = parse_ip2region(IP2R_V4_PATH)
    print(f'  ip2region: {len(v4_ip2r)} ranges')
    v4_dbip = parse_dbip(DBIP_PATH)
    print(f'  DB-IP: {len(v4_dbip)} ranges')
    v4_geofeed = parse_geofeed(GEOFEED_PATH)
    print(f'  Geofeed (with province): {len(v4_geofeed)} ranges')
    print()
    print('Fusing IPv4...')
    v4_fused = fuse(v4_ip2r + v4_dbip + v4_geofeed)
    v4_fused.sort(key=lambda x: x['start_ip_int'] or 0)
    print(f'  Fused: {len(v4_fused)} ranges')
    fieldnames = ['start_ip', 'end_ip', 'start_ip_int', 'province', 'city',
                  'latitude', 'longitude', 'confidence', 'n_sources', 'sources']
    with open(OUTPUT_V4, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(v4_fused)
    conf_levels = Counter(); prov_counts = Counter()
    n_source_dist = Counter()
    for r in v4_fused:
        if r['confidence'] >= 0.8: conf_levels['high'] += 1
        elif r['confidence'] >= 0.5: conf_levels['medium'] += 1
        else: conf_levels['low'] += 1
        prov_counts[r['province']] += 1
        n_source_dist[r['n_sources']] += 1
    print()
    print(f'Confidence: {dict(conf_levels)}')
    print(f'Source count: {dict(n_source_dist)}')
    print(f'Top provinces: {dict(prov_counts.most_common(10))}')
    # Count records that include geofeed
    geofeed_in_fusion = sum(1 for r in v4_fused if 'geofeed' in r['sources'])
    print(f'Records including geofeed source: {geofeed_in_fusion}')
    print(f'Written: {OUTPUT_V4}')
if __name__ == '__main__':
    main()