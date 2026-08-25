# -*- coding: utf-8 -*-
"""
S1.9 QA 测试用例设计器
======================
任务：根据 target_schema.json（S1.2）与 classification_rules.json（S1.3）设计可执行 QA 测试用例，
输出 data/audit/qa_test_cases.json。

覆盖五类可执行用例：
  1. field_completeness  字段完整性扫描（必选字段覆盖、文件级核心字段集合、键白名单、legacy 兼容键）
  2. residential_logic   家宽逻辑抽样（非 IDC ⇒ is_residential=true；IDC 命中 ⇒ false；residential 库重叠覆盖）
  3. idc_must_false      IDC 段必为 false（IDC 专用库全量断言；预过滤命中 ⇒ unknown）
  4. coordinate          坐标类型（float 归一化、数值范围、(0,0) 哨兵）
  5. random_query        随机查询健壮性（随机 IP、边界/特殊地址、文件可打开）
外加：value_validation（枚举/约束值校验）、regression（精度回归）两类支撑用例。

依赖产物（已存在）：
  - data/audit/target_schema.json
  - data/audit/classification_rules.json
  - data/audit/field_name_map.json（S1.6，提供不变量）
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
AUDIT_DIR = os.path.join(ROOT, "data", "audit")
OUT_PATH = os.path.join(AUDIT_DIR, "qa_test_cases.json")

# ---------------------------------------------------------------------------
# 1. 读取依赖产物
# ---------------------------------------------------------------------------
with open(os.path.join(AUDIT_DIR, "target_schema.json"), "r", encoding="utf-8") as f:
    TARGET = json.load(f)

with open(os.path.join(AUDIT_DIR, "classification_rules.json"), "r", encoding="utf-8") as f:
    RULES = json.load(f)

with open(os.path.join(AUDIT_DIR, "field_name_map.json"), "r", encoding="utf-8") as f:
    FIELDMAP = json.load(f)

ALL_FILES = [
    "china_ipv4.mmdb", "china_ipv4_telecom.mmdb", "china_ipv4_unicom.mmdb",
    "china_ipv4_mobile.mmdb", "china_ipv4_other.mmdb", "china_ipv4_high_prec.mmdb",
    "china_ipv4_high_prec_v2.mmdb", "china_ipv4_with_isp.mmdb",
    "china_ipv6.mmdb", "china_ipv6_enriched.mmdb", "china_ipv6_telecom.mmdb",
    "china_ipv6_unicom.mmdb", "china_ipv6_mobile.mmdb", "china_ipv6_other.mmdb",
    "china_ipv6_with_isp.mmdb",
    "china_ipv4_idc.mmdb", "china_ipv4_idc_enriched.mmdb",
    "china_ipv6_idc.mmdb", "china_ipv6_idc_enriched.mmdb",
    "global_ipv4_residential.mmdb", "global_ipv6_residential.mmdb",
    "global_ipv4_idc.mmdb", "global_ipv6_idc.mmdb",
]
GROUP_FILES = {
    g: FG["files"] for g, FG in TARGET["file_group_applicability"].items()
}
IDC_FILES = GROUP_FILES["china_idc"] + GROUP_FILES["global_idc"]
RES_FILES = GROUP_FILES["china_main"] + GROUP_FILES["global_residential"]
ALLOWED_CONN = RULES["conventions"]["connection_type_allowed_values"] \
    if "conventions" in RULES else TARGET["conventions"]["connection_type_allowed_values"]
ALLOWED_GEO = TARGET["conventions"]["geo_level_allowed_values"]

CASES = []


def add(cid, title, category, severity, description, method, pass_criteria,
        scope=None, sample_size=None, references=None):
    case = {
        "id": cid,
        "title": title,
        "category": category,
        "severity": severity,
        "description": description,
        "scope": scope if scope is not None else {"file_groups": list(GROUP_FILES.keys()),
                                                   "files": list(ALL_FILES)},
        "method": method,
        "pass_criteria": pass_criteria,
    }
    if sample_size is not None:
        case["sample_size"] = sample_size
    if references is not None:
        case["references"] = references
    CASES.append(case)


# ===========================================================================
# A. 字段完整性扫描 field_completeness（S10.1）
# ===========================================================================
add(
    "TC-F01",
    "必选字段全记录覆盖",
    "field_completeness",
    "P0",
    "按 target_schema.fields 中 required=true 的字段（is_residential, connection_type, "
    "country, geo_level）逐文件逐记录检查键存在且值非空。missing_value_policy 规定仅缺失字段省略键，"
    "因此 required 字段不允许省略。",
    [
        "遍历 output/ 下 23 个目标 MMDB（排除 tmp_v6.mmdb 测试残留）",
        "对每个文件的每条记录，检查 4 个必选键（is_residential/connection_type/country/geo_level）是否均存在",
        "统计缺失键记录数，按文件输出违规清单",
    ],
    [
        "每个文件 100% 记录的必选键齐全，缺失记录数 = 0",
        "country 值非空字符串；中国库为中文完整名称，全球库为 ISO 3166-1 alpha-2 大写（conventions.country_code_format）",
        "违规文件若存在（除 tmp_v6.mmdb）则整体 FAIL，阻断 S10 后续部署",
    ],
    sample_size=None,
    references={
        "target_schema": ["fields.is_residential", "fields.connection_type",
                          "fields.country", "fields.geo_level",
                          "conventions.missing_value_policy"],
        "plan": "S10.1 全库字段完整性扫描（20+ 文件）",
    },
)

add(
    "TC-F02",
    "文件级核心字段集合覆盖",
    "field_completeness",
    "P0",
    "按 target_schema.file_group_applicability 中各组 core_fields，检查每个文件的记录键并集（union）"
    "覆盖所在组核心字段（china_idc 组 notes 标注 division_code 可选，global_idc 组坐标/城市可选）。"
    "计划质量标准：每个文件的字段集合 ⊇ {isp, idc_vendor, is_residential, connection_type}。",
    [
        "按文件名映射到 file group（china_main / china_idc / global_residential / global_idc）",
        "对每组文件读取全部记录的键并集 union(keys)",
        "断言 union(keys) ⊇ 该组 core_fields（扣除 notes 明确标注的『可选』字段）",
    ],
    [
        "每个文件的 union(keys) ⊇ {is_residential, connection_type} 且 ≥ core_fields 必选子集",
        "每个文件 union(keys) ⊇ {isp, is_residential, connection_type}（字段名称规范后）",
        "idc_vendor 至少在一个文件内出现（IDC 段存在标记可查）",
        "字段名规范化后，未知键数 = 0（见 TC-F03）",
    ],
    references={
        "target_schema": ["file_group_applicability", "fields.isp", "fields.idc_vendor"],
        "plan": "S10.1 全库字段完整性扫描（20+ 文件）；质量标准：字段集合 ⊇ {isp, idc_vendor, is_residential, connection_type}",
    },
)

add(
    "TC-F03",
    "记录键白名单检查",
    "field_completeness",
    "P1",
    "字段名规范化后，不允许出现目标字段集之外的未知键。允许保留的兼容键为 "
    "{source, start_ip, end_ip, start_ip_int, end_ip_int, start_ip_hex, end_ip_hex, "
    "region, vendor, type}（field_name_map.invariant_4）。防拼写错误（如 isResidential / ConnectionType）。",
    [
        "遍历全部记录键，与白名单（target_schema.fields 名 ∪ legacy/兼容键集）比对",
        "收集未知键及出现次数，列出样例记录",
    ],
    [
        "未知键命中记录数 = 0",
        "发现未知键时输出样本（IP + 未知键 + 值）便于定位补丁遗漏",
    ],
    references={
        "target_schema": ["fields"],
        "field_name_map": ["validation.invariant_4"],
        "plan": "S10.1",
    },
)

add(
    "TC-F04",
    "legacy 兼容键保留",
    "field_completeness",
    "P2",
    "vendor / type / source 为 legacy 键，补丁后按 field_name_map 策略保留作兼容键 "
    "（vendor→idc_vendor 后保留 vendor，type[idc]→connection_type[idc] 后保留 type，source 原样保留），"
    "保证旧查询兼容。",
    [
        "对 6 个含 vendor 的 IDC 库断言 vendor 键仍存在，且值可由 idc_vendor 校验",
        "对 2 个含 type='idc' 的全球 IDC 库断言 type 键仍存在，且与 connection_type 值一致",
        "对 9 个含 source 的文件断言 source 键仍存在且值非空",
    ],
    [
        "含 legacy 键的文件补丁后该键保留（invariant_1 无键丢失）",
        "vendor 值 == idc_vendor 值（存在时）；type 值 == connection_type 值（存在时）",
    ],
    references={
        "field_name_map": ["validation.invariant_1", "field_map.vendor", "field_map.type", "field_map.source"],
        "target_schema": ["legacy_field_map"],
    },
)

# ===========================================================================
# B. 家宽逻辑抽样 residential_logic（S10.2）
# ===========================================================================
add(
    "TC-R01",
    "家宽逻辑抽样：非 IDC ⇒ is_residential=true",
    "residential_logic",
    "P0",
    "对 china_main 与 global_residential 组库随机抽样，凡通过预过滤器且未命中任何 IDC 范围的记录，"
    "按规则链 R5/R2 必须 is_residential=true 且 connection_type=residential。"
    "判定采用 classification_rules.execution_contract 复算：pre_filter → IDC match（source 优先级链）→ 规则输出。",
    [
        "对 17 个 residential 组库（china_main 15 + global_residential 2）每库随机抽样 1000 条有效命中记录",
        "对每条记录：ip 解析 → 预过滤检查（PF_RFC1918 等 9 条）→ IDC 源匹配（SRC_IDC_CSV → SRC_CONSTANTS_V4/V6）",
        "未命中 IDC 且通过预过滤者，断言 is_residential=true 且 connection_type=residential",
    ],
    [
        "抽样 17000 条中『非 IDC ⇒ true』符合率 100%（0 条违规）",
        "抽样覆盖中国 v4/v6 与全球 v4/v6、多个 ISP 段（telecom/unicom/mobile/other 至少各 1 库）",
        "违规记录输出（IP、命中源、实际值、期望值）便于追踪",
    ],
    sample_size={"per_file": 1000, "total": 17000},
    references={
        "classification_rules": ["R2", "R5", "execution_contract", "pre_filters", "idc_sources"],
        "plan": "S10.2 家宽逻辑验证（抽样：IDC⇒false，非IDC⇒true）；质量标准：家宽逻辑抽样 1000 条 100% 符合",
    },
)

add(
    "TC-R02",
    "家宽逻辑抽样：IDC 命中 ⇒ is_residential=false",
    "residential_logic",
    "P0",
    "使用 classification_rules.examples 及 IDC 源内已知厂商段构造正例（如 47.96.0.1 阿里云、52.219.170.1 AWS、"
    "2403:b180::1 阿里云 IPv6），对 china_main / global_residential / china_idc / global_idc 任意库命中即断言 "
    "is_residential=false、connection_type=idc、idc_vendor=具体厂商（不得为聚合别名 cn_cloud_ipv6，"
    "须经 vendor_alias 还原）。",
    [
        "从 SRC_IDC_CSV（vendor ∈ 白名单）随机抽 50 个 IPv4 + 20 个 IPv6 CIDR 内取 IP",
        "从 SRC_CONSTANTS_V4 抽 20 个范围、SRC_CONSTANTS_V6 抽全部 6 个前缀内取 IP",
        "对每条 IP 在各库查询并断言输出与执行契约 Step3 一致",
    ],
    [
        "命中记录 100% 满足 is_residential=false 且 connection_type=idc",
        "idc_vendor 等于期望厂商名；csv 命中 cn_cloud_ipv6 的前缀须还原为 constants 具体厂商（R1 vendor_alias_resolution）",
        "覆盖 阿里云/腾讯云/华为云/百度云/京东云/AWS/Azure/GCP 至少各 1 条正例",
    ],
    sample_size={"idc_positive": 90},
    references={
        "classification_rules": ["R1", "examples", "conflict_resolution.vendor_alias"],
        "plan": "S10.2 / S10.7 IDC 分类准确率评测（云厂商 IP）",
    },
)

add(
    "TC-R05",
    "residential 库内 IDC 重叠段必为 false",
    "residential_logic",
    "P1",
    "global_residential（及 china_main）库中命中 IDC 范围的记录，R5 文件级默认 true 必须被 R1 覆盖为 "
    "is_residential=false、connection_type=idc。此类重叠同时按 classification_rules.residential_vs_idc "
    "生成重叠量报告（数据质量观察项，不单独判失败）。",
    [
        "对 2 个 global_residential 库全量扫描，标记命中 IDC 范围（SRC_IDC_CSV）的记录",
        "断言重叠记录字段值；汇总重叠记录数与比例",
    ],
    [
        "重叠记录 100% 满足 is_residential=false 且 connection_type=idc（0 条漏标）",
        "输出重叠量报告（数量/占比/前 10 个厂商分布）供 S6/S8 数据质量评估",
    ],
    references={
        "classification_rules": ["R1", "R5", "conflict_resolution.residential_vs_idc"],
        "plan": "S10.2；conflict_resolution.residential_vs_idc.qa_alert=true",
    },
)

# ===========================================================================
# C. IDC 段必为 false idc_must_false
# ===========================================================================
add(
    "TC-R03",
    "IDC 专用库全量断言：is_residential=false",
    "idc_must_false",
    "P0",
    "china_idc 4 库 + global_idc 2 库为 IDC 专用库，R4 文件级覆盖要求 100% 记录 "
    "is_residential=false 且 connection_type=idc，无论 IP 是否在 IDC 范围内。"
    "同时校验 invariant_2：idc_vendor 存在时 isp == idc_vendor。",
    [
        "对 6 个 IDC 库全记录扫描",
        "断言每条记录 is_residential == false 且 connection_type == 'idc'",
        "存在 idc_vendor 键的记录，断言 isp == idc_vendor（coverage 规则：IDC 库 isp = idc_vendor）",
    ],
    [
        "6 库 100% 记录满足 is_residential=false 且 connection_type=idc（违规数 = 0）",
        "含 idc_vendor 的记录 isp == idc_vendor（invariant_2）",
        "geo_level 应为 'datacenter'（target_schema.default_fill；global_idc core_fields 要求）",
    ],
    references={
        "classification_rules": ["R4", "apply_to_file_groups.china_idc", "apply_to_file_groups.global_idc"],
        "target_schema": ["file_group_applicability.china_idc", "file_group_applicability.global_idc",
                          "fields.geo_level.default_fill"],
        "field_name_map": ["validation.invariant_2"],
        "plan": "S10.2",
    },
)

add(
    "TC-R04",
    "预过滤命中 ⇒ connection_type=unknown",
    "idc_must_false",
    "P1",
    "私有/保留/组播/ULA 等 9 条预过滤器（PF_RFC1918/PF_CGNAT/PF_LOOPBACK/PF_LINKLOCAL/PF_RESERVED/"
    "PF_MULTICAST/PF_IPV6_ULA/PF_IPV6_LL/PF_IPV6_RESERVED）命中时不参与 IDC/住宅分类，"
    "connection_type 必须为 unknown。典型样本：10.0.0.1、172.16.1.1、192.168.1.1、100.64.0.1、"
    "127.0.0.1、169.254.0.1、224.0.0.1、fd00::1、fe80::1、2001:db8::1。",
    [
        "构造上述预过滤命中样本 IP 列表",
        "对全部 23 库查询（记录可能存在也可能不存在——私有地址不应出现在公开库中）",
        "凡存在命中记录的，断言 connection_type == 'unknown'",
    ],
    [
        "命中记录 100% connection_type=unknown（R3 输出）",
        "0 条预过滤地址被标记为 residential 或 idc（若此类地址出现即数据污染告警）",
    ],
    references={
        "classification_rules": ["R3", "pre_filters"],
        "plan": "S10.2",
    },
)

# ===========================================================================
# D. 坐标类型 coordinate（S10.4）
# ===========================================================================
add(
    "TC-C01",
    "坐标字段类型归一化：latitude/longitude 必须为 float",
    "coordinate",
    "P0",
    "target_schema.conventions.coordinate_precision：WGS-84，float 6 位小数。"
    "china_ipv4_with_isp 与 global_ipv4_residential 曾为 str 类型，须归一化；"
    "全库含坐标键的记录一律不得为 str/int。",
    [
        "遍历全部记录，凡存在 latitude / longitude 键的，断言其类型为 float",
        "重点核查 type_normalize_required 标注的两个文件（china_ipv4_with_isp, global_ipv4_residential）",
        "统计 str 类型违规记录数",
    ],
    [
        "含坐标键的记录 100% 类型为 float（str/int 违规数 = 0）",
        "float 精度保留 6 位小数（值序列化为 6 位小数等价，比较时容差 1e-6）",
    ],
    references={
        "target_schema": ["conventions.coordinate_system", "conventions.coordinate_precision",
                          "fields.latitude", "fields.longitude"],
        "field_name_map": ["identity_fields.type_normalize_required"],
        "plan": "S10.4 坐标类型一致性检查；质量标准：坐标字段全部为 float",
    },
)

add(
    "TC-C02",
    "坐标数值范围与 (0,0) 哨兵检查",
    "coordinate",
    "P1",
    "latitude ∈ [-90, 90]，longitude ∈ [-180, 180]，WGS-84。"
    "（0,0）为无效哨兵（几内亚湾），仅允许出现在 geo_level='unknown' 或需单独上报说明来源。",
    [
        "对含坐标的记录断言 lat/lng 在合法范围内",
        "标记 (0,0) 记录，输出清单（IP、geo_level、所属文件）",
    ],
    [
        "越界记录数 = 0",
        "(0,0) 记录数输出报告（允许白名单化：仅 geo_level='unknown' 或已说明的数据源）",
    ],
    references={
        "target_schema": ["conventions.latitude_range", "conventions.longitude_range", "fields.latitude", "fields.longitude"],
        "plan": "S10.4",
    },
)

# ===========================================================================
# E. 值域/枚举校验 value_validation
# ===========================================================================
add(
    "TC-T01",
    "枚举与约束值校验",
    "value_validation",
    "P0",
    "对全部记录校验：connection_type ∈ {residential, idc, unknown}；is_residential ∈ {true, false}（布尔型）；"
    "geo_level ∈ {district, city, province, admin_center, datacenter, unknown}；division_code 匹配 ^\\d{6}$；"
    "accuracy_radius 为整数 ≥ 0；confidence 为 float 且 ∈ [0,1]。",
    [
        "遍历全部记录按字段规则断言（仅对存在的键校验，缺失键按 missing_value_policy 允许）",
        "is_residential 类型断言为 bool（不得为字符串 'true'/'false'）",
        "confidence 类型断言为 number（曾为 str 的 global_ipv4_residential 已归一化）",
    ],
    [
        "各枚举字段违规记录数 = 0",
        "is_residential 非 bool 违规数 = 0；confidence 非 number 或越界违规数 = 0",
        "division_code 存在时 100% 匹配 ^\\d{6}$；accuracy_radius 存在时 100% int ≥ 0",
    ],
    references={
        "target_schema": ["conventions.connection_type_allowed_values",
                          "conventions.geo_level_allowed_values",
                          "fields.confidence.constraints", "fields.accuracy_radius.constraints",
                          "fields.division_code.constraints"],
        "plan": "S10.x 值约束",
    },
)

add(
    "TC-T02",
    "division_code 合法性（GB/T 2260 省级前缀）",
    "value_validation",
    "P2",
    "中国库 division_code 为 6 位 GB/T 2260 行政区划码，前 2 位必须属于合法省级码集合"
    "（11/12/13/14/15/21/22/23/31/32/33/34/35/36/37/41/42/43/44/45/46/50/51/52/53/54/61/62/63/64/65/71/81/82）。",
    [
        "抽取含 division_code 的记录（抽样每库 ≤ 2000）",
        "断言 ^\\d{6}$ 且前 2 位 ∈ 合法省级码集合",
        "存在 province 字段时抽查前 2 位与省份对应关系（GB/T 2260 映射表）",
    ],
    [
        "division_code 格式与省级前缀合法率 = 100%",
        "province 与 division_code 前 2 位对应抽查一致率 ≥ 99%（允许历史数据异常白名单）",
    ],
    sample_size={"per_file": 2000},
    references={
        "target_schema": ["fields.division_code", "conventions.division_code_format"],
        "plan": "S10.x",
    },
)

# ===========================================================================
# F. 随机查询 random_query
# ===========================================================================
add(
    "TC-Q01",
    "随机 IP 查询健壮性",
    "random_query",
    "P0",
    "以 maxminddb 打开各库随机查询（含随机 IPv4/IPv6 与库里未覆盖地址），查询不得抛异常；"
    "未覆盖地址返回 None 属正常。模拟真实使用方随机查询负载。",
    [
        "对每个文件随机生成 500 个与库族匹配的 IP（IPv4 库用随机 v4，IPv6 库用随机 v6）",
        "调用 maxminddb.Reader.get(ip)（或等价查询函数），捕获异常",
        "统计异常数与耗时（可选基准）",
    ],
    [
        "23 库 × 500 随机查询异常数 = 0（None 返回值不算异常）",
        "文件可被 maxminddb 正常打开（open_database 不抛错）",
        "查询耗时均值 < 1ms（可选性能基线，P2 观察项）",
    ],
    sample_size={"per_file": 500, "total": 11500},
    references={
        "plan": "S10.x；质量标准：文件可被 maxminddb 正常打开且随机查询无异常",
    },
)

add(
    "TC-Q02",
    "边界与特殊地址查询",
    "random_query",
    "P1",
    "对边界及特殊地址执行查询（0.0.0.0、255.255.255.255、127.0.0.1、10.255.255.255、"
    "::、::1、fe80::1、2001:db8::1、2403:b180::ffff 等），保证查询 API 对任何输入都健壮。",
    [
        "构造边界地址列表（v4 最小/最大/私有/组播；v6 未指定/回环/ULA/LL/文档前缀）",
        "对每个文件逐一查询并断言无异常",
    ],
    [
        "边界地址查询异常数 = 0",
        "返回结果（若有）不引发类型解析错误（如地址串字段与 schema 类型一致）",
    ],
    references={
        "classification_rules": ["pre_filters", "PF_IPV6_RESERVED"],
        "plan": "S10.x",
    },
)

add(
    "TC-Q03",
    "MMDB 文件完整性打开检查（23 库）",
    "random_query",
    "P2",
    "全部 23 个目标文件可被 maxminddb 完整打开并读取 metadata（ip_version / node_count / "
    "record_size / build_epoch / languages 等），排除 tmp_v6.mmdb 测试残留。",
    [
        "对 23 个目标文件逐个 maxminddb.open_database + reader.metadata()",
        "记录 metadata 摘要（ip_version、node_count、build_epoch）",
        "断言 tmp_v6.mmdb 不参与任何 QA 统计",
    ],
    [
        "23/23 文件打开成功且 metadata 可读",
        "输出每库 ip_version 与记录数摘要，供 S10.10 终审报告引用",
    ],
    references={
        "plan": "S10.1；target_schema.apply_to：全部 output/*.mmdb（23 个已扫描文件，排除 tmp_v6.mmdb）",
    },
)

# ===========================================================================
# G. 回归 regression（S10.3）
# ===========================================================================
add(
    "TC-P01",
    "补丁后精度回归：无回退",
    "regression",
    "P0",
    "补丁（S2~S9）不得降低地理精度：对补丁后各库运行 evaluate_precision.py（锚点集），"
    "province/city 一致率与坐标中位距离须不劣于补丁前基线。",
    [
        "保存补丁前基线：evaluate_precision.py 输出（province/city 一致率、中位距离 km）",
        "补丁完成后重跑同一评测（相同锚点输入与随机种子）",
        "逐库对比前后指标",
    ],
    [
        "每库 province/city 一致率 ≥ 补丁前基线（允许 ±0.5% 抽样波动，严禁系统性回退）",
        "坐标中位距离不劣于补丁前（无精度劣化）",
        "产出前后对比表写入审计报告（S10.10）",
    ],
    references={
        "plan": "S10.3 回归精度评测（evaluate_precision.py 前后对比）；质量标准：重建后 QA 精度不低于重建前（province/city 一致率 ± 无回退）",
    },
)

# ---------------------------------------------------------------------------
# 2. 组装并写出
# ---------------------------------------------------------------------------
assert len(CASES) >= 10, "测试用例数量必须 ≥ 10"

payload = {
    "schema_info": {
        "task": "S1.9 QA Test Case Designer",
        "created_at": "2026-08-24T09:00:00+00:00",
        "schema_version": "1.0",
        "inputs": [
            "data/audit/target_schema.json",
            "data/audit/classification_rules.json",
            "data/audit/field_name_map.json",
        ],
        "apply_to": "全部 output/*.mmdb（23 个目标文件，排除 tmp_v6.mmdb 测试残留）",
        "execution_phase": "S10（整体 QA 验证），用例在 S2~S9 补丁完成后执行",
        "purpose": "将 target_schema 与 classification_rules 固化为可执行 QA 测试用例，覆盖字段完整性、"
                   "家宽逻辑、IDC 段约束、坐标类型与随机查询五类核心检查，作为 S10.1~S10.10 的执行清单",
    },
    "test_case_count": len(CASES),
    "category_summary": {
        "field_completeness": len([c for c in CASES if c["category"] == "field_completeness"]),
        "residential_logic": len([c for c in CASES if c["category"] == "residential_logic"]),
        "idc_must_false": len([c for c in CASES if c["category"] == "idc_must_false"]),
        "coordinate": len([c for c in CASES if c["category"] == "coordinate"]),
        "value_validation": len([c for c in CASES if c["category"] == "value_validation"]),
        "random_query": len([c for c in CASES if c["category"] == "random_query"]),
        "regression": len([c for c in CASES if c["category"] == "regression"]),
    },
    "cases": CASES,
    "execution_notes": [
        "执行前置：S2~S9 字段补丁已完成（is_residential/connection_type/idc_vendor/district 等已写入）",
        "判定引擎：tests 逻辑可由 scripts/tools/50_mmdb_field_patch.py 的只读校验模式或独立 runner 实现",
        "复算依赖：classification_rules.execution_contract（pre_filter → source 优先级链 → R1/R2/R3 输出）",
        "样本随机性：随机抽样须固定随机种子以保障结果可复现",
        "tmp_v6.mmdb 为测试残留，绝不参与任何用例",
    ],
}

with open(OUT_PATH, "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False, indent=2)
    f.write("\n")

print("written:", OUT_PATH)
print("cases:", len(CASES))