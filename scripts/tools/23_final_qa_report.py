#!/usr/bin/env python3
"""Subagent S10: QA & Final Report — Phase 6. Aggregates all results and writes improvement report v2."""
import csv, json, os
from datetime import datetime
from collections import Counter
BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE, 'data')
OUTPUT_DIR = os.path.join(BASE, 'output')
GEOFEED_DIR = os.path.join(DATA_DIR, 'geofeed')
REPORT_PATH = os.path.join(OUTPUT_DIR, 'improvement_report_v2.json')
def load_json(path):
    if not os.path.exists(path): return None
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)
def main():
    print('=' * 60)
    print('Subagent S10: QA & Final Report')
    print('=' * 60)
    report = {
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'phase': 'Phase 6 - City Mapping + Geofeed Integration',
    }
    # 1. City mapping results
    city_map = load_json(os.path.join(DATA_DIR, 'city_map_final.json'))
    pinyin_map = load_json(os.path.join(DATA_DIR, 'city_map_pinyin.json'))
    coord_map = load_json(os.path.join(DATA_DIR, 'city_map_coords.json'))
    if city_map:
        report['city_mapping'] = {
            'coverage_pct': city_map.get('statistics', {}).get('coverage_pct'),
            'mapped': city_map.get('statistics', {}).get('mapped'),
            'unmapped': city_map.get('statistics', {}).get('unmapped'),
            'total': city_map.get('statistics', {}).get('total_cities'),
            'confidence': city_map.get('statistics', {}).get('confidence'),
            'methods': city_map.get('statistics', {}).get('methods'),
        }
        print('City mapping:')
        print(f'  Coverage: {report["city_mapping"]["coverage_pct"]}%')
        print(f'  Mapped: {report["city_mapping"]["mapped"]}')
    # 2. Geofeed results
    geofeed_stats = load_json(os.path.join(GEOFEED_DIR, 'geofeed_norm_stats.json'))
    if geofeed_stats:
        report['geofeed'] = {
            'normalized_total': geofeed_stats.get('normalized_total'),
            'caida': geofeed_stats.get('normalized_caida'),
            'sapics': geofeed_stats.get('normalized_sapics'),
            'province_distribution': geofeed_stats.get('province_distribution'),
        }
        print('\nGeofeed:')
        print(f'  Normalized total: {report["geofeed"]["normalized_total"]}')
    # 3. Fused v2 stats
    fused_path = os.path.join(OUTPUT_DIR, 'china_ipv4_fused_v2.csv')
    if os.path.exists(fused_path):
        total = 0; with_geofeed = 0; geofeed_provs = Counter()
        with open(fused_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                total += 1
                if 'geofeed' in row.get('sources', ''):
                    with_geofeed += 1
        report['fused_v2'] = {'total_records': total, 'with_geofeed': with_geofeed,
                              'geofeed_share_pct': round(with_geofeed / max(total, 1) * 100, 2)}
        print(f'\nFused v2: {total} records, {with_geofeed} include geofeed')
    # 4. Precision comparison
    prec_old = load_json(os.path.join(OUTPUT_DIR, 'precision_report.json'))
    prec_new = load_json(os.path.join(OUTPUT_DIR, 'precision_report_v2.json'))
    if prec_old and prec_new:
        old_ = prec_old.get('per_mmdb', {}).get('china_ipv4_high_prec.mmdb', {})
        new_ = prec_new.get('per_mmdb', {}).get('china_ipv4_high_prec_v2.mmdb', {})
        report['precision_comparison'] = {
            'baseline_province_pct': old_.get('province_accuracy_pct'),
            'v2_province_pct': new_.get('province_accuracy_pct'),
            'province_delta': round((new_.get('province_accuracy_pct', 0) or 0) - (old_.get('province_accuracy_pct', 0) or 0), 2),
            'baseline_city_pct': old_.get('city_accuracy_pct'),
            'v2_city_pct': new_.get('city_accuracy_pct'),
            'city_delta': round((new_.get('city_accuracy_pct', 0) or 0) - (old_.get('city_accuracy_pct', 0) or 0), 2),
            'baseline_within50km_pct': old_.get('within_50km_pct'),
            'v2_within50km_pct': new_.get('within_50km_pct'),
            'within50km_delta': round((new_.get('within_50km_pct', 0) or 0) - (old_.get('within_50km_pct', 0) or 0), 2),
        }
        print('\nPrecision comparison:')
        comp = report['precision_comparison']
        for k, v in comp.items():
            print(f'  {k}: {v}')
    # 5. Success criteria check
    criteria = {}
    cm = report.get('city_mapping', {})
    criteria['city_mapping_ge80pct'] = (cm.get('coverage_pct') or 0) >= 80
    comp2 = report.get('precision_comparison', {})
    criteria['city_accuracy_gt_78p2'] = (comp2.get('v2_city_pct') or 0) > 78.2
    criteria['province_accuracy_ge_91p7'] = (comp2.get('v2_province_pct') or 0) >= 91.7
    criteria['geofeed_ge_500'] = (report.get('geofeed', {}).get('normalized_total') or 0) >= 500
    report['success_criteria'] = {k: bool(v) for k, v in criteria.items()}
    print('\nSuccess criteria:', report['success_criteria'])
    with open(REPORT_PATH, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f'\n[OK] {REPORT_PATH}')
if __name__ == '__main__':
    main()