$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "============================================"
Write-Host " PROMETHEUS — Scriabin Luce Controller v0.6.3 Release Build"
Write-Host "============================================"
Write-Host ""

Write-Host "[1/5] Isolated Python environment"
$BuildVenv = Join-Path $PSScriptRoot ".venv-build"
$BuildPython = Join-Path $BuildVenv "Scripts\python.exe"
if (-not (Test-Path -LiteralPath $BuildPython)) {
    py -m venv $BuildVenv
}
& $BuildPython --version

Write-Host ""
Write-Host "[2/5] Locked build dependencies"
& $BuildPython -m pip install --upgrade pip
& $BuildPython -m pip install -r requirements-build.txt

Write-Host ""
Write-Host "[3/5] Automated tests"
& $BuildPython -m unittest discover -s tests -v
& $BuildPython -m py_compile luce_app.py luce_core.py luce_defaults.py

Write-Host ""
Write-Host "[4/5] Cleaning previous build"
Remove-Item -Recurse -Force build -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force dist -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "[5/5] Building one-file Windows GUI executable"
& $BuildPython -m PyInstaller --noconfirm --clean PROMETHEUS.spec

Write-Host ""
Write-Host "DONE"
Write-Host "Executable:"
Write-Host "  $PSScriptRoot\dist\PROMETHEUS.exe"
Write-Host ""
Invoke-Item "$PSScriptRoot\dist"
