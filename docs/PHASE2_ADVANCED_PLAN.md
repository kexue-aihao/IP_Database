
# 高精度定位修正 · 第二阶段推进计划（优先级 1+2）

> 基于上一阶段（基线 91.77% 省精度 / 75.17% 市精度）的改进决议：
> **优先级1**：补全 DB-IP 英文城市名 → 中文映射（3,714 个待映射）
> **优先级2**：接入真实 RFC 8805 geofeed 数据（替换全部 404 的旧 URL）

## 一、现状侦察结论（2026-08-24 实测）

| 项目 | 结论 |
|------|------|
| DB-IP 城市名 | 127,744 条记录中 **3,714 个唯一英文/拼音城市名**，仅 2 个已是中文 |
| 现有 EN_TO_CN_CITY | 仅 ~80 条映射（07 号脚本内硬编码）→ 需扩展为独立词典 |
| AreaCity 数据 | `data/ok_data_level3.csv`（地级市）+ `ok_data_level4.csv`（区县），**含 pinyin 字段**，可作匹配依据 |
| CAIDA geofeed | ✅ **有效**：`publicdata.caida.org/datasets/geofeed-whois/2026/06/10/registries/apnic/standard/`，505 个文件、26 个含 CN 记录（google-geo-feed 519 行 CN） |
| sapics user-country | ✅ **有效**：`user-country-ipv4.csv`（8.7MB，国家粒度，仅验证用） |
| 旧 geofeed URL（04 脚本） | ❌ 全部 404（`geofeed/`、`whois/` 目录已移除） |

## 二、10 个子代理分工协同

### 链路 A — 城市名映射（优先级 1）
| # | 子代理名 | 输入 | 输出 | 方法 |
|---|----------|------|------|------|
| S1 | **城市名全量提取器** | `dbip_china_records.csv` | `data/dbip_city_names.json` | 提取 3,714 城市名 + 频次统计，规范化 |
| S2 | **中英城市词典构建器** | `ok_data_level3/4.csv` | `data/china_city_dict.json` | 地级市+区县中文名/拼音/GB/T 2260 码索引 |
| S3 | **拼音模糊匹配器** | S1 + S2 | `data/city_map_pinyin.json` | 拼音前缀/子串/Levenshtein 匹配（fuzzywuzzy） |
| S4 | **坐标就近匹配器** | 未匹配项 + `ok_geo.csv` | `data/city_map_coords.json` | 最近城市中心（20km 阈值） |
| S5 | **映射合成 QA** | S3 + S4 + 别名表 | `data/city_map_final.json` | 合并去冲突、地域别名（Amoy→厦门、Sai Kung→西贡）、覆盖率报告 |

### 链路 B — geofeed 接入（优先级 2）
| # | 子代理名 | 输入 | 输出 | 方法 |
|---|----------|------|------|------|
| S6 | **geofeed 主源下载器** | CAIDA 目录 + sapics | `data/geofeed/china_geofeed_raw.csv` | 并发下载 505 文件抽取 CN 行 + sapics 国家段 |
| S7 | **geofeed 解析标准化器** | S6 | `data/geofeed/china_geofeed_norm.csv` | prefix→start/end，CN-XX 区域码→省，清洗去重 |
| S8 | **融合引擎升级器** | S5 + S7 | `output/china_ipv4_fused_v2.csv` | 改造 07 脚本：+geofeed 源(权重0.9)、+city_map 动态加载 |

### 链路 C — 重建评测（汇合）
| # | 子代理名 | 输入 | 输出 | 方法 |
|---|----------|------|------|------|
| S9 | **MMDB 重建评测器** | S8 | `output/china_ipv4_high_prec_v2.mmdb` + `precision_report_v2.json` | 跑 09 建模 + evaluate_precision 对比基线 |
| S10 | **QA 总检与报告器** | S5/S7/S8/S9 | `output/improvement_report_v2.json` + 文档更新 | 覆盖率、指标可视化、结论归档 |

### 依赖拓扑
```
S1 ──┐
S2 ──┼─> S3 ─┐
     │        ├─> S5 ─┐
S4 ──┘        │       ├─> S8 ─> S9 ─> S10
S6 ───────────┴─> S7 ──┘
```
并行批次：{S1,S2,S6} 同时 → {S3,S4,S7} 同时 → {S5,S8} 同时 → S9 → S10

## 三、技能调用映射
- **gis-spatial-data-engineer**：S2/S4/S6/S7（空间 ETL、坐标归一、格式转换）
- **gis-qa-engineer**：S5/S10（数据质量门禁、精度评估、覆盖审计）
- **engineering-data-engineer**：S1/S3/S8（管线建设、schema 纪律、融合逻辑）

## 四、成功标准
1. 城市名映射覆盖 ≥ 3,000/3,714（≥80%），其中高置信 ≥ 2,500
2. 城市准确率 **> 78.2%（超越原基线）**，省准确率保持 ≥ 91.7%
3. geofeed 真实数据落库 ≥ 500 条 CN 段，纳入融合权重
4. 输出可复用的 `data/city_map_final.json` + `data/geofeed/china_geofeed_norm.csv`
