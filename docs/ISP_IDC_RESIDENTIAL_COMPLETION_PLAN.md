# IP 数据库 ISP/IDC/家宽 字段补齐执行计划 (10x10 子代理架构)

> **版本**: v1.0  
> **创建时间**: 2026-08-24  
> **目标**: 对所有 22 个 MMDB 数据库文件（中国库 18 个 + 全球库 4 个）补齐 **运营商(isp)**、**IDC 厂商(idc_vendor)**、**家宽判断(is_residential/connection_type)** 字段  
> **判断逻辑**: 非 IDC 数据中心 IP => 归属为家宽 IP (is_residential=true, connection_type='residential')  
> **执行架构**: 10 个一级子代理 x 每个嵌套 10 个二级子代理 = **100 个子代理** 协同执行  
> **技能**: engineering-data-engineer . gis-spatial-data-engineer . engineering-database-optimizer . gis-qa-engineer . engineering-software-architect

---

## 1. 现状审计结论（实测）

> 审计时间：2026-08-24 最新实测扫描  
> 工具：python + maxminddb 遍历全部 23 个 MMDB 文件（排除 tmp_v6.mmdb）

### 1.1 中国库 (18 个文件)

| 文件 | 大小 | isp 字段 | idc_vendor 字段 | is_residential | connection_type |
|---|---|---|---|---|---|
| **基础库** | | | | | |
| china_ipv4.mmdb | 1.16MB | 86.4% 覆盖 | 0.98% 覆盖 | 缺失 | 缺失 |
| china_ipv6.mmdb | 0.23MB | 74.0% 覆盖 | 0.01% 覆盖 | 缺失 | 缺失 |
| china_ipv6_enriched.mmdb | 0.23MB | 74.0% 覆盖 | 0.01% 覆盖 | 缺失 | 缺失 |
| **高精度库** | | | | | |
| china_ipv4_high_prec.mmdb | 2.35MB | **完全缺失** | **完全缺失** | 缺失 | 缺失 |
| china_ipv4_high_prec_v2.mmdb | 2.34MB | **完全缺失** | **完全缺失** | 缺失 | 缺失 |
| china_ipv4_with_isp.mmdb | 2.65MB | 83.0% 覆盖 | **完全缺失** | 缺失 | 缺失 |
| china_ipv6_with_isp.mmdb | 0.42MB | 83.1% 覆盖 | **完全缺失** | 缺失 | 缺失 |
| **分 ISP 库** | | | | | |
| china_ipv4_telecom.mmdb | 0.36MB | 有 | 1.3% 覆盖 | 缺失 | 缺失 |
| china_ipv4_unicom.mmdb | 0.24MB | 有 | 1.7% 覆盖 | 缺失 | 缺失 |
| china_ipv4_mobile.mmdb | 0.30MB | 有 | 缺失 | 缺失 | 缺失 |
| china_ipv4_other.mmdb | 0.48MB | 52.8% 覆盖 | 0.88% 覆盖 | 缺失 | 缺失 |
| china_ipv6_telecom.mmdb | 0.03MB | 有 | 缺失 | 缺失 | 缺失 |
| china_ipv6_unicom.mmdb | 0.03MB | 有 | 缺失 | 缺失 | 缺失 |
| china_ipv6_mobile.mmdb | 0.02MB | 有 | 缺失 | 缺失 | 缺失 |
| china_ipv6_other.mmdb | 0.16MB | 37.1% 覆盖 | 0.03% 覆盖 | 缺失 | 缺失 |
| **IDC 专用库** | | | | | |
| china_ipv4_idc.mmdb | 0.00MB | 缺失 | 名为 vendor | 缺失 | 缺失 |
| china_ipv4_idc_enriched.mmdb | 0.00MB | 缺失 | 名为 vendor | 缺失 | 缺失 |
| china_ipv6_idc.mmdb | 0.00MB | 缺失 | 名为 vendor | 缺失 | 缺失 |
| china_ipv6_idc_enriched.mmdb | 0.00MB | 缺失 | 名为 vendor | 缺失 | 缺失 |

### 1.2 全球库 (4 个文件)

| 文件 | 大小 | isp 字段 | idc_vendor 字段 | is_residential | connection_type |
|---|---|---|---|---|---|
| global_ipv4_residential.mmdb | 64.6MB | **完全缺失** | **完全缺失** | 缺失 | 缺失 |
| global_ipv4_idc.mmdb | 0.21MB | 缺失 | 名为 vendor | 缺失 | 名为 type |
| global_ipv6_residential.mmdb | 53.3MB | **完全缺失** | **完全缺失** | 缺失 | 缺失 |
| global_ipv6_idc.mmdb | 0.16MB | 缺失 | 名为 vendor | 缺失 | 名为 type |

### 1.3 共性问题总结

1. **全部 22 个文件均无 is_residential 字段** -- 家宽/IDC 只能靠文件名隐式区分
2. **全部 22 个文件均无 connection_type 字段** -- 缺少统一的连接类型枚举
3. **全球 residential 库** 完全没有 isp 和 idc_vendor 信息（仅含 country/region/city/source）
4. **中国 high_prec 库** 是最关键缺口：isp/idc_vendor 完全缺失，且 lat/lng 为字符串类型
5. **IDC 库字段名不统一**：vendor 应补充为 isp + idc_vendor，type 应映射为 connection_type
6. **坐标类型不一致**：部分文件 lat/lng 为 str（如 "-27.4767"），需归一化到 float
---

## 2. 目标统一 Schema

所有 MMDB 修复后必须包含以下字段（按文件组别子集适用）：

| 字段名 | 类型 | 必选 | 说明 |
|---|---|---|---|
| isp | string | 否 | 运营商名称（中国电信/Vodafone/云厂商名兜底） |
| idc_vendor | string | 否 | IDC/云厂商标记，非 IDC 段省略 |
| is_residential | boolean | **是** | 家宽判断：true=家宽/非IDC，false=IDC |
| connection_type | string | **是** | 枚举值：residential / idc / unknown |
| confidence | number | 否 | 保留现有值，缺失默认 0.3 |
| accuracy_radius | integer | 否 | 保留现有值，缺失默认 city 50km / province 200km |
| country | string | 是 | 中国库中文；全球库 ISO 3166-1 alpha-2 |
| region | string | 否 | 全球库 ISO 3166-2 一级行政区 |
| province | string | 否 | 中国库省份 |
| city | string | 否 | 城市名称 |
| district | string | 否 | 区县名称（仅 district 级记录回填） |
| division_code | string | 否 | GB/T 2260 6 位码，仅中国库 |
| geo_level | string | 是 | district/city/province/admin_center/datacenter/unknown |
| latitude | number | 否 | WGS-84，float 6 位小数 |
| longitude | number | 否 | WGS-84，float 6 位小数 |

### 文件组适用性

| 组别 | 文件 | 核心字段 |
|---|---|---|
| China main (15 个) | china_ipv4/6.mmdb, *_telecom/unicom/mobile/other, *_high_prec, *_with_isp, *_enriched | 全部 15 个字段 |
| China IDC (4 个) | china_ipv4/6_idc[,_enriched].mmdb | isp, idc_vendor, is_residential=false, connection_type=idc, country, province, city, geo_level=datacenter |
| Global residential (2 个) | global_ipv4/6_residential.mmdb | isp, idc_vendor, is_residential=true, connection_type=residential, country, region, city, confidence, accuracy_radius |
| Global IDC (2 个) | global_ipv4/6_idc.mmdb | isp=vendor, idc_vendor=vendor, is_residential=false, connection_type=idc, country, region, source |

### 遗留字段兼容

| 遗留字段 | 目标字段 | 操作 |
|---|---|---|
| vendor | idc_vendor | 复制/重命名，保留 vendor 作兼容键 |
| type | connection_type | type='idc' -> connection_type='idc'，保留 type 作兼容键 |
| source | source | 保留不变 |

---

## 3. 家宽/IDC 分类逻辑规则

> 来源：data/audit/classification_rules.json（S1.3 产物）

### 3.1 预过滤规则（跳过分类）

IP 地址属于以下范围时，跳过 IDC 匹配，connection_type='unknown'：

| 规则 | 范围 | 说明 |
|---|---|---|
| RFC 1918 私有地址 | 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16 | 非公开路由 |
| CGNAT | 100.64.0.0/10 | RFC 6598 共享地址空间 |
| 回环 | 127.0.0.0/8 | 本机回环 |
| 链路本地 | 169.254.0.0/16 | APIPA |
| 保留/未来使用 | 0.0.0.0/8, 240.0.0.0/4, 255.255.255.255/32 | IANA 保留 |
| 组播 | 224.0.0.0/4 | 组播地址 |
| IPv6 ULA | fc00::/7 | 唯一本地地址 |
| IPv6 链路本地 | fe80::/10 | 链路本地 |
| IPv6 保留 | ::1/128, ::/128, 2001:db8::/32 | 回环/未指定/文档 |

### 3.2 IDC 匹配规则（按优先级）

**规则 A**: 命中 scripts/common/constants.py 中的 IDC_IPV4_RANGES（阿里云/腾讯云/华为云/百度云/京东云）
-> is_residential=false, connection_type='idc', idc_vendor=匹配厂商名

**规则 B**: 命中 data/global/idc/idc_all.csv 中的全球 IDC 范围（AWS/Azure/GCP/Cloudflare/DigitalOcean/Fastly/中国云厂商等）
-> is_residential=false, connection_type='idc', idc_vendor=匹配厂商名

**规则 C**: 命中 IDC_IPV6_PREFIXES（2403:b180::/32 阿里云 IPv6 等）
-> is_residential=false, connection_type='idc', idc_vendor=匹配厂商名

### 3.3 缺省规则

**未命中任何 IDC 规则**
-> is_residential=true, connection_type='residential'

### 3.4 库级规则优化

| 库类型 | 默认行为 | 覆盖规则 |
|---|---|---|
| IDC 专用库（*_idc*） | 全量 is_residential=false, connection_type=idc | 不执行逐条 IDC 查找 |
| Residential 专用库（*_residential*） | 全量 is_residential=true, connection_type=residential | 仍执行 IDC 查找以补 idc_vendor |
| 混合库（主库/分 ISP 库） | 逐条 IDC 查找，非命中->家宽 | 执行完整分类逻辑 |
---

## 4. 执行架构：10x10 子代理拓扑

```
                      Orchestrator（本会话 - 主控）
    计划编写 · 技能加载 · 派发 100 子代理 · 进度追踪 · 汇总报告
       |
       |-- S1: 审计基座 ------ 10 个二级子代理 (S1.1~S1.10) ------ Schema 规范 + 工具库
       |                       skills: engineering-software-architect, engineering-database-optimizer
       |
       |-- S2: 中国 IPv4 主库 -- 10 个二级子代理 (S2.1~S2.10) ---- 8 个主库文件补丁
       |                       skills: engineering-data-engineer, gis-spatial-data-engineer
       |
       |-- S3: 中国 IPv4 IDC -- 10 个二级子代理 (S3.1~S3.10) ---- 2 个 IDC 库补丁
       |                       skills: engineering-data-engineer
       |
       |-- S4: 中国 IPv6 主库 -- 10 个二级子代理 (S4.1~S4.10) ---- 7 个主库文件补丁
       |                       skills: engineering-data-engineer, gis-spatial-data-engineer
       |
       |-- S5: 中国 IPv6 IDC -- 10 个二级子代理 (S5.1~S5.10) ---- 2 个 IDC 库补丁
       |                       skills: engineering-data-engineer
       |
       |-- S6: 全球 IPv4 住宅 -- 10 个二级子代理 (S6.1~S6.10) ---- 1 个 64MB 住宅库补丁
       |                       skills: engineering-data-engineer, gis-spatial-data-engineer
       |
       |-- S7: 全球 IPv4 IDC -- 10 个二级子代理 (S7.1~S7.10) ---- 1 个 IDC 库补丁
       |                       skills: engineering-data-engineer
       |
       |-- S8: 全球 IPv6 住宅 -- 10 个二级子代理 (S8.1~S8.10) ---- 1 个 53MB 住宅库补丁
       |                       skills: engineering-data-engineer, gis-spatial-data-engineer
       |
       |-- S9: 全球 IPv6 IDC -- 10 个二级子代理 (S9.1~S9.10) ---- 1 个 IDC 库补丁
       |                       skills: engineering-data-engineer
       |
       +-- S10: QA 验证与部署 -- 10 个二级子代理 (S10.1~S10.10) -- 整体验证 + 部署
                                skills: gis-qa-engineer, engineering-data-engineer
```

---

## 5. 一级子代理详表：S1-S10

### S1：Schema 规范与审计基座（先行运行）

**技能**: engineering-software-architect, engineering-database-optimizer  
**覆盖**: 全部 22 个 MMDB 文件  
**产出目录**: data/audit/, scripts/tools/50_mmdb_field_patch.py

| ID | 二级子代理任务 | 输入 | 输出 | 方法概要 |
|---|---|---|---|---|
| S1.1 | 字段清单盘点器 | 全部 MMDB | data/audit/field_inventory.json | 遍历每个 .mmdb，记录字段集合、覆盖率、类型、样例 |
| S1.2 | 目标 Schema 定义器 | S1.1 + 需求 | data/audit/target_schema.json | 定义统一字段名/类型/必选性/允许值/文件组适用性 |
| S1.3 | 分类逻辑规则器 | 需求 | data/audit/classification_rules.json | 编纂非IDC=>家宽规则，含优先级、预过滤、冲突处理 |
| S1.4 | 字段差异分析器 | S1.1 vs S1.2 | data/audit/field_gap_report.csv | 逐文件比对缺失字段、类型不匹配，输出 CSV |
| S1.5 | 修复优先级排序器 | S1.4 | data/audit/repair_priority.json | 按重要性 x 缺口数量排序文件清单 |
| S1.6 | 字段名映射表 | S1.2 + 现文件名 | data/audit/field_name_map.json | vendor->idc_vendor, type->connection_type, source 保留 |
| S1.7 | 共享补丁工具库 | S1.2 + build_mmdb.py | scripts/tools/50_mmdb_field_patch.py | 编写可复用库：read_mmdb/add_missing_fields/normalize_coords/idc_lookup/write_mmdb + CLI |
| S1.8 | 数据源亲和性分析 | ip2region 源/分类 | data/audit/source_field_affinity.csv | 统计各源 ISP 可用性覆盖率 |
| S1.9 | QA 测试用例设计 | S1.2 + S1.3 | data/audit/qa_test_cases.json | >=10 个可执行测试用例 |
| S1.10 | 审计报告终稿 | S1 全部产物 | data/audit/audit_final_report.md | 汇总盘点结论、差异清单、优先级、工具库用法 |
### S2：中国 IPv4 主库补丁

**技能**: engineering-data-engineer, gis-spatial-data-engineer  
**覆盖**: china_ipv4.mmdb, china_ipv4_{telecom,unicom,mobile,other}.mmdb, china_ipv4_with_isp.mmdb, china_ipv4_high_prec(_v2).mmdb  
**产出目录**: data/china/v4/, output/ 重建文件

| ID | 二级子代理任务 | 输入 | 输出 | 方法概要 |
|---|---|---|---|---|
| S2.1 | v4 isp 缺失分析 | 主库 + field_inventory | data/china/v4/v4_isp_gap.json | 统计各文件 isp 缺失率 |
| S2.2 | ip2region org 回填 | ipv4_source.txt | data/china/v4/v4_org_intervals.json | 解析 CN/HK/MO/TW 行(start_int,end_int,org) 持久化 |
| S2.3 | IDC 区间匹配 | constants.IDC_IPV4_RANGES | data/china/v4/v4_idc_matched.csv | 主库记录逐一匹配 IDC 区间 |
| S2.4 | is_residential 计算 | S2.3 + classification_rules | data/china/v4/v4_res_flags.csv | 全量计算，非IDC=>true/residential |
| S2.5 | high_prec 库补丁 | 两个 high_prec.mmdb | output/ 重建 high_prec* | 补 isp/idc_vendor/is_residential/connection_type，坐标归一 |
| S2.6 | with_isp 库补丁 | china_ipv4_with_isp.mmdb | output/ 重建 | 补 idc_vendor/is_residential/connection_type |
| S2.7 | 分 ISP 库补丁 | 4 个 v4 分 ISP 库 | output/ 重建 4 文件 | 补 idc_vendor/is_residential/connection_type |
| S2.8 | 主库重建 | china_ipv4.mmdb + S2.4 | output/ 重建 | 补 isp(缺失回填)/idc_vendor/is_residential/connection_type |
| S2.9 | Schema 校验 | S2 全部重建产物 | data/china/v4/v4_schema_check.json | 遍历校验字段存在性与 lat/lng float 类型 |
| S2.10 | 抽样验证报告 | S2 全部产物 | data/china/v4/v4_pool_report.md | 抽样查询已知 IP，验证 isp 与 is_residential 正确性 |

### S3：中国 IPv4 IDC 库补丁

**技能**: engineering-data-engineer  
**覆盖**: china_ipv4_idc.mmdb, china_ipv4_idc_enriched.mmdb  
**产出目录**: data/china/v4_idc/, output/ 重建文件

| ID | 任务 | 方法概要 |
|---|---|---|
| S3.1 | Schema 审计 | 枚举文件字段（vendor/start_ip/end_ip/region）与记录数 |
| S3.2 | isp=vendor 映射 | vendor 值复制为 isp 字段 |
| S3.3 | idc_vendor 归一 | vendor->idc_vendor 映射 |
| S3.4 | 家宽字段设计 | 全量 is_residential=false, connection_type=idc |
| S3.5 | 重建 idc 库 | 50_mmdb_field_patch.py --idc-mode all-idc |
| S3.6 | enriched 库补丁 | 补 isp/idc_vendor/is_residential/connection_type |
| S3.7 | geo_level 校对 | 校验所有记录 geo_level=datacenter |
| S3.8 | 一致性校验 | constants.IDC_IPV4_RANGES 全覆盖检查 |
| S3.9 | v4/v6 IDC 交叉校验 | vendor 集合一致性（v4 vs v6 IDC） |
| S3.10 | 报告 | 中文总结：新旧字段、重建结果 |

### S4：中国 IPv6 主库补丁

**技能**: engineering-data-engineer, gis-spatial-data-engineer  
**覆盖**: china_ipv6.mmdb, china_ipv6_{telecom,unicom,mobile,other}.mmdb, china_ipv6_with_isp.mmdb, china_ipv6_enriched.mmdb  
**产出目录**: data/china/v6/, output/ 重建文件

| ID | 任务 | 方法概要 |
|---|---|---|
| S4.1 | v6 isp 缺失分析 | 统计 isp 缺失率 |
| S4.2 | ip2region v6 org 回填 | 解析 v6 源 org 持久化 |
| S4.3 | 前缀 ISP 推断 | 240e->telecom, 2409->mobile, 2408->unicom |
| S4.4 | IDC v6 前缀匹配 | IDC_IPV6_PREFIXES 匹配 |
| S4.5 | is_residential 计算 | 非 IDC=>true |
| S4.6 | 重建 china_ipv6.mmdb + with_isp | 50_mmdb_field_patch.py |
| S4.7 | 重建 enriched 库 | 补 isp(缺失回填)/idc_vendor/is_residential |
| S4.8 | 分 ISP v6 库重建 | 4 个文件补 idc_vendor/is_residential/connection_type |
| S4.9 | Schema 校验 | 字段存在性 + 坐标类型 |
| S4.10 | 抽样验证报告 | 查询 240e/2409/2408 与 IDC 前缀验证 |
### S5：中国 IPv6 IDC 库补丁

**技能**: engineering-data-engineer  
**覆盖**: china_ipv6_idc.mmdb, china_ipv6_idc_enriched.mmdb  
**产出目录**: data/china/v6_idc/, output/ 重建文件

**任务**: 与 S3 同构
- S5.1 Schema 审计 -> S5.2 isp=vendor -> S5.3 idc_vendor 归一 -> S5.4 家宽字段设计 -> S5.5 重建 idc 库 -> S5.6 enriched 补丁 -> S5.7 geo_level 校对 -> S5.8 一致性校验 -> S5.9 v4/v6 交叉校验 -> S5.10 报告

### S6：全球 IPv4 住宅库补丁

**技能**: engineering-data-engineer, gis-spatial-data-engineer  
**覆盖**: global_ipv4_residential.mmdb（64.6MB，约 620 万记录）  
**产出目录**: data/global/confidence/, output/ 重建文件

| ID | 任务 | 方法概要 |
|---|---|---|
| S6.1 | 字段审计 | 确认当前仅 country/region/city/lat/lng/confidence/source |
| S6.2 | 关联 classification.csv | 利用 global/classification.csv 分类信息 |
| S6.3 | ISP 字段生成 | 从 ip2region org + ASN 关键词生成 ISP |
| S6.4 | idc_vendor 匹配 | idc_all.csv 重叠检测 |
| S6.5 | is_residential=true | 住宅库全量 true + 补丁 hit 校验 |
| S6.6 | connection_type=residential | 全量赋值 |
| S6.7 | lat/lng str->float | 坐标归一化 |
| S6.8 | 分块 MMDB 重建 | 64MB 大文件内存控制重建 |
| S6.9 | 字段一致性检查 | 大文件字段完整性校验 |
| S6.10 | 大小/性能回归报告 | 重建前后对比 |

### S7：全球 IPv4 IDC 库补丁

**技能**: engineering-data-engineer  
**覆盖**: global_ipv4_idc.mmdb  
**产出目录**: data/global/idc/, output/ 重建文件

**任务**:
- S7.1 Schema 审计（vendor/type/source 字段现状）
- S7.2 isp=vendor（IDC 运营商即云厂商名）
- S7.3 idc_vendor=vendor（统一命名）
- S7.4 is_residential=false（IDC 段）
- S7.5 connection_type=idc（从 type 映射）
- S7.6 补充 country/region 字段
- S7.7 geo_level=datacenter
- S7.8 MMDB 重建
- S7.9 与住宅库重叠检测（应 0 重叠）
- S7.10 报告

### S8：全球 IPv6 住宅库补丁

**技能**: engineering-data-engineer, gis-spatial-data-engineer  
**覆盖**: global_ipv6_residential.mmdb（53.3MB，约 860 万记录）  
**产出目录**: data/global/fusion/, output/ 重建文件

**任务**: 与 S6 同构
- S8.1 字段审计（当前仅 country/region/city/source）-> S8.2 关联分类 -> S8.3 ISP 生成 -> S8.4 idc_vendor 匹配 -> S8.5 is_residential=true -> S8.6 connection_type=residential -> S8.7 坐标补充 -> S8.8 分块重建 -> S8.9 一致性检查 -> S8.10 性能报告

### S9：全球 IPv6 IDC 库补丁

**技能**: engineering-data-engineer  
**覆盖**: global_ipv6_idc.mmdb  
**产出目录**: data/global/idc/, output/ 重建文件

**任务**: 与 S7 同构
- S9.1~S9.10: 字段审计 -> isp=vendor -> idc_vendor=vendor -> is_residential=false -> connection_type=idc -> 补充字段 -> geo_level -> MMDB 重建 -> 重叠检测 -> 报告
### S10：整体 QA 验证与部署（收尾，依赖 S2~S9 全部完成）

**技能**: gis-qa-engineer, engineering-data-engineer  
**覆盖**: 全部 22 个重建后 MMDB 文件  
**产出目录**: data/audit/, docs/, output/

| ID | 任务 | 方法概要 | 通过标准 |
|---|---|---|---|
| S10.1 | 全库字段完整性扫描 | 遍历 22 个文件，逐一校验字段清单 | 每个文件字段包含 {isp, idc_vendor, is_residential, connection_type} |
| S10.2 | 家宽逻辑验证 | 抽样 1000 条：IDC=>false，非IDC=>true | 100% 符合规则 |
| S10.3 | 回归精度评测 | evaluate_precision.py 前后对比 | 精度不降低 |
| S10.4 | 坐标类型一致性检查 | 全部 lat/lng 为 float | 0 个 str 类型 |
| S10.5 | 全球 QA 评测对比 | global_qa_report.json 对比 | 无回归 |
| S10.6 | ISP 字段准确率评测 | 锚点 IP 验证 | >=90% 准确率 |
| S10.7 | IDC 分类准确率评测 | 云厂商 IP 验证 | 100% IDC 标记正确 |
| S10.8 | 部署脚本更新 | build_outputs.ps1, deploy_isp.ps1 | 脚本可运行 |
| S10.9 | 文档更新 | README, docs 中的 Schema 说明 | 文档完整 |
| S10.10 | 最终审计报告 | data/audit/final_audit_report.md | 报告覆盖全部检查项 |

---

## 6. 依赖与并行策略

```
时间线（有向无环图）

阶段 1:  S1 (审计基座) - 先行运行，全部 10 个二级子代理按顺序链执行
         |
         +-- S1.1 -> S1.2 -> S1.3 -> S1.4 -> S1.5 -> S1.6 -> S1.7 -> S1.8 -> S1.9 -> S1.10
         |
         +-- S1 完成后
         |
阶段 2:  四组并行（彼此无依赖）
         |
         +-- 组 A: S2 + S3  (中国 IPv4 组，S2 与 S3 内部可并行部分二级任务)
         +-- 组 B: S4 + S5  (中国 IPv6 组，S4 与 S5 内部可并行部分二级任务)
         +-- 组 C: S6 + S7  (全球 IPv4 组，S6 与 S7 内部可并行部分二级任务)
         +-- 组 D: S8 + S9  (全球 IPv6 组，S8 与 S9 内部可并行部分二级任务)
         |
         +-- S2~S9 全部完成
         |
阶段 3:  S10 (QA 验证与部署) - 收尾，全部 10 个二级子代理按顺序链执行
         |
         S10.1 -> S10.2 -> ... -> S10.10
```

### 每池内部二级子代理执行策略

| 模式 | 池 | 说明 |
|---|---|---|
| 顺序链 | S1, S10 | 每步依赖前一步产物，必须串行 |
| 混合并行 | S2, S4, S6, S8 | 分析任务(1-4) 可串行，补丁重建(5-8) 可并行独立文件，校验(9-10) 需依赖全部补丁完成 |
| 纯并行 | S3, S5, S7, S9 | 大部分二级任务可并行（IDC 库结构简单，字段少） |

---

## 7. 质量标准（门禁）

**每个文件必须 PASS 以下检查才能进入 S10：**

- [ ] 字段完整性：{[isp], [idc_vendor], [is_residential], [connection_type]} 全部存在
- [ ] 家宽逻辑：抽样 1000 条 100% 符合"非 IDC => is_residential=true"
- [ ] 坐标类型：latitude/longitude 全部为 float（非 str）
- [ ] 精度回归：重建后 QA 精度 >= 重建前（province/city 一致率无回退）
- [ ] 格式正确：文件可被 maxminddb 正常打开，随机查询无异常
- [ ] 文件大小：重建后文件大小在合理范围内（+/-20% 原始大小）

---

## 8. 产物清单

### 审计产物 (data/audit/)

| 文件 | 来源 | 说明 |
|---|---|---|
| field_inventory.json | S1.1 | 全部 MMDB 字段现状盘点 |
| target_schema.json | S1.2 | 目标统一字段规范 |
| classification_rules.json | S1.3 | 家宽/IDC 分类逻辑规则 |
| field_gap_report.csv | S1.4 | 逐文件缺失字段差异清单 |
| repair_priority.json | S1.5 | 修复优先级排序 |
| field_name_map.json | S1.6 | 遗留字段映射表 |
| source_field_affinity.csv | S1.8 | 数据源 ISP 可用性分析 |
| qa_test_cases.json | S1.9 | QA 测试用例设计 |
| audit_final_report.md | S1.10 | 审计报告终稿 |

### 补丁工具库

| 文件 | 来源 | 说明 |
|---|---|---|
| scripts/tools/50_mmdb_field_patch.py | S1.7 | 共享 MMDB 补丁工具库（CLI + API） |

### 数据池产物

| 目录 | 来源 | 说明 |
|---|---|---|
| data/china/v4/ | S2 | v4 主库分析/映射/CSV 中间产物 |
| data/china/v4_idc/ | S3 | v4 IDC 库分析/校验产物 |
| data/china/v6/ | S4 | v6 主库分析/映射/CSV 中间产物 |
| data/china/v6_idc/ | S5 | v6 IDC 库分析/校验产物 |
| data/global/confidence/ | S6~S9 | 全球库分析/校验产物 |

### 重建后 MMDB 文件 (output/)

| 文件 | 组 | 新增字段 |
|---|---|---|
| china_ipv4.mmdb | S2 | isp(回填), idc_vendor, is_residential, connection_type |
| china_ipv4_high_prec.mmdb | S2 | isp, idc_vendor, is_residential, connection_type, lat/lng 归一 |
| china_ipv4_high_prec_v2.mmdb | S2 | isp, idc_vendor, is_residential, connection_type, lat/lng 归一 |
| china_ipv4_idc.mmdb | S3 | isp, idc_vendor, is_residential, connection_type |
| china_ipv4_idc_enriched.mmdb | S3 | isp, idc_vendor, is_residential, connection_type |
| china_ipv4_mobile.mmdb | S2 | idc_vendor, is_residential, connection_type |
| china_ipv4_other.mmdb | S2 | is_residential, connection_type |
| china_ipv4_telecom.mmdb | S2 | is_residential, connection_type |
| china_ipv4_unicom.mmdb | S2 | is_residential, connection_type |
| china_ipv4_with_isp.mmdb | S2 | idc_vendor, is_residential, connection_type |
| china_ipv6.mmdb | S4 | is_residential, connection_type |
| china_ipv6_enriched.mmdb | S4 | is_residential, connection_type |
| china_ipv6_idc.mmdb | S5 | isp, idc_vendor, is_residential, connection_type |
| china_ipv6_idc_enriched.mmdb | S5 | isp, idc_vendor, is_residential, connection_type |
| china_ipv6_mobile.mmdb | S4 | idc_vendor, is_residential, connection_type |
| china_ipv6_other.mmdb | S4 | is_residential, connection_type |
| china_ipv6_telecom.mmdb | S4 | idc_vendor, is_residential, connection_type |
| china_ipv6_unicom.mmdb | S4 | idc_vendor, is_residential, connection_type |
| china_ipv6_with_isp.mmdb | S4 | idc_vendor, is_residential, connection_type |
| global_ipv4_idc.mmdb | S7 | isp, idc_vendor, is_residential, connection_type, country, region, geo_level |
| global_ipv4_residential.mmdb | S6 | isp, idc_vendor, is_residential, connection_type, lat/lng 归一 |
| global_ipv6_idc.mmdb | S9 | isp, idc_vendor, is_residential, connection_type, country, region, geo_level |
| global_ipv6_residential.mmdb | S8 | isp, idc_vendor, is_residential, connection_type, lat/lng, confidence |

### 最终交付

| 文件 | 来源 | 说明 |
|---|---|---|
| data/audit/final_audit_report.md | S10.10 | 完整 QA 审计报告 |

---

## 附录：子代理编排说明

### 主控器（Orchestrator）职责

1. **前置检查**：确认各 MMDB 文件存在且可读，确认 50_mmdb_field_patch.py 工具库可用
2. **派发 S1**：按顺序链 S1.1->S1.10 派发一级子代理，每步验证产物存在后再派发下一步
3. **并行派发 S2~S9**：S1 完成后，同时派发 S2、S3、S4、S5、S6、S7、S8、S9 八个一级子代理（各组内部可再并行二级子代理）
4. **等待全部完成**：收集所有 S2~S9 完成信号，确认产物
5. **派发 S10**：按顺序链 S10.1->S10.10 逐步骤验证派发
6. **汇总报告**：输出最终审计报告

### 子代理约束

- 每个二级子代理是独立 agent，拥有自己的上下文
- 子代理必须真实执行：读取文件、运行命令、写入产物
- 子代理不得编造产物——无法完成时明确说明阻塞原因
- 子代理使用 pwsh 执行 python 脚本，UTF-8 编码

### 关键工具依赖

- Python 3.14+ 标准库：sqlite3, json, csv, glob, os, sys, ipaddress
- 第三方库：maxminddb>=3.1.1, netaddr, mmdb_writer（site-packages 已安装）
- 共享库：scripts/tools/50_mmdb_field_patch.py（S1.7 产物，所有 S2~S9 子代理必须加载）
- 数据源：data/global/idc/idc_all.csv（122240 行全球 IDC 范围）
- 常量：scripts/common/constants.py（IDC_IPV4_RANGES, IDC_IPV6_PREFIXES, IPV6_ISP_PREFIXES, ISP_KEYWORDS）
