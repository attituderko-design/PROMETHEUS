$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "common.ps1")
Initialize-PrometheusBuildEnvironment

if (-not (Get-Command pio -ErrorAction SilentlyContinue)) {
    throw "PlatformIO (pio) が見つかりません。先に: py -m pip install --user platformio"
}

Write-Host "Building FULGUR / PIXEL..."
pio run -e fulgur_pixel
if ($LASTEXITCODE -ne 0) {
    throw "Build failed: fulgur_pixel"
}

Write-Host "Building AURORA / PIXEL..."
pio run -e aurora_pixel
if ($LASTEXITCODE -ne 0) {
    throw "Build failed: aurora_pixel"
}

Write-Host ""
Write-Host "DONE"
