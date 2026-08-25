# MMDB 字段补齐与家宽 IP 分类 · 完整执行计划

> 目标：检查并更新**所有数据库（中国库 + 全球库）**，补齐 **ISP 字段**、**IDC 字段**，并新增**家宽 IP 判断字段**
> 判断逻辑：**非 IDC 数据中心 IP ⇒ 归属为家宽 IP（is_residential = true）**
> 方法：10 个一级子代理 × 每个嵌套 10 个二级子代理 = 100 子代理协同执行
> 技能：engineering-data-engineer、gis-spatial-data-engineer、engineering-database-optimizer、gis-qa-engineer、engineering-software-architect

---

## 0. 现状审计结论（2026-08-24 实测全部 MMDB 文件）

### 0.1 中国库 (12 个文件)

| 文件 | isp 字段 | idc_vendor 字段 | is_residential 家宽字段 |
|---|---|---|---|
| `china_ipv4.mmdb` | ✅ 部分缺失 | ✅ 部分缺失 | ❌ 缺失 |
| `china_ipv4_telecom/unicom/mobile/other.mmdb` | ✅ 基本有 | ⚠️ 部分有 | ❌ 缺失 |
| `china_ipv4_with_isp.mmdb` | ✅ | ❌ 缺失 | ❌ 缺失 |
| `china_ipv4_high_prec.mmdb` / `_v2` | ❌ **完全缺失** | ❌ 完全缺失 | ❌ 缺失 |
| `china_ipv4_idc.mmdb` | ❌ 缺失 | ⚠️ 名为 `vendor` | ❌ 缺失 |
| `china_ipv4_idc_enriched.mmdb` | ❌ 缺失 | ⚠️ 名为 `vendor` | ❌ 缺失 |
| `china_ipv6.mmdb` / `_enriched` | ✅ 部分缺失 | ✅ 部分缺失 | ❌ 缺失 |
| `china_ipv6_telecom/unicom/mobile/other.mmdb` | ✅ 基本有 | ⚠️ 部分 | ❌ 缺失 |
| `china_ipv6_with_isp.mmdb` | ✅ | ❌ 缺失 | ❌ 缺失 |
| `china_ipv6_idc.mmdb` | ❌ 缺失 | ⚠️ 名为 `vendor` | ❌ 缺失 |
| `china_ipv6_idc_enriched.mmdb` | ❌ 缺失 | ⚠️ 名为 `vendor` | ❌ 缺失 |

### 0.2 全球库 (4 个文件)

| 文件 | isp 字段 | idc_vendor/type 字段 | is_residential 家宽字段 |
|---|---|---|---|
| `global_ipv4_residential.mmdb` | ❌ **完全缺失** | ❌ 完全缺失 | ❌ 缺失 |
| `global_ipv4_idc.mmdb` | ❌ 缺失 | ✅ type='idc', vendor, source | ❌ 缺失 |
| `global_ipv6_residential.mmdb` | ❌ **完全缺失** | ❌ 完全缺失 | ❌ 缺失 |
| `global_ipv6_idc.mmdb` | ❌ 缺失 | ✅ type='idc', vendor, source | ❌ 缺失 |

### 0.3 发现的共性问题

1. **全部 20 个文件均无 `is_residential`（家宽判断）字段** —— 家宽/IDC 只能靠文件名隐式区分。
2. **全球 residential 库** 连 isp、idc_vendor 都没有（只有 country/region/city/lat/lng/confidence/source）。
3. **中国 high_prec 库**（web 端主用）isp / idc_vendor 完全缺失，且 lat/lng 为字符串类型。
4. **IDC 库字段名不统一**：`vendor` 应统一补充 `isp`、`idc_vendor` 双字段。
5. **坐标类型不一致**：部分文件 lat/lng 为 str（如 `"-27.4767"`），需归一为 float。
6. **tmp_v6.mmdb** 为测试残留，应排除处理。

### 0.4 目标统一 Schema（所有 MMDB 生效）

```
isp:               string  运营商名称（"中国电信"/"Vodafone"/云厂商名兜底）
idc_vendor:        string  IDC/云厂商标记（非 IDC 段缺省或空）
is_residential:    bool    家宽判断：true=家宽/非IDC，false=IDC
connection_type:   string  residential | idc | unknown
confidence:        float   置信度（保留现有）
accuracy_radius:   int     精度半径（保留现有）
country/region/city/province/district/division_code/lat/lng/geo_level: 保留现有
```

---

## 1. 执行架构：10 个一级子代理 × 10 个二级子代理

```
                ┌────────────────────────────────────────────┐
                │  Orchestrator（本会话）                       │
                │  计划编写 · Skill 加载 · 派发 · 汇总          │
                └────────────────────────────────────────────┘
    ┌───────┬───────┬───────┬───────┬───────┬───────┬───────┬───────┬───────┐
    ▼       ▼       ▼       ▼       ▼       ▼       ▼       ▼       ▼       ▼
  S1审计   S2中国v4 S3中国v4 S4中国v6 S5中国v6 S6全球v4 S7全球v4 S8全球v6 S9全球v6 S10QA
  基座     主库     IDC库   主库     IDC库   住宅库   IDC库   住宅库   IDC库   验证部署
    │       │       │       │       │       │       │       │       │       │
  10个     10个     10个     10个     10个     10个     10个     10个     10个     10个
  二级     二级     二级     二级     二级     二级     二级     二级     二级     二级
```

---

## 2. 一级子代理详表

### S1：Schema 规范与审计基座（先行）

**技能**：engineering-software-architect、engineering-database-optimizer
**产出**：`data/audit/field_inventory.json`、`data/audit/target_schema.json`、`scripts/tools/50_mmdb_field_patch.py`（统一补丁工具库）

| 嵌套 | 任务 | 输入 | 输出 |
|---|---|---|---|
| S1.1 | 字段清单盘点器 | 全部 MMDB | `data/audit/field_inventory.json` |
| S1.2 | 目标 Schema 定义器 | S1.1 + 需求 | `data/audit/target_schema.json` |
| S1.3 | 分类逻辑规则器 | 需求 | `data/audit/classification_rules.json`（非IDC⇒家宽） |
| S1.4 | 字段差异分析器 | S1.1 vs S1.2 | `data/audit/field_gap_report.csv` |
| S1.5 | 修复优先级排序器 | S1.4 | `data/audit/repair_priority.json` |
| S1.6 | 字段名映射表 | S1.2 | vendor→idc_vendor 等映射 |
| S1.7 | 补丁工具库 base | mmdb_writer | `scripts/tools/50_mmdb_field_patch.py` |
| S1.8 | 数据源亲和性分析 | 现有源字段 | `data/audit/source_field_affinity.csv` |
| S1.9 | QA 测试用例设计器 | S1.2 | `data/audit/qa_test_cases.json` |
| S1.10 | 审计报告终稿 | 全部 | `data/audit/audit_final_report.md` |

### S2：中国 IPv4 主库补丁（S2.1~S2.10）

**技能**：engineering-data-engineer、gis-spatial-data-engineer
**覆盖文件**：`china_ipv4.mmdb`、`china_ipv4_{telecom,unicom,mobile,other}.mmdb`、`china_ipv4_with_isp.mmdb`、`china_ipv4_high_prec(_v2).mmdb`

| 嵌套 | 任务 |
|---|---|
| S2.1 | v4 主库 isp 缺失分析（gap 清单） |
| S2.2 | ip2region org 列 isp 回填 |
| S2.3 | ISP 关键词归类（telecom/unicom/mobile/system） |
| S2.4 | idc_vendor 回填（constants.IDC_IPV4_RANGES 匹配） |
| S2.5 | is_residential 计算（非 IDC ⇒ true） |
| S2.6 | connection_type 赋值 |
| S2.7 | high_prec 库补 isp/idc_vendor（fused_v2 回填） |
| S2.8 | 坐标 str→float 归一化 |
| S2.9 | MMDB 重建（50_mmdb_field_patch.py） |
| S2.10 | 抽样验证 + 报告 |

### S3：中国 IPv4 IDC 库补丁（S3.1~S3.10）

**覆盖文件**：`china_ipv4_idc.mmdb`、`china_ipv4_idc_enriched.mmdb`

| 嵌套 | 任务 |
|---|---|
| S3.1 | Schema 审计（vendor/start/end/region） |
| S3.2 | isp = vendor（IDC 运营商即云厂商名） |
| S3.3 | idc_vendor = vendor（统一命名） |
| S3.4 | is_residential = false（IDC 段） |
| S3.5 | connection_type = 'idc' |
| S3.6 | enriched 库同步补字段 |
| S3.7 | geo_level='datacenter' 校对 |
| S3.8 | MMDB 重建 |
| S3.9 | 与中国 v6 IDC 一致性校验 |
| S3.10 | 完整性报告 |

### S4：中国 IPv6 主库补丁（S4.1~S4.10）

**覆盖文件**：`china_ipv6.mmdb`、`china_ipv6_{telecom,unicom,mobile,other}.mmdb`、`china_ipv6_with_isp.mmdb`、`china_ipv6_enriched.mmdb`

| 嵌套 | 任务 |
|---|---|
| S4.1 | v6 主库 isp 缺失分析 |
| S4.2 | ip2region v6 org 回填 |
| S4.3 | 前缀推断（240e→telecom, 2409→mobile, 2408→unicom） |
| S4.4 | idc_vendor 回填（IDC_IPV6_PREFIXES 匹配） |
| S4.5 | is_residential 计算 |
| S4.6 | connection_type 赋值 |
| S4.7 | with_isp / enriched 库同步 |
| S4.8 | 坐标归一化 |
| S4.9 | MMDB 重建 |
| S4.10 | 抽样验证 |

### S5：中国 IPv6 IDC 库补丁（S5.1~S5.10）

**覆盖文件**：`china_ipv6_idc.mmdb`、`china_ipv6_idc_enriched.mmdb`
**任务**：与 S3 同构 —— 字段审计 → isp=vendor → idc_vendor=vendor → is_residential=false → connection_type='idc' → enriched 同步 → geo_level 校对 → MMDB 重建 → 与 v4 交叉校验 → 报告。

### S6：全球 IPv4 住宅库补丁（S6.1~S6.10）

**覆盖文件**：`global_ipv4_residential.mmdb`（67MB，约 200 万记录）

| 嵌套 | 任务 |
|---|---|
| S6.1 | 字段审计（确认无 isp/idc_vendor/is_residential） |
| S6.2 | 关联 classification.csv（classification 字段） |
| S6.3 | ISP 字段生成（ip2region org + ASN 关键字） |
| S6.4 | idc_vendor 匹配（idc_all.csv 重叠检测） |
| S6.5 | is_residential = true（住宅库全量 + 补丁 hit 校验） |
| S6.6 | connection_type = 'residential' |
| S6.7 | lat/lng str→float 修复 |
| S6.8 | 分块 MMDB 重建（内存控制） |
| S6.9 | 大文件字段一致性检查 |
| S6.10 | 大小/性能回归报告 |

### S7：全球 IPv4 IDC 库补丁（S7.1~S7.10）

**覆盖文件**：`global_ipv4_idc.mmdb`
**任务**：字段审计 → isp=vendor → idc_vendor=vendor → is_residential=false → connection_type='idc' → 补充坐标/region → geo_level='datacenter' → MMDB 重建 → 与住宅库重叠检测（应 0 重叠）→ 报告。

### S8：全球 IPv6 住宅库补丁（S8.1~S8.10）

**覆盖文件**：`global_ipv6_residential.mmdb`（55MB）
**任务**：字段审计（当前仅有 country/region/city/source）→ 关联分类 → ISP 生成 → idc_vendor 匹配 → is_residential=true → connection_type 赋值 → 坐标补充（fused 数据）→ 分块重建 → 一致性检查 → 性能报告。

### S9：全球 IPv6 IDC 库补丁（S9.1~S9.10）

**覆盖文件**：`global_ipv6_idc.mmdb`
**任务**：与 S7 同构 → 最终"四库（v4/v6 × 住宅/IDC）字段完全对齐"校验。

### S10：整体 QA 验证与部署（收尾，依赖 S2~S9）

**技能**：gis-qa-engineer、engineering-data-engineer

| 嵌套 | 任务 |
|---|---|
| S10.1 | 全库字段完整性扫描（20+ 文件） |
| S10.2 | 家宽逻辑验证（抽样：IDC⇒false，非IDC⇒true） |
| S10.3 | 回归精度评测（`evaluate_precision.py` 前后对比） |
| S10.4 | 坐标类型一致性检查 |
| S10.5 | 全球 QA 评测对比 |
| S10.6 | ISP 字段准确率评测（锚点） |
| S10.7 | IDC 分类准确率评测（云厂商 IP） |
| S10.8 | 部署脚本更新（`build_outputs.ps1`/`deploy_isp.ps1`） |
| S10.9 | 文档更新（README/docs Schema 说明） |
| S10.10 | 最终审计报告 `data/audit/final_audit_report.md` |

---

## 3. 依赖与并行策略

```
S1(先行) 完成后：
  ├─ S2 + S3   （中国 v4 组，可并行）
  ├─ S4 + S5   （中国 v6 组，可并行）
  ├─ S6 + S7   （全球 v4 组，可并行）
  └─ S8 + S9   （全球 v6 组，可并行）
最后 S10（依赖全部前序）
同组内 10 个二级子代理按依赖链流水执行，独立任务可并行。
```

## 4. 质量标准（每库必须 PASS 才能进入 S10）

- [ ] 每个文件的字段集合 ⊇ {isp, idc_vendor, is_residential, connection_type}
- [ ] 家宽逻辑抽样 1000 条 100% 符合"非 IDC ⇒ is_residential=true"
- [ ] 坐标字段全部为 float
- [ ] 重建后 QA 精度不低于重建前（province/city 一致率 ± 无回退）
- [ ] 文件可被 maxminddb 正常打开且随机查询无异常