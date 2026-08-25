# -*- coding: utf-8 -*-
"""FAIR eval: v1 vs v2 on hit anchors with proper HK/TW/MO province normalization."""
import csv, sys, io, json, os, math, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import maxminddb
ANCHOR_PATH = r'E:/IP_Database/data/anchor_ips.csv'
V1 = r'E:/IP_Database/output/china_ipv4_high_prec.mmdb'
V2 = r'E:/IP_Database/output/china_ipv4_high_prec_v2.mmdb'
OUT = r'E:/IP_Database/output/fair_precision.json'
EN_PROV = {
    'HK': '香港', 'HONG KONG': '香港', 'HONGKONG': '香港',
    'MO': '澳门', 'MACAU': '澳门', 'MACAO': '澳门',
    'TW': '台湾', 'TAIWAN': '台湾',
    'Beijing': '北京', 'Shanghai': '上海', 'Tianjin': '天津', 'Chongqing': '重庆',
    'Hebei': '河北', 'Shanxi': '山西', 'Inner Mongolia': '内蒙古', 'Neimeng': '内蒙古',
    'Liaoning': '辽宁', 'Jilin': '吉林', 'Heilongjiang': '黑龙江',
    'Jiangsu': '江苏', 'Zhejiang': '浙江', 'Anhui': '安徽', 'Fujian': '福建',
    'Jiangxi': '江西', 'Shandong': '山东', 'Henan': '河南', 'Hubei': '湖北',
    'Hunan': '湖南', 'Guangdong': '广东', 'Guangxi': '广西', 'Hainan': '海南',
    'Sichuan': '四川', 'Guizhou': '贵州', 'Yunnan': '云南', 'Xizang': '西藏', 'Tibet': '西藏',
    'Shaanxi': '陕西', 'Gansu': '甘肃', 'Qinghai': '青海', 'Ningxia': '宁夏', 'Xinjiang': '新疆',
    'Xianggang': '香港', 'Aomen': '澳门', 'Taiwan Province': '台湾',
}
def to_float(v):
    try:
        return None if v in (None, '') else float(v)
    except: return None
def norm_prov(name):
    if not name: return ''
    name = str(name).strip()
    if name in EN_PROV: return EN_PROV[name]
    name = re.sub(r'[省市区]', '', name)
    name = name.replace('壮族自治区','').replace('回族自治区','').replace('维吾尔自治区','')
    name = name.replace('自治区','').replace('特别行政区','')
    return name
def norm_city(name):
    if not name: return ''
    name = str(name).strip()
    name = re.sub(r'[市区县镇]', '', name)
    return name
def load_anchors():
    anchors = []
    with open(ANCHOR_PATH, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for r in reader:
            ip = r.get('ip_range_start','').strip()
            if not ip or ':' in ip: continue
            prov = norm_prov(r.get('province',''))
            city = r.get('city','').strip()
            lat = to_float(r.get('lat')); lng = to_float(r.get('lng'))
            if prov and city and lat is not None and lng is not None:
                anchors.append({'ip': ip, 'province': prov, 'city': city, 'lat': lat, 'lng': lng, 'type': r.get('type','')})
    return anchors
def evaluate(mmdb_path, anchor_list):
    reader = maxminddb.open_database(mmdb_path)
    results = []
    for a in anchor_list:
        try: result = reader.get(a['ip'])
        except: continue
        if not isinstance(result, dict) or not result.get('province'): continue
        db_prov = norm_prov(result.get('province',''))
        prov_ok = db_prov and a['province'] and db_prov == a['province']
        db_city = norm_city(result.get('city',''))
        a_city = norm_city(a['city'])
        city_ok = db_city and a_city and (db_city in a_city or a_city in db_city)
        db_lat = to_float(result.get('latitude')); db_lng = to_float(result.get('longitude'))
        dist = None
        if db_lat is not None and db_lng is not None:
            R = 6371.0
            dlat = math.radians(db_lat - a['lat']); dlng = math.radians(db_lng - a['lng'])
            aa = math.sin(dlat/2)**2 + math.cos(math.radians(a['lat'])) * math.cos(math.radians(db_lat)) * math.sin(dlng/2)**2
            dist = R * 2 * math.atan2(math.sqrt(aa), math.sqrt(1-aa))
        results.append({'ip': a['ip'], 'type': a['type'], 'a_prov': a['province'], 'a_city': a['city'],
            'db_prov': result.get('province',''), 'db_city': result.get('city',''),
            'prov_ok': prov_ok, 'city_ok': city_ok, 'dist': dist, 'dist_ok': dist is not None and dist <= 50.0})
    reader.close()
    total = len(results)
    if total == 0: return None, []
    prov_ok = sum(1 for r in results if r['prov_ok'])
    city_ok = sum(1 for r in results if r['city_ok'])
    dist_ok = sum(1 for r in results if r['dist_ok'])
    dists = sorted([r['dist'] for r in results if r['dist'] is not None])
    mism = [r for r in results if not r['city_ok'] or not r['prov_ok']][:20]
    return {
        'mmdb_file': os.path.basename(mmdb_path),
        'total_matched': total,
        'province_accuracy_pct': round(prov_ok/total*100, 2),
        'city_accuracy_pct': round(city_ok/total*100, 2),
        'within_50km_pct': round(dist_ok/total*100, 2),
        'median_distance_km': round(dists[len(dists)//2], 2) if dists else None,
    }, mism
anchors = load_anchors()
print(f'Anchors with complete data: {len(anchors)}')
# Hits from v1 define the set
reader1 = maxminddb.open_database(V1)
hits = [a for a in anchors if isinstance(reader1.get(a['ip']), dict)]
reader1.close()
print(f'Anchors hitting v1: {len(hits)}')
report = {'anchor_set_size': len(hits), 'per_mmdb': {}, 'mismatch_samples': {}}
for name, path in [('china_ipv4_high_prec.mmdb', V1), ('china_ipv4_high_prec_v2.mmdb', V2)]:
    s, mism = evaluate(path, hits)
    if s:
        report['per_mmdb'][name] = s
        report['mismatch_samples'][name] = mism
        print(f'  {name}: matched={s["total_matched"]} prov={s["province_accuracy_pct"]}% city={s["city_accuracy_pct"]}% <50km={s["within_50km_pct"]}% med={s["median_distance_km"]}km')
with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(report, f, ensure_ascii=False, indent=2)
print(f'\n[OK] {OUT}')
