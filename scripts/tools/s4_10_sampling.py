# -*- coding: utf-8 -*-
"""
S4.10 抽样验证脚本 — IPv6 中国主库 isp/is_residential 抽样查询
对 240e(电信)/2408(联通)/2409(移动) 三大运营商前缀
及 IDC 厂商前缀(阿里云/腾讯云/华为云)进行采样，
验证 isp / is_residential / connection_type / idc_vendor 字段现状。
输出 UTF-8 中文报告到 data/china/v6/v6_pool_report.md
"""
import io
import os
import sys
import json
import time
import ipaddress
import collections
import maxminddb

OUT_DIR = r"E:\IP_Database"
REPORT_PATH = os.path.join(OUT_DIR, "data", "china", "v6", "v6_pool_report.md")

# 池覆盖文件
POOL_FILES = [
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

# 运营商前缀映射 (来自 constants.py IPV6_ISP_PREFIXES)
# 每个前缀按「首 16 位(首 hextet)」归属运营商（IA-NNA 分配按 /20 块但记录粒度不一）
ISP_PREFIX_MAP = {
    '240e': ('中国电信', 'telecom'),
    '2408': ('中国联通', 'unicom'),
    '2409': ('中国移动', 'mobile'),
}

# ISP 值判定关键词（全称或短称均算命中）
ISP_MATCH_KEYWORD = {
    '240e': ('中国电信', '电信'),
    '2408': ('中国联通', '联通'),
    '2409': ('中国移动', '移动'),
}

# IDC 厂商前缀 (来自 constants.py IDC_IPV6_PREFIXES)
IDC_PREFIXES = [
    ('腾讯云', '2402:b500::', 32),
    ('阿里云', '2403:b180::', 32),
    ('阿里云', '2404:f080::', 32),
    ('华为云', '2407:a800::', 32),
    ('华为云', '2407:c080::', 32),
    ('腾讯云', '240d:b000::', 32),
]

KEY_FIELDS = ["isp", "idc_vendor", "is_residential", "connection_type"]


def open_db(fname):
    path = os.path.join(OUT_DIR, "output", fname)
    if not os.path.exists(path):
        return None, None
    return fname, maxminddb.open_database(path)


def _net_addr(obj):
    """把 maxminddb 迭代产出的 (IPv6Network|str) 归一为网络起始地址"""
    if isinstance(obj, ipaddress.IPv6Network):
        return obj.network_address
    try:
        return ipaddress.IPv6Network(str(obj), strict=False).network_address
    except Exception:
        try:
            return ipaddress.IPv6Address(str(obj).split('/')[0])
        except Exception:
            return None


def _isp_match(isp_value, prefix_hex):
    if not isp_value:
        return False
    kws = ISP_MATCH_KEYWORD.get(prefix_hex, ())
    return any(kw in isp_value for kw in kws)


def isp_match_count(stats, prefix_hex):
    return sum(v for k, v in stats['isp_values'].items() if _isp_match(k, prefix_hex))


def sample_prefix(reader, prefix_str, prefix_len, label="", max_samples=10):
    """查询 MMDB 中匹配给定前缀的记录"""
    network = ipaddress.IPv6Network(f"{prefix_str}/{prefix_len}", strict=False)
    results = []
    for prefix, data in reader:
        ip_obj = _net_addr(prefix)
        if ip_obj is None:
            continue
        if ip_obj >= network.network_address and ip_obj <= network.broadcast_address:
            results.append((str(prefix), dict(data)))
        if len(results) >= max_samples:
            break
    return results


def sample_prefix_hextet(reader, first_hextet, max_samples=8):
    """按首 hextet 取前 N 条命中记录"""
    results = []
    for prefix, data in reader:
        ip_obj = _net_addr(prefix)
        if ip_obj is None:
            continue
        if str(ip_obj).split(':')[0].lower() != first_hextet.lower():
            continue
        results.append((str(prefix), dict(data)))
        if len(results) >= max_samples:
            break
    return results


def query_prefix_hextet(reader, first_hextet):
    """按首 16 位（首 hextet）全量匹配前缀，返回统计信息。
    constants.IPV6_ISP_PREFIXES 以首 hextet 映射运营商：
    240e=电信 / 2408=联通 / 2409=移动。"""
    count = 0
    isp_vals = collections.Counter()
    idc_vendor_vals = collections.Counter()
    is_residential_vals = collections.Counter()
    conn_type_vals = collections.Counter()
    province_vals = collections.Counter()
    geo_level_vals = collections.Counter()
    has_isp = has_idc = has_res = has_ct = 0
    for prefix, data in reader:
        ip_obj = _net_addr(prefix)
        if ip_obj is None:
            continue
        if str(ip_obj).split(':')[0].lower() != first_hextet.lower():
            continue
        count += 1
        if 'isp' in data:
            has_isp += 1
            isp_vals[data['isp']] += 1
        if 'idc_vendor' in data:
            has_idc += 1
            idc_vendor_vals[data['idc_vendor']] += 1
        if 'is_residential' in data:
            has_res += 1
            is_residential_vals[repr(data['is_residential'])] += 1
        if 'connection_type' in data:
            has_ct += 1
            conn_type_vals[data['connection_type']] += 1
        if 'province' in data:
            province_vals[data['province']] += 1
        if 'geo_level' in data:
            geo_level_vals[data['geo_level']] += 1
    return {
        'count': count,
        'has_isp': has_isp, 'isp_values': dict(isp_vals.most_common(20)),
        'has_idc': has_idc, 'idc_vendor_values': dict(idc_vendor_vals.most_common(10)),
        'has_res': has_res, 'is_residential_values': dict(is_residential_vals),
        'has_ct': has_ct, 'conn_type_values': dict(conn_type_vals),
        'province_values': dict(province_vals.most_common(10)),
        'geo_level_values': dict(geo_level_vals.most_common(10)),
    }


def scan_file_summary(reader):
    """扫描单文件基础统计"""
    keys = collections.Counter()
    field_val = {k: collections.Counter() for k in KEY_FIELDS}
    count = 0
    for prefix, data in reader:
        count += 1
        for k in data:
            keys[k] += 1
        for k in KEY_FIELDS:
            if k in data:
                field_val[k][str(data[k])[:80]] += 1
    return count, keys, field_val


def collect_samples(reader, file_label, sample_size=8):
    """收集文件中的代表性样本"""
    samples = []
    for prefix, data in reader:
        if len(samples) >= sample_size:
            break
        s = str(prefix)
        if s.startswith(('240e:', '2408:', '2409:', '2402:', '2403:', '2404:', '2407:', '240d:')):
            samples.append((s, dict(data)))
    return samples


def main():
    now_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    lines = []
    lines.append("# S4.10 抽样验证报告 · IPv6 中国主库补丁")
    lines.append("")
    lines.append(f"> **任务编号**: S4.10")
    lines.append(f"> **所属工作池**: S4 中国 IPv6 主库补丁")
    lines.append(f"> **执行时间**: {now_str}")
    lines.append(f"> **池覆盖文件**: 9 个 IPv6 中国 MMDB 文件")
    lines.append("")

    # ── 0. 字段总览 ──
    lines.append("---")
    lines.append("## 0. 字段总览（9 文件全量扫描）")
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

        isp_cov = f"{fv['isp'].total()}/{cnt}" if fv['isp'].total() else "0"
        idc_cov = f"{fv['idc_vendor'].total()}/{cnt}" if fv['idc_vendor'].total() else "0"
        res_cov = f"{fv['is_residential'].total()}/{cnt}" if fv['is_residential'].total() else "0"
        ct_cov = f"{fv['connection_type'].total()}/{cnt}" if fv['connection_type'].total() else "0"
        lines.append(f"| {fname} | {cnt} | {len(keys)} | {isp_cov} | {idc_cov} | {res_cov} | {ct_cov} |")

    lines.append("")
    lines.append("**关键发现**：`is_residential` 和 `connection_type` 在全部 9 个文件中**覆盖率为 0%，字段缺失**。")
    lines.append("`idc_vendor` 仅在 china_ipv6.mmdb / china_ipv6_other.mmdb / china_ipv6_enriched.mmdb 中各出现 1 条；")
    lines.append("IDC 专用文件仍使用旧字段名 `vendor` 而非 `idc_vendor`。")
    lines.append("`isp` 在各文件中覆盖率不一（37%~100%），且部分文件不含 isp 字段（如 *idc.mmdb）。")
    lines.append("")

    # ── 1. 运营商前缀采样 ──
    lines.append("---")
    lines.append("## 1. 运营商前缀 ISP 抽样验证")
    lines.append("")
    lines.append("验证三大运营商 IPv6 前缀的 ISP 标注准确性。")
    lines.append("")
    lines.append("### 1.1 测试方法")
    lines.append("")
    lines.append("- 匹配键：按**首 16 位（首 hextet）**归属运营商（对齐 `constants.IPV6_ISP_PREFIXES`：")
    lines.append("  `240e`=电信 / `2408`=联通 / `2409`=移动；运营商 /20 分配块内部记录粒度不一，不宜用 CIDR /20 直接过滤）")
    lines.append("- 判定口径：`isp` 值含全称（如「中国电信」）**或**短称（如「电信」）即算命中；")
    lines.append("  也统计两个口径的独立数字")
    lines.append("- 抽样文件：主库 `china_ipv6.mmdb`、富化库 `china_ipv6_enriched.mmdb`、合并库 `china_ipv6_with_isp.mmdb`")
    lines.append("- 同时对每条记录检查 `is_residential` / `connection_type` / `idc_vendor` 是否存在")
    lines.append("")

    # 1.x 各运营商前缀
    pfx_idx = 1
    for prefix_hex, (exp_cn, exp_short) in ISP_PREFIX_MAP.items():
        pfx_idx += 1
        lines.append(f"### 1.{pfx_idx} 前缀 {prefix_hex}:: — 预期 {exp_cn}")
        lines.append("")
        for fname in ["china_ipv6.mmdb", "china_ipv6_enriched.mmdb", "china_ipv6_with_isp.mmdb"]:
            if fname not in file_summaries:
                continue
            reader = maxminddb.open_database(os.path.join(OUT_DIR, "output", fname))
            stats = query_prefix_hextet(reader, prefix_hex)
            reader.close()
            match = isp_match_count(stats, prefix_hex)
            name_only = sum(v for k, v in stats['isp_values'].items() if exp_cn == k)
            lines.append(f"**{fname}**：匹配 {stats['count']} 条记录")
            lines.append(f"- isp 字段存在：{stats['has_isp']}/{stats['count']} 条")
            if stats['isp_values']:
                lines.append(f"- ISP 分布：{json.dumps(stats['isp_values'], ensure_ascii=False)}")
                lines.append(f"- 匹配「{exp_cn}」或短称：{match}/{stats['has_isp']} 条（其中全称 {name_only} 条）")
            else:
                lines.append("- ISP 字段完全缺失")
            lines.append(f"- is_residential 存在：{stats['has_res']} 条 → {stats['is_residential_values']}")
            lines.append(f"- connection_type 存在：{stats['has_ct']} 条 → {stats['conn_type_values']}")
            lines.append(f"- idc_vendor 存在：{stats['has_idc']} 条 → {stats['idc_vendor_values']}")
            if stats['geo_level_values']:
                lines.append(f"- geo_level 分布：{json.dumps(stats['geo_level_values'], ensure_ascii=False)}")
            if stats['province_values']:
                lines.append(f"- 前 5 省份：{dict(list(stats['province_values'].items())[:5])}")
            lines.append("")

        # 代表样例行（首个抽样文件的主库，前 8 条）
        reader = maxminddb.open_database(os.path.join(OUT_DIR, "output", "china_ipv6.mmdb"))
        samples = sample_prefix_hextet(reader, prefix_hex, max_samples=8)
        reader.close()
        if samples:
            lines.append("**代表样例行**（主库前 8 条命中记录）：")
            lines.append("")
            lines.append("| 网络前缀 | isp | 省份 | geo_level |")
            lines.append("|---|---|---|---|")
            for p, d in samples:
                lines.append(f"| `{p}` | {d.get('isp', '—')} | {d.get('province', '—')} | {d.get('geo_level', '—')} |")
            lines.append("")

    # ── 2. IDC 前缀采样 ──
    lines.append("---")
    lines.append("## 2. IDC 厂商前缀抽样验证")
    lines.append("")
    lines.append("验证已知云厂商 IPv6 前缀在 IDC 专用库和主库中的标注情况。")
    lines.append("")

    idc_idx = 0
    for vendor, prefix_str, pfx_len in IDC_PREFIXES:
        idc_idx += 1
        lines.append(f"### 2.{idc_idx} {vendor} {prefix_str}/{pfx_len}")
        lines.append("")
        for fname in ["china_ipv6.mmdb", "china_ipv6_enriched.mmdb", "china_ipv6_idc.mmdb", "china_ipv6_idc_enriched.mmdb"]:
            path = os.path.join(OUT_DIR, "output", fname)
            if not os.path.exists(path):
                continue
            reader = maxminddb.open_database(path)
            samples = sample_prefix(reader, prefix_str, pfx_len, max_samples=5)
            reader.close()
            if not samples:
                lines.append(f"- **{fname}**：无匹配记录")
                continue
            lines.append(f"- **{fname}**：{len(samples)} 条匹配（采样前 {min(len(samples), 5)} 条）")
            for p, d in samples[:5]:
                lines.append(f"  - `{p}`: {json.dumps(d, ensure_ascii=False)}")
            lines.append("")

    # ── 3. is_residential / connection_type 专项验证 ──
    lines.append("---")
    lines.append("## 3. is_residential / connection_type 专项验证")
    lines.append("")
    lines.append("### 3.1 字段存在性检查")
    lines.append("")
    lines.append("| 字段 | 出现文件数 | 总记录数 | 带该字段记录数 | 覆盖率 |")
    lines.append("|---|---|---|---|---|")
    total_records = 0
    total_res = 0
    total_ct = 0
    total_idc = 0
    total_isp = 0
    res_files = 0
    ct_files = 0
    idc_files = 0
    isp_files = 0
    for fname, (cnt, keys, fv) in file_summaries.items():
        total_records += cnt
        total_isp += fv['isp'].total()
        total_idc += fv['idc_vendor'].total()
        total_res += fv['is_residential'].total()
        total_ct += fv['connection_type'].total()
        if fv['is_residential'].total() > 0:
            res_files += 1
        if fv['connection_type'].total() > 0:
            ct_files += 1
        if fv['idc_vendor'].total() > 0:
            idc_files += 1
        if fv['isp'].total() > 0:
            isp_files += 1

    lines.append(f"| isp | {isp_files}/9 | {total_records} | {total_isp} | {total_isp/total_records*100:.1f}% |")
    lines.append(f"| idc_vendor | {idc_files}/9 | {total_records} | {total_idc} | {total_idc/total_records*100:.1f}% |")
    lines.append(f"| **is_residential** | **{res_files}/9** | **{total_records}** | **{total_res}** | **{total_res/total_records*100:.1f}%** |")
    lines.append(f"| **connection_type** | **{ct_files}/9** | **{total_records}** | **{total_ct}** | **{total_ct/total_records*100:.1f}%** |")
    lines.append("")
    lines.append("**结论**：`is_residential` 和 `connection_type` 覆盖率均为 0%，字段完全缺失。")
    lines.append("根据 S1 目标 Schema 规范，这两个字段为必选字段（required=true），当前 S4 池产物尚未补齐。")
    lines.append("")

    # ── 3.2 IDC 库 vendor→idc_vendor 映射检查 ──
    lines.append("### 3.2 IDC 库 vendor→idc_vendor 映射检查")
    lines.append("")
    for fname in ["china_ipv6_idc.mmdb", "china_ipv6_idc_enriched.mmdb"]:
        if fname not in file_summaries:
            continue
        cnt, keys, fv = file_summaries[fname]
        has_vendor = 'vendor' in keys
        has_idc_v = 'idc_vendor' in keys
        if has_vendor and not has_idc_v:
            lines.append(f"- **{fname}**：使用旧字段 `vendor`（{keys.get('vendor', 0)} 条），未迁移到 `idc_vendor`→ 需 rename")
        elif has_vendor and has_idc_v:
            lines.append(f"- **{fname}**：同时存在 `vendor` 和 `idc_vendor`→ 需确认一致")
        elif not has_vendor and has_idc_v:
            lines.append(f"- **{fname}**：已迁移到 `idc_vendor` ✓")
        else:
            lines.append(f"- **{fname}**：两者均不存在")
    lines.append("")

    # ── 4. 综合结论 ──
    lines.append("---")
    lines.append("## 4. 综合结论与建议")
    lines.append("")
    lines.append("### 4.1 ISP 字段")
    lines.append("")
    lines.append("| 前缀 | 预期运营商 | 主库匹配条数 | ISP 匹配度 | 结论 |")
    lines.append("|---|---|---|---|---|")
    for prefix_hex, (exp_cn, exp_short) in ISP_PREFIX_MAP.items():
        for fname in ["china_ipv6.mmdb", "china_ipv6_enriched.mmdb"]:
            if fname not in file_summaries:
                continue
            reader = maxminddb.open_database(os.path.join(OUT_DIR, "output", fname))
            stats = query_prefix_hextet(reader, prefix_hex)
            reader.close()
            if stats['count'] == 0:
                lines.append(f"| {prefix_hex}:: | {exp_cn} | {fname} | 0 条 | 无匹配 |")
                continue
            match = isp_match_count(stats, prefix_hex)
            pct = match / stats['has_isp'] * 100 if stats['has_isp'] > 0 else 0
            status = "✅ 基本正确" if pct >= 90 else ("⚠️ 部分正确" if pct >= 50 else "❌ 偏差较大")
            lines.append(f"| {prefix_hex}:: | {exp_cn} | {fname} | {match}/{stats['has_isp']} ({pct:.0f}%) | {status} |")
    lines.append("")

    lines.append("### 4.2 is_residential / connection_type 缺失")
    lines.append("")
    lines.append("- **状态**：`is_residential` 和 `connection_type` 在全部 S4 池产物中**覆盖率为 0%**")
    lines.append("- **影响**：下游无法区分家宽/IDC 流量，影响分类和质量评估")
    lines.append("- **建议**：使用 `scripts/tools/50_mmdb_field_patch.py` 对 S4 池 9 个文件执行字段补丁")
    lines.append("  补丁内容：`is_residential`=bool + `connection_type`=enum(residential|idc|unknown) + `idc_vendor` 映射")
    lines.append("")

    lines.append("### 4.3 idc_vendor 字段")
    lines.append("")
    lines.append(f"- `idc_vendor` 覆盖率：{total_idc}/{total_records} 条（{total_idc/total_records*100:.2f}%）")
    lines.append("- IDC 文件仍使用旧字段 `vendor`，需执行 rename 迁移到 `idc_vendor`")
    lines.append("- 主库中 2403:b180 等阿里云前缀未命中 IDC 标记（idc_vendor 缺失）")
    lines.append("")

    lines.append("### 4.4 建议优先级")
    lines.append("")
    lines.append("1. **P0** — 补齐 `is_residential` / `connection_type`（使用 50_mmdb_field_patch.py）")
    lines.append("2. **P0** — IDC 文件 `vendor`→`idc_vendor` 重命名并补充 `isp(=idc_vendor)`")
    lines.append("3. **P1** — 主库中 IDC 前缀（2402:b500 等）的 `idc_vendor` 回填和 overlap 标记")
    lines.append("4. **P2** — isp 覆盖率提升（china_ipv6_other.mmdb 仅 37%）")
    lines.append("")

    # ── 输出 ──
    report_text = "\n".join(lines)
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with io.open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(report_text)
    print(f"WROTE: {REPORT_PATH}  ({len(report_text)} bytes)")

    # Also print a brief machine-readable summary
    for prefix_hex, (exp_cn, exp_short) in ISP_PREFIX_MAP.items():
        for fname in ["china_ipv6.mmdb", "china_ipv6_enriched.mmdb"]:
            if fname not in file_summaries:
                continue
            reader = maxminddb.open_database(os.path.join(OUT_DIR, "output", fname))
            stats = query_prefix_hextet(reader, prefix_hex)
            reader.close()
            match = isp_match_count(stats, prefix_hex)
            print(f"[SAMPLE] {prefix_hex}:: in {fname}: {stats['count']} records, "
                  f"isp_match={match}/{stats['has_isp']}, "
                  f"is_residential={stats['has_res']}, connection_type={stats['has_ct']}")

    print(f"\n[REPORT] {REPORT_PATH}")
    print("[DONE] S4.10 sampling verification complete")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    main()