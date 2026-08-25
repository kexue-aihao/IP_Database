# -*- coding: utf-8 -*-
import json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
d = json.load(open(r'E:/IP_Database/data/city_map_final.json', encoding='utf-8'))
city_data = json.load(open(r'E:/IP_Database/data/dbip_city_names.json', encoding='utf-8'))
unmapped = set(d.get('unmapped_names', []))
# Get counts
name2count = {c['name']: c['count'] for c in city_data['all_cities']}
sorted_unmapped = sorted(unmapped, key=lambda n: -name2count.get(n, 0))
print('=== Unmapped by frequency (top 60) ===')
for n in sorted_unmapped[:60]:
    print(f'  {n} (x{name2count.get(n, 0)})')
total_unmapped_records = sum(name2count.get(n, 0) for n in unmapped)
print()
print(f'Unmapped names: {len(unmapped)}, unmapped records: {total_unmapped_records}')
print(f'Total records: {city_data["total_records"]}, unmapped share: {total_unmapped_records/city_data["total_records"]*100:.2f}%')
