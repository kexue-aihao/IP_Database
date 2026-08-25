# -*- coding: utf-8 -*-
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
with open(r'E:/IP_Database/data/ip2region_data/ipv4_source.txt', encoding='utf-8') as f:
    for i, line in enumerate(f):
        parts = line.strip().split('|')
        if i < 5:
            print(f'cols={len(parts)}:')
            for j, p in enumerate(parts):
                print(f'  [{j}]={p[:40]}')
        if len(parts) > 5 and parts[5].strip() and parts[5] != '0':
            print(f'[SAMPLE ORG at line {i}]: {parts[5][:80]}')
            break
    # Count org non-empty
    f.seek(0)
    total = 0; with_org = 0
    for line in f:
        parts = line.strip().split('|')
        total += 1
        if len(parts) > 5 and parts[5].strip() and parts[5] != '0':
            with_org += 1
    print(f'\nTotal ip2region v4 rows: {total}, with org: {with_org} ({with_org/total*100:.1f}%)')
