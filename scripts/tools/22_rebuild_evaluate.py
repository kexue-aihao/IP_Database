#!/usr/bin/env python3
"""Subagent S9: MMDB Rebuild & Evaluation — Phase 6. Rebuilds MMDB from fused_v2 and evaluates."""
import csv, json, os, sys, subprocess
from datetime import datetime
BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTPUT_DIR = os.path.join(BASE, 'output')
FUSED_V2 = os.path.join(OUTPUT_DIR, 'china_ipv4_fused_v2.csv')
V2_MMDB = os.path.join(OUTPUT_DIR, 'china_ipv4_high_prec_v2.mmdb')
REPORT_V2 = os.path.join(OUTPUT_DIR, 'precision_report_v2.json')
def build_mmdb():
    """Build MMDB v2 from fused_v2 CSV (reuse confidence modeler logic)."""
    import sys
    sys.path.insert(0, os.path.join(BASE, 'scripts'))
    try:
        from mmdb_writer import MMDBWriter
    except ImportError:
        print('[ERROR] mmdb_writer not available')
        return None
    import ipaddress
    from netaddr import IPSet, IPNetwork
    if not os.path.exists(FUSED_V2):
        print(f'[ERROR] {FUSED_V2} not found'); return None
    def confidence_to_radius(confidence):
        if confidence >= 0.9: return 20
        elif confidence >= 0.7: return 50
        elif confidence >= 0.5: return 100
        else: return 200
    def ip_range_to_cidrs(start_ip, end_ip):
        try:
            start = ipaddress.IPv4Address(start_ip)
            end = ipaddress.IPv4Address(end_ip)
            return [str(n) for n in ipaddress.summarize_address_range(start, end)]
        except ValueError:
            return []
    writer = MMDBWriter()
    count = 0
    with open(FUSED_V2, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            start_ip = row['start_ip']; end_ip = row['end_ip']
            if not start_ip or not end_ip: continue
            # Skip IPv6 (this is v4 fusion output)
            if ':' in start_ip: continue
            cidrs = ip_range_to_cidrs(start_ip, end_ip)
            if not cidrs: continue
            try: confidence = float(row['confidence'])
            except (ValueError, TypeError): confidence = 0.3
            data = {
                'province': row['province'], 'city': row['city'],
                'confidence': confidence,
                'accuracy_radius': confidence_to_radius(confidence),
                'source': row['sources'],
            }
            if row['latitude'] and row['longitude']:
                try:
                    data['latitude'] = float(row['latitude'])
                    data['longitude'] = float(row['longitude'])
                except ValueError: pass
            for cidr_str in cidrs:
                try:
                    writer.insert_network(IPSet(IPNetwork(cidr_str)), data)
                    count += 1
                except Exception: pass
    writer.to_db_file(V2_MMDB)
    print(f'Written {count} networks to {V2_MMDB}')
    return V2_MMDB
def evaluate():
    """Run evaluate_precision.py on v2 MMDB."""
    eval_script = os.path.join(BASE, 'scripts', 'evaluate_precision.py')
    cmd = ['python', eval_script, '--mmdb', V2_MMDB]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    print(f'Evaluation exit: {result.returncode}')
    return result.stdout[-3000:] if result.stdout else result.stderr[-1000:]
def main():
    print('=' * 60)
    print('Subagent S9: MMDB Rebuild & Evaluation')
    print('=' * 60)
    mmdb = build_mmdb()
    if mmdb:
        print()
        print('Evaluating v2 MMDB...')
        out = evaluate()
        print(out)
if __name__ == '__main__':
    main()