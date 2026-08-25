# -*- coding: utf-8 -*-
"""Probe and fetch Azure IP ranges from multiple alternate sources."""
import csv, json, os, sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
try:
    import requests
except ImportError:
    print('NO REQUESTS'); sys.exit(1)

CANDIDATES = [
    # enzo-g.github.io mirror
    'https://enzo-g.github.io/azureIPranges/ServiceTags_Public.json',
    'https://enzo-g.github.io/azureIPranges/Data/ServiceTags_Public.json',
    # maciejporebski/azure-ips raw
    'https://raw.githubusercontent.com/maciejporebski/azure-ips/main/ServiceTags_Public.json',
    'https://raw.githubusercontent.com/maciejporebski/azure-ips/master/ServiceTags_Public.json',
]
OUT = r'E:/IP_Database/data/global/idc/azure_ranges.csv'

def fetch(url, timeout=30):
    try:
        r = requests.get(url, timeout=timeout, headers={'User-Agent': 'Mozilla/5.0'}, verify=False)
        if r.status_code == 200: return r.text, len(r.content)
        print(f'  [HTTP {r.status_code}] {url}')
    except Exception as e:
        print(f'  [FAIL] {url}: {type(e).__name__}: {str(e)[:60]}')
    return None, 0

def parse_and_save(text):
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
                    w.writerow([p, 'Azure', v.get('name',''), region, region[:2].upper() if region else '', 'azure-official'])
                    count += 1
    print(f'Parsed {count} Azure prefixes from source')
    return count

for url in CANDIDATES:
    print(f'Trying: {url}')
    text, size = fetch(url)
    if text and size > 1000:
        try:
            count = parse_and_save(text)
            if count > 1000:
                # Merge into idc_all
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
                            new_rows.append(row)
                            existing.add(row['cidr'])
                            added += 1
                if new_rows:
                    with open(idc_all, 'a', newline='', encoding='utf-8') as f:
                        w = csv.DictWriter(f, fieldnames=['cidr','vendor','service','region','country','source'])
                        w.writerows(new_rows)
                print(f'[OK] Added {added} Azure ranges to idc_all.csv')
                sys.exit(0)
        except Exception as e:
            print(f'  Parse error: {e}')
print('ALL FAILED')
