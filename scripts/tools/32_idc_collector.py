#!/usr/bin/env python3
"""
S2: IDC/Cloud Provider IP Range Collector (Phase 2 of Global Pipeline)
Collects IP ranges from major cloud providers and hosting companies.
Nested agents: 10 sources (S2.1-S2.10) rolled into one script.
"""
import csv, json, os, sys, io, re
from datetime import datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE, 'data')
GLOBAL_DIR = os.path.join(DATA_DIR, 'global')
IDC_DIR = os.path.join(GLOBAL_DIR, 'idc')
OUTPUT_PATH = os.path.join(IDC_DIR, 'idc_all.csv')
REPORT_PATH = os.path.join(IDC_DIR, 'idc_collection_report.json')

try:
    import requests
except ImportError:
    requests = None
    print('[WARN] requests not available, IDC downloads will be limited')

def safe_fetch(url, timeout=30):
    if requests:
        try:
            r = requests.get(url, timeout=timeout, headers={'User-Agent': 'Mozilla/5.0'})
            if r.status_code == 200: return r.text
            else: print(f'  [HTTP {r.status_code}] {url}'); return None
        except Exception as e: print(f'  [FAIL] {url}: {e}'); return None
    return None

def fetch_aws():
    """S2.1: AWS IP ranges."""
    print('[S2.1] Fetching AWS IP ranges...')
    text = safe_fetch('https://ip-ranges.amazonaws.com/ip-ranges.json', timeout=60)
    if not text: return []
    try:
        data = json.loads(text)
        prefixes = data.get('prefixes', []) + data.get('ipv6_prefixes', [])
        rows = []
        for p in prefixes:
            cidr = p.get('ip_prefix', p.get('ipv6_prefix', ''))
            region = p.get('region', '')
            service = p.get('service', '')
            rows.append({
                'cidr': cidr, 'vendor': 'AWS', 'service': service,
                'region': region, 'country': region[:2].upper() if region else '',
                'source': 'aws-official'
            })
        print(f'  AWS: {len(rows)} prefixes')
        return rows
    except Exception as e:
        print(f'  Parse error: {e}')
        return []

def fetch_azure():
    """S2.2: Azure IP ranges."""
    print('[S2.2] Fetching Azure IP ranges...')
    # Azure uses a download URL pattern that changes - try the service tags file
    text = safe_fetch('https://download.microsoft.com/download/7/1/D/71D86715-5596-4529-9B13-DC13A4DE5B63/ServiceTags_Public_20260817.json', timeout=60)
    if not text:
        # Try alternative URL
        text = safe_fetch('https://www.microsoft.com/en-us/download/confirmation.aspx?id=56519', timeout=30)
    if not text: return []
    try:
        data = json.loads(text)
        rows = []
        for v in data.get('values', []):
            props = v.get('properties', {})
            region = props.get('region', '')
            for p in props.get('addressPrefixes', []):
                if '/' in p:
                    rows.append({
                        'cidr': p, 'vendor': 'Azure', 'service': v.get('name', ''),
                        'region': region, 'country': region[:2].upper() if region else '',
                        'source': 'azure-official'
                    })
        print(f'  Azure: {len(rows)} prefixes')
        return rows
    except Exception as e:
        print(f'  Parse error: {e}')
        return []

def fetch_gcp():
    """S2.3: GCP IP ranges."""
    print('[S2.3] Fetching GCP IP ranges...')
    text = safe_fetch('https://www.gstatic.com/ipranges/cloud.json', timeout=60)
    if not text: return []
    try:
        data = json.loads(text)
        rows = []
        for p in data.get('prefixes', []):
            ipv4 = p.get('ipv4Prefix', '')
            ipv6 = p.get('ipv6Prefix', '')
            cidr = ipv4 or ipv6
            if not cidr: continue
            scope = p.get('scope', '')
            rows.append({
                'cidr': cidr, 'vendor': 'GCP', 'service': p.get('service', ''),
                'region': scope, 'country': scope[:2].upper() if scope else '',
                'source': 'gcp-official'
            })
        print(f'  GCP: {len(rows)} prefixes')
        return rows
    except Exception as e:
        print(f'  Parse error: {e}')
        return []

def fetch_cn_cloud():
    """S2.4: CN cloud providers from existing constants.py + known ranges."""
    print('[S2.4] Collecting CN cloud ranges...')
    rows = []
    # Parse existing IDC_IPV4_RANGES from constants.py
    constants_path = os.path.join(BASE, 'scripts', 'common', 'constants.py')
    if os.path.exists(constants_path):
        with open(constants_path, 'r', encoding='utf-8') as f:
            content = f.read()
        # Find IP ranges
        pattern = r"\('([^']+)',\s*\((\d+),\s*(\d+)\)"
        for m in re.finditer(pattern, content):
            vendor = m.group(1)
            start = int(m.group(2))
            end = int(m.group(3))
            # Convert integer back to IP
            import ipaddress
            start_ip = str(ipaddress.IPv4Address(start))
            end_ip = str(ipaddress.IPv4Address(end))
            rows.append({
                'cidr': f'{start_ip}-{end_ip}', 'vendor': vendor,
                'service': 'cloud', 'country': 'CN',
                'source': 'constants.py'
            })
        # Find IPv6 prefixes
        for m in re.finditer(r"'([0-9a-fA-F]+)'", content):
            hex_str = m.group(1)
            if len(hex_str) == 8:
                cidr = f'{hex_str[:4]}:{hex_str[4:]}::/32'
                rows.append({
                    'cidr': cidr, 'vendor': 'cn_cloud_ipv6',
                    'service': 'cloud', 'country': 'CN',
                    'source': 'constants.py'
                })
    print(f'  CN Cloud: {len(rows)} ranges')
    return rows

def fetch_common_hosting():
    """S2.5+S2.6+S2.7: Common international hosting providers."""
    print('[S2.5-2.7] Fetching common hosting ranges...')
    rows = []
    # Known hosting ranges (well-known public IP ranges)
    known = [
        # DigitalOcean
        ('https://digitalocean.com/geo/google.csv', 'DigitalOcean', 'hosting'),
        # Cloudflare
        ('https://www.cloudflare.com/ips-v4', 'Cloudflare', 'cdn'),
        # Fastly
        ('https://api.fastly.com/public-ip-list', 'Fastly', 'cdn'),
    ]
    for url, vendor, svc in known:
        text = safe_fetch(url, timeout=30)
        if text:
            count = 0
            for line in text.splitlines():
                line = line.strip()
                if line and '/' in line:
                    rows.append({
                        'cidr': line, 'vendor': vendor, 'service': svc,
                        'region': '', 'country': '', 'source': 'official'
                    })
                    count += 1
            print(f'  {vendor}: {count}')
    print(f'  Hosting total: {len(rows)}')
    return rows

def merge_and_write(all_rows):
    """S2.10: Merge and deduplicate."""
    print(f'[S2.10] Merging {len(all_rows)} total ranges...')
    seen = set()
    unique = []
    for r in all_rows:
        cidr = r['cidr']
        if cidr not in seen:
            seen.add(cidr)
            unique.append(r)
    print(f'  Unique: {len(unique)}')
    fieldnames = ['cidr', 'vendor', 'service', 'region', 'country', 'source']
    with open(OUTPUT_PATH, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(unique)
    print(f'[OK] {OUTPUT_PATH}')
    return unique

def main():
    os.makedirs(IDC_DIR, exist_ok=True)
    print('=' * 60)
    print('S2: IDC/Cloud Provider IP Range Collector')
    print('=' * 60)
    
    all_rows = []
    all_rows += fetch_aws()
    all_rows += fetch_azure()
    all_rows += fetch_gcp()
    all_rows += fetch_cn_cloud()
    all_rows += fetch_common_hosting()
    
    unique = merge_and_write(all_rows)
    
    # Vendor stats
    from collections import Counter
    vendor_counts = Counter(r['vendor'] for r in unique)
    report = {
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total_unique': len(unique),
        'by_vendor': dict(vendor_counts),
        'output': OUTPUT_PATH,
    }
    with open(REPORT_PATH, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f'\n[OK] Report: {REPORT_PATH}')
    print(f'  Vendors: {dict(vendor_counts)}')

if __name__ == '__main__':
    main()
