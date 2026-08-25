$ErrorActionPreference = 'Stop'
$ipdb = "E:/v2board/resources/ipdb"
$bak = "$ipdb/backup_global_$(Get-Date -Format yyyyMMdd_HHmmss)"
$output = "E:/IP_Database/output"

# Backup old global files
New-Item -ItemType Directory -Path $bak -Force | Out-Null
@("global_ipv4_residential.mmdb", "global_ipv4_idc.mmdb", "global_ipv6_residential.mmdb", "global_ipv6_idc.mmdb") | ForEach-Object {
    $src = "$ipdb/$_"
    if (Test-Path $src) {
        Copy-Item $src "$bak/$_" -Force
        Write-Output "[BACKUP] $_"
    }
}
Write-Output ""

# Replace with new files
@("global_ipv4_residential.mmdb", "global_ipv4_idc.mmdb", "global_ipv6_residential.mmdb", "global_ipv6_idc.mmdb") | ForEach-Object {
    $src = "$output/$_"
    $dst = "$ipdb/$_"
    if (Test-Path $src) {
        Copy-Item $src $dst -Force
        $item = Get-Item $dst
        Write-Output "[REPLACE] $_ -> $($item.Length) bytes"
    } else {
        Write-Output "[SKIP] $_ not found in output"
    }
}
Write-Output ""
Write-Output "=== 替换后目录内容 ==="
Get-ChildItem $ipdb -Filter "*.mmdb" | Select-Object Name, Length, LastWriteTime | Format-Table -AutoSize | Out-String -Width 160
