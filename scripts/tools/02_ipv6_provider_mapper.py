#!/usr/bin/env python3
"""
Subagent 2: IPv6 Provider Mapper — Phase 1

Maps IPv6 prefixes to provinces using:
1. APNIC delegated stats
2. ip2region IPv6 data (has province/city for many subnets)
"""

import json
import os
import re
from collections import Counter
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE, 'data')
IP2R_V6_PATH = os.path.join(DATA_DIR, 'ip2region_data', 'ipv6_source.txt')
APNIC_PATH = os.path.join(DATA_DIR, 'delegated-apnic-latest')
OUTPUT_PATH = os.path.join(DATA_DIR, 'ipv6_provider_map.json')

# /16 prefix → ISP mapping
IPV6_ISP_PREFIXES = {
    '240e': 'telecom',
    '2408': 'unicom',
    '2409': 'mobile',
}

# Known /16 prefix → default province (from APNIC allocation records)
PREFIX_PROVINCE = {
    '240e': '北京',    # China Telecom HQ
    '2408': '北京',    # China Unicom HQ
    '2409': '北京',    # China Mobile HQ
    '2001': '北京',    # CERNET/CNGI (various, default Beijing)
    '2400': '北京',    # Various Chinese allocations
    '2401': '北京',
    '2402': '北京',
    '2403': '北京',
    '2404': '北京',
    '2405': '北京',
    '2406': '北京',
    '2407': '北京',
    '240a': '北京',
    '240b': '北京',
    '240c': '北京',
    '240d': '北京',
    '240f': '北京',
}


def parse_apnic(path):
    """Parse APNIC for Chinese IPv6 allocations."""
    prefixes_by_16 = Counter()
    allocations = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split('|')
            if len(parts) < 7 or parts[2] != 'ipv6' or parts[1] not in ('CN', 'HK', 'TW', 'MO'):
                continue
            prefix = parts[3]
            length = int(parts[4])
            first_hex = prefix.split(':')[0].lower() if ':' in prefix else prefix.lower()[:4]
            prefixes_by_16[first_hex] += 1
            allocations.append({
                'prefix': prefix, 'prefix_len': length,
                'country': parts[1], 'first_hex': first_hex,
                'status': parts[6],
            })
    print(f'  APNIC: {len(allocations)} Chinese IPv6 allocations')
    print(f'  Top /16 prefixes: {prefixes_by_16.most_common(15)}')
    return allocations, prefixes_by_16


def parse_ip2region_v6(path):
    """Extract province info from ip2region IPv6 data."""
    prov_by_prefix = {}
    prov_by_16 = Counter()
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split('|')
            if len(parts) < 7:
                continue
            cc = parts[6]
            if cc not in ('CN', 'HK', 'TW', 'MO'):
                continue
            province = parts[3] if len(parts) > 3 else ''
            if not province or province in ('0', 'Reserved', ''):
                continue
            start_ip = parts[0]
            p_parts = start_ip.split(':')
            if len(p_parts) >= 1:
                first_hex = p_parts[0].lower()
                prov_by_16[first_hex] += 1
                if first_hex not in prov_by_prefix:
                    prov_by_prefix[first_hex] = Counter()
                prov_by_prefix[first_hex][province] += 1
    print(f'  ip2region: {len(prov_by_prefix)} /16 prefixes with province data')
    # Show top province for each prefix
    for ph in sorted(prov_by_prefix.keys())[:20]:
        most_common = prov_by_prefix[ph].most_common(3)
        print(f'    {ph}: {most_common}')
    return prov_by_prefix, prov_by_16


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    print('IPv6 Provider Mapper — Phase 1')
    print('=' * 50)

    apnic_allocs, apnic_by_16 = parse_apnic(APNIC_PATH)
    ip2r_prov, ip2r_by_16 = parse_ip2region_v6(IP2R_V6_PATH)

    # Build final mapping: for each /16 prefix, determine ISP and province
    all_16_prefixes = set(apnic_by_16.keys()) | set(ip2r_by_16.keys())
    results = []

    for ph in sorted(all_16_prefixes):
        isp = IPV6_ISP_PREFIXES.get(ph, 'other')
        province = PREFIX_PROVINCE.get(ph, '')

        # If ip2region has province data for this prefix, use the most common
        if ph in ip2r_prov:
            most_common_prov = ip2r_prov[ph].most_common(1)
            if most_common_prov:
                province = most_common_prov[0][0]

        apnic_count = apnic_by_16.get(ph, 0)
        ip2r_count = ip2r_by_16.get(ph, 0)

        results.append({
            'prefix_16': ph,
            'isp': isp,
            'province': province,
            'apnic_allocations': apnic_count,
            'ip2region_subnets': ip2r_count,
        })

    # Write output
    output = {
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total_prefixes': len(results),
        'prefixes': results,
        'summary': {
            'by_isp': Counter(r['isp'] for r in results),
            'by_province': Counter(r['province'] or 'unknown' for r in results),
        }
    }

    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f'\nTotal /16 prefixes: {len(results)}')
    print(f'By ISP: {dict(output["summary"]["by_isp"])}')
    provs = {k: v for k, v in sorted(output['summary']['by_province'].items(), key=lambda x: -x[1])[:15]}
    print(f'By province (top 15): {provs}')
    print(f'Written to: {OUTPUT_PATH}')


if __name__ == '__main__':
    main()
