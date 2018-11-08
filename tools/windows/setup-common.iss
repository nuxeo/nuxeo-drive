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

; Minimum Windows version required
; http://www.jrsoftware.org/ishelp/index.php?topic=winvernotes
MinVersion=6.1.7600

; Other
Compression=lzma
SolidCompression=yes

; Controls which files Setup will check for being in use before upgrading
CloseApplicationsFilter=*.*


[UninstallDelete]
; Force the installation directory to be removed when uninstalling
Type: filesandordirs; Name: "{app}"



[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon


[Files]
Source: "..\..\dist\ndrive\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs


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
