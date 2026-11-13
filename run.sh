#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install -q --upgrade pip
.venv/bin/python -m pip install -q --upgrade -r requirements.txt

command -v ffmpeg >/dev/null || echo "[!] ffmpeg가 없어요. (macOS: brew install ffmpeg / Ubuntu: sudo apt install ffmpeg)"

exec .venv/bin/python app.py
