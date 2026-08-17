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

pio run -e fulgur_pixel -t upload --upload-port $Port
if ($LASTEXITCODE -ne 0) {
    throw "Upload failed: fulgur_pixel"
}
