; Setup details

AppName={#MyAppName}
AppVersion={#MyAppVersion}
VersionInfoVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppUpdatesURL}
AppCopyright="© 2025 {#MyAppPublisher}, Inc. and its affiliates. All rights reserved. All Hyland product names are registered or unregistered trademarks of Hyland Software, Inc. or its affiliates."

; Outputs
OutputDir=..\..\dist

; Startup menu entry: "Publisher/Application Name", i.e.: "Nuxeo/Nuxeo Drive"
DefaultGroupName={#MyAppPublisher}
DisableProgramGroupPage=yes

; License file
LicenseFile=..\..\LICENSE.txt

; Icons
UninstallDisplayIcon={app}\{#MyAppExeName}
; 256x256px, generated from a PNG with https://convertico.com/
SetupIconFile=app_icon.ico

; Pictures
; 164x314px
WizardImageFile=wizard.bmp
; 55x58px
WizardSmallImageFile=wizard-small.bmp

; Use a modern look
WizardStyle=modern

; Other
Compression=lzma
SolidCompression=yes

; Disable the "close applications" prompt
CloseApplications=no

; Minimum Windows version required (Windows 8)
MinVersion=6.2.9200


[InstallDelete]
; This is required to handle upgrades from 5.4.0 (PyInstaller 5.0) which had different
; Qt DLL structure. Without this, orphaned 32-bit DLLs from 5.4.0 can cause
; "DLL load failed while importing QtCore: %1 is not a valid Win32 application" errors.
Type: filesandordirs; Name: "{app}\PyQt5"
Type: files; Name: "{app}\Qt*.dll"
Type: files; Name: "{app}\qt*.dll"
Type: files; Name: "{app}\python*.dll"
Type: files; Name: "{app}\vcruntime*.dll"
Type: files; Name: "{app}\msvcp*.dll"
Type: files; Name: "{app}\api-ms-*.dll"
Type: files; Name: "{app}\ucrtbase.dll"
Type: files; Name: "{app}\libcrypto*.dll"
Type: files; Name: "{app}\libssl*.dll"
Type: files; Name: "{app}\libffi*.dll"
Type: files; Name: "{app}\sqlite3.dll"


[UninstallDelete]
; Force the installation directory to be removed when uninstalling
Type: filesandordirs; Name: "{app}"


[UninstallRun]
Filename: "{app}\{#MyAppExeName}"; Parameters: "uninstall"
Filename: "taskkill"; Parameters: "/F /IM {#MyAppExeName}"


[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon


[Files]
Source: "..\..\dist\ndrive\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs


[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "dutch"; MessagesFile: "compiler:Languages\Dutch.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"
Name: "polish"; MessagesFile: "compiler:Languages\Polish.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

; Waiting for official support: http://www.jrsoftware.org/files/istrans/
Name: "basque"; MessagesFile: "unofficial_i18n\Basque.isl"
Name: "indonesian"; MessagesFile: "unofficial_i18n\Indonesian.isl"
Name: "swedish"; MessagesFile: "unofficial_i18n\Swedish.isl"


[Tasks]
; Create the desktop icon
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"


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
function IsNDriveRunning(): Boolean;
// Check if Nuxeo Drive is currently running by querying the task list.
// Writes tasklist output to a temp file and searches for the process name.
var
    ResultCode: Integer;
    TempFile: String;
    FileLines: TArrayOfString;
    I: Integer;
begin
    Result := False;
    TempFile := ExpandConstant('{tmp}\ndrive_check.txt');
    Exec(
        ExpandConstant('{sys}\cmd.exe'),
        '/C tasklist /FI "IMAGENAME eq {#MyAppExeName}" /NH > "' + TempFile + '"',
        '',
        SW_HIDE,
        ewWaitUntilTerminated,
        ResultCode
    );    if LoadStringsFromFile(TempFile, FileLines) then
    begin
        for I := 0 to GetArrayLength(FileLines) - 1 do
        begin
            if Pos('{#MyAppExeName}', LowerCase(FileLines[I])) > 0 then
            begin
                Result := True;
                Break;
            end;
        end;
    end;
    DeleteFile(TempFile);
end;

function InitializeSetup(): Boolean;
// Before setup begins, check whether Nuxeo Drive is running.
// If it is, ask the user for confirmation:
//   - Yes  → kill Nuxeo Drive and continue installation.
//   - No   → abort installation immediately.
var
    ResultCode: Integer;
    UserChoice: Integer;
begin
    Result := True;

    if IsNDriveRunning() then
    begin
        UserChoice := MsgBox(
            'Nuxeo Drive is currently running.' + #13#10 +
            'It must be closed before continuing with the installation.' + #13#10#13#10 +
            'Would you like to close Nuxeo Drive now and proceed with the installation?',
            mbConfirmation,
            MB_YESNO
        );
        if UserChoice = IDYES then
        begin
            // Kill the running process and let setup continue.
            if Exec(
                ExpandConstant('{sys}\taskkill.exe'),
                '/F /IM {#MyAppExeName}',
                '',
                SW_HIDE,
                ewWaitUntilTerminated,
                ResultCode
            ) and (ResultCode = 0) then
            begin
                Result := True;
            end
            else
            begin
                MsgBox(
                    'Unable to kill Nuxeo Drive. Please close the application manually and retry the installation.',
                    mbError,
                    MB_OK
                );
                Result := False;
            end;
        end
        else
        begin
            // User chose No – abort the installation silently.
            Result := False;
        end;
    end;
end;

function NeedEngineBinding(): Boolean;
// Check if the sysadmin wants to bind an engine.
// It will check mandatory arguments.
var
    url: String;
    username: String;
begin
    url := ExpandConstant('{param:TARGETURL}');
    username := ExpandConstant('{param:TARGETUSERNAME}');
    if (Length(url) > 0) and (Length(username) > 0) then
        Result := True;
end;
