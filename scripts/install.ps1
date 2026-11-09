[CmdletBinding()]
param(
    [string] $ShortcutPath = "",
    [switch] $ReplaceOfficial
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$DistExe = Join-Path $ProjectRoot "dist\GloryCodexBoot\GloryCodexBoot.exe"
$SourcePython = Join-Path $ProjectRoot ".venv\Scripts\pythonw.exe"
$ShortcutPathWasExplicit = -not [string]::IsNullOrWhiteSpace($ShortcutPath)

if (Test-Path -LiteralPath $DistExe) {
    $Target = $DistExe
    $Arguments = ""
    $WorkingDirectory = Split-Path -Parent $DistExe
} elseif (Test-Path -LiteralPath $SourcePython) {
    $Target = $SourcePython
    $Arguments = "-m glory_boot"
    $WorkingDirectory = $ProjectRoot
} else {
    throw "No packaged executable or project virtual environment was found."
}

if ([string]::IsNullOrWhiteSpace($ShortcutPath)) {
    $Desktop = [Environment]::GetFolderPath("Desktop")
    $ShortcutName = (-join (
        [char[]](0x43, 0x6F, 0x64, 0x65, 0x78, 0x20, 0x8363, 0x8000, 0x542F, 0x52A8)
    )) + ".lnk"
    $ShortcutPath = Join-Path $Desktop $ShortcutName
}

$ShortcutPath = [IO.Path]::GetFullPath($ShortcutPath)
$StateRoot = Join-Path $env:LOCALAPPDATA "GloryCodexBoot"
$StatePath = Join-Path $StateRoot "shortcut-backup.json"
$Shell = New-Object -ComObject WScript.Shell
$Mode = "dedicated"
$OriginalTarget = ""
$OriginalArguments = ""
$OriginalIcon = ""
$OriginalWorkingDirectory = ""

if (Test-Path -LiteralPath $ShortcutPath) {
    if ($ReplaceOfficial) {
        if (-not $ShortcutPathWasExplicit) {
            throw "ReplaceOfficial requires an explicit ShortcutPath."
        }
        $Existing = $Shell.CreateShortcut($ShortcutPath)
        $OriginalTarget = [string] $Existing.TargetPath
        $OriginalArguments = [string] $Existing.Arguments
        $OriginalIcon = [string] $Existing.IconLocation
        $OriginalWorkingDirectory = [string] $Existing.WorkingDirectory
        if ([string]::IsNullOrWhiteSpace($OriginalTarget)) {
            throw "The existing shortcut has no readable target."
        }
        $Mode = "replace_official"
    } elseif (-not (Test-Path -LiteralPath $StatePath)) {
        throw "Refusing to overwrite an unrecorded shortcut: $ShortcutPath"
    } else {
        $Backup = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json
        if ($Backup.path -ne $ShortcutPath) {
            throw "Shortcut backup belongs to a different path: $($Backup.path)"
        }
        $Mode = [string] $Backup.mode
        $OriginalTarget = [string] $Backup.original_target
        $OriginalArguments = [string] $Backup.original_arguments
        $OriginalIcon = [string] $Backup.original_icon
        $OriginalWorkingDirectory = [string] $Backup.original_working_directory
    }
} elseif ($ReplaceOfficial) {
    throw "ReplaceOfficial requires an existing shortcut: $ShortcutPath"
}

$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $Target
$Shortcut.Arguments = $Arguments
$Shortcut.WorkingDirectory = $WorkingDirectory
$Shortcut.IconLocation = "$Target,0"
$Shortcut.Save()

$Hash = (Get-FileHash -LiteralPath $ShortcutPath -Algorithm SHA256).Hash.ToLowerInvariant()
$BackupData = [ordered]@{
    path = $ShortcutPath
    target = $Target
    arguments = $Arguments
    icon = "$Target,0"
    working_directory = $WorkingDirectory
    shortcut_sha256 = $Hash
    mode = $Mode
    original_target = $OriginalTarget
    original_arguments = $OriginalArguments
    original_icon = $OriginalIcon
    original_working_directory = $OriginalWorkingDirectory
}
New-Item -ItemType Directory -Path $StateRoot -Force | Out-Null
$BackupData | ConvertTo-Json | Set-Content -LiteralPath $StatePath -Encoding utf8

$RuntimeSync = Join-Path $PSScriptRoot "sync-codex-runtime.ps1"
if (Test-Path -LiteralPath $RuntimeSync) {
    try {
        & $RuntimeSync | Out-Null
    } catch {
        Write-Warning "Codex runtime version was not recorded; wallpaper remains disabled."
    }
}

Write-Output "Shortcut installed: $ShortcutPath"
