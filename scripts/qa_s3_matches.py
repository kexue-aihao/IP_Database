# -*- coding: utf-8 -*-
import json, sys, io
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
d = json.load(open(r'E:/IP_Database/data/city_map_pinyin.json', encoding='utf-8'))
print('Match rate:', d['statistics']['match_rate_pct'], '%')
by_method = defaultdict(list)
for m in d['matches']:
    by_method[m['method']].append(m)
for method, items in by_method.items():
    print()
    print(f'=== {method} ({len(items)}) ===')
    for i in sorted(items, key=lambda x: -x['count'])[:4]:
        print(f'  {i["name"]} -> {i["mapped"]} (conf={i["confidence"]}, x{i["count"]})')
print()
print('=== Unmatched TOP 25 (by count) ===')
for u in sorted(d['unmatched'], key=lambda x: -x['count'])[:25]:
    print(f'  {u["name"]} (x{u["count"]})')
