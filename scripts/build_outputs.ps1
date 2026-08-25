$ErrorActionPreference = 'Stop'
$rawDir = 'E:\IP_Database\data\raw'
$outCsv = 'E:\IP_Database\data\anchor_ips.csv'
$outStats = 'E:\IP_Database\data\anchor_stats.json'

Add-Type -AssemblyName System.Numerics

$rows = [System.Collections.Generic.List[string]]::new()
$rows.Add('ip_range_start,ip_range_end,province,city,district,lat,lng,source,type')

$ci = [System.Globalization.CultureInfo]::InvariantCulture

function Q { param([string]$v) if ($null -eq $v) { return '""' } else { return '"' + ($v -replace '"','""') + '"' } }
function FmtCoord { param([string]$v) if ([string]::IsNullOrEmpty($v)) { return '""' } else { try { return ('"' + [double]::Parse($v, $ci).ToString('F6', $ci) + '"') } catch { return '""' } } }

# IPv4 整数 -> 点分字符串 (逐字节计算避免 @() 内 -band 负数 BUG)
function Ipv4ToStr {
  param([long]$val)
  $a = ($val -shr 24) -band 0xFF
  $b = ($val -shr 16) -band 0xFF
  $c = ($val -shr 8) -band 0xFF
  $d = $val -band 0xFF
  return ('{0}.{1}.{2}.{3}' -f $a, $b, $c, $d)
}

# IPv4 CIDR -> (start,end) 字符串
function Cidr4Range {
  param([string]$Cidr)
  $parts = $Cidr -split '/'
  $ip = $parts[0]; $len = [int]$parts[1]
  $octets = $ip -split '\.'
  if ($octets.Count -ne 4) { return $null }
  $v = ([long]$octets[0] -shl 24) + ([long]$octets[1] -shl 16) + ([long]$octets[2] -shl 8) + [long]$octets[3]
  $end = $v + [long]([math]::Pow(2, 32 - $len)) - 1
  return @((Ipv4ToStr $v), (Ipv4ToStr $end))
}

# IPv6 前缀 -> (start,end) 字符串
function Cidr6Range {
  param([string]$Prefix, [int]$Len)
  $addr = [System.Net.IPAddress]::Parse($Prefix)
  $bytes = $addr.GetAddressBytes()
  $start = [System.Numerics.BigInteger]::new($bytes, $true, $true)  # isUnsigned, isBigEndian
  $mask = ([System.Numerics.BigInteger]::One -shl (128 - $Len)) - 1
  $end = $start + $mask
  $endBytes = $end.ToByteArray($true, $true)  # isUnsigned, isBigEndian
  if ($endBytes.Length -lt 16) { $pad = [byte[]]::new(16 - $endBytes.Length); $endBytes = $pad + $endBytes }
  $endAddr = [System.Net.IPAddress]::new($endBytes)
  return @($Prefix, $endAddr.IPAddressToString)
}

# ========== 1. PeeringDB FAC (global) ==========
Write-Host '--- parsing fac ---'
$facAll = (Get-Content (Join-Path $rawDir 'peeringdb_fac.json') -Raw | ConvertFrom-Json).data
$facMap = @{}
foreach ($f in $facAll) { $facMap[$f.id] = $f }
$facCount = $facAll.Count
$facCNCount = 0
$facRows = 0
foreach ($f in $facAll) {
  $prov = if ($f.country -eq 'CN') { $f.state } else { $f.country }
  if ([string]::IsNullOrEmpty($prov)) { $prov = '' }
  if ($f.country -eq 'CN') { $facCNCount++ }
  $city = if ($f.city) { $f.city } else { '' }
  $rows.Add((Q '') + ',' + (Q '') + ',' + (Q $prov) + ',' + (Q $city) + ',' + (Q '') + ',' + (FmtCoord $f.latitude) + ',' + (FmtCoord $f.longitude) + ',' + (Q 'peeringdb_fac') + ',' + (Q 'facility'))
  $facRows++
}
Write-Host "  $facRows facility rows ($facCNCount CN)"

# ========== 2. PeeringDB IX + ixfac + netixlan ==========
Write-Host '--- parsing ix ---'
$ixAll = (Get-Content (Join-Path $rawDir 'peeringdb_ix.json') -Raw | ConvertFrom-Json).data
$ixMap = @{}
foreach ($x in $ixAll) { $ixMap[$x.id] = $x }

$ixfacAll = (Get-Content (Join-Path $rawDir 'peeringdb_ixfac.json') -Raw | ConvertFrom-Json).data
$ixfacByIx = @{}
foreach ($xf in $ixfacAll) {
  if (-not $ixfacByIx.ContainsKey($xf.ix_id)) { $ixfacByIx[$xf.ix_id] = [System.Collections.Generic.List[PSObject]]::new() }
  $ixfacByIx[$xf.ix_id].Add($xf)
}

$netixlanAll = (Get-Content (Join-Path $rawDir 'peeringdb_netixlan.json') -Raw | ConvertFrom-Json).data
$netixlanRows = 0
$netixlanNoGeo = 0
foreach ($ni in $netixlanAll) {
  $ix = $ixMap[$ni.ix_id]
  $geoLat = ''; $geoLng = ''; $geoProv = ''; $geoCity = ''
  if ($ix) { $geoProv = $ix.city }
  $ixfacs = $ixfacByIx[$ni.ix_id]
  if ($ixfacs) {
    foreach ($xf in $ixfacs) {
      $f = $facMap[$xf.fac_id]
      if ($f -and $f.latitude) {
        $geoLat = [string]$f.latitude; $geoLng = [string]$f.longitude
        $geoProv = if ($f.country -eq 'CN') { $f.state } else { $f.country }
        if ([string]::IsNullOrEmpty($geoProv)) { $geoProv = $xf.city }
        $geoCity = $f.city
        break
      }
    }
  }
  if ([string]::IsNullOrEmpty($geoCity)) { $geoCity = if ($ix) { $ix.city } else { '' } }
  if ([string]::IsNullOrEmpty($geoLat)) { $netixlanNoGeo++ }
  if ($ni.ipaddr4) {
    $rows.Add((Q $ni.ipaddr4) + ',' + (Q $ni.ipaddr4) + ',' + (Q $geoProv) + ',' + (Q $geoCity) + ',' + (Q '') + ',' + (FmtCoord $geoLat) + ',' + (FmtCoord $geoLng) + ',' + (Q 'peeringdb_netixlan') + ',' + (Q 'ixp_ip'))
    $netixlanRows++
  }
  if ($ni.ipaddr6) {
    $rows.Add((Q $ni.ipaddr6) + ',' + (Q $ni.ipaddr6) + ',' + (Q $geoProv) + ',' + (Q $geoCity) + ',' + (Q '') + ',' + (FmtCoord $geoLat) + ',' + (FmtCoord $geoLng) + ',' + (Q 'peeringdb_netixlan') + ',' + (Q 'ixp_ip'))
    $netixlanRows++
  }
  if ($netixlanRows % 20000 -eq 0) { Write-Host "  netixlan: $netixlanRows rows" }
}
Write-Host "  netixlan done: $netixlanRows rows (no geo: $netixlanNoGeo records)"

# ========== 3. IPIP china_ip_list ==========
Write-Host '--- parsing ipip ---'
$ipipRows = 0
$ipipSkip = 0
foreach ($line in (Get-Content (Join-Path $rawDir 'china_ip_list.txt'))) {
  $line = $line.Trim()
  if ($line -eq '' -or $line -match '^#') { continue }
  $rng = Cidr4Range $line
  if (-not $rng) { $ipipSkip++; continue }
  $rows.Add((Q $rng[0]) + ',' + (Q $rng[1]) + ',' + (Q '') + ',' + (Q '') + ',' + (Q '') + ',' + (Q '') + ',' + (Q '') + ',' + (Q 'ipip_china_ip_list') + ',' + (Q 'cn_ipv4'))
  $ipipRows++
}
Write-Host "  ipip done: $ipipRows rows (skip: $ipipSkip)"

# ========== 4. APNIC delegated CN ==========
Write-Host '--- parsing apnic ---'
$apnicRows = 0
$apnicV4 = 0; $apnicV6 = 0
foreach ($line in (Get-Content (Join-Path $rawDir 'delegated_apnic.txt'))) {
  $line = $line.Trim()
  if ($line -match '^apnic\|CN\|ipv6\|([^|]+)\|(\d+)\|') {
    $prefix = $Matches[1]; $pfxLen = [int]$Matches[2]
    try {
      $rng = Cidr6Range $prefix $pfxLen
      if ($rng) {
        $rows.Add((Q $rng[0]) + ',' + (Q $rng[1]) + ',' + (Q '') + ',' + (Q '') + ',' + (Q '') + ',' + (Q '') + ',' + (Q '') + ',' + (Q 'apnic_delegated') + ',' + (Q 'cn_ipv6'))
        $apnicRows++; $apnicV6++
      }
    } catch {}
  } elseif ($line -match '^apnic\|CN\|ipv4\|([^|]+)\|(\d+)\|') {
    $prefix = $Matches[1]; $count = [long]$Matches[2]
    if ($count -ge 1 -and ($count -band ($count - 1)) -eq 0) {
      $len = 32 - [int][Math]::Log($count, 2)
    } else { $len = 32 - [int][Math]::Floor([Math]::Log($count, 2)) }
    $rng = Cidr4Range ($prefix + '/' + $len)
    if ($rng) {
      $rows.Add((Q $rng[0]) + ',' + (Q $rng[1]) + ',' + (Q '') + ',' + (Q '') + ',' + (Q '') + ',' + (Q '') + ',' + (Q '') + ',' + (Q 'apnic_delegated') + ',' + (Q 'cn_ipv4'))
      $apnicRows++; $apnicV4++
    }
  }
}
Write-Host "  apnic done: $apnicRows rows (v4: $apnicV4, v6: $apnicV6)"

# ========== 5. BGP.HE.NET AS4538 (CERNET) ==========
Write-Host '--- parsing HE AS4538 ---'
$html = Get-Content (Join-Path $rawDir 'bgp_he_AS4538.html') -Raw
$eduPrefixes = [System.Collections.Generic.HashSet[string]]::new()
$m = [regex]::Matches($html, '/net/([a-f0-9.:]+/\d+)')
foreach ($mm in $m) { [void]$eduPrefixes.Add($mm.Groups[1].Value) }
$eduRows = 0
$eduV4 = 0; $eduV6 = 0
foreach ($cidr in $eduPrefixes) {
  if ($cidr -match ':') {
    $parts = $cidr -split '/'; $rng = Cidr6Range $parts[0] ([int]$parts[1])
    if ($rng) { $rows.Add((Q $rng[0]) + ',' + (Q $rng[1]) + ',' + (Q '') + ',' + (Q '') + ',' + (Q '') + ',' + (Q '') + ',' + (Q '') + ',' + (Q 'bgp_he_cernet') + ',' + (Q 'edu_ipv6')); $eduRows++; $eduV6++ }
  } else {
    $rng = Cidr4Range $cidr
    if ($rng) { $rows.Add((Q $rng[0]) + ',' + (Q $rng[1]) + ',' + (Q '') + ',' + (Q '') + ',' + (Q '') + ',' + (Q '') + ',' + (Q '') + ',' + (Q 'bgp_he_cernet') + ',' + (Q 'edu_ipv4')); $eduRows++; $eduV4++ }
  }
}
Write-Host "  HE AS4538 edu done: $eduRows rows (v4: $eduV4, v6: $eduV6, unique: $($eduPrefixes.Count))"

# ========== 6. BGP.HE.NET router/nodes ==========
Write-Host '--- parsing HE routers ---'
$routerRows = 0
$routerSet = [System.Collections.Generic.HashSet[string]]::new()
foreach ($pf in @('bgp_he_net_2001_250','bgp_he_net_2001_da8','bgp_he_net_2001_cc0')) {
  $pfPath = Join-Path $rawDir ($pf + '.html')
  if (-not (Test-Path $pfPath)) { continue }
  $h = Get-Content $pfPath -Raw
  # 提取所有 IPv4/IPv6 地址（含 /net/ 链接中的 IP 前缀主机地址）
  $ipMatches = [regex]::Matches($h, '(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)|(?<![:\w])[a-f0-9]{1,4}(?::[a-f0-9]{0,4}){2,7}(?![\w:])')
  foreach ($im in $ipMatches) {
    $ip = $im.Value.TrimEnd('.')
    if ($ip -match '^0\.' -or $ip -match '^255\.') { continue }
    if ($routerSet.Add($ip)) {
      $rows.Add((Q $ip) + ',' + (Q $ip) + ',' + (Q '') + ',' + (Q '') + ',' + (Q '') + ',' + (Q '') + ',' + (Q '') + ',' + (Q 'bgp_he_router') + ',' + (Q 'router_node'))
      $routerRows++
    }
  }
}
Write-Host "  HE routers: $routerRows rows"

# ========== 写入 CSV ==========
Write-Host '--- writing CSV ---'
[IO.File]::WriteAllLines($outCsv, $rows, (New-Object System.Text.UTF8Encoding($false)))

# ========== 统计 ==========
Write-Host '--- generating stats ---'
$totalRows = $rows.Count - 1
$byType = @{}
$bySource = @{}
$ipv4Ranges = 0; $ipv6Ranges = 0
$seen = [System.Collections.Generic.HashSet[string]]::new()
$unique4 = 0; $unique6 = 0
for ($i = 1; $i -lt $rows.Count; $i++) {
  $line = $rows[$i]
  $c1 = $line.IndexOf(','); $rest = $line.Substring($c1 + 1)
  $c2 = $rest.IndexOf(','); $start = $line.Substring(0, $c1).Trim('"')
  $srcIdx = $line.LastIndexOf(',')
  $srcLine = $line.Substring($srcIdx + 1).Trim('"')
  # source/type 解析：倒数两个字段
  $parts = $line -split ',(?=(?:[^"]*"[^"]*")*[^"]*$)'
  if ($parts.Count -ge 9) {
    $src = $parts[7].Trim('"')
    $typ = $parts[8].Trim('"')
    $st = $start
    if ($st -match ':') { $ipv6Ranges++ } elseif ($st -eq '') {} else { $ipv4Ranges++ }
    if (-not $byType.ContainsKey($typ)) { $byType[$typ] = 0 }
    $byType[$typ]++
    if (-not $bySource.ContainsKey($src)) { $bySource[$src] = 0 }
    $bySource[$src]++
  }
}

$stats = @{
  generated_at = (Get-Date -Format o)
  total_rows = $totalRows
  ipv4_range_rows = $ipv4Ranges
  ipv6_range_rows = $ipv6Ranges
  sources = @{
    peeringdb_fac = @{ status='ok'; url='https://www.peeringdb.com/api/fac?depth=0'; records=$facAll.Count; cn_records=$facCNCount; rows_in_csv=$facRows; type='facility'; note='facility geolocation anchors (no IP range)' }
    peeringdb_netixlan = @{ status='ok'; url='https://www.peeringdb.com/api/netixlan?depth=0'; records=$netixlanAll.Count; rows_in_csv=$netixlanRows; records_without_geo=$netixlanNoGeo; type='ixp_ip'; note='IXP peer IPs joined to IXP facility geolocation' }
    ipip_china_ip_list = @{ status='ok'; url='https://raw.githubusercontent.com/17mon/china_ip_list/master/china_ip_list.txt'; rows_in_csv=$ipipRows; skipped=$ipipSkip; type='cn_ipv4'; note='China IPv4 CIDR list from IPIP/17mon' }
    apnic_delegated = @{ status='ok'; url='https://ftp.apnic.net/stats/apnic/delegated-apnic-extended-latest'; rows_in_csv=$apnicRows; ipv4_rows=$apnicV4; ipv6_rows=$apnicV6; type='cn_ipv4,cn_ipv6'; note='APNIC CN delegated ranges (inetnum/inet6num allocations)' }
    bgp_he_cernet = @{ status='ok'; url='https://bgp.he.net/AS4538'; unique_prefixes=$eduPrefixes.Count; rows_in_csv=$eduRows; ipv4_rows=$eduV4; ipv6_rows=$eduV6; type='edu_ipv4,edu_ipv6'; note='CERNET(AS4538) originated prefixes from HE' }
    bgp_he_router = @{ status='ok'; url='https://bgp.he.net/net/2001:250::/32 etc'; rows_in_csv=$routerRows; type='router_node'; note='IPs extracted from HE prefix detail pages (router/node anchors)' }
  }
  by_type = $byType
  by_source = $bySource
}

[IO.File]::WriteAllText($outStats, ($stats | ConvertTo-Json -Depth 10), (New-Object System.Text.UTF8Encoding($false)))
Write-Host "  stats written. total_rows=$totalRows"
Write-Host '=== DONE ==='
