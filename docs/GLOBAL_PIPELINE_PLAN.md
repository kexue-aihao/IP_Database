# 全球 IP 归属地数据库 · 完整更新动工计划

> 目标：构建 global_ipv4_residential.mmdb、global_ipv4_idc.mmdb、global_ipv6_residential.mmdb、global_ipv6_idc.mmdb 四个完整 MMDB 库
> 方法：10 个主代理 × 10 个嵌套子代理 = 100 子代理协同，三层管线（采集→分类→融合→构建→评测→部署）
> 技能：gis-spatial-data-engineer, engineering-data-engineer, engineering-software-architect, gis-qa-engineer, engineering-database-optimizer

---

## 管线总览

```
[数据源层]                    [处理层]                    [产出层]
ip2region (37M+77M) ─┐
                      ├─> S1 数据摄入 ─┐
DB-IP City (88M) ────┘               │
                                      ├─> S2 IDC收集 ─┐
PeeringDB ────────────────────────────┘               │
                                                      ├─> S3 分类 ─┐
Cloud Provider APIs ──────────────────────────────────┘            │
                                                                     ├─> S4 区域归一 ─┐
APNIC/RIPE/ARIN ────────────────────────────────────────────────────┘               │
                                                                                      ├─> S5 融合 ─┐
ISO 3166-2 数据 ──────────────────────────────────────────────────────────────────────┘            │
                                                                                                       ├─> S6 置信度 ─┐
已知 ISP/IDC 清单 ─────────────────────────────────────────────────────────────────────────────────────┘              │
                                                                                                                        ├─> S7 IPv4 Residential MMDB ─┐
                                                                                                                        │                              ├─> S10 部署
                                                                                                                        ├─> S8 IPv6+IDC MMDB ──────────┘
                                                                                                                        │
                                                                                                                        └─> S9 评测 QA
```

---

## 子代理 1：全球数据摄入与标准化（S1）

**技能**：gis-spatial-data-engineer, engineering-data-engineer

| 嵌套 | 名称 | 输入 | 输出 | 方法 |
|------|------|------|------|------|
| S1.1 | ip2region IPv4 全量解析器 | `data/ip2region_data/ipv4_source.txt` | `data/global/ip2region_v4.csv` | 解析所有国家（非仅 CN），统一字段结构 |
| S1.2 | ip2region IPv6 全量解析器 | `data/ip2region_data/ipv6_source.txt` | `data/global/ip2region_v6.csv` | IPv6 范围转为 start/end IP |
| S1.3 | DB-IP 全球解析器 | `data/dbip-city-lite-2026-07.csv.gz` | `data/global/dbip_global.csv` | 过滤所有国家，保留全部字段 |
| S1.4 | DB-IP 国家代码校验器 | S1.3 输出 | `data/global/dbip_country_validated.csv` | ISO 3166-1 alpha-2 校验，修复常见错误 |
| S1.5 | IP 范围去重合并器 | S1.1 + S1.2 + S1.4 | `data/global/deduped_v4.csv`, `data/global/deduped_v6.csv` | 按 (start_ip,end_ip) 去重，保留置信度最高的源 |
| S1.6 | 坐标格式标准化器 | S1.5 输出 | `data/global/coords_normalized.csv` | 确保 (lat,lng) 在合理范围，标记 (0,0) 为无效 |
| S1.7 | 重叠范围检测器 | S1.6 输出 | `data/global/overlap_report.json` | 检测 IP 范围重叠，标记冲突区域 |
| S1.8 | 国家洲际归类器 | S1.6 输出 | `data/global/country_continent.csv` | 添加 continent 字段，便于分块处理 |
| S1.9 | 数据质量快照 | S1.6 输出 | `data/global/ingestion_quality.json` | 记录各源行数、缺失率、异常值 |
| S1.10 | Schema 统一输出 | 全部 S1 子代理 | `data/global/global_raw_fused.csv` | 统一列名：start_ip,end_ip,country,region,city,lat,lng,source |

**S1 依赖**：无（原始数据层）
**S1 产出**：原始数据统一 CSV + 质量报告

---

## 子代理 2：IDC/云厂商 IP 范围收集器（S2）

**技能**：engineering-data-engineer, gis-spatial-data-engineer

| 嵌套 | 名称 | 输入 | 输出 | 方法 |
|------|------|------|------|------|
| S2.1 | AWS IP 范围爬取 | `https://ip-ranges.amazonaws.com/ip-ranges.json` | `data/global/idc/aws_ranges.csv` | AWS 官方 JSON API→ CSV |
| S2.2 | Azure IP 范围爬取 | `https://download.microsoft.com/download/...` | `data/global/idc/azure_ranges.csv` | Azure 官方 XML/JSON |
| S2.3 | GCP IP 范围爬取 | `https://www.gstatic.com/ipranges/cloud.json` | `data/global/idc/gcp_ranges.csv` | GCP 官方 JSON |
| S2.4 | 阿里云/腾讯云/华为云 | 厂商文档爬取 + 现有 `scripts/common/constants.py` | `data/global/idc/cn_cloud.csv` | 扩展现有 IDC 范围 |
| S2.5 | 国际主机商（DO/Linode/Vultr） | 各厂商官方 IP 列表 | `data/global/idc/hosting_intl.csv` | DigitalOcean, Linode, Vultr, UpCloud 等 |
| S2.6 | 欧洲主机商（OVH/Hetzner） | 官方 IP 列表 + RIPE 数据 | `data/global/idc/hosting_eu.csv` | OVH, Hetzner, Scaleway, Ionos |
| S2.7 | 亚洲主机商 | 各区域厂商文档 | `data/global/idc/hosting_asia.csv` | 日本/韩国/新加坡等 |
| S2.8 | PeeringDB 设施数据挖掘 | 已有 `data/global_cloud_providers.json` | `data/global/idc/peeringdb_fac.csv` | 扩展已有 PeeringDB 设施坐标 |
| S2.9 | ASN→组织映射聚合器 | APNIC/RIPE/ARIN/AFRINIC/LACNIC delegated | `data/global/idc/asn_org_map.csv` | 合并五大 RIR 数据 |
| S2.10 | IDC 范围合并去重 | S2.1~S2.9 | `data/global/idc/idc_all.csv` | 合并、去重、标记供应商 |

**S2 依赖**：S1（IDC 范围需要 IP 格式一致）
**S2 产出**：全球 IDC 段 CSV + 供应商映射

---

## 子代理 3：住宅 vs IDC 分类器（S3）

**技能**：engineering-data-engineer, engineering-software-architect

| 嵌套 | 名称 | 输入 | 输出 | 方法 |
|------|------|------|------|------|
| S3.1 | ASN 组织关键词分类器 | S2.9 + WHOIS 数据 | `data/global/classify/asn_keywords.csv` | 关键词正则匹配：hosting/cloud/datacenter→IDC，isp/broadband→residential |
| S3.2 | BGP 前缀分析器 | 路由表转储分析 | `data/global/classify/bgp_profile.csv` | 分析前缀宣告模式（/24 vs /19 暗示不同用途） |
| S3.3 | WHOIS 组织描述解析器 | WHOIS 数据库 | `data/global/classify/org_type.csv` | 解析 org 描述字段，归类为 ISP/企业/教育/政府 |
| S3.4 | 已知 ISP 全球范围库 | 各运营商公开 IP 段 | `data/global/classify/known_isp.csv` | 各国有线/光纤/DSL 运营商 |
| S3.5 | 已知托管商全球库 | S2.1~S2.7 | `data/global/classify/known_hosting.csv` | 已知 IDC 段 |
| S3.6 | 移动运营商范围 | 各 MNO 公开 IP 段 | `data/global/classify/mobile_carrier.csv` | 蜂窝网络分配（3GPP 分配） |
| S3.7 | 教育机构范围 | edu 域名 WHOIS | `data/global/classify/educational.csv` | 各大学/教育网段 |
| S3.8 | 政府/军事范围 | gov/mil WHOIS | `data/global/classify/gov_mil.csv` | 政府/军事段 |
| S3.9 | 分类置信度评分器 | S3.1~S3.8 | `data/global/classify/classification_scores.csv` | 多源投票→IDC/residential/unknown 三分类 + 置信度 |
| S3.10 | 分类冲突解决器 | S3.9 | `data/global/classify/final_classification.csv` | 处理冲突（如某段同时被标记为 ISP 和 hosting），按权重仲裁 |

**S3 依赖**：S1, S2
**S3 产出**：每条 IP 段的 residential/IDC/unknown 分类

---

## 子代理 4：区域/省份/州标准化器（S4）

**技能**：gis-spatial-data-engineer

| 嵌套 | 名称 | 输入 | 输出 | 方法 |
|------|------|------|------|------|
| S4.1 | 美国州名标准化 | ISO 3166-2 US | `data/global/regions/us_states.csv` | US-CA→加利福尼亚, US-NY→纽约 |
| S4.2 | 中国省份（已有成果） | 现有 `china_city_dict.json` | `data/global/regions/cn_provinces.csv` | 复用现有成果 |
| S4.3 | 欧盟国家-区域映射 | ISO 3166-2 + NUTS | `data/global/regions/eu_regions.csv` | DE-BY→巴伐利亚, FR-IDF→法兰西岛 |
| S4.4 | 英国郡/区映射 | ISO 3166-2 GB | `data/global/regions/uk_counties.csv` | GB-ENG→英格兰, GB-SCT→苏格兰 |
| S4.5 | 日本都道府县 | ISO 3166-2 JP | `data/global/regions/jp_prefectures.csv` | JP-13→东京都, JP-27→大阪府 |
| S4.6 | 韩国/东南亚 | ISO 3166-2 KR/TH/VN/ID | `data/global/regions/sea_regions.csv` | 韩国/泰国/越南/印尼 |
| S4.7 | 拉丁美洲 | ISO 3166-2 BR/AR/MX | `data/global/regions/latam_regions.csv` | 巴西/阿根廷/墨西哥 |
| S4.8 | 大洋洲 | ISO 3166-2 AU/NZ | `data/global/regions/oceania_regions.csv` | 澳大利亚州/新西兰区 |
| S4.9 | 非洲/中东 | ISO 3166-2 ZA/NG/AE/SA | `data/global/regions/africa_mideast.csv` | 南非/尼日利亚/阿联酋/沙特 |
| S4.10 | 南亚 | ISO 3166-2 IN/PK/BD | `data/global/regions/south_asia.csv` | 印度/巴基斯坦/孟加拉 |

**S4 依赖**：S1（使用 S1 产生的区域名做映射）
**S4 产出**：全球区域名→中文/英文标准名映射表

---

## 子代理 5：全球投票融合引擎（S5）

**技能**：engineering-data-engineer, engineering-software-architect

| 嵌套 | 名称 | 输入 | 输出 | 方法 |
|------|------|------|------|------|
| S5.1 | 数据源权重校准器 | S1 质量报告 | `data/global/fusion/source_weights.json` | 基于源覆盖率、精度、时效性设定权重 |
| S5.2 | 按国家分块处理器 | S1.8 + S1.10 | `data/global/fusion/chunked/` | 按国家/洲分块，避免内存溢出 |
| S5.3 | 投票融合核心（IPv4 分块） | S5.2 | `data/global/fusion/v4_fused_chunk/` | 加权多数投票，每个 IP 段 |
| S5.4 | 投票融合核心（IPv6 分块） | S5.2 | `data/global/fusion/v6_fused_chunk/` | IPv6 段投票融合 |
| S5.5 | 坐标融合（加权平均） | S5.3 + S5.4 | `data/global/fusion/coords_fused/` | 按权重平均坐标 |
| S5.6 | 冲突解决引擎 | S5.5 | `data/global/fusion/conflict_resolved/` | 同 IP 段不同省份→按置信度仲裁 |
| S5.7 | 多语言城市名归一化 | S5.6 + S4 | `data/global/fusion/city_normalized/` | 识别同一城市的不同语言表示 |
| S5.8 | 国际边界处理 | S5.7 | `data/global/fusion/border_fixed/` | 解决边界附近 IP 的归属争议 |
| S5.9 | 融合质量指标 | S5.8 | `data/global/fusion/fusion_quality.json` | 记录每块融合的统计指标 |
| S5.10 | 融合输出合并 | S5.8 | `data/global/fusion/global_fused_v4.csv`, `data/global/fusion/global_fused_v6.csv` | 合并所有分块为最终融合 CSV |

**S5 依赖**：S1, S4
**S5 产出**：全球融合 CSV（IPv4 + IPv6）

---

## 子代理 6：全球置信度建模器（S6）

**技能**：engineering-data-engineer, engineering-software-architect

| 嵌套 | 名称 | 输入 | 输出 | 方法 |
|------|------|------|------|------|
| S6.1 | 源可靠性评分 | S1.9 + S5.1 | `data/global/confidence/source_reliability.json` | 基于历史命中率评分 |
| S6.2 | 坐标精度半径 | S5.5 | `data/global/confidence/accuracy_radius.csv` | 根据源类型和置信度设定半径 |
| S6.3 | 共识置信度 | S5.3 | `data/global/confidence/consensus_score.csv` | 多源一致→高置信，单源→低置信 |
| S6.4 | 单源回退策略 | S6.3 | `data/global/confidence/single_source_fallback.csv` | 单源且未知→国家级别，不提供城市 |
| S6.5 | 行政中心 vs 精确坐标 | S5.5 | `data/global/confidence/geo_level.csv` | 标记 precise_city / admin_center / country |
| S6.6 | 数据时效性衰减 | 时间戳分析 | `data/global/confidence/temporal_decay.csv` | 数据越旧→置信度越低 |
| S6.7 | 国家级别回退链 | S6.4 | `data/global/confidence/fallback_chain.csv` | 城市→省份→国家→未知 |
| S6.8 | 置信度直方图 | S6.3 | `data/global/confidence/histogram.json` | 置信度分布报告 |
| S6.9 | 质量门控阈值 | S6.8 | `data/global/confidence/quality_gates.json` | 定义哪些记录进入 MMDB |
| S6.10 | MMDB 数据结构设计 | S6.9 | 数据字典 | 定义最终 MMDB 字段结构 |

**S6 依赖**：S5
**S6 产出**：置信度标注 + 质量门控规则

---

## 子代理 7：IPv4 Residential MMDB 构建器（S7）

**技能**：engineering-database-optimizer, engineering-data-engineer

| 嵌套 | 名称 | 输入 | 输出 | 方法 |
|------|------|------|------|------|
| S7.1 | CIDR 汇总优化 | S5.10 + S3.10 | `data/global/mmdb/v4_residential_cidrs.csv` | 连续 IP 范围合并为 CIDR |
| S7.2 | Residential 过滤器 | S7.1 + S3 | `data/global/mmdb/v4_residential_filtered.csv` | 仅保留 type=residential 的记录 |
| S7.3 | 分块 MMDB 写入器 | S7.2 | `data/global/mmdb/v4_residential_chunks/` | 分块插入，避免 MMDBWriter 内存溢出 |
| S7.4 | 大文件内存管理 | S7.3 | 运行时监控 | 每 10 万条写一次，GC 回收 |
| S7.5 | 字段 Schema 验证 | S6.10 | 验证报告 | 确保每条记录包含所有必需字段 |
| S7.6 | 索引优化 | MMDB 构建 | `output/global_ipv4_residential.mmdb` | 优化 MMDB 的二分查找树 |
| S7.7 | 数据完整性校验 | S7.6 | 校验报告 | 随机抽样查询验证 |
| S7.8 | 大小优化 | S7.6 | 大小报告 | 移除冗余字段，压缩 |
| S7.9 | v2board 字段兼容 | S7.8 | 兼容性报告 | 确保字段名与 v2board 现有格式一致 |
| S7.10 | 构建验证测试 | S7.9 | 验证报告 | 查询测试：已知 IP 段返回预期结果 |

**S7 依赖**：S5, S6, S3
**S7 产出**：`output/global_ipv4_residential.mmdb`（50-60MB）

---

## 子代理 8：IPv6 + IDC MMDB 构建器（S8）

**技能**：engineering-database-optimizer, gis-spatial-data-engineer

| 嵌套 | 名称 | 输入 | 输出 | 方法 |
|------|------|------|------|------|
| S8.1 | IPv6 CIDR 展开 | S5.10 | `data/global/mmdb/v6_cidrs.csv` | IPv6 范围→CIDR（MMDBWriter 需要） |
| S8.2 | IPv6 Residential 过滤 | S8.1 + S3 | `data/global/mmdb/v6_residential.csv` | 仅保留 residential |
| S8.3 | IPv6 Residential MMDB | S8.2 | `output/global_ipv6_residential.mmdb` | 使用 MMDBWriter(ip_version=6) |
| S8.4 | IPv4 IDC 过滤 | S5.10 + S2 | `data/global/mmdb/v4_idc.csv` | 仅保留 IDC 分类 |
| S8.5 | IPv6 IDC 过滤 | S8.1 + S2 | `data/global/mmdb/v6_idc.csv` | IPv6 IDC 段 |
| S8.6 | MMDBWriter IPv6 模式 | S8.3 + S8.5 | 模式验证 | 确保 ip_version=6 参数正确 |
| S8.7 | 批量插入优化 | S8.3 + S8.5 | 性能日志 | 批量插入减少写入次数 |
| S8.8 | IPv4/IPv6 Schema 兼容 | S8.4 + S8.5 | 兼容性报告 | 确保四库字段统一 |
| S8.9 | IPv6 坐标密度检查 | S8.2 | 密度报告 | IPv6 坐标通常稀疏，标记低密度区域 |
| S8.10 | 四库构建验证 | 全部 S8 产出 | 验证报告 | 四库完整性检查 |

**S8 依赖**：S5, S6, S3, S2
**S8 产出**：`output/global_ipv6_residential.mmdb` + `output/global_ipv4_idc.mmdb` + `output/global_ipv6_idc.mmdb`

---

## 子代理 9：全球评测与 QA（S9）

**技能**：gis-qa-engineer, engineering-data-engineer

| 嵌套 | 名称 | 输入 | 输出 | 方法 |
|------|------|------|------|------|
| S9.1 | 全球锚点采集 | PeeringDB + 各 RIR 验证数据 | `data/global/anchors/global_anchors.csv` | 10 万+ 全球锚点 |
| S9.2 | 省份/州准确率评测 | S7 + S8 + S9.1 | 准确率报告 | 按国家/区域分别统计 |
| S9.3 | 城市准确率评测 | S7 + S8 + S9.1 | 城市准确率报告 | 对比 v2board 旧库 |
| S9.4 | 坐标距离评测 | S7 + S8 + S9.1 | 距离分布报告 | 中位数/平均/50km 占比 |
| S9.5 | Residential/IDC 分类准确率 | S7/S8 vs S2 | 分类准确率报告 | IDC 是否被误判为 residential |
| S9.6 | 回归测试：旧库 vs 新库 | S7 + S8 + 旧库 | 回归报告 | 抽样 10 万条，新旧库对比 |
| S9.7 | 区域准确率分解 | S9.2 | 区域报告 | 欧美/亚太/拉美/非分别统计 |
| S9.8 | 边界情况分析 | S9.2~S9.7 | 边界报告 | 分析最差 10% 区域 |
| S9.9 | 性能基准测试 | S7 + S8 | 性能报告 | 查询速度、内存占用 |
| S9.10 | QA 总报告 | S9.2~S9.9 | `output/global_qa_report.json` | 合并所有评测结果 |

**S9 依赖**：S7, S8
**S9 产出**：全球精度评测报告

---

## 子代理 10：部署与文档（S10）

**技能**：engineering-software-architect, gis-qa-engineer

| 嵌套 | 名称 | 输入 | 输出 | 方法 |
|------|------|------|------|------|
| S10.1 | 旧库备份 | v2board 现有 `resources/ipdb/*.mmdb` | `backup_global_${date}/` | 时间戳命名备份 |
| S10.2 | 四库替换 | S7 + S8 + S10.1 | v2board `resources/ipdb/` | 替换 global_ipv4/residential, global_ipv6/residential, global_ipv4_idc, global_ipv6_idc |
| S10.3 | 替换完整性验证 | S10.2 | 完整性报告 | 四库文件大小、字段对比 |
| S10.4 | 回滚脚本 | S10.1 | `rollback_global.ps1` | 一键恢复旧库 |
| S10.5 | 管线架构文档 | 全部 S1~S9 | `docs/GLOBAL_PIPELINE.md` | 架构图、数据流、依赖关系 |
| S10.6 | 数据源文档 | S1, S2 | `docs/DATA_SOURCES.md` | 各数据源 URL、更新频率、许可 |
| S10.7 | 配置指南 | S5.1, S6.9 | `docs/CONFIGURATION.md` | 权重调整、质量门控阈值 |
| S10.8 | 运行监控指南 | 全部 | `docs/MONITORING.md` | 定期更新流程、健康检查 |
| S10.9 | Pipeline Runner 更新 | S10.5~S10.8 | `scripts/tools/global_pipeline_runner.py` | 全局管线的 CI/CD 脚本 |
| S10.10 | 最终交付报告 | S9 + S10.1~S10.9 | `output/global_delivery_report.json` | 所有成果汇总 |

**S10 依赖**：S7, S8, S9
**S10 产出**：已替换的 v2board 库 + 完整文档 + 回滚脚本

---

## 依赖拓扑

```
S1 ──┬──> S4 ──> S5 ──┬──> S6 ──┬──> S7 ──┬──> S9 ──┬──> S10
     │                 │         │         │         │
S2 ──┤                 │         │         ├──> S8 ──┤
     ├──> S3 ──────────┘         │         │         │
S1 ──┘                           └──> S6 ──┘         │
                                                      │
                                              S10 ────┘
```

**并行批次**：
- 第一批：S1, S2（采集层，并行）
- 第二批：S3, S4（分类层，S1 依赖）
- 第三批：S5, S6（融合层，依赖 S3+S4）
- 第四批：S7, S8（构建层，并行，依赖 S5+S6+S3）
- 第五批：S9（评测，依赖 S7+S8）
- 第六批：S10（部署，依赖 S7+S8+S9）

---

## 技能调用映射

| 子代理群 | 技能 | 作用 |
|----------|------|------|
| S1, S4, S8 | **gis-spatial-data-engineer** | 空间 ETL、坐标归一、格式转换、区域映射 |
| S1, S2, S3, S5, S6 | **engineering-data-engineer** | 管线建设、数据质量、融合逻辑、置信度 |
| S3, S5, S10 | **engineering-software-architect** | 架构设计、分类策略、系统设计 |
| S9, S10 | **gis-qa-engineer** | 质量门禁、精度评估、覆盖审计 |
| S7, S8 | **engineering-database-optimizer** | MMDB 索引优化、内存管理、查询性能 |

---

## 成功标准

1. 四库产出：所有 4 个 `global_*.mmdb` 文件成功构建，可被 v2board 正常加载
2. 新库体积：global_ipv4_residential ≈ 50-60MB，与旧库（55MB）相近
3. 精度不低于旧库：抽样 10 万条对比，新库准确率不低于旧库
4. IDC 分类：已知 IDC 段被正确分类为 IDC 而非 residential
5. 替换无破坏：替换后 v2board 服务正常运行，查询无异常
6. 文档完整：所有 6 份文档 + 1 个回滚脚本 + 1 个 pipeline runner 就绪
