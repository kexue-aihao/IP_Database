#!/usr/bin/env python3
"""Merge exact record counts into field_inventory.json.
Reads data/audit/exact_counts.json (produced by 50_exact_counts.py) and
updates each matching file entry's record_count / record_count_exact flag.
"""
import json
import os

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
INV_PATH = os.path.join(ROOT, "data", "audit", "field_inventory.json")
COUNT_PATH = os.path.join(ROOT, "data", "audit", "exact_counts.json")

with open(INV_PATH, encoding="utf-8") as f:
    inv = json.load(f)

if not os.path.exists(COUNT_PATH):
    print("exact_counts.json not found yet — nothing to merge")
    raise SystemExit(0)

with open(COUNT_PATH, encoding="utf-8") as f:
    exact = json.load(f)

updated = []
for fi in inv["files"]:
    fn = fi["filename"]
    if fn in exact:
        fi["record_count"] = exact[fn]["record_count"]
        fi["record_count_exact"] = True
        fi["warning"] = "Exact count merged from full scan"
        fi.pop("warning", None) if False else None
        # keep prior warning only if still meaningful
        updated.append((fn, exact[fn]["record_count"]))

with open(INV_PATH, "w", encoding="utf-8") as f:
    json.dump(inv, f, ensure_ascii=False, indent=2)

inv["scan_info"]["exact_count_merge_time"] = __import__("datetime").datetime.now(
    __import__("datetime").timezone.utc
).isoformat()

# rewrite again to include merge time (simpler: re-dump after adding field)
with open(INV_PATH, "w", encoding="utf-8") as f:
    json.dump(inv, f, ensure_ascii=False, indent=2)

print(f"Merged exact counts for {len(updated)} files:")
for fn, rc in updated:
    print(f"  {fn}: {rc}")
print("Written:", INV_PATH)