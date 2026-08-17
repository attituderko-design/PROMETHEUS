param(
    [Parameter(Mandatory=$true)]
    [string]$Port
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "common.ps1")
Initialize-PrometheusBuildEnvironment

if (-not (Get-Command pio -ErrorAction SilentlyContinue)) {
    throw "PlatformIO (pio) が見つかりません。"
}

Write-Warning "DMX用RS-485出力段が実装済みの場合のみ使用してください。"
Read-Host "続行するなら Enter"
pio run -e fulgur_dmx -t upload --upload-port $Port
if ($LASTEXITCODE -ne 0) {
    throw "Upload failed: fulgur_dmx"
}
