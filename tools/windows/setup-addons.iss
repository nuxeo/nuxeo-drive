; Create the Windows installer for add-ons.
#define MyAppName "Nuxeo Drive Addons"
#define MyAppParent "Nuxeo Drive"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Nuxeo"


[Setup]
AppId={{6AB83667-881F-40CD-9BB2-9413575DB414}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
VersionInfoVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppCopyright="© {#MyAppPublisher}. All rights reserved."
DisableDirPage=yes
DefaultDirName={param:targetdir|{localappdata}\{#MyAppParent}}

ArchitecturesInstallIn64BitMode=x64
OutputDir=..\..\dist
OutputBaseFilename=nuxeo-drive-addons
Compression=lzma
SolidCompression=yes
PrivilegesRequired=admin
SetupIconFile=app_icon.ico
WizardImageFile=wizard.bmp
WizardSmallImageFile=wizard-small.bmp
WizardStyle=modern

; Overlays
#include "setup-overlay.iss"

[Registry]
; Remove the MAX_PATH limitation
Root: HKLM; Subkey: "SYSTEM\CurrentControlSet\Control\FileSystem"; ValueType: dword; ValueName: "LongPathsEnabled"; ValueData: "1"; Flags: createvalueifdoesntexist

[Files]
Source: "addons-installed.txt"; DestDir: "{app}"; Flags: ignoreversion
