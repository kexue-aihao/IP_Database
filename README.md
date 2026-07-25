# 中国 IP 完整归属地数据库 (IPv4 + IPv6)

基于 [ip2region (lionsoul2014)](https://github.com/lionsoul2014/ip2region) + [GeoCN (ljxi)](https://github.com/ljxi/GeoCN) + [AreaCity-JsSpider-StatsGov](https://github.com/small-dream/AreaCity-JsSpider-StatsGov) + [APNIC](https://ftp.apnic.net/pub/stats/apnic/delegated-apnic-latest) 构建的全量中国 IPv4 + IPv6 归属地数据库，IPv4 精确到 **区县级**，IPv6 覆盖 **大陆/香港/澳门/台湾** 分配段，含 **经纬度**、**行政区划代码** 及 **大厂 IDC 标记**。

---

## 目录

- [文件说明](#文件说明)
- [数据库结构](#数据库结构)
- [快速使用](#快速使用)
- [查询工具](#查询工具)
- [数据精度](#数据精度)
- [IDC 厂商覆盖](#idc-厂商覆盖)
- [主要运营商](#主要运营商)
- [数据来源](#数据来源)
- [构建流程](#构建流程)
- [性能优化](#性能优化)
- [许可证](#许可证)

---

## 文件说明

| 文件 | 大小 | 格式 | 说明 |
|------|------|------|------|
| **china_ip_complete.sql** | 9.4 MB | MySQL Dump | **IPv4 完整数据库**，含 IDC 厂商标记 |
| **china_ip_db.sqlite** | 16 MB | SQLite | IPv4 主数据库，含区县/经纬度/行政区划码 |
| **china_ip_db.csv** | 5.8 MB | CSV | IPv4 数据导出 |
| **china_ipv6_complete.sql** | 1.5 MB | MySQL Dump | **IPv6 完整数据库**，3,103 段含港澳台 |
| **china_ipv6_db.csv** | 539 KB | CSV | IPv6 数据导出 |
| **query_china_ip.py** | 15 KB | Python | **双栈查询工具**（自动识别 v4/v6） |
| **build_china_ip_db.py** | 12 KB | Python | IPv4 数据库构建脚本 |
| **build_ipv6_db.py** | 16 KB | Python | **IPv6 数据库构建脚本**（APNIC + GeoCN） |
| **GeoCN.mmdb** | 8.7 MB | MaxMind DB | 实时逐 IP 区县查询引擎（v4+v6） |
| **ok_data_level4.csv** | 3.0 MB | CSV | GB/T 2260 行政区划码 → 名称映射 |
| **ok_geo.csv** | 160 MB | CSV | 行政区划码 → 经纬度坐标 |

---

## 数据库结构

### MySQL 版 (`china_ip_complete.sql`)

```sql
-- 主表：64,957 条记录
CREATE TABLE `china_ip_locations` (
  `id`            int(11)      NOT NULL AUTO_INCREMENT,
  `start_ip`      varchar(15)  NOT NULL COMMENT '起始IP',
  `end_ip`        varchar(15)  NOT NULL COMMENT '结束IP',
  `start_ip_int`  bigint(20)   NOT NULL COMMENT '起始IP整型',
  `end_ip_int`    bigint(20)   NOT NULL COMMENT '结束IP整型',
  `country`       varchar(20)  NOT NULL DEFAULT '中国',
  `province`      varchar(30)  NOT NULL DEFAULT '' COMMENT '省份',
  `city`          varchar(30)  NOT NULL DEFAULT '' COMMENT '城市',
  `district`      varchar(30)  NOT NULL DEFAULT '' COMMENT '区县',
  `isp`           varchar(50)  NOT NULL DEFAULT '' COMMENT '运营商',
  `division_code` varchar(6)   NOT NULL DEFAULT '' COMMENT '行政区划代码(GB/T 2260)',
  `latitude`      decimal(10,6) DEFAULT NULL COMMENT '纬度',
  `longitude`     decimal(10,6) DEFAULT NULL COMMENT '经度',
  `geo_level`     varchar(10)  NOT NULL DEFAULT '' COMMENT '精度: province/city/district',
  `idc_vendor`    varchar(30)  NOT NULL DEFAULT '' COMMENT 'IDC/云厂商标记',
  PRIMARY KEY (`id`),
  KEY `idx_start_ip_int` (`start_ip_int`),
  KEY `idx_end_ip_int`   (`end_ip_int`),
  KEY `idx_province`     (`province`),
  KEY `idx_city`         (`city`),
  KEY `idx_idc_vendor`   (`idc_vendor`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

```sql
-- IDC 参考表：105+ 条范围
CREATE TABLE `china_idc_ranges` (
  `id`           int(11)     NOT NULL AUTO_INCREMENT,
  `vendor`       varchar(30) NOT NULL COMMENT '厂商',
  `start_ip`     varchar(15) NOT NULL,
  `end_ip`       varchar(15) NOT NULL,
  `start_ip_int` bigint(20)  NOT NULL,
  `end_ip_int`   bigint(20)  NOT NULL,
  `major_region` varchar(30) DEFAULT '' COMMENT '主要区域',
  PRIMARY KEY (`id`),
  KEY `idx_idc_vendor` (`vendor`),
  KEY `idx_idc_start`  (`start_ip_int`),
  KEY `idx_idc_end`    (`end_ip_int`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### IPv6 版 (`china_ipv6_complete.sql`)

```sql
-- IPv6 主表：3,103 条记录（含大陆、香港、澳门、台湾）
CREATE TABLE `china_ipv6_locations` (
  `id`            int(11)      NOT NULL AUTO_INCREMENT,
  `start_ip`      varchar(39)  NOT NULL COMMENT '起始IPv6',
  `end_ip`        varchar(39)  NOT NULL COMMENT '结束IPv6',
  `cidr`          varchar(43)  DEFAULT '' COMMENT 'CIDR表示',
  `prefix_len`    int(11)      DEFAULT 0 COMMENT '前缀长度',
  `country`       varchar(20)  NOT NULL DEFAULT '中国',
  `province`      varchar(30)  NOT NULL DEFAULT '' COMMENT '省份',
  `city`          varchar(30)  NOT NULL DEFAULT '' COMMENT '城市',
  `district`      varchar(30)  NOT NULL DEFAULT '' COMMENT '区县',
  `isp`           varchar(50)  NOT NULL DEFAULT '' COMMENT '运营商',
  `division_code` varchar(6)   NOT NULL DEFAULT '' COMMENT '行政区划代码',
  `latitude`      decimal(10,6) DEFAULT NULL COMMENT '纬度',
  `longitude`     decimal(10,6) DEFAULT NULL COMMENT '经度',
  `geo_level`     varchar(10)  NOT NULL DEFAULT '' COMMENT '精度: country/province/city/district',
  `idc_vendor`    varchar(30)  NOT NULL DEFAULT '' COMMENT 'IDC/云厂商标记',
  `start_ip_bin`  binary(16)   DEFAULT NULL COMMENT '起始IP二进制(索引)',
  `end_ip_bin`    binary(16)   DEFAULT NULL COMMENT '结束IP二进制(索引)',
  PRIMARY KEY (`id`),
  KEY `idx_ipv6_start_bin` (`start_ip_bin`),
  KEY `idx_ipv6_end_bin`   (`end_ip_bin`),
  KEY `idx_ipv6_province`  (`province`),
  KEY `idx_ipv6_idc_vendor` (`idc_vendor`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### SQLite IPv4 版 (`china_ip_db.sqlite`)

```sql
CREATE TABLE china_ip (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  start_ip      TEXT    NOT NULL,
  end_ip        TEXT    NOT NULL,
  start_ip_int  INTEGER NOT NULL,
  end_ip_int    INTEGER NOT NULL,
  country       TEXT    DEFAULT '中国',
  province      TEXT    DEFAULT '',
  city          TEXT    DEFAULT '',
  district      TEXT    DEFAULT '',
  isp           TEXT    DEFAULT '',
  isp_short     TEXT    DEFAULT '',
  division_code TEXT    DEFAULT '',
  latitude      REAL,
  longitude     REAL,
  geo_level     TEXT    DEFAULT ''
);
CREATE INDEX idx_start_ip_int ON china_ip(start_ip_int);
CREATE INDEX idx_end_ip_int   ON china_ip(end_ip_int);
CREATE INDEX idx_province     ON china_ip(province);
```

---

## 快速使用

### MySQL 导入

```bash
# 创建数据库并导入
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS china_ip_db CHARACTER SET utf8mb4"
mysql -u root -p china_ip_db < china_ip_complete.sql

# 导入 IPv6 数据（可选，独立表）
mysql -u root -p china_ip_db < china_ipv6_complete.sql
```

### 查询示例

#### IPv4 (MySQL)
```sql
-- 查询指定 IPv4 归属地
SELECT province, city, district, isp, idc_vendor
FROM china_ip_locations
WHERE start_ip_int <= INET_ATON('27.39.157.25')
  AND end_ip_int   >= INET_ATON('27.39.157.25');

-- 统计各省 IDC IP 数量
SELECT province, idc_vendor, COUNT(*) as cnt
FROM china_ip_locations
WHERE idc_vendor != ''
GROUP BY province, idc_vendor ORDER BY cnt DESC;
```

#### IPv6 (MySQL)
```sql
-- 查询指定 IPv6 归属地
SELECT cidr, province, city, isp, idc_vendor, geo_level
FROM china_ipv6_locations
WHERE start_ip_bin <= INET6_ATON('2409:8000::1')
  AND end_ip_bin   >= INET6_ATON('2409:8000::1');

-- 查询所有 IDC 厂商的 IPv6 段
SELECT cidr, idc_vendor, province
FROM china_ipv6_locations
WHERE idc_vendor != '' ORDER BY idc_vendor;

-- 统计 IPv6 精度分布
SELECT geo_level, COUNT(*) as cnt
FROM china_ipv6_locations GROUP BY geo_level;
```
```

### SQLite 查询

```python
import sqlite3, ipaddress

conn = sqlite3.connect('china_ip_db.sqlite')
ip_int = int(ipaddress.IPv4Address('27.39.157.25'))
row = conn.execute('''
    SELECT province, city, district, isp_short, division_code, latitude, longitude
    FROM china_ip
    WHERE start_ip_int <= ? AND end_ip_int >= ?
    LIMIT 1
''', (ip_int, ip_int)).fetchone()
print(row)
conn.close()
```

---

## 查询工具

项目提供了双栈查询脚本 `query_china_ip.py`，自动识别 IPv4/IPv6：

```bash
# 自动识别 v4/v6 并查询
python query_china_ip.py 27.39.157.25
python query_china_ip.py 2409:8000::1

# 仅用 GeoCN 实时查询（最精确）
python query_china_ip.py --geocn 27.39.157.25

# 强制 IPv6 数据库查询
python query_china_ip.py --ipv6 2409:8000::1

# 数据库统计信息 (IPv4 + IPv6)
python query_china_ip.py --stats

# 查询某省所有 IP 段 (IPv4)
python query_china_ip.py --province 广东

# 验证大厂 IDC IP 归属 (IPv4 + IPv6)
python query_china_ip.py --verify
```

### 架构说明

```
┌──────────────┐
│  用户输入 IP  │────> 自动识别 v4/v6
└──────┬───────┘
       │
       ├── IPv4 ──> china_ip_db.sqlite (ip2region)
       │                │
       │                ├── GeoCN 区县级精度
       │                └── IDC 厂商标记
       │
       └── IPv6 ──> china_ipv6_db.sqlite (APNIC)
                        │
                        ├── GeoCN 省级+精度
                        ├── 港澳台 覆盖
                        └── IDC IPv6 标记
```

1. **自动识别** — 查询工具自动判断 IPv4/IPv6，选择对应数据库
2. **GeoCN 引擎** — 实时 MaxMind 查询，支持 v4/v6，返回层级行政区划代码
3. **DB 引擎** — IPv4 做整数范围查询；IPv6 做十六进制字符串范围查询
4. **联动** — 6 位行政区划码通过 `ok_data_level4.csv` + `ok_geo.csv` 解析为中文名称和经纬度

---

## 数据精度

### IPv4 精度

| 精度级别 | 记录数 | 占比 | 含义 |
|---------|--------|------|------|
| **区县级** `district` | 22,071 | 34.0% | 精确到区/县/县级市 |
| **城市级** `city` | 24,818 | 38.2% | 精确到地级市 |
| **省级** `province` | 18,068 | 27.8% | 仅知所属省份 |
| **有经纬度** | 64,811 | 99.1% | WGS-84 坐标 |

### IPv6 精度

| 精度级别 | 记录数 | 占比 | 含义 |
|---------|--------|------|------|
| **区县级** `district` | 43 | 1.4% | 精确到区县（GeoCN 命中） |
| **城市级** `city` | 493 | 15.9% | 精确到地级市 |
| **省级** `province` | 308 | 9.9% | 省级精度 |
| **国家级** `country` | 2,259 | 72.8% | 中国范围（无更精细数据） |

> IPv6 地理定位精度普遍比 IPv4 低，因为 IPv6 分配段更大（通常 /32 或 /48），覆盖范围更广。
> GeoCN 对 IPv6 的区县级覆盖率约 1.4%，主要由三大运营商（电信/联通/移动）和其他主要 ISP 的已知部署区域推断。

### 精度说明

- 中国 IPv4 地址分配按 ISP/数据中心 进行，而非按地理网格切割，因此一个 IP 段可能横跨多个区县
- IPv6 分配段通常为 /32 或 /48，覆盖范围比 IPv4 大得多，精度相应降低
- 需要 **精确到具体 IP 的区县** 时，应用 GeoCN 实时查询（`query_china_ip.py` 自动使用）

---

## IDC 厂商覆盖

### IPv4 IDC 覆盖

MySQL 版本中已对 **8 家主流云厂商/IDC** 的 IPv4 段进行了标记：

| 厂商 | 标记条数 | 主要区域 |
|------|---------|---------|
| 中国电信天翼云 | 429 | 全国 |
| **阿里云** | 287 | 杭州、北京、上海、深圳、香港 |
| 华为云 | 111 | 北京、广州、上海 |
| 腾讯云 | 101 | 广州、上海、北京 |
| AWS 中国 | 43 | 北京、宁夏 |
| 百度云 | 40 | 北京 |
| 火山引擎/字节跳动 | 27 | 北京 |
| 京东云 | 18 | 北京 |

### IPv6 IDC 覆盖

| 厂商 | 覆盖段数 | 主要区域 | 已知前缀 |
|------|---------|---------|----------|
| **阿里云** | 1 | 北京 | `2408:4000::/22` |
| **腾讯云** | 11 | 上海、广州 | `2402:4e00::/23`, `2402:4c00::/23` |
| 华为云 | 1 | 北京、广州 | `2407:c080::/32` |
| 中国电信天翼云 | 2 | 全国 | `240e:400::/22` |
| 百度云 | 1 | 北京 | `2400:da00::/32` |
| 火山引擎 | 3 | 北京 | `2408:8700::/32` |
| AWS 中国 | 0 | 北京、宁夏 | 暂未发现公开 IPv6 分配 |

> IPv6 的 IDC 段数据来自公开资料整理，实际覆盖可能更广。

IDC 检测在 MySQL 构建阶段完成，通过 IP 范围匹配标记 `idc_vendor` 字段。查询时可直接按厂商筛选：`WHERE idc_vendor = '阿里云'`。

---

## 主要运营商

数据库覆盖 **584 个 ISP/运营商**，前 10 大运营商：

| 运营商 | 覆盖 IP 段数 | 简写 |
|-------|-------------|------|
| 中国电信 | 13,240 | 电信 |
| 中国移动 | 12,980 | 移动 |
| 中国联通 | 12,073 | 联通 |
| 中国教育网 | 2,950 | 教育网 |
| 中国铁通 | 1,685 | 铁通 |
| 中国科技网 | 363 | 科技网 |

涵盖 48 个省份/地区，包括 **中国大陆 31 省 + 港澳台 + 部分海外归属中国运营商的 IP**。

---

## 数据来源

### ip2region (IPv4 主要数据源)
- **仓库**: [lionsoul2014/ip2region](https://github.com/lionsoul2014/ip2region)
- **数据**: 整理收录了中国大陆、港、澳、台几乎所有运营商/IDC 的 IPv4 地址段
- **格式**: `start_ip|end_ip|国家|省份|城市|运营商|0|国家代码`
- **覆盖**: 约 65,000 条中国 IPv4 段

### APNIC Delegation Stats (IPv6 主要数据源)
- **来源**: [APNIC FTP](https://ftp.apnic.net/pub/stats/apnic/delegated-apnic-latest)
- **数据**: 亚太互联网信息中心官方授权数据，记录所有分配到中国（CN/HK/TW/MO）的 IPv6 段
- **覆盖**: 3,103 条中国 IPv6 分配段（/21 ~ /64）
- **更新**: 每日更新

### GeoCN (区县精度补充)
- **仓库**: [ljxi/GeoCN](https://github.com/ljxi/GeoCN)
- **格式**: MaxMind DB (.mmdb)，可逐 IP 实时查询
- **精度**: IPv4 约 86% 区县级；IPv6 约 27% 省级/区县级
- **使用**: 作为双引擎的实时查询层

### AreaCity-JsSpider-StatsGov (行政区划映射)
- **仓库**: [small-dream/AreaCity-JsSpider-StatsGov](https://github.com/small-dream/AreaCity-JsSpider-StatsGov)
- **文件**: `ok_data_level4.csv` + `ok_geo.csv`
- **内容**: GB/T 2260 6 位行政区划代码 ↔ 省/市/区名称 ↔ 经纬度坐标
- **层级**: XX0000=省, XXYY00=市, XXYYZZ=区县

---

## 构建流程

### IPv4 构建 (`build_china_ip_db.py`)

```
ipv4_source.txt ──> 解析中国 IPv4 段 ──> SQLite (china_ip)
                                          │
                                          ├── 省/市/运营商
                                          ├── start_ip_int/end_ip_int 索引
                                          └── meta 元信息表
```

### IPv6 构建 (`build_ipv6_db.py`)

```
APNIC 数据 ──> 解析中国 IPv6 分配段 ──> GeoCN 采样 ──> ISP 推断
                                              │
                                              ├── SQLite (china_ipv6_db)
                                              ├── MySQL (china_ipv6_complete.sql)
                                              ├── CSV   (china_ipv6_db.csv)
                                              └── 支持字段：省/市/区/ISP/经纬度/IDC
```

### MySQL 合成 (`build_mysql.py`，仅 IPv4)

```
SQLite (china_ip) ───┐
GeoCN.mmdb      ─────┤
ok_data_level4  ─────┤──> china_ip_complete.sql
ok_geo          ─────┤
                     │
IDC 已知范围 ─────────┤──> china_idc_ranges
```

合成过程：
1. 读取 SQLite 所有记录
2. 对每条记录，查询 GeoCN 获取区县级行政区划码
3. 通过 AreaCity 数据将 6 位码转换为中文省/市/区名称和经纬度
4. 标记已知 IDC/云厂商 IP 段
5. 输出 MySQL 格式 dump

---

## 性能优化

### 查询优化建议

### IPv4 查询

对于高并发查询场景，推荐使用 **MySQL 版本** 并针对 `start_ip_int` 和 `end_ip_int` 建立索引（已包含在 DDL 中）。查询模式为：

```sql
SELECT * FROM china_ip_locations
WHERE start_ip_int <= ? AND end_ip_int >= ?;
```

这个查询可以利用 `(start_ip_int, end_ip_int)` 复合索引执行范围扫描。

### IPv6 查询

IPv6 使用 `BINARY(16)` 字段和 `INET6_ATON()`/`INET6_NTOA()` 函数：

```sql
SELECT * FROM china_ipv6_locations
WHERE start_ip_bin <= INET6_ATON('2409:8000::1')
  AND end_ip_bin   >= INET6_ATON('2409:8000::1');
```

SQLite 中使用十六进制字符串比较：

```python
def ipv6_to_hex(ip_str):
    ip = ipaddress.IPv6Address(ip_str)
    return ip.exploded.replace(':', '').lower()

# 查询
ip_hex = ipv6_to_hex('2409:8000::1')
cur.execute('''
    SELECT * FROM china_ipv6
    WHERE start_ip_hex <= ? AND end_ip_hex >= ?
''', (ip_hex, ip_hex))
```

---

## 许可证

本项目数据基于以下开源项目整合：

- **ip2region** — [Apache-2.0 License](https://github.com/lionsoul2014/ip2region/blob/master/LICENSE)
- **GeoCN** — [MIT License](https://github.com/ljxi/GeoCN/blob/main/LICENSE)
- **AreaCity-JsSpider-StatsGov** — [MIT License](https://github.com/small-dream/AreaCity-JsSpider-StatsGov)

整合后的数据库和工具脚本可按需使用。
