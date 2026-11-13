from __future__ import annotations

import json
import mimetypes
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
MAX_MEDIA_BYTES = 200 * 1024 * 1024
VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".mkv", ".m4v"}

app = FastAPI(title="TokSave", version="1.0.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class LinkRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2048)


class DownloadRequest(LinkRequest):
    media_type: str = Field(default="video", pattern="^(video|audio)$")


def cleanup_directory(path: str) -> None:
    shutil.rmtree(path, ignore_errors=True)


def validate_tiktok_url(raw_url: str) -> str:
    url = raw_url.strip()
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower().rstrip(".")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Đường dẫn URL không hợp lệ.") from exc

    allowed = host == "tiktok.com" or host.endswith(".tiktok.com")
    if parsed.scheme not in {"http", "https"} or not allowed:
        raise HTTPException(status_code=400, detail="Chỉ chấp nhận liên kết http(s) thuộc tên miền TikTok.")
    if parsed.username or parsed.password:
        raise HTTPException(status_code=400, detail="URL không được chứa thông tin đăng nhập.")
    return url


def ytdlp_options() -> dict:
    return {
        "format": (
            "best[vcodec=h264][acodec!=none]/"
            "best[vcodec^=avc1][acodec!=none]/"
            "bestvideo[vcodec=h264]+bestaudio/"
            "bestvideo[vcodec^=avc1]+bestaudio/"
            "best[vcodec!=none][acodec!=none]/"
            "bestvideo*+bestaudio/best"
        ),
        "merge_output_format": "mp4",
        "check_formats": True,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": False,
        "socket_timeout": 30,
        "retries": 3,
        "fragment_retries": 3,
        "max_filesize": MAX_MEDIA_BYTES,
    }


def extract_video_info(url: str) -> dict:
    with yt_dlp.YoutubeDL({**ytdlp_options(), "skip_download": True}) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info:
        raise RuntimeError("Nguồn không trả về thông tin video.")
    return {
        "title": info.get("title") or "Video TikTok",
        "uploader": info.get("uploader") or info.get("channel") or "Không rõ",
        "duration": info.get("duration"),
        "thumbnail": info.get("thumbnail"),
        "webpage_url": info.get("webpage_url") or url,
        "extractor": info.get("extractor_key") or info.get("extractor") or "TikTok",
    }


def ensure_ffmpeg() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("Chưa tìm thấy FFmpeg. Trên Windows có thể cài bằng: scoop install ffmpeg")
    return ffmpeg


def verify_video(path: Path) -> None:
    ffprobe = shutil.which("ffprobe")
    ffmpeg = ensure_ffmpeg()
    if not ffprobe:
        raise RuntimeError("Không tìm thấy ffprobe. Hãy cài FFmpeg và thêm vào PATH.")
    result = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "stream=codec_type,codec_name",
         "-of", "json", str(path)],
        capture_output=True, text=True, timeout=30, check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("Không đọc được cấu trúc tệp video.")
    try:
        streams = json.loads(result.stdout).get("streams", [])
    except (json.JSONDecodeError, AttributeError):
        streams = []
    videos = [s for s in streams if s.get("codec_type") == "video"]
    if not videos:
        raise RuntimeError("Tệp tải về không có luồng hình ảnh.")
    if (videos[0].get("codec_name") or "").lower() not in {"h264", "avc1"}:
        converted = path.with_name("converted_h264.mp4")
        try:
            result = subprocess.run(
                [ffmpeg, "-y", "-i", str(path), "-map", "0:v:0", "-map", "0:a?",
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                 "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
                 "-movflags", "+faststart", str(converted)],
                capture_output=True, text=True, timeout=600, check=False,
            )
            if result.returncode or not converted.exists() or converted.stat().st_size == 0:
                raise RuntimeError("Không thể chuyển video sang MP4 tương thích.")
            converted.replace(path)
        finally:
            converted.unlink(missing_ok=True)


@app.get("/", response_class=HTMLResponse)
def home():
    return FileResponse(STATIC_DIR / "index.html", media_type="text/html; charset=utf-8")


@app.get("/sitemap.xml")
def get_sitemap():
    return FileResponse(STATIC_DIR / "sitemap.xml", media_type="application/xml")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/info")
def get_info(request: LinkRequest):
    url = validate_tiktok_url(request.url)
    try:
        return extract_video_info(url)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Không lấy được thông tin video: {str(exc)[:250]}") from exc


@app.post("/api/download")
def download_media(request: DownloadRequest):
    url = validate_tiktok_url(request.url)
    temp_dir = tempfile.mkdtemp(prefix="toksave_")
    outtmpl = str(Path(temp_dir) / "media.%(ext)s")
    options = ytdlp_options()
    options["outtmpl"] = outtmpl

    if request.media_type == "audio":
        options["format"] = "bestaudio/best"
        options["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }]
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.extract_info(url, download=True)

        expected_exts = {".mp3"} if request.media_type == "audio" else VIDEO_EXTENSIONS
        candidates = [p for p in Path(temp_dir).rglob("*") if p.is_file() and p.suffix.lower() in expected_exts]
        if not candidates:
            raise RuntimeError("Không tìm thấy tệp đầu ra. Hãy kiểm tra liên kết và cài FFmpeg.")
        candidates.sort(key=lambda p: p.stat().st_size, reverse=True)
        output = candidates[0]
        if output.stat().st_size <= 0:
            raise RuntimeError("Tệp tải về rỗng.")
        if output.stat().st_size > MAX_MEDIA_BYTES:
            raise RuntimeError("Tệp vượt giới hạn 200 MiB của bản demo.")
        if request.media_type == "video":
            verify_video(output)
        media = "audio/mpeg" if request.media_type == "audio" else (mimetypes.guess_type(output.name)[0] or "video/mp4")
        filename = "toksave-audio.mp3" if request.media_type == "audio" else "toksave-video" + output.suffix.lower()
        return FileResponse(
            path=str(output), media_type=media, filename=filename,
            background=BackgroundTask(cleanup_directory, temp_dir),
        )
    except HTTPException:
        cleanup_directory(temp_dir)
        raise
    except Exception as exc:
        cleanup_directory(temp_dir)
        raise HTTPException(status_code=422, detail=f"Không tải được tệp: {str(exc)[:300]}") from exc
