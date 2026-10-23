$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Test-Path '.venv\Scripts\python.exe')) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Cannot create build environment' }
}
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
& $python -m pip install -r requirements-lock.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
& $python -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Tests failed' }
& $python -m PyInstaller --noconfirm --windowed --onedir --name LXTool src/desktop.py
if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
Compress-Archive -Path dist/LXTool -DestinationPath dist/LXTool-windows-x64.zip -Force
Get-FileHash dist/LXTool-windows-x64.zip -Algorithm SHA256
