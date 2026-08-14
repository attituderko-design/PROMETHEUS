param(
    [Parameter(Mandatory=$true)]
    [string]$Port
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command pio -ErrorAction SilentlyContinue)) {
    throw "PlatformIO (pio) が見つかりません。"
}

Write-Host "WT32-ETH01をダウンロードモード(IO0=GND)にしてから続行してください。"
Read-Host "準備できたら Enter"

pio run -e aurora_pixel -t upload --upload-port $Port

Write-Host ""
Write-Host "書込み完了後: IO0-GNDを外してWT32-ETH01を再起動してください。"
