# -*- coding: utf-8 -*-
"""Resolve merge conflicts: README.md and .gitignore"""

NL = chr(10)
HEAD_MARK = '<<<<<<< HEAD' + NL
EQ_MARK = '=======' + NL
TAIL_MARK = '>>>>>>>'

def resolve_gitignore():
    merged = [
        '# Per-developer config',
        '.claude/',
        '.reasonix/',
        '',
        '# Generated database files',
        'china_ip_db.sqlite',
        'china_ip_db.csv',
        'china_ip_cidrs.txt',
        'china_ipv6_db.sqlite',
        'china_ipv6_db.csv',
        '',
        '# External data sources (download separately)',
        'GeoCN.mmdb',
        'ok_data_level4.csv',
        'ok_geo.csv',
        'ipv4_source.txt',
        '',
        '# Source data directories',
        'data/',
        '',
        '# Generated output',
        'output/',
        '',
        '# Python',
        '__pycache__/',
        '*.pyc',
        '*.pyo',
        'ip2region_py/',
        '',
        '# IDE',
        '.vscode/',
        '.idea/',
        '*.swp',
        '*.swo',
        '',
    ]
    with open('.gitignore', 'w', encoding='utf-8') as f:
        f.write(NL.join(merged))
    print('  .gitignore resolved')

def resolve_readme():
    with open('README.md', 'r', encoding='utf-8') as f:
        content = f.read()
    hs = content.find(HEAD_MARK)
    eq = content.find(EQ_MARK, hs)
    tail_b = content.find(TAIL_MARK, eq)
    tail_e = content.find(NL, tail_b)
    if tail_e < 0:
        tail_e = len(content)
    head_local = content[hs + len(HEAD_MARK):eq]
    remote = content[eq + len(EQ_MARK):tail_b]
    # MMDB appendix from local
    mmdb_section = ''
    for m in ('## 统一字段 Schema', '### MaxMind DB 格式'):
        if m in head_local:
            mmdb_section = head_local[head_local.index(m):]
            break
    if not mmdb_section:
        mmdb_section = head_local
    merged = remote.rstrip() + NL + NL + '---' + NL + NL + mmdb_section.rstrip() + NL
    new_content = content[:hs] + merged + content[tail_e:]
    with open('README.md', 'w', encoding='utf-8') as f:
        f.write(new_content)
    print('  README.md resolved')

resolve_gitignore()
resolve_readme()
print('Done')
