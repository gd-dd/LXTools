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
$env:PYTHONFAULTHANDLER='1'
& $python -B -c "import sys,platform,PySide6,shiboken6;print('Test runtime:',sys.version,platform.platform(),'PySide6',PySide6.__version__,'shiboken6',shiboken6.__version__,flush=True)"
if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect test runtime' }
& $python -X faulthandler -m unittest discover -s tests -v
$testExitCode = $LASTEXITCODE
Write-Output "Test Python process exit code: $testExitCode"
if ($testExitCode -ne 0) { throw "Tests failed (Python exit code $testExitCode)" }
& $python -B -c "import sys,json;sys.path.insert(0,'src');from repository_source import validate_index;validate_index(json.load(open('catalog/repo-store.json',encoding='utf-8')))"
if ($LASTEXITCODE -ne 0) { throw 'Bundled store index is invalid or empty' }
& $python -m PyInstaller --noconfirm --windowed --onedir --specpath build --distpath build/packaged --name LXTool --collect-submodules xml --icon "$PSScriptRoot/assets/brand/icon.ico" --add-data "$PSScriptRoot/assets/brand/icon.png;assets/brand" --add-data "$PSScriptRoot/catalog/repo-store.json;catalog" src/desktop.py
if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
Copy-Item portable.json build/packaged/LXTool/portable.json -Force
New-Item -ItemType Directory -Force dist | Out-Null
# Do not overwrite a potentially running legacy preview at dist/LXTool.
# All release artifacts use the clean PyInstaller build/packaged source.
# Package the clean build only. Local tools beside the installed EXE remain untouched.
Compress-Archive -Path build/packaged/LXTool -DestinationPath dist/LXTool-windows-x64.zip -Force
Get-FileHash dist/LXTool-windows-x64.zip -Algorithm SHA256
