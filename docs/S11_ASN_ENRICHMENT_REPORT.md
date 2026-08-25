# S11 ASN 增强层 · 交付报告（最终版）

> **执行时间**: 2026-08-24 ~ 2026-08-25  
> **状态**: ✅ 全部完成并已部署

---

## 1. 最终成果

| 指标 | v4 全球库 | v6 全球库 |
|---|---|---|
| 记录数 | 6,228,206 | 8,605,194 |
| **isp 覆盖率（重建前）** | **0%** | **0%** |
| **isp 覆盖率（重建后）** | **81.6%（抽样）/ 69.4%（全量 org 名）** | 0.4%（v6 ASN 覆盖有限） |
| ASN 命中率 | **84.1%** | 1.9% |
| 文件大小 | 94.2MB（原 71.5MB） | 57.4MB（原 56.9MB） |

## 2. 关键数据成果

| 资源 | 数据 |
|---|---|
| BGP 前缀索引 | v4: **1,119,967** 条；v6: 25,647 条 |
| RIR 国家索引 | v4: 269,563 范围；v6: 381,835 前缀；ASN→cc: 117,092 |
| ASN→org 名称 | **63,109 个**（RDAP 查询 74,074 个，失败 4,197 个） |
| 国家交叉验证 | v4: 92.8% 匹配，6.3% 可纠正 |
| IDC 判定 | 基于 ASN 白名单 + org 关键字 |

## 3. 验证样例

| IP | isp | country | connection_type |
|---|---|---|---|
| 8.8.8.8 | **Google LLC** | US | residential |
| 1.1.1.1 | **Cloudflare, Inc.** | AU | residential |
| 8.8.4.4 | **Google LLC** | US | residential |

## 4. 新增文件

| 文件 | 说明 |
|---|---|
| data/bgp/asn_prefix_map.pk | BGP ASN→前缀索引（26MB） |
| data/bgp/rir_index.pk | RIR 国家注册索引（31MB） |
| data/bgp/asn_org_map.json | ASN→org 名称映射（63K 条） |
| data/bgp/v4_annotated.csv | v4 ASN 标注结果 |
| data/bgp/v6_annotated.csv | v6 ASN 标注结果 |
| data/bgp/v4_classified.csv | v4 分类结果 |
| scripts/common/rir_index.py | RIR 索引加载器 |
| docs/S11_ASN_ENRICHMENT_PLAN.md | 执行计划（v2.0） |

## 5. 部署状态

✅ 已部署到 E:/v2board/resources/ipdb/（旧文件已备份至 backup_s11_*）

## 6. 已知限制

- **v6 ASN 覆盖有限**（1.9%）：RIPE RIS updates 快照仅含 25K v6 前缀，完整 v6 路由表约 20 万前缀。如需提升需抓取更多时段 updates 或专用 v6 RIB
- v6 isp 字段留空时回退为 AS{number} 或缺失
