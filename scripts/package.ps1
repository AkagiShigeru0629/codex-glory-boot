[CmdletBinding()]
param(
    [switch] $Benchmark
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$OutputRoot = Join-Path $ProjectRoot "dist\GloryCodexBoot"
$ArchivePath = Join-Path $ProjectRoot "dist\GloryCodexBoot-win-x64.zip"

if (-not (Test-Path -LiteralPath (Join-Path $OutputRoot "GloryCodexBoot.exe"))) {
    throw "Packaged executable not found. Run scripts/build.ps1 first."
}

$GeneratedLogs = Join-Path $OutputRoot "logs"
if (Test-Path -LiteralPath $GeneratedLogs) {
    Remove-Item -LiteralPath $GeneratedLogs -Recurse -Force
}

if (Test-Path -LiteralPath $ArchivePath) {
    Remove-Item -LiteralPath $ArchivePath
}
Compress-Archive -Path (Join-Path $OutputRoot "*") -DestinationPath $ArchivePath
$Hash = (Get-FileHash -LiteralPath $ArchivePath -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Output "archive=$ArchivePath"
Write-Output "sha256=$Hash"

if ($Benchmark) {
    $Exe = Join-Path $OutputRoot "GloryCodexBoot.exe"
    $Process = Start-Process -FilePath $Exe -ArgumentList "--benchmark" `
        -WorkingDirectory $OutputRoot -Wait -PassThru
    Write-Output "benchmark_exit=$($Process.ExitCode)"
    $LogPath = Join-Path $OutputRoot "logs\launcher.log"
    if (Test-Path -LiteralPath $LogPath) {
        Get-Content -LiteralPath $LogPath -Tail 20
    }
}
