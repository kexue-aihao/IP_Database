# -*- coding: utf-8 -*-
"""
S4.10 辅助脚本 A：S4 IPv6 产物字段结构扫描
扫描 data 中池覆盖的全部 MMDB 文件，输出每个文件的：
  - 记录数、字段键集合（union）
  - 关键字段 isp / idc_vendor / is_residential / connection_type 的覆盖情况
结果写入 UTF-8 输出文件（控制台避免中文）。
"""
import io
import os
import sys
import json
import maxminddb

OUT_DIR = r"E:\IP_Database"
FILES = [
    "china_ipv6.mmdb",
    "china_ipv6_telecom.mmdb",
    "china_ipv6_unicom.mmdb",
    "china_ipv6_mobile.mmdb",
    "china_ipv6_other.mmdb",
    "china_ipv6_idc.mmdb",
    "china_ipv6_with_isp.mmdb",
    "china_ipv6_enriched.mmdb",
    "china_ipv6_idc_enriched.mmdb",
]

KEY_FIELDS = ["isp", "idc_vendor", "is_residential", "connection_type"]

def scan_one(path):
    reader = maxminddb.open_database(path)
    record_count = 0
    keys = {}
    key_coverage = {k: 0 for k in KEY_FIELDS}
    sample = []
    for prefix, data in reader:
        record_count += 1
        for k in data:
            keys[k] = keys.get(k, 0) + 1
        for k in KEY_FIELDS:
            if k in data:
                key_coverage[k] += 1
        if record_count <= 6:
            sample.append((str(prefix), {k: str(v) for k, v in data.items()}))
    reader.close()
    return record_count, keys, key_coverage, sample

def main():
    lines = []
    summary = {}
    for fname in FILES:
        path = os.path.join(OUT_DIR, "output", fname)
        if not os.path.exists(path):
            lines.append(f"## {fname}\n  [缺失] {path}")
            summary[fname] = {"missing": True}
            continue
        try:
            record_count, keys, cov, sample = scan_one(path)
        except Exception as e:
            lines.append(f"## {fname}\n  [错误] {e!r}")
            summary[fname] = {"error": str(e)}
            continue
        kv = {k: v for k, v in sorted(keys.items())}
        cov_all = {k: (cov[k], record_count) for k in KEY_FIELDS}
        summary[fname] = {
            "records": record_count,
            "field_keys": kv,
            "coverage": cov_all,
        }
        lines.append(f"## {fname}")
        lines.append(f"- 记录数: {record_count}")
        lines.append(f"- 字段键数: {len(kv)}")
        lines.append("- 字段键:" + " ".join(f"`{k}`({v})" for k, v in kv.items()))
        lines.append("- 关键字段覆盖:")
        for k in KEY_FIELDS:
            lines.append(f"  - {k}: {cov[k]}/{record_count}")
        lines.append("- 前 6 条样例:")
        for p, d in sample:
            lines.append(f"  - {p}: {json.dumps(d, ensure_ascii=True)}")
        lines.append("")

    out_path = os.path.join(OUT_DIR, "data", "china", "v6", "v6_pool_field_scan.json")
    with io.open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, sort_keys=True)
    txt_path = os.path.join(OUT_DIR, "data", "china", "v6", "v6_pool_field_scan.txt")
    with io.open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("WROTE:", out_path)
    print("WROTE:", txt_path)
    print("SUMMARY_JSON_OK")
    # also print machine-readable brief on stdout (ASCII only)
    for fname, s in summary.items():
        if "missing" in s:
            print(f"[MISSING] {fname}")
        elif "error" in s:
            print(f"[ERROR] {fname}: {s['error']}")
        else:
            cov = s["coverage"]
            print(f"[OK] {fname} records={s['records']} keys={len(s['field_keys'])} "
                  f"isp={cov['isp'][0]} idc_vendor={cov['idc_vendor'][0]} "
                  f"is_residential={cov['is_residential'][0]} connection_type={cov['connection_type'][0]}")

if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    main()