import ast
import re
import os
import sys
import ipaddress

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONST_PATH = os.path.join(BASE, 'scripts', 'common', 'constants.py')

with open(CONST_PATH, 'r', encoding='utf-8') as f:
    content = f.read()

idx = content.find('IDC_IPV4_RANGES')
if idx < 0:
    print('ERROR: not found')
    sys.exit(1)

eq = content.find('=', idx)
bracket = content.find('[', eq)
depth = 0
end = bracket
for i, ch in enumerate(content[bracket:]):
    if ch == '[':
        depth += 1
    elif ch == ']':
        depth -= 1
        if depth == 0:
            end = bracket + i + 1
            break

list_str = content[bracket:end]
print('Found list, {} bytes'.format(len(list_str)))

pattern = r"\('([^']+)',\s*\((\d+),\s*(\d+)\)"
matches = re.findall(pattern, list_str)
print('Parsed {} ranges'.format(len(matches)))
for m in matches[:10]:
    print('  {}: {} -> {}'.format(m[0], m[1], m[2]))
