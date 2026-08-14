$ErrorActionPreference = "Stop"

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
}

Write-Host ""
Write-Host "DONE"
