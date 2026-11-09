$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force "$PSScriptRoot/runtime/build-temp", "$PSScriptRoot/runtime/build-local", "$PSScriptRoot/runtime/build-roaming" | Out-Null
$env:TEMP="$PSScriptRoot/runtime/build-temp"; $env:TMP=$env:TEMP
$env:LOCALAPPDATA="$PSScriptRoot/runtime/build-local"; $env:APPDATA="$PSScriptRoot/runtime/build-roaming"
$env:PIP_CACHE_DIR="$PSScriptRoot/runtime/pip-cache"; $env:PYTHONDONTWRITEBYTECODE='1'; $env:QT_QPA_PLATFORM='offscreen' 
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
& $python -m PyInstaller --noconfirm --windowed --onedir --specpath build --distpath build/packaged --name LXTool --collect-submodules xml --icon "$PSScriptRoot/assets/brand/icon.ico" --add-data "$PSScriptRoot/assets/brand/icon.png;assets/brand" --add-data "$PSScriptRoot/catalog/repo-store.json;catalog" src/desktop.py
if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
Copy-Item portable.json build/packaged/LXTool/portable.json -Force
New-Item -ItemType Directory -Force dist/LXTool | Out-Null
Copy-Item -Path build/packaged/LXTool/* -Destination dist/LXTool -Recurse -Force
# Package the clean build only. Local tools beside the installed EXE remain untouched.
Compress-Archive -Path build/packaged/LXTool -DestinationPath dist/LXTool-windows-x64.zip -Force
Get-FileHash dist/LXTool-windows-x64.zip -Algorithm SHA256
