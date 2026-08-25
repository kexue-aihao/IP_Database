# -*- coding: utf-8 -*-
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
with open(r'E:/IP_Database/data/ip2region_data/ipv6_source.txt', encoding='utf-8') as f:
    total = 0; with_org = 0
    for line in f:
        parts = line.strip().split('|')
        total += 1
        if len(parts) > 5 and parts[5].strip() and parts[5] != '0':
            with_org += 1
        if total < 3:
            print(f'cols={len(parts)}:', parts[:7])
    print(f'\nTotal ip2region v6 rows: {total}, with org: {with_org} ({with_org/total*100:.1f}%)')
