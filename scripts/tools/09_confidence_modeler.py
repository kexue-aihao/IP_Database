#!/usr/bin/env python3
"""
Subagent 9: Confidence Modeler — Phase 4

Builds upgraded MMDB files with confidence, accuracy_radius, source fields
from the fused CSV produced by the vote fusion engine.

Usage:
  python scripts/tools/09_confidence_modeler.py
"""

import csv
import ipaddress
import json
import math
import os
import sys
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTPUT_DIR = os.path.join(BASE, 'output')
FUSED_V4 = os.path.join(OUTPUT_DIR, 'china_ipv4_fused.csv')
OUTPUT_MMDB = os.path.join(OUTPUT_DIR, 'china_ipv4_high_prec.mmdb')

# Try to import mmdb_writer (may be vendored in scripts dir)
sys.path.insert(0, os.path.join(BASE, 'scripts'))
try:
    from mmdb_writer import MMDBWriter
except ImportError:
    MMDBWriter = None


def confidence_to_accuracy_radius(confidence):
    """Estimate accuracy radius (km) from confidence score."""
    if confidence >= 0.9:
        return 20   # city-level precision
    elif confidence >= 0.7:
        return 50   # city-region
    elif confidence >= 0.5:
        return 100  # province
    else:
        return 200  # coarse


def ip_range_to_cidrs(start_ip, end_ip):
    try:
        start = ipaddress.IPv4Address(start_ip)
        end = ipaddress.IPv4Address(end_ip)
        return [str(n) for n in ipaddress.summarize_address_range(start, end)]
    except (ValueError, ipaddress.AddressValueError):
        return []


def build_mmdb():
    if MMDBWriter is None:
        print('[ERROR] mmdb_writer not available. Install it or run from scripts dir.')
        return None

    if not os.path.exists(FUSED_V4):
        print(f'[ERROR] Fused CSV not found: {FUSED_V4}')
        return None

    writer = MMDBWriter()

    count = 0
    with open(FUSED_V4, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            start_ip = row['start_ip']
            end_ip = row['end_ip']
            if not start_ip or not end_ip:
                continue

            cidrs = ip_range_to_cidrs(start_ip, end_ip)
            if not cidrs:
                continue

            try:
                confidence = float(row['confidence'])
            except (ValueError, TypeError):
                confidence = 0.3

            data = {
                'province': row['province'],
                'city': row['city'],
                'confidence': confidence,
                'accuracy_radius': confidence_to_accuracy_radius(confidence),
                'source': row['sources'],
            }
            if row['latitude'] and row['longitude']:
                try:
                    data['latitude'] = float(row['latitude'])
                    data['longitude'] = float(row['longitude'])
                except ValueError:
                    pass

            for cidr_str in cidrs:
                try:
                    from netaddr import IPSet, IPNetwork
                    writer.insert_network(IPSet(IPNetwork(cidr_str)), data)
                    count += 1
                except Exception:
                    pass

    writer.to_db_file(OUTPUT_MMDB)
    print(f'Written {count} networks to {OUTPUT_MMDB}')

    # Summary
    conf_summary = {'high': 0, 'medium': 0, 'low': 0}
    try:
        import maxminddb
        reader = maxminddb.open_database(OUTPUT_MMDB)
        for net, data in reader:
            c = data.get('confidence', 0)
            if c >= 0.8:
                conf_summary['high'] += 1
            elif c >= 0.5:
                conf_summary['medium'] += 1
            else:
                conf_summary['low'] += 1
        reader.close()
        print(f'Confidence distribution: {conf_summary}')
    except Exception as e:
        print(f'  (stats skipped: {e})')

    return OUTPUT_MMDB


def main():
    print('Confidence Modeler — Phase 4')
    print('=' * 50)
    result = build_mmdb()
    print('Done.')


if __name__ == '__main__':
    main()
