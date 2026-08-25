# 中国 IP 归属地数据库 (China IP Geolocation Database)

中国大陆 + 港澳台 IPv4/IPv6 完整归属地数据库，含运营商分类、高精度经纬度和 IDC/云厂商标记。

## 数据来源

| 源 | 用途 | 许可 |
|---|------|------|
| [ip2region](https://github.com/lionsoul2014/ip2region) | IPv4 基础数据 (ISP + 省/市) | Apache 2.0 |
| [GeoCN](https://github.com/ljxi/GeoCN) | 区县级经纬度富化 | 免费 |
| [AreaCity](https://github.com/small-dream/AreaCity-JsSpider-StatsGov) | 行政区划码 → 坐标映射 | MIT |
| [APNIC](https://ftp.apnic.net/pub/stats/apnic/) | IPv6 段配额权威来源 | 公开 |

## 输出文件 (`output/`)

### MaxMind DB 格式 (MMDB)

所有数据库以 [MaxMind DB](https://maxmind.github.io/MaxMind-DB/) 格式提供，可直接用 `maxminddb` Python 库或各语言绑定查询。

### 中国库 (19 个文件)

| 文件 | 说明 | 记录数 |
|---|---|---|
| `china_ipv4.mmdb` | IPv4 综合归属地 | 84,432 |
| `china_ipv4_telecom.mmdb` | 中国电信 IPv4 | 26,537 |
| `china_ipv4_unicom.mmdb` | 中国联通 IPv4 | 15,681 |
| `china_ipv4_mobile.mmdb` | 中国移动 IPv4 (含铁通) | 23,350 |
| `china_ipv4_other.mmdb` | 其他运营商 IPv4 | 24,415 |
| `china_ipv4_idc.mmdb` | 中国 IDC/云厂商 IPv4 段 | 42 |
| `china_ipv4_idc_enriched.mmdb` | 中国 IDC IPv4 富化版 | 42 |
| `china_ipv4_high_prec.mmdb` | IPv4 高精度版 | 275,933 |
| `china_ipv4_high_prec_v2.mmdb` | IPv4 高精度 v2 | 277,772 |
| `china_ipv4_with_isp.mmdb` | IPv4 含 ISP 高精度 | 277,772 |
| `china_ipv6.mmdb` | IPv6 综合归属地 | 7,642 |
| `china_ipv6_enriched.mmdb` | IPv6 富化版 | 7,642 |
| `china_ipv6_telecom.mmdb` | 中国电信 IPv6 | 1,484 |
| `china_ipv6_unicom.mmdb` | 中国联通 IPv6 | 1,450 |
| `china_ipv6_mobile.mmdb` | 中国移动 IPv6 | 1,586 |
| `china_ipv6_other.mmdb` | 其他运营商 IPv6 | 3,158 |
| `china_ipv6_idc.mmdb` | 中国 IDC/云厂商 IPv6 段 | 6 |
| `china_ipv6_idc_enriched.mmdb` | 中国 IDC IPv6 富化版 | 6 |
| `china_ipv6_with_isp.mmdb` | IPv6 含 ISP 高精度 | 16,352 |

### 全球库 (4 个文件)

| 文件 | 说明 | 记录数 |
|---|---|---|
| `global_ipv4_residential.mmdb` | 全球 IPv4 住宅库 | 6,228,196 |
| `global_ipv4_idc.mmdb` | 全球 IPv4 IDC 库 | 29,047 |
| `global_ipv6_residential.mmdb` | 全球 IPv6 住宅库 | 8,605,194 |
| `global_ipv6_idc.mmdb` | 全球 IPv6 IDC 库 | 11,433 |

## 统一字段 Schema

所有 MMDB 数据库遵循统一字段规范，包含以下核心字段：

### 通用字段

| 字段名 | 类型 | 必选 | 说明 |
|---|---|---|---|
| `connection_type` | string | **是** | 连接类型: `residential`(家宽/住宅) / `idc`(数据中心) / `unknown`(未知) |
| `is_residential` | boolean | **是** | 家宽判断: `true`=家宽/非IDC / `false`=IDC |
| `isp` | string | 否 | 运营商名称 (如"中国电信"/"Vodafone") |
| `idc_vendor` | string | 否 | IDC/云厂商标记 (如"阿里云"/"AWS"/"Azure") |
| `country` | string | 是 | 国家: 中国库中文, 全球库 ISO 3166-1 alpha-2 |
| `region` | string | 否 | 区域/州 (全球库) |
| `province` | string | 否 | 省份 (中国库) |
| `city` | string | 否 | 城市名称 |
| `district` | string | 否 | 区县 (仅 district 级记录) |
| `division_code` | string | 否 | GB/T 2260 6 位行政区划代码 |
| `geo_level` | string | 是 | 地理精度: district/city/province/admin_center/datacenter/unknown |
| `latitude` | number | 否 | WGS-84 纬度 (float) |
| `longitude` | number | 否 | WGS-84 经度 (float) |
| `confidence` | number | 否 | 置信度 0.0~1.0 |
| `accuracy_radius` | integer | 否 | 精度半径 (km) |

### 家宽/IDC 判定逻辑

```
IP 命中 IDC 范围(阿里云/AWS/Azure/GCP/Cloudflare 等) 
  ⇒ is_residential=false, connection_type='idc', idc_vendor=厂商名
未命中 IDC 范围(非IDC数据中心IP) 
  ⇒ is_residential=true,  connection_type='residential'  (家宽)
私有/保留地址(RFC 1918/CGNAT/回环等) 
  ⇒ connection_type='unknown'
```

## 构建

```bash
# 1. 下载源数据
#    将以下文件放入 data/ 目录:
#    - ip.merge.txt  (ip2region 源数据)
#    - GeoCN.mmdb    (GeoCN MaxMind 数据库)
#    - ok_data_level4.csv  (行政区划层级)
#    - ok_geo.csv          (行政区划坐标)

# 2. 运行构建脚本
python scripts/build_ipv4.py
python scripts/build_ipv6.py
```

## 查询示例

### Python (maxminddb)

```python
import maxminddb

# 打开数据库
reader = maxminddb.open_database('output/china_ipv4.mmdb')

# 查询 IP 归属地
result = reader.get('1.0.1.0')
print(result)
# {'province': '福建', 'city': '福州', 'isp': '中国电信',
#  'connection_type': 'residential', 'is_residential': True,
#  'latitude': 26.07, 'longitude': 119.30, ...}

# 查询云厂商 IP
result = reader.get('8.129.0.0')
print(result['connection_type'], result['is_residential'])
# idc False

# 查询 IPv6
result = reader.get('240e:1::1')
print(result['connection_type'], result['is_residential'])
# residential True

reader.close()
```

### 筛选家宽/IDC IP

```python
def is_residential(reader, ip):
    """判断是否为家宽 IP (非 IDC 数据中心 IP ⇒ 家宽)"""
    result = reader.get(ip)
    return result.get('is_residential', False) if result else None

def is_idc(reader, ip):
    """判断是否为 IDC 数据中心 IP"""
    result = reader.get(ip)
    return result.get('connection_type') == 'idc' if result else None
```

### SQL (仅限中国 ISP 分库)

```sql
-- 查询某个 IPv4 的归属地
SELECT * FROM china_ipv4_telecom
WHERE start_ip_int <= INET_ATON('1.0.1.0')
  AND end_ip_int   >= INET_ATON('1.0.1.0');

-- 查询云厂商 IP
SELECT * FROM china_ipv4_idc WHERE vendor = '阿里云';
```
