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
DefaultDirName={param:targetdir|{commonpf}\{#MyAppName}}

; Disable the used user areas warning, we're all consenting adults
UsedUserAreasWarning=no


#include "setup-common.iss"
#include "setup-overlay.iss"


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

; Taken from setup-addons.iss (to keep synchronized)
; Remove the MAX_PATH limitation
Root: HKLM; Subkey: "SYSTEM\CurrentControlSet\Control\FileSystem"; ValueType: dword; ValueName: "LongPathsEnabled"; ValueData: "1"; Flags: createvalueifdoesntexist


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
