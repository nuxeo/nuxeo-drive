; Create the Windows installer for add-ons.
#define MyAppName "Nuxeo Drive Add-Ons"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Nuxeo"


[Setup]
AppId={{6AB83667-881F-40CD-9BB2-9413575DB414}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
VersionInfoVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppCopyright="© {#MyAppPublisher}. All rights reserved."

ArchitecturesInstallIn64BitMode=x64
CreateAppDir=no
OutputDir=..\..\dist
OutputBaseFilename=nuxeo-drive-addons
Compression=lzma
SolidCompression=yes
PrivilegesRequired=admin
SetupIconFile=app_icon.ico
WizardImageFile=wizard.bmp
WizardSmallImageFile=wizard-small.bmp
MinVersion=6.1.7600


[Registry]
; Remove the MAX_PATH limitation
Root: HKLM; Subkey: "SYSTEM\CurrentControlSet\Control\FileSystem"; ValueType: dword; ValueName: "LongPathsEnabled"; ValueData: "1"; Flags: createvalueifdoesntexist

; Register the icon overlay
; The ValueData must be the AppId from setup.iss
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\Explorer\ShellIconOverlayIdentifiers\DriveIconOverlay"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\Explorer\ShellIconOverlayIdentifiers\DriveIconOverlay"; ValueType: expandsz; ValueData: "{{64519FA4-137A-4DC6-BF91-E2B698C02788}"
