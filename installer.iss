; Script Inno Setup — Valorant Config Manager
; Compiler avec : iscc installer.iss
; Produit : Output\ValorantConfigManager-Setup-{version}.exe

#define MyAppName "Valorant Config Manager"
#define MyAppVersion "1.5.1"
#define MyAppExeName "ValorantConfigManager.exe"

[Setup]
AppId={{B7E31A62-4C8F-4D2A-9E51-3F0D8A6C21E4}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
OutputDir=Output
OutputBaseFilename=ValorantConfigManager-Setup-{#MyAppVersion}
SetupIconFile=icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
DisableProgramGroupPage=yes

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "Créer un raccourci sur le Bureau"; GroupDescription: "Raccourcis :"

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; Association des fichiers .vcmprofile
Root: HKCU; Subkey: "Software\Classes\.vcmprofile"; ValueType: string; ValueData: "VCM.Profile"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\VCM.Profile"; ValueType: string; ValueData: "Profil Valorant Config Manager"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\VCM.Profile\DefaultIcon"; ValueType: string; ValueData: """{app}\{#MyAppExeName}"",0"
Root: HKCU; Subkey: "Software\Classes\VCM.Profile\shell\open\command"; ValueType: string; ValueData: """{app}\{#MyAppExeName}"" ""%1"""

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Lancer {#MyAppName}"; Flags: nowait postinstall skipifsilent
