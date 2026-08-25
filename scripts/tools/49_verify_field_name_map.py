# -*- coding: utf-8 -*-
"""S1.6 字段名映射表 - 产出验证脚本"""
import json
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

MAP_PATH = r"E:\IP_Database\data\audit\field_name_map.json"

with open(MAP_PATH, "r", encoding="utf-8") as f:
    m = json.load(f)

print("字段扫描结果汇总:")
print("  field_map 规则数:", len(m["field_map"]))
for k, v in m["field_map"].items():
    tgt = v["target"]
    act = v["action"]
    n = len(v["scope_files"])
    print("    %s -> %s (%s), 覆盖 %d 个文件" % (k, tgt, act, n))
print("  identity 字段数:", len(m["identity_fields"]["fields"]))
print("  appendix 字段数:", len(m["appendix_fields"]["fields"]))
print("  patch recipe 文件数:", len(m["complete_patch_recipe_per_file"]))
print("  file_group 数:", len(m["rules_by_file_group"]))
print("  校验不变量数:", len(m["validation"].get("invariant", [])) +
      sum(1 for kk in m["validation"] if kk.startswith("invariant_")))