#!/usr/bin/env python3
"""Summarize the complete field schema across all MMDB files."""
import json
import os

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
path = os.path.join(ROOT, "data", "audit", "field_inventory.json")

with open(path, encoding="utf-8") as f:
    inv = json.load(f)

# Collect all unique field names across all files
all_fields = {}
for fi in inv["files"]:
    for fd in fi["fields"]:
        name = fd["name"]
        if name not in all_fields:
            all_fields[name] = {"files": [], "types": set(), "max_coverage_files": []}
        all_fields[name]["files"].append(fi["filename"])
        all_fields[name]["types"].update(fd["types"])
        if fd["coverage_pct"] == 100.0:
            all_fields[name]["max_coverage_files"].append(fi["filename"])

print("=" * 80)
print("COMPLETE FIELD SCHEMA INVENTORY (Across All 23 MMDB Files)")
print("=" * 80)
print(f"{'Field':<20} {'Files':>5} {'Types':<20} {'FullCoverage':>6}")
print("-" * 80)
for name in sorted(all_fields.keys()):
    info = all_fields[name]
    nf = len(info["files"])
    types = ", ".join(sorted(info["types"]))
    fc = len(info["max_coverage_files"])
    print(f"{name:<20} {nf:>5} {types:<20} {fc:>6}")

print()
print("=" * 80)
print("FILES BY FIELD COUNT")
print("=" * 80)
for fi in sorted(inv["files"], key=lambda x: len(x["fields"]), reverse=True):
    fn = fi["filename"]
    nf = len(fi["fields"])
    warn = " (!truncated)" if not fi.get("record_count_exact", True) else ""
    print(f"  {nf:>2} fields  {fn}{warn}")

print()
print("=" * 80)
print("FIELD COVERAGE BY FILE (matrix)")
print("=" * 80)
header = "{:<32}".format("File")
for name in sorted(all_fields.keys()):
    header += f" {name:<15}"
print(header)
for fi in inv["files"]:
    fn = fi["filename"]
    field_map = {fd["name"]: fd["coverage_pct"] for fd in fi["fields"]}
    row = f"{fn:<32}"
    for name in sorted(all_fields.keys()):
        if name in field_map:
            pct = field_map[name]
            if pct == 100.0:
                row += f" {'100%':>15}"
            else:
                row += f" {pct:>5}%{'':>8}"
        else:
            row += f" {'-':>15}"
    print(row)