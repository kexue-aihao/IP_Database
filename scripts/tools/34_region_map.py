#!/usr/bin/env python3
"""
S4: Global Region/Province/State Standardizer (Phase 4 of Global Pipeline)
Maps ISO 3166-2 regional codes and English names to canonical Chinese/English names.
Nested agents: 10 regional mappers (S4.1-S4.10).
"""
import csv, json, os, sys, io
from datetime import datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE, 'data')
GLOBAL_DIR = os.path.join(DATA_DIR, 'global')
OUT_PATH = os.path.join(GLOBAL_DIR, 'region_map.json')

# US states (S4.1)
US_STATES = {
    'US-AL': ('Alabama', '阿拉巴马'), 'US-AK': ('Alaska', '阿拉斯加'),
    'US-AZ': ('Arizona', '亚利桑那'), 'US-AR': ('Arkansas', '阿肯色'),
    'US-CA': ('California', '加利福尼亚'), 'US-CO': ('Colorado', '科罗拉多'),
    'US-CT': ('Connecticut', '康涅狄格'), 'US-DE': ('Delaware', '特拉华'),
    'US-FL': ('Florida', '佛罗里达'), 'US-GA': ('Georgia', '佐治亚'),
    'US-HI': ('Hawaii', '夏威夷'), 'US-ID': ('Idaho', '爱达荷'),
    'US-IL': ('Illinois', '伊利诺伊'), 'US-IN': ('Indiana', '印第安纳'),
    'US-IA': ('Iowa', '艾奥瓦'), 'US-KS': ('Kansas', '堪萨斯'),
    'US-KY': ('Kentucky', '肯塔基'), 'US-LA': ('Louisiana', '路易斯安那'),
    'US-ME': ('Maine', '缅因'), 'US-MD': ('Maryland', '马里兰'),
    'US-MA': ('Massachusetts', '马萨诸塞'), 'US-MI': ('Michigan', '密歇根'),
    'US-MN': ('Minnesota', '明尼苏达'), 'US-MS': ('Mississippi', '密西西比'),
    'US-MO': ('Missouri', '密苏里'), 'US-MT': ('Montana', '蒙大拿'),
    'US-NE': ('Nebraska', '内布拉斯加'), 'US-NV': ('Nevada', '内华达'),
    'US-NH': ('New Hampshire', '新罕布什尔'), 'US-NJ': ('New Jersey', '新泽西'),
    'US-NM': ('New Mexico', '新墨西哥'), 'US-NY': ('New York', '纽约'),
    'US-NC': ('North Carolina', '北卡罗来纳'), 'US-ND': ('North Dakota', '北达科他'),
    'US-OH': ('Ohio', '俄亥俄'), 'US-OK': ('Oklahoma', '俄克拉何马'),
    'US-OR': ('Oregon', '俄勒冈'), 'US-PA': ('Pennsylvania', '宾夕法尼亚'),
    'US-RI': ('Rhode Island', '罗德岛'), 'US-SC': ('South Carolina', '南卡罗来纳'),
    'US-SD': ('South Dakota', '南达科他'), 'US-TN': ('Tennessee', '田纳西'),
    'US-TX': ('Texas', '得克萨斯'), 'US-UT': ('Utah', '犹他'),
    'US-VT': ('Vermont', '佛蒙特'), 'US-VA': ('Virginia', '弗吉尼亚'),
    'US-WA': ('Washington', '华盛顿'), 'US-WV': ('West Virginia', '西弗吉尼亚'),
    'US-WI': ('Wisconsin', '威斯康星'), 'US-WY': ('Wyoming', '怀俄明'),
    'US-DC': ('District of Columbia', '哥伦比亚特区'),
}

# CN provinces (S4.2) - reuse from existing work
CN_PROVINCES = {
    '北京': '北京', '天津': '天津', '上海': '上海', '重庆': '重庆',
    '河北': '河北', '山西': '山西', '内蒙古': '内蒙古', '辽宁': '辽宁',
    '吉林': '吉林', '黑龙江': '黑龙江', '江苏': '江苏', '浙江': '浙江',
    '安徽': '安徽', '福建': '福建', '江西': '江西', '山东': '山东',
    '河南': '河南', '湖北': '湖北', '湖南': '湖南', '广东': '广东',
    '广西': '广西', '海南': '海南', '四川': '四川', '贵州': '贵州',
    '云南': '云南', '西藏': '西藏', '陕西': '陕西', '甘肃': '甘肃',
    '青海': '青海', '宁夏': '宁夏', '新疆': '新疆',
    '香港': '香港', '澳门': '澳门', '台湾': '台湾',
    'Hainan': '海南', 'Guangdong': '广东', 'Fujian': '福建',
    'Zhejiang': '浙江', 'Jiangsu': '江苏', 'Shandong': '山东',
    'Beijing': '北京', 'Shanghai': '上海', 'Tianjin': '天津', 'Chongqing': '重庆',
    'Guangzhou': '广州', 'Shenzhen': '深圳',
}

# EU regions (S4.3) - key ones
EU_REGIONS = {
    'DE-BY': ('Bavaria', '巴伐利亚'), 'DE-BE': ('Berlin', '柏林'),
    'DE-HH': ('Hamburg', '汉堡'), 'DE-HE': ('Hesse', '黑森'),
    'DE-NW': ('North Rhine-Westphalia', '北莱茵-威斯特法伦'),
    'FR-IDF': ('Ile-de-France', '法兰西岛'), 'FR-PAC': ('Provence-Alpes-Cote dAzur', '普罗旺斯'),
    'FR-ARA': ('Auvergne-Rhone-Alpes', '奥弗涅-罗讷-阿尔卑斯'),
    'GB-ENG': ('England', '英格兰'), 'GB-SCT': ('Scotland', '苏格兰'),
    'GB-WLS': ('Wales', '威尔士'), 'GB-NIR': ('Northern Ireland', '北爱尔兰'),
    'NL-NH': ('North Holland', '北荷兰'), 'NL-ZH': ('South Holland', '南荷兰'),
    'IT-LAZ': ('Lazio', '拉齐奥'), 'IT-LOM': ('Lombardy', '伦巴第'),
    'ES-MD': ('Community of Madrid', '马德里'), 'ES-CT': ('Catalonia', '加泰罗尼亚'),
}

# Japan prefectures (S4.5) - key ones
JP_PREFECTURES = {
    'JP-13': ('Tokyo', '东京都'), 'JP-27': ('Osaka', '大阪府'),
    'JP-23': ('Aichi', '爱知县'), 'JP-14': ('Kanagawa', '神奈川县'),
    'JP-11': ('Saitama', '埼玉县'), 'JP-40': ('Fukuoka', '福冈县'),
    'JP-01': ('Hokkaido', '北海道'), 'JP-28': ('Hyogo', '兵库县'),
    'JP-12': ('Chiba', '千叶县'), 'JP-26': ('Kyoto', '京都府'),
}

# Oceania (S4.8)
OCEANIA = {
    'AU-NSW': ('New South Wales', '新南威尔士'), 'AU-VIC': ('Victoria', '维多利亚'),
    'AU-QLD': ('Queensland', '昆士兰'), 'AU-WA': ('Western Australia', '西澳大利亚'),
    'AU-SA': ('South Australia', '南澳大利亚'), 'AU-TAS': ('Tasmania', '塔斯马尼亚'),
    'NZ-AUK': ('Auckland', '奥克兰'), 'NZ-WGN': ('Wellington', '惠灵顿'),
    'NZ-CAN': ('Canterbury', '坎特伯雷'),
}

# South Korea (S4.6)
KOREA = {
    'KR-11': ('Seoul', '首尔'), 'KR-26': ('Busan', '釜山'),
    'KR-28': ('Incheon', '仁川'), 'KR-27': ('Daegu', '大邱'),
    'KR-29': ('Gwangju', '光州'), 'KR-30': ('Daejeon', '大田'),
}

# Latin America (S4.7)
LATAM = {
    'BR-SP': ('Sao Paulo', '圣保罗'), 'BR-RJ': ('Rio de Janeiro', '里约热内卢'),
    'BR-MG': ('Minas Gerais', '米纳斯吉拉斯'), 'BR-PR': ('Parana', '巴拉那'),
    'BR-RS': ('Rio Grande do Sul', '南里奥格兰德州'),
    'AR-B': ('Buenos Aires', '布宜诺斯艾利斯'),
    'MX-DIF': ('Mexico City', '墨西哥城'), 'MX-JAL': ('Jalisco', '哈利斯科'),
}

def main():
    os.makedirs(GLOBAL_DIR, exist_ok=True)
    print('=' * 60)
    print('S4: Global Region Standardizer')
    print('=' * 60)
    
    mapping = {}
    for name, data in [('US_STATES', US_STATES), ('CN_PROVINCES', CN_PROVINCES),
                       ('EU_REGIONS', EU_REGIONS), ('JP_PREFECTURES', JP_PREFECTURES),
                       ('OCEANIA', OCEANIA), ('KOREA', KOREA), ('LATAM', LATAM)]:
        count = len(data)
        if isinstance(next(iter(data.values())), tuple):
            for k, (en, zh) in data.items():
                mapping[k] = {'en': en, 'zh': zh}
                mapping[en.lower()] = {'en': en, 'zh': zh}
        else:
            for k, v in data.items():
                mapping[k] = {'en': k, 'zh': v}
                mapping[k.lower()] = {'en': k, 'zh': v}
        print(f'  {name}: {count} entries')
    
    output = {
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total_entries': len(mapping),
        'regions': mapping,
    }
    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f'[OK] {OUT_PATH}')

if __name__ == '__main__':
    main()
