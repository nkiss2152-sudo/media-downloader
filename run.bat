@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo [!] Python not found. Install it from https://www.python.org/downloads/
  echo     and check "Add python.exe to PATH" during setup.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [*] Creating virtual environment...
  python -m venv .venv
  if errorlevel 1 goto fail
)

echo [*] Installing / updating packages... please wait
".venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check --upgrade -r requirements.txt
if errorlevel 1 goto fail

where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo [!] ffmpeg not found. HD video merge and mp3 may fail.
  echo     Install: winget install Gyan.FFmpeg
)

echo [*] Starting... the browser will open automatically.
".venv\Scripts\python.exe" app.py
pause
exit /b 0

:fail
echo [!] Setup failed. See the messages above.
pause
exit /b 1
