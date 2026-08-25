#!/usr/bin/env python3
"""
Extracts China (CN/HK/TW/MO) records from local dbip-city-lite CSV.
Normalizes province/city names and provides coordinates.

Output: data/dbip_china_records.csv
"""

import csv
import gzip
import json
import os
from collections import Counter
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE, 'data')
DBIP_PATH = os.path.join(DATA_DIR, 'dbip-city-lite-2026-07.csv.gz')
OUTPUT_PATH = os.path.join(DATA_DIR, 'dbip_china_records.csv')
STATS_PATH = os.path.join(DATA_DIR, 'dbip_china_stats.json')

# English province name → Chinese province name mapping
EN_TO_CN_PROVINCE = {
    'Beijing': '北京', 'Tianjin': '天津', 'Shanghai': '上海', 'Chongqing': '重庆',
    'Hebei': '河北', 'Shanxi': '山西', 'Inner Mongolia': '内蒙古', 'Neimenggu': '内蒙古',
    'Liaoning': '辽宁', 'Jilin': '吉林', 'Heilongjiang': '黑龙江',
    'Jiangsu': '江苏', 'Zhejiang': '浙江', 'Anhui': '安徽', 'Fujian': '福建',
    'Jiangxi': '江西', 'Shandong': '山东',
    'Henan': '河南', 'Hubei': '湖北', 'Hunan': '湖南',
    'Guangdong': '广东', 'Guangxi': '广西',
    'Hainan': '海南',
    'Sichuan': '四川', 'Guizhou': '贵州', 'Yunnan': '云南', 'Tibet': '西藏', 'Xizang': '西藏',
    'Shaanxi': '陕西', 'Shanxi': '山西', 'Gansu': '甘肃', 'Qinghai': '青海',
    'Ningxia': '宁夏', 'Xinjiang': '新疆',
    'Hong Kong': '香港', 'Macau': '澳门', 'Macao': '澳门',
    'Taiwan': '台湾',
    'Fujian': '福建',
}

# Ambiguous mappings (Shanxi/Shaanxi correction)
# Note: 'Shanxi' could be 山西 or 陕西. We'll use context where possible.
# dbip uses 'Shaanxi' for 陕西 and 'Shanxi' for 山西


def normalize_province(en_name):
    """Convert English province name to Chinese."""
    if not en_name:
        return ''
    # Direct match
    en_name = en_name.strip()
    if en_name in EN_TO_CN_PROVINCE:
        return EN_TO_CN_PROVINCE[en_name]
    # Try partial match
    for k, v in EN_TO_CN_PROVINCE.items():
        if k.lower() in en_name.lower() or en_name.lower() in k.lower():
            return v
    return en_name


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    print('DB-IP China Extractor — Phase 2')
    print('=' * 50)

    records = []
    if not os.path.exists(DBIP_PATH):
        print(f'[ERROR] File not found: {DBIP_PATH}')
        return

    with gzip.open(DBIP_PATH, 'rt', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split(',')
            if len(parts) < 8:
                continue
            cc = parts[3].strip()
            if cc not in ('CN', 'HK', 'TW', 'MO'):
                continue
            start_ip = parts[0].strip()
            end_ip = parts[1].strip()
            region_en = parts[4].strip('"').strip()
            city_en = parts[5].strip('"').strip()
            lat = parts[6].strip()
            lng = parts[7].strip()

            province = normalize_province(region_en)
            records.append({
                'start_ip': start_ip, 'end_ip': end_ip,
                'province': province, 'city': city_en,
                'lat': lat, 'lng': lng,
                'country': cc,
            })

    # Deduplicate by (start_ip, end_ip)
    seen = set()
    unique = []
    for r in records:
        key = (r['start_ip'], r['end_ip'])
        if key not in seen:
            seen.add(key)
            unique.append(r)

    # Write CSV
    fieldnames = ['start_ip', 'end_ip', 'province', 'city', 'lat', 'lng', 'country']
    with open(OUTPUT_PATH, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(unique)

    # Stats
    prov_stats = Counter(r['province'] for r in unique)
    city_stats = Counter(r['city'] for r in unique)

    stats = {
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total_records': len(unique),
        'by_province': dict(prov_stats.most_common(35)),
        'unique_cities': len(city_stats),
    }

    with open(STATS_PATH, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    print(f'\nTotal records: {len(unique)}')
    print(f'Unique provinces: {len(prov_stats)}')
    print(f'Unique cities: {len(city_stats)}')
    print(f'By province: {dict(prov_stats.most_common(10))}')
    print(f'Written to: {OUTPUT_PATH}')


if __name__ == '__main__':
    main()
