$ErrorActionPreference = 'Stop'
$dst = 'E:/v2board/resources/ipdb'
$bak = $dst + '\backup_20260824'
if (!(Test-Path $bak)) { New-Item -ItemType Directory -Path $bak | Out-Null }
# Backup old files
Get-ChildItem $dst -Filter '*.mmdb' | ForEach-Object {
  Copy-Item $_.FullName ($bak + '\' + $_.Name) -Force
}
Write-Output '=== 备份完成 ==='
Get-ChildItem $bak -Filter '*.mmdb' | Select-Object Name, Length | Format-Table -AutoSize | Out-String -Width 120
# Map new outputs to v2board names
$mappings = @(
  @{ Src = 'E:/IP_Database/output/china_ipv4_high_prec_v2.mmdb';   Dst = $dst + '/china_ipv4.mmdb' },
  @{ Src = 'E:/IP_Database/output/china_ipv4_idc_enriched.mmdb';   Dst = $dst + '/china_ipv4_idc.mmdb' },
  @{ Src = 'E:/IP_Database/output/china_ipv6_enriched.mmdb';       Dst = $dst + '/china_ipv6.mmdb' },
  @{ Src = 'E:/IP_Database/output/china_ipv6_idc_enriched.mmdb';   Dst = $dst + '/china_ipv6_idc.mmdb' }
)
Write-Output ''
Write-Output '=== 执行替换 ==='
foreach ($m in $mappings) {
  if (!(Test-Path $m.Src)) {
    Write-Output ('[FAIL] 源文件不存在: ' + $m.Src)
    continue
  }
  Copy-Item $m.Src $m.Dst -Force
  $item = Get-Item $m.Dst
  Write-Output ('[OK] ' + $m.Src + '  -->  ' + $m.Dst + ' (' + $item.Length + ' bytes)')
}
Write-Output ''
Write-Output '=== 替换后目录内容 ==='
Get-ChildItem $dst -Filter '*.mmdb' | Select-Object Name, Length, LastWriteTime | Format-Table -AutoSize | Out-String -Width 160