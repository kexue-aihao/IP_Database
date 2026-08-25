$ipdb = "E:/v2board/resources/ipdb"
$bak = "$ipdb/backup_isp_$(Get-Date -Format yyyyMMdd_HHmmss)"
$output = "E:/IP_Database/output"

# Backup old china_ipv4 and china_ipv6
New-Item -ItemType Directory -Path $bak -Force | Out-Null
@("china_ipv4.mmdb", "china_ipv6.mmdb") | ForEach-Object {
    $src = "$ipdb/$_"
    if (Test-Path $src) {
        Copy-Item $src "$bak/$_" -Force
        Write-Output "[BACKUP] $_"
    }
}

# Replace with ISP-enabled versions
@(
    @("china_ipv4_with_isp.mmdb", "china_ipv4.mmdb"),
    @("china_ipv6_with_isp.mmdb", "china_ipv6.mmdb")
) | ForEach-Object {
    $src = "$output/$($_[0])"
    $dst = "$ipdb/$($_[1])"
    Copy-Item $src $dst -Force
    $item = Get-Item $dst
    Write-Output "[REPLACE] $($_[1]) -> $($item.Length) bytes"
}

Write-Output ""
Write-Output "=== 替换后 china 库 ==="
Get-ChildItem $ipdb -Filter "china_*.mmdb" | Select-Object Name, Length, LastWriteTime | Format-Table -AutoSize | Out-String -Width 120
