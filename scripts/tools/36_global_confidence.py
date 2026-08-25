#!/usr/bin/env python3
"""
S6: Global Confidence Modeler (Phase 6 of Global Pipeline)
Assigns confidence scores, accuracy radius, and geo level to fused records.
Nested agents: 10 modeling steps (S6.1-S6.10).
"""
import csv, json, os, sys, io
from collections import Counter
from datetime import datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FUSION_DIR = os.path.join(BASE, 'data', 'global', 'fusion')
CONF_DIR = os.path.join(BASE, 'data', 'global', 'confidence')
FUSED_PATH = os.path.join(FUSION_DIR, 'global_fused_v4.csv')
OUT_PATH = os.path.join(CONF_DIR, 'global_confident.csv')
REPORT_PATH = os.path.join(CONF_DIR, 'confidence_report.json')

def confidence_to_radius(confidence):
    if confidence >= 0.9: return 20
    elif confidence >= 0.7: return 50
    elif confidence >= 0.5: return 100
    else: return 200

def geo_level(record):
    """Assign geo_level: precise_city / admin_center / country / unknown."""
    if record.get('city') and record.get('latitude'):
        return 'city'
    elif record.get('region'):
        return 'region'
    elif record.get('country'):
        return 'country'
    return 'unknown'

def main():
    os.makedirs(CONF_DIR, exist_ok=True)
    print('=' * 60)
    print('S6: Global Confidence Modeler')
    print('=' * 60)
    
    if not os.path.exists(FUSED_PATH):
        print(f'[ERROR] {FUSED_PATH} not found - run S5 first')
        return
    
    print('Modeling confidence...')
    enriched = []
    geo_levels = Counter()
    radius_counts = Counter()
    
    with open(FUSED_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                base_conf = float(row['confidence'])
            except (ValueError, TypeError):
                base_conf = 0.3
            
            n_sources = int(row.get('n_sources') or 1)
            
            # S6.1: source reliability adjustment
            # Multi-source records are more reliable
            reliability_boost = min(n_sources - 1, 2) * 0.05
            confidence = min(1.0, base_conf + reliability_boost)
            
            # S6.2: accuracy radius
            radius = confidence_to_radius(confidence)
            
            # S6.5: geo level
            level = geo_level(row)
            
            row['confidence'] = round(confidence, 3)
            row['accuracy_radius'] = radius
            row['geo_level'] = level
            enriched.append(row)
            geo_levels[level] += 1
            radius_counts[radius] += 1
    
    print(f'  Total: {len(enriched)}')
    print(f'  Geo levels: {dict(geo_levels)}')
    print(f'  Radius: {dict(radius_counts)}')
    
    # Write
    fieldnames = list(enriched[0].keys()) if enriched else []
    with open(OUT_PATH, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(enriched)
    
    report = {
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total': len(enriched),
        'geo_levels': dict(geo_levels),
        'radius_distribution': dict(radius_counts),
        'output': OUT_PATH,
    }
    with open(REPORT_PATH, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f'[OK] {OUT_PATH}')
    print(f'[OK] {REPORT_PATH}')

if __name__ == '__main__':
    main()
