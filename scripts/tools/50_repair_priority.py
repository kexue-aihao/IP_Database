#!/usr/bin/env python3
"""S1.5 — Repair Priority Sorter

Read the field gap report (data/audit/field_gap_report.csv) produced by
S1.4 and compute a repair priority ordering across all audited MMDB files:

    data/audit/repair_priority.json

Sorting policy (per pool spec):
  * File importance tier first (primary-use libraries first):
      T1  china_ipv4/6.mmdb            — 主库/主要用途库
      T2  global_*_residential.mmdb    — 全球住宅库
      T3  *_with_isp.mmdb              — 带 ISP 字段的聚合库
      T4  *_high_prec*.mmdb            — 高精度库
      T5  china_ipv{4,6}_{telecom,unicom,mobile,other}.mmdb — ISP 细分库
      T6  其余(IDC 库 / enriched 库)    — 专用库
  * Within a tier, files with MORE gaps come first (worst offenders first).
  * Gap count = #missing_fields + #type_mismatches.
  * Tie-break: filename ascending (deterministic).

tmp_v6.mmdb is a test residue excluded by S1.1 and is dropped from the list;
each entry carries an "excluded_reason" note where applicable.

Output is a JSON array (ordered list) of per-file objects.
"""

import csv
import json
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
AUDIT_DIR = os.path.join(ROOT, "data", "audit")
REPORT_PATH = os.path.join(AUDIT_DIR, "field_gap_report.csv")
OUTPUT_PATH = os.path.join(AUDIT_DIR, "repair_priority.json")

# Importance tiers: lower number = more important (repaired first).
# T1..T4 are the explicitly named "primary-use" families from the pool spec.
TIER_ORDER = {
    "china_ipv4.mmdb": 1,
    "china_ipv6.mmdb": 1,
    "global_ipv4_residential.mmdb": 2,
    "global_ipv6_residential.mmdb": 2,
    "china_ipv4_with_isp.mmdb": 3,
    "china_ipv6_with_isp.mmdb": 3,
    "china_ipv4_high_prec.mmdb": 4,
    "china_ipv4_high_prec_v2.mmdb": 4,
    "china_ipv4_telecom.mmdb": 5,
    "china_ipv4_unicom.mmdb": 5,
    "china_ipv4_mobile.mmdb": 5,
    "china_ipv4_other.mmdb": 5,
    "china_ipv6_telecom.mmdb": 5,
    "china_ipv6_unicom.mmdb": 5,
    "china_ipv6_mobile.mmdb": 5,
    "china_ipv6_other.mmdb": 5,
    "china_ipv4_idc.mmdb": 6,
    "china_ipv4_idc_enriched.mmdb": 6,
    "china_ipv6_idc.mmdb": 6,
    "china_ipv6_idc_enriched.mmdb": 6,
    "china_ipv6_enriched.mmdb": 6,
    "global_ipv4_idc.mmdb": 6,
    "global_ipv6_idc.mmdb": 6,
}

TIER_LABELS = {
    1: "primary",        # 主要用途库 china_ipv4/6.mmdb
    2: "global_residential",
    3: "with_isp",
    4: "high_prec",
    5: "isp_specific",
    6: "idc_enriched",
}

# Test residue file — excluded from the repair queue (S1.1 排除).
EXCLUDED_FILES = {
    "tmp_v6.mmdb": "测试残留文件（S1.1 排除，不参与修复）",
}


def count_multi(value):
    """Count ';'-separated items in a CSV cell; empty cell -> 0."""
    if not value or not value.strip():
        return 0
    return len([item for item in value.split(";") if item.strip()])


def load_report(path):
    rows = []
    # utf-8-sig strips the UTF-8 BOM from the header row.
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    if not rows:
        raise RuntimeError(f"report is empty: {path}")
    return rows


def build_priority_list(rows):
    entries = []
    seen = set()
    for row in rows:
        filename = row["file"].strip()
        if not filename:
            continue
        missing_count = count_multi(row.get("missing_fields", ""))
        type_count = count_multi(row.get("type_mismatches", ""))
        gap_count = missing_count + type_count
        if filename in EXCLUDED_FILES:
            entries.append({
                "file": filename,
                "importance_tier": None,
                "importance_label": "excluded",
                "gap_count": gap_count,
                "missing_fields_count": missing_count,
                "type_mismatch_count": type_count,
                "excluded_reason": EXCLUDED_FILES[filename],
            })
            seen.add(filename)
            continue
        tier = TIER_ORDER.get(filename)
        if tier is None:
            raise RuntimeError(
                f"file {filename!r} from the gap report has no importance tier; "
                "update TIER_ORDER"
            )
        entries.append({
            "file": filename,
            "importance_tier": tier,
            "importance_label": TIER_LABELS[tier],
            "gap_count": gap_count,
            "missing_fields_count": missing_count,
            "type_mismatch_count": type_count,
            "excluded_reason": None,
        })
        seen.add(filename)

    # Warn if any tier-mapped file is missing from the report (data drift).
    for fname in sorted(set(TIER_ORDER) - seen):
        print(f"WARN: {fname} not present in the gap report", flush=True)

    # Sort: importance tier asc -> gap count desc -> filename asc.
    ranked = sorted(
        (e for e in entries if e["importance_tier"] is not None),
        key=lambda e: (e["importance_tier"], -e["gap_count"], e["file"]),
    )
    excluded = [e for e in entries if e["importance_tier"] is None]
    return ranked, excluded


def main():
    rows = load_report(REPORT_PATH)
    ranked, excluded = build_priority_list(rows)

    for idx, entry in enumerate(ranked, start=1):
        entry["priority_rank"] = idx

    # JSON array = ordered list (array order IS the priority order).
    payload = ranked + excluded

    os.makedirs(AUDIT_DIR, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"input : {REPORT_PATH}")
    print(f"output: {OUTPUT_PATH}")
    print(f"ranked files: {len(ranked)} | excluded: {len(excluded)}")
    for e in ranked:
        print(
            f"  #{e['priority_rank']:>2} {e['file']:<28} "
            f"tier={e['importance_tier']} label={e['importance_label']:<18} "
            f"gaps={e['gap_count']:>2}"
        )
    for e in excluded:
        print(f"  X  {e['file']:<28} excluded: {e['excluded_reason']}")


if __name__ == "__main__":
    main()