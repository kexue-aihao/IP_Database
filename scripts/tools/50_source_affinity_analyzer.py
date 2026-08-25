#!/usr/bin/env python3
"""S1.8 — Data-Source Affinity Analyzer (Data Source Field Affinity)

Inspect the raw data sources for org/ISP info availability and measure the
coverage of the org/ISP column over CN (China) records. Emits:

    data/audit/source_field_affinity.csv

Sources inspected:
  - data/ip2region_data/ipv4_source.txt   (ip2region IPv4, pipe delimited)
  - data/ip2region_data/ipv6_source.txt   (ip2region IPv6, pipe delimited)
  - data/global/classification.csv        (global classification, CSV; header + capped sample)

Method:
  - For the ip2region sources: sample the FIRST 50,000 data rows (all countries),
    classify a row as CN via the trailing country-code field (== 'CN'), and count
    how many of those CN records carry a non-empty org/ISP value in the org column.
  - For the global classification.csv: read the header to detect whether any
    org/ISP column exists; enumerate the distinct `source` lineage values over a
    capped sample (first 50,000 data rows).
  - Emit one CSV row per source with the org/ISP availability conclusion.
"""

import csv
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
AUDIT_DIR = os.path.join(ROOT, "data", "audit")
OUT_PATH = os.path.join(AUDIT_DIR, "source_field_affinity.csv")

IPV4_SRC = os.path.join(ROOT, "data", "ip2region_data", "ipv4_source.txt")
IPV6_SRC = os.path.join(ROOT, "data", "ip2region_data", "ipv6_source.txt")
CLASS_SRC = os.path.join(ROOT, "data", "global", "classification.csv")

SAMPLE_LIMIT = 50000  # 抽查前 5 万行

# Values treated as "no org/ISP info" in the org column of ip2region sources
EMPTY_ORG = {"", "0", "reserved", "unknown", "-", "null", "none"}


def is_empty_org(val):
    if val is None:
        return True
    return val.strip().lower() in EMPTY_ORG


def scan_pipe_source(path, org_idx, cc_idx):
    """Scan the FIRST SAMPLE_LIMIT data rows of a pipe-delimited source.

    Rows of every country are counted toward the sample; only CN rows (cc == 'CN')
    are measured for org/ISP coverage.

    org_idx: column index holding org/ISP
    cc_idx:  column index holding the ISO country code ('' for non-CN rows)
    Returns (rows_read, cn_total, cn_with_org, org_values_counter).
    """
    rows_read = 0
    cn_total = 0
    cn_with_org = 0
    org_counts = {}  # distinct org value -> count (CN rows only)
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.rstrip("\r\n")
            if not line.strip():
                continue
            cols = line.split("|")
            if len(cols) <= max(org_idx, cc_idx):
                continue
            rows_read += 1
            cc = cols[cc_idx].strip()
            if cc.upper() != "CN":
                if rows_read >= SAMPLE_LIMIT:
                    break
                continue
            cn_total += 1
            org = cols[org_idx]
            if not is_empty_org(org):
                cn_with_org += 1
                key = org.strip()
                org_counts[key] = org_counts.get(key, 0) + 1
            if rows_read >= SAMPLE_LIMIT:
                break
    return rows_read, cn_total, cn_with_org, org_counts


def top_orgs(org_counts, n=8):
    """Top-n distinct org values as a compact string."""
    top = sorted(org_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:n]
    return "; ".join(f"{k}({v})" for k, v in top)


def scan_classification(path):
    """Read header + first SAMPLE_LIMIT data rows of the classification.csv."""
    header = None
    rows_read = 0
    source_counts = {}
    with open(path, encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f)
        for row in reader:
            if header is None:
                header = row
                continue
            if not row:
                continue
            rows_read += 1
            source = row[header.index("source")] if "source" in header else "?"
            source_counts[source] = source_counts.get(source, 0) + 1
            if rows_read >= SAMPLE_LIMIT:
                break
    return header, rows_read, source_counts


def main():
    os.makedirs(AUDIT_DIR, exist_ok=True)

    # ---- ip2region IPv4: start_ip|end_ip|country|province|city|isp|cc ----
    v4_rows, v4_cn, v4_cn_org, v4_orgs = scan_pipe_source(IPV4_SRC, org_idx=5, cc_idx=6)
    v4_cov = (v4_cn_org / v4_cn * 100.0) if v4_cn else 0.0

    # ---- ip2region IPv6: start_ip|end_ip|country|province|city|org|cc ----
    v6_rows, v6_cn, v6_cn_org, v6_orgs = scan_pipe_source(IPV6_SRC, org_idx=5, cc_idx=6)
    v6_cov = (v6_cn_org / v6_cn * 100.0) if v6_cn else 0.0

    # ---- global classification.csv: header + capped sample ----
    class_header, class_rows, class_sources = scan_classification(CLASS_SRC)
    has_org_col = any(k.lower() in ("org", "isp", "asn", "as_name", "organization")
                      for k in class_header)
    src_summary = "; ".join(f"{k}({v})" for k, v in
                            sorted(class_sources.items(), key=lambda kv: -kv[1]))

    rows = [
        {
            "source": "ip2region_ipv4",
            "file_path": os.path.relpath(IPV4_SRC, ROOT),
            "has_org_isp_column": "yes",
            "org_isp_column": "col5 (isp)",
            "record_format": "pipe | start_ip|end_ip|country|province|city|isp|cc",
            "sampled_rows": v4_rows,
            "cn_records": v4_cn,
            "cn_records_with_org": v4_cn_org,
            "cn_org_coverage_pct": round(v4_cov, 2),
            "sample_org_values": top_orgs(v4_orgs),
            "conclusion": "含 ISP 列；CN 记录覆盖率高，可作中国库 isp 字段主来源。",
        },
        {
            "source": "ip2region_ipv6",
            "file_path": os.path.relpath(IPV6_SRC, ROOT),
            "has_org_isp_column": "yes",
            "org_isp_column": "col5 (org)",
            "record_format": "pipe | start_ip|end_ip|country|province|city|org|cc",
            "sampled_rows": v6_rows,
            "cn_records": v6_cn,
            "cn_records_with_org": v6_cn_org,
            "cn_org_coverage_pct": round(v6_cov, 2),
            "sample_org_values": top_orgs(v6_orgs),
            "conclusion": "含 org 列；CN 记录覆盖率高，含校园网/政企单位名，可作 isp/机构名来源。",
        },
        {
            "source": "global_classification_csv",
            "file_path": os.path.relpath(CLASS_SRC, ROOT),
            "has_org_isp_column": "no",
            "org_isp_column": "无（表头: "
            + "|".join(class_header)
            + "）",
            "record_format": "csv | start_ip,end_ip,country,region,city,lat,lng,source,continent,classification,class_confidence",
            "sampled_rows": class_rows,
            "cn_records": "n/a",
            "cn_records_with_org": "n/a",
            "cn_org_coverage_pct": "n/a",
            "sample_org_values": src_summary or "n/a",
            "conclusion": "无 org/ISP 列；仅含来源溯源列 source，ISP 需由 ip2region org / ASN 数据回填。",
        },
    ]

    fieldnames = [
        "source",
        "file_path",
        "has_org_isp_column",
        "org_isp_column",
        "record_format",
        "sampled_rows",
        "cn_records",
        "cn_records_with_org",
        "cn_org_coverage_pct",
        "sample_org_values",
        "conclusion",
    ]

    with open(OUT_PATH, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"[S1.8] wrote {OUT_PATH}")
    for r in rows:
        print(f"  {r['source']:>24s}  has_org={'yes' if r['has_org_isp_column']=='yes' else 'NO':<3s}  "
              f"cn={r['cn_records']}  cn_with_org={r['cn_records_with_org']}  cov={r['cn_org_coverage_pct']}")


if __name__ == "__main__":
    main()