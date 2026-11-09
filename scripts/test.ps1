[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $PytestArguments
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Project virtual environment not found. Run scripts/bootstrap.ps1 first."
}

Push-Location $ProjectRoot
try {
    & $Python -m pytest @PytestArguments
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }

    & $Python -m compileall -q "src\glory_boot"
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}
finally {
    Pop-Location
}
