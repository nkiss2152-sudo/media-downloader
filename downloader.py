"""YouTube / Instagram 다운로드 엔진.

- YouTube 및 Instagram 동영상: yt-dlp
- Instagram 이미지/캐러셀(여러 장) 게시물: gallery-dl (실패 시 yt-dlp로 재시도)
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import yt_dlp
from yt_dlp.utils import sanitize_filename

BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
COOKIE_FILE = BASE_DIR / "cookies.txt"

MODES = ("auto", "video", "audio", "image")
BROWSERS = ("", "chrome", "edge", "firefox", "brave", "opera", "whale")

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def detect_site(url: str) -> str:
    u = url.lower()
    if "instagram.com" in u:
        return "instagram"
    if "youtube.com" in u or "youtu.be" in u:
        return "youtube"
    return "other"


def _js_runtimes() -> dict:
    """유튜브 서명 해제(EJS)에 쓸 JS 런타임. 설치된 것만 켠다."""
    found = {name: {} for name in ("deno", "node", "bun") if shutil.which(name)}
    return found or {"deno": {}}


def _collect_ytdlp_files(info: dict | None, out: list[Path]) -> None:
    """yt-dlp info dict에서 최종 파일 경로를 모은다(재생목록 포함)."""
    if not info:
        return
    for entry in info.get("entries") or []:
        _collect_ytdlp_files(entry, out)
    for d in info.get("requested_downloads") or []:
        if d.get("filepath"):
            out.append(Path(d["filepath"]))
    for t in info.get("thumbnails") or []:
        if t.get("filepath"):
            out.append(Path(t["filepath"]))


@dataclass
class Job:
    url: str
    mode: str = "auto"
    playlist: bool = False
    browser: str = ""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    site: str = ""
    status: str = "queued"  # queued | running | done | error
    progress: float = 0.0
    title: str = ""
    log: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    created: float = field(default_factory=time.time)

    def add_log(self, msg: str) -> None:
        msg = ANSI_RE.sub("", str(msg)).strip()
        if msg:
            self.log.append(msg)
            del self.log[:-200]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "url": self.url,
            "mode": self.mode,
            "site": self.site,
            "status": self.status,
            "progress": round(self.progress, 1),
            "title": self.title,
            "log": self.log[-30:],
            "files": self.files,
            "created": self.created,
        }


class _Logger:
    def __init__(self, job: Job):
        self.job = job

    def debug(self, msg):
        if not msg.startswith("[debug]") and "[download]" not in msg:
            self.job.add_log(msg)

    def info(self, msg):
        self.job.add_log(msg)

    def warning(self, msg):
        self.job.add_log(f"경고: {msg}")

    def error(self, msg):
        self.job.add_log(f"오류: {msg}")


def _cookie_opts(job: Job) -> dict:
    if COOKIE_FILE.exists():
        return {"cookiefile": str(COOKIE_FILE)}
    if job.browser:
        return {"cookiesfrombrowser": (job.browser,)}
    return {}


def _run_ytdlp(job: Job) -> list[Path]:
    def hook(d):
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            if total:
                job.progress = min(99.0, d.get("downloaded_bytes", 0) * 100 / total)
        elif d.get("status") == "finished":
            job.progress = 99.0

    opts: dict = {
        "outtmpl": str(DOWNLOAD_DIR / "%(extractor_key)s" /
                       "%(uploader).40B - %(title).80B [%(id)s].%(ext)s"),
        "noplaylist": not job.playlist,
        "progress_hooks": [hook],
        "logger": _Logger(job),
        "windowsfilenames": True,
        "restrictfilenames": False,
        "ignoreerrors": False,
        "concurrent_fragment_downloads": 4,
        "js_runtimes": _js_runtimes(),
        **_cookie_opts(job),
    }

    if job.mode == "audio":
        opts["format"] = "ba/b"
        opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "0",
        }]
    elif job.mode == "image":
        opts["skip_download"] = True
        opts["writethumbnail"] = True
        opts["postprocessors"] = [{
            "key": "FFmpegThumbnailsConvertor",
            "format": "jpg",
            "when": "before_dl",
        }]
    else:  # auto / video
        opts["format"] = "bv*[ext=mp4]+ba[ext=m4a]/bv*+ba/b"
        opts["merge_output_format"] = "mp4"

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(job.url, download=True)
    if not info:
        return []
    job.title = info.get("title") or info.get("id") or ""
    files: list[Path] = []
    _collect_ytdlp_files(info, files)
    return files


def _best_image_url(entry: dict) -> str | None:
    """인스타 thumbnails 중 원본에 가장 가까운 이미지 주소.

    yt-dlp는 선호도 낮은 것부터 정렬하므로 마지막이 보통 크기 제한 없는 원본이다.
    잘린 정사각형(c0.… 크롭) 버전은 피한다.
    """
    thumbs = [t for t in entry.get("thumbnails") or [] if t.get("url")]
    if not thumbs:
        return entry.get("thumbnail")
    uncropped = [t for t in thumbs if not re.search(r"stp=c\d", t["url"])]
    return (uncropped or thumbs)[-1]["url"]


def _run_instagram(job: Job) -> list[Path]:
    """인스타 게시물(단일/캐러셀): 영상은 yt-dlp로, 사진은 원본 주소에서 직접 받는다.

    yt-dlp는 사진 항목을 'No video formats found'로 실패 처리하기 때문에
    정보만 먼저 받고(ignore_no_formats_error) 항목별로 나눠 처리한다.
    """
    opts: dict = {
        "outtmpl": str(DOWNLOAD_DIR / "Instagram" /
                       "%(uploader).40B - %(title).60B [%(id)s].%(ext)s"),
        "format": "bv*[ext=mp4]+ba[ext=m4a]/bv*+ba/b",
        "merge_output_format": "mp4",
        "ignore_no_formats_error": True,
        "noplaylist": False,
        "logger": _Logger(job),
        "windowsfilenames": True,
        "js_runtimes": _js_runtimes(),
        **_cookie_opts(job),
    }
    files: list[Path] = []
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(job.url, download=False)
        if not info:
            raise RuntimeError("게시물 정보를 가져오지 못했습니다.")
        job.title = info.get("title") or info.get("id") or ""
        post_id = info.get("id") or "post"
        owner = info.get("uploader") or info.get("channel") or "instagram"
        entries = [e for e in (info.get("entries") or [info]) if e]

        for idx, entry in enumerate(entries, 1):
            job.progress = (idx - 1) * 100 / len(entries)
            is_video = bool(entry.get("formats"))
            if is_video and job.mode != "image":
                done = ydl.process_ie_result(entry, download=True)
                _collect_ytdlp_files(done, files)
            elif not is_video and job.mode != "video":
                url = _best_image_url(entry)
                if not url:
                    job.add_log(f"{idx}번째 항목: 이미지 주소 없음, 건너뜀")
                    continue
                ext = Path(url.split("?")[0]).suffix.lower() or ".jpg"
                if ext not in (".jpg", ".jpeg", ".png", ".webp", ".heic"):
                    ext = ".jpg"
                name = sanitize_filename(f"{owner[:40]} - {post_id}_{idx:02d}{ext}",
                                         restricted=False)
                dest = DOWNLOAD_DIR / "Instagram" / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                if not dest.exists():
                    with ydl.urlopen(url) as resp:
                        dest.write_bytes(resp.read())
                job.add_log(f"[사진 {idx}/{len(entries)}] {dest.name}")
                files.append(dest)
    if not files:
        raise RuntimeError("받은 파일이 없음")
    return files


def _run_gallerydl(job: Job) -> list[Path]:
    cmd = [sys.executable, "-m", "gallery_dl", "-d", str(DOWNLOAD_DIR)]
    if COOKIE_FILE.exists():
        cmd += ["--cookies", str(COOKIE_FILE)]
    elif job.browser:
        cmd += ["--cookies-from-browser", job.browser]
    if job.mode == "video":
        cmd += ["--filter", "extension in ('mp4', 'webm', 'mov')"]
    elif job.mode == "image":
        cmd += ["--filter", "extension in ('jpg', 'jpeg', 'png', 'webp', 'heic')"]
    cmd.append(job.url)

    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    assert proc.stdout
    files: list[Path] = []
    for line in proc.stdout:
        job.add_log(line)
        # gallery-dl은 받은 파일 경로를 한 줄씩 출력한다(이미 있는 파일은 "# " 접두사).
        candidate = ANSI_RE.sub("", line).strip().removeprefix("# ").strip()
        if candidate and Path(candidate).is_file():
            files.append(Path(candidate))
    if proc.wait() != 0:
        raise RuntimeError(f"gallery-dl 종료 코드 {proc.returncode}")
    if not files:
        raise RuntimeError("gallery-dl이 받은 파일이 없음")
    return files


def run_job(job: Job) -> None:
    job.status = "running"
    job.site = detect_site(job.url)
    DOWNLOAD_DIR.mkdir(exist_ok=True)

    try:
        if job.site == "instagram" and job.mode != "audio":
            try:
                found = _run_instagram(job)
            except Exception as e:  # noqa: BLE001
                job.add_log(f"yt-dlp 실패({e}) → gallery-dl로 재시도")
                found = _run_gallerydl(job)
        else:
            found = _run_ytdlp(job)

        root = DOWNLOAD_DIR.resolve()
        rel: list[str] = []
        for p in found:
            p = p.resolve()
            if p.is_file() and p.is_relative_to(root):
                r = p.relative_to(root).as_posix()
                if r not in rel:
                    rel.append(r)
        job.files = rel
        if not job.files:
            job.add_log("받은 파일이 없습니다(로그인 쿠키가 필요할 수 있어요).")
        if not job.title and rel:
            job.title = Path(rel[0]).stem
        job.progress = 100.0
        job.status = "done"
    except Exception as e:  # noqa: BLE001
        job.add_log(f"오류: {e}")
        if job.site == "instagram":
            job.add_log("힌트: 인스타는 로그인 쿠키가 필요한 경우가 많습니다. README의 '쿠키 설정'을 참고하세요.")
        job.status = "error"


class JobManager:
    """동시에 최대 N개까지 다운로드를 실행하는 간단한 큐."""

    def __init__(self, workers: int = 2):
        self.jobs: dict[str, Job] = {}
        self._sem = threading.Semaphore(workers)
        self._lock = threading.Lock()

    def submit(self, job: Job) -> Job:
        with self._lock:
            self.jobs[job.id] = job
        threading.Thread(target=self._worker, args=(job,), daemon=True).start()
        return job

    def _worker(self, job: Job) -> None:
        with self._sem:
            run_job(job)

    def list(self) -> list[dict]:
        with self._lock:
            jobs = sorted(self.jobs.values(), key=lambda j: j.created, reverse=True)
        return [j.to_dict() for j in jobs]

    def clear_finished(self) -> None:
        with self._lock:
            for jid in [k for k, j in self.jobs.items() if j.status in ("done", "error")]:
                del self.jobs[jid]
