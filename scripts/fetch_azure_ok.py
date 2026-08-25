# -*- coding: utf-8 -*-
"""Fetch Azure IP ranges from working GitHub repos."""
import csv, json, os, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
try:
    import requests
except ImportError:
    print('NO REQUESTS'); sys.exit(1)

URLS = [
    'https://raw.githubusercontent.com/jensihnow/AzurePublicIPAddressRanges/main/ServiceTags_Public.json',
    'https://raw.githubusercontent.com/maciejporebski/azure-ips/main/ServiceTags_Public_Latest.json',
]
OUT = r'E:/IP_Database/data/global/idc/azure_ranges.csv'

for url in URLS:
    print(f'Fetching: {url}')
    try:
        r = requests.get(url, timeout=60, headers={'User-Agent': 'Mozilla/5.0'})
        if r.status_code == 200 and len(r.content) > 10000:
            data = r.json()
            os.makedirs(os.path.dirname(OUT), exist_ok=True)
            count = 0
            with open(OUT, 'w', newline='', encoding='utf-8') as f:
                w = csv.writer(f)
                w.writerow(['cidr','vendor','service','region','country','source'])
                for v in data.get('values', []):
                    props = v.get('properties', {})
                    region = props.get('region', '')
                    for p in props.get('addressPrefixes', []):
                        if '/' in p:
                            w.writerow([p, 'Azure', v.get('name',''), region, region[:2].upper() if region else '', 'azure-official'])
                            count += 1
            print(f'[OK] {count} Azure prefixes')

            # Merge into idc_all.csv
            idc_all = r'E:/IP_Database/data/global/idc/idc_all.csv'
            existing = set()
            with open(idc_all, encoding='utf-8') as f:
                for row in csv.DictReader(f):
                    existing.add(row['cidr'])
            added = 0
            new_rows = []
            with open(OUT, encoding='utf-8') as f:
                for row in csv.DictReader(f):
                    if row['cidr'] not in existing:
                        new_rows.append(row); added += 1
            if new_rows:
                with open(idc_all, 'a', newline='', encoding='utf-8') as f:
                    w = csv.DictWriter(f, fieldnames=['cidr','vendor','service','region','country','source'])
                    w.writerows(new_rows)
            print(f'[OK] Added {added} Azure to idc_all.csv')
            sys.exit(0)
        else:
            print(f'  Size error: {len(r.content) if r.status_code==200 else r.status_code}')
    except Exception as e:
        print(f'  Error: {e}')
print('ALL FAILED')
