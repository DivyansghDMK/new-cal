#ifndef MyAppName
  #define MyAppName "ECG Monitor"
#endif
#ifndef MyAppExeName
  #define MyAppExeName "ECGMonitor.exe"
#endif
#ifndef MyAppPublisher
  #define MyAppPublisher "Deckmount Electronics"
#endif
#ifndef MyAppVersion
  #define MyAppVersion "2.0.0"
#endif
#ifndef MyAppChannel
  #define MyAppChannel "stable"
#endif
#ifndef MyAppDistDir
  #define MyAppDistDir "..\dist\ECGMonitor"
#endif
#ifndef MyAppOutputDir
  #define MyAppOutputDir "..\dist_installer"
#endif
#ifndef MyAppURL
  #define MyAppURL "https://example.com"
#endif
#ifndef MyAppRepository
  #define MyAppRepository ""
#endif

; =====================================================================
; CardioX ECG Monitor Inno Setup Installer Script
; Designed for Deckmount Electronics Pvt. Ltd.
; =====================================================================

[Setup]
AppId={{B29D5C9D-67E6-4F8C-8EF0-DBE8E2F0C5EA}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
VersionInfoVersion={#MyAppVersion}
LicenseFile=EULA.txt
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir={#MyAppOutputDir}
OutputBaseFilename=Setup_{#MyAppName}_{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=admin
ChangesEnvironment=no
SetupLogging=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop icon"; GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
; Main application directory (recursively copy all PyInstaller ONEDIR output files)
Source: "{#MyAppDistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; Clean up previous installation directory completely to prevent PyInstaller DLL conflicts
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{app}\*"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"

[Run]
; Launch the executable as admin after installation. Since the app is built with --uac-admin,
; we use the 'runas' verb to trigger the UAC elevation prompt correctly from the finish page.
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; WorkingDir: "{app}"; Verb: "runas"; Flags: shellexec nowait postinstall skipifsilent

[Code]
procedure CurUninstallStepChanged(JustAfterAnUninstallStep: TUninstallStep);
var
  AppDataDir: string;
  LocalAppDataDir: string;
  DeleteData: Integer;
begin
  // After uninstall finishes, ask the user if they want to wipe local configuration and records
  if JustAfterAnUninstallStep = usPostUninstall then
  begin
    AppDataDir := ExpandConstant('{userappdata}\Deckmount');
    LocalAppDataDir := ExpandConstant('{userlocalappdata}\Deckmount\ECGMonitor');
    
    if DirExists(LocalAppDataDir) or DirExists(AppDataDir) then
    begin
      DeleteData := MsgBox('Do you want to delete your CardioX ECG Monitor local configurations, local patient databases, generated reports, and license activation files?', mbConfirmation, MB_YESNO);
      if DeleteData = idYes then
      begin
        // Remove LOCALAPPDATA runtime directory (reports, logs, config, users, database)
        if DirExists(LocalAppDataDir) then
        begin
          if DelTree(LocalAppDataDir, True, True, True) then
            Log('Deleted LocalAppData directory: ' + LocalAppDataDir)
          else
            Log('Failed to delete LocalAppData directory: ' + LocalAppDataDir);
        end;
        
        // Remove license files in APPDATA
        if DirExists(AppDataDir) then
        begin
          if FileExists(AppDataDir + '\cardiox.lic') then
            DeleteFile(AppDataDir + '\cardiox.lic');
          if FileExists(AppDataDir + '\cardiox_meta.json') then
            DeleteFile(AppDataDir + '\cardiox_meta.json');
            
          // Clean up the parent directory if empty
          RemoveDir(AppDataDir);
        end;
      end;
    end;
  end;
end;
