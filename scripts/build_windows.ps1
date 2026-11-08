$ErrorActionPreference = "Stop"
$Project = Split-Path -Parent $PSScriptRoot
Set-Location $Project

python -m pip install -r requirements.txt pyinstaller
python -m PyInstaller --noconfirm --clean --windowed --name "My LivLiv" --collect-all PySide6 --add-data "schemas;schemas" main.py
Write-Host "Windows executable folder: $Project\dist\My LivLiv"
