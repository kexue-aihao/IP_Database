#!/usr/bin/env python3
"""Subagent S3: Pinyin Fuzzy Matcher — Phase 6. Matches DB-IP English city names to Chinese using pinyin."""
import json, os, re, sys
from datetime import datetime
BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE, 'data')
CITY_NAMES_PATH = os.path.join(DATA_DIR, 'dbip_city_names.json')
CITY_DICT_PATH = os.path.join(DATA_DIR, 'china_city_dict.json')
OUTPUT_PATH = os.path.join(DATA_DIR, 'city_map_pinyin.json')

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def normalize(name):
    """Normalize city name for matching."""
    n = name.strip().lower()
    n = re.sub(r'[\s()（）,-]+', ' ', n)
    n = n.strip()
    return n

def parse_pinyin_for_city(name):
    """Try to interpret a city name as pinyin text."""
    # Split by space, underscore, parens
    name2 = name.replace('(', ' ').replace(')', ' ').replace('_', ' ').replace('-', ' ')
    parts = [p.strip().lower() for p in re.split(r'[\s,]+', name2) if p.strip()]
    return parts

def main():
    print('=' * 60)
    print('Subagent S3: Pinyin Fuzzy Matcher')
    print('=' * 60)
    # Load inputs
    if not os.path.exists(CITY_NAMES_PATH):
        print(f'[ERROR] {CITY_NAMES_PATH} not found'); return
    if not os.path.exists(CITY_DICT_PATH):
        print(f'[ERROR] {CITY_DICT_PATH} not found'); return
    city_names = load_json(CITY_NAMES_PATH)
    city_dict = load_json(CITY_DICT_PATH)
    en_to_cn = city_dict.get('en_to_cn_mapping', {})
    pinyin_to_cn = city_dict.get('pinyin_to_cn', {})
    pinyin_prefix_to_cn = city_dict.get('pinyin_prefix_to_cn', {})
    prefectures = city_dict.get('prefectures', [])
    districts = city_dict.get('districts', [])
    print(f'Loaded: {len(city_names["all_cities"])} city names, {len(en_to_cn)} EN→CN mappings')
    # Build lookup helpers
    prefecture_names = {p['name'] for p in prefectures}
    district_names = {d['name'] for d in districts}
    all_cn_names = prefecture_names | district_names
    # Build pinyin→name lookup (full pinyin string)
    prefecture_pinyin = {}
    for p in prefectures:
        py = p['pinyin'].strip()
        if py:
            prefecture_pinyin[py] = p['name']
            prefecture_pinyin[py.replace(' ', '')] = p['name']
            # Title case
            prefecture_pinyin[py.title().replace(' ', '')] = p['name']
    district_pinyin = {}
    for d in districts:
        py = d['pinyin'].strip()
        if py:
            district_pinyin[py] = d['name']
            district_pinyin[py.replace(' ', '')] = d['name']
            district_pinyin[py.title().replace(' ', '')] = d['name']
    all_pinyin_lookup = {**prefecture_pinyin, **district_pinyin}
    # Known special mappings (not in standard dict)
    SPECIAL_MAP = {
        'sai kung': '西贡', 'sai kung district': '西贡',
        'tseung kwan o': '将军澳',
        'kwai chung': '葵涌', 'tsuen wan': '荃湾',
        'tuen mun': '屯门', 'yuen long': '元朗',
        'fanling': '粉岭', 'sheung shui': '上水',
        'tai po': '大埔', 'sha tin': '沙田',
        'ma on shan': '马鞍山', 'sham shui po': '深水埗',
        'kowloon city': '九龙城', 'wong tai sin': '黄大仙',
        'kwun tong': '观塘', 'central and western': '中西区',
        'wan chai': '湾仔', 'eastern district': '东区',
        'southern district': '南区',
        'islands district': '离岛区',
        'north district': '北区',
        'taipo': '大埔', 'shatin': '沙田',
        'sai kung town': '西贡市',
        'chek lap kok': '赤鱲角',
        'hong kong international airport': '赤鱲角',
        'discovery bay': '愉景湾',
        'tung chung': '东涌',
    }
    # Match each city name
    all_cities = city_names['all_cities']
    matches = []
    unmatched = []
    ambiguous = []
    for entry in all_cities:
        name = entry['name']
        count = entry['count']
        # 1. Exact lookup in EN→CN mapping
        if name in en_to_cn:
            matches.append({'name': name, 'mapped': en_to_cn[name], 'method': 'direct', 'confidence': 1.0, 'count': count})
            continue
        # 2. Try without parentheses
        base = name.split(' (')[0].strip() if ' (' in name else name
        if base and base != name and base in en_to_cn:
            matches.append({'name': name, 'mapped': en_to_cn[base], 'method': 'base_direct', 'confidence': 0.95, 'count': count})
            continue
        # 3. Try normalized lookup
        norm = normalize(name)
        if norm in en_to_cn:
            matches.append({'name': name, 'mapped': en_to_cn[norm], 'method': 'norm_direct', 'confidence': 0.9, 'count': count})
            continue
        # 4. Try pinyin lookup (full)
        if name.lower() in all_pinyin_lookup:
            matches.append({'name': name, 'mapped': all_pinyin_lookup[name.lower()], 'method': 'pinyin_exact', 'confidence': 0.95, 'count': count})
            continue
        # 5. Try pinyin without spaces
        compact = name.lower().replace(' ', '')
        if compact in all_pinyin_lookup:
            matches.append({'name': name, 'mapped': all_pinyin_lookup[compact], 'method': 'pinyin_compact', 'confidence': 0.9, 'count': count})
            continue
        # 6. Try special names
        if name.lower() in SPECIAL_MAP:
            matches.append({'name': name, 'mapped': SPECIAL_MAP[name.lower()], 'method': 'special', 'confidence': 0.95, 'count': count})
            continue
        # 7. Try base name special
        base_lower = base.lower()
        if base_lower in SPECIAL_MAP:
            matches.append({'name': name, 'mapped': SPECIAL_MAP[base_lower], 'method': 'special_base', 'confidence': 0.9, 'count': count})
            continue
        # 8. Try pinyin prefix matching
        pp = parse_pinyin_for_city(name)
        # Try first word as pinyin prefix
        if pp and pp[0] in pinyin_prefix_to_cn:
            candidates = pinyin_prefix_to_cn[pp[0]]
            # If there's a second word, try to match more precisely
            if len(pp) > 1 and pp[1] in pinyin_to_cn:
                second_candidates = set(pinyin_to_cn[pp[1]])
                common = candidates & second_candidates
                if len(common) == 1:
                    cn = list(common)[0]
                    matches.append({'name': name, 'mapped': cn, 'method': 'pinyin_prefix_pair', 'confidence': 0.85, 'count': count})
                    continue
            # Single word prefix match - only if it's unique
            if len(candidates) == 1:
                cn = list(candidates)[0]
                matches.append({'name': name, 'mapped': cn, 'method': 'pinyin_prefix_unique', 'confidence': 0.7, 'count': count})
                continue
            else:
                ambiguous.append({'name': name, 'candidates': list(candidates), 'method': 'pinyin_prefix_multi'})
        # 9. Try pinyin word-by-word fuzzy matching
        words = parse_pinyin_for_city(name)
        best_match = None
        best_score = 0
        for py, cn_list in pinyin_to_cn.items():
            for cn in cn_list:
                cn_py = cn
                # Check if any word overlaps
                for w in words:
                    if w and len(w) > 1:
                        if w == py[:len(w)] or py.startswith(w):
                            score = len(w) / max(len(py), 1)
                            if score > best_score:
                                best_score = score
                                best_match = cn
        if best_match and best_score > 0.6:
            matches.append({'name': name, 'mapped': best_match, 'method': 'pinyin_prefix_fuzzy', 'confidence': round(best_score * 0.7, 2), 'count': count})
            continue
        # 10. Unmatched
        unmatched.append({'name': name, 'count': count})
    print(f'\nMatched: {len(matches)}')
    print(f'Unmatched: {len(unmatched)}')
    print(f'Ambiguous: {len(ambiguous)}')
    # Aggregate by method
    method_counts = {}
    for m in matches:
        method_counts[m['method']] = method_counts.get(m['method'], 0) + 1
    print(f'\nMethod breakdown:')
    for method, ct in sorted(method_counts.items(), key=lambda x: -x[1]):
        print(f'  {method}: {ct}')
    output = {
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'inputs': {'city_names': 'dbip_city_names.json', 'city_dict': 'china_city_dict.json'},
        'statistics': {
            'total_cities': len(all_cities),
            'matched': len(matches),
            'unmatched': len(unmatched),
            'ambiguous': len(ambiguous),
            'match_rate_pct': round(len(matches) / max(len(all_cities), 1) * 100, 1),
            'method_counts': method_counts,
        },
        'matches': matches,
        'unmatched': unmatched,
        'ambiguous': ambiguous,
    }
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f'\n[OK] {OUTPUT_PATH}')
    print(f'  Match rate: {output["statistics"]["match_rate_pct"]}%')
    # Show some unmatched
    if unmatched:
        print(f'\nFirst 20 unmatched:')
        for u in unmatched[:20]:
            print(f'  {u["name"]} (x{u["count"]})')
if __name__ == '__main__':
    main()