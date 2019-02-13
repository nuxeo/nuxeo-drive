
[Files]
; Copy LiferayNativityUtil_* DLL first because the other DLLs depend on it
Source: "dll\x86\NuxeoDriveUtil_x86.dll"; DestDir: "{app}\dll"; Flags: replacesameversion 32bit; Check: "not IsWin64";
Source: "dll\x64\NuxeoDriveUtil_x64.dll"; DestDir: "{app}\dll"; Flags: replacesameversion 64bit; Check: IsWin64

Source: "dll\x86\NuxeoDriveConflicted_x86.dll"; DestDir: "{app}\dll"; Flags: replacesameversion restartreplace regserver 32bit; Check: "not IsWin64";
Source: "dll\x86\NuxeoDriveError_x86.dll"; DestDir: "{app}\dll"; Flags: replacesameversion restartreplace regserver 32bit; Check: "not IsWin64";
Source: "dll\x86\NuxeoDriveLocked_x86.dll"; DestDir: "{app}\dll"; Flags: replacesameversion restartreplace regserver 32bit; Check: "not IsWin64";
Source: "dll\x86\NuxeoDriveSynced_x86.dll"; DestDir: "{app}\dll"; Flags: replacesameversion restartreplace regserver 32bit; Check: "not IsWin64";
Source: "dll\x86\NuxeoDriveSyncing_x86.dll"; DestDir: "{app}\dll"; Flags: replacesameversion restartreplace regserver 32bit; Check: "not IsWin64";
Source: "dll\x86\NuxeoDriveUnsynced_x86.dll"; DestDir: "{app}\dll"; Flags: replacesameversion restartreplace regserver 32bit; Check: "not IsWin64";
Source: "dll\x64\NuxeoDriveConflicted_x64.dll"; DestDir: "{app}\dll"; Flags: replacesameversion restartreplace regserver 64bit; Check: IsWin64
Source: "dll\x64\NuxeoDriveError_x64.dll"; DestDir: "{app}\dll"; Flags: replacesameversion restartreplace regserver 64bit; Check: IsWin64
Source: "dll\x64\NuxeoDriveLocked_x64.dll"; DestDir: "{app}\dll"; Flags: replacesameversion restartreplace regserver 64bit; Check: IsWin64
Source: "dll\x64\NuxeoDriveSynced_x64.dll"; DestDir: "{app}\dll"; Flags: replacesameversion restartreplace regserver 64bit; Check: IsWin64
Source: "dll\x64\NuxeoDriveSyncing_x64.dll"; DestDir: "{app}\dll"; Flags: replacesameversion restartreplace regserver 64bit; Check: IsWin64
Source: "dll\x64\NuxeoDriveUnsynced_x64.dll"; DestDir: "{app}\dll"; Flags: replacesameversion restartreplace regserver 64bit; Check: IsWin64


[Registry]
; Disable overlays by default to prevent checking all files if there's no filterFolders
Root: HKCU; Subkey: "Software\Nuxeo\Drive\Overlays"; ValueType: string; ValueName: "EnableOverlay"; ValueData: "0"
