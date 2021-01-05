; Setup details

AppName={#MyAppName}
AppVersion={#MyAppVersion}
VersionInfoVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppUpdatesURL}
AppCopyright="© {#MyAppPublisher}. All rights reserved."

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

; Controls which files Setup will check for being in use before upgrading
CloseApplicationsFilter=*.*

; Minimum Windows version required (Windows 8)
MinVersion=6.2.9200


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
