# -*- coding: utf-8 -*-
"""Final attempt: try Azure download center with retries and known URLs."""
import re, sys, io, json, csv, os, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
try:
    import requests
except ImportError:
    print('NO REQUESTS'); sys.exit(1)

# Try multiple URL candidates for the 2026 ServiceTags
BASE_URLS = [
    'https://download.microsoft.com/download/7/1/D/71D86715-5596-4529-9B13-DC13A4DE5B63',
    'https://download.microsoft.com/download/6/B/6/6B6F5C49-D5B2-4B87-9C95-5D9C1C79C7C5',
    'https://download.microsoft.com/download/7/C/E/7CE0C0D9-0C6A-4F4A-8A3F-7B5B3A2E0C1B',
]
FILES = [
    'ServiceTags_Public_20260817.json',
    'ServiceTags_Public.json',
    'ServiceTags_Public_20260801.json',
    'ServiceTags_Public_20260701.json',
    'ServiceTags_Public_20260617.json',
]

def fetch(url, timeout=45):
    try:
        r = requests.get(url, timeout=timeout, headers={'User-Agent': 'Mozilla/5.0'}, verify=False)
        if r.status_code == 200 and len(r.content) > 10000:
            return r.text
        print(f'  [HTTP {r.status_code}] {url}')
    except Exception as e:
        print(f'  [FAIL {type(e).__name__}] {url}')
    return None

for base in BASE_URLS:
    for fname in FILES:
        url = f'{base}/{fname}'
        text = fetch(url)
        if text:
            try:
                data = json.loads(text)
                out = r'E:/IP_Database/data/global/idc/azure_ranges.csv'
                os.makedirs(os.path.dirname(out), exist_ok=True)
                count = 0
                with open(out, 'w', newline='', encoding='utf-8') as f:
                    w = csv.writer(f)
                    w.writerow(['cidr','vendor','service','region','country','source'])
                    for v in data.get('values', []):
                        props = v.get('properties', {})
                        region = props.get('region', '')
                        for p in props.get('addressPrefixes', []):
                            if '/' in p:
                                w.writerow([p, 'Azure', v.get('name',''), region, region[:2].upper() if region else '', 'azure-official'])
                                count += 1
                print(f'[OK] {count} Azure prefixes from {url}')
                # Merge into idc_all
                idc_all = r'E:/IP_Database/data/global/idc/idc_all.csv'
                existing = set()
                with open(idc_all, encoding='utf-8') as f:
                    for row in csv.DictReader(f):
                        existing.add(row['cidr'])
                added = 0
                new_rows = []
                with open(out, encoding='utf-8') as f:
                    for row in csv.DictReader(f):
                        if row['cidr'] not in existing:
                            new_rows.append(row); added += 1
                if new_rows:
                    with open(idc_all, 'a', newline='', encoding='utf-8') as f:
                        w = csv.DictWriter(f, fieldnames=['cidr','vendor','service','region','country','source'])
                        w.writerows(new_rows)
                print(f'[OK] Added {added} Azure ranges to idc_all.csv')
                sys.exit(0)
            except Exception as e:
                print(f'  Parse error: {e}')

print('[完成] All Azure URLs failed, will continue with other vendors only')
