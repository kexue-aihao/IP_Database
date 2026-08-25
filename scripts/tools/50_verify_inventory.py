#!/usr/bin/env python3
"""Verify field_inventory.json summary."""
import json
import os

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
path = os.path.join(ROOT, "data", "audit", "field_inventory.json")

with open(path, encoding="utf-8") as f:
    inv = json.load(f)

print("Total files in inventory:", len(inv["files"]))
print("Excluded:", inv["scan_info"]["excluded_files"])
print()
print(f"{'filename':<32} {'records':>9} {'exact':<6} {'fields':>6}")
print("-" * 60)
for fi in inv["files"]:
    rc = fi["record_count"]
    ex = fi.get("record_count_exact", True)
    nf = len(fi["fields"])
    warn = " !truncated" if not ex else ""
    print(f"{fi['filename']:<32} {rc:>9} {str(ex):<6} {nf:>6}{warn}")

print()
for fn in ["global_ipv4_residential.mmdb", "global_ipv6_residential.mmdb",
           "global_ipv4_idc.mmdb", "global_ipv6_idc.mmdb", "china_ipv4_high_prec.mmdb"]:
    fi = next(x for x in inv["files"] if x["filename"] == fn)
    print(f"--- {fn} ---")
    for fd in fi["fields"]:
        print(f"  {fd['name']:<20} cov={fd['coverage_pct']}% types={fd['types']} samples={fd['sample_values']}")
    print()