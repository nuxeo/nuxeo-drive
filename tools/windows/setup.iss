﻿; Normal (user) installation without required admin rights.

#include "setup-constants.iss"


[Setup]
AppId={{64519FA4-137A-4DC6-BF91-E2B698C02788}
OutputBaseFilename=nuxeo-drive-{#MyAppVersion}
PrivilegesRequired=lowest

; Set the output directory to user's AppData\Local by default.
; You can override by setting the "/TARGETDIR="C:\folder" argument.
; NOTE 1: the installer will not ask for admin rights, so check
; the current user can install in that directory.
; If not, comment the previous line "PrivilegesRequired=...".
; NOTE 2: we do not support this argument as it will break the auto-updater.
; NOTE 3: if you want full control over destination folder, use the admin version of the installer.
DisableDirPage=yes
DefaultDirName={param:targetdir|{localappdata}\{#MyAppName}}


#include "setup-common.iss"


[Files]
Source: "..\..\dist\nuxeo-drive-addons.exe"; DestDir: "{app}"; Flags: ignoreversion


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


[Code]
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
