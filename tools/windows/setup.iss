﻿; Script generated by the Inno Setup Script Wizard.
; SEE THE DOCUMENTATION FOR DETAILS ON CREATING INNO SETUP SCRIPT FILES!
; >>> http://www.jrsoftware.org/ishelp/ <<<


; ##################################################
; TODO: Sign the installer
; ##################################################


#define MyAppName "Nuxeo Drive"
#define MyAppPublisher "Nuxeo"
#define MyAppURL "https://www.nuxeo.com/products/drive-desktop-sync/"
#define MyAppUpdatesURL "https://github.com/nuxeo/nuxeo-drive/releases"
#define MyAppExeName "ndrive.exe"

; The version must be define via an argument on calling ISCC.exe:
;    iscc /DMyAppVersion="3.1.0" setup.iss
;#define MyAppVersion "3.1.0"

[Setup]
; NOTE: The value of AppId uniquely identifies this particular application.
; Do not use the same AppId value in installers for other applications.
; (To generate a new GUID, click Tools | Generate GUID inside the IDE.)
AppId={{64519FA4-137A-4DC6-BF91-E2B698C02788}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppUpdatesURL}
AppCopyright="© {#MyAppPublisher}"

; Outputs
OutputDir=..\..\dist
OutputBaseFilename=nuxeo-drive-{#MyAppVersion}

; Startup menu entry: "Publisher/Application Name", i.e.: "Nuxeo/Nuxeo Drive"
;DefaultGroupName={#MyAppPublisher}
; Startup menu entry: "Application Name" only, i.e.: "Nuxeo Drive"
DisableProgramGroupPage=yes

; Do not require admin rights, no UAC
PrivilegesRequired=lowest

; Set the output directory to user's AppData by default.
; You can override by setting the "/TARGETDIR="C:\folder" argument.
; NOTE: the installer will not ask for admin rights, so check
; the current user can install in that directory.
; If not, comment the previous line "PrivilegesRequired=...".
DisableDirPage=yes
DefaultDirName={param:targetdir|{userappdata}\{#MyAppName}}

; License file
LicenseFile=..\..\LICENSE.txt

; Icons
UninstallDisplayIcon={app}\{#MyAppExeName}
; 256x256px, generated from a PNG with https://convertico.com/
SetupIconFile=app_icon.ico

; Pictures
; 164x314px
;WizardImageFile=wizard.bmp
; 55x58px
WizardSmallImageFile=wizard-small.bmp

; Minimum Windows version required
; http://www.jrsoftware.org/ishelp/index.php?topic=winvernotes
MinVersion=6.1.7600

; Other
Compression=lzma
SolidCompression=yes


[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "dutch"; MessagesFile: "compiler:Languages\Dutch.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "hebrew"; MessagesFile: "compiler:Languages\Hebrew.isl"
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

; Waiting for official support: http://www.jrsoftware.org/files/istrans/
Name: "indonesian"; MessagesFile: "unofficial_i18n\Indonesian.isl"
Name: "swedish"; MessagesFile: "unofficial_i18n\Swedish.isl"


[CustomMessages]
; Translations from Crowdin
; NOTE: when upgrading silently, english is used by default. So we are not using it for now.

; Context meny entry: Access online
english.ctx_menu_access_online=Access online
;french.ctx_menu_access_online=Voir en ligne

; Context meny entry: Copy share-link
english.ctx_menu_copy_share_link=Copy share-link
;french.ctx_menu_copy_share_link=Copier le lien de partage

; Context meny entry: Edit metadata
english.ctx_menu_edit_metadata=Edit metadata
;french.ctx_menu_edit_metadata=Éditer les métadonnées


[Tasks]
; Create the desktop icon
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"


[Files]
Source: "..\..\dist\ndrive\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs


[UninstallDelete]
; Force the installation directory to be removed when uninstalling
Type: filesandordirs; Name: "{app}"


[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon


[Registry]
; NOTE: when adding an entry in a registry key, passing `None` as the name will set the `default` value of the key.
; That way, the Windows Explorer sees the right label and command to add as an entry in the contextual menu.
; Here, to pass `None` as the key name, we just need to forget to declare `ValueName`.

; Start at Windows boot
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#MyAppName}"; ValueData: "{app}\{#MyAppExeName}"; Flags: uninsdeletevalue

; Protocol handler "ndrive://" for Direct Edit
Root: HKCU; Subkey: "Software\Classes\nxdrive"; ValueType: expandsz; ValueData: "Direct Edit URL"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\nxdrive"; ValueType: expandsz; ValueName: "FriendlyTypeName"; ValueData: "Direct Edit URL"
Root: HKCU; Subkey: "Software\Classes\nxdrive"; ValueType: dword; ValueName: "EditFlags"; ValueData: "2"
Root: HKCU; Subkey: "Software\Classes\nxdrive"; ValueType: expandsz; ValueName: "URL Protocol"
Root: HKCU; Subkey: "Software\Classes\nxdrive\DefaultIcon"; ValueType: expandsz; ValueData: "{app}\{#MyAppExeName},0"
Root: HKCU; Subkey: "Software\Classes\nxdrive\shell"; ValueType: expandsz; ValueData: ""
Root: HKCU; Subkey: "Software\Classes\nxdrive\shell\open\command"; ValueType: expandsz; ValueData: "{app}\{#MyAppExeName} ""%1"""

; Context menu: create the submenu
; On files
Root: HKCU; Subkey: "Software\Classes\*\shell\{#MyAppName}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\*\shell\{#MyAppName}"; ValueType: expandsz; ValueName: "Icon"; ValueData: "{app}\{#MyAppExeName}"
Root: HKCU; Subkey: "Software\Classes\*\shell\{#MyAppName}"; ValueType: expandsz; ValueName: "MUIVerb"; ValueData: "{#MyAppName}"
Root: HKCU; Subkey: "Software\Classes\*\shell\{#MyAppName}"; ValueType: expandsz; ValueName: "ExtendedSubCommandsKey"; ValueData: "*\shell\{#MyAppName}\"
; On folders
Root: HKCU; Subkey: "Software\Classes\directory\shell\{#MyAppName}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\directory\shell\{#MyAppName}"; ValueType: expandsz; ValueName: "Icon"; ValueData: "{app}\{#MyAppExeName}"
Root: HKCU; Subkey: "Software\Classes\directory\shell\{#MyAppName}"; ValueType: expandsz; ValueName: "MUIVerb"; ValueData: "{#MyAppName}"
Root: HKCU; Subkey: "Software\Classes\directory\shell\{#MyAppName}"; ValueType: expandsz; ValueName: "ExtendedSubCommandsKey"; ValueData: "*\shell\{#MyAppName}\"

; Context menu entry: Access online
Root: HKCU; Subkey: "Software\Classes\*\shell\{#MyAppName}\shell\item1"; ValueType: expandsz; ValueName: "MUIVerb"; ValueData: "{cm:ctx_menu_access_online}"
Root: HKCU; Subkey: "Software\Classes\*\shell\{#MyAppName}\shell\item1"; ValueType: expandsz; ValueName: "Icon"; ValueData: "shell32.dll,17"
Root: HKCU; Subkey: "Software\Classes\*\shell\{#MyAppName}\shell\item1\command"; ValueType: expandsz; ValueData: """{app}\{#MyAppExeName}"" access-online --file ""%1"""

; Context menu entry: Copy share-link
Root: HKCU; Subkey: "Software\Classes\*\shell\{#MyAppName}\shell\item2"; ValueType: expandsz;  ValueName: "MUIVerb"; ValueData: "{cm:ctx_menu_copy_share_link}"
Root: HKCU; Subkey: "Software\Classes\*\shell\{#MyAppName}\shell\item2"; ValueType: expandsz; ValueName: "Icon"; ValueData: "shell32.dll,134"
Root: HKCU; Subkey: "Software\Classes\*\shell\{#MyAppName}\shell\item2\command"; ValueType: expandsz; ValueData: """{app}\{#MyAppExeName}"" copy-share-link --file ""%1"""

; Context menu entry: Edit metadata
Root: HKCU; Subkey: "Software\Classes\*\shell\{#MyAppName}\shell\item3"; ValueType: expandsz;  ValueName: "MUIVerb"; ValueData: "{cm:ctx_menu_edit_metadata}"
Root: HKCU; Subkey: "Software\Classes\*\shell\{#MyAppName}\shell\item3"; ValueType: expandsz; ValueName: "Icon"; ValueData: "shell32.dll,269"
Root: HKCU; Subkey: "Software\Classes\*\shell\{#MyAppName}\shell\item3\command"; ValueType: expandsz; ValueData: """{app}\{#MyAppExeName}"" edit-metadata --file ""%1"""


[Run]
; Launch Nuxeo Drive after installation
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall; Check: WantToStart

; Bind an eventual engine (arguments are not case sensitive):
;    {#MyAppExeName} /SILENT ARGS
;
; Where ARGS are:
;    /TARGETURL="http://localhost:8080/nuxeo" (mandatory)
;    /TARGETUSERNAME="username"               (mandatory)
;    /TARGETPASSWORD="password"
;    /TARGETDRIVEFOLDER="%USERPROFILE%\Documents\Nuxeo Drive"
Filename: "{app}\{#MyAppExeName}"; Parameters: "bind-server --password ""{param:TARGETPASSWORD}"" --local-folder ""{param:TARGETDRIVEFOLDER}"" ""{param:TARGETUSERNAME}"" ""{param:TARGETURL}"""; Flags: nowait postinstall skipifnotsilent; Check: NeedEngineBinding


[Code]
function NeedEngineBinding(): Boolean;
// Check if the sysadmin wants to bind an engine.
// It will guess by checking mandatory arguments.
var
    url: String;
    username: String;
begin
    url := ExpandConstant('{param:TARGETURL}');
    username := ExpandConstant('{param:TARGETUSERNAME}');
    if (Length(url) > 0) and (Length(username) > 0) then
        Result := True;
end;


function WantToStart(): Boolean;
// Start Drive after the installation, useful for scripted calls (silent auto-update for instance).
// It will check the "/START=auto" argument to enable the auto start.
// Also, if none of /[VERY]SILENT are passed, consider it too (1st GUI installation for instance).
var
    start: String;
begin
    start := ExpandConstant('{param:START}');
    if (Length(start) > 0) or not WizardSilent() then
        Result := True;
end;
