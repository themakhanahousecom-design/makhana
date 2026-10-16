[Setup]
AppId=SidhuAI
AppName=SIDHU AI
AppVersion=0.1.0
DefaultDirName={localappdata}\Programs\SidhuAI
DefaultGroupName=SIDHU AI
PrivilegesRequired=lowest
OutputDir=..\dist\installer
OutputBaseFilename=SidhuAI-Setup
Compression=lzma2
SolidCompression=yes
UninstallDisplayIcon={app}\SidhuAI.exe

[Files]
Source: "..\dist\SidhuAI\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\SIDHU AI"; Filename: "{app}\SidhuAI.exe"; Parameters: "--supervise"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueName: "SidhuAI"; Flags: uninsdeletevalue

[Run]
Filename: "{app}\SidhuAI.exe"; Parameters: "--supervise"; Description: "Open SIDHU AI"; Flags: postinstall nowait skipifsilent
