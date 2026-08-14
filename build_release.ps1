$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "============================================"
Write-Host " PROMETHEUS — Scriabin Luce Controller v0.6.2 Release Build"
Write-Host "============================================"
Write-Host ""

Write-Host "[1/5] Python"
py --version

Write-Host ""
Write-Host "[2/5] Build dependencies"
py -m pip install --upgrade pip
py -m pip install --only-binary=:all: pygame-ce==2.5.8
py -m pip install "pyinstaller>=6.20,<7"

Write-Host ""
Write-Host "[3/5] Core tests"
py -m unittest discover -s tests -v

Write-Host ""
Write-Host "[4/5] Cleaning previous build"
Remove-Item -Recurse -Force build -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force dist -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "[5/5] Building one-file Windows GUI executable"
py -m PyInstaller --noconfirm --clean PROMETHEUS.spec

Write-Host ""
Write-Host "DONE"
Write-Host "Executable:"
Write-Host "  $PSScriptRoot\dist\PROMETHEUS.exe"
Write-Host ""
Invoke-Item "$PSScriptRoot\dist"
