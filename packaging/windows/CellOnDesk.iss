#define MyAppName "CellOnDesk"
#ifndef MyAppVersion
  #define MyAppVersion "0.9.0"
#endif
#define MyAppPublisher "Yu-Chen Liu"
#define MyAppExeName "CellOnDesk.exe"

[Setup]
AppId={{7D0A3C92-FF68-4E5A-88CF-27666E44E4A7}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\CellOnDesk
DefaultGroupName=CellOnDesk
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\..\installer
OutputBaseFilename=CellOnDesk-Setup-x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}

[Files]
Source: "..\..\dist\CellOnDesk\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\CellOnDesk"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\CellOnDesk"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch CellOnDesk"; Flags: nowait postinstall skipifsilent
