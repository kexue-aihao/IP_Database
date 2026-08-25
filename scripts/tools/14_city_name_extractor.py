#!/usr/bin/env python3
"""Subagent S1: City Name Extractor — Phase 6. Extracts all unique English city names from DB-IP China records."""
import csv, json, os, re
from collections import Counter
from datetime import datetime
BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE, 'data')
DBIP_PATH = os.path.join(DATA_DIR, 'dbip_china_records.csv')
OUTPUT_PATH = os.path.join(DATA_DIR, 'dbip_city_names.json')
def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    print('=' * 60)
    print('Subagent S1: City Name Extractor')
    print('=' * 60)
    if not os.path.exists(DBIP_PATH):
        print(f'[ERROR] DB-IP records not found: {DBIP_PATH}'); return
    city_counter = Counter()
    city_base_counter = Counter()
    total_records = 0
    with open(DBIP_PATH, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader)
        for row in reader:
            total_records += 1
            if len(row) >= 6:
                city = row[3].strip()
                if city:
                    city_counter[city] += 1
                    base = city.split(' (')[0].strip() if ' (' in city else city
                    city_base_counter[base] += 1
    sorted_cities = sorted(city_counter.items(), key=lambda x: -x[1])
    chinese_cities = {n: c for n, c in sorted_cities if any('\u4e00' <= ch <= '\u9fff' for ch in n)}
    english_cities = {n: c for n, c in sorted_cities if not any('\u4e00' <= ch <= '\u9fff' for ch in n)}
    base_to_variants = {}
    for name, count in sorted_cities:
        base = name.split(' (')[0].strip() if ' (' in name else name
        base_to_variants.setdefault(base, []).append({'name': name, 'count': count})
    output = {
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total_records': total_records, 'unique_city_names': len(city_counter),
        'unique_base_names': len(city_base_counter),
        'chinese_city_count': len(chinese_cities), 'english_city_count': len(english_cities),
        'top_100_cities': [{'name': n, 'count': c} for n, c in sorted_cities[:100]],
        'all_cities': [{'name': n, 'count': c} for n, c in sorted_cities],
        'base_name_variants': {k: v for k, v in base_to_variants.items() if len(v) > 1},
    }
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f'\nTop 10:')
    for n, c in sorted_cities[:10]:
        print(f'  {"✓ CN" if n in chinese_cities else "   EN"} {n:40s} x {c:5d}')
    print(f'\n[OK] {OUTPUT_PATH}')
    print(f'  Total: {len(sorted_cities)} unique, Chinese: {len(chinese_cities)}, English: {len(english_cities)}')
if __name__ == '__main__':
    main()