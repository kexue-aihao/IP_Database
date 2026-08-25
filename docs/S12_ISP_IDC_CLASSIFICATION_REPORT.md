# S12 报告：基于运营商标签的 IDC 归类升级（Like ByteVirt LLC）

## 背景与目标
用户要求：当 IP 记录的 **isp（运营商标签）** 命中类似 "ByteVirt LLC" 的 IDC/云/托管运营商名称时，将其网络类型归类为**机房IP（IDC）**，即：
- `connection_type = idc`
- `is_residential = false`
- `idc_vendor = <规范运营商名>`

此前仅凭 IP 段（`IDC_IPV4_RANGES`/`IDC_IPV6_PREFIXES`/`idc_all.csv`）判断 IDC；大量携带 ByteVirt LLC / LINODE LLC / DigitalOcean / Hetzner / Amazon 等 isp 标签的段未被识别，全部落在 `residential`。本阶段补齐了这条规则。

## 执行架构（10 个子代理）
按计划创建 10 个并行子代理，每个负责 1/10 的待审 ISP 名称切片（`data/bgp/review_slices/slice_00~09.txt`，按记录数均衡切分，每片 ~42,633 条记录 / ~1,580 个 ISP）：

| 子代理 | 切片 | 判定 IDC | 判定 NON | 备注 |
|---|---|---|---|---|
| s1 | slice_00 | 73 | 1489 | 保守，质量高 |
| s2 | slice_01 | 98 | 1478 | 保守 |
| s3 | slice_02 | 312 | 1266 | 中 |
| s4 | slice_03 | 65 | 1514 | 保守（重跑后修正） |
| s5 | slice_04 | 79 | 1500 | 保守 |
| s6 | slice_05 | 70 | 1510 | 保守 |
| s7 | slice_06 | 54 | 1526 | 保守，质量高 |
| s8 | slice_07 | 83 | 1497 | 保守 |
| s9 | slice_08 | 47 | 1533 | 保守 |
| s10 | slice_09 | 491 | 1089 | 中 |

> 过程中发现 slice_03 首次输出把 1332/1579 判为 IDC（过度乐观，混入 VECTRA S.A、H3G-Austria-MNT、Telkom SA Ltd 等电信运营商），已要求该子代理按「非IDC优先」重跑，输出修正为 65/1514。

## 分类规则（三阶段）
1. **精确基调（846 ISPs）**：品牌字典（Amazon/AWS、Microsoft、Google、Alibaba、Tencent、Cloudflare、Fastly、Akamai、ByteVirt、Linode、DigitalOcean、Vultr、Hetzner、OVH、Contabo、Netcup、Hostinger、Namecheap、Equinix、Digital Realty、Zayo、Cogent、GTT、Lumen、Level 3、Colt、Zenlayer 等 200+ 品牌）+ 强关键词（\bhosting\b、\bdatacenter\b、\bcolo\b、\bvps\b、\bserver\b、\bidc\b 等）
2. **子代理审核**：10 个子代理对 15,774 个待审 ISP 逐个判定并输出 JSON
3. **否决过滤**：电信/移动运营商（TELEFÓNICA、Telenor、Vodafone、AT&T、Comcast 等）、注册表角色对象（Administration Adresses、Admin-C、IRT-*、-MNT 句柄）、政府/企业 → 剔除，不回填 IDC

## 最终结果
**ISP→IDC 映射**：`data/bgp/idc_isp_map_auto.json`（4,794 个 ISP）

**全库升级**（23 个 MMDB，含中国库与全球库）：
- `global_ipv4_residential.mmdb`：6,228,206 条，其中 **371,312 条** → idc / is_residential=false（原仅 1 条）；ByteVirt LLC (23.95.123.0/24 等 24 条) → idc/ByteVirt ✓；LINODE LLC 919 条 → idc/Linode ✓；8.8.8.8→Google Cloud；1.1.1.1→Cloudflare ✓
- `global_ipv6_residential.mmdb`：8,605,194 条，其中 **9,043 条** → idc / false（原有 0 条）
- `china_ipv4_with_isp.mmdb`：6,550 条 idc（如 1.178.31.0/24 → Amazon Web Services）
- `china_ipv4_other.mmdb` 等中国库同步升级
- 电信/联通/移动/长城等居民库不受影响（0 变更，验证通过）

**验证样例**（QA）：
| 查询 | connection_type | is_residential | idc_vendor |
|---|---|---|---|
| 8.8.8.8 | idc | false | Google Cloud |
| 1.1.1.1 | idc | false | Cloudflare |
| 23.92.16.1 (Linode) | idc | false | Linode |
| 23.95.123.1 (ByteVirt) | idc | false | ByteVirt |
| AT&T Enterprises, LLC | residential | true | — |
| Comcast Cable Communications, LLC | residential | true | — |
| Administration Adresses | residential | true | — |

## 工具变更
- `scripts/tools/50_mmdb_field_patch.py`：新增 `--idc-org-map <json>` 参数 + 执行逻辑（isp 命中映射表 → 强制 ct=idc / res=false / idc_vendor=vendor），含归一化缓存优化（避免每个记录重复 normalize）
- 新增 `data/bgp/idc_isp_map_auto.json`（4,794 ISPs 映射表，gitignored 数据目录）

## 部署
23 个 MMDB 已同步至 `E:\v2board\resources\ipdb\`（含 high_prec 系列、with_isp、idc_enriched、global residential/idc 全套）。

## 已知限制
1. **IPv6 isp 覆盖率低**（此前 S11 已知）：v6 库仅 1,496 个唯一 isp 标签（v6 ASN/RIB 数据有限），故 v6 IDC 命中率 ~0.1%（9,043/8,605,194）。后续可从 RIPE RIS v6 updates 或 RouteViews v6 RIB 补充。
2. 部分 ISP 为人工实例名（如 "ByteVirt LLC" 出现在 23.95.123.0/24 & 69.8.128.0/24 等多段），映射表按字符串匹配，若有同名不同实体属罕见情况。
3. 子代理系统在该环境下成功率约 30%（首次运行 10 个中 3 个成功），重试后 10/10 全部完成（其中两次需要 send_message 重跑修正）。
