#!/usr/bin/env python3
"""
Phase 0: Precision Evaluation Benchmark

Evaluates IP geolocation database accuracy against known anchor IPs.
Usage:
  python scripts/evaluate_precision.py
  python scripts/evaluate_precision.py --mmdb output/china_ipv4.mmdb
"""

import csv
import json
import math
import os
import sys
import re
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANCHOR_PATH = os.path.join(BASE, 'data', 'anchor_ips.csv')
OUTPUT_DIR = os.path.join(BASE, 'output')

DEFAULT_MMDB_FILES = [
    'china_ipv4.mmdb', 'china_ipv6.mmdb',
    'china_ipv4_telecom.mmdb', 'china_ipv4_unicom.mmdb',
    'china_ipv4_mobile.mmdb', 'china_ipv4_other.mmdb',
    'china_ipv4_idc.mmdb',
    'china_ipv6_telecom.mmdb', 'china_ipv6_unicom.mmdb',
    'china_ipv6_mobile.mmdb', 'china_ipv6_other.mmdb',
    'china_ipv6_idc.mmdb',
]


def normalize_name(name):
    """Normalize region name for comparison."""
    if not name:
        return ''
    name = str(name).strip()
    name = re.sub(r'[省市区]', '', name)
    name = name.replace('壮族自治区', '').replace('回族自治区', '').replace('维吾尔自治区', '')
    name = name.replace('自治区', '').replace('特别行政区', '')
    return name


def to_float(v):
    """Convert value to float, return None if impossible."""
    try:
        if v is None or v == '':
            return None
        return float(v)
    except (ValueError, TypeError):
        return None


def haversine_km(lat1, lng1, lat2, lng2):
    lat1, lng1, lat2, lng2 = to_float(lat1), to_float(lng1), to_float(lat2), to_float(lng2)
    if None in (lat1, lng1, lat2, lng2):
        return None
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlng / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def load_anchors(path):
    anchors = []
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            anchors.append(row)
    return anchors


def evaluate_anchors(anchors, mmdb_path):
    import maxminddb

    print(f'\n  Evaluating: {os.path.basename(mmdb_path)}')
    try:
        reader = maxminddb.open_database(mmdb_path)
    except Exception as e:
        print(f'    [SKIP] Cannot open: {e}')
        return None

    results = []
    anchor_type_stats = {}

    for anchor in anchors:
        ip = anchor.get('start_ip', '') or anchor.get('ip_range_start', '')
        if not ip:
            continue

        try:
            result = reader.get(ip)
        except Exception:
            continue
        if not isinstance(result, dict):
            continue

        anchor_type = anchor.get('type', 'unknown')
        if anchor_type not in anchor_type_stats:
            anchor_type_stats[anchor_type] = {'total': 0, 'prov_ok': 0, 'city_ok': 0, 'dist_ok': 0}

        stats = anchor_type_stats[anchor_type]
        stats['total'] += 1

        db_prov = normalize_name(result.get('province', ''))
        anchor_prov = normalize_name(anchor.get('province', ''))
        prov_ok = db_prov and anchor_prov and db_prov == anchor_prov

        db_city = normalize_name(result.get('city', ''))
        anchor_city = normalize_name(anchor.get('city', ''))
        city_ok = db_city and anchor_city and db_city == anchor_city

        dist = haversine_km(
            anchor.get('lat'), anchor.get('lng'),
            result.get('latitude'), result.get('longitude')
        )
        dist_ok = dist is not None and dist <= 50.0

        if prov_ok:
            stats['prov_ok'] += 1
        if city_ok:
            stats['city_ok'] += 1
        if dist_ok:
            stats['dist_ok'] += 1

        results.append({
            'ip': ip,
            'anchor_type': anchor_type,
            'anchor_prov': anchor_prov,
            'anchor_city': anchor_city,
            'db_prov': db_prov,
            'db_city': db_city,
            'db_district': normalize_name(result.get('district', '')),
            'db_geo_level': result.get('geo_level', ''),
            'db_lat': result.get('latitude'),
            'db_lng': result.get('longitude'),
            'distance_km': round(dist, 2) if dist is not None else None,
            'prov_ok': prov_ok,
            'city_ok': city_ok,
            'dist_ok': dist_ok,
        })

    reader.close()

    total = len(results)
    if total == 0:
        print(f'    No anchors matched')
        return None

    prov_ok = sum(1 for r in results if r['prov_ok'])
    city_ok = sum(1 for r in results if r['city_ok'])
    dist_ok = sum(1 for r in results if r['dist_ok'])

    dists = [r['distance_km'] for r in results if r['distance_km'] is not None]
    geo_levels = {}
    for r in results:
        lvl = r['db_geo_level'] or 'none'
        geo_levels[lvl] = geo_levels.get(lvl, 0) + 1

    summary = {
        'mmdb_file': os.path.basename(mmdb_path),
        'total_matched': total,
        'province_accuracy_pct': round(prov_ok / total * 100, 2),
        'city_accuracy_pct': round(city_ok / total * 100, 2),
        'within_50km_pct': round(dist_ok / total * 100, 2),
        'median_distance_km': round(sorted(dists)[len(dists)//2], 2) if dists else None,
        'avg_distance_km': round(sum(dists)/len(dists), 2) if dists else None,
        'max_distance_km': round(max(dists), 2) if dists else None,
        'geo_level_distribution': geo_levels,
        'anchor_type_stats': {k: {
            'total': v['total'],
            'prov_accuracy_pct': round(v['prov_ok']/v['total']*100, 1),
            'city_accuracy_pct': round(v['city_ok']/v['total']*100, 1),
            'within_50km_pct': round(v['dist_ok']/v['total']*100, 1),
        } for k, v in anchor_type_stats.items()}
    }

    print(f'    Matched: {total}')
    print(f'    Province accuracy: {summary["province_accuracy_pct"]}%')
    print(f'    City accuracy: {summary["city_accuracy_pct"]}%')
    print(f'    Within 50km: {summary["within_50km_pct"]}%')
    print(f'    Median distance: {summary["median_distance_km"]} km')
    print(f'    Geo level: {geo_levels}')
    for k, v in summary['anchor_type_stats'].items():
        print(f'    [{k}] prov={v["prov_accuracy_pct"]}% city={v["city_accuracy_pct"]}% <50km={v["within_50km_pct"]}% n={v["total"]}')

    return {'summary': summary, 'details': results}


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Evaluate IP geolocation precision')
    parser.add_argument('--mmdb', help='Evaluate a single MMDB file')
    parser.add_argument('--report', action='store_true', help='Generate JSON report only')
    args = parser.parse_args()

    if not os.path.exists(ANCHOR_PATH):
        print(f'[ERROR] Anchor file not found: {ANCHOR_PATH}')
        sys.exit(1)

    anchors = load_anchors(ANCHOR_PATH)
    print(f'Loaded {len(anchors)} anchor IPs')

    if args.mmdb:
        mmdb_list = [args.mmdb]
    else:
        mmdb_list = [os.path.join(OUTPUT_DIR, f) for f in DEFAULT_MMDB_FILES
                     if os.path.exists(os.path.join(OUTPUT_DIR, f))]

    all_reports = {}
    for mmdb_path in mmdb_list:
        report = evaluate_anchors(anchors, mmdb_path)
        if report:
            all_reports[os.path.basename(mmdb_path)] = report['summary']

    report = {
        'evaluation_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total_anchors': len(anchors),
        'anchor_types': {},
        'per_mmdb': all_reports,
    }
    for a in anchors:
        t = a.get('type', 'unknown')
        report['anchor_types'][t] = report['anchor_types'].get(t, 0) + 1

    report_path = os.path.join(OUTPUT_DIR, 'precision_report.json')
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f'\nReport saved to: {report_path}')

    if args.report:
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
