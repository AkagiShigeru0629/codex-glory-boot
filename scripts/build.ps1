[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Project virtual environment not found. Run scripts/bootstrap.ps1 first."
}
foreach ($Required in @(
    "media\startup.mp4",
    "media\poster.png",
    "media\wallpaper.jpg",
    "config\launcher.example.json"
)) {
    if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot $Required))) {
        throw "Required build asset is missing: $Required"
    }
}

Push-Location $ProjectRoot
try {
    & $Python -m PyInstaller --noconfirm --clean "packaging\glory_boot.spec"
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller build failed."
    }

    $OutputRoot = Join-Path $ProjectRoot "dist\GloryCodexBoot"
    $ConfigOutput = Join-Path $OutputRoot "config"
    $MediaOutput = Join-Path $OutputRoot "media"
    New-Item -ItemType Directory -Path $ConfigOutput -Force | Out-Null
    New-Item -ItemType Directory -Path $MediaOutput -Force | Out-Null
    Copy-Item -LiteralPath "config\launcher.example.json" `
        -Destination $ConfigOutput -Force
    Copy-Item -LiteralPath "media\startup.mp4" `
        -Destination $MediaOutput -Force
    Copy-Item -LiteralPath "media\poster.png" `
        -Destination $MediaOutput -Force
    Copy-Item -LiteralPath "media\wallpaper.jpg" `
        -Destination $MediaOutput -Force
    Copy-Item -LiteralPath "THIRD_PARTY_NOTICES.md" `
        -Destination $OutputRoot -Force
}
finally {
    Pop-Location
}
