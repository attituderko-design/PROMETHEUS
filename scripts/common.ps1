function Initialize-PrometheusBuildEnvironment {
    $projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
    Set-Location $projectRoot

    if ($projectRoot -match "[^\u0000-\u007F]") {
        $workDir = Join-Path ([System.IO.Path]::GetTempPath()) "prometheus-node-firmware"
        if ($workDir -match "[^\u0000-\u007F]") {
            throw "PlatformIO cannot build from a path containing non-ASCII characters. Move the project to an ASCII-only path."
        }

        New-Item -ItemType Directory -Force -Path $workDir | Out-Null
        $env:PLATFORMIO_BUILD_DIR = Join-Path $workDir "build"
        $env:PLATFORMIO_LIBDEPS_DIR = Join-Path $workDir "libdeps"
        Write-Host "Using ASCII-only PlatformIO work directory: $workDir"
    }

    if (-not (Get-Command pio -ErrorAction SilentlyContinue)) {
        throw "PlatformIO (pio) was not found. Install it first: py -m pip install --user platformio"
    }
}
