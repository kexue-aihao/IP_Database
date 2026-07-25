# 中国 IP 完整归属地数据库

基于 [ip2region (lionsoul2014)](https://github.com/lionsoul2014/ip2region) + [GeoCN (ljxi)](https://github.com/ljxi/GeoCN) + [AreaCity-JsSpider-StatsGov](https://github.com/small-dream/AreaCity-JsSpider-StatsGov) 构建的全量中国 IPv4 归属地数据库，精确到 **区县级**，含 **经纬度**、**行政区划代码** 及 **大厂 IDC 标记**。

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
| **china_ip_complete.sql** | 9.4 MB | MySQL Dump | **最终交付：完整合成数据库**，含 IDC 厂商标记 |
| **china_ip_db.sqlite** | 16 MB | SQLite | 主数据库，含区县/经纬度/行政区划码 |
| **china_ip_db.csv** | 5.8 MB | CSV | 数据导出 |
| **query_china_ip.py** | 13 KB | Python | 双引擎查询工具 |
| **build_china_ip_db.py** | 12 KB | Python | 数据库构建脚本 |
| **GeoCN.mmdb** | 8.7 MB | MaxMind DB | 实时逐 IP 区县查询引擎 |
| **ok_data_level4.csv** | 3.0 MB | CSV | GB/T 2260 行政区划码 → 名称映射 |
| **ok_geo.csv** | 160 MB | CSV | 行政区划码 → 经纬度坐标 |
| **china_ip_cidrs.txt** | 26 KB | 文本 | 按省份分组的 CIDR 概览 |

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

### SQLite 版 (`china_ip_db.sqlite`)

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
```

### 查询示例

```sql
-- 查询指定 IP 归属地
SELECT province, city, district, isp, idc_vendor
FROM china_ip_locations
WHERE start_ip_int <= INET_ATON('27.39.157.25')
  AND end_ip_int   >= INET_ATON('27.39.157.25');

-- 查询某省大厂 IP
SELECT DISTINCT city, idc_vendor, COUNT(*) as cnt
FROM china_ip_locations
WHERE province = '广东' AND idc_vendor != ''
GROUP BY city, idc_vendor ORDER BY cnt DESC;

-- 查询阿里云所有 IP 段
SELECT * FROM china_idc_ranges WHERE vendor LIKE '%阿里%';

-- 统计各省 IDC IP 数量
SELECT province, idc_vendor, COUNT(*) as cnt
FROM china_ip_locations
WHERE idc_vendor != ''
GROUP BY province, idc_vendor
ORDER BY cnt DESC;
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

项目提供了双引擎查询脚本 `query_china_ip.py`：

```bash
# 双引擎查询（GeoCN 优先，DB 兜底）
python query_china_ip.py 27.39.157.25

# 仅用 GeoCN 实时查询（最精确）
python query_china_ip.py --geocn 27.39.157.25

# 数据库统计信息
python query_china_ip.py --stats

# 查询某省所有 IP 段
python query_china_ip.py --province 广东

# 验证大厂 IDC IP 归属
python query_china_ip.py --verify
```

### 架构说明

```
┌──────────────┐     ┌─────────────────┐
│  用户输入 IP  │     │  GeoCN.mmdb      │
│              │────>│  (MaxMind DB)    │
│              │     │  └── 区县/经纬度   │
│              │     └────────┬─────────┘
│              │              │
│              │     ┌───────▼─────────┐
│              │     │  china_ip_db     │
│              │────>│  (SQLite 范围)   │
│              │     │  └── 省/市/运营商  │
└──────────────┘     └─────────────────┘
```

1. **GeoCN 引擎** — 实时查询 MaxMind 格式数据库，返回区县级精度 + 行政区划代码
2. **DB 引擎** — 从 SQLite 数据库做 IP 整数范围查询，返回省/市/运营商
3. **联动** — 6 位行政区划码通过 `ok_data_level4.csv` + `ok_geo.csv` 解析为中文名称和经纬度

---

## 数据精度

| 精度级别 | 记录数 | 占比 | 含义 |
|---------|--------|------|------|
| **区县级** `district` | 22,071 | 34.0% | 精确到区/县/县级市 |
| **城市级** `city` | 24,818 | 38.2% | 精确到地级市 |
| **省级** `province` | 18,068 | 27.8% | 仅知所属省份 |
| **有经纬度** | 64,811 | 99.1% | WGS-84 坐标 |
| **有行政区划码** | 64,811 | 99.1% | GB/T 2260 6位码 |

### 精度说明

- 中国 IPv4 地址分配按 ISP/数据中心 进行，而非按地理网格切割，因此一个 IP 段可能横跨多个区县
- 数据库中以 **该 IP 范围的起始 IP** 归属为准。对于跨区县的范围（如 `27.39.152.0/21` 同时覆盖佛山禅城、顺德、高明、南海），起始 IP 归属地可能与其他 IP 不同
- 需要 **精确到具体 IP 的区县** 时，应使用 GeoCN 实时查询引擎（`query_china_ip.py` 会自动执行双引擎查询并对比）

---

## IDC 厂商覆盖

MySQL 版本中已对 **8 家主流云厂商/IDC** 的 IP 段进行了标记：

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

### ip2region (主要数据源)
- **仓库**: [lionsoul2014/ip2region](https://github.com/lionsoul2014/ip2region)
- **数据**: 整理收录了中国大陆、港、澳、台几乎所有运营商/IDC 的 IP 地址段
- **格式**: `start_ip|end_ip|国家|省份|城市|运营商|0|国家代码`
- **覆盖**: 约 65,000 条中国 IP 段

### GeoCN (区县精度补充)
- **仓库**: [ljxi/GeoCN](https://github.com/ljxi/GeoCN)
- **格式**: MaxMind DB (.mmdb)，可逐 IP 实时查询
- **精度**: 对约 86% 的中国 IP 能返回区县级行政区划代码
- **使用**: 作为双引擎的实时查询层

### AreaCity-JsSpider-StatsGov (行政区划映射)
- **仓库**: [small-dream/AreaCity-JsSpider-StatsGov](https://github.com/small-dream/AreaCity-JsSpider-StatsGov)
- **文件**: `ok_data_level4.csv` + `ok_geo.csv`
- **内容**: GB/T 2260 6 位行政区划代码 ↔ 省/市/区名称 ↔ 经纬度坐标
- **层级**: XX0000=省, XXYY00=市, XXYYZZ=区县

---

## 构建流程

数据构建分两个阶段：

### 阶段 1：基础 SQLite 数据库 (`build_china_ip_db.py`)

```
ipv4_source.txt ──> 解析中国 IP 段 ──> SQLite (china_ip)
                                       │
                                       ├── 省/市/运营商
                                       ├── start_ip_int/end_ip_int 索引
                                       └── meta 元信息表
```

### 阶段 2：MySQL 合成数据库 (`build_mysql.py`)

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

对于高并发查询场景，推荐使用 **MySQL 版本** 并针对 `start_ip_int` 和 `end_ip_int` 建立索引（已包含在 DDL 中）。查询模式为：

```sql
SELECT * FROM china_ip_locations
WHERE start_ip_int <= ? AND end_ip_int >= ?;
```

这个查询可以利用 `(start_ip_int, end_ip_int)` 复合索引执行范围扫描。

### IP 整数转换

```python
def ip_to_int(ip_str):
    """将 IP 地址转为整数，用于数据库查询"""
    parts = ip_str.split('.')
    return (int(parts[0]) << 24) + (int(parts[1]) << 16) \
         + (int(parts[2]) << 8)  + int(parts[3])
```

---

## 许可证

本项目数据基于以下开源项目整合：

- **ip2region** — [Apache-2.0 License](https://github.com/lionsoul2014/ip2region/blob/master/LICENSE)
- **GeoCN** — [MIT License](https://github.com/ljxi/GeoCN/blob/main/LICENSE)
- **AreaCity-JsSpider-StatsGov** — [MIT License](https://github.com/small-dream/AreaCity-JsSpider-StatsGov)

整合后的数据库和工具脚本可按需使用。
