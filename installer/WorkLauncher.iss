#ifndef AppVersion
  #error AppVersion must be supplied by the build, for example /DAppVersion=1.0.0
#endif
#ifndef FileVersion
  #error FileVersion must be supplied by the build, for example /DFileVersion=1.0.0.0
#endif

#define AppName "Work Launcher"
#define AppPublisher "decypher0012"
#define AppURL "https://github.com/decypher0012/powtoon-sites"

[Setup]
AppId={{7A07E62F-0C3A-45D2-91E8-4E5BE929A8D9}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
DefaultDirName={localappdata}\Programs\WorkLauncher
DefaultGroupName={#AppName}
AllowNoIcons=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=WorkLauncher-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
UsePreviousAppDir=yes
UninstallDisplayIcon={app}\WorkLauncher.exe
VersionInfoVersion={#FileVersion}
VersionInfoProductName={#AppName}
VersionInfoProductVersion={#AppVersion}
VersionInfoCompany={#AppPublisher}
VersionInfoDescription={#AppName} per-user installer
VersionInfoCopyright=Copyright (C) 2026 {#AppPublisher}

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\WorkLauncher.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\Updater.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "install-mode.json"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\WorkLauncher.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\WorkLauncher.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\WorkLauncher.exe"; Description: "Launch {#AppName}"; WorkingDir: "{app}"; Flags: nowait postinstall; Check: ShouldLaunch

[Code]
function ShouldLaunch: Boolean;
var
  I: Integer;
begin
  Result := True;
  for I := 1 to ParamCount do
    if CompareText(ParamStr(I), '/NOLAUNCH') = 0 then
    begin
      Result := False;
      Exit;
    end;
end;
