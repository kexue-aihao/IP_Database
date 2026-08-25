$ErrorActionPreference = 'Continue'
$rawDir = 'E:\IP_Database\data\raw'
New-Item -ItemType Directory -Force -Path $rawDir | Out-Null

$status = [ordered]@{}
$stamp = Get-Date -Format o
$ua = 'ip-anchor-collector/1.0 (geolocation research)'

function Get-Utf8String {
  param([string]$Uri, [int]$TimeoutSec = 300, [int]$MaxAttempts = 5)
  for ($i = 1; $i -le $MaxAttempts; $i++) {
    try {
      $wc = New-Object System.Net.WebClient
      $wc.Headers.Add('User-Agent', $ua)
      $bytes = $wc.DownloadData($Uri)
      return [Text.Encoding]::UTF8.GetString($bytes)
    } catch {
      if ($i -lt $MaxAttempts) {
        Write-Host "  retry $i of $MaxAttempts for $Uri : $_"
        Start-Sleep -Seconds ($i * 6)
      } else { throw }
    }
  }
}

function Save-Utf8 {
  param([string]$Path, [string]$Content)
  [IO.File]::WriteAllText($Path, $Content, (New-Object System.Text.UTF8Encoding($false)))
}

# 1. PeeringDB fac
Write-Host '--- peeringdb fac ---'
try {
  $c = Get-Utf8String 'https://www.peeringdb.com/api/fac?depth=0'
  Save-Utf8 (Join-Path $rawDir 'peeringdb_fac.json') $c
  $cnt = ($c -split '"id":').Count - 1
  $status['peeringdb_fac'] = @{status='ok'; approx_records=$cnt; fetched_at=$stamp}
  Write-Host "  ok ~$cnt records"
} catch { $status['peeringdb_fac'] = @{status='failed'; error=$_.Exception.Message; fetched_at=$stamp} }
Start-Sleep -Seconds 4

# 2. PeeringDB ix
Write-Host '--- peeringdb ix ---'
try {
  $c = Get-Utf8String 'https://www.peeringdb.com/api/ix?depth=0'
  Save-Utf8 (Join-Path $rawDir 'peeringdb_ix.json') $c
  $cnt = ($c -split '"id":').Count - 1
  $status['peeringdb_ix'] = @{status='ok'; approx_records=$cnt; fetched_at=$stamp}
  Write-Host "  ok ~$cnt records"
} catch { $status['peeringdb_ix'] = @{status='failed'; error=$_.Exception.Message; fetched_at=$stamp} }
Start-Sleep -Seconds 4

# 3. PeeringDB ixfac
Write-Host '--- peeringdb ixfac ---'
try {
  $c = Get-Utf8String 'https://www.peeringdb.com/api/ixfac?depth=0'
  Save-Utf8 (Join-Path $rawDir 'peeringdb_ixfac.json') $c
  $cnt = ($c -split '"id":').Count - 1
  $status['peeringdb_ixfac'] = @{status='ok'; approx_records=$cnt; fetched_at=$stamp}
  Write-Host "  ok ~$cnt records"
} catch { $status['peeringdb_ixfac'] = @{status='failed'; error=$_.Exception.Message; fetched_at=$stamp} }
Start-Sleep -Seconds 4

# 4. PeeringDB ixlan
Write-Host '--- peeringdb ixlan ---'
try {
  $c = Get-Utf8String 'https://www.peeringdb.com/api/ixlan?depth=0'
  Save-Utf8 (Join-Path $rawDir 'peeringdb_ixlan.json') $c
  $cnt = ($c -split '"id":').Count - 1
  $status['peeringdb_ixlan'] = @{status='ok'; approx_records=$cnt; fetched_at=$stamp}
  Write-Host "  ok ~$cnt records"
} catch { $status['peeringdb_ixlan'] = @{status='failed'; error=$_.Exception.Message; fetched_at=$stamp} }
Start-Sleep -Seconds 4

# 5. PeeringDB netixlan
Write-Host '--- peeringdb netixlan (large) ---'
try {
  $c = Get-Utf8String 'https://www.peeringdb.com/api/netixlan?depth=0' -TimeoutSec 600
  Save-Utf8 (Join-Path $rawDir 'peeringdb_netixlan.json') $c
  $cnt = ($c -split '"id":').Count - 1
  $status['peeringdb_netixlan'] = @{status='ok'; approx_records=$cnt; fetched_at=$stamp}
  Write-Host "  ok ~$cnt records"
} catch { $status['peeringdb_netixlan'] = @{status='failed'; error=$_.Exception.Message; fetched_at=$stamp} }
Start-Sleep -Seconds 4

# 6. IPIP china_ip_list
Write-Host '--- ipip china_ip_list ---'
try {
  $c = Get-Utf8String 'https://raw.githubusercontent.com/17mon/china_ip_list/master/china_ip_list.txt'
  Save-Utf8 (Join-Path $rawDir 'china_ip_list.txt') $c
  $lines = $c -split '\r?\n'
  $cnt = $lines.Count
  $status['ipip_china_ip_list'] = @{status='ok'; lines=$cnt; fetched_at=$stamp}
  Write-Host "  ok $cnt lines"
} catch { $status['ipip_china_ip_list'] = @{status='failed'; error=$_.Exception.Message; fetched_at=$stamp} }

# 7. APNIC delegated
Write-Host '--- apnic delegated ---'
try {
  $c = Get-Utf8String 'https://ftp.apnic.net/stats/apnic/delegated-apnic-extended-latest' -TimeoutSec 300
  Save-Utf8 (Join-Path $rawDir 'delegated_apnic.txt') $c
  $lines = $c -split '\r?\n'
  $cnt = $lines.Count
  $status['apnic_delegated'] = @{status='ok'; lines=$cnt; fetched_at=$stamp}
  Write-Host "  ok $cnt lines"
} catch { $status['apnic_delegated'] = @{status='failed'; error=$_.Exception.Message; fetched_at=$stamp} }

# 8. BGP.HE.NET AS4538
Write-Host '--- bgp.he.net AS4538 ---'
try {
  $c = Get-Utf8String 'https://bgp.he.net/AS4538' -TimeoutSec 180
  Save-Utf8 (Join-Path $rawDir 'bgp_he_AS4538.html') $c
  $status['bgp_he_AS4538'] = @{status='ok'; bytes=$c.Length; fetched_at=$stamp}
  Write-Host "  ok $($c.Length) bytes"
} catch { $status['bgp_he_AS4538'] = @{status='failed'; error=$_.Exception.Message; fetched_at=$stamp} }

# 9. BGP.HE.NET AS24151
Write-Host '--- bgp.he.net AS24151 ---'
try {
  $c = Get-Utf8String 'https://bgp.he.net/AS24151' -TimeoutSec 120
  Save-Utf8 (Join-Path $rawDir 'bgp_he_AS24151.html') $c
  $status['bgp_he_AS24151'] = @{status='ok'; bytes=$c.Length; fetched_at=$stamp}
  Write-Host "  ok $($c.Length) bytes"
} catch { $status['bgp_he_AS24151'] = @{status='failed'; error=$_.Exception.Message; note='AS24151 may not exist'; fetched_at=$stamp} }

# 10. Prefix pages (router nodes)
$prefixPages = @(
  @{url='https://bgp.he.net/net/2001:250::/32'; file='bgp_he_net_2001_250.html'},
  @{url='https://bgp.he.net/net/2001:da8::/32'; file='bgp_he_net_2001_da8.html'},
  @{url='https://bgp.he.net/net/2001:cc0::/32'; file='bgp_he_net_2001_cc0.html'}
)
foreach ($pp in $prefixPages) {
  $key = 'bgp_he_net_' + ($pp.file -replace '\.html','')
  Write-Host "  fetching $key"
  try {
    $c = Get-Utf8String $pp.url -TimeoutSec 120
    Save-Utf8 (Join-Path $rawDir $pp.file) $c
    $status[$key] = @{status='ok'; bytes=$c.Length; fetched_at=$stamp}
    Write-Host "    ok $($c.Length) bytes"
  } catch { $status[$key] = @{status='failed'; error=$_.Exception.Message; fetched_at=$stamp} }
  Start-Sleep -Seconds 2
}

# write status
$statusJson = $status | ConvertTo-Json -Depth 10
Save-Utf8 (Join-Path $rawDir '..\fetch_status.json') $statusJson
Write-Host "=== DONE ==="
$status | Format-Table -AutoSize | Out-String | Write-Host
