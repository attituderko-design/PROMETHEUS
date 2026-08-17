$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "common.ps1")
Initialize-PrometheusBuildEnvironment

if (-not (Get-Command pio -ErrorAction SilentlyContinue)) {
    throw "PlatformIO (pio) が見つかりません。先に: py -m pip install --user platformio"
}

$envs = @(
    "fulgur_pixel",
    "aurora_pixel",
    "fulgur_dmx",
    "aurora_dmx"
)

foreach ($envName in $envs) {
    Write-Host "Building $envName..."
    pio run -e $envName
    if ($LASTEXITCODE -ne 0) {
        throw "Build failed: $envName"
    }
}

Write-Host ""
Write-Host "DONE"
