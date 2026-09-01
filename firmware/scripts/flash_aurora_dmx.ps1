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
Write-Host "WT32-ETH01をダウンロードモード(IO0=GND)にしてから続行してください。"
Read-Host "準備できたら Enter"
pio run -e aurora_dmx -t upload --upload-port $Port
if ($LASTEXITCODE -ne 0) {
    throw "Upload failed: aurora_dmx"
}
Write-Host "書込み完了後: IO0-GNDを外してWT32-ETH01を再起動してください。"
