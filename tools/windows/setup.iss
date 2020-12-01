; Normal (user) installation without required admin rights.

#include "setup-constants.iss"

; Defining the AppId here to be able to craft the registry key
; needed for the IsNotUpdating() function.
#define AppId "{64519FA4-137A-4DC6-BF91-E2B698C02788}"
#define RegKey "Software\Microsoft\Windows\CurrentVersion\Uninstall\" + AppId + "_is1"


[Setup]
AppId={{#AppId}
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
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#MyAppName}"; ValueData: "{app}\{#MyAppExeName}"; Flags: uninsdeletevalue; Check: IsNotUpdating()

; Protocol handler "ndrive://" for Direct Edit
Root: HKCU; Subkey: "Software\Classes\nxdrive"; ValueType: expandsz; ValueData: "Direct Edit URL"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\nxdrive"; ValueType: expandsz; ValueName: "FriendlyTypeName"; ValueData: "Direct Edit URL"
Root: HKCU; Subkey: "Software\Classes\nxdrive"; ValueType: dword; ValueName: "EditFlags"; ValueData: "2"
Root: HKCU; Subkey: "Software\Classes\nxdrive"; ValueType: expandsz; ValueName: "URL Protocol"
Root: HKCU; Subkey: "Software\Classes\nxdrive\DefaultIcon"; ValueType: expandsz; ValueData: "{app}\{#MyAppExeName},0"
Root: HKCU; Subkey: "Software\Classes\nxdrive\shell"; ValueType: expandsz; ValueData: ""
Root: HKCU; Subkey: "Software\Classes\nxdrive\shell\open\command"; ValueType: expandsz; ValueData: "{app}\{#MyAppExeName} ""%1"""

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

function IsNotUpdating(): Boolean;
// Return true if the current installation is a fresh one (as opposed to an update).
var
    S: string;
begin
    Result := not RegQueryStringValue(HKCU, '{#RegKey}', 'Inno Setup: App Path', S);
end;
