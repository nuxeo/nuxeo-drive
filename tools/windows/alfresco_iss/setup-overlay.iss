
[Files]
; Copy LiferayNativityUtil_* DLL first because the other DLLs depend on it
Source: "dll\x86\AlfrescoDriveUtil_x86.dll"; DestDir: "{app}\dll"; Flags: replacesameversion 32bit; Check: "not IsWin64";
Source: "dll\x64\AlfrescoDriveUtil_x64.dll"; DestDir: "{app}\dll"; Flags: replacesameversion 64bit; Check: IsWin64

Source: "dll\x86\AlfrescoDriveConflicted_x86.dll"; DestDir: "{app}\dll"; Flags: replacesameversion restartreplace regserver 32bit; Check: "not IsWin64";
Source: "dll\x86\AlfrescoDriveError_x86.dll"; DestDir: "{app}\dll"; Flags: replacesameversion restartreplace regserver 32bit; Check: "not IsWin64";
Source: "dll\x86\AlfrescoDriveLocked_x86.dll"; DestDir: "{app}\dll"; Flags: replacesameversion restartreplace regserver 32bit; Check: "not IsWin64";
Source: "dll\x86\AlfrescoDriveSynced_x86.dll"; DestDir: "{app}\dll"; Flags: replacesameversion restartreplace regserver 32bit; Check: "not IsWin64";
Source: "dll\x86\AlfrescoDriveSyncing_x86.dll"; DestDir: "{app}\dll"; Flags: replacesameversion restartreplace regserver 32bit; Check: "not IsWin64";
Source: "dll\x86\AlfrescoDriveUnsynced_x86.dll"; DestDir: "{app}\dll"; Flags: replacesameversion restartreplace regserver 32bit; Check: "not IsWin64";
Source: "dll\x64\AlfrescoDriveConflicted_x64.dll"; DestDir: "{app}\dll"; Flags: replacesameversion restartreplace regserver 64bit; Check: IsWin64
Source: "dll\x64\AlfrescoDriveError_x64.dll"; DestDir: "{app}\dll"; Flags: replacesameversion restartreplace regserver 64bit; Check: IsWin64
Source: "dll\x64\AlfrescoDriveLocked_x64.dll"; DestDir: "{app}\dll"; Flags: replacesameversion restartreplace regserver 64bit; Check: IsWin64
Source: "dll\x64\AlfrescoDriveSynced_x64.dll"; DestDir: "{app}\dll"; Flags: replacesameversion restartreplace regserver 64bit; Check: IsWin64
Source: "dll\x64\AlfrescoDriveSyncing_x64.dll"; DestDir: "{app}\dll"; Flags: replacesameversion restartreplace regserver 64bit; Check: IsWin64
Source: "dll\x64\AlfrescoDriveUnsynced_x64.dll"; DestDir: "{app}\dll"; Flags: replacesameversion restartreplace regserver 64bit; Check: IsWin64


[Registry]
; Disable overlays by default to prevent checking all files if there's no filterFolders
Root: HKCU; Subkey: "Software\Alfresco\Drive\Overlays"; ValueType: string; ValueName: "EnableOverlay"; ValueData: "0"
