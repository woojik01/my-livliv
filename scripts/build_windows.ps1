$ErrorActionPreference = "Stop"
$Project = Split-Path -Parent $PSScriptRoot
Set-Location $Project
$Python = Join-Path $Project ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = (Get-Command python).Source
}

& $Python -m pip install -r requirements.txt pyinstaller
& $Python -m PyInstaller --noconfirm --clean --windowed --name "My LivLiv" --add-data "schemas;schemas" --add-data "runtime\preview.html;runtime" --add-data "runtime\preview.css;runtime" --add-data "runtime\preview.js;runtime" --add-data "runtime\vendor\player-0.3.0;runtime\vendor\player-0.3.0" main.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }
Write-Host "Windows executable folder: $Project\dist\My LivLiv"
