[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$StateRoot = Join-Path $env:LOCALAPPDATA "GloryCodexBoot"
$StatePath = Join-Path $StateRoot "codex-runtime.json"

$Process = Get-Process ChatGPT, Codex -ErrorAction SilentlyContinue |
    Where-Object {
        $_.Path -and
        (Test-Path -LiteralPath $_.Path) -and
        $_.Path -match "\\OpenAI\.Codex_(\d+(?:\.\d+){3})_[^\\]+\\"
    } |
    Select-Object -First 1

if (-not $Process) {
    if (Test-Path -LiteralPath $StatePath) {
        Remove-Item -LiteralPath $StatePath -Force
    }
    Write-Output "runtime=unknown"
    exit 0
}

$Path = [IO.Path]::GetFullPath([string] $Process.Path)
$Match = [regex]::Match(
    $Path,
    "\\OpenAI\.Codex_(\d+(?:\.\d+){3})_[^\\]+\\"
)
$Version = $Match.Groups[1].Value
$Payload = [ordered]@{
    version = $Version
    executable_path = $Path
}

New-Item -ItemType Directory -Path $StateRoot -Force | Out-Null
$Json = $Payload | ConvertTo-Json
[IO.File]::WriteAllText(
    $StatePath,
    $Json,
    [Text.UTF8Encoding]::new($false)
)
Write-Output "runtime=$Version"
