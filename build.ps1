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
& $python -m PyInstaller --noconfirm --windowed --onedir --distpath build/packaged --name LXTool src/desktop.py
if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
New-Item -ItemType Directory -Force dist/LXTool | Out-Null
Copy-Item -Path build/packaged/LXTool/* -Destination dist/LXTool -Recurse -Force
# Package the clean build only. Local tools beside the installed EXE remain untouched.
Compress-Archive -Path build/packaged/LXTool -DestinationPath dist/LXTool-windows-x64.zip -Force
Get-FileHash dist/LXTool-windows-x64.zip -Algorithm SHA256

