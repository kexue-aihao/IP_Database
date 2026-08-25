# S11 · ASN 增强层执行计划 (10x10 子代理架构)

> **版本**: v2.0（评审修订版）  
> **创建时间**: 2026-08-24  
> **目标**: 通过 BGP/ASN 数据增强海外 IP 库准确率 — 回填全球库 isp 字段、强化 IDC/家宽判定、交叉验证国家归属  
> **判定逻辑**: IP → ASN（BGP 路由表）→ org 名称/注册国 → isp 字段 + is_residential 判定  
> **执行架构**: 10 个一级子代理 × 每个嵌套 10 个二级子代理 = **100 个子代理**  
> **技能**: engineering-data-engineer · gis-spatial-data-engineer · engineering-database-optimizer · gis-qa-engineer  
> **关键依赖**: pybgpkit_parser (已安装 0.18.0), mrtparse (已安装 2.2.0), requests

---

## 1. 背景与现状（实测数据，2026-08-24）

### 1.1 现状缺口

| 缺口 | 实测数据 | 影响 |
|---|---|---|
| 全球库 isp 字段为空 | global_ipv4/6_residential.mmdb 14.8M 条记录 isp=缺失 | 用户无法获取运营商信息 |
| IDC 判定覆盖不足 | idc_all.csv 仅 Azure(108K)+AWS(11K)+GCP(1K) 等少量厂商 | 中小 IDC 被判定为家宽 |
| 国家归属单一数据源 | 仅 dbip/ip2region，无交叉验证 | 错配无法发现 |

### 1.2 数据源验证结果

| 数据源 | 可用性 | 用途 | 备注 |
|---|---|---|---|
| **RouteViews RIB dump** | ✅ 200 (79MB bz2) | **全量 BGP 路由表 → IP→ASN 映射** | 一次下载，秒级解析，替代 15 万次 API |
| **RIR delegated ×5** | ✅ 全部 200 | 离线 IP→cc 注册索引；ASN 分配记录 | 总量 ~45MB |
| **RIPEstat** | ✅ 已验证 | network-info (IP→ASN), as-overview (ASN→org) | 补充查询，非主通道 |
| **ip-api.com** | ✅ 已验证 | 单条 ISP/AS/org 查询 | 免费 45/min，用于抽样校验 |
| ipinfo.io | ✅ 已验证 | 同 ip-api，免费 50K/月 | 抽样校验 |
| ~~bgpview.io~~ | ❌ DNS 不可达 | 弃用 | — |

### 1.3 评审后的关键策略调整

| 版本 | 原方案 | 评审后方案 |
|---|---|---|
| S11.2 ASN 获取 | RIPEstat 逐 ASN 抓取（15 万次 ≈ 50 小时） | **RouteViews RIB dump 一次下载 + pybgpkit_parser**（≈ 10 分钟） |
| S11.2 org 名称 | RIPEstat as-overview 再 15 万次 | **RIPE RDAP/ARIN WHOIS 离线批量 → ASN→org** |
| 架构角色 | RIR delegated 为 ASN 主数据 | RIR→国家索引；BGP RIB→ASN；RDAP→org 名称；三者互补 |
| 时间预算 | ~8 天（串行） | ~2-3 小时（含 RIB 下载解析 + 全量标注） |

---

## 2. 数据流架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│ ① BGP 路由表 (离线)             ② RIR delegated (离线)                 │
│ RouteViews / 79MB bz2            RIPE/APNIC/ARIN/LACNIC/AFRINIC        │
│   ↓ pybgpkit_parser               ↓ Python 解析                        │
│ IP→ASN 映射 (100万+ 前缀)         IP→cc 国家注册索引                    │
│   ↓                                ↓                                   │
│ ③ ASN→org 名称 (RDAP)           ④ 国家交叉验证                        │
│ RIPE/ARIN RDAP 批量               RIR cc vs dbip/ip2region cc          │
│   ↓                                ↓                                   │
│ ⑤ 全量标注: 每条 IP 段 → ASN + org + cc_rir + isp_field               │
│ ⑥ IDC 判定: org 关键字 + idc_all.csv 合并 → is_residential 更新        │
│ ⑦ global MMDB 重建 (isp 回填)                                          │
│ ⑧ QA 验证 (覆盖率 + 准确率 + 性能回归)                                  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. 一级子代理详表：S11.1 ~ S11.10

### S11.1：RIR 数据抓取与注册索引（离线，不受限速）

**技能**: engineering-data-engineer  
**产出**: `data/bgp/rir_index.pk`（IP→cc + ASN 分配索引）
**估算**: 15 分钟

| ID | 二级子代理任务 | 输入 | 输出 | 方法概要 |
|---|---|---|---|---|
| S11.1.1 | RIR 5 文件下载 | 5 个 URL（已验证） | data/raw/delegated-*-latest | Invoke-WebRequest 下载，记录大小/校验和 |
| S11.1.2 | ipv4 行解析（5 文件） | 各 RIR 的 ipv4 行 | data/bgp/rir_v4_ranges.csv.gz | 解析 (start, value_count, cc, status)，value=count → 前缀长度 |
| S11.1.3 | ipv6 行解析（5 文件） | 各 RIR 的 ipv6 行 | data/bgp/rir_v6_prefixes.csv.gz | 解析 (prefix, prefix_len, cc, status) |
| S11.1.4 | asn 记录解析（5 文件） | 各 RIR 的 asn 行 | data/bgp/rir_asn_map.csv | (asn_start, count, cc, status)，去重 15 万 ASN |
| S11.1.5 | 国家 vs 区域映射 | ISO 3166 + RIR 区域 | data/bgp/rir_region_map.json | RIR 区域（RIPE/ARIN/APNIC）→ 大洲映射 |
| S11.1.6 | v4 二分索引构建 | S11.1.2 | data/bgp/rir_v4_index.pk | start_int 排序 + bisect 索引（同 50_mmdb_field_patch 模式） |
| S11.1.7 | v6 前缀索引构建 | S11.1.3 | data/bgp/rir_v6_index.pk | 前缀排序 + 二分索引 |
| S11.1.8 | 注册状态统计 | S11.1.2~4 | data/bgp/rir_status_report.json | 各 RIR 的记录数、各状态占比 |
| S11.1.9 | 公共加载器模块 | S11.1.6~7 | scripts/common/rir_index.py | rir_v4_lookup(ip)→cc, rir_v6_lookup(ip)→cc |
| S11.1.10 | 数据 QA | 全部 | data/bgp/rir_qa.json | 行数对账、覆盖率校验、抽查 100 条 |

### S11.2：BGP 路由表全量解析（核心变革）

**技能**: engineering-data-engineer  
**覆盖**: RouteViews RIB dump（79MB bz2）→ 全量 IP→ASN 映射  
**产出**: `data/bgp/asn_prefix_map.pk`（IP→ASN 二分索引）+ `data/bgp/asn_org_map.json`（ASN→org 名称）
**依赖**: pybgpkit_parser 0.18.0（已安装），mrtparse 2.2.0（已安装）
**估算**: 30 分钟（下载 5-10min + 解析 10-15min + 索引 5min）

| ID | 二级子代理任务 | 方法概要 |
|---|---|---|
| S11.2.1 | RIB 下载 | RouteViews rib.20260824.0000.bz2（79MB），校验 bz2 完整性 |
| S11.2.2 | pybgpkit 解析器测试 | 对 1000 条前缀测试解析，验证 (prefix, asn, as_path) 提取 |
| S11.2.3 | 全量 RIB 解析（v4） | 提取所有 IPv4 unicast 前缀 → (prefix, origin_as) |
| S11.2.4 | 全量 RIB 解析（v6） | 提取所有 IPv6 unicast 前缀 |
| S11.2.5 | AS 去重预聚合 | 重复前缀取最新 ASN，多 origin AS 取 first |
| S11.2.6 | v4 前缀二分索引构建 | start_int 排序 + bisect 索引 |
| S11.2.7 | v6 前缀二分索引构建 | 同 v4 |
| S11.2.8 | ASN→org 名称获取（RDAP 批量） | RIPE RDAP (rdap.db.ripe.net) + ARIN WHOIS 批量查询 → 去重后约 15 万 ASN |
| S11.2.9 | ASN→org 名称补充（RIPEstat） | RDAP 未覆盖的 → RIPEstat as-overview 补充（限速，后台） |
| S11.2.10 | 索引合并与持久化 | asn_prefix_map.pk + asn_org_map.json → 公共加载器 |

> ★ 相比原方案（逐 ASN RIPEstat 50 小时），此方案将时间压缩到 **约 30 分钟**（一次下载 + 一个解析脚本）

### S11.3：全球 IP 段 ASN 标注

**技能**: engineering-data-engineer  
**覆盖**: global_raw_v4.csv (4M) + global_raw_v6.csv (4.8M)  
**产出**: `data/bgp/global_asn_annotated.csv.gz`（新增 asn/org_name/cc_rir/isp_match 列）
**估算**: 15 分钟

| ID | 二级子代理任务 | 方法概要 |
|---|---|---|
| S11.3.1 | 标注策略设计 | 每行记录：查 asn_prefix_map → asn; 查 rir_index → cc; 查 asn_org_map → org_name |
| S11.3.2 | v4 标注 v1（前 100 万） | 分块并行处理前 100 万行 |
| S11.3.3 | v4 标注 v2（剩余） | 100 万→完成 |
| S11.3.4 | v6 标注 v1（前 100 万） | 分块并行 |
| S11.3.5 | v6 标注 v2（剩余） | 100 万→完成 |
| S11.3.6 | 标注合并去重 | 分块合并 → 完整 annotated CSV |
| S11.3.7 | 命中率统计 | ASN 标注覆盖率、RIR cc 覆盖率 |
| S11.3.8 | 未命中分析 | 未命中 ASN 的原因：BGP 未宣告、私有地址、保留段 |
| S11.3.9 | 抽样比对 | 1000 条 vs ip-api 查询结果 |
| S11.3.10 | 标注报告 | data/bgp/annotation_report.json |

### S11.4：isp 回填 + IDC 判定增强

**技能**: engineering-data-engineer, gis-spatial-data-engineer  
**覆盖**: global classification.csv + 现有字段  
**产出**: `data/global/classification_asn.csv`（新增 asn/org_name/isp/conn_type 列）
**估算**: 20 分钟

| ID | 二级子代理任务 | 方法概要 |
|---|---|---|
| S11.4.1 | isp 回填规则器 | org_name 清洗 → isp 字段（去 AS 前缀，取可读公司名；空→保留空） |
| S11.4.2 | org 关键字 IDC 规则 | datacenter/cloud/hosting/server/colo 等关键字 → 候选 IDC |
| S11.4.3 | 住宅 ASN 白名单 | Comcast/AT&T/Verizon/中国三大运营商 等 → 强制住宅，不做 IDC 误判 |
| S11.4.4 | 与 idc_all.csv 合并 | 关键字候选 + idc_all 命中 → idc_vendor 值（idc_all 厂商名优先） |
| S11.4.5 | is_residential 重判 | 命中 IDC 关键字且不在住宅白名单 → false/idc；否则保持 true |
| S11.4.6 | 大厂白名单 | AWS/Azure/GCP/Cloudflare/阿里云/腾讯云/OVH/Hetzner 等 → 确认 IDC |
| S11.4.7 | 回填应用器 | 在 classification.csv 上应用规则，输出新列 |
| S11.4.8 | 变更统计 | isp 新增覆盖率、IDC 新增判定数、变更前后对比表 |
| S11.4.9 | 抽样复核 | 500 条 IDC 新判定 + 500 条住宅保持，输出复核表 |
| S11.4.10 | 规则固化 | 更新 scripts/common/isp_classifier.py 关键字表 |

### S11.5：国家归属交叉验证（RIR cc）

**技能**: engineering-data-engineer, gis-qa-engineer  
**覆盖**: 全部 global 记录  
**产出**: `data/bgp/cc_validation_report.md`
**估算**: 10 分钟

| ID | 二级子代理任务 | 方法概要 |
|---|---|---|
| S11.5.1 | 交叉比对 | country(源) vs cc_rir(delegated) 差异集 |
| S11.5.2 | 冲突分类 | 可纠正（RIR 权威）/ 需人工（anycast CDN）/ 忽略（保留段） |
| S11.5.3 | anycast 厂商白名单 | Cloudflare/Google/Akamai/Fastly → 不做国家纠正，标注 anycast=true |
| S11.5.4 | 纠正应用 | 非 anycast 且 RIR cc 明确 → 以 RIR 为准，标记 source=asn_corrected |
| S11.5.5 | 变更统计 | 纠正 N 条国家归属 |
| S11.5.6 | 质量抽查 | 200 条纠正 vs ip-api 复核 |
| S11.5.7 | 报告 | data/bgp/cc_validation_report.md |

### S11.6：global MMDB 重建（isp 回填）

**技能**: engineering-data-engineer, gis-spatial-data-engineer  
**产出**: 重建 global_ipv4/6_residential.mmdb + global_ipv4/6_idc.mmdb  
**估算**: 30 分钟（2 个大文件重建）

| ID | 二级子代理任务 | 方法概要 |
|---|---|---|
| S11.6.1 | 新字段定义 | isp(org_name), idc_vendor(命中厂商), 保持 is_residential 逻辑 |
| S11.6.2 | 补丁脚本适配 | 50_mmdb_field_patch.py 新增 --asn-map 参数 |
| S11.6.3 | v4 residential 重建 | 62 万条记录 + isp 回填（streaming 分块）|
| S11.6.4 | v6 residential 重建 | 860 万条 |
| S11.6.5 | IDC 库交叉核对 | 新判定 IDC 段 vs 现有 global_idc 库重叠检测 |
| S11.6.6 | 字段类型校验 | isp str, idc_vendor str, is_residential bool |
| S11.6.7 | 打开/查询验证 | maxminddb 打开 + 随机 100 查询 |
| S11.6.8 | 文件大小回归 | 重建后 ≤ 原大小 × 1.3 |
| S11.6.9 | 精度回归 | evaluate_precision.py 前后对比 |
| S11.6.10 | 部署更新 | deploy_global.ps1, README |

### S11.7：中国库 ASN 交叉应用（可选）

**技能**: engineering-data-engineer  
**估算**: 15 分钟

| ID | 二级子代理任务 | 方法概要 |
|---|---|---|
| S11.7.1 | CN ASN 映射 | AS4134(电信)/AS4837(联通)/AS9808(移动) 等 → ISP 回填验证 |
| S11.7.2 | CN isp 缺失回填 | 中国库 isp 覆盖率 from 37%~86% → 目标 95%+ |
| S11.7.3 | CN IDC 段交叉 | 新判定 IDC vs constants.IDC_IPV4_RANGES 一致性 |
| S11.7.4 | CN country 校验 | 台湾/香港/澳门 country 字段与 RIR cc 比对 |
| S11.7.5~7 | CN v4/v6 重建 + 抽样 | 重建 + 抽样验证 |
| S11.7.8~10 | 精度回归 + 报告 | evaluate_precision + 报告 |

### S11.8：QA 全量验证

**技能**: gis-qa-engineer  
**估算**: 10 分钟

| 检查项 | 通过标准 |
|---|---|
| 全球库 isp 覆盖率 | **≥ 60%**（目标 80%） |
| isp 准确率 (vs ip-api 抽查 500 条) | **≥ 80%** |
| 国家归属准确率 (vs RIR/ip-api 抽查 3000 条) | **≥ 95%** |
| IDC 判定召回 | 已知云厂商 100% 命中 |
| 家宽逻辑 | 5000 条 0 违规 |
| 精度回归 | 无回退 |
| 文件可用性 | maxminddb 打开/查询正常 |

### S11.9：性能与规模优化

**技能**: engineering-database-optimizer  
**估算**: 10 分钟

| ID | 任务 |
|---|---|
| S11.9.1 | ASN 索引内存评估（~15 万 ASN × 平均 20 前缀 ≈ 300 万条映射，~200MB） |
| S11.9.2 | 二分查找优化（同 50_mmdb_field_patch 的 bisect 模式） |
| S11.9.3 | 分块 streaming 处理，峰值内存控制 |
| S11.9.4 | 并行标注（多进程/分块，4 核） |
| S11.9.5 | RDAP 批量查询限速控制（1 req/s，15 万 ASN ≈ 42 小时后台） |
| S11.9.6 | org 名称 LRU 缓存 |
| S11.9.7 | 索引构建耗时：反查 vs 内存 |
| S11.9.8 | 调优报告 |

### S11.10：文档与部署收尾

**技能**: engineering-software-architect, engineering-data-engineer  

| ID | 任务 |
|---|---|
| S11.10.1 | README 更新（ASN 增强说明、新字段） |
| S11.10.2 | 构建脚本更新（build_outputs.ps1 加入 S11 步骤） |
| S11.10.3 | 部署脚本更新（deploy_global.ps1） |
| S11.10.4 | 数据来源文档（RIR/RouteViews/RDAP 许可说明） |
| S11.10.5 | 版本号更新 |
| S11.10.6 | 最终交付报告 |

---

## 4. 依赖与并行策略

```
S11.1 ──► S11.2 ──► S11.3 ──► S11.4 + S11.5 ──► S11.6 ──► S11.7 ──► S11.8 ──► S11.9 ──► S11.10
  RIR        BGP        标注       isp+IDC  cc     MMDB      CN        QA      调优     部署
  15min      30min      15min      20min    10min  30min     15min     10min    10min    10min
│         │           │          │              │        │          │        │         │
└─────────┴───────────┴──────────┴──────────────┴────────┴──────────┴────────┴─────────┘
  总估算: ~2 小时 45 分钟（不含 RDAP 后台 42h）
```

> ★ RDAP ASN→org 批量查询（42 小时后台）与标注重建并行，不阻塞主流程：
> - 先用 RIB 中的 AS 号回填 isp（格式 "AS15169"）
> - RDAP 完成后更新为 "Google LLC"

---

## 5. 产物清单

| 目录 | 内容 |
|---|---|
| data/raw/rib.20260824.0000.bz2 | RouteViews BGP 路由表 dump |
| data/raw/delegated-*-latest ×5 | RIR 注册文件 |
| data/bgp/ | rir 索引、asn_prefix_map、annotated CSV、QA 报告 |
| scripts/common/rir_index.py | RIR 索引公共加载器 |
| scripts/common/isp_classifier.py (更新) | org 关键字 IDC 规则 + 住宅白名单 |
| scripts/tools/50_mmdb_field_patch.py (更新) | --asn-map 参数 |
| output/global_*.mmdb (重建) | isp 字段回填 |
| docs/S11_ASN_ENRICHMENT_REPORT.md | 最终交付报告 |

---

## 6. 风险与缓解

| 风险 | 缓解 |
|---|---|
| RouteViews RIB 79MB 下载超时 | 断点续传 + 重试 3 次；备用 RIPE RIS |
| RDAP 42 小时后台耗时 | 后置不阻塞；先用 AS 号占位，后更新为 org 名称 |
| RIR 对同一 ASN 的国家冲突 | 以 BGP RIB 实际宣告来源为准 |
| anycast CDN 国家归属误判 | Cloudflare/Google/Akamai 白名单，不纠正 |
| 关键字误判住宅为 IDC | 住宅 ASN 白名单（Comcast/AT&T/中国三大运营商）优先 |
| RIB 解析内存不足 | 流式解析（pybgpkit 支持 streaming）+ 分块写入 |

---

## 附录：已验证的数据源 URL

```
# RouteViews BGP RIB dump (主通道，一次下载)
http://archive.routeviews.org/bgpdata/2026.08/RIBS/rib.20260824.0000.bz2  (79MB)

# RIR delegated (离线，国家索引)
https://ftp.ripe.net/pub/stats/ripencc/delegated-ripencc-extended-latest   (18MB)
https://ftp.apnic.net/pub/stats/apnic/delegated-apnic-extended-latest      (9.2MB)
https://ftp.arin.net/pub/stats/arin/delegated-arin-extended-latest         (12.8MB)
https://ftp.lacnic.net/pub/stats/lacnic/delegated-lacnic-extended-latest   (4.6MB)
https://ftp.afrinic.net/pub/stats/afrinic/delegated-afrinic-extended-latest (1MB)

# RDAP (ASN→org 名称，批量后台)
https://rdap.db.ripe.net/autnum/AS{number}
https://rdap.arin.net/registry/autnum/{number}

# RIPEstat (补充查询)
https://stat.ripe.net/data/network-info/data.json?resource={ip}
https://stat.ripe.net/data/as-overview/data.json?resource={asn}

# 校验抽样
http://ip-api.com/json/{ip}?fields=status,country,isp,org,as,asname
```

---

## 评审修订记录

| 版本 | 日期 | 修订内容 |
|---|---|---|
| v1.0 | 2026-08-24 | 初始版本（RIPEstat 逐 ASN 方案） |
| v2.0 | 2026-08-24 | **重大修订**：RouteViews RIB dump 替代 RIPEstat 逐 ASN 抓取（50h→30min）；新增 RDAP ASN→org 方案；新增住宅 ASN 白名单；更新工程估算；修正 S11.2 依赖关系 |
