# -*- coding: utf-8 -*-
import csv, json, sys
sys.stdout.reconfigure(encoding='utf-8')

# 1. Count unique DB-IP city names
cities = set()
title_case = set()
records = 0
with open(r'E:/IP_Database/data/dbip_china_records.csv', encoding='utf-8') as f:
    reader = csv.reader(f)
    header = next(reader)
    for row in reader:
        if len(row) >= 6:
            records += 1
            city = row[3].strip()
            cities.add(city)
            if city[0].isupper() if city else False:
                title_case.add(city)

sorted_cities = sorted(cities)
print(f"DB-IP records: {records}, unique city names: {len(sorted_cities)}")
chinese = [c for c in sorted_cities if any('\u4e00' <= ch <= '\u9fff' for ch in c)]
english = [c for c in sorted_cities if not any('\u4e00' <= ch <= '\u9fff' for ch in c)]
print(f"Already Chinese: {len(chinese)}")
print(f"English/Other: {len(english)}")
print("First 50 English:", ' | '.join(english[:50]))
print("Last 50 English:", ' | '.join(english[-50:]))

# 2. Check AreaCity level3 for city names
print("\n=== AreaCity Level3 (first 5) ===")
with open(r'E:/IP_Database/data/ok_data_level3.csv', encoding='utf-8') as f:
    for i, line in enumerate(f):
        if i < 5: print(line.strip())
        else: break

# 3. Check level4
print("\n=== AreaCity Level4 (first 3) ===")
with open(r'E:/IP_Database/data/ok_data_level4.csv', encoding='utf-8') as f:
    for i, line in enumerate(f):
        if i < 3: print(line.strip())
        else: break

# 4. Check existing fused CSV city distribution
print("\n=== Fused CSV city names (first 30 unique) ===")
fused_cities = set()
with open(r'E:/IP_Database/output/china_ipv4_fused.csv', encoding='utf-8') as f:
    reader = csv.reader(f)
    header = next(reader)
    for row in reader:
        if len(row) >= 5:
            city = row[4].strip()
            if city: fused_cities.add(city)
fused_sorted = sorted(fused_cities)
print(f"Unique cities in fused: {len(fused_sorted)}")
print("First 30:", ' | '.join(fused_sorted[:30]))
