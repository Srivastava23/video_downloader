import os
import shutil
import tempfile
import time
import json
import datetime
from pathlib import Path
from threading import Thread

from flask import Flask, request, send_file, jsonify, abort
from flask_cors import CORS
import yt_dlp
import requests
from werkzeug.utils import secure_filename
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# ---------- Config ----------
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "https://reeloader.netlify.app")
API_KEY = os.getenv("API_KEY", "secret123")
MAX_SIMULTANEOUS = int(os.getenv("MAX_SIMULTANEOUS", "2"))
BASE_TMP = Path(tempfile.gettempdir()) / "viddl"
BASE_TMP.mkdir(parents=True, exist_ok=True)
COUNTER_FILE = Path("counter.json")
DOWNLOAD_DIR = Path.home() / "Downloads"

# ---------- Cookie Setup ----------
COOKIE_FILE = Path("cookies.txt")
YOUTUBE_COOKIES = os.getenv("YOUTUBE_COOKIES")
if YOUTUBE_COOKIES:
    COOKIE_FILE.write_text(YOUTUBE_COOKIES)

app = Flask(__name__)
CORS(app, supports_credentials=True, origins=[FRONTEND_ORIGIN])

@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = FRONTEND_ORIGIN
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-API-KEY"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response

limiter = Limiter(get_remote_address, app=app, default_limits=["50 per hour"])
_active_downloads = 0


def _inc_active():
    global _active_downloads
    _active_downloads += 1


def _dec_active():
    global _active_downloads
    _active_downloads = max(0, _active_downloads - 1)


def cleanup_path(path: Path, delay=5):
    def _cleanup():
        time.sleep(delay)
        try:
            if path.is_dir():
                shutil.rmtree(path)
            elif path.exists():
                path.unlink()
        except Exception:
            pass
    Thread(target=_cleanup, daemon=True).start()


def inc_counter():
    today = datetime.date.today().isoformat()
    try:
        data = json.loads(COUNTER_FILE.read_text())
    except Exception:
        data = {}
    data[today] = data.get(today, 0) + 1
    COUNTER_FILE.write_text(json.dumps(data))


def _format_seconds(s):
    if not s:
        return "00:00"
    h, rem = divmod(int(s), 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h:02d}:{m:02d}:{sec:02d}"
    return f"{m:02d}:{sec:02d}"


@app.before_request
def check_key():
    if request.method == "OPTIONS":
        return '', 200
    if request.endpoint in ["download", "formats", "playlist_info"]:
        key = request.headers.get("X-API-KEY")
        if key != API_KEY:
            abort(403)


# ---------- ROOT ----------
@app.route("/", methods=["GET", "HEAD", "OPTIONS"])
@limiter.exempt
def root():
    return jsonify({"status": "ok"}), 200


# ---------- Helper: Fallback to Piped API ----------
def fetch_piped_info(url):
    try:
        import re
        match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", url)
        if not match:
            return None
        vid = match.group(1)
        api = f"https://pipedapi.kavin.rocks/streams/{vid}"
        res = requests.get(api, timeout=10)
        if res.status_code != 200:
            return None
        data = res.json()
        fmts = [
            {"id": f.get("qualityLabel"), "label": f"{f.get('qualityLabel')} | {f.get('mimeType')}", "url": f.get("url")}
            for f in data.get("videoStreams", [])
        ]
        return {"title": data.get("title"), "formats": fmts}
    except Exception:
        return None


# ---------- FORMATS ----------
@app.route("/formats", methods=["POST", "OPTIONS"])
@limiter.limit("20 per hour")
def formats():
    data = request.get_json() or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "no url"}), 400

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "cookiefile": str(COOKIE_FILE) if COOKIE_FILE.exists() else None,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        piped = fetch_piped_info(url)
        if piped:
            return jsonify(piped)
        return jsonify({"error": str(e)}), 400

    if not info.get("formats"):
        return jsonify({"error": "No formats found."}), 404

    formats = []
    for f in info["formats"]:
        height = f.get("height")
        ext = f.get("ext", "")
        acodec = f.get("acodec", "")
        vcodec = f.get("vcodec", "")
        fps = f.get("fps", 0)
        size = f.get("filesize") or f.get("filesize_approx")

        if not size and f.get("url"):
            try:
                r = requests.head(f["url"], timeout=3)
                if "Content-Length" in r.headers:
                    size = int(r.headers["Content-Length"])
            except Exception:
                pass

        size_mb = round(size / (1024 * 1024), 1) if size else None
        label_parts = []
        if height:
            label_parts.append(f"{height}p")
        if fps:
            label_parts.append(f"{fps}fps")
        if vcodec and vcodec != "none":
            label_parts.append(vcodec)
        if acodec and acodec != "none":
            label_parts.append(acodec)
        label_parts.append(f"{size_mb or '?'} MB")
        label_parts.append(ext)

        label = " | ".join(label_parts)
        formats.append({"id": f["format_id"], "label": label})

    formats = sorted(formats, key=lambda x: int(x["label"].split("p")[0]) if "p" in x["label"] else 0, reverse=True)
    return jsonify({"title": info.get("title"), "formats": formats})


# ---------- PLAYLIST INFO ----------
@app.route("/playlist_info", methods=["POST", "OPTIONS"])
@limiter.limit("30 per hour")
def playlist_info():
    data = request.get_json() or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "no url"}), 400

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "cookiefile": str(COOKIE_FILE) if COOKIE_FILE.exists() else None,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    if not info.get("entries"):
        duration = info.get("duration") or 0
        return jsonify({
            "is_playlist": False,
            "count": 1,
            "total_seconds": duration,
            "total_human": _format_seconds(duration),
            "items": [{
                "index": 1,
                "title": info.get("title"),
                "duration": duration,
                "duration_human": _format_seconds(duration),
                "thumbnail": info.get("thumbnail"),
                "url": info.get("webpage_url")
            }]
        })

    entries = []
    total = 0
    for idx, e in enumerate(info.get("entries"), 1):
        if not e:
            continue
        dur = e.get("duration") or 0
        total += dur
        entries.append({
            "index": e.get("playlist_index") or idx,
            "title": e.get("title") or "Untitled",
            "duration": dur,
            "duration_human": _format_seconds(dur),
            "thumbnail": e.get("thumbnail"),
            "url": e.get("webpage_url")
        })

    return jsonify({
        "is_playlist": True,
        "count": len(entries),
        "total_seconds": total,
        "total_human": _format_seconds(total),
        "items": entries
    })


# ---------- DOWNLOAD ----------
@app.route("/download", methods=["POST", "OPTIONS"])
@limiter.limit("5 per hour")
def download():
    global _active_downloads
    if _active_downloads >= MAX_SIMULTANEOUS:
        return jsonify({"error": "server busy"}), 429

    data = request.get_json() or {}
    url = data.get("url", "").strip()
    fmt = data.get("format_id")
    mode = data.get("mode", "combined")
    save_as_zip = bool(data.get("zip", False))

    if not url:
        return jsonify({"error": "no url"}), 400

    tmpdir = Path(tempfile.mkdtemp(prefix="viddl_", dir=BASE_TMP))
    _inc_active()
    inc_counter()

    try:
        ydl_probe_opts = {
            "quiet": True,
            "no_warnings": True,
            "cookiefile": str(COOKIE_FILE) if COOKIE_FILE.exists() else None,
        }
        with yt_dlp.YoutubeDL(ydl_probe_opts) as ydlp:
            info = ydlp.extract_info(url, download=False)

        is_playlist = "list=" in url
        duration = info.get("duration") or 0
        total_videos = len(info.get("entries", [])) if info.get("entries") else 1

        is_long_video = duration > 3600
        is_large_playlist = total_videos > 10

        if mode == "audio":
            fmt_str = "bestaudio"
        elif mode == "video":
            fmt_str = "bestvideo"
        else:
            fmt_str = "bv*+ba/b"

        if fmt:
            fmt_str = fmt

        outtmpl = (
            str(tmpdir / "%(playlist_title)s" / "%(playlist_index)02d - %(title)s.%(ext)s")
            if is_playlist else str(tmpdir / "%(title)s.%(ext)s")
        )

        ydl_opts = {
            "format": fmt_str,
            "outtmpl": outtmpl,
            "merge_output_format": "mp4" if mode != "audio" else "m4a",
            "noplaylist": not is_playlist,
            "quiet": True,
            "no_warnings": True,
            "cookiefile": str(COOKIE_FILE) if COOKIE_FILE.exists() else None,
        }

        if mode == "combined" and (is_long_video or is_large_playlist):
            ydl_opts_video = ydl_opts.copy()
            ydl_opts_audio = ydl_opts.copy()
            ydl_opts_video["format"] = "bestvideo[height<=1080]"
            ydl_opts_video["outtmpl"] = str(tmpdir / "%(title)s_video.%(ext)s")
            ydl_opts_audio["format"] = "bestaudio"
            ydl_opts_audio["outtmpl"] = str(tmpdir / "%(title)s_audio.%(ext)s")

            with yt_dlp.YoutubeDL(ydl_opts_video) as ydlv:
                ydlv.download([url])
            with yt_dlp.YoutubeDL(ydl_opts_audio) as ydla:
                ydla.download([url])
        else:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

        files = list(tmpdir.glob("*"))
        if not files:
            raise RuntimeError("no file downloaded")

        preferred = next((f for f in files if f.suffix.lower() in [".mp4", ".m4a"]), files[0])
        filename = secure_filename(preferred.name)
        resp = send_file(str(preferred), as_attachment=True, download_name=filename)
        cleanup_path(tmpdir, delay=10)
        return resp

    except Exception as e:
        cleanup_path(tmpdir, delay=2)
        return jsonify({"error": str(e)}), 500
    finally:
        _dec_active()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
