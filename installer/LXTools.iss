; Build only from the clean PyInstaller output, never from a user's installed tools.
#ifndef AppVersion
  #error AppVersion must be supplied by build-installer.ps1
#endif
#ifndef ProgramSource
  #error ProgramSource must be supplied by build-installer.ps1
#endif
#ifndef OutputPath
  #error OutputPath must be supplied by build-installer.ps1
#endif

[Setup]
AppId={{274EA1C3-2387-4ABC-9603-B145B178E8F2}
AppName=LXTools
AppVersion={#AppVersion}
AppPublisher=gd-dd
AppPublisherURL=https://github.com/gd-dd/LXTools
AppSupportURL=https://github.com/gd-dd/LXTools/issues
AppUpdatesURL=https://github.com/gd-dd/LXTools/releases
DefaultDirName={localappdata}\Programs\LXTools
DefaultGroupName=LXTools
DisableProgramGroupPage=yes
DisableDirPage=no
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutputPath}
OutputBaseFilename=LXTools-Setup-{#AppVersion}-windows-x64
SetupIconFile=..\assets\brand\icon.ico
UninstallDisplayIcon={app}\LXTool.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
UninstallDisplayName=LXTools
VersionInfoVersion={#AppVersion}.0
InfoAfterFile=install-notes.txt

[Languages]
Name: "chinesesimplified"; MessagesFile: "languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; Flags: unchecked

[Files]
Source: "{#ProgramSource}\LXTool.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#ProgramSource}\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\LXTools"; Filename: "{app}\LXTool.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\LXTools"; Filename: "{app}\LXTool.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\LXTool.exe"; Description: "启动 LXTools"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Self-updates can add runtime files not present in the original uninstall log.
; Only the application-owned runtime is removed. NEVER remove {app}, tools, or user config.
Type: filesandordirs; Name: "{app}\_internal"
