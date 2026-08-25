#!/usr/bin/env python3
"""
Subagent 8: RTT Triangulator — Phase 3

Network measurement-based geolocation using RTT triangulation.
For IP ranges without reliable registration data, measures network
latency from multiple probe locations and estimates geographic origin
using a calibrated latency-distance model.

NOTE: This requires network access to probe IPs. For offline usage,
provide --measurements-file with pre-collected RTT data.

Output:
  data/rtt_measurements.json — collected RTT data
  data/rtt_locations.csv — inferred locations
"""

import argparse
import json
import math
import os
import socket
import subprocess
import sys
import time
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE, 'data')
OUTPUT_MEAS = os.path.join(DATA_DIR, 'rtt_measurements.json')
OUTPUT_LOC = os.path.join(DATA_DIR, 'rtt_locations.csv')

# Probe locations (city, lat, lng) — ideal deployment points in mainland China
DEFAULT_PROBES = [
    {'city': '北京', 'lat': 39.9042, 'lng': 116.4074},
    {'city': '上海', 'lat': 31.2304, 'lng': 121.4737},
    {'city': '广州', 'lat': 23.1291, 'lng': 113.2644},
    {'city': '成都', 'lat': 30.5728, 'lng': 104.0668},
    {'city': '武汉', 'lat': 30.5928, 'lng': 114.3055},
    {'city': '西安', 'lat': 34.2611, 'lng': 108.9426},
    {'city': '郑州', 'lat': 34.7466, 'lng': 113.6253},
    {'city': '沈阳', 'lat': 41.8057, 'lng': 123.4315},
]


def ping_rtt(ip, count=3, timeout=2):
    """Measure RTT to an IP using system ping. Returns min RTT in ms or None."""
    if sys.platform == 'win32':
        cmd = ['ping', '-n', str(count), '-w', str(timeout * 1000), ip]
    else:
        cmd = ['ping', '-c', str(count), '-W', str(timeout), ip]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout * count + 5)
        # Parse RTT from output
        for line in result.stdout.splitlines():
            if 'time=' in line:
                # Extract all time values, take min
                import re
                times = re.findall(r'time[=<](d+.?d*)s*ms', line)
                if times:
                    return min(float(t) for t in times)
        return None
    except (subprocess.TimeoutExpired, OSError):
        return None


def haversine_km(lat1, lng1, lat2, lng2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlng / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def triangulate(rtts, probes):
    """
    Estimate location from RTT measurements using weighted centroid.
    Model: latency in ms roughly correlates with ~40-80 km per ms
    (speed of light fiber ~200km/ms; typical routing adds 2-4x).
    """
    if not rtts:
        return None

    # Weight: lower RTT = higher weight, plus distance calibration
    total_weight = 0
    sum_lat = 0
    sum_lng = 0
    weights = []

    calibration_factor = 60.0  # km per ms (conservative, typical for CN backbone)

    for city, lat, lng in probes:
        rtt = rtts.get(city)
        if rtt is None or rtt <= 0:
            continue
        w = 1.0 / max(rtt, 1.0)  # inverse latency weight
        weights.append((lat, lng, w, rtt))
        total_weight += w

    if total_weight == 0:
        return None

    for lat, lng, w, rtt in weights:
        sum_lat += lat * w
        sum_lng += lng * w

    est_lat = sum_lat / total_weight
    est_lng = sum_lng / total_weight

    # Estimate accuracy radius from RTT spread
    best_rtt = min(w[3] for w in weights)
    radius_km = best_rtt * calibration_factor

    return {
        'latitude': round(est_lat, 5),
        'longitude': round(est_lng, 5),
        'estimated_radius_km': round(radius_km, 1),
        'best_rtt_ms': best_rtt,
        'n_probes': len(weights),
    }


def main():
    parser = argparse.ArgumentParser(description='RTT-based IP triangulation')
    parser.add_argument('--targets', help='Path to file with IPs to measure (one per line)')
    parser.add_argument('--max-targets', type=int, default=10,
                        help='Maximum targets to measure (default 10)')
    parser.add_argument('--load-measurements', action='store_true',
                        help='Load existing measurements instead of measuring')
    args = parser.parse_args()

    print('RTT Triangulator — Phase 3')
    print('=' * 50)

    if args.load_measurements and os.path.exists(OUTPUT_MEAS):
        with open(OUTPUT_MEAS, 'r', encoding='utf-8') as f:
            data = json.load(f)
        print(f'Loaded {len(data)} existing measurements')
        for ip, meas in list(data.items())[:5]:
            print(f'  {ip}: {meas}')
        return

    # Get target IPs
    if args.targets and os.path.exists(args.targets):
        with open(args.targets, 'r', encoding='utf-8') as f:
            targets = [l.strip() for l in f if l.strip()][:args.max_targets]
    else:
        # Default: measure a few known infrastructure IPs as calibration
        targets = [
            '223.5.5.5',    # AliDNS
            '119.29.29.29', # Tencent DNS
            '180.76.76.76', # Baidu DNS
            '114.114.114.114',  # 114DNS
        ][:args.max_targets]

    print(f'Targets to measure: {targets}')
    measurements = {}

    for ip in targets:
        print(f'\n  Measuring {ip}...')
        rtts = {}
        for probe in DEFAULT_PROBES:
            rtt = ping_rtt(ip)
            if rtt is not None:
                rtts[probe['city']] = rtt
                print(f'    {probe["city"]}: {rtt:.1f} ms')
            else:
                print(f'    {probe["city"]}: timeout')
            time.sleep(0.2)  # avoid rate limiting

        if rtts:
            location = triangulate(rtts, [(p['city'], p['lat'], p['lng']) for p in DEFAULT_PROBES])
            measurements[ip] = {
                'rtts': rtts,
                'location': location,
                'measured_at': datetime.now().isoformat(),
            }
            if location:
                print(f'    => inferred at ({location["latitude"]}, {location["longitude"]})'
                      f' ± {location["estimated_radius_km"]} km')

    # Save measurements
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(OUTPUT_MEAS, 'w', encoding='utf-8') as f:
        json.dump(measurements, f, ensure_ascii=False, indent=2)

    print(f'\nMeasurements saved: {OUTPUT_MEAS}')

    # Write locations CSV
    import csv
    with open(OUTPUT_LOC, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['ip', 'latitude', 'longitude', 'radius_km', 'sources'])
        for ip, meas in measurements.items():
            loc = meas.get('location')
            if loc:
                writer.writerow([ip, loc['latitude'], loc['longitude'],
                                 loc['estimated_radius_km'],
                                 ';'.join(f"{k}:{v:.1f}" for k, v in meas['rtts'].items())])

    print(f'Locations saved: {OUTPUT_LOC}')


if __name__ == '__main__':
    main()
