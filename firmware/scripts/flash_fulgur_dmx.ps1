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
Write-Host "FULGUR / WT32-ETH01 をダウンロードモード(IO0=GND)にしてください。"
Write-Host "AE-FT234X: TXD->WT32 RX0, RXD->WT32 TX0, GND->GND"
Read-Host "準備できたら Enter"

pio run -e fulgur_dmx -t upload --upload-port $Port
if ($LASTEXITCODE -ne 0) {
    throw "Upload failed: fulgur_dmx"
}

Write-Host ""
Write-Host "書込み完了後: IO0-GNDを外してWT32-ETH01を再起動してください。"
