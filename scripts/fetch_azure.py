# -*- coding: utf-8 -*-
"""Fetch Azure IP ranges from GitHub mirror."""
import csv, json, os, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
try:
    import requests
except ImportError:
    print('NO REQUESTS'); sys.exit(1)

URLS = [
    'https://raw.githubusercontent.com/SamuelElh/azure-ip-ranges/main/ServiceTags_Public.json',
    'https://raw.githubusercontent.com/afwaw/azure-ip-ranges/master/ServiceTags_Public.json',
    'https://raw.githubusercontent.com/ThePsychologistr/AzureIPRanges/master/ServiceTags_Public.json',
]
OUT = r'E:/IP_Database/data/global/idc/azure_ranges.csv'

def fetch(url, timeout=30):
    try:
        r = requests.get(url, timeout=timeout, headers={'User-Agent': 'Mozilla/5.0'})
        if r.status_code == 200: return r.text
        print(f'  [HTTP {r.status_code}] {url}')
    except Exception as e:
        print(f'  [FAIL] {url}: {type(e).__name__}: {str(e)[:80]}')
    return None

for url in URLS:
    print(f'Trying: {url}')
    text = fetch(url)
    if text:
        try:
            data = json.loads(text)
            os.makedirs(os.path.dirname(OUT), exist_ok=True)
            count = 0
            with open(OUT, 'w', newline='', encoding='utf-8') as f:
                w = csv.writer(f)
                w.writerow(['cidr', 'vendor', 'service', 'region', 'country', 'source'])
                for v in data.get('values', []):
                    props = v.get('properties', {})
                    region = props.get('region', '')
                    for p in props.get('addressPrefixes', []):
                        if '/' in p:
                            w.writerow([p, 'Azure', v.get('name',''), region, region[:2].upper(), 'azure-official'])
                            count += 1
            print(f'OK: {count} Azure prefixes -> {OUT}')
            # Also merge into idc_all.csv
            idc_all = r'E:/IP_Database/data/global/idc/idc_all.csv'
            if os.path.exists(idc_all):
                existing = set()
                with open(idc_all, encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        existing.add(row['cidr'])
                added = 0
                with open(OUT, encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    rows_to_add = []
                    for row in reader:
                        if row['cidr'] not in existing:
                            rows_to_add.append(row)
                            existing.add(row['cidr'])
                            added += 1
                if rows_to_add:
                    with open(idc_all, 'a', newline='', encoding='utf-8') as f:
                        w = csv.DictWriter(f, fieldnames=['cidr','vendor','service','region','country','source'])
                        w.writerows(rows_to_add)
                print(f'Added {added} new Azure ranges to idc_all.csv')
            sys.exit(0)
        except Exception as e:
            print(f'  Parse error: {e}')
print('ALL URLS FAILED')
