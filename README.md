# 中国 IP 完整归属地数据库 (IPv4 + IPv6) — MaxMind DB 格式

基于 [ip2region](https://github.com/lionsoul2014/ip2region) + [GeoCN](https://github.com/ljxi/GeoCN) + [APNIC](https://ftp.apnic.net/pub/stats/apnic/delegated-apnic-latest) + 多源融合构建的 **IP 地理定位与网络类型分类数据库**，提供 **MaxMind DB (.mmdb)** 格式输出，支持 IPv4/IPv6 双栈。

**核心特色：**
- 🏠 **家宽/IDC 智能分类** — 非 IDC 数据中心 IP 自动判定为家宽（住宅），支持 4,794+ 家云/托管运营商标签识别
- 🌍 **中国 + 全球双库** — 中国区县级精度 + 全球 ASN 级覆盖
- 📍 **23 个细分库** — 按运营商/类型/精度分库，适配不同场景
- ⚡ **MaxMind DB 格式** — 高性能二进制树，微秒级查询
- 🔄 **自动化流水线** — S1~S12 多阶段构建，10×10 子代理并行编排

---

## 快速使用

### Python (maxminddb)

```bash
pip install maxminddb
```

```python
import maxminddb

# 查询中国 IP 归属地
reader = maxminddb.open_database('output/china_ipv4.mmdb')
result = reader.get('1.0.1.0')
print(result)
# {'province': '福建', 'city': '福州', 'isp': '中国电信',
#  'connection_type': 'residential', 'is_residential': True,
#  'latitude': 26.07, 'longitude': 119.30, ...}

# 查询云厂商 IP
result = reader.get('8.129.0.0')
print(result['connection_type'], result['is_residential'])
# idc False

# 查询全球 IP
reader = maxminddb.open_database('output/global_ipv4_residential.mmdb')
result = reader.get('8.8.8.8')
print(result['isp'], result['connection_type'])
# Google LLC idc
reader.close()
```

### 判断家宽/IDC

```python
def is_residential(reader, ip):
    result = reader.get(ip)
    return result.get('is_residential', False) if result else None

def is_idc(reader, ip):
    result = reader.get(ip)
    return result.get('connection_type') == 'idc' if result else None
```

---

## 数据库文件说明

### 中国库 (China)

| 文件 | 大小 | 说明 |
|------|------|------|
| `china_ipv4.mmdb` | 1.3 MB | IPv4 归属地（含 isp、connection_type） |
| `china_ipv4_with_isp.mmdb` | 3.0 MB | IPv4 归属地 + ASN 增强 isp 字段 |
| `china_ipv4_high_prec.mmdb` | 2.6 MB | IPv4 高精度（区县级为主） |
| `china_ipv4_high_prec_v2.mmdb` | 2.6 MB | IPv4 高精度 v2（含边界修正） |
| `china_ipv4_idc.mmdb` | 3.6 KB | IPv4 已知 IDC 范围 |
| `china_ipv4_idc_enriched.mmdb` | 2.0 KB | IPv4 IDC + ASN 增强 |
| `china_ipv4_telecom.mmdb` | 390 KB | 中国电信 IPv4 段 |
| `china_ipv4_unicom.mmdb` | 262 KB | 中国联通 IPv4 段 |
| `china_ipv4_mobile.mmdb` | 332 KB | 中国移动 IPv4 段 |
| `china_ipv4_other.mmdb` | 519 KB | 其他运营商 IPv4 段 |
| `china_ipv6.mmdb` | 253 KB | IPv6 归属地 |
| `china_ipv6_with_isp.mmdb` | 452 KB | IPv6 + ASN 增强 isp |
| `china_ipv6_enriched.mmdb` | 253 KB | IPv6 增强版 |
| `china_ipv6_idc.mmdb` | 5.2 KB | IPv6 已知 IDC 范围 |
| `china_ipv6_idc_enriched.mmdb` | 1.3 KB | IPv6 IDC + ASN 增强 |
| `china_ipv6_telecom.mmdb` | 33 KB | 中国电信 IPv6 |
| `china_ipv6_unicom.mmdb` | 28 KB | 中国联通 IPv6 |
| `china_ipv6_mobile.mmdb` | 26 KB | 中国移动 IPv6 |
| `china_ipv6_other.mmdb` | 175 KB | 其他运营商 IPv6 |

### 全球库 (Global)

| 文件 | 大小 | 说明 |
|------|------|------|
| `global_ipv4_residential.mmdb` | 90 MB | 全球 IPv4 住宅/家宽库（含 isp、connection_type） |
| `global_ipv4_idc.mmdb` | 211 KB | 全球 IPv4 IDC 已知范围 |
| `global_ipv6_residential.mmdb` | 57 MB | 全球 IPv6 住宅/家宽库 |
| `global_ipv6_idc.mmdb` | 166 KB | 全球 IPv6 IDC 已知范围 |

---

## 统一字段 Schema

所有 MMDB 数据库遵循统一字段规范：

| 字段名 | 类型 | 必选 | 说明 |
|---|---|---|---|
| `connection_type` | string | **是** | `residential`(家宽/住宅) / `idc`(数据中心) / `unknown`(未知) |
| `is_residential` | bool | **是** | `true`=家宽/非IDC / `false`=IDC |
| `isp` | string | 否 | 运营商名称 (如"中国电信"/"Google LLC"/"ByteVirt LLC") |
| `idc_vendor` | string | 否 | IDC/云厂商标记 (如"阿里云"/"AWS"/"ByteVirt") |
| `country` | string | 是 | 国家: 中国库中文, 全球库 ISO 3166-1 alpha-2 |
| `region` | string | 否 | 区域/州 (全球库) |
| `province` | string | 否 | 省份 (中国库) |
| `city` | string | 否 | 城市名称 |
| `district` | string | 否 | 区县 (仅 district 级记录) |
| `division_code` | string | 否 | GB/T 2260 6 位行政区划代码 |
| `geo_level` | string | 是 | 地理精度: district/city/province/admin_center/datacenter/unknown |
| `latitude` | number | 否 | WGS-84 纬度 |
| `longitude` | number | 否 | WGS-84 经度 |
| `confidence` | number | 否 | 置信度 0.0~1.0 |
| `accuracy_radius` | integer | 否 | 精度半径 (km) |

---

## 家宽/IDC 判定逻辑

判定按以下优先级执行：

1. **IDC 范围匹配** (IP 段命中已知 IDC 范围，如 8.129.0.0/16 阿里云)
   ⇒ `connection_type=idc`, `is_residential=false`, `idc_vendor=厂商名`

2. **ISP 标签匹配** (isp 字段命中已知 IDC 运营商标签，如 ByteVirt LLC)
   ⇒ `connection_type=idc`, `is_residential=false`, `idc_vendor=规范运营商名`
   覆盖 4,794 个 IDC 运营商标签 (Amazon/AWS/Google/Cloudflare/ByteVirt/Linode/DigitalOcean 等)

3. **非 IDC 且非 ISP 匹配** ⇒ `connection_type=residential`, `is_residential=true` (家宽)

4. **私有/保留地址** (RFC 1918/CGNAT/回环等) ⇒ `connection_type=unknown`

**IDC 范围来源**：阿里云/腾讯云/华为云/百度云/AWS/Azure/GCP/Cloudflare 等 122,240+ 条 IP 段

**ISP 标签来源**：BGP 路由表 (RouteViews RIB) + RIR Delegation Stats + RIPE RDAP 回填 ASN 组织名

---

## 数据库分类体系

```
output/
├── china_ipv4.mmdb              # 基础归属地 + 运营商 + 连接类型
├── china_ipv4_with_isp.mmdb     # + ASN 增强 isp 字段
├── china_ipv4_high_prec*.mmdb   # 高精度区县级
├── china_ipv4_idc*.mmdb         # 仅 IDC 记录
├── china_ipv4_{telecom,unicom,mobile,other}.mmdb  # 按运营商分库
│
├── china_ipv6.mmdb
├── china_ipv6_with_isp.mmdb
├── china_ipv6_{telecom,unicom,mobile,other}.mmdb
│
├── global_ipv4_residential.mmdb # 全球 IPv4 住宅/家宽 (~6.2M 记录)
├── global_ipv4_idc.mmdb         # 全球 IPv4 IDC (~29K 记录)
├── global_ipv6_residential.mmdb # 全球 IPv6 住宅/家宽 (~8.6M 记录)
└── global_ipv6_idc.mmdb         # 全球 IPv6 IDC (~11K 记录)
```

---

## 查询示例

### Python (maxminddb)

```python
import maxminddb

reader = maxminddb.open_database('output/global_ipv4_residential.mmdb')

# 云服务商
print(reader.get('8.8.8.8'))
# => connection_type=idc, is_residential=False, isp=Google LLC

# 托管商
print(reader.get('23.95.123.1'))
# => connection_type=idc, is_residential=False, isp=ByteVirt LLC

# 家宽
print(reader.get('1.0.1.0'))
# => connection_type=residential, is_residential=True

reader.close()
```

### 批量筛选

```python
import maxminddb

reader = maxminddb.open_database('output/global_ipv4_residential.mmdb')
for ip in ['8.8.8.8', '1.1.1.1', '23.92.16.1', '1.0.1.0']:
    rec = reader.get(ip)
    if rec:
        print(f"{ip:12} -> {rec['connection_type']:12} {rec['is_residential']} "
              f"isp={rec.get('isp','')}")
```

---

## 数据来源

### 地理定位层
- **ip2region** ([lionsoul2014](https://github.com/lionsoul2014/ip2region)) — IPv4 中国归属地主数据源
- **GeoCN** ([ljxi](https://github.com/ljxi/GeoCN)) — 实时 MaxMind 区县级查询引擎
- **APNIC Delegation Stats** — IPv6 分配段
- **AreaCity-JsSpider-StatsGov** — GB/T 2260 行政区划代码
- **DB-IP** — 全球 IP 定位
- **GeoFeed** — ISP 地理定位源
- **IPIP** — 部分免费定位数据

### 网络类型 & 运营商层
- **IDC 范围集** — 122,240+ 条已知云厂商/数据中心 IP 段
- **BGP 路由表** — RouteViews RIB dump -> 约 1.1M v4 + 25K v6 前缀与 ASN 映射
- **RIR 授权数据** — 五大 RIR delegated stats -> IP->国家代码索引
- **RIPE RDAP** — 约 74K ASN 组织名称查询
- **ISP 标签映射** — 4,794 个 IDC 运营商标签，含 200+ 品牌字典 + 10 子代理审核

---

## 构建流水线

项目采用多阶段流水线 (S1~S12)，每阶段可用 10x10 子代理并行编排。

### 阶段概览

| 阶段 | 说明 | 关键产出 |
|------|------|---------|
| **S1** | 字段审计 & Schema 统一 | 字段清单、Gap 报告、修复优先级 |
| **S2** | 中国 IPv4 基础库补丁 | 补全 isp/is_residential/connection_type |
| **S3** | 中国 IPv4 IDC 库补丁 | IDC 范围基库 |
| **S4** | 中国 IPv6 基础库补丁 | IPv6 字段补全 |
| **S5** | 中国 IPv6 IDC 库补丁 | IPv6 IDC 范围 |
| **S6** | 全球 IPv4 住宅库补丁 | 全球 v4 住宅库 + 多源融合 |
| **S7** | 全球 IPv4 IDC 库补丁 | 全球 v4 IDC 库 |
| **S8** | 全球 IPv6 住宅库补丁 | 全球 v6 住宅库 |
| **S9** | 全球 IPv6 IDC 库补丁 | 全球 v6 IDC 库 |
| **S10** | QA 质量审计 | 字段全覆盖、分类规则校验 |
| **S11** | ASN 增强层 | BGP 路由表 + RDAP 回填 isp 字段 |
| **S12** | **ISP 标签 IDC 归类** | 4,794 个 IDC 运营商标签驱动分类 |

### 构建命令

```bash
# 基础库构建
python scripts/build_ipv4.py
python scripts/build_ipv6.py
python scripts/build_global_mmdb.py

# 字段补丁 (S12 ISP 标签 IDC 归类)
python scripts/tools/50_mmdb_field_patch.py \
    --in output/global_ipv4_residential.mmdb \
    --out output/patched.mmdb \
    --idc-org-map data/bgp/idc_isp_map_auto.json

# ASN 增强 (isp 回填)
python scripts/tools/50_mmdb_field_patch.py \
    --in output/china_ipv4.mmdb \
    --out output/china_ipv4_with_isp.mmdb \
    --asn-map data/bgp/asn_prefix_map.pk \
    --asn-org data/bgp/asn_org_map.json
```

---

## 性能指标

### 数据库规模

| 数据库 | 记录数 | 大小 | 说明 |
|--------|--------|------|------|
| global_ipv4_residential | 6,228,206 | 90 MB | 全球 IPv4: 371,312 条 IDC + 5,856,894 条家宽 |
| global_ipv6_residential | 8,605,194 | 57 MB | 全球 IPv6: 9,043 条 IDC + 8,596,151 条家宽 |
| global_ipv4_idc | 29,047 | 211 KB | 全球 IPv4 已知 IDC 范围 |
| global_ipv6_idc | 11,433 | 166 KB | 全球 IPv6 已知 IDC 范围 |
| china_ipv4_with_isp | 277,782 | 3.0 MB | 中国 IPv4: 6,550 条 IDC |
| china_ipv6_with_isp | 16,352 | 452 KB | 中国 IPv6: 2 条 IDC |

### ISP 覆盖

| 维度 | 数据 |
|------|------|
| 全球 v4 唯一 ISP 标签 | 48,238 个 |
| 全球 v4 isp 覆盖率 | 67% (4,174,378/6,228,206 条记录含 isp) |
| 全球 v4 ASN 命中率 | 82.9% |
| 全球 v4 org 命中率 | 67% |
| IDC 运营商标签映射 | 4,794 个 |
| 中国库 ISP 数量 | 588 个 (v4) / 1,320 个 (v6) |

### 查询性能

MaxMind DB 格式使用前缀树 (Trie) 结构，单次查询为 O(prefix_len) 时间：
- **IPv4**: ~50-200 ns/query (SSD)
- **IPv6**: ~100-500 ns/query (SSD)
- **内存映射**: 文件可 mmap 后直接读取，零拷贝

---

## 许可证

本项目数据基于以下开源项目整合：

- **ip2region** — [Apache-2.0](https://github.com/lionsoul2014/ip2region/blob/master/LICENSE)
- **GeoCN** — [MIT](https://github.com/ljxi/GeoCN/blob/main/LICENSE)
- **AreaCity-JsSpider-StatsGov** — [MIT](https://github.com/small-dream/AreaCity-JsSpider-StatsGov)

整合后的数据库和工具脚本可按需使用。`data/` 和 `output/` 目录为 gitignored 生成数据。