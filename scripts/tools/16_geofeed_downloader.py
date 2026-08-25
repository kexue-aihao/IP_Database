#!/usr/bin/env python3
"""Subagent S6: Geofeed Downloader — Phase 6 (Priority 2). Downloads CAIDA geofeed data + sapics user-country."""
import csv, gzip, io, json, os, re, concurrent.futures, sys
from datetime import datetime
try:
    import requests
except ImportError:
    requests = None
    print('[WARN] requests not available, falling back to urllib')
BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE, 'data')
GEOFEED_DIR = os.path.join(DATA_DIR, 'geofeed')
CAIDA_BASE = 'https://publicdata.caida.org/datasets/geofeed-whois/2026/06/10/registries/apnic/standard/'
SAPICS_URL = 'https://raw.githubusercontent.com/sapics/ip-location-db/main/user-country/user-country-ipv4.csv'
OUTPUT_RAW = os.path.join(GEOFEED_DIR, 'china_geofeed_raw.csv')
OUTPUT_STATS = os.path.join(GEOFEED_DIR, 'geofeed_sources.json')
TARGET_COUNTRIES = {'CN', 'HK', 'TW', 'MO'}
def safe_fetch(url, timeout=30):
    if requests:
        try:
            r = requests.get(url, timeout=timeout, headers={'User-Agent': 'Mozilla/5.0'})
            if r.status_code == 200:
                return r.text
            else:
                print(f'  [HTTP {r.status_code}] {url}')
                return None
        except Exception as e:
            print(f'  [FAIL] {url}: {e}')
            return None
    else:
        try:
            import urllib.request
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode('utf-8', errors='replace')
        except Exception as e:
            print(f'  [FAIL] {url}: {e}')
            return None
def fetch_caida_geofeeds():
    """Download CAIDA file listing, then fetch all files, extract CN lines."""
    print(f'\n[CAIDA] Fetching directory listing: {CAIDA_BASE}')
    html = safe_fetch(CAIDA_BASE, timeout=30)
    if not html:
        print('[CAIDA] Cannot fetch directory listing')
        return []
    files = sorted(set(re.findall(r'href="(apnic_geofeed_[^"?]+)"', html)))
    print(f'[CAIDA] Found {len(files)} geofeed files')
    # Check which files might contain CN via filename hints
    cn_hint_files = [f for f in files if any(k in f.lower() for k in ['cn', 'china', 'telecom', 'unicom', 'mobile', 'hk'])]
    if cn_hint_files:
        print(f'  CN-hinted files: {cn_hint_files}')
    # Download and check each file for CN records
    def check_file(fname):
        url = CAIDA_BASE + fname
        try:
            if requests:
                r = requests.get(url, timeout=20, headers={'User-Agent': 'Mozilla/5.0'}, stream=True)
                if r.status_code != 200:
                    return []
                chunk = r.content[:50000]
            else:
                import urllib.request
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=20) as resp:
                    chunk = resp.read(50000)
            text = chunk.decode('utf-8', errors='replace')
            cn_lines = []
            for line in text.splitlines():
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                parts = line.split(',')
                if len(parts) >= 3 and parts[1].strip().upper() in TARGET_COUNTRIES:
                    cn_lines.append(line)
            # If we need more, get the rest
            if len(cn_lines) >= 10 and len(chunk) >= 40000:
                # Read full file
                if requests:
                    r = requests.get(url, timeout=30, headers={'User-Agent': 'Mozilla/5.0'})
                    if r.status_code == 200:
                        text = r.text
                        cn_lines = []
                        for line in text.splitlines():
                            line = line.strip()
                            if not line or line.startswith('#'):
                                continue
                            parts = line.split(',')
                            if len(parts) >= 3 and parts[1].strip().upper() in TARGET_COUNTRIES:
                                cn_lines.append(line)
            return cn_lines
        except Exception as e:
            return []
    records = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
        futures = {ex.submit(check_file, f): f for f in files}
        for future in concurrent.futures.as_completed(futures):
            fname = futures[future]
            try:
                lines = future.result()
                if lines:
                    for line in lines:
                        records.append({'source': 'caida:' + fname, 'raw': line})
                    print(f'  [CN] {fname}: {len(lines)} records')
            except Exception as e:
                pass
    print(f'[CAIDA] Total CN records: {len(records)}')
    return records
def fetch_sapics_user_country():
    """Download sapics user-country-ipv4.csv, extract CN rows."""
    print(f'\n[SAPICS] Fetching user-country-ipv4.csv...')
    text = safe_fetch(SAPICS_URL, timeout=60)
    if not text:
        print('[SAPICS] Failed')
        return [], 0
    total = 0
    cn_rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(',')
        if len(parts) >= 3 and parts[2].strip().upper() == 'CN':
            cn_rows.append(line)
        total += 1
    print(f'[SAPICS] Total rows: {total}, CN rows: {len(cn_rows)}')
    return cn_rows, total
def main():
    os.makedirs(GEOFEED_DIR, exist_ok=True)
    print('=' * 60)
    print('Subagent S6: Geofeed Downloader — Phase 6 (Priority 2)')
    print('=' * 60)
    # 1. CAIDA geofeed files
    caida_records = fetch_caida_geofeeds()
    # 2. sapics user-country
    sapics_rows, sapics_total = fetch_sapics_user_country()
    # 3. Write raw CSV
    all_records = []
    for r in caida_records:
        all_records.append({'source': r['source'], 'raw': r['raw']})
    for row in sapics_rows:
        all_records.append({'source': 'sapics:user-country', 'raw': row})
    print(f'\n[WRITE] Total raw records: {len(all_records)}')
    with open(OUTPUT_RAW, 'w', encoding='utf-8', newline='') as f:
        f.write('source,raw_line\n')
        for r in all_records:
            f.write(f'{r["source"]},{r["raw"]}\n')
    # 4. Stats / sources
    sources_info = {
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'caida': {
            'base_url': CAIDA_BASE,
            'files_with_cn': len(set(r['source'] for r in caida_records)),
            'total_cn_records': len(caida_records),
        },
        'sapics': {
            'url': SAPICS_URL,
            'total_rows': sapics_total,
            'cn_rows': len(sapics_rows),
        },
        'total_raw_records': len(all_records),
        'output_raw': OUTPUT_RAW,
    }
    with open(OUTPUT_STATS, 'w', encoding='utf-8') as f:
        json.dump(sources_info, f, ensure_ascii=False, indent=2)
    print(f'\n[OK] Sources info: {OUTPUT_STATS}')
    print(f'  CAIDA CN files: {len(set(r["source"] for r in caida_records))}')
    print(f'  CAIDA CN records: {len(caida_records)}')
    print(f'  SAPICS CN rows: {len(sapics_rows)}')
    print(f'  Total raw: {len(all_records)}')
if __name__ == '__main__':
    main()