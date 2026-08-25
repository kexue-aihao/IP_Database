#!/usr/bin/env python3
"""
Subagent 1: Anchor Collector — Phase 0

Collects known-location anchor IPs from multiple public sources.
ip2region format: start_ip|end_ip|country|province|city|isp|country_code
"""

import csv
import json
import os
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE, 'data')
ANCHOR_PATH = os.path.join(DATA_DIR, 'anchor_ips.csv')
STATS_PATH = os.path.join(DATA_DIR, 'anchor_stats.json')

CITY_CENTERS = {
    ('北京', '北京'): (39.9042, 116.4074),
    ('上海', '上海'): (31.2304, 121.4737),
    ('天津', '天津'): (39.1252, 117.1908),
    ('重庆', '重庆'): (29.4316, 106.9123),
    ('广东', '广州'): (23.1291, 113.2644),
    ('广东', '深圳'): (22.5431, 114.0579),
    ('浙江', '杭州'): (30.2741, 120.1551),
    ('江苏', '南京'): (32.0603, 118.7969),
    ('湖北', '武汉'): (30.5928, 114.3055),
    ('四川', '成都'): (30.5728, 104.0668),
    ('陕西', '西安'): (34.2611, 108.9426),
    ('福建', '福州'): (26.0743, 119.2964),
    ('福建', '厦门'): (24.4798, 118.0894),
    ('山东', '济南'): (36.6512, 116.9972),
    ('山东', '青岛'): (36.0671, 120.3826),
    ('辽宁', '沈阳'): (41.8057, 123.4315),
    ('湖南', '长沙'): (28.2282, 112.9388),
    ('安徽', '合肥'): (31.8206, 117.2272),
    ('河南', '郑州'): (34.7466, 113.6253),
    ('河北', '石家庄'): (38.0428, 114.5149),
    ('黑龙江', '哈尔滨'): (45.8038, 126.5350),
    ('吉林', '长春'): (43.8868, 125.3245),
    ('山西', '太原'): (37.8706, 112.5489),
    ('江西', '南昌'): (28.6829, 115.8582),
    ('广西', '南宁'): (22.8170, 108.3665),
    ('云南', '昆明'): (25.0389, 102.7183),
    ('贵州', '贵阳'): (26.6470, 106.6302),
    ('甘肃', '兰州'): (36.0611, 103.8343),
    ('内蒙古', '呼和浩特'): (40.8421, 111.7488),
    ('新疆', '乌鲁木齐'): (43.8256, 87.6168),
    ('宁夏', '银川'): (38.4872, 106.2309),
    ('青海', '西宁'): (36.6171, 101.7802),
    ('西藏', '拉萨'): (29.6500, 91.1000),
    ('海南', '海口'): (20.0440, 110.3499),
    ('香港', '香港'): (22.3027, 114.1772),
    ('澳门', '澳门'): (22.1987, 113.5439),
    ('台湾', '台北'): (25.0330, 121.5654),
    ('台湾', '高雄'): (22.6195, 120.3100),
    ('台湾', '台中'): (24.1484, 120.6740),
    ('台湾', '台南'): (22.9984, 120.2126),
}


def normalize_name(name):
    """Remove 省/市 suffix for comparison."""
    if not name:
        return name
    for suffix in ['省', '市', '自治区', '壮族', '回族', '维吾尔']:
        name = name.replace(suffix, '')
    name = name.replace('特别行政区', '')
    return name.strip()


def extract_university_anchors():
    """
    Extract university IP ranges from ip2region data.
    ip2region format: start_ip|end_ip|country|province|city|organization|country_code
    """
    ipv4_path = os.path.join(DATA_DIR, 'ip2region_data', 'ipv4_source.txt')
    ipv6_path = os.path.join(DATA_DIR, 'ip2region_data', 'ipv6_source.txt')
    anchors = []
    edu_keywords = ['大学', '学院', '教育网', '教育科研网', 'CERNET']

    for src_path in [ipv4_path, ipv6_path]:
        if not os.path.exists(src_path):
            continue
        with open(src_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split('|')
                if len(parts) < 7:
                    continue

                # ip2region format: start_ip|end_ip|country|province|city|org|country_code
                country = parts[2] if len(parts) > 2 else ''
                province = parts[3] if len(parts) > 3 else ''
                city = parts[4] if len(parts) > 4 else ''
                organization = parts[5] if len(parts) > 5 else ''
                country_code = parts[6] if len(parts) > 6 else ''

                if country_code not in ('CN', 'HK', 'TW', 'MO'):
                    # Also check if country name contains China
                    if not any(cn in country for cn in ['中国', '香港', '澳门', '台湾']):
                        continue

                combined = f'{organization} {province} {city}'
                if not any(kw in combined for kw in edu_keywords):
                    continue

                start_ip = parts[0]
                end_ip = parts[1]

                if not province or province in ('0', 'Reserved', ''):
                    continue

                # Get coordinates
                lat, lng = '', ''
                # Try (province, city)
                pn = normalize_name(province)
                cn = normalize_name(city)
                key = (pn, cn)
                if key in CITY_CENTERS:
                    lat, lng = CITY_CENTERS[key][0], CITY_CENTERS[key][1]
                # Try (province, province) for province-level cities
                key2 = (pn, pn)
                if not lat and key2 in CITY_CENTERS:
                    lat, lng = CITY_CENTERS[key2][0], CITY_CENTERS[key2][1]

                anchors.append({
                    'start_ip': start_ip, 'end_ip': end_ip,
                    'province': pn, 'city': cn, 'district': '',
                    'lat': str(lat) if lat else '', 'lng': str(lng) if lng else '',
                    'source': 'ip2region', 'type': 'educational', 'name': organization,
                })

    print(f'  ip2region: {len(anchors)} educational anchors')
    return anchors


def collect_public_infrastructure():
    anchors = [
        {'start_ip': '223.5.5.5', 'end_ip': '223.5.5.5', 'province': '浙江', 'city': '杭州', 'district': '',
         'lat': '30.2741', 'lng': '120.1551', 'source': 'public_docs', 'type': 'public_dns', 'name': 'Alibaba DNS'},
        {'start_ip': '223.6.6.6', 'end_ip': '223.6.6.6', 'province': '浙江', 'city': '杭州', 'district': '',
         'lat': '30.2741', 'lng': '120.1551', 'source': 'public_docs', 'type': 'public_dns', 'name': 'Alibaba DNS'},
        {'start_ip': '119.29.29.29', 'end_ip': '119.29.29.29', 'province': '广东', 'city': '深圳', 'district': '',
         'lat': '22.5431', 'lng': '114.0579', 'source': 'public_docs', 'type': 'public_dns', 'name': 'Tencent DNS'},
        {'start_ip': '180.76.76.76', 'end_ip': '180.76.76.76', 'province': '北京', 'city': '北京', 'district': '',
         'lat': '39.9042', 'lng': '116.4074', 'source': 'public_docs', 'type': 'public_dns', 'name': 'Baidu DNS'},
        {'start_ip': '114.114.114.114', 'end_ip': '114.114.114.114', 'province': '江苏', 'city': '南京', 'district': '',
         'lat': '32.0603', 'lng': '118.7969', 'source': 'public_docs', 'type': 'public_dns', 'name': '114DNS'},
    ]
    print(f'  Public infra: {len(anchors)} anchors')
    return anchors


def get_cloudflare_cities():
    cities = [
        '北京', '上海', '广东广州', '广东深圳', '四川成都', '浙江杭州',
        '江苏南京', '湖北武汉', '陕西西安', '重庆', '福建福州', '福建厦门',
        '山东青岛', '辽宁沈阳', '湖南长沙', '香港', '台湾台北',
    ]
    anchors = []
    for entry in cities:
        parts = entry.split()
        if len(parts) == 2:
            prov, city = parts[0], parts[1]
        else:
            prov, city = entry, entry
        lat, lng = CITY_CENTERS.get((prov, city), ('', ''))
        anchors.append({
            'start_ip': '', 'end_ip': '', 'province': prov, 'city': city, 'district': '',
            'lat': str(lat), 'lng': str(lng),
            'source': 'cloudflare_public', 'type': 'cdn_node', 'name': f'Cloudflare {city}',
        })
    print(f'  Cloudflare: {len(anchors)} city anchors')
    return anchors


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    print('Anchor Collector — Phase 0')
    print('=' * 50)

    all_anchors = []
    all_anchors.extend(extract_university_anchors())
    all_anchors.extend(collect_public_infrastructure())
    all_anchors.extend(get_cloudflare_cities())

    # Deduplicate
    unique_anchors = []
    seen_ip = set()
    seen_city = set()
    for a in all_anchors:
        if a['start_ip'] and a['end_ip']:
            key = (a['start_ip'], a['end_ip'], a['type'])
            if key not in seen_ip:
                seen_ip.add(key)
                unique_anchors.append(a)
        else:
            key = (a['city'], a['type'])
            if key not in seen_city:
                seen_city.add(key)
                unique_anchors.append(a)

    fieldnames = ['start_ip', 'end_ip', 'province', 'city', 'district', 'lat', 'lng', 'source', 'type', 'name']
    with open(ANCHOR_PATH, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(unique_anchors)

    type_counts = {}
    source_counts = {}
    for a in unique_anchors:
        type_counts[a['type']] = type_counts.get(a['type'], 0) + 1
        source_counts[a['source']] = source_counts.get(a['source'], 0) + 1

    stats = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total_anchors': len(unique_anchors),
        'by_type': type_counts,
        'by_source': source_counts,
    }
    with open(STATS_PATH, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    print(f'\nTotal unique anchors: {len(unique_anchors)}')
    print(f'By type: {type_counts}')
    print(f'By source: {source_counts}')
    print(f'Written to: {ANCHOR_PATH}')


if __name__ == '__main__':
    main()
