#!/usr/bin/env python3
"""S1.4 — Field Gap Analyzer
Compare each MMDB file's field inventory (field_inventory.json) against the
target schema (target_schema.json), and emit a per-file gap report:

    data/audit/field_gap_report.csv

CSV columns:
  file              — MMDB filename (output/*.mmdb)
  missing_fields    — target fields (per file-group core_fields) absent from the file
  type_mismatches   — target fields whose value type differs (e.g. lat/lng as str),
                      with sample values
  notes             — coverage warnings, legacy fields, required-field violation,
                      extra fields, group assignment, record count

Coverage: one row per MMDB file present in output/ (including files excluded
from the S1.1 inventory, which are scanned directly here).
"""

import csv
import glob
import json
import os

import maxminddb

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
AUDIT_DIR = os.path.join(ROOT, "data", "audit")
OUTPUT_DIR = os.path.join(ROOT, "output")
REPORT_PATH = os.path.join(AUDIT_DIR, "field_gap_report.csv")

# Inventory scanner type names -> target_schema type names
INV_TYPE_MAP = {
    "str": "string",
    "float": "number",
    "int": "integer",
    "bool": "boolean",
    "null": "null",
    "list": "array",
    "dict": "map",
}

TYPE_MAP = {
    type(None): "null",
    str: "str",
    int: "int",
    float: "float",
    bool: "bool",
    list: "list",
    dict: "dict",
}


def get_type_name(val):
    return TYPE_MAP.get(type(val), type(val).__name__)


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def direct_scan(filepath):
    """Minimal inventory scan for files missing from field_inventory.json."""
    filename = os.path.basename(filepath)
    result = {
        "filename": filename,
        "record_count": 0,
        "record_count_exact": True,
        "fields": [],
        "samples": [],
        "direct_scan": True,
    }
    try:
        reader = maxminddb.Reader(filepath, maxminddb.const.MODE_FILE)
        meta = reader.metadata()
        result["metadata"] = {
            "node_count": meta.node_count,
            "ip_version": meta.ip_version,
            "database_type": meta.database_type,
        }
    except Exception as e:
        result["direct_scan_error"] = f"Failed to open: {e}"
        return result

    field_stats = {}
    for network, record in reader:
        if record is None:
            continue
        result["record_count"] += 1
        if len(result["samples"]) < 5:
            result["samples"].append({"network": str(network), "record": record})
        if isinstance(record, dict):
            for key, val in record.items():
                if key not in field_stats:
                    field_stats[key] = {"count": 0, "types": set(), "sample_values": []}
                field_stats[key]["count"] += 1
                field_stats[key]["types"].add(get_type_name(val))
                if len(field_stats[key]["sample_values"]) < 3:
                    sv = val
                    if isinstance(sv, str) and len(sv) > 50:
                        sv = sv[:50] + "..."
                    if sv not in field_stats[key]["sample_values"]:
                        field_stats[key]["sample_values"].append(sv)
    reader.close()

    for fname in sorted(field_stats.keys()):
        stat = field_stats[fname]
        result["fields"].append({
            "name": fname,
            "coverage_pct": round(stat["count"] / max(result["record_count"], 1) * 100, 2),
            "records_with_field": stat["count"],
            "types": sorted(stat["types"]),
            "sample_values": stat["sample_values"],
        })
    return result


def main():
    inventory = load_json(os.path.join(AUDIT_DIR, "field_inventory.json"))
    schema = load_json(os.path.join(AUDIT_DIR, "target_schema.json"))

    inv_by_file = {f["filename"]: f for f in inventory["files"]}

    groups = schema["file_group_applicability"]
    group_by_file = {}
    for gname, ginfo in groups.items():
        for f in ginfo["files"]:
            group_by_file[f] = gname

    # Union of all core fields -> fallback target set for unclassified files
    union_core = set()
    for ginfo in groups.values():
        union_core.update(ginfo["core_fields"])
    union_core = sorted(union_core)

    # Required target fields (schema fields with required: true)
    required_target = {f["name"] for f in schema["fields"] if f.get("required")}

    all_mmdb = sorted(glob.glob(os.path.join(OUTPUT_DIR, "*.mmdb")))

    rows = []
    for fp in all_mmdb:
        fname = os.path.basename(fp)
        entry = inv_by_file.get(fname)
        if entry is None:
            entry = direct_scan(fp)  # e.g. tmp_v6.mmdb excluded from S1.1

        group = group_by_file.get(fname)
        if group:
            target_fields = list(groups[group]["core_fields"])
        else:
            target_fields = list(union_core)

        inv_fields = {fd["name"]: fd for fd in entry.get("fields", [])}

        missing, mismatches, notes = [], [], []

        # --- missing fields + coverage / required notes ---
        for tf in target_fields:
            if tf not in inv_fields:
                missing.append(tf)
                if tf in required_target:
                    notes.append(f"[REQUIRED] {tf} 缺失")
            else:
                fd = inv_fields[tf]
                if fd["coverage_pct"] < 100.0:
                    notes.append(f"覆盖率 {tf}={fd['coverage_pct']}% ({fd['records_with_field']}/{entry.get('record_count', '?')})")

        # --- type mismatches (with samples) ---
        tf_types = {f["name"]: f.get("type") for f in schema["fields"]}
        for tf in target_fields:
            if tf not in inv_fields:
                continue
            fd = inv_fields[tf]
            target_t = tf_types.get(tf)
            if target_t is None:
                continue  # target field without declared type (unlikely)
            bad = [t for t in fd["types"] if INV_TYPE_MAP.get(t) != target_t]
            if bad:
                samples = ", ".join(repr(s) for s in fd["sample_values"][:2])
                mismatches.append(
                    f"{tf}: {'/'.join(fd['types'])}→{target_t} (样例 {samples})"
                )

        # --- legacy / extra field notes ---
        legacy_map = schema.get("legacy_field_map", {})
        for legacy_name, linfo in legacy_map.items():
            if legacy_name in inv_fields:
                notes.append(f"legacy 字段 {legacy_name} → {linfo['target']}")

        extras = sorted(set(inv_fields) - set(target_fields))
        if extras:
            notes.append("额外字段: " + ", ".join(extras))

        # --- file-level notes ---
        if entry.get("warning"):
            notes.append("警告: " + entry["warning"])
        if entry.get("direct_scan"):
            notes.append("S1.1 未扫描，本报告直扫")
        if entry.get("direct_scan_error"):
            notes.append("打开失败: " + entry["direct_scan_error"])
        if fname == "tmp_v6.mmdb":
            notes.append("测试残留文件（S1.1 排除），按全并集 core_fields 比对")
        elif not group:
            notes.append("未归类到任何文件组，按全并集 core_fields 比对")

        rows.append({
            "file": fname,
            "missing_fields": "; ".join(missing) if missing else "",
            "type_mismatches": "; ".join(mismatches) if mismatches else "",
            "notes": " | ".join(notes) if notes else "OK",
        })

    os.makedirs(AUDIT_DIR, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["file", "missing_fields", "type_mismatches", "notes"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"Written: {REPORT_PATH}")
    print(f"Rows: {len(rows)} (MMDB files in output/: {len(all_mmdb)})")
    for r in rows:
        n_miss = len([x for x in r["missing_fields"].split("; ") if x])
        n_mis = len([x for x in r["type_mismatches"].split("; ") if x])
        print(f"  {r['file']:<38} missing={n_miss:>2} type_mismatch={n_mis:>2}")


if __name__ == "__main__":
    main()