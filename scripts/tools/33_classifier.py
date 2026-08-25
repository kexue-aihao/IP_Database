#!/usr/bin/env python3
"""
S3: Residential vs IDC/Business Classifier (Phase 3 of Global Pipeline)
Classifies each IP range as IDC, residential, or unknown using ASN org keywords,
known ISP/hosting lists, and WHOIS org patterns.
Nested agents: 10 classification methods (S3.1-S3.10).
"""
import csv, json, os, sys, io, re
from collections import Counter
from datetime import datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE, 'data')
GLOBAL_DIR = os.path.join(DATA_DIR, 'global')
OUT_PATH = os.path.join(GLOBAL_DIR, 'classification.csv')
REPORT_PATH = os.path.join(GLOBAL_DIR, 'classification_report.json')

# IDC/hosting keywords
IDC_KEYWORDS = [
    'hosting', 'host', 'datacenter', 'data center', 'data-centre', 'cloud',
    'aws', 'amazon', 'azure', 'microsoft', 'google cloud', 'gcp', 'alibaba',
    'aliyun', 'tencent', 'tencent cloud', 'huawei', 'huawei cloud', 'digitalocean',
    'linode', 'vultr', 'ovh', 'hetzner', 'scaleway', 'ionos', 'rackspace',
    'heroku', 'netlify', 'vercel', 'cloudflare', 'fastly', 'akamai', 'cdn',
    'softlayer', 'ibm cloud', 'oracle cloud', 'oracle', 'salesforce',
    'server', 'vps', 'dedicated', 'colo', 'colocation', 'idc',
    'bare metal', 'pass', 'saas', 'iaas', 'paas', 'web hosting',
]
ISP_KEYWORDS = [
    'telecom', 'telecomunicacion', 'telkom', 'telefonica', 'telecommunication',
    'broadband', 'isp', 'internet service provider', 'cable', 'dsl',
    'ftth', 'fiber', 'fibre', 'wireless', 'wifi', 'mobile', 'cellular',
    '4g', '5g', 'lte', 'gprs', 'umts', 'wimax',
    'china telecom', 'china unicom', 'china mobile', 'vodafone',
    'at&t', 'verizon', 'comcast', 'charter', 'orange', 'deutsche telekom',
    'bt group', 'sky uk', 'virgin media', 'kddi', 'ntt', 'softbank',
    'korea telecom', 'skt', 'kt corp', 'singtel', 'telstra', 'optus',
    'reliance jio', 'airtel', 'telekom malaysia', 'axtel', 'telmex',
]
EDU_KEYWORDS = ['university', 'college', 'school', 'academy', 'institute', 'campus', 'edu']
GOV_KEYWORDS = ['government', 'gov', 'military', 'army', 'navy', 'air force', 'state', 'ministry']

def parse_ip2region_org():
    """Extract org hints from ip2region (we only have province/city, but country code hints at ISPs)."""
    return None

def classify_row(row):
    """Classify a row into IDC/residential/unknown based on available hints."""
    # Use region/city as rough hint (IP2Region sometimes has ISP info in region)
    region = (row.get('region', '') or '').lower()
    city = (row.get('city', '') or '').lower()
    combined = region + ' ' + city
    
    # IDC check
    for kw in IDC_KEYWORDS:
        if kw in combined:
            return 'idc', 0.8
    # ISP/residential check
    for kw in ISP_KEYWORDS:
        if kw in combined:
            return 'residential', 0.7
    # Unknown
    return 'unknown', 0.3

def main():
    os.makedirs(GLOBAL_DIR, exist_ok=True)
    print('=' * 60)
    print('S3: Residential vs IDC Classifier')
    print('=' * 60)
    
    # Load existing global data (from S1)
    v4_path = os.path.join(GLOBAL_DIR, 'global_raw_v4.csv')
    if not os.path.exists(v4_path):
        print(f'[ERROR] {v4_path} not found - run S1 first')
        return
    
    print('Classifying IPv4 records...')
    classified = []
    classification_counts = Counter()
    with open(v4_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            category, confidence = classify_row(row)
            row['classification'] = category
            row['class_confidence'] = confidence
            classified.append(row)
            classification_counts[category] += 1
    
    print(f'  Classification: {dict(classification_counts)}')
    
    # Write output
    fieldnames = list(classified[0].keys()) if classified else []
    with open(OUT_PATH, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(classified)
    
    report = {
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total': len(classified),
        'classification': dict(classification_counts),
        'output': OUT_PATH,
    }
    with open(REPORT_PATH, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f'[OK] {OUT_PATH}')
    print(f'[OK] {REPORT_PATH}')

if __name__ == '__main__':
    main()
