#define AppName "GPUPress"
#define AppVersion "0.1.0"
#define AppPublisher "BAS1C VISUALS"
#define AppDisplayName "GPUPress — by BAS1C VISUALS"
#define AppExeName "GPUPress.exe"
#define AppId "{{C8EE6532-4848-4BA7-BA5E-3DF2A3F631B1}"
#define AppStage "..\build\installer-stage\GPUPress"

[Setup]
AppId={#AppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppDisplayName}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\GPUPress
DefaultGroupName=GPUPress
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
VersionInfoVersion=0.1.0.0
VersionInfoProductVersion={#AppVersion}
VersionInfoCompany={#AppPublisher}
VersionInfoDescription=GPUPress Windows Installer
VersionInfoProductName={#AppName}
LicenseFile=..\LICENSE
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\GPUPress.exe
OutputDir=..\dist\installer
OutputBaseFilename=GPUPress-Setup-v0.1.0
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
Uninstallable=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "{#AppStage}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\THIRD_PARTY_NOTICES.md"; DestDir: "{app}\Documentation"; Flags: ignoreversion
Source: "..\third_party\ffmpeg\README.md"; DestDir: "{app}\Documentation\FFmpeg"; Flags: ignoreversion
Source: "..\third_party\ffmpeg\LICENSES.md"; DestDir: "{app}\Documentation\FFmpeg"; Flags: ignoreversion
Source: "..\third_party\ffmpeg\SOURCE.md"; DestDir: "{app}\Documentation\FFmpeg"; Flags: ignoreversion
Source: "..\third_party\ffmpeg\BUILD-OUTPUTS.txt"; DestDir: "{app}\Documentation\FFmpeg"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\GPUPress\GPUPress"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\_internal\assets\icon.ico"
Name: "{autodesktop}\GPUPress"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\_internal\assets\icon.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch GPUPress"; WorkingDir: "{app}"; Flags: postinstall nowait skipifsilent

[Code]
procedure InitializeWizard;
begin
  CreateOutputMsgPage(
    wpLicense,
    'Third-party components',
    'Licenses for bundled third-party components are separate.',
    'The GPUPress source code is licensed under the MIT License shown on the previous page. This installer also includes FFmpeg and FFprobe as separate third-party components. Their applicable license and distribution requirements are not covered by the GPUPress MIT License.'
  );
end;
