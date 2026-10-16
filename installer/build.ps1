$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
py -3.12 -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 is required' }
& .\.venv\Scripts\python.exe -m pip install -e '.[desktop,browser,documents,dev]'
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
& .\.venv\Scripts\python.exe -m pytest
if ($LASTEXITCODE -ne 0) { throw 'Tests failed' }
$bundleArguments = @(
    '--noconfirm', '--clean', '--windowed', '--onedir', '--name', 'SidhuAI',
    '--collect-all', 'vosk',
    '--collect-submodules', 'pyttsx3.drivers',
    '--hidden-import', 'pyttsx3.drivers.sapi5',
    '--hidden-import', 'comtypes.client',
    '--collect-all', 'sounddevice',
    '--collect-all', 'pypdf',
    '--collect-all', 'playwright',
    '--collect-data', 'sidhu',
    # These modules are imported lazily by the avatar. Let PyInstaller's Qt hooks
    # collect their runtime/QML dependencies instead of collecting all PySide6.
    '--hidden-import', 'PySide6.QtQml',
    '--hidden-import', 'PySide6.QtQuick',
    '--hidden-import', 'PySide6.QtQuickWidgets',
    '--hidden-import', 'PySide6.QtQuick3D',
    'sidhu/app_entry.py'
)
& .\.venv\Scripts\python.exe -m PyInstaller @bundleArguments
if ($LASTEXITCODE -ne 0) { throw 'Packaging failed' }
Write-Host 'Portable app: dist\SidhuAI\SidhuAI.exe. Build installer with Inno Setup 6: ISCC installer\sidhu.iss'
