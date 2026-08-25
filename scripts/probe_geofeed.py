# -*- coding: utf-8 -*-
import sys, io
sys.stdout.reconfigure(encoding='utf-8')
try:
    import requests
except ImportError:
    print("NO REQUESTS")
    sys.exit(0)

urls = [
    'https://publicdata.caida.org/datasets/geofeed-whois/2026/06/10/registries/apnic/standard/apnic_geofeed_467_geofeed-hk.csv',
    'https://publicdata.caida.org/datasets/geofeed-whois/2026/06/10/registries/apnic/standard/apnic_geofeed_1_geofeed.csv',
    'https://publicdata.caida.org/datasets/geofeed-whois/2026/08/23/registries/apnic/standard/apnic_geofeed_467_geofeed-hk.csv',
]
for u in urls:
    try:
        r = requests.get(u, timeout=30, headers={'User-Agent': 'Mozilla/5.0'}, allow_redirects=True)
        print(f'=== {u}')
        print(f'Status: {r.status_code}, final_url: {r.url}, size: {len(r.content)}')
        text = r.text[:500]
        print(text[:500])
    except Exception as e:
        print(f'FAIL {u}: {e}')
