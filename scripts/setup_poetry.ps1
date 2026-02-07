<#
.SYNOPSIS
Installs Poetry (if missing) and runs `poetry install` for this project.

#>
param()

Set-StrictMode -Version Latest

function Write-ErrAndExit($msg) {
    Write-Error $msg
    exit 2
}

$root = Join-Path -Path (Split-Path -Parent $MyInvocation.MyCommand.Definition) -ChildPath '..' | Resolve-Path -Relative
Push-Location $root

Write-Host "Working in: $(Get-Location)"

# Check for poetry
$poetryCmd = Get-Command poetry -ErrorAction SilentlyContinue
if (-not $poetryCmd) {
    Write-Host "Poetry not found. Installing Poetry using the official installer..."
    $tmp = [IO.Path]::Combine($env:TEMP, 'install-poetry.py')
    try {
        Invoke-WebRequest -Uri 'https://install.python-poetry.org' -OutFile $tmp -UseBasicParsing -ErrorAction Stop
    } catch {
        Write-ErrAndExit "Failed to download Poetry installer: $_"
    }

    # Run installer with python on PATH
    $py = Get-Command python -ErrorAction SilentlyContinue
    if (-not $py) {
        Write-ErrAndExit "Python is not found on PATH. Please install Python and re-run this script."
    }

    & $py.Source $tmp

    Remove-Item $tmp -ErrorAction SilentlyContinue

    # After install, poetry may not be on PATH in this session. Try to reload.
    $poetryCmd = Get-Command poetry -ErrorAction SilentlyContinue
    if (-not $poetryCmd) {
        Write-Host "Poetry installed but not on PATH in this session. You may need to start a new shell."
        Write-Host "Try running: poetry --version"
    }
}

Write-Host "Running: poetry install"
try {
    & poetry install
} catch {
    Write-ErrAndExit "poetry install failed: $_"
}

Write-Host "Poetry install completed. Use 'poetry run pytest -q' or 'poetry shell' to run tests."

Pop-Location
