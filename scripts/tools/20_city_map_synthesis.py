#!/usr/bin/env python3
"""Subagent S5: City Map Synthesis QA — Phase 6. Merges pinyin+coord matches, resolves conflicts, outputs final map.
V2: drops low-quality pinyin_prefix_fuzzy matches, expanded manual overrides for HK/TW/mainland cities."""
import json, os, re
from collections import Counter
from datetime import datetime
BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE, 'data')
PINYIN_PATH = os.path.join(DATA_DIR, 'city_map_pinyin.json')
COORD_PATH = os.path.join(DATA_DIR, 'city_map_coords.json')
DICT_PATH = os.path.join(DATA_DIR, 'china_city_dict.json')
OUTPUT_PATH = os.path.join(DATA_DIR, 'city_map_final.json')
# Methods to DROP from pinyin matching (known to produce bad results)
DROP_METHODS = {'pinyin_prefix_fuzzy', 'pinyin_prefix_pair', 'pinyin_prefix_unique'}
MANUAL_OVERRIDES = {
    'Wenquan': '福州',
    'Central': '香港',
    'Wan Chai': '湾仔区', 'Wanchai': '湾仔区',
    'Yau Tsim Mong': '油尖旺区',
    'Sha Tin': '沙田区', 'Shatin': '沙田区', 'Sha Tin District': '沙田区',
    'Sai Kung': '西贡区', 'Sai Kung District': '西贡区',
    'Tsuen Wan': '荃湾区', 'Tsuen Wan District': '荃湾区',
    'Tuen Mun': '屯门区', 'Yuen Long': '元朗区',
    'Tai Po': '大埔区', 'Tai Po District': '大埔区',
    'North District': '北区', 'Northern District': '北区',
    'Islands District': '离岛区', 'Kwai Tsing': '葵青区',
    'Southern District': '南区', 'Eastern District': '东区',
    'Kowloon City': '九龙城区', 'Wong Tai Sin': '黄大仙区',
    'Sham Shui Po': '深水埗区', 'Kwun Tong': '观塘区', 'Kwun Tong District': '观塘区',
    'Mong Kok': '旺角', 'Mongkok': '旺角',
    'Quarry Bay': '鲗鱼涌', 'Kowloon Bay': '九龙湾',
    'Causeway Bay': '铜锣湾', 'Tsim Sha Tsui': '尖沙咀',
    'Jordan': '佐敦', 'Jordan Road': '佐敦',
    'Yau Ma Tei': '油麻地', 'Sheung Wan': '上环',
    'Sai Wan Ho': '西湾河', 'North Point': '北角', 'North Point District': '北角',
    'Happy Valley': '跑马地', 'Kennedy Town': '坚尼地城',
    'Sai Ying Pun': '西营盘', 'Admiralty': '金钟',
    'Chai Wan': '柴湾', 'Tsing Yi': '青衣',
    'Kwai Chung': '葵涌', 'Fo Tan': '火炭',
    'Tai Wo': '太和', 'Ping Shan': '屏山',
    'Tai Ping Shan': '太平山', 'Cheung Sha Wan': '长沙湾',
    'Lai Chi Kok': '荔枝角', 'Mei Foo': '美孚',
    'Hung Hom': '红磡', 'To Kwa Wan': '土瓜湾',
    'Ngau Tau Kok': '牛头角', 'Lam Tin': '蓝田',
    'Yau Tong': '油塘', 'Tai Kok Tsui': '大角咀',
    'Chek Lap Kok': '赤鱲角', 'Tung Chung': '东涌',
    'Discovery Bay': '愉景湾', 'Aberdeen': '香港仔',
    'Ap Lei Chau': '鸭脷洲', 'Stanley': '赤柱',
    'Repulse Bay': '浅水湾', 'Shek O': '石澳',
    'Sai Kung Town': '西贡市', 'Ma On Shan': '马鞍山',
    'Fanling': '粉岭', 'Sheung Shui': '上水',
    'Kam Tin': '锦田', 'Tin Shui Wai': '天水围',
    'Shau Kei Wan': '筲箕湾', 'Taikoo': '太古',
    'Fortress Hill': '炮台山', 'Tin Hau': '天后',
    'Sai Wan': '西环', 'Mui Wo': '梅窝',
    'Peng Chau': '坪洲', 'Cheung Chau': '长洲',
    'Lamma Island': '南丫岛', 'Lantau Island': '大屿山',
    'Hong Kong Island': '香港', 'New Territories': '新界',
    'Kowloon': '九龙', 'Tseung Kwan O': '将军澳',
    'Neihu District': '内湖区', 'Neihu': '内湖区',
    'Banqiao District': '板桥区', 'Banqiao': '板桥区',
    'Yingge District': '莺歌区', 'Xindian District': '新店区', 'Xindian': '新店区',
    'Shulin District': '树林区', 'Yongkang District': '永康区',
    'Fongshan District': '凤山区', 'Xizhi District': '汐止区',
    'Hualien City': '花莲市', 'Hualien': '花莲',
    'Kaohsiung City': '高雄市', 'Kaohsiung': '高雄',
    'Chiayi City': '嘉义市', 'Chiayi': '嘉义',
    'Pingtung City': '屏东市', 'Pingtung': '屏东',
    'Changhua': '彰化', 'Changhua City': '彰化市',
    'Tainan City': '台南市', 'Taichung City': '台中市',
    'Taipei City': '台北市', 'New Taipei': '新北',
    'Keelung City': '基隆市', 'Hsinchu City': '新竹市',
    'Taitung City': '台东市', 'Yilan City': '宜兰市',
    'Miaoli City': '苗栗市', 'Yunlin County': '云林县',
    'Nantou City': '南投市', 'Hsinchu County': '新竹县',
    'Taiwan': '台湾', 'Kinmen': '金门', 'Matsu': '马祖',
    'Penghu': '澎湖', 'Zhubei': '竹北',
    'Jinrongjie (Xicheng District)': '金融街', 'Jinrongjie': '金融街',
    'Chaowai (Chaoyang)': '朝外', 'Chaowai': '朝外',
    'Pudong (Pudong Xinqu)': '浦东新区', 'Pudong': '浦东新区',
    'Yangpu (Pudong Xinqu)': '杨浦', 'Jingshan (Dongcheng District)': '景山',
    'Zhangzhou (Neimeng)': '漳州', 'Xiabancheng (South Building)': '下板城',
    'Neili': '内里', 'Tuniugou': '土牛沟',
    'Anren Chengguanzhen': '安仁城关镇', 'Haidian (Haidian Qu)': '海淀区',
    'Haidian': '海淀区', 'Wanghailou (Hebei Qu)': '望海楼',
    'Fuzhou (Gulou Qu)': '鼓楼区', 'Dongcheng': '东城', 'Xicheng': '西城',
    'San Po Kong': '新蒲岗', 'Chai Wan Kok': '柴湾角',
    'Kau Wa Keng': '九华径', 'Tsing Yi Town': '青衣镇',
    'Tuen Mun San Hui': '屯门新墟', 'Tai Wo Hau': '大窝口',
    'Ha Kwai Chung': '下葵涌', 'Hang Hau': '坑口',
    'Shek Lei': '石篱', 'Sau Mau Ping': '秀茂坪',
    'Tai Yuen Estate': '太源邨', 'Sha Tin Wai': '沙田围',
    'Yuen Long Kau Hui': '元朗旧墟', 'Tiu Keng Leng': '调景岭',
    'Pok Fu Lam': '薄扶林', 'Ho Man Tin': '何文田',
    'Shek Kip Mei': '石硤尾', 'Lau Fau Shan': '流浮山',
    'Tai Wai': '大围', 'Tai Shui Hang': '大水坑',
    'San Tin': '新田', 'Siu Sai Wan': '小西湾',
    'So Kwun Wat': '扫管笏', 'Ha Tsuen': '厦村',
    'Yu Chui': '愉翠', 'Wo Che': '禾輋',
    'Lek Yuen': '沥源', 'Sui Wo Court': '穗禾苑',
    'Kowloon Tong': '九龙塘', 'Diamond Hill': '钻石山',
    'Lok Fu': '乐富', 'Choi Hung': '彩虹',
    'Ngau Chi Wan': '牛池湾', 'Tsz Wan Shan': '慈云山',
    'Chuk Yuen': '竹园', 'Lei Yue Mun': '鲤鱼门',
    'Cha Kwo Ling': '茶果岭', 'Heng Fa Chuen': '杏花邨',
    'Deep Water Bay': '深水湾', 'Big Wave Bay': '大浪湾',
    'Bade District': '八德区', 'Toufen Township': '头份市',
    'Xinying District': '新营区', 'Wufeng District': '五峰区',
    'Taitung': '台东', 'Shimen District': '石门区',
    'Jiufen': '九份',
    'Hongkou (Hongkou Qu)': '虹口区', 'Xuhui (Xuhui Qu)': '徐汇区',
    'Changning (Changning Qu)': '长宁区', 'Fengtai (Fengtai Qu)': '丰台区',
    'Yangpu (Yangpu Qu)': '杨浦区', 'Nanchangshi (Qingshanhu Qu)': '南昌市',
    'Dawangzhuang (Hedong Qu)': '大王庄', 'Huaqingbei (Futian Qu)': '华强北',
    'Hechi (Inner Mongolia)': '河池', 'Shaoxing (Yuecheng Qu)': '绍兴',
    'Pengpu (Baoshan Qu)': '彭浦', 'Yuehai Residential (Nanshan Qu)': '粤海',
    'Keji yuan (Nanshan Qu)': '科技园', 'Wushipai (Nanshan Qu)': '屋士排',
    'Lishui (Liandu Qu)': '丽水', 'Nanchong (Shunqing Qu)': '南充',
    'Shangli (Liu Yang Shi)': '上栗', 'Qianshan (Xiangzhou Qu)': '前山',
    'Zhongxing New Village': '中兴新村', 'Wangdingdi (Xiqing Qu)': '王顶堤',
    'Hankou (Hongshan Qu)': '汉口', 'Changhongjie (Nankai Qu)': '长虹街',
    'Chaowai (Chaoyang Qu)': '朝外', 'Hongkou (Hongkou Qu)': '虹口区',
    'Kam Ying': '锦英',
}
def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)
def main():
    print('=' * 60)
    print('Subagent S5: City Map Synthesis QA (V2)')
    print('=' * 60)
    if not os.path.exists(PINYIN_PATH):
        print(f'[ERROR] {PINYIN_PATH} not found'); return
    pinyin = load_json(PINYIN_PATH)
    coord = {}
    if os.path.exists(COORD_PATH):
        coord = load_json(COORD_PATH)
    # Merge pinyin matches - DROP bad methods
    merged = {}
    dropped = 0
    for m in pinyin.get('matches', []):
        method = m['method']
        if method in DROP_METHODS:
            dropped += 1
            continue
        name = m['name']
        merged[name] = {
            'name': name, 'mapped': m['mapped'], 'method': method,
            'confidence': m['confidence'], 'count': m['count'],
        }
    print(f'Dropped low-quality pinyin matches: {dropped}')
    # Coord matches fill in gaps (only if not already mapped by a good method)
    coord_added = 0
    for m in coord.get('matches', []):
        name = m['name']
        if name not in merged:
            merged[name] = {
                'name': name, 'mapped': m['mapped'], 'method': 'coord:' + m['method'],
                'confidence': m['confidence'], 'count': m['count'],
            }
            coord_added += 1
    print(f'Coord matches added: {coord_added}')
    # Load all city names for coverage stats (needed before manual override loop)
    city_names_file = os.path.join(DATA_DIR, 'dbip_city_names.json')
    all_names = []
    city_names_data = {'all_cities': []}
    if os.path.exists(city_names_file):
        city_names_data = load_json(city_names_file)
        all_names = [c['name'] for c in city_names_data['all_cities']]
    # Apply manual overrides (highest authority - overrides everything AND adds unmapped names)
    manual_applied = 0
    manual_added = 0
    for name, cn in MANUAL_OVERRIDES.items():
        if name in merged:
            merged[name]['mapped'] = cn
            merged[name]['method'] = 'manual_override'
            merged[name]['confidence'] = 1.0
            manual_applied += 1
        else:
            # Add the name directly - these are known-correct mappings
            # Get count from dbip city names if available
            count = 0
            for entry in city_names_data.get('all_cities', []):
                if entry['name'] == name:
                    count = entry['count']
                    break
            merged[name] = {
                'name': name, 'mapped': cn, 'method': 'manual_override',
                'confidence': 1.0, 'count': count,
            }
            manual_added += 1
    print(f'Manual overrides applied: {manual_applied}, added: {manual_added}')
    mapped_names = set(merged.keys())
    unmapped = [n for n in all_names if n not in mapped_names]
    print(f'Total DB-IP cities: {len(all_names)}')
    print(f'Mapped: {len(mapped_names)}')
    print(f'Unmapped: {len(unmapped)}')
    conf_counts = Counter()
    method_counts = Counter()
    for name, v in merged.items():
        c = v['confidence']
        if c >= 0.9: conf_counts['high (0.9+)'] += 1
        elif c >= 0.7: conf_counts['medium (0.7-0.9)'] += 1
        elif c >= 0.5: conf_counts['low (0.5-0.7)'] += 1
        else: conf_counts['very_low (<0.5)'] += 1
        method_counts[v['method']] += 1
    print(f'\nConfidence distribution: {dict(conf_counts)}')
    print(f'Method distribution: {dict(method_counts)}')
    final = {
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'statistics': {
            'total_cities': len(all_names),
            'mapped': len(mapped_names),
            'unmapped': len(unmapped),
            'coverage_pct': round(len(mapped_names) / max(len(all_names), 1) * 100, 2),
            'confidence': dict(conf_counts),
            'methods': dict(method_counts),
            'dropped_pinyin_fuzzy': dropped,
            'coord_added': coord_added,
            'manual_applied': manual_applied,
        },
        'mapping': {k: v['mapped'] for k, v in sorted(merged.items())},
        'mapping_detail': [v for v in merged.values()],
        'unmapped_names': unmapped,
    }
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(final, f, ensure_ascii=False, indent=2)
    print(f'\n[OK] {OUTPUT_PATH}')
    print(f'  Coverage: {final["statistics"]["coverage_pct"]}%')
    print(f'  High confidence: {conf_counts.get("high (0.9+)", 0)}')
    if unmapped[:15]:
        print(f'\nSample unmapped (first 15):')
        for n in unmapped[:15]:
            print(f'  {n}')
if __name__ == '__main__':
    main()


