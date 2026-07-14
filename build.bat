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
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python -m pytest
if errorlevel 1 exit /b 1
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul
del /q WorkLauncher.spec 2>nul
python -m PyInstaller --noconsole --name WorkLauncher --onefile --distpath dist --workpath build --clean src\work_launcher\__main__.py
if errorlevel 1 exit /b 1
if not exist dist\WorkLauncher.exe (
  echo dist\WorkLauncher.exe was not created.
  exit /b 1
)
echo Built dist\WorkLauncher.exe
for %%I in (dist\WorkLauncher.exe) do echo Size: %%~zI bytes
