# -*- coding: utf-8 -*-
"""Scrape MS download page for actual Azure Service Tags URL."""
import re, sys, io, json, csv, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
try:
    import requests
except ImportError:
    print('NO REQUESTS'); sys.exit(1)

# Try the download page to find the actual URL
urls = [
    'https://www.microsoft.com/en-us/download/details.aspx?id=56519',
    'https://www.microsoft.com/en-us/download/confirmation.aspx?id=56519',
]

for page_url in urls:
    print(f'Scraping: {page_url}')
    try:
        r = requests.get(page_url, timeout=30, headers={'User-Agent': 'Mozilla/5.0'})
        text = r.text
        # Look for download links
        for m in re.finditer(r'https://download\.microsoft\.com/download/[^"']+\.json', text):
            url = m.group(0)
            print(f'  Found: {url}')
            r2 = requests.get(url, timeout=30, headers={'User-Agent': 'Mozilla/5.0'})
            if r2.status_code == 200 and len(r2.text) > 10000:
                # Save it
                data = r2.json()
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
                print(f'[OK] {count} Azure prefixes -> {out}')
                # Merge
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
                print(f'[OK] Added {added} Azure to idc_all.csv')
                sys.exit(0)
        # If no direct JSON found, look for confirmation page redirect
        # Try known URL patterns
        base = 'https://download.microsoft.com/download/7/1/D/71D86715-5596-4529-9B13-DC13A4DE5B63'
        import glob2
        for fname in ['ServiceTags_Public_20260801.json', 'ServiceTags_Public_20260601.json']:
            url = f'{base}/{fname}'
            print(f'Trying: {url}')
            r2 = requests.get(url, timeout=30, headers={'User-Agent': 'Mozilla/5.0'})
            if r2.status_code == 200:
                print(f'  Found!')
                # save and process
                data = r2.json()
                # ... (same as above)
    except Exception as e:
        print(f'  Error: {e}')

print('ALL ATTEMPTS FAILED')
