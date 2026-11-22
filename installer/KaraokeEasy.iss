#define AppName "Karaoke Easy"
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{6F1B7E2A-4C1D-4E7B-9A55-3B1C2D7E8F90}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Karaoke Easy
DefaultDirName={autopf}\Karaoke Easy
DefaultGroupName={#AppName}
OutputDir=..\Output
OutputBaseFilename=KaraokeEasy-Setup-{#AppVersion}
; Los modelos de IA casi no se comprimen: compresión rápida (mismo tamaño, varios minutos menos)
Compression=lzma2/fast
SolidCompression=no
DiskSpanning=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
UninstallDisplayIcon={app}\KaraokeEasy.exe
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\KaraokeEasy\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\KaraokeEasy.exe"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\KaraokeEasy.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\KaraokeEasy.exe"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
