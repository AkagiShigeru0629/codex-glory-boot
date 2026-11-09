[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$StatePath = Join-Path $env:LOCALAPPDATA "GloryCodexBoot\shortcut-backup.json"
if (-not (Test-Path -LiteralPath $StatePath)) {
    Write-Output "No launcher shortcut backup was found."
    exit 0
}

$Backup = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json
$ShortcutPath = [string] $Backup.path

if (Test-Path -LiteralPath $ShortcutPath) {
    $Hash = (Get-FileHash -LiteralPath $ShortcutPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($Hash -ne $Backup.shortcut_sha256) {
        throw "Shortcut was modified after installation; refusing to delete it."
    }
    if ([string] $Backup.mode -eq "replace_official") {
        $Shell = New-Object -ComObject WScript.Shell
        $Original = $Shell.CreateShortcut($ShortcutPath)
        $Original.TargetPath = [string] $Backup.original_target
        $Original.Arguments = [string] $Backup.original_arguments
        $Original.IconLocation = [string] $Backup.original_icon
        $Original.WorkingDirectory = [string] $Backup.original_working_directory
        $Original.Save()
    } else {
        Remove-Item -LiteralPath $ShortcutPath
    }
}

Remove-Item -LiteralPath $StatePath
Write-Output "Launcher shortcut restored: $ShortcutPath"
