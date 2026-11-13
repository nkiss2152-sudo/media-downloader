@echo off
chcp 65001 >nul
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo [!] Python이 없습니다. https://www.python.org/downloads/ 에서 설치하세요. 설치 시 "Add to PATH"를 체크하세요.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [*] 가상환경 만드는 중...
  python -m venv .venv || goto :fail
)

echo [*] 패키지 설치/업데이트 중... (yt-dlp는 자주 업데이트돼요)
".venv\Scripts\python.exe" -m pip install -q --upgrade pip
".venv\Scripts\python.exe" -m pip install -q --upgrade -r requirements.txt || goto :fail

where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo [!] ffmpeg가 없어서 고화질 영상 병합과 mp3 변환이 안 될 수 있어요.
  echo     설치: winget install Gyan.FFmpeg
)

".venv\Scripts\python.exe" app.py
pause
exit /b 0

:fail
echo [!] 설치 중 오류가 발생했습니다.
pause
exit /b 1
