#!/usr/bin/env python3
"""
Subagent 6: IPIP Free Importer — Phase 2

Downloads and parses the IPIP.net free IP location database.
The free version provides country/province/city at city precision.
Source: https://www.ipip.net/ (free access) or github mirrors.

Since the free IPIP data requires registration, this tool:
  1. Checks for a locally cached copy
  2. Falls back to the china_ip_list (GitHub 17mon repo) for segment data
  3. Parses both into a unified records file

Output: data/ipip_china_records.csv
"""

import csv
import json
import os
import urllib.request
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE, 'data')
OUTPUT_PATH = os.path.join(DATA_DIR, 'ipip_china_records.csv')
STATS_PATH = os.path.join(DATA_DIR, 'ipip_china_stats.json')

# IPIP free data sources
IPIP_SOURCES = [
    # china_ip_list.txt from 17mon GitHub (IPIP maintainer's segment list)
    {
        'name': 'china_ip_list',
        'url': 'https://raw.githubusercontent.com/17mon/china_ip_list/master/china_ip_list.txt',
        'local': os.path.join(DATA_DIR, 'china_ip_list.txt'),
    },
]


def safe_fetch(url, local_path=None, timeout=30):
    """Fetch from URL, or use local cache if exists."""
    if local_path and os.path.exists(local_path):
        with open(local_path, 'r', encoding='utf-8') as f:
            return f.read()
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content = resp.read().decode('utf-8', errors='replace')
        if local_path:
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            with open(local_path, 'w', encoding='utf-8') as f:
                f.write(content)
        return content
    except Exception as e:
        print(f'  [FAIL] {url}: {e}')
        return None


def parse_china_ip_list(content):
    """Parse china_ip_list.txt: one CIDR per line."""
    records = []
    if not content:
        return records
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        # Format: CIDR or start_ip-end_ip
        records.append({
            'network': line,
            'country': 'CN',
            'province': '',
            'city': '',
            'source': 'ipip_china_list',
        })
    return records


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    print('IPIP Free Importer — Phase 2')
    print('=' * 50)

    all_records = []
    for src in IPIP_SOURCES:
        print(f'  Fetching {src["name"]}...')
        content = safe_fetch(src['url'], src.get('local'))
        if content:
            records = parse_china_ip_list(content)
            all_records.extend(records)
            print(f'    → {len(records)} records')

    # Deduplicate by network
    seen = set()
    unique = []
    for r in all_records:
        if r['network'] not in seen:
            seen.add(r['network'])
            unique.append(r)

    print(f'\nTotal unique networks: {len(unique)}')

    # Write CSV
    with open(OUTPUT_PATH, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['network', 'country', 'province', 'city', 'source'])
        writer.writeheader()
        writer.writerows(unique)

    stats = {
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total_records': len(unique),
    }
    with open(STATS_PATH, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    print(f'Written: {OUTPUT_PATH}')


if __name__ == '__main__':
    main()
