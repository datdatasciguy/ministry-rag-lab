#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

[Setup]
AppId={{DD72C3AF-54F0-4E01-B268-71F88F1F973F}
AppName=Ministry Search RAG
AppVersion={#AppVersion}
AppPublisher=datdatasciguy
AppPublisherURL=https://github.com/datdatasciguy/ministry-rag-lab
DefaultDirName={localappdata}\Programs\Ministry Search RAG
DefaultGroupName=Ministry Search RAG
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename=MinistrySearchRAG-{#AppVersion}-windows-x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\Ministry Search RAG.exe
LicenseFile=..\LICENSE

[Tasks]
Name: ollama; Description: "Download and run official Ollama setup for local models"; Check: not OllamaInstalled

[Files]
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Ministry Search RAG"; Filename: "{app}\Ministry Search RAG.exe"

[Run]
Filename: "{tmp}\OllamaSetup.exe"; Tasks: ollama; Check: not OllamaInstalled; Flags: waituntilterminated
Filename: "{app}\Ministry Search RAG.exe"; Description: "Open Ministry Search RAG setup"; Flags: nowait postinstall skipifsilent

[Code]
var DownloadPage: TDownloadWizardPage;

function OllamaInstalled: Boolean;
begin
  Result := FileExists(ExpandConstant('{localappdata}\Programs\Ollama\ollama.exe'));
end;

procedure InitializeWizard;
begin
  DownloadPage := CreateDownloadPage('Downloading Ollama', 'Getting the official local model runtime. Its setup window will open next.', nil);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = wpReady) and WizardIsTaskSelected('ollama') and not OllamaInstalled then
  begin
    DownloadPage.Clear;
    DownloadPage.Add('https://ollama.com/download/OllamaSetup.exe', 'OllamaSetup.exe', '');
    DownloadPage.Show;
    try
      try
        DownloadPage.Download;
      except
        if not DownloadPage.AbortedByUser then SuppressibleMsgBox(GetExceptionMessage, mbCriticalError, MB_OK, IDOK);
        Result := False;
      end;
    finally
      DownloadPage.Hide;
    end;
  end;
end;
