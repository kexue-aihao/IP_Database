#!/usr/bin/env python3
"""Subagent S2: City Dictionary Builder — Phase 6. Builds comprehensive EN→CN city dict from AreaCity data."""
import csv, json, os, re
from datetime import datetime
BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE, 'data')
L3_PATH = os.path.join(DATA_DIR, 'ok_data_level3.csv')
L4_PATH = os.path.join(DATA_DIR, 'ok_data_level4.csv')
OUTPUT_PATH = os.path.join(DATA_DIR, 'china_city_dict.json')
# Known English aliases for Chinese cities
EN_ALIASES = {
    'Beijing': '北京', 'Peking': '北京',
    'Shanghai': '上海', 'Shanghai Shi': '上海',
    'Tianjin': '天津', 'Tientsin': '天津',
    'Chongqing': '重庆', 'Chungking': '重庆',
    'Guangzhou': '广州', 'Canton': '广州',
    'Shenzhen': '深圳', 'Shumchun': '深圳',
    'Hangzhou': '杭州', 'Hangchow': '杭州',
    'Nanjing': '南京', 'Nanking': '南京',
    'Wuhan': '武汉', 'Chengdu': '成都',
    "Xi'an": '西安', 'Sian': '西安', 'Xian': '西安',
    'Fuzhou': '福州', 'Foochow': '福州',
    'Xiamen': '厦门', 'Amoy': '厦门',
    'Jinan': '济南', 'Tsinan': '济南',
    'Qingdao': '青岛', 'Tsingtao': '青岛',
    'Shenyang': '沈阳', 'Mukden': '沈阳',
    'Changsha': '长沙', 'Hefei': '合肥',
    'Zhengzhou': '郑州', 'Shijiazhuang': '石家庄',
    'Harbin': '哈尔滨', 'Changchun': '长春',
    'Taiyuan': '太原', 'Nanchang': '南昌',
    'Nanning': '南宁', 'Kunming': '昆明',
    'Guiyang': '贵阳', 'Lanzhou': '兰州',
    'Hohhot': '呼和浩特', 'Huhehaote': '呼和浩特',
    'Urumqi': '乌鲁木齐', 'Urumchi': '乌鲁木齐',
    'Yinchuan': '银川', 'Xining': '西宁',
    'Lhasa': '拉萨', 'Haikou': '海口',
    'Ningbo': '宁波', 'Ningpo': '宁波',
    'Dalian': '大连', 'Dairen': '大连',
    'Wuxi': '无锡', 'Wuhsi': '无锡',
    'Suzhou': '苏州', 'Soochow': '苏州',
    'Foshan': '佛山', 'Dongguan': '东莞',
    'Zhuhai': '珠海', 'Zhongshan': '中山',
    'Wenzhou': '温州', 'Wenchow': '温州',
    'Changzhou': '常州', 'Nantong': '南通',
    'Xuzhou': '徐州', 'Yantai': '烟台',
    'Weifang': '潍坊', 'Zibo': '淄博',
    'Linyi': '临沂', 'Tangshan': '唐山',
    'Handan': '邯郸', 'Baoding': '保定',
    'Luoyang': '洛阳', 'Nanyang': '南阳',
    'Guilin': '桂林', 'Liuzhou': '柳州',
    'Sanya': '三亚', 'Huangshan': '黄山',
    'Macau': '澳门', 'Macao': '澳门',
    'Hong Kong': '香港', 'Hongkong': '香港',
    'Kowloon': '九龙', 'Kwun Tong': '观塘',
    'Taipei': '台北', 'Kaohsiung': '高雄',
    'Taichung': '台中', 'Tainan': '台南',
    'Taoyuan': '桃园', 'Hsinchu': '新竹',
    'Keelung': '基隆', 'Chiayi': '嘉义',
    'New Taipei': '新北', 'New Taipei City': '新北',
    'Wenquan': '福州',  # Wenquan is a district in Fuzhou, Fujian
}
# ISO 3166-2 CN province codes
CN_REGION_CODES = {
    'CN-11': '北京', 'CN-12': '天津', 'CN-13': '河北', 'CN-14': '山西',
    'CN-15': '内蒙古', 'CN-21': '辽宁', 'CN-22': '吉林', 'CN-23': '黑龙江',
    'CN-31': '上海', 'CN-32': '江苏', 'CN-33': '浙江', 'CN-34': '安徽',
    'CN-35': '福建', 'CN-36': '江西', 'CN-37': '山东', 'CN-41': '河南',
    'CN-42': '湖北', 'CN-43': '湖南', 'CN-44': '广东', 'CN-45': '广西',
    'CN-46': '海南', 'CN-50': '重庆', 'CN-51': '四川', 'CN-52': '贵州',
    'CN-53': '云南', 'CN-54': '西藏', 'CN-61': '陕西', 'CN-62': '甘肃',
    'CN-63': '青海', 'CN-64': '宁夏', 'CN-65': '新疆',
    'CN-71': '台湾', 'CN-91': '香港', 'CN-92': '澳门',
}
def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    print('=' * 60)
    print('Subagent S2: City Dictionary Builder')
    print('=' * 60)
    # Parse level3 (prefecture-level + above)
    level3 = []
    level3_pinyin = {}
    with open(L3_PATH, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader)
        for row in reader:
            if len(row) >= 7:
                item = {'id': row[0], 'pid': row[1], 'deep': int(row[2]), 'name': row[3],
                        'pinyin_prefix': row[4], 'pinyin': row[5], 'ext_id': row[6], 'ext_name': row[7]}
                level3.append(item)
                # Index by pinyin
                pinyin = row[5].strip()
                if pinyin:
                    parts = pinyin.split()
                    for p in parts:
                        level3_pinyin.setdefault(p, []).append(item)
                    level3_pinyin[pinyin] = level3_pinyin.get(pinyin, []) + [item]
    print(f'L3 entries: {len(level3)}')
    # Parse level4 (street-level, full detail)
    level4 = []
    with open(L4_PATH, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader)
        for row in reader:
            if len(row) >= 7:
                item = {'id': row[0], 'pid': row[1], 'deep': int(row[2]), 'name': row[3],
                        'pinyin_prefix': row[4], 'pinyin': row[5], 'ext_id': row[6], 'ext_name': row[7]}
                level4.append(item)
    print(f'L4 entries: {len(level4)}')
    # Build per-province/nested structure
    # Deep 0: country, Deep 1: province, Deep 2: prefecture/city, Deep 3: district/county
    provinces = [x for x in level3 if x['deep'] == 0 and x['ext_id'] != '110000000000']
    prefectures = [x for x in level3 if x['deep'] == 2]
    districts = [x for x in level4 if x['deep'] == 3]
    print(f'Provinces: {len(provinces)}, Prefectures: {len(prefectures)}, Districts: {len(districts)}')
    # Build English name → Chinese name mapping
    mapping = {}
    # 1. English aliases
    mapping.update(EN_ALIASES)
    # 2. Pinyin-based: prefecture and district names
    for item in prefectures + districts:
        cn_name = item['name']
        pinyin = item['pinyin'].strip()
        pinyin_prefix = item['pinyin_prefix'].strip()
        # Add pinyin (e.g. "bei jing" → "Beijing")
        if pinyin:
            # Title case pinyin
            title_py = pinyin.title().replace(' ', '')
            if title_py not in mapping:
                mapping[title_py] = cn_name
            # Also try compressing without spaces
            compressed = pinyin.replace(' ', '')
            if compressed not in mapping and compressed != title_py.lower():
                pass
            # spaced version
            if pinyin not in mapping:
                mapping[pinyin] = cn_name
        # Add pinyin prefix (first letter of each syllable)
        if pinyin_prefix:
            mapping[pinyin_prefix] = cn_name
    # 3. Add ext_name (region codes only)
    for item in prefectures:
        if item['ext_name']:
            mapping[item['ext_name']] = item['name']
    # 4. Add ISO 3166-2 codes
    mapping.update(CN_REGION_CODES)
    # 5. Build pinyin index for fuzzy matching
    pinyin_index = {}
    for item in prefectures + districts:
        pinyin = item['pinyin'].strip()
        if pinyin:
            for word in pinyin.split():
                pinyin_index.setdefault(word, set()).add(item['name'])
    # Also index by pinyin prefix letter
    pinyin_prefix_index = {}
    for item in prefectures + districts:
        pp = item['pinyin_prefix'].strip()
        if pp:
            pinyin_prefix_index.setdefault(pp, set()).add(item['name'])
    output = {
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'sources': {'level3': L3_PATH, 'level4': L4_PATH},
        'statistics': {
            'provinces': len(provinces), 'prefectures': len(prefectures),
            'districts': len(districts), 'en_aliases': len(EN_ALIASES),
            'total_mapping_entries': len(mapping),
            'pinyin_index_words': len(pinyin_index),
            'pinyin_prefix_entries': len(pinyin_prefix_index),
        },
        'en_to_cn_mapping': {k: v for k, v in sorted(mapping.items())},
        'pinyin_to_cn': {k: sorted(v) for k, v in sorted(pinyin_index.items())},
        'pinyin_prefix_to_cn': {k: sorted(v) for k, v in sorted(pinyin_prefix_index.items())},
        'cn_region_codes': CN_REGION_CODES,
        'prefectures': [{'name': x['name'], 'pinyin': x['pinyin'], 'pinyin_prefix': x['pinyin_prefix'],
                         'ext_name': x['ext_name'], 'ext_id': x['ext_id']} for x in prefectures],
        'districts': [{'name': x['name'], 'pinyin': x['pinyin'], 'pinyin_prefix': x['pinyin_prefix'],
                       'ext_id': x['ext_id']} for x in districts],
    }
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f'\n[OK] {OUTPUT_PATH}')
    print(f'  EN→CN mapping entries: {len(mapping)}')
    print(f'  Pinyin index words: {len(pinyin_index)}')
    print(f'  Pinyin prefix entries: {len(pinyin_prefix_index)}')
if __name__ == '__main__':
    main()