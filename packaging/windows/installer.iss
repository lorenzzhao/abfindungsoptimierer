; SPDX-License-Identifier: GPL-3.0-or-later
; Copyright (C) 2025–2026 Lorenz Zhao (adapted from PDF Multifile Searcher)
; NOT TESTED YET.
;
; Inno Setup script for the Windows installer. Built by packaging/windows/build.ps1:
;   iscc /DAppVersion=2.0.0 /DSourceDir=<program folder> /DOutputDir=<folder> installer.iss
;
; Installs for the current user without administrator rights by default; the user can
; choose an installation for all users instead.

#ifndef AppVersion
  #error AppVersion must be defined
#endif
#ifndef SourceDir
  #error SourceDir must be defined
#endif
#ifndef OutputDir
  #define OutputDir "."
#endif

#define AppName "Abfindungsoptimierer"
#define AppExe "abfindungsoptimierer.exe"

[Setup]
; Never change the AppId: Windows uses it to recognise upgrades.
AppId={{6F0E2A51-3C4B-4E7D-9B2A-0A8D5C7E1F43}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Lorenz Zhao
AppCopyright=Copyright (C) 2026 Lorenz Zhao
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
LicenseFile={#SourceDir}\licenses\LICENSE
SetupIconFile={#SourcePath}\..\icons\app-icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
OutputDir={#OutputDir}
OutputBaseFilename=abfindungsoptimierer-{#AppVersion}-windows-x64-setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; Remove files of an older version before installing the new one.
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
