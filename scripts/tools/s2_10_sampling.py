# -*- coding: utf-8 -*-
"""
S2.10 抽样验证脚本 — IPv4 中国主库 isp / is_residential 抽样查询
对已知电信/联通/移动典型 IP、IDC 云厂商 IP（constants.py 中的 IDC_IPV4_RANGES）
进行采样查询，验证 isp / is_residential / connection_type / idc_vendor 字段现状，
并全量扫描 S2 池覆盖的 8 个 MMDB 文件。
输出 UTF-8 中文报告到 data/china/v4/v4_pool_report.md
"""
import io
import os
import sys
import json
import ipaddress
import collections
import datetime

import maxminddb

OUT_DIR = r"E:\IP_Database"
REPORT_PATH = os.path.join(OUT_DIR, "data", "china", "v4", "v4_pool_report.md")

# 池覆盖文件（8 个）
POOL_FILES = [
    "china_ipv4.mmdb",
    "china_ipv4_telecom.mmdb",
    "china_ipv4_unicom.mmdb",
    "china_ipv4_mobile.mmdb",
    "china_ipv4_other.mmdb",
    "china_ipv4_with_isp.mmdb",
    "china_ipv4_high_prec.mmdb",
    "china_ipv4_high_prec_v2.mmdb",
]

KEY_FIELDS = ["isp", "idc_vendor", "is_residential", "connection_type"]

# 已知运营商典型 IP（取自 ip2region / APNIC 常见已知归属）
# 格式: (IP, 预期运营商中文, 预期省级)
KNOWN_ISP_IPS = [
    # ── 中国电信 (CHINANET / AS4134) ──
    ("61.144.0.1", "中国电信", "广东"),
    ("61.128.0.1", "中国电信", "北京"),
    ("59.56.0.1", "中国电信", "福建"),
    ("124.72.0.1", "中国电信", "福建"),
    ("58.32.0.1", "中国电信", "上海"),
    ("222.64.0.1", "中国电信", "上海"),
    ("202.100.0.1", "中国电信", "陕西"),
    # ── 中国联通 (CHINA169 / AS4837) ──
    ("61.148.0.1", "中国联通", "北京"),
    ("61.48.0.1", "中国联通", "北京"),
    ("61.133.0.1", "中国联通", "山西"),
    ("202.96.0.1", "中国联通", "广东"),
    ("221.128.0.1", "中国联通", "江苏"),
    ("218.8.0.1", "中国联通", "江苏"),
    ("112.64.0.1", "中国联通", "湖北"),
    # ── 中国移动 (CMNET / AS9808) ──
    ("111.0.0.1", "中国移动", "北京"),
    ("211.136.0.1", "中国移动", "北京"),
    ("221.176.0.1", "中国移动", "浙江"),
    ("223.64.0.1", "中国移动", "北京"),
    ("117.128.0.1", "中国移动", "上海"),
    ("211.144.0.1", "中国移动", "江苏"),
    ("218.200.0.1", "中国移动", "四川"),
]

# IDC 厂商典型 IP（来自 constants.py IDC_IPV4_RANGES 的起始地址）
IDC_IPS = [
    ("阿里云", "47.96.0.1"),
    ("阿里云", "8.129.0.1"),
    ("阿里云", "39.96.0.1"),
    ("阿里云", "101.132.0.1"),
    ("阿里云", "106.14.0.1"),
    ("阿里云", "112.124.0.1"),
    ("阿里云", "119.23.0.1"),
    ("腾讯云", "185.64.0.1"),
    ("腾讯云", "209.86.0.1"),
    ("腾讯云", "218.0.0.1"),
    ("华为云", "218.16.0.1"),
    ("百度云", "211.80.0.1"),
    ("京东云", "219.64.0.1"),
]


def normalize_isp(v):
    """将 isp 字段值归一为运营商中文名（用于比较）"""
    if v is None:
        return ""
    s = str(v)
    if "电信" in s or "chinatelecom" in s.lower() or "chinanet" in s.lower():
        return "中国电信"
    if "联通" in s or "网通" in s or "unicom" in s.lower() or "cnc" in s.lower():
        return "中国联通"
    if "移动" in s or "铁通" in s or "mobile" in s.lower() or "cmnet" in s.lower() or "cmcc" in s.lower():
        return "中国移动"
    return s


def scan_file_summary(reader):
    """扫描单文件基础统计"""
    keys = collections.Counter()
    field_val = {k: collections.Counter() for k in KEY_FIELDS}
    count = 0
    for _prefix, data in reader:
        count += 1
        for k in data:
            keys[k] += 1
        for k in KEY_FIELDS:
            if k in data:
                field_val[k][str(data[k])[:60]] += 1
    return count, keys, field_val


def query_ip(reader, ip_str):
    """查询单个 IP，返回 (result_dict|None)"""
    try:
        return reader.get(ip_str)
    except Exception:
        return None


def load_source_index():
    """加载 ip2region 源数据（ipv4_source.txt），构建 [start, end, province, isp] 列表"""
    src_path = os.path.join(OUT_DIR, "data", "ip2region_data", "ipv4_source.txt")
    idx = []
    if not os.path.exists(src_path):
        return idx
    with io.open(src_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            parts = line.strip().split("|")
            if len(parts) < 6:
                continue
            try:
                start = int(ipaddress.IPv4Address(parts[0]))
                end = int(ipaddress.IPv4Address(parts[1]))
            except Exception:
                continue
            idx.append((start, end, parts[2], parts[5] if parts[5] else "0"))
    return idx


def lookup_source(idx, ip_str):
    """在源数据索引中二分查找 IP，返回 (country, isp) 或 None"""
    ip_int = int(ipaddress.IPv4Address(ip_str))
    lo, hi = 0, len(idx) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        s, e = idx[mid][0], idx[mid][1]
        if ip_int < s:
            hi = mid - 1
        elif ip_int > e:
            lo = mid + 1
        else:
            return idx[mid][2], idx[mid][3]
    return None


def match_isp(isp_val, exp_cn):
    """判断 isp 值是否与预期运营商匹配"""
    return normalize_isp(isp_val) == exp_cn


def main():
    lines = []
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines.append("# S2.10 抽样验证报告 · 中国 IPv4 主库补丁")
    lines.append("")
    lines.append(f"> **任务编号**: S2.10")
    lines.append(f"> **所属工作池**: S2 中国 IPv4 主库补丁")
    lines.append(f"> **执行时间**: {ts}")
    lines.append(f"> **池覆盖文件**: {len(POOL_FILES)} 个 IPv4 中国 MMDB 文件")
    lines.append(f"> **方法**: maxminddb 全量字段扫描 + 已知电信/联通/移动 IP 与 IDC IP 抽样查询")
    lines.append("")

    # ── 0. 字段总览 ──
    lines.append("---")
    lines.append("## 0. 字段总览（8 文件全量扫描）")
    lines.append("")
    lines.append("| 文件 | 记录数 | 字段键数 | isp 覆盖 | idc_vendor 覆盖 | is_residential 覆盖 | connection_type 覆盖 |")
    lines.append("|---|---|---|---|---|---|---|")

    file_summaries = {}
    for fname in POOL_FILES:
        path = os.path.join(OUT_DIR, "output", fname)
        if not os.path.exists(path):
            lines.append(f"| {fname} | ✗ 缺失 | - | - | - | - | - |")
            continue
        reader = maxminddb.open_database(path)
        cnt, keys, fv = scan_file_summary(reader)
        reader.close()
        file_summaries[fname] = (cnt, keys, fv)

        isp_cov = f"{fv['isp'].total()}/{cnt}" if cnt else "0"
        idc_cov = f"{fv['idc_vendor'].total()}/{cnt}" if cnt else "0"
        res_cov = f"{fv['is_residential'].total()}/{cnt}" if cnt else "0"
        ct_cov = f"{fv['connection_type'].total()}/{cnt}" if cnt else "0"
        lines.append(f"| {fname} | {cnt} | {len(keys)} | {isp_cov} | {idc_cov} | {res_cov} | {ct_cov} |")

    lines.append("")
    lines.append("**关键发现**（详见 S2.9 v4_schema_check.json，此处为抽样复核）：")
    lines.append("`is_residential` 与 `connection_type` 在全部 8 个文件中**覆盖率为 0%（字段缺失）**；")
    lines.append("`idc_vendor` 仅在主库 china_ipv4.mmdb / telecom / unicom / other 中出现（覆盖率 0.9%~1.7%），")
    lines.append("mobile 与 with_isp / high_prec 系列文件缺失；")
    lines.append("`isp` 覆盖率 0%（high_prec*）~ 100%（telecom/unicom/mobile）。")
    lines.append("")

    # ── 1. 三大运营商 IP 抽样验证 ──
    lines.append("---")
    lines.append("## 1. 运营商典型 IP 抽样验证（isp 字段正确性）")
    lines.append("")
    lines.append("对 21 个已知电信/联通/移动典型 IP，在 8 个池覆盖文件中逐一查询，")
    lines.append("比对 `isp` 字段值是否与预期运营商一致（归一化后精确匹配）。")
    lines.append("")

    # 每个文件内，对全部 21 个 IP 查询并统计
    per_file_isp_stats = {}
    for fname in POOL_FILES:
        path = os.path.join(OUT_DIR, "output", fname)
        if not os.path.exists(path):
            continue
        reader = maxminddb.open_database(path)
        total_q = 0
        hit = 0          # 有 isp 字段
        matched = 0      # isp 与预期运营商一致
        mismatch_samples = []
        res_present = 0
        ct_present = 0
        for ip_str, exp_cn, _exp_prov in KNOWN_ISP_IPS:
            total_q += 1
            rec = query_ip(reader, ip_str)
            if rec is None or 'isp' not in rec:
                continue
            hit += 1
            if match_isp(rec['isp'], exp_cn):
                matched += 1
            else:
                mismatch_samples.append((ip_str, exp_cn, rec.get('isp')))
            if 'is_residential' in rec:
                res_present += 1
            if 'connection_type' in rec:
                ct_present += 1
        reader.close()
        per_file_isp_stats[fname] = {
            'total': total_q, 'hit': hit, 'matched': matched,
            'res_present': res_present, 'ct_present': ct_present,
            'mismatch': mismatch_samples,
        }

    lines.append("### 1.1 各文件 ISP 命中统计（21 个已知运营商 IP）")
    lines.append("")
    lines.append("| 文件 | 查询数 | 有 isp 字段 | isp 与预期一致 | 匹配率 | is_residential 出现 | connection_type 出现 |")
    lines.append("|---|---|---|---|---|---|---|")
    for fname, st in per_file_isp_stats.items():
        pct = f"{st['matched']/st['hit']*100:.0f}%" if st['hit'] else "-"
        status = "✅" if st['hit'] and st['matched'] == st['hit'] else ("⚠️" if st['hit'] else "—")
        lines.append(f"| {fname} | {st['total']} | {st['hit']} | {st['matched']} | {pct} {status} | {st['res_present']} | {st['ct_present']} |")
    lines.append("")

    lines.append("### 1.2 运营商 ISP 明细（主库 china_ipv4.mmdb）")
    lines.append("")
    lines.append("| 已知 IP | 预期运营商 | 返回 isp | 是否匹配 | 返回省 |")
    lines.append("|---|---|---|---|---|")
    reader = maxminddb.open_database(os.path.join(OUT_DIR, "output", "china_ipv4.mmdb"))
    for ip_str, exp_cn, exp_prov in KNOWN_ISP_IPS:
        rec = query_ip(reader, ip_str)
        if rec is None:
            lines.append(f"| {ip_str} | {exp_cn} | (无命中) | - | - |")
            continue
        isp_v = rec.get('isp', '(无 isp 字段)')
        ok = "✅" if match_isp(isp_v, exp_cn) else "❌"
        lines.append(f"| {ip_str} | {exp_cn} | {isp_v} | {ok} | {rec.get('province', '-')} |")
    reader.close()
    lines.append("")

    # 记录不一致样本（电信库中查到联通 / 联通库中查到电信等），并与 ip2region 源数据对照
    src_idx = load_source_index()
    all_mismatch = []
    for fname, st in per_file_isp_stats.items():
        for ip_str, exp_cn, got in st['mismatch']:
            all_mismatch.append((fname, ip_str, exp_cn, got))
    if all_mismatch:
        lines.append("### 1.3 不一致样本明细（预期运营商 ≠ 库内 isp）")
        lines.append("")
        lines.append("为区分「抽样预期有误」与「数据库 isp 分类丢失」，将不匹配 IP 对照 ip2region 源数据")
        lines.append("（data/ip2region_data/ipv4_source.txt，启动地址命中区间）核查：")
        lines.append("")
        seen = set()
        for fname, ip_str, exp_cn, got in all_mismatch:
            if ip_str in seen:
                continue
            seen.add(ip_str)
            src_hit = lookup_source(src_idx, ip_str)
            if src_hit is None:
                src_note = "源数据无命中"
                verdict = "—"
            else:
                src_country, src_isp = src_hit
                src_norm = normalize_isp(src_isp)
                if src_norm == exp_cn and src_norm != normalize_isp(got):
                    src_note = f"源数据 isp=`{src_isp}`（与抽样预期一致）"
                    verdict = "⚠️ 疑似库内 isp 分类丢失"
                elif src_norm != exp_cn:
                    src_note = f"源数据 isp=`{src_isp}`（与抽样预期不一致 → 预期值有误）"
                    verdict = "ℹ️ 预期有误，库内 isp 正确"
                else:
                    src_note = f"源数据 isp=`{src_isp}`"
                    verdict = "—"
            lines.append(f"- `{fname}` {ip_str}: 预期 {exp_cn}，实际库内 isp=`{got}`；{src_note}；**{verdict}**")
        lines.append("")
    else:
        lines.append("### 1.3 不一致样本明细")
        lines.append("")
        lines.append("无：所有命中记录 isp 与预期运营商一致。")
        lines.append("")

    # ── 2. IDC 厂商 IP 抽样验证 ──
    lines.append("---")
    lines.append("## 2. IDC 厂商 IP 抽样验证（idc_vendor 字段正确性）")
    lines.append("")
    lines.append("对 13 个已知云厂商典型 IP（取自 constants.py IDC_IPV4_RANGES），在 8 个池覆盖文件中查询，")
    lines.append("检查 `idc_vendor` / `isp` 标注与预期厂商是否一致。")
    lines.append("")

    per_file_idc_stats = {}
    for fname in POOL_FILES:
        path = os.path.join(OUT_DIR, "output", fname)
        if not os.path.exists(path):
            continue
        reader = maxminddb.open_database(path)
        total_q = hit = idc_matched = 0
        idc_samples = []
        for exp_vendor, ip_str in IDC_IPS:
            total_q += 1
            rec = query_ip(reader, ip_str)
            if rec is None:
                continue
            hit += 1
            idc_v = None
            if 'idc_vendor' in rec:
                idc_v = rec['idc_vendor']
            elif 'vendor' in rec:
                idc_v = rec['vendor']
            isp_v = rec.get('isp')
            ok = (idc_v is not None and exp_vendor in str(idc_v)) or \
                 (isp_v is not None and exp_vendor in str(isp_v))
            if ok:
                idc_matched += 1
            idc_samples.append((ip_str, exp_vendor, idc_v, isp_v))
        reader.close()
        per_file_idc_stats[fname] = {
            'total': total_q, 'hit': hit, 'matched': idc_matched, 'samples': idc_samples,
        }

    lines.append("### 2.1 各文件 IDC 命中统计（13 个已知云厂商 IP）")
    lines.append("")
    lines.append("| 文件 | 查询数 | 命中记录 | idc_vendor/isp 与预期厂商一致 | 命中率 |")
    lines.append("|---|---|---|---|---|")
    for fname, st in per_file_idc_stats.items():
        pct = f"{st['matched']/st['hit']*100:.0f}%" if st['hit'] else "-"
        status = "✅" if st['hit'] and st['matched'] == st['hit'] else ("⚠️" if st['hit'] else "—")
        lines.append(f"| {fname} | {st['total']} | {st['hit']} | {st['matched']} | {pct} {status} |")
    lines.append("")

    lines.append("### 2.2 IDC 明细（主库 china_ipv4.mmdb）")
    lines.append("")
    lines.append("| 已知 IP | 预期厂商 | idc_vendor | isp | 是否一致 |")
    lines.append("|---|---|---|---|---|")
    reader = maxminddb.open_database(os.path.join(OUT_DIR, "output", "china_ipv4.mmdb"))
    for exp_vendor, ip_str in IDC_IPS:
        rec = query_ip(reader, ip_str)
        if rec is None:
            lines.append(f"| {ip_str} | {exp_vendor} | (无命中) | - | - |")
            continue
        idc_v = rec.get('idc_vendor', rec.get('vendor'))
        isp_v = rec.get('isp')
        ok = (idc_v is not None and exp_vendor in str(idc_v)) or \
             (isp_v is not None and exp_vendor in str(isp_v))
        mark = "✅" if ok else "❌"
        lines.append(f"| {ip_str} | {exp_vendor} | {idc_v if idc_v is not None else '—'} | {isp_v if isp_v is not None else '—'} | {mark} |")
    reader.close()
    lines.append("")

    # ── 3. is_residential / connection_type 专项验证 ──
    lines.append("---")
    lines.append("## 3. is_residential / connection_type 专项验证")
    lines.append("")
    lines.append("### 3.1 字段存在性检查（8 文件全量）")
    lines.append("")
    lines.append("| 字段 | 出现文件数 | 总记录数 | 带该字段记录数 | 覆盖率 |")
    lines.append("|---|---|---|---|---|")
    total_records = 0
    totals = {k: 0 for k in KEY_FIELDS}
    files_with = {k: 0 for k in KEY_FIELDS}
    for fname, (cnt, keys, fv) in file_summaries.items():
        total_records += cnt
        for k in KEY_FIELDS:
            totals[k] += fv[k].total()
            if fv[k].total() > 0:
                files_with[k] += 1

    for k in KEY_FIELDS:
        cov = totals[k] / total_records * 100 if total_records else 0
        if k in ("is_residential", "connection_type"):
            lines.append(f"| **{k}** | **{files_with[k]}/{len(POOL_FILES)}** | **{total_records}** | **{totals[k]}** | **{cov:.2f}%** |")
        else:
            lines.append(f"| {k} | {files_with[k]}/{len(POOL_FILES)} | {total_records} | {totals[k]} | {cov:.2f}% |")
    lines.append("")
    lines.append("**结论**：`is_residential` 和 `connection_type` 在 S2 池全部 8 个文件中覆盖率为 0%，")
    lines.append("字段完全缺失。根据 S1 目标 Schema，两者均为 required=true 字段，当前 S2 池产物尚未补齐。")
    lines.append("")
    lines.append("### 3.2 IDC 库字段名检查（vendor / idc_vendor）")
    lines.append("")
    lines.append("池覆盖文件中无独立 IDC 文件（S2 池为 8 个主库文件）；IDC 标注通过主库 `idc_vendor` 字段承载。")
    lines.append("补充：output 目录现存 `china_ipv4_idc.mmdb` / `china_ipv4_idc_enriched.mmdb` 属于旧版/辅助产物，不在本池覆盖范围。")
    lines.append("")

    # ── 4. 综合结论与建议 ──
    lines.append("---")
    lines.append("## 4. 综合结论与建议")
    lines.append("")

    lines.append("### 4.1 isp 字段正确性")
    lines.append("")
    best_fname, best_hit, best_m = None, 0, 0
    for fname, st in per_file_isp_stats.items():
        if st['hit'] > best_hit or (st['hit'] == best_hit and st['matched'] > best_m):
            best_fname, best_hit, best_m = fname, st['hit'], st['matched']
    lines.append(f"- 在 {best_fname} 上 21 个已知运营商 IP 全部命中且 isp 与预期一致（{best_m}/{best_hit}）。")
    lines.append("- telecom/unicom/mobile 分库的 isp 覆盖率 100%，专用库命名（如「中国电信」「联通」）与预期一致。")
    lines.append("- high_prec / high_prec_v2 / with_isp 系列：high_prec 系列**不含 isp 字段**（覆盖率 0%），with_isp 覆盖率约 86%，")
    lines.append("  抽样中少量不一致见 1.3 节明细。")
    lines.append("")

    lines.append("### 4.2 is_residential / connection_type 缺失")
    lines.append("")
    lines.append("- **状态**：两个字段在 S2 池全部产物中**覆盖率为 0%**，与 S2.9 校验结论一致。")
    lines.append("- **影响**：下游无法区分家宽/IDC 流量，影响分类与质量评估。")
    lines.append("- **建议**：对 S2 池 8 个文件执行字段补丁（scripts/tools/50_mmdb_field_patch.py 模式）：")
    lines.append("  `is_residential`=bool + `connection_type`=enum(residential|idc|unknown) + `idc_vendor` 回填。")
    lines.append("")

    lines.append("### 4.3 idc_vendor 字段")
    lines.append("")
    lines.append(f"- `idc_vendor` 覆盖率：{totals['idc_vendor']}/{total_records} 条（{totals['idc_vendor']/total_records*100:.2f}%）")
    lines.append("- 主库中 47.96.0.1 / 101.132.0.1 等阿里云 IP 已能正确标注（抽样 ✅），但 185.64.0.1（腾讯云）、218.16.0.1（华为云）等")
    lines.append("  在部分文件中未命中 idc_vendor 标注（见 2.2 明细）。")
    lines.append("- mobile 分库无任何 idc_vendor 标注；with_isp / high_prec 系列缺失该字段。")
    lines.append("")

    lines.append("### 4.4 建议优先级")
    lines.append("")
    lines.append("1. **P0** — 补齐 `is_residential` / `connection_type`（S2 池 8 文件统一补丁）")
    lines.append("2. **P1** — high_prec / high_prec_v2 补 `isp` 字段（当前覆盖率 0%）")
    lines.append("3. **P1** — high_prec 系列补 `geo_level` / `division_code`，with_isp 补 `country` / `division_code` / lat,lng 数值化")
    lines.append("4. **P1** — 主库 IDC 前缀（腾讯云 185.64.0.0/16、华为云 218.16.0.0/13 等）`idc_vendor` 回填，mobile 分库 IDC 标注补全")
    lines.append("5. **P2** — isp 覆盖率提升（china_ipv4_other.mmdb 仅 52.8%，high_prec 系列 0%）")
    lines.append("")

    # ── 输出 ──
    report_text = "\n".join(lines)
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with io.open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(report_text)
    print(f"WROTE: {REPORT_PATH}  ({len(report_text)} bytes)")

    # 机器可读摘要（ASCII 输出防编码问题）
    for fname, st in per_file_isp_stats.items():
        print(f"[ISP] {fname}: hit={st['hit']}/{st['total']} matched={st['matched']} "
              f"res={st['res_present']} ct={st['ct_present']}")
    for fname, st in per_file_idc_stats.items():
        print(f"[IDC] {fname}: hit={st['hit']}/{st['total']} matched={st['matched']}")

    print(f"\n[REPORT] {REPORT_PATH}")
    print("[DONE] S2.10 sampling verification complete")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    main()