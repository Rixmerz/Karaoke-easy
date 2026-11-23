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
#ifdef LIGHT
OutputBaseFilename=KaraokeEasy-Setup-Ligero-{#AppVersion}
#else
OutputBaseFilename=KaraokeEasy-Setup-{#AppVersion}
#endif
; Los modelos de IA casi no se comprimen: compresión rápida (mismo tamaño, varios minutos menos)
Compression=lzma2/fast
SolidCompression=no
DiskSpanning=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
UninstallDisplayIcon={app}\KaraokeEasy.exe
SetupIconFile=..\src-tauri\icons\icon.ico
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "showdetails"; Description: "Mostrar detalles técnicos durante la instalación (archivos que se copian)"; GroupDescription: "Opciones avanzadas:"; Flags: unchecked

[Files]
Source: "..\src-tauri\target\release\KaraokeEasy.exe"; DestDir: "{app}"; Flags: ignoreversion
#ifdef LIGHT
Source: "..\dist\KaraokeEngine\*"; DestDir: "{app}\engine"; Excludes: "\_internal\models"; Flags: ignoreversion recursesubdirs createallsubdirs
#else
Source: "..\dist\KaraokeEngine\*"; DestDir: "{app}\engine"; Flags: ignoreversion recursesubdirs createallsubdirs
#endif

[InstallDelete]
; versiones 1.x: el motor estaba en la raíz de la app
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\KaraokeEasy.exe"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\KaraokeEasy.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\KaraokeEasy.exe"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
; actualización automática desde la app (/RELAUNCH): volver a abrirla al terminar
Filename: "{app}\KaraokeEasy.exe"; Flags: nowait; Check: ShouldRelaunch

[Code]
function ShouldRelaunch: Boolean;
begin
  Result := WizardSilent and (Pos('/RELAUNCH', UpperCase(GetCmdTail)) > 0);
end;

// Sin "detalles técnicos" (por defecto): solo la barra y un mensaje sencillo, sin la lista de archivos.
procedure CurPageChanged(CurPageID: Integer);
begin
  if (CurPageID = wpInstalling) and not WizardIsTaskSelected('showdetails') then
  begin
    WizardForm.FilenameLabel.Visible := False;
    WizardForm.StatusLabel.Caption := 'Instalando Karaoke Easy… esto puede tardar unos minutos.';
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssInstall) and not WizardIsTaskSelected('showdetails') then
    WizardForm.FilenameLabel.Visible := False;
end;
