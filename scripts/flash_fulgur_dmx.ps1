param(
    [Parameter(Mandatory=$true)]
    [string]$Port
)

$ErrorActionPreference = "Stop"

Write-Warning "DMX用RS-485出力段が実装済みの場合のみ使用してください。"
Read-Host "続行するなら Enter"
pio run -e fulgur_dmx -t upload --upload-port $Port
