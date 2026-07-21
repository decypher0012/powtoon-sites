@echo off
setlocal
python --version >nul 2>nul
if errorlevel 1 (
  echo Python is required but was not found.
  exit /b 1
)
if not exist .venv (
  python -m venv .venv
)
call .venv\Scripts\activate.bat
set PYTHONPATH=%CD%\src
python -m pip install -r requirements-dev.txt
python -m pytest
if errorlevel 1 exit /b 1
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul
python -m PyInstaller --distpath dist --workpath build --clean WorkLauncher.spec
if errorlevel 1 exit /b 1
python -m PyInstaller --distpath dist --workpath build --clean Updater.spec
if errorlevel 1 exit /b 1
if not exist dist\WorkLauncher.exe (
  echo dist\WorkLauncher.exe was not created.
  exit /b 1
)
if not exist dist\Updater.exe (
  echo dist\Updater.exe was not created.
  exit /b 1
)
if defined WORKLAUNCHER_SIGNING_THUMBPRINT (
  where signtool.exe >nul 2>nul
  if errorlevel 1 (
    echo WORKLAUNCHER_SIGNING_THUMBPRINT is set but signtool.exe was not found.
    exit /b 1
  )
  signtool.exe sign /sha1 %WORKLAUNCHER_SIGNING_THUMBPRINT% /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 dist\WorkLauncher.exe
  if errorlevel 1 exit /b 1
  signtool.exe sign /sha1 %WORKLAUNCHER_SIGNING_THUMBPRINT% /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 dist\Updater.exe
  if errorlevel 1 exit /b 1
)
set "ISCC_PATH="
where ISCC.exe >nul 2>nul && set "ISCC_PATH=ISCC.exe"
if not defined ISCC_PATH if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC_PATH=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not defined ISCC_PATH if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC_PATH=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC_PATH if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC_PATH=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC_PATH (
  echo Inno Setup 6 is required. Install JRSoftware.InnoSetup 6.7.3 and rerun build.bat.
  exit /b 1
)
for /f "usebackq delims=" %%V in (`python -c "from work_launcher.version import __version__; print(__version__)"`) do set "APP_VERSION=%%V"
for /f "usebackq delims=" %%V in (`python -c "from work_launcher.version import __version__; from work_launcher.update_models import parse_version; v=parse_version(__version__); print(f'{v.major}.{v.minor}.{v.patch}.0')"`) do set "FILE_VERSION=%%V"
if not defined APP_VERSION (
  echo Unable to read the canonical application version.
  exit /b 1
)
if not defined FILE_VERSION (
  echo Unable to derive the numeric Windows file version.
  exit /b 1
)
"%ISCC_PATH%" /Qp /DAppVersion=%APP_VERSION% /DFileVersion=%FILE_VERSION% installer\WorkLauncher.iss
if errorlevel 1 exit /b 1
if not exist dist\WorkLauncher-Setup.exe (
  echo dist\WorkLauncher-Setup.exe was not created.
  exit /b 1
)
if defined WORKLAUNCHER_SIGNING_THUMBPRINT (
  signtool.exe sign /sha1 %WORKLAUNCHER_SIGNING_THUMBPRINT% /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 dist\WorkLauncher-Setup.exe
  if errorlevel 1 exit /b 1
)
python tools\audit_installer.py
if errorlevel 1 exit /b 1
python tools\generate_release_assets.py
if errorlevel 1 exit /b 1
python tools\audit_release.py
if errorlevel 1 exit /b 1
echo Built dist\WorkLauncher.exe
for %%I in (dist\WorkLauncher.exe) do echo Size: %%~zI bytes
echo Built dist\Updater.exe
for %%I in (dist\Updater.exe) do echo Size: %%~zI bytes
echo Built dist\WorkLauncher-Setup.exe
for %%I in (dist\WorkLauncher-Setup.exe) do echo Size: %%~zI bytes
