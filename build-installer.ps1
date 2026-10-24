param([string]$Compiler = '', [switch]$SkipClientBuild)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not $SkipClientBuild) { & ./build.ps1 }
if (-not $Compiler) {
    $candidates = @(
        "$PSScriptRoot/runtime/toolchains/inno/ISCC.exe",
        "${env:ProgramFiles(x86)}/Inno Setup 6/ISCC.exe",
        "$env:LOCALAPPDATA/Programs/Inno Setup 6/ISCC.exe"
    )
    $Compiler = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if (-not $Compiler) { throw 'Install Inno Setup 6, or pass -Compiler <ISCC.exe path>.' }
$match = Select-String -Path src/updater.py -Pattern "^VERSION = '([0-9]+\.[0-9]+\.[0-9]+)'"
if (-not $match) { throw 'Cannot read client version.' }
$appVersion = $match.Matches[0].Groups[1].Value
$programSource = Join-Path $PSScriptRoot 'build/packaged/LXTool'
if (-not (Test-Path "$programSource/LXTool.exe") -or -not (Test-Path "$programSource/_internal")) {
    throw 'Clean client build is missing. Run build.ps1 first.'
}
if (Test-Path "$programSource/tools") { throw 'Build staging contains tools/test data; rebuild the client first.' }
& $Compiler "/DAppVersion=$appVersion" "/DProgramSource=$programSource" "/DOutputPath=$PSScriptRoot/dist" installer/LXTools.iss
if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed.' }
$assets = @("dist/LXTools-Setup-$appVersion-windows-x64.exe",'dist/LXTool-windows-x64.zip')
$checksums = foreach ($asset in $assets) {
    $hash = Get-FileHash -LiteralPath $asset -Algorithm SHA256
    "$($hash.Hash.ToLower())  $([IO.Path]::GetFileName($asset))"
}
$checksums | Set-Content dist/SHA256SUMS.txt -Encoding ascii
$checksums
