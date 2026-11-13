"""로컬 웹 UI 서버.

실행: python app.py
- 이 PC:            http://127.0.0.1:5000  (키 없이 접속)
- 같은 와이파이:     http://<내부IP>:5000/?key=<접속키>
- 외부(LTE 등):     화면의 '외부 접속 켜기' → https://….trycloudflare.com/?key=<접속키>
"""
from __future__ import annotations

import hmac
import io
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

import qrcode
import qrcode.image.svg
from flask import (Flask, abort, jsonify, make_response, redirect, render_template,
                   request, send_from_directory)

from downloader import BASE_DIR, BROWSERS, COOKIE_FILE, DOWNLOAD_DIR, MODES, Job, JobManager

app = Flask(__name__)
manager = JobManager(workers=2)

BIND = os.environ.get("BIND", "0.0.0.0")  # 같은 네트워크의 휴대폰·PC에서 접속 가능
PORT = int(os.environ.get("PORT", "5000"))
KEY_FILE = BASE_DIR / "access_key.txt"
COOKIE_NAME = "md_key"
LOOPBACK = {"127.0.0.1", "::1"}


def _load_key() -> str:
    """접속 키. 재시작해도 QR·주소가 바뀌지 않도록 파일에 저장한다."""
    env = os.environ.get("ACCESS_KEY", "").strip()
    if env:
        return env
    if KEY_FILE.exists():
        key = KEY_FILE.read_text(encoding="utf-8").strip()
        if key:
            return key
    key = secrets.token_urlsafe(8)
    KEY_FILE.write_text(key, encoding="utf-8")
    return key


ACCESS_KEY = _load_key()
state = {"port": PORT, "public_url": "", "tunnel": None, "tunnel_status": "off"}


# ── 접근 제어 ────────────────────────────────────────────────
def is_local() -> bool:
    """이 PC에서 직접 연 경우만 True. (Cloudflare 터널은 localhost로 들어오지만 헤더가 붙는다)"""
    return request.remote_addr in LOOPBACK and "Cf-Connecting-Ip" not in request.headers


def _key_ok(value: str | None) -> bool:
    return bool(value) and hmac.compare_digest(value, ACCESS_KEY)


@app.before_request
def guard():
    if is_local():
        return None
    if _key_ok(request.args.get("key")):
        # 키를 쿠키로 저장하고 주소창에서 키를 지운다
        resp = redirect(request.path)
        resp.set_cookie(COOKIE_NAME, ACCESS_KEY, max_age=60 * 60 * 24 * 90,
                        httponly=True, samesite="Lax", secure=request.is_secure or
                        request.headers.get("X-Forwarded-Proto") == "https")
        return resp
    if _key_ok(request.cookies.get(COOKIE_NAME)):
        return None
    if request.path.startswith("/api/"):
        return jsonify(error="접속 키가 필요합니다."), 401
    return make_response(render_template("login.html"), 401)


def local_only():
    if not is_local():
        abort(403)


# ── 페이지 / API ─────────────────────────────────────────────
@app.get("/")
def index():
    return render_template("index.html", cookie_file=COOKIE_FILE.exists(), local=is_local())


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
    local_only()
    DOWNLOAD_DIR.mkdir(exist_ok=True)
    if sys.platform == "win32":
        os.startfile(DOWNLOAD_DIR)  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(DOWNLOAD_DIR)])
    else:
        subprocess.Popen(["xdg-open", str(DOWNLOAD_DIR)])
    return jsonify(ok=True)


# ── 공유(다른 기기 접속) ─────────────────────────────────────
def lan_ip() -> str | None:
    """기본 네트워크 인터페이스의 내부 IP (실제로 패킷은 보내지 않음)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            return None if ip.startswith("127.") else ip
    except OSError:
        return None


def qr_svg(text: str) -> str:
    img = qrcode.make(text, image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=2)
    buf = io.BytesIO()
    img.save(buf)
    svg = buf.getvalue().decode("utf-8")
    return svg[svg.find("<svg"):]


def find_cloudflared() -> str | None:
    found = shutil.which("cloudflared")
    if found:
        return found
    for p in (r"C:\Program Files (x86)\cloudflared\cloudflared.exe",
              r"C:\Program Files\cloudflared\cloudflared.exe"):
        if Path(p).exists():
            return p
    return None


def _start_tunnel() -> None:
    exe = find_cloudflared()
    if not exe:
        state["tunnel_status"] = "missing"
        return
    state["tunnel_status"] = "starting"
    proc = subprocess.Popen(
        [exe, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{state['port']}"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        encoding="utf-8", errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    state["tunnel"] = proc
    assert proc.stdout
    for line in proc.stdout:
        m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
        if m and not state["public_url"]:
            state["public_url"] = m.group(0)
            state["tunnel_status"] = "on"
            print(f"  External: {state['public_url']}/?key={ACCESS_KEY}")
    # 사용자가 끈 게 아니라 주소를 얻기 전에 종료됐다면 실패로 표시
    failed = state["tunnel_status"] == "starting"
    state.update(public_url="", tunnel=None, tunnel_status="failed" if failed else "off")


@app.post("/api/tunnel")
def api_tunnel():
    local_only()
    on = (request.get_json(silent=True) or {}).get("on", True)
    if on and not state["tunnel"]:
        threading.Thread(target=_start_tunnel, daemon=True).start()
    elif not on and state["tunnel"]:
        state["tunnel"].terminate()
        state.update(public_url="", tunnel_status="off")
    return jsonify(ok=True)


@app.get("/api/share")
def api_share():
    local_only()
    links = []
    ip = lan_ip()
    if ip and BIND != "127.0.0.1":
        url = f"http://{ip}:{state['port']}/?key={ACCESS_KEY}"
        links.append({"kind": "lan", "label": "같은 와이파이", "url": url, "qr": qr_svg(url)})
    if state["public_url"]:
        url = f"{state['public_url']}/?key={ACCESS_KEY}"
        links.append({"kind": "public", "label": "어디서나(인터넷)", "url": url, "qr": qr_svg(url)})
    return jsonify(links=links, key=ACCESS_KEY, tunnel=state["tunnel_status"],
                   cloudflared=bool(find_cloudflared()))


# ── 실행 ─────────────────────────────────────────────────────
def _free_port(start: int) -> int:
    """start부터 비어 있는 포트를 찾는다(이미 실행 중인 창이 있어도 충돌 방지)."""
    for port in range(start, start + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((BIND, port))
                return port
            except OSError:
                continue
    raise RuntimeError("사용 가능한 포트를 찾지 못했습니다.")


if __name__ == "__main__":
    port = _free_port(PORT)
    state["port"] = port
    local_url = f"http://127.0.0.1:{port}"
    print(f"  This PC : {local_url}")
    ip = lan_ip()
    if ip and BIND != "127.0.0.1":
        print(f"  Wi-Fi   : http://{ip}:{port}/?key={ACCESS_KEY}")
    print("  (stop: Ctrl+C)")
    if "--public" in sys.argv:
        threading.Thread(target=_start_tunnel, daemon=True).start()
    if "--no-browser" not in sys.argv:
        threading.Timer(1.0, lambda: webbrowser.open(local_url)).start()
    try:
        app.run(host=BIND, port=port, debug=False)
    finally:
        if state["tunnel"]:
            state["tunnel"].terminate()
