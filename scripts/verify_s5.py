# -*- coding: utf-8 -*-
import json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
d = json.load(open(r'E:/IP_Database/data/city_map_final.json', encoding='utf-8'))
print('Stats:', json.dumps(d['statistics'], ensure_ascii=False))
m = d['mapping']
for name in ['Chai Wan', 'Tsing Yi', 'Tsim Sha Tsui', 'Kaohsiung City', 'Taipei', 'Banqiao District', 'Neihu District', 'Mong Kok', 'Quarry Bay', 'Haidian (Haidian Qu)', 'Central', 'Kowloon Bay', 'Jinrongjie (Xicheng District)']:
    print(f'  {name} -> {m.get(name, "<MISSING>")}')
print()
print('Unmapped:', len(d.get('unmapped_names', [])))
print('Sample unmapped:', d.get('unmapped_names', [])[:20])
