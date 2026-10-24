param([string]$SetupPath)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$sandbox = Join-Path $root 'runtime/installer-smoke'
$target = Join-Path $sandbox 'installed'
$registration = 'HKCU:/Software/Microsoft/Windows/CurrentVersion/Uninstall/{274EA1C3-2387-4ABC-9603-B145B178E8F2}_is1'
if (Test-Path $registration) { throw 'An LXTools installer registration already exists; do not overwrite it with a smoke test.' }
if (Test-Path $target) { throw 'Smoke target already exists; inspect it before another run.' }
if (-not $target.StartsWith($root + '\')) { throw 'Smoke target outside workspace.' }
New-Item -ItemType Directory -Force $sandbox | Out-Null
$setup = (Resolve-Path -LiteralPath $SetupPath).Path
$installArgs = @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-','/NOICONS',"/DIR=`"$target`"",'/TASKS=""')
foreach ($iteration in 1,2) {
    $run = Start-Process -FilePath $setup -ArgumentList ($installArgs + "/LOG=`"$sandbox/install-$iteration.log`"") -Wait -PassThru -WindowStyle Hidden
    if ($run.ExitCode -ne 0) { throw "Installer failed: $($run.ExitCode)" }
    if (-not (Test-Path "$target/LXTool.exe") -or -not (Test-Path "$target/unins000.exe")) { throw 'Missing program or uninstaller.' }
    if ($iteration -eq 1) {
        New-Item -ItemType Directory "$target/tools" | Out-Null
        [IO.File]::WriteAllText("$target/tools/preserve.txt",'keep-installed-tools')
    } elseif ([IO.File]::ReadAllText("$target/tools/preserve.txt") -ne 'keep-installed-tools') {
        throw 'Reinstall changed installed tools.'
    }
}
$registered = Get-ItemProperty $registration
if ([IO.Path]::GetFullPath($registered.InstallLocation).TrimEnd('\') -ne $target) { throw 'Wrong uninstall registration target.' }
Write-Output "PASS install + reinstall + registration + tools retained: $target"
