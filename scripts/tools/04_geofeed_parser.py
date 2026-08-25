#!/usr/bin/env python3
"""
Subagent 4: Geofeed Parser — Phase 2

Parses RFC 8805 geofeed data from public sources:
  - CAIDA geofeed-whois dataset (APNIC registry)
  - sapics/ip-location-db (GeoFeed + Whois aggregated data)
  - Individual ISP geofeeds

Output: data/geofeed/geofeed_records.csv
"""

import csv
import gzip
import io
import json
import os
import urllib.request
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE, 'data')
GEOFEED_DIR = os.path.join(DATA_DIR, 'geofeed')
OUTPUT_PATH = os.path.join(GEOFEED_DIR, 'geofeed_records.csv')
STATS_PATH = os.path.join(GEOFEED_DIR, 'geofeed_stats.json')

# CAIDA dataset: uses latest available month
# The URL pattern is: publicdata.caida.org/datasets/geofeed-whois/YYYY/MM/DD/registries/apnic/standard/
# We'll use the direct data files
GEOFEED_URLS = [
    # sapics ip-location-db: GeoFeed CSV (best for China)
    'https://raw.githubusercontent.com/sapics/ip-location-db/main/geofeed/geofeed-ipv4.csv',
    'https://raw.githubusercontent.com/sapics/ip-location-db/main/geofeed/geofeed-ipv6.csv',
    # sapics whois-db: Whois-based location data
    'https://raw.githubusercontent.com/sapics/ip-location-db/main/whois/whois-ipv4.csv',
    'https://raw.githubusercontent.com/sapics/ip-location-db/main/whois/whois-ipv6.csv',
]

TARGET_COUNTRIES = {'CN', 'HK', 'TW', 'MO'}


def safe_fetch(url, timeout=30):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            # Handle gzip
            if url.endswith('.gz'):
                import gzip
                data = gzip.decompress(data)
            return data.decode('utf-8', errors='replace')
    except Exception as e:
        print(f'  [FAIL] {url}: {e}')
        return None


def fetch_geofeed_sapics():
    """Fetch sapics geofeed data."""
    all_records = []
    for url in GEOFEED_URLS:
        name = url.split('/')[-1]
        print(f'  Fetching {name}...')
        content = safe_fetch(url)
        if not content:
            continue

        count = 0
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split(',')
            if len(parts) < 5:
                continue
            # Format: network,country,region,city,postal_code
            # or: prefix,start_ip,end_ip,country,region,city
            network = parts[0]
            country = parts[1].strip().upper() if len(parts) > 1 else ''
            region = parts[2].strip() if len(parts) > 2 else ''
            city = parts[3].strip() if len(parts) > 3 else ''

            if country in TARGET_COUNTRIES:
                all_records.append({
                    'network': network,
                    'country': country,
                    'region': region,
                    'city': city,
                    'source': name,
                })
                count += 1

        print(f'    → {count} CN/HK/TW/MO records')

    return all_records


def main():
    os.makedirs(GEOFEED_DIR, exist_ok=True)
    print('Geofeed Parser — Phase 2')
    print('=' * 50)

    records = fetch_geofeed_sapics()

    # Deduplicate by network
    seen = set()
    unique = []
    for r in records:
        if r['network'] not in seen:
            seen.add(r['network'])
            unique.append(r)

    print(f'\nUnique CN/HK/TW/MO geofeed records: {len(unique)}')

    # Write CSV
    with open(OUTPUT_PATH, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['network', 'country', 'region', 'city', 'source'])
        writer.writeheader()
        writer.writerows(unique)

    # Stats
    country_stats = {}
    region_stats = {}
    for r in unique:
        country_stats[r['country']] = country_stats.get(r['country'], 0) + 1
        if r['region']:
            region_stats[r['region']] = region_stats.get(r['region'], 0) + 1

    stats = {
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total_records': len(unique),
        'by_country': country_stats,
        'top_regions': dict(sorted(region_stats.items(), key=lambda x: -x[1])[:20]),
    }

    with open(STATS_PATH, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    print(f'By country: {country_stats}')
    print(f'Top regions: {stats["top_regions"]}')
    print(f'Written to: {OUTPUT_PATH}')


if __name__ == '__main__':
    main()
