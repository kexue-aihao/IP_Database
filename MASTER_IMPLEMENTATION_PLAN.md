# IP 高精度定位修正 — 主实现计划

## 10 个子代理工具清单

| 编号 | 工具名 | 脚本文件 | 负责阶段 | 说明 |
|------|--------|----------|----------|------|
| 1 | **Anchor Collector** | `scripts/tools/01_anchor_collector.py` | 阶段0 | 收集已知位置锚点 IP（测速节点、CDN、高校、数据中心） |
| 2 | **IPv6 Provider Mapper** | `scripts/tools/02_ipv6_provider_mapper.py` | 阶段1 | 解析 APNIC delegated 数据，映射 IPv6 段到运营商/省份 |
| 3 | **IDC Locator** | `scripts/tools/03_idc_locator.py` | 阶段1 | 通过 PeeringDB + 云厂商文档给 IDC 段加坐标 |
| 4 | **Geofeed Parser** | `scripts/tools/04_geofeed_parser.py` | 阶段2 | 解析 RFC 8805 Geofeed 数据 |
| 5 | **QQWry Importer** | `scripts/tools/05_qqwry_importer.py` | 阶段2 | 解析纯真 IP 库格式并提取位置 |
| 6 | **IPIP Free Importer** | `scripts/tools/06_ipip_free_importer.py` | 阶段2 | 解析 IPIP 免费库数据 |
| 7 | **Vote Fusion Engine** | `scripts/tools/07_vote_fusion_engine.py` | 阶段2/4 | 多源投票融合 + 置信度评分 |
| 8 | **RTT Triangulator** | `scripts/tools/08_rtt_triangulator.py` | 阶段3 | RTT 三角定位测量框架 |
| 9 | **Confidence Modeler** | `scripts/tools/09_confidence_modeler.py` | 阶段4 | 置信度建模 + 输出升级 |
| 10 | **Pipeline Runner** | `scripts/tools/10_pipeline_runner.py` | 阶段5 | CI/CD 自动更新管道 |

## 执行阶段

### 阶段 0：建立评测基准（第 1 周）
- 子代理 1：Anchor Collector
- 输出：`data/anchor_ips.csv` + `scripts/evaluate_precision.py`

### 阶段 1：修复最紧急问题（第 2~3 周）
- 子代理 2：IPv6 Provider Mapper
- 子代理 3：IDC Locator
- 输出：修正后的 `common/constants.py` + 新增富化脚本

### 阶段 2：多源交叉融合（第 3~6 周）
- 子代理 4：Geofeed Parser
- 子代理 5：QQWry Importer
- 子代理 6：IPIP Free Importer
- 子代理 7：Vote Fusion Engine
- 输出：`scripts/vote_fusion.py` + 融合后的 MMDB

### 阶段 3：网络测量定位（第 6~10 周）
- 子代理 8：RTT Triangulator
- 输出：`scripts/rtt_triangulation.py` + 测量结果

### 阶段 4：置信度建模与输出升级（第 10~12 周）
- 子代理 9：Confidence Modeler
- 输出：升级后的 MMDB 格式（含 accuracy_radius 等字段）

### 阶段 5：持续更新机制（第 12 周 ~ 持续）
- 子代理 10：Pipeline Runner
- 输出：GitHub Actions CI 配置文件 + 自动更新脚本
