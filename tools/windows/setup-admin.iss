; System-wide installation requiring admin rights.

; Limitations compared to the normal (user) setup:
;    - Drive does not start automatically after the installation in silent mode.
;    - Drive will not be listed in "Add/Remove software".

#include "setup-constants.iss"


[Setup]
AppId={{F743CD4F-3AA1-4ED6-8C97-5A7D6211FE1B}
OutputBaseFilename=nuxeo-drive-{#MyAppVersion}-admin
PrivilegesRequired=admin
CreateUninstallRegKey=no

; Set the output directory to "Program Files" by default.
; You can override by setting the "/TARGETDIR="C:\folder" argument.
DefaultDirName={param:targetdir|{pf}\{#MyAppName}}


#include "setup-common.iss"


[Files]
Source: "system-wide.txt"; DestDir: "{app}"; Flags: ignoreversion


[Registry]
; NOTE: when adding an entry in a registry key, passing `None` as the name will set the `default` value of the key.
; That way, the Windows Explorer sees the right label and command to add as an entry in the contextual menu.
; Here, to pass `None` as the key name, we just need to forget to declare `ValueName`.

; Start at Windows boot
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#MyAppName}"; ValueData: "{app}\{#MyAppExeName}"; Flags: uninsdeletevalue

; Protocol handler "ndrive://" for Direct Edit
Root: HKLM; Subkey: "Software\Classes\nxdrive"; ValueType: expandsz; ValueData: "Direct Edit URL"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\nxdrive"; ValueType: expandsz; ValueName: "FriendlyTypeName"; ValueData: "Direct Edit URL"
Root: HKLM; Subkey: "Software\Classes\nxdrive"; ValueType: dword; ValueName: "EditFlags"; ValueData: "2"
Root: HKLM; Subkey: "Software\Classes\nxdrive"; ValueType: expandsz; ValueName: "URL Protocol"
Root: HKLM; Subkey: "Software\Classes\nxdrive\DefaultIcon"; ValueType: expandsz; ValueData: "{app}\{#MyAppExeName},0"
Root: HKLM; Subkey: "Software\Classes\nxdrive\shell"; ValueType: expandsz; ValueData: ""
Root: HKLM; Subkey: "Software\Classes\nxdrive\shell\open\command"; ValueType: expandsz; ValueData: "{app}\{#MyAppExeName} ""%1"""

; Context menu: create the submenu
; On files
Root: HKLM; Subkey: "Software\Classes\*\shell\{#MyAppName}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\*\shell\{#MyAppName}"; ValueType: expandsz; ValueName: "Icon"; ValueData: "{app}\{#MyAppExeName}"
Root: HKLM; Subkey: "Software\Classes\*\shell\{#MyAppName}"; ValueType: expandsz; ValueName: "MUIVerb"; ValueData: "{#MyAppName}"
Root: HKLM; Subkey: "Software\Classes\*\shell\{#MyAppName}"; ValueType: expandsz; ValueName: "ExtendedSubCommandsKey"; ValueData: "*\shell\{#MyAppName}\"
; On folders
Root: HKLM; Subkey: "Software\Classes\directory\shell\{#MyAppName}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\directory\shell\{#MyAppName}"; ValueType: expandsz; ValueName: "Icon"; ValueData: "{app}\{#MyAppExeName}"
Root: HKLM; Subkey: "Software\Classes\directory\shell\{#MyAppName}"; ValueType: expandsz; ValueName: "MUIVerb"; ValueData: "{#MyAppName}"
Root: HKLM; Subkey: "Software\Classes\directory\shell\{#MyAppName}"; ValueType: expandsz; ValueName: "ExtendedSubCommandsKey"; ValueData: "*\shell\{#MyAppName}\"

; Context menu entry: Access online
Root: HKLM; Subkey: "Software\Classes\*\shell\{#MyAppName}\shell\item1"; ValueType: expandsz; ValueName: "MUIVerb"; ValueData: "{cm:ctx_menu_access_online}"
Root: HKLM; Subkey: "Software\Classes\*\shell\{#MyAppName}\shell\item1"; ValueType: expandsz; ValueName: "Icon"; ValueData: "shell32.dll,17"
Root: HKLM; Subkey: "Software\Classes\*\shell\{#MyAppName}\shell\item1\command"; ValueType: expandsz; ValueData: """{app}\{#MyAppExeName}"" access-online --file ""%1"""

; Context menu entry: Copy share-link
Root: HKLM; Subkey: "Software\Classes\*\shell\{#MyAppName}\shell\item2"; ValueType: expandsz;  ValueName: "MUIVerb"; ValueData: "{cm:ctx_menu_copy_share_link}"
Root: HKLM; Subkey: "Software\Classes\*\shell\{#MyAppName}\shell\item2"; ValueType: expandsz; ValueName: "Icon"; ValueData: "shell32.dll,134"
Root: HKLM; Subkey: "Software\Classes\*\shell\{#MyAppName}\shell\item2\command"; ValueType: expandsz; ValueData: """{app}\{#MyAppExeName}"" copy-share-link --file ""%1"""

; Context menu entry: Edit metadata
Root: HKLM; Subkey: "Software\Classes\*\shell\{#MyAppName}\shell\item3"; ValueType: expandsz;  ValueName: "MUIVerb"; ValueData: "{cm:ctx_menu_edit_metadata}"
Root: HKLM; Subkey: "Software\Classes\*\shell\{#MyAppName}\shell\item3"; ValueType: expandsz; ValueName: "Icon"; ValueData: "shell32.dll,269"
Root: HKLM; Subkey: "Software\Classes\*\shell\{#MyAppName}\shell\item3\command"; ValueType: expandsz; ValueData: """{app}\{#MyAppExeName}"" edit-metadata --file ""%1"""

; Taken from setup-addons.iss (to keep synchronized)
; Remove the MAX_PATH limitation
Root: HKLM; Subkey: "SYSTEM\CurrentControlSet\Control\FileSystem"; ValueType: dword; ValueName: "LongPathsEnabled"; ValueData: "1"; Flags: createvalueifdoesntexist

; Taken from setup-addons.iss (to keep synchronized)
; Register the icon overlay
; The ValueData must be the AppId from setup.iss
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\Explorer\ShellIconOverlayIdentifiers\DriveIconOverlay"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\Explorer\ShellIconOverlayIdentifiers\DriveIconOverlay"; ValueType: expandsz; ValueData: "{{64519FA4-137A-4DC6-BF91-E2B698C02788}"


[Code]
function WantToStart(): Boolean;
// Start Drive after the installation, useful for scripted calls (silent auto-update for instance).
// It will check the "/START=auto" argument to enable the auto start.
var
    start: String;
begin
    start := ExpandConstant('{param:START}');
    if (Length(start) > 0) then
        Result := True;
end;
