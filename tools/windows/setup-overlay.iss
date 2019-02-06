
[Files]
; Copy LiferayNativityUtil_* DLL first because the other DLLs depend on it
Source: "dll\x86\LiferayNativityUtil_x86.dll"; DestDir: "{app}\dll"; Flags: onlyifdoesntexist 32bit; Check: "not IsWin64";
Source: "dll\x64\LiferayNativityUtil_x64.dll"; DestDir: "{app}\dll"; Flags: onlyifdoesntexist 64bit; Check: IsWin64

Source: "dll\x86\DriveConflictedOverlay_x86.dll"; DestDir: "{app}\dll"; Flags: onlyifdoesntexist regserver 32bit; Check: "not IsWin64";
Source: "dll\x86\DriveErrorOverlay_x86.dll"; DestDir: "{app}\dll"; Flags: onlyifdoesntexist regserver 32bit; Check: "not IsWin64";
Source: "dll\x86\DriveLockedOverlay_x86.dll"; DestDir: "{app}\dll"; Flags: onlyifdoesntexist regserver 32bit; Check: "not IsWin64";
Source: "dll\x86\DriveSyncedOverlay_x86.dll"; DestDir: "{app}\dll"; Flags: onlyifdoesntexist regserver 32bit; Check: "not IsWin64";
Source: "dll\x86\DriveSyncingOverlay_x86.dll"; DestDir: "{app}\dll"; Flags: onlyifdoesntexist regserver 32bit; Check: "not IsWin64";
Source: "dll\x86\DriveUnsyncedOverlay_x86.dll"; DestDir: "{app}\dll"; Flags: onlyifdoesntexist regserver 32bit; Check: "not IsWin64";
Source: "dll\x64\DriveConflictedOverlay_x64.dll"; DestDir: "{app}\dll"; Flags: onlyifdoesntexist regserver 64bit; Check: IsWin64
Source: "dll\x64\DriveErrorOverlay_x64.dll"; DestDir: "{app}\dll"; Flags: onlyifdoesntexist regserver 64bit; Check: IsWin64
Source: "dll\x64\DriveLockedOverlay_x64.dll"; DestDir: "{app}\dll"; Flags: onlyifdoesntexist regserver 64bit; Check: IsWin64
Source: "dll\x64\DriveSyncedOverlay_x64.dll"; DestDir: "{app}\dll"; Flags: onlyifdoesntexist regserver 64bit; Check: IsWin64
Source: "dll\x64\DriveSyncingOverlay_x64.dll"; DestDir: "{app}\dll"; Flags: onlyifdoesntexist regserver 64bit; Check: IsWin64
Source: "dll\x64\DriveUnsyncedOverlay_x64.dll"; DestDir: "{app}\dll"; Flags: onlyifdoesntexist regserver 64bit; Check: IsWin64


[Registry]
; Disable overlays by default to prevent checking all files if there's no filterFolders
Root: HKCU; Subkey: "Software\Nuxeo\Drive\Overlays"; ValueType: dword; ValueName: "EnableOverlay"; ValueData: "0"
