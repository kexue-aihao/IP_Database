# -*- coding: utf-8 -*-
"""Scan CAIDA apnic geofeed files for CN records."""
import sys, io, concurrent.futures, re
sys.stdout.reconfigure(encoding='utf-8')
try:
    import requests
except ImportError:
    print("NO REQUESTS"); sys.exit(0)

BASE = 'https://publicdata.caida.org/datasets/geofeed-whois/2026/06/10/registries/apnic/standard/'

# Get file list from directory listing
r = requests.get(BASE, timeout=30, headers={'User-Agent': 'Mozilla/5.0'})
files = sorted(set(re.findall(r'href="(apnic_geofeed_[^"?]+)"', r.text)))
print(f'Found {len(files)} geofeed files')

def check_cn(fname):
    url = BASE + fname
    try:
        rr = requests.get(url, timeout=20, headers={'User-Agent': 'Mozilla/5.0'}, stream=True)
        # Read first 20KB, look for CN records
        chunk = b''
        for part in rr.iter_content(8192):
            chunk += part
            if len(chunk) > 40000: break
        text = chunk.decode('utf-8', errors='replace')
        cn_lines = [l for l in text.splitlines() if re.search(r',CN(,|$)', l)]
        total = len(text.splitlines())
        return (fname, len(cn_lines), total)
    except Exception as e:
        return (fname, -1, 0)

results = []
with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:
    for fname, cn_ct, total in ex.map(check_cn, files):
        if cn_ct > 0:
            results.append((fname, cn_ct, total))
            print(f'  CN FILE: {fname} cn_lines={cn_ct} total_head={total}')

print(f'\nFiles with CN records: {len(results)}')
print('Names hinting CN:', [f for f,_,_ in results if any(k in f.lower() for k in ['cn','china','telecom','unicom','mobile'])])
