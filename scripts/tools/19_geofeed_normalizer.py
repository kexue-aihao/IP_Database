#!/usr/bin/env python3
"""Subagent S7: Geofeed Normalizer — Phase 6. Parses and normalizes raw geofeed data."""
import csv, json, os, re, ipaddress
from collections import Counter
from datetime import datetime
BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE, 'data')
GEOFEED_DIR = os.path.join(DATA_DIR, 'geofeed')
RAW_PATH = os.path.join(GEOFEED_DIR, 'china_geofeed_raw.csv')
OUTPUT_PATH = os.path.join(GEOFEED_DIR, 'china_geofeed_norm.csv')
STATS_PATH = os.path.join(GEOFEED_DIR, 'geofeed_norm_stats.json')
# ISO 3166-2 CN province codes (numeric)
CN_REGION = {
    'CN-11': '北京', 'CN-12': '天津', 'CN-13': '河北', 'CN-14': '山西',
    'CN-15': '内蒙古', 'CN-21': '辽宁', 'CN-22': '吉林', 'CN-23': '黑龙江',
    'CN-31': '上海', 'CN-32': '江苏', 'CN-33': '浙江', 'CN-34': '安徽',
    'CN-35': '福建', 'CN-36': '江西', 'CN-37': '山东', 'CN-41': '河南',
    'CN-42': '湖北', 'CN-43': '湖南', 'CN-44': '广东', 'CN-45': '广西',
    'CN-46': '海南', 'CN-50': '重庆', 'CN-51': '四川', 'CN-52': '贵州',
    'CN-53': '云南', 'CN-54': '西藏', 'CN-61': '陕西', 'CN-62': '甘肃',
    'CN-63': '青海', 'CN-64': '宁夏', 'CN-65': '新疆',
    'CN-71': '台湾', 'CN-91': '香港', 'CN-92': '澳门',
}
# ISO 3166-2 CN alpha-2 codes (used by geofeeds)
CN_ALPHA = {
    'CN-BJ': '北京', 'CN-TJ': '天津', 'CN-HE': '河北', 'CN-SX': '山西',
    'CN-NM': '内蒙古', 'CN-LN': '辽宁', 'CN-JL': '吉林', 'CN-HL': '黑龙江',
    'CN-SH': '上海', 'CN-JS': '江苏', 'CN-ZJ': '浙江', 'CN-AH': '安徽',
    'CN-FJ': '福建', 'CN-JX': '江西', 'CN-SD': '山东', 'CN-HA': '河南',
    'CN-HB': '湖北', 'CN-HN': '湖南', 'CN-GD': '广东', 'CN-GX': '广西',
    'CN-HI': '海南', 'CN-CQ': '重庆', 'CN-SC': '四川', 'CN-GZ': '贵州',
    'CN-YN': '云南', 'CN-XZ': '西藏', 'CN-SN': '陕西', 'CN-GS': '甘肃',
    'CN-QH': '青海', 'CN-NX': '宁夏', 'CN-XJ': '新疆',
    'CN-TW': '台湾', 'CN-HK': '香港', 'CN-MO': '澳门',
}
EN_PROV = {
    'Beijing': '北京', 'Tianjin': '天津', 'Shanghai': '上海', 'Chongqing': '重庆',
    'Hebei': '河北', 'Shanxi': '山西', 'Neimenggu': '内蒙古', 'Inner Mongolia': '内蒙古',
    'Liaoning': '辽宁', 'Jilin': '吉林', 'Heilongjiang': '黑龙江',
    'Jiangsu': '江苏', 'Zhejiang': '浙江', 'Anhui': '安徽', 'Fujian': '福建',
    'Jiangxi': '江西', 'Shandong': '山东', 'Henan': '河南', 'Hubei': '湖北',
    'Hunan': '湖南', 'Guangdong': '广东', 'Guangxi': '广西', 'Hainan': '海南',
    'Sichuan': '四川', 'Guizhou': '贵州', 'Yunnan': '云南', 'Xizang': '西藏',
    'Shaanxi': '陕西', 'Gansu': '甘肃', 'Qinghai': '青海',
    'Ningxia': '宁夏', 'Xinjiang': '新疆',
    'Hong Kong': '香港', 'Macau': '澳门', 'Macao': '澳门', 'Taiwan': '台湾',
}
def norm_province(region_str):
    if not region_str: return ''
    r = region_str.strip()
    if r in CN_REGION: return CN_REGION[r]
    if r in CN_ALPHA: return CN_ALPHA[r]
    if r in EN_PROV: return EN_PROV[r]
    # Check if it's a Chinese province name directly
    chinese_provs = ['北京','天津','上海','重庆','河北','山西','内蒙古','辽宁','吉林','黑龙江',
                     '江苏','浙江','安徽','福建','江西','山东','河南','湖北','湖南','广东',
                     '广西','海南','四川','贵州','云南','西藏','陕西','甘肃','青海','宁夏','新疆']
    # Handle HK/MO special codes
    if r.upper() in ('HK', 'CN-HK', 'HONG KONG', 'HONGKONG', 'HONG KONG ISLAND'): return '香港'
    if r.upper() in ('MO', 'CN-MO', 'MACAU', 'MACAO'): return '澳门'
    if r.upper() in ('TW', 'CN-TW', 'TAIWAN', 'TAIPEI', 'TAIWAN PROVINCE OF CHINA'): return '台湾'
    for p in chinese_provs:
        if p in r: return p
    # Handle sub-region codes with prefix (e.g. HK-HCW, TW-TPE, CN-GD-GZ)
    up = r.upper()
    for prefix, cn in [('HK', '香港'), ('MO', '澳门'), ('TW', '台湾')]:
        if up.startswith(prefix):
            return cn
    # Handle CN-XX ALPHA prefixes
    if up.startswith('CN-'):
        parts = up.split('-')
        if len(parts) >= 2:
            alpha = parts[0] + '-' + parts[1]
            if alpha in CN_ALPHA:
                return CN_ALPHA[alpha]
    return r
def norm_city(city_str):
    if not city_str: return ''
    return city_str.strip().replace('"', '')
def parse_caida(line):
    """Parse RFC 8805: prefix,country,region,city,postal_code"""
    parts = line.split(',')
    if len(parts) < 3: return None
    prefix = parts[0].strip()
    country = parts[1].strip().upper()
    region = parts[2].strip() if len(parts) > 2 else ''
    city = parts[3].strip() if len(parts) > 3 else ''
    return {'prefix': prefix, 'country': country, 'region': region, 'city': city, 'source_type': 'caida'}
def parse_sapics(line):
    """Parse sapics: start_ip,end_ip,country"""
    parts = line.split(',')
    if len(parts) < 3: return None
    start = parts[0].strip()
    end = parts[1].strip()
    country = parts[2].strip().upper()
    return {'start_ip': start, 'end_ip': end, 'country': country, 'source_type': 'sapics'}
def prefix_to_range(prefix):
    """Convert CIDR prefix to start/end IP."""
    try:
        net = ipaddress.ip_network(prefix, strict=False)
        return str(net.network_address), str(net.broadcast_address)
    except ValueError:
        return None, None
def main():
    print('=' * 60)
    print('Subagent S7: Geofeed Normalizer')
    print('=' * 60)
    if not os.path.exists(RAW_PATH):
        print(f'[ERROR] {RAW_PATH} not found'); return
    os.makedirs(GEOFEED_DIR, exist_ok=True)
    # Parse raw records - read lines directly (raw_line contains commas!)
    caida_records = []
    sapics_records = []
    with open(RAW_PATH, 'r', encoding='utf-8') as f:
        header = f.readline()  # skip header
        for line in f:
            line = line.strip()
            if not line: continue
            # First comma separates source from raw_line; raw_line may contain additional commas
            sep = line.index(',')
            source = line[:sep].strip()
            raw = line[sep+1:].strip()
            if not raw: continue
            if source.startswith('caida'):
                rec = parse_caida(raw)
                if rec: caida_records.append(rec)
            elif source.startswith('sapics'):
                rec = parse_sapics(raw)
                if rec: sapics_records.append(rec)
    print(f'CAIDA records: {len(caida_records)}')
    print(f'Sapics records: {len(sapics_records)}')
    # Normalize CAIDA records
    norm_caida = []
    prov_counts = Counter()
    for r in caida_records:
        prov = norm_province(r['region'])
        city = norm_city(r['city'])
        start, end = prefix_to_range(r['prefix'])
        if start and end:
            norm_caida.append({
                'start_ip': start, 'end_ip': end,
                'prefix': r['prefix'], 'province': prov,
                'city': city, 'source': 'caida'
            })
            prov_counts[prov] += 1
    # Normalize sapics records (country-only, no province)
    norm_sapics = []
    for r in sapics_records:
        norm_sapics.append({
            'start_ip': r['start_ip'], 'end_ip': r['end_ip'],
            'prefix': '', 'province': '', 'city': '',
            'source': 'sapics'
        })
    # Deduplicate by IP range
    seen = set()
    all_norm = []
    for r in norm_caida + norm_sapics:
        key = (r['start_ip'], r['end_ip'])
        if key not in seen:
            seen.add(key)
            all_norm.append(r)
    print(f'\nAfter dedup: {len(all_norm)}')
    print(f'Province distribution (top 10):')
    for p, c in prov_counts.most_common(10):
        print(f'  {p}: {c}')
    # Write normalized CSV
    with open(OUTPUT_PATH, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['start_ip', 'end_ip', 'prefix', 'province', 'city', 'source'])
        writer.writeheader()
        writer.writerows(all_norm)
    print(f'\n[OK] {OUTPUT_PATH}')
    # Stats
    stats = {
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'raw_caida': len(caida_records),
        'raw_sapics': len(sapics_records),
        'normalized_total': len(all_norm),
        'normalized_caida': len(norm_caida),
        'normalized_sapics': len(norm_sapics),
        'province_distribution': dict(prov_counts.most_common(20)),
        'sources': {'caida': True, 'sapics': True},
    }
    with open(STATS_PATH, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(f'[OK] {STATS_PATH}')
if __name__ == '__main__':
    main()