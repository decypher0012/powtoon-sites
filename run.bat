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
python -m work_launcher
if errorlevel 1 (
  echo Launch failed.
  exit /b 1
)
