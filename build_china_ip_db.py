#!/usr/bin/env python3
"""
中国全量 IP 数据库构建工具
===========================
从 ip2region 的 ipv4_source.txt 解析出所有中国 IP 段，
输出为 SQLite 数据库和 CSV 文件。

数据来源: https://github.com/lionsoul2014/ip2region
格式: start_ip|end_ip|国家|省份|城市|运营商|0|国家代码

输出:
  - china_ip_db.sqlite    SQLite 数据库
  - china_ip_db.csv        CSV 文件
  - china_ip_cidrs.txt    按省份/城市分组的 CIDR 概览
"""

import csv
import ipaddress
import sqlite3
import os
import sys
from collections import defaultdict

# ============================================================
# 配置
# ============================================================
SOURCE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ipv4_source.txt')
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(OUTPUT_DIR, 'china_ip_db.sqlite')
CSV_FILE = os.path.join(OUTPUT_DIR, 'china_ip_db.csv')
CIDR_FILE = os.path.join(OUTPUT_DIR, 'china_ip_cidrs.txt')

CHINA_KEYWORDS = ['中国', 'China']

# 运营商简写映射
ISP_SHORT_MAP = {
    '中国电信': '电信',
    '中国移动': '移动',
    '中国联通': '联通',
    '中国教育网': '教育网',
    '中国铁通': '铁通',
    '中国长城': '长城',
    '中国科技网': '科技网',
}


def ip_to_int(ip_str: str) -> int:
    """将 IP 字符串转为整数"""
    return int(ipaddress.IPv4Address(ip_str))


def int_to_ip(ip_int: int) -> str:
    """将整数转为 IP 字符串"""
    return str(ipaddress.IPv4Address(ip_int))


def ip_range_to_cidrs(start_ip: str, end_ip: str):
    """将 IP 范围转为 CIDR 列表（尽量合并）"""
    try:
        start = ipaddress.IPv4Address(start_ip)
        end = ipaddress.IPv4Address(end_ip)
        return [str(net) for net in ipaddress.summarize_address_range(start, end)]
    except (ValueError, TypeError):
        return []


def parse_line(line: str):
    """解析单行，返回结构化数据或 None"""
    line = line.strip()
    if not line or line.startswith('#'):
        return None

    parts = line.split('|')
    if len(parts) < 7:
        return None

    start_ip, end_ip, country, province, city, isp = parts[0], parts[1], parts[2], parts[3], parts[4], parts[5]

    # 只保留中国 IP
    is_china = False
    for kw in CHINA_KEYWORDS:
        if kw in country:
            is_china = True
            break
    if not is_china:
        return None

    # 处理空值
    province = province.strip() if province and province != '0' else ''
    city = city.strip() if city and city != '0' else ''
    isp = isp.strip() if isp and isp != '0' else ''

    # 运营商简称
    isp_short = ISP_SHORT_MAP.get(isp, isp)

    try:
        start_int = ip_to_int(start_ip)
        end_int = ip_to_int(end_ip)
    except ValueError:
        return None

    return {
        'start_ip': start_ip,
        'end_ip': end_ip,
        'start_ip_int': start_int,
        'end_ip_int': end_int,
        'country': '中国',
        'province': province,
        'city': city,
        'isp': isp,
        'isp_short': isp_short,
    }


def build_database():
    """主函数：构建数据库"""
    print('=' * 60)
    print('  中国全量 IP 数据库构建工具')
    print('=' * 60)

    # 检查源文件
    if not os.path.exists(SOURCE_FILE):
        print(f'[错误] 源文件不存在: {SOURCE_FILE}')
        print('请先下载: curl -sL "https://raw.githubusercontent.com/lionsoul2014/ip2region/'
              'master/data/ipv4_source.txt" -o ipv4_source.txt')
        sys.exit(1)

    file_size = os.path.getsize(SOURCE_FILE)
    print(f'\n[1/4] 读取源文件: {SOURCE_FILE} ({file_size / 1024 / 1024:.1f} MB)')
    print(f'      预计中国 IP 条目: ~65000')

    # 解析数据
    print(f'\n[2/4] 解析中国 IP 段...')
    records = []
    parse_errors = 0
    total_lines = 0

    with open(SOURCE_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            total_lines += 1
            record = parse_line(line)
            if record:
                records.append(record)
            elif '|中国|' in line or '|China|' in line:
                parse_errors += 1

    print(f'      总行数: {total_lines}')
    print(f'      中国 IP 段: {len(records)}')
    if parse_errors:
        print(f'      解析失败: {parse_errors}')

    # 统计信息
    provinces = set(r['province'] for r in records if r['province'])
    cities = set(r['city'] for r in records if r['city'])
    isps = set(r['isp'] for r in records if r['isp'])

    print(f'      覆盖省份: {len(provinces)}')
    print(f'      覆盖城市: {len(cities)}')
    print(f'      覆盖运营商: {len(isps)}')

    # 写入 SQLite
    print(f'\n[3/4] 写入 SQLite 数据库...')
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    cur.execute('''
        CREATE TABLE IF NOT EXISTS china_ip (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_ip TEXT NOT NULL,
            end_ip TEXT NOT NULL,
            start_ip_int INTEGER NOT NULL,
            end_ip_int INTEGER NOT NULL,
            country TEXT DEFAULT '中国',
            province TEXT DEFAULT '',
            city TEXT DEFAULT '',
            isp TEXT DEFAULT '',
            isp_short TEXT DEFAULT ''
        )
    ''')

    # 创建索引以加速查询
    cur.execute('CREATE INDEX IF NOT EXISTS idx_start_ip_int ON china_ip(start_ip_int)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_end_ip_int ON china_ip(end_ip_int)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_province ON china_ip(province)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_city ON china_ip(city)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_isp ON china_ip(isp)')

    # 批量插入 (每次 1000 条)
    batch_size = 1000
    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]
        cur.executemany('''
            INSERT INTO china_ip (start_ip, end_ip, start_ip_int, end_ip_int,
                                  country, province, city, isp, isp_short)
            VALUES (:start_ip, :end_ip, :start_ip_int, :end_ip_int,
                    :country, :province, :city, :isp, :isp_short)
        ''', batch)

    conn.commit()

    # 数据库元信息
    cur.execute('''
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    cur.executemany('INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)', [
        ('version', '1.0'),
        ('source', 'ip2region (lionsoul2014/ip2region)'),
        ('ipv4_entries', str(len(records))),
        ('provinces', str(len(provinces))),
        ('cities', str(len(cities))),
        ('isps', str(len(isps))),
        ('generated_at', __import__('datetime').datetime.now().isoformat()),
        ('description', '中国全量 IPv4 归属地数据库 (省/市/运营商级别)'),
    ])
    conn.commit()

    # 查询验证
    cur.execute('SELECT COUNT(*) FROM china_ip')
    db_count = cur.fetchone()[0]
    conn.close()
    print(f'      写入完成: {db_count} 条记录')
    db_size = os.path.getsize(DB_FILE)
    print(f'      数据库大小: {db_size / 1024:.1f} KB')

    # 写入 CSV
    print(f'\n[4/4] 写入 CSV 文件...')
    fieldnames = ['start_ip', 'end_ip', 'start_ip_int', 'end_ip_int',
                  'country', 'province', 'city', 'isp', 'isp_short']

    with open(CSV_FILE, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow({k: record.get(k, '') for k in fieldnames})

    csv_size = os.path.getsize(CSV_FILE)
    print(f'      写入完成: {len(records)} 条记录')
    print(f'      CSV 大小: {csv_size / 1024 / 1024:.1f} MB')

    # ============================================================
    # 生成 CIDR 概览 (按省份分组)
    # ============================================================
    print(f'\n[可选] 生成 CIDR 概览...')

    # 按省分组统计
    province_stats = defaultdict(lambda: {'count': 0, 'cities': set(), 'isps': set(), 'min_ip': '255.255.255.255', 'max_ip': '0.0.0.0'})
    for r in records:
        p = r['province'] or '未知'
        province_stats[p]['count'] += 1
        if r['city']:
            province_stats[p]['cities'].add(r['city'])
        if r['isp']:
            province_stats[p]['isps'].add(r['isp_short'])
        if r['start_ip_int'] < ip_to_int(province_stats[p]['min_ip']):
            province_stats[p]['min_ip'] = r['start_ip']
        if r['end_ip_int'] > ip_to_int(province_stats[p]['max_ip']):
            province_stats[p]['max_ip'] = r['end_ip']

    with open(CIDR_FILE, 'w', encoding='utf-8') as f:
        f.write('中国全量 IP 段概览 (按省份分组)\n')
        f.write('=' * 70 + '\n')
        f.write(f'总 IP 段数: {len(records)}\n')
        f.write(f'覆盖省份: {len(provinces)}\n')
        f.write(f'覆盖城市: {len(cities)}\n')
        f.write(f'覆盖运营商: {len(isps)}\n')
        f.write(f'生成时间: {__import__("datetime").datetime.now().isoformat()}\n')
        f.write('=' * 70 + '\n\n')

        for prov in sorted(province_stats.keys()):
            s = province_stats[prov]
            f.write(f'【{prov}】\n')
            f.write(f'   IP 段数: {s["count"]}\n')
            f.write(f'   城市数: {len(s["cities"])}\n')
            if s['cities']:
                cities_list = ', '.join(sorted(s['cities'])[:10])
                if len(s['cities']) > 10:
                    cities_list += f' ... 等{len(s["cities"])}个城市'
                f.write(f'   城市: {cities_list}\n')
            f.write(f'   运营商: {", ".join(s["isps"]) if s["isps"] else "未知"}\n')
            f.write(f'   范围: {s["min_ip"]} ~ {s["max_ip"]}\n')
            f.write('\n')

    print(f'      CIDR 概览已生成: {CIDR_FILE}')

    # ============================================================
    # 打印使用说明
    # ============================================================
    print()
    print('=' * 60)
    print('  ✅ 数据库构建完成！')
    print('=' * 60)
    print(f'  SQLite: {DB_FILE} ({db_size / 1024:.1f} KB)')
    print(f'  CSV:    {CSV_FILE} ({csv_size / 1024 / 1024:.1f} MB)')
    print(f'  概览:   {CIDR_FILE}')
    print()
    print('  使用示例:')
    print()
    print('  -- Python 查询 SQLite:')
    print('  import sqlite3')
    print('  conn = sqlite3.connect("china_ip_db.sqlite")')
    print('  cur = conn.cursor()')
    print('  # 查询指定 IP 的归属地')
    print('  ip_int = int(ipaddress.IPv4Address("1.2.4.0"))')
    print("  cur.execute('''")
    print('      SELECT province, city, isp FROM china_ip')
    print('      WHERE start_ip_int <= ? AND end_ip_int >= ?')
    print("  ''', (ip_int, ip_int))")
    print('  print(cur.fetchone())')
    print()
    print('  -- 查询某个省份的所有 IP 段:')
    print("  cur.execute('SELECT COUNT(*) FROM china_ip WHERE province = ?', ('广东省',))")
    print('  print(cur.fetchone())')
    print('=' * 60)


if __name__ == '__main__':
    build_database()
