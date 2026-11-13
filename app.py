"""로컬 웹 UI 서버. 실행: python app.py  →  http://127.0.0.1:5000"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import webbrowser

from flask import Flask, abort, jsonify, render_template, request, send_from_directory

from downloader import BROWSERS, COOKIE_FILE, DOWNLOAD_DIR, MODES, Job, JobManager

app = Flask(__name__)
manager = JobManager(workers=2)

HOST = "127.0.0.1"
PORT = int(os.environ.get("PORT", "5000"))


@app.get("/")
def index():
    return render_template("index.html", cookie_file=COOKIE_FILE.exists())


@app.post("/api/download")
def api_download():
    data = request.get_json(silent=True) or {}
    urls = [u.strip() for u in str(data.get("urls", "")).splitlines() if u.strip()]
    mode = data.get("mode", "auto")
    browser = data.get("browser", "")
    if mode not in MODES:
        return jsonify(error="잘못된 모드입니다."), 400
    if browser not in BROWSERS:
        return jsonify(error="지원하지 않는 브라우저입니다."), 400
    urls = [u for u in urls if u.startswith(("http://", "https://"))]
    if not urls:
        return jsonify(error="http(s)로 시작하는 링크를 입력하세요."), 400

    jobs = [
        manager.submit(Job(url=u, mode=mode, playlist=bool(data.get("playlist")), browser=browser))
        for u in urls[:50]
    ]
    return jsonify(ids=[j.id for j in jobs])


@app.get("/api/jobs")
def api_jobs():
    return jsonify(jobs=manager.list())


@app.post("/api/jobs/clear")
def api_clear():
    manager.clear_finished()
    return jsonify(ok=True)


@app.get("/files/<path:name>")
def files(name: str):
    if not DOWNLOAD_DIR.exists():
        abort(404)
    return send_from_directory(DOWNLOAD_DIR, name, as_attachment=request.args.get("dl") == "1")


@app.post("/api/open-folder")
def open_folder():
    DOWNLOAD_DIR.mkdir(exist_ok=True)
    if sys.platform == "win32":
        os.startfile(DOWNLOAD_DIR)  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(DOWNLOAD_DIR)])
    else:
        subprocess.Popen(["xdg-open", str(DOWNLOAD_DIR)])
    return jsonify(ok=True)


def _free_port(start: int) -> int:
    """start부터 비어 있는 포트를 찾는다(이미 실행 중인 창이 있어도 충돌 방지)."""
    for port in range(start, start + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((HOST, port))
                return port
            except OSError:
                continue
    raise RuntimeError("사용 가능한 포트를 찾지 못했습니다.")


if __name__ == "__main__":
    port = _free_port(PORT)
    url = f"http://{HOST}:{port}"
    if "--no-browser" not in sys.argv:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    print(f"  Running at {url}  (stop: Ctrl+C)")
    app.run(host=HOST, port=port, debug=False)
