"""本地上传视频的安全存储、解析和路径解析工具。"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional


BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "data" / "uploads"
LOCAL_PREFIX = "local://"
ALLOWED_EXTENSIONS = {
    ".mp4", ".m4v", ".mov", ".mkv", ".webm", ".avi", ".flv", ".wmv", ".ts",
}


def is_local_media_url(url: str) -> bool:
    return isinstance(url, str) and url.startswith(LOCAL_PREFIX)


def _token_from_url(url: str) -> Optional[str]:
    if not is_local_media_url(url):
        return None
    token = url[len(LOCAL_PREFIX):]
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{7,255}", token):
        return None
    return token


def resolve_local_path(url: str) -> Optional[str]:
    token = _token_from_url(url)
    if not token:
        return None

    upload_root = UPLOAD_DIR.resolve()
    candidate = (upload_root / token).resolve()
    if candidate.parent != upload_root or not candidate.is_file():
        return None
    return str(candidate)


def metadata_path_for(filename: str) -> Path:
    return UPLOAD_DIR / f"{filename}.json"


def write_metadata(filename: str, metadata: dict) -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    path = metadata_path_for(filename)
    temp_path = path.with_suffix(".tmp")
    with temp_path.open("w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False)
    temp_path.replace(path)


def read_metadata(filename: str) -> dict:
    try:
        with metadata_path_for(filename).open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _format_filesize(size: int) -> str:
    if size < 1024 * 1024:
        return f"{size / 1024:.0f}KB"
    if size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.1f}MB"
    return f"{size / (1024 * 1024 * 1024):.2f}GB"


def _format_duration(seconds: Optional[float]) -> str:
    if not seconds:
        return "00:00"
    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _probe_duration(path: str) -> Optional[float]:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    try:
        result = subprocess.run(
            [
                ffprobe, "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", path,
            ],
            capture_output=True,
            text=True,
            timeout=20,
            check=True,
        )
        return float(result.stdout.strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def build_local_video_info(url: str) -> dict:
    path = resolve_local_path(url)
    if not path:
        raise ValueError("本地视频不存在或上传标识已失效")

    filename = Path(path).name
    metadata = read_metadata(filename)
    title = metadata.get("original_name") or Path(path).stem
    extension = Path(path).suffix.lstrip(".").lower() or "mp4"
    size = os.path.getsize(path)
    duration = _probe_duration(path)

    return {
        "id": filename,
        "title": title,
        "thumbnail": "",
        "duration": duration,
        "duration_string": _format_duration(duration),
        "uploader": "本地文件",
        "platform": "Local Upload",
        "view_count": None,
        "upload_date": "",
        "description": f"本地上传 · {_format_filesize(size)}",
        "formats": [{
            "format_id": "local",
            "ext": extension,
            "resolution": "原始文件",
            "height": 0,
            "filesize": size,
            "filesize_approx": size,
            "vcodec": "unknown",
            "acodec": "unknown",
            "has_audio": True,
            "label": f"原始文件 {extension.upper()} ({_format_filesize(size)})",
        }],
        "subtitles": [],
        "automatic_captions": [],
    }
