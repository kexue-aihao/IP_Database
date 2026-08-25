#!/usr/bin/env python3
"""Subagent S4: Coordinate Nearest Matcher — Phase 6. Matches unmatched city names via nearest coordinate."""
import csv, json, math, os, re
from datetime import datetime
csv.field_size_limit(100 * 1024 * 1024)  # ok_geo.csv boundary field can exceed default 131072 limit
BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE, 'data')
DBIP_PATH = os.path.join(DATA_DIR, 'dbip_china_records.csv')
PINYIN_PATH = os.path.join(DATA_DIR, 'city_map_pinyin.json')
GEO_PATH = os.path.join(DATA_DIR, 'ok_geo.csv')
OUTPUT_PATH = os.path.join(DATA_DIR, 'city_map_coords.json')
def haversine_km(lat1, lng1, lat2, lng2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)
def main():
    print('=' * 60)
    print('Subagent S4: Coordinate Nearest Matcher')
    print('=' * 60)
    # Load pinyin matcher results to get unmatched names
    if not os.path.exists(PINYIN_PATH):
        print(f'[ERROR] {PINYIN_PATH} not found'); return
    pinyin = load_json(PINYIN_PATH)
    unmatched = {u['name']: u['count'] for u in pinyin.get('unmatched', [])}
    print(f'Unmatched names from pinyin matcher: {len(unmatched)}')
    if not unmatched:
        print('Nothing to match!')
        # Write empty output
        output = {'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                  'message': 'No unmatched names to process', 'matches': [], 'unmatched': []}
        with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        return
    # Load DB-IP coords for unmatched cities
    # dbip_china_records.csv columns: start_ip,end_ip,province,city,lat,lng,country (7 columns)
    dbip_coords = {}  # city_name -> (lat, lng, province)
    with open(DBIP_PATH, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader)
        for row in reader:
            if len(row) >= 7:
                name = row[3].strip()
                if name in unmatched:
                    try:
                        lat = float(row[4])  # column index 4, not 6!
                        lng = float(row[5])  # column index 5, not 7!
                        prov = row[2].strip()  # province is at index 2
                        if name not in dbip_coords:
                            dbip_coords[name] = (lat, lng, prov)
                    except (ValueError, IndexError):
                        pass
    print(f'Cities with DB-IP coordinates: {len(dbip_coords)}')
    # Load ok_geo.csv for city center coordinates (format: id,pid,deep,name,ext_path,geo,boundary)
    # geo field is "lng lat" (space-separated string)
    city_centers = []
    if os.path.exists(GEO_PATH):
        with open(GEO_PATH, 'r', encoding='utf-8') as f:
            # Need to parse csv properly because geo is quoted
            reader = csv.reader(f)
            for row in reader:
                if len(row) >= 6:
                    try:
                        name = row[3].strip()
                        geo = row[5].strip().strip('"').strip()
                        if geo and ' ' in geo:
                            parts = geo.split()
                            lng = float(parts[0])
                            lat = float(parts[1])
                            if name:
                                city_centers.append((name, lat, lng))
                    except (ValueError, IndexError):
                        pass
    print(f'City centers from ok_geo.csv: {len(city_centers)}')
    # For each unmatched city with coords, find nearest city center
    matched = []
    still_unmatched = []
    for name, count in sorted(unmatched.items(), key=lambda x: -x[1]):
        if name in dbip_coords:
            lat, lng, prov = dbip_coords[name]
            # Find nearest city center within 20km
            nearest = None
            nearest_dist = 20.0  # km threshold
            for cn_name, clat, clng in city_centers:
                d = haversine_km(lat, lng, clat, clng)
                if d < nearest_dist:
                    nearest_dist = d
                    nearest = cn_name
            if nearest:
                matched.append({'name': name, 'mapped': nearest, 'method': 'coord_nearest',
                                'distance_km': round(nearest_dist, 2),
                                'confidence': round(max(0.3, 1.0 - nearest_dist / 20.0), 2),
                                'count': count, 'province': prov})
            else:
                still_unmatched.append({'name': name, 'count': count, 'reason': 'no_nearby_city',
                                        'province': prov})
        else:
            still_unmatched.append({'name': name, 'count': count, 'reason': 'no_coords'})
    print(f'\nCoordinate-matched: {len(matched)}')
    print(f'Still unmatched: {len(still_unmatched)}')
    output = {
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'statistics': {
            'input_unmatched': len(unmatched),
            'with_dbip_coords': len(dbip_coords),
            'city_centers': len(city_centers),
            'coord_matched': len(matched),
            'still_unmatched': len(still_unmatched),
        },
        'matches': matched,
        'unmatched': [u for u in still_unmatched if u['reason'] == 'no_coords'],
        'no_nearby_city': [u for u in still_unmatched if u['reason'] == 'no_nearby_city'],
    }
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f'\n[OK] {OUTPUT_PATH}')
    if still_unmatched[:10]:
        print(f'\nFirst 10 still unmatched:')
        for u in still_unmatched[:10]:
            print(f'  {u["name"]} (x{u["count"]}) - {u["reason"]}')
if __name__ == '__main__':
    main()