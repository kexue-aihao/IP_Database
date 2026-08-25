# -*- coding: utf-8 -*-
import io

with open('README.md', 'r', encoding='utf-8') as f:
    lines = f.readlines()

head_start = None
eq_idx = None
tail_idx = None
for i, ln in enumerate(lines):
    if ln.strip() == '<<<<<<< HEAD':
        head_start = i
    elif ln.strip() == '=======':
        eq_idx = i
    elif '>>>>>>>' in ln:
        tail_idx = i

print('markers:', head_start, eq_idx, tail_idx, 'total:', len(lines))

head_body = lines[head_start+1:eq_idx]
local_body = lines[eq_idx+1:tail_idx]
local_text = ''.join(local_body)

marker = '## 统一字段 Schema'
if marker in local_text:
    mmdb_section = local_text[local_text.index(marker):]
else:
    mmdb_section = local_text

NL = chr(10)
merged = ''.join(head_body).rstrip() + NL + NL + '---' + NL + NL + mmdb_section.rstrip() + NL

with open('README.md', 'w', encoding='utf-8') as f:
    f.write(merged)

print('Merged README written:', merged.count(NL), 'lines')
