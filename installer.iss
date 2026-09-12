; Douyin Downloader — Inno Setup script.
; Build:  iscc installer.iss   (cần Inno Setup 6)
; Ra:     installer/DouyinDownloader-Setup-1.0.0.exe
; Cài vào {autopf}\DouyinDownloader, không cần admin.

#define AppVersion "1.0.0"
#define SrcRoot "."

[Setup]
AppName=Douyin Downloader
AppVersion={#AppVersion}
AppPublisher=BDTG
DefaultDirName={autopf}\DouyinDownloader
DefaultGroupName=Douyin Downloader
PrivilegesRequired=lowest
OutputDir=installer
OutputBaseFilename=DouyinDownloader-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
SetupIconFile=assets/icon.ico
UninstallDisplayName=Douyin Downloader
UninstallDisplayIcon={app}\app\DouyinDownloader.exe
; Giữ downloads + cookie khi gỡ (chỉ xóa file app đã cài)
UninstallFilesDir={app}\uninstall

[Files]
; --- app Qt (PyInstaller) ---
Source: "{#SrcRoot}\dist\DouyinDownloader\*"; DestDir: "{app}\app"; Flags: recursesubdirs ignoreversion
; --- engine Python (source, không kèm secret) ---
Source: "{#SrcRoot}\engine\api\*";   DestDir: "{app}\engine\api"; Flags: recursesubdirs ignoreversion
Source: "{#SrcRoot}\engine\core\*";  DestDir: "{app}\engine\core"; Flags: recursesubdirs ignoreversion
Source: "{#SrcRoot}\engine\gallery\*";      DestDir: "{app}\engine\gallery";      Flags: recursesubdirs ignoreversion
Source: "{#SrcRoot}\engine\web\*";          DestDir: "{app}\engine\web";          Flags: recursesubdirs ignoreversion
Source: "{#SrcRoot}\engine\aliases.json";   DestDir: "{app}\engine"; Flags: ignoreversion
Source: "{#SrcRoot}\engine\subjects.json";  DestDir: "{app}\engine"; Flags: ignoreversion skipifsourcedoesntexist
Source: "{#SrcRoot}\engine\api\config.native.example.yml"; DestDir: "{app}\engine\api"; Flags: ignoreversion
; --- engine venv (đóng gói sẵn, khỏi pip install) ---
Source: "{#SrcRoot}\engine\.venv\*"; DestDir: "{app}\engine\.venv"; Flags: recursesubdirs ignoreversion

[Dirs]
Name: "{app}\engine\downloads"
Name: "{app}\engine\logs"

[Icons]
Name: "{group}\Douyin Downloader"; Filename: "{app}\app\DouyinDownloader.exe"; IconFilename: "{app}\app\DouyinDownloader.exe"
Name: "{autodesktop}\Douyin Downloader"; Filename: "{app}\app\DouyinDownloader.exe"; IconFilename: "{app}\app\DouyinDownloader.exe"; Tasks: desktopicon

[Tasks]
Name: desktopicon; Description: "Tạo icon ngoài Desktop"; Flags: checkedonce

[Run]
Filename: "{app}\app\DouyinDownloader.exe"; Description: "Chạy Douyin Downloader"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  ExFile, CfgFile: String;
begin
  if CurStep = ssPostInstall then
  begin
    { Lần đầu: tạo config.native.yml từ mẫu. Nâng cấp: giữ nguyên file cũ. }
    ExFile := ExpandConstant('{app}\engine\api\config.native.example.yml');
    CfgFile := ExpandConstant('{app}\engine\api\config.native.yml');
    if (not FileExists(CfgFile)) and FileExists(ExFile) then
      CopyFile(ExFile, CfgFile, False);
  end;
end;

function InitializeUninstall(): Boolean;
begin
  { Giữ lại downloads + cookie khi gỡ }
  Result := True;
end;
