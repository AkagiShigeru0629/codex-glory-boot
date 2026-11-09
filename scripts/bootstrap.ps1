[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BasePython = (Get-Command python -ErrorAction Stop).Source
$PythonVersion = & $BasePython -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"

if ($PythonVersion -ne "3.14") {
    throw "This project requires CPython 3.14; found $PythonVersion."
}

$VenvPath = Join-Path $ProjectRoot ".venv"
$VenvPython = Join-Path $VenvPath "Scripts\python.exe"

if (-not (Test-Path -LiteralPath $VenvPython)) {
    & $BasePython -m venv $VenvPath
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create the project virtual environment."
    }
}

Push-Location $ProjectRoot
try {
    & $VenvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to upgrade pip."
    }

    & $VenvPython -m pip install --editable ".[dev]"
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install project dependencies."
    }

    & $VenvPython -m pip freeze
}
finally {
    Pop-Location
}
