"""AI 视频总结模块：字幕提取 + 多供应商大模型总结"""

import json
import hashlib
import os
import re
import shutil
import tempfile
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Iterator
from pathlib import Path
from typing import Callable, Optional

import httpx
import yt_dlp
from openai import OpenAI


QUIZ_BATCH_SPECS = (
    {"type": "single", "label": "单选题", "count": 5, "points": 4, "max_tokens": 3072},
    {"type": "multiple", "label": "多选题", "count": 3, "points": 6, "max_tokens": 2560},
    {"type": "true_false", "label": "判断题", "count": 3, "points": 4, "max_tokens": 2048},
    {"type": "short_answer", "label": "简答题", "count": 3, "points": 10, "max_tokens": 3072},
    {"type": "analysis", "label": "分析题", "count": 2, "points": 10, "max_tokens": 3072},
)
from local_media import is_local_media_url, resolve_local_path
from settings import load_backend_env
from cookies import common_ydl_opts, cookie_header


load_backend_env()


ChatMessage = dict[str, str]


def _parse_json_object(text: str) -> dict:
    """解析模型返回的 JSON，兼容 Markdown 代码块包装。"""
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("模型没有返回有效的 JSON 题卷")
        try:
            data = json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError as exc:
            raise ValueError("模型返回的题卷 JSON 格式不正确") from exc

    if not isinstance(data, dict):
        raise ValueError("模型返回的题卷格式不正确")
    return data


def _is_bilibili_url(url: str) -> bool:
    return "bilibili.com" in url or "b23.tv" in url


class SubtitleExtractor:
    """从视频 URL 提取平台字幕（人工字幕 > 自动字幕）"""

    PREFERRED_LANGS = ["zh-Hans", "zh", "zh-CN", "en", "ja", "ko"]
    SUBTITLE_FORMAT = "json3"
    CACHE_DIR = Path(__file__).resolve().parent / "data" / "subtitles"
    CACHE_VERSION = 1

    def __init__(self):
        self.cache_ttl_seconds = max(
            0, int(os.getenv("SUBTITLE_CACHE_TTL_SECONDS", str(30 * 24 * 60 * 60)))
        )
        self.CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, url: str) -> Path:
        bvid = self._parse_bvid(url)
        if bvid:
            # 合集/多 P 视频：同一 BV 下不同分 P 的 ?p=N 必须区分，否则字幕会串
            part = re.search(r"[?&]p=(\d+)", url)
            video_key = f"bilibili:{bvid}:p{part.group(1)}" if part else f"bilibili:{bvid}"
        else:
            video_key = url.strip()
        digest = hashlib.sha256(video_key.encode("utf-8")).hexdigest()
        return self.CACHE_DIR / f"{digest}.json"

    def _load_cache(self, url: str) -> Optional[dict]:
        path = self._cache_path(url)
        try:
            with path.open("r", encoding="utf-8") as f:
                payload = json.load(f)
            if payload.get("version") != self.CACHE_VERSION:
                return None
            cached_at = float(payload.get("cached_at") or 0)
            if (
                self.cache_ttl_seconds
                and time.time() - cached_at > self.cache_ttl_seconds
            ):
                path.unlink(missing_ok=True)
                return None
            result = payload.get("result")
            if not isinstance(result, dict) or not isinstance(result.get("segments"), list):
                return None
            cached = dict(result)
            cached["cache_hit"] = True
            return cached
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return None

    def _save_cache(self, url: str, result: dict) -> dict:
        path = self._cache_path(url)
        temp_path = path.with_suffix(f".{threading.get_ident()}.tmp")
        clean_result = dict(result)
        clean_result.pop("cache_hit", None)
        try:
            with temp_path.open("w", encoding="utf-8") as f:
                json.dump({
                    "version": self.CACHE_VERSION,
                    "cached_at": time.time(),
                    "url": url,
                    "result": clean_result,
                }, f, ensure_ascii=False)
            temp_path.replace(path)
        except OSError:
            temp_path.unlink(missing_ok=True)
        clean_result["cache_hit"] = False
        return clean_result

    def extract(self, url: str, force: bool = False) -> dict:
        """
        提取视频字幕，返回:
        {
            "has_subtitle": bool,
            "language": str,
            "subtitle_type": "manual" | "auto" | "none",
            "segments": [{"start": float, "end": float, "text": str}, ...],
            "full_text": str
        }
        """
        if is_local_media_url(url):
            return {
                "has_subtitle": False,
                "language": "",
                "subtitle_type": "none",
                "segments": [],
                "full_text": "",
                "cache_hit": False,
            }

        cached = None if force else self._load_cache(url)
        if cached is not None:
            return cached

        if _is_bilibili_url(url):
            result = self._extract_bilibili(url)
            if result["has_subtitle"]:
                return self._save_cache(url, result)

        info = self._get_video_info(url)

        manual_subs = info.get("subtitles") or {}
        auto_subs = info.get("automatic_captions") or {}

        manual_subs = {k: v for k, v in manual_subs.items() if k != "danmaku"}

        lang, sub_url, sub_type = self._pick_best_subtitle(manual_subs, auto_subs)
        if not sub_url:
            return self._save_cache(url, {
                "has_subtitle": False,
                "language": "",
                "subtitle_type": "none",
                "segments": [],
                "full_text": "",
            })

        segments = self._download_and_parse(url, lang, sub_type)

        full_text = " ".join(seg["text"] for seg in segments)

        return self._save_cache(url, {
            "has_subtitle": True,
            "language": lang,
            "subtitle_type": sub_type,
            "segments": segments,
            "full_text": full_text,
        })

    def _extract_bilibili(self, url: str) -> dict:
        """B 站专用字幕提取（通过 player/v2 API 获取 CC 字幕和 AI 字幕）"""
        empty = {
            "has_subtitle": False, "language": "", "subtitle_type": "none",
            "segments": [], "full_text": "",
        }
        try:
            bvid = self._parse_bvid(url)
            if not bvid:
                return empty

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": f"https://www.bilibili.com/video/{bvid}",
            }
            cookie = cookie_header()
            if cookie:
                headers["Cookie"] = cookie

            view_resp = httpx.get(
                f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}",
                headers=headers, timeout=15,
            )
            view_data = view_resp.json().get("data", {})
            aid = view_data.get("aid")
            # 多 P 合集：根据 ?p=N 选对应分 P 的 cid，否则所有分 P 都会取到第 1 P 的字幕
            pages = view_data.get("pages") or []
            part = re.search(r"[?&]p=(\d+)", url)
            page_index = (int(part.group(1)) - 1) if part else 0
            if pages and 0 <= page_index < len(pages):
                cid = pages[page_index].get("cid")
            else:
                cid = view_data.get("cid")
            if not cid or not aid:
                return empty

            player_resp = httpx.get(
                f"https://api.bilibili.com/x/player/v2?aid={aid}&cid={cid}",
                headers=headers, timeout=15,
            )
            player_data = player_resp.json().get("data", {})
            subtitle_list = player_data.get("subtitle", {}).get("subtitles", [])

            if not subtitle_list:
                return empty

            best = subtitle_list[0]
            for s in subtitle_list:
                lang = s.get("lan", "")
                if lang == "zh" or lang == "zh-Hans":
                    best = s
                    break

            sub_type = "auto" if best.get("lan", "").startswith("ai-") else "manual"

            sub_url = best.get("subtitle_url", "")
            if sub_url.startswith("//"):
                sub_url = "https:" + sub_url
            if sub_url.startswith("http://"):
                sub_url = "https://" + sub_url[7:]

            if not sub_url:
                return empty

            sub_resp = httpx.get(sub_url, headers=headers, timeout=15)
            sub_json = sub_resp.json()
            body = sub_json.get("body", [])

            segments = []
            for item in body:
                content = item.get("content", "").strip()
                if not content:
                    continue
                segments.append({
                    "start": round(item.get("from", 0), 2),
                    "end": round(item.get("to", 0), 2),
                    "text": content,
                })

            full_text = " ".join(seg["text"] for seg in segments)
            return {
                "has_subtitle": True,
                "language": best.get("lan", "zh"),
                "subtitle_type": sub_type,
                "segments": segments,
                "full_text": full_text,
            }
        except Exception:
            return empty

    @staticmethod
    def _parse_bvid(url: str) -> Optional[str]:
        m = re.search(r"(BV[a-zA-Z0-9]+)", url)
        return m.group(1) if m else None

    def _get_video_info(self, url: str) -> dict:
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "extract_flat": False,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "skip_download": True,
            **common_ydl_opts(),
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        if not info:
            raise ValueError("无法解析该视频链接")
        return info

    def _pick_best_subtitle(
        self, manual_subs: dict, auto_subs: dict
    ) -> tuple[str, Optional[str], str]:
        """按优先级选择最佳字幕，返回 (lang, url, type)"""
        for lang in self.PREFERRED_LANGS:
            if lang in manual_subs:
                formats = manual_subs[lang]
                url = self._get_format_url(formats)
                if url:
                    return lang, url, "manual"

        for lang in self.PREFERRED_LANGS:
            if lang in auto_subs:
                formats = auto_subs[lang]
                url = self._get_format_url(formats)
                if url:
                    return lang, url, "auto"

        if manual_subs:
            first_lang = next(iter(manual_subs))
            url = self._get_format_url(manual_subs[first_lang])
            if url:
                return first_lang, url, "manual"

        if auto_subs:
            first_lang = next(iter(auto_subs))
            url = self._get_format_url(auto_subs[first_lang])
            if url:
                return first_lang, url, "auto"

        return "", None, "none"

    @staticmethod
    def _get_format_url(formats: list) -> Optional[str]:
        preferred = ["json3", "srv3", "vtt", "ttml"]
        for pref in preferred:
            for fmt in formats:
                if fmt.get("ext") == pref:
                    return fmt.get("url")
        return formats[0].get("url") if formats else None

    def _download_and_parse(self, url: str, lang: str, sub_type: str) -> list[dict]:
        """通过 yt-dlp 下载字幕文件并解析为分段列表"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
                "skip_download": True,
                "writesubtitles": sub_type == "manual",
                "writeautomaticsub": sub_type == "auto",
                "subtitleslangs": [lang],
                "subtitlesformat": "vtt",
                "outtmpl": os.path.join(tmp_dir, "subtitle"),
                **common_ydl_opts(),
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            vtt_files = [
                f for f in os.listdir(tmp_dir) if f.endswith(".vtt")
            ]
            if not vtt_files:
                return []

            vtt_path = os.path.join(tmp_dir, vtt_files[0])
            return self._parse_vtt(vtt_path)

    @staticmethod
    def _parse_vtt(filepath: str) -> list[dict]:
        """解析 VTT 字幕文件为结构化分段"""
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        segments = []
        blocks = re.split(r"\n\n+", content)
        time_pattern = re.compile(
            r"(\d{2}:\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}\.\d{3})"
        )

        seen_texts = set()
        for block in blocks:
            lines = block.strip().split("\n")
            time_match = None
            text_lines = []
            for line in lines:
                m = time_pattern.search(line)
                if m:
                    time_match = m
                elif time_match and line.strip() and not line.strip().isdigit():
                    clean = re.sub(r"<[^>]+>", "", line.strip())
                    if clean:
                        text_lines.append(clean)

            if time_match and text_lines:
                text = " ".join(text_lines)
                if text in seen_texts:
                    continue
                seen_texts.add(text)

                start = _time_to_seconds(time_match.group(1))
                end = _time_to_seconds(time_match.group(2))
                segments.append({
                    "start": round(start, 2),
                    "end": round(end, 2),
                    "text": text,
                })

        return segments


class AudioTranscriber:
    """无平台字幕时，下载音频并使用 faster-whisper 生成带时间戳的文本。"""

    CACHE_DIR = Path(__file__).resolve().parent / "data" / "transcripts"
    MODEL_DIR = Path(__file__).resolve().parent / "data" / "whisper-models"
    _model = None
    _model_lock = threading.Lock()

    def __init__(self):
        self.model_name = os.getenv("WHISPER_MODEL", "small").strip() or "small"
        self.device = os.getenv("WHISPER_DEVICE", "cpu").strip() or "cpu"
        self.compute_type = os.getenv("WHISPER_COMPUTE_TYPE", "int8").strip() or "int8"
        self.language = os.getenv("WHISPER_LANGUAGE", "").strip() or None
        self.beam_size = max(1, int(os.getenv("WHISPER_BEAM_SIZE", "5")))
        self.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self.MODEL_DIR.mkdir(parents=True, exist_ok=True)

    def _cache_key(self, url: str) -> str:
        bvid = SubtitleExtractor._parse_bvid(url)
        if bvid:
            # 合集/多 P 视频：不同分 P 的 ?p=N 必须区分，否则转写结果会串
            part = re.search(r"[?&]p=(\d+)", url)
            video_key = f"bilibili:{bvid}:p{part.group(1)}" if part else f"bilibili:{bvid}"
        else:
            video_key = url.strip()
        value = f"v1:{self.model_name}:{self.language or 'auto'}:{video_key}"
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def _cache_path(self, url: str) -> Path:
        return self.CACHE_DIR / f"{self._cache_key(url)}.json"

    def _load_cache(self, url: str) -> Optional[dict]:
        path = self._cache_path(url)
        try:
            with path.open("r", encoding="utf-8") as f:
                cached = json.load(f)
            if cached.get("has_subtitle") and cached.get("full_text"):
                cached["cache_hit"] = True
                return cached
        except (OSError, json.JSONDecodeError):
            pass
        return None

    def _save_cache(self, url: str, result: dict) -> None:
        path = self._cache_path(url)
        temp_path = path.with_suffix(".tmp")
        try:
            with temp_path.open("w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False)
            temp_path.replace(path)
        except OSError:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass

    def _cached_model_path(self) -> Optional[Path]:
        configured_path = Path(self.model_name)
        if configured_path.is_dir():
            candidates = [configured_path]
        else:
            repo_id = (
                self.model_name
                if "/" in self.model_name
                else f"Systran/faster-whisper-{self.model_name}"
            )
            snapshots_dir = (
                self.MODEL_DIR
                / f"models--{repo_id.replace('/', '--')}"
                / "snapshots"
            )
            candidates = list(snapshots_dir.glob("*")) if snapshots_dir.exists() else []

        required_files = ("config.json", "model.bin", "tokenizer.json")
        complete = [
            path
            for path in candidates
            if path.is_dir()
            and all((path / filename).is_file() for filename in required_files)
            and (path / "model.bin").stat().st_size > 1024 * 1024
        ]
        if not complete:
            return None
        return max(complete, key=lambda path: (path / "model.bin").stat().st_mtime)

    def _get_model(
        self,
        progress_callback: Optional[Callable[[dict], None]] = None,
    ):
        if AudioTranscriber._model is None:
            with AudioTranscriber._model_lock:
                if AudioTranscriber._model is None:
                    try:
                        from faster_whisper import WhisperModel
                    except ImportError as exc:
                        raise RuntimeError(
                            "未安装 faster-whisper，请在 backend 目录执行: pip install -r requirements.txt"
                        ) from exc

                    os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "120")
                    os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "30")
                    mirror = os.getenv("WHISPER_HF_ENDPOINT", "").strip()
                    if mirror:
                        os.environ["HF_ENDPOINT"] = mirror.rstrip("/")

                    cached_path = self._cached_model_path()
                    model_source = str(cached_path) if cached_path else self.model_name
                    attempts = 1 if cached_path else 3
                    for attempt in range(1, attempts + 1):
                        try:
                            AudioTranscriber._model = WhisperModel(
                                model_source,
                                device=self.device,
                                compute_type=self.compute_type,
                                download_root=str(self.MODEL_DIR),
                                local_files_only=bool(cached_path),
                            )
                            break
                        except Exception as exc:
                            if attempt >= attempts:
                                raise RuntimeError(
                                    f"语音识别模型加载失败: {exc}"
                                ) from exc
                            self._emit_progress(
                                progress_callback,
                                "model_loading",
                                f"模型下载连接中断，正在重试（{attempt}/{attempts - 1}）...",
                                40,
                            )
                            time.sleep(attempt * 2)
        return AudioTranscriber._model

    @staticmethod
    def _emit_progress(
        callback: Optional[Callable[[dict], None]],
        stage: str,
        message: str,
        percent: int,
    ) -> None:
        if callback:
            callback({
                "stage": stage,
                "message": message,
                "percent": max(0, min(100, int(percent))),
            })

    def _download_audio(
        self,
        url: str,
        temp_dir: str,
        progress_callback: Optional[Callable[[dict], None]] = None,
    ) -> str:
        local_path = resolve_local_path(url)
        if local_path:
            self._emit_progress(
                progress_callback, "audio_download", "本地视频读取完成，正在准备语音识别...", 35
            )
            return local_path

        last_download_percent = -1

        def download_progress(status: dict) -> None:
            nonlocal last_download_percent
            if status.get("status") == "finished":
                self._emit_progress(
                    progress_callback, "audio_download", "音频下载完成，正在准备语音识别...", 35
                )
                return
            if status.get("status") != "downloading":
                return

            downloaded = status.get("downloaded_bytes") or 0
            total = status.get("total_bytes") or status.get("total_bytes_estimate") or 0
            if total:
                download_percent = min(100, int(downloaded * 100 / total))
                if download_percent < 100 and download_percent - last_download_percent < 2:
                    return
                last_download_percent = download_percent
                overall_percent = 5 + round(download_percent * 0.30)
                message = f"正在下载视频音频... {download_percent}%"
            else:
                overall_percent = 10
                message = "正在下载视频音频..."

            self._emit_progress(
                progress_callback, "audio_download", message, overall_percent
            )

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": os.path.join(temp_dir, "audio.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "nopart": True,
            "retries": 10,
            "fragment_retries": 10,
            "extractor_retries": 5,
            "socket_timeout": 30,
            "progress_hooks": [download_progress],
            **common_ydl_opts(),
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

        if not info:
            raise ValueError("无法下载视频音频")

        prepared = ydl.prepare_filename(info)
        if os.path.exists(prepared):
            return prepared

        candidates = [
            os.path.join(temp_dir, name)
            for name in os.listdir(temp_dir)
            if name.startswith("audio.")
        ]
        if candidates:
            return candidates[0]
        raise ValueError("音频下载完成，但没有找到音频文件")

    def transcribe_url(
        self,
        url: str,
        progress_callback: Optional[Callable[[dict], None]] = None,
        force: bool = False,
    ) -> dict:
        cached = None if force else self._load_cache(url)
        if cached:
            self._emit_progress(
                progress_callback, "cache", "已找到语音转写缓存", 100
            )
            return cached

        temp_dir = tempfile.mkdtemp(prefix="video-transcribe-")
        try:
            self._emit_progress(
                progress_callback, "audio_download", "正在获取视频音频...", 5
            )
            audio_path = self._download_audio(url, temp_dir, progress_callback)

            model_cached = self._cached_model_path() is not None
            model_message = (
                "正在加载语音识别模型..."
                if model_cached
                else "首次使用，正在下载语音识别模型..."
            )
            self._emit_progress(
                progress_callback, "model_loading", model_message, 40
            )
            model = self._get_model(progress_callback)
            self._emit_progress(
                progress_callback, "transcribing", "正在识别音频内容...", 45
            )
            segments, info = model.transcribe(
                audio_path,
                language=self.language,
                beam_size=self.beam_size,
                vad_filter=True,
            )

            parsed_segments = []
            duration = float(getattr(info, "duration", 0) or 0)
            last_transcribe_percent = 44
            for segment in segments:
                text = (segment.text or "").strip()
                if not text:
                    continue
                parsed_segments.append({
                    "start": round(float(segment.start), 2),
                    "end": round(float(segment.end), 2),
                    "text": text,
                })
                if duration > 0:
                    overall_percent = 45 + round(min(float(segment.end) / duration, 1) * 50)
                    if overall_percent - last_transcribe_percent >= 2:
                        last_transcribe_percent = overall_percent
                        self._emit_progress(
                            progress_callback,
                            "transcribing",
                            f"正在识别音频内容... {round(min(float(segment.end) / duration, 1) * 100)}%",
                            overall_percent,
                        )

            full_text = " ".join(item["text"] for item in parsed_segments)
            if not full_text:
                raise ValueError("语音转写没有识别出有效内容")

            result = {
                "has_subtitle": True,
                "language": getattr(info, "language", "") or "",
                "subtitle_type": "transcription",
                "segments": parsed_segments,
                "full_text": full_text,
            }
            self._save_cache(url, result)
            self._emit_progress(
                progress_callback, "transcribing", "语音识别完成", 100
            )
            return result
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


class LLMProvider(ABC):
    """统一不同大模型供应商的文本生成接口"""

    name: str
    model: str

    @abstractmethod
    def stream_chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float,
        max_tokens: int,
    ) -> Iterator[str]:
        """流式生成文本"""

    @abstractmethod
    def complete_chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """一次性生成文本"""


class OpenAICompatibleProvider(LLMProvider):
    """兼容 OpenAI Chat Completions 的供应商（官方 API / 中转站）"""

    def __init__(
        self,
        *,
        name: str,
        api_key: str,
        model: str,
        base_url: str = "",
    ):
        self.name = name
        self.model = model
        self.base_url = (base_url or "").rstrip("/")
        client_options = {
            "api_key": api_key,
            "timeout": httpx.Timeout(120.0, connect=10.0),
            "max_retries": 1,
        }
        if self.base_url:
            self.client = OpenAI(base_url=self.base_url, **client_options)
        else:
            self.client = OpenAI(**client_options)

    @staticmethod
    def _first_choice(response_obj):
        choices = getattr(response_obj, "choices", None)
        if not choices:
            return None
        return choices[0]

    @staticmethod
    def _message_text(message) -> str:
        if message is None:
            return ""
        content = getattr(message, "content", None)
        if isinstance(content, str) and content.strip():
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                    continue
                if isinstance(item, dict):
                    text = item.get("text") or item.get("content")
                    if text:
                        parts.append(str(text))
                    continue
                text = getattr(item, "text", None)
                if text:
                    parts.append(str(text))
            joined = "".join(parts).strip()
            if joined:
                return joined

        # 部分中转站把正文放在 reasoning/thinking 字段
        for attr in ("reasoning_content", "reasoning", "refusal"):
            value = getattr(message, attr, None)
            if isinstance(value, str) and value.strip():
                return value
        return content or ""

    def _raise_if_error_payload(self, response_obj) -> None:
        error = getattr(response_obj, "error", None)
        if error:
            raise RuntimeError(f"{self.name} API 错误: {error}")
        if isinstance(response_obj, str):
            preview = response_obj[:200].replace("\n", " ")
            raise RuntimeError(
                f"{self.name} 返回了非 JSON 内容（常见原因：Base URL 未带 /v1）。"
                f" 当前 base_url={self.base_url or '(默认)'}，响应预览: {preview}"
            )

    def stream_chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float,
        max_tokens: int,
    ) -> Iterator[str]:
        started = time.perf_counter()
        input_tokens = sum(len(str(item.get("content") or "")) for item in messages) // 4
        output_parts = []
        status = "success"
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=True,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            for chunk in response:
                self._raise_if_error_payload(chunk)
                choice = self._first_choice(chunk)
                if not choice:
                    continue
                delta = getattr(choice, "delta", None)
                if delta is None:
                    continue
                content = getattr(delta, "content", None)
                if isinstance(content, str) and content:
                    output_parts.append(content)
                    yield content
                    continue
                # Claude 兼容中转偶发把增量放在 reasoning_content
                reasoning = getattr(delta, "reasoning_content", None)
                if isinstance(reasoning, str) and reasoning:
                    output_parts.append(reasoning)
                    yield reasoning
        except Exception:
            status = "failed"
            raise
        finally:
            try:
                from learning_efficiency import record_model_usage
                record_model_usage(
                    None, "stream_chat", self.model, input_tokens,
                    len("".join(output_parts)) // 4,
                    round((time.perf_counter() - started) * 1000), status,
                )
            except Exception:
                pass

    def complete_chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float,
        max_tokens: int,
    ) -> str:
        started = time.perf_counter()
        input_tokens = sum(len(str(item.get("content") or "")) for item in messages) // 4
        text = ""
        status = "success"
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=False,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            self._raise_if_error_payload(response)
            choice = self._first_choice(response)
            if not choice:
                raise RuntimeError(
                    f"{self.name} API 返回空 choices。"
                    f" 请确认 Base URL 类似 https://your-relay.com/v1，模型名正确。"
                )
            message = getattr(choice, "message", None)
            text = self._message_text(message)
            if text is None or text == "":
                raise RuntimeError(
                    f"{self.name} API 未返回可用文本。"
                    f" finish_reason={getattr(choice, 'finish_reason', None)}"
                )
            return text
        except Exception:
            status = "failed"
            raise
        finally:
            try:
                from learning_efficiency import record_model_usage
                record_model_usage(
                    None, "complete_chat", self.model, input_tokens, len(text) // 4,
                    round((time.perf_counter() - started) * 1000), status,
                )
            except Exception:
                pass


def _env_first(*names: str, default: str = "") -> str:
    """优先读 app_settings（页面保存），再读环境变量。"""
    for name in names:
        try:
            from database import get_app_setting

            saved_value = (get_app_setting(name) or "").strip()
            if saved_value:
                return saved_value
        except Exception:
            pass

        value = os.getenv(name, "").strip()
        if value:
            return value
    return default


def sanitize_mindmap_markdown(text: str) -> str:
    """清洗模型返回的思维导图 Markdown，避免代码块导致 markmap 无法画图。"""
    cleaned = (text or "").strip()
    if not cleaned:
        return ""

    # 去掉整段 ```markdown ... ``` 包裹
    fenced = re.match(
        r"^```(?:markdown|md|markmap)?\s*\n([\s\S]*?)\n?```\s*$",
        cleaned,
        flags=re.IGNORECASE,
    )
    if fenced:
        cleaned = fenced.group(1).strip()
    else:
        # 去掉开头/结尾残留的围栏
        cleaned = re.sub(r"^```(?:markdown|md|markmap)?\s*\n?", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\n?```\s*$", "", cleaned).strip()
        # 若仍混有围栏，提取第一个标题层级块
        if "```" in cleaned:
            parts = re.split(r"```(?:markdown|md|markmap)?", cleaned, flags=re.IGNORECASE)
            candidates = [part.strip("` \n") for part in parts if "#" in part]
            if candidates:
                cleaned = max(candidates, key=len).strip()

    # 从第一个标题行开始，丢掉模型的说明性前言
    lines = cleaned.splitlines()
    start = 0
    for idx, line in enumerate(lines):
        if re.match(r"^#{1,6}\s+\S", line.strip()):
            start = idx
            break
    cleaned = "\n".join(lines[start:]).strip()
    return cleaned


def _build_llm_provider(operation: str = "default") -> LLMProvider:
    """Resolve a model per task, falling back to the active profile."""
    route = re.sub(r"[^A-Z0-9]+", "_", operation.upper()).strip("_")
    routed_key = os.getenv(f"LLM_{route}_API_KEY", "").strip() if route != "DEFAULT" else ""
    if routed_key:
        routed_base = os.getenv(f"LLM_{route}_BASE_URL", os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"))
        routed_model = os.getenv(f"LLM_{route}_MODEL", os.getenv("LLM_MODEL", "gpt-4o-mini"))
        return OpenAICompatibleProvider(
            name=f"route:{operation}", api_key=routed_key,
            base_url=routed_base.rstrip("/"), model=routed_model,
        )
    try:
        from api_model_config import get_resolved_model_config, normalize_llm_base_url

        cfg = get_resolved_model_config()
        api_key = (cfg.get("api_key") or "").strip()
        if api_key:
            base_url = normalize_llm_base_url(cfg.get("base_url") or "https://api.openai.com/v1")
            model = (cfg.get("model") or "gpt-4o-mini").strip() or "gpt-4o-mini"
            return OpenAICompatibleProvider(
                name="relay",
                api_key=api_key,
                base_url=base_url,
                model=model,
            )
    except Exception:
        # 数据库未初始化等情况下，继续走环境变量回退
        pass

    api_key = _env_first(
        "LLM_API_KEY",
        "OPENAI_API_KEY",
        "DEEPSEEK_API_KEY",
        "MX52_API_KEY",
        "ANTHROPIC_API_KEY",
        "CLAUDE_API_KEY",
        "CODEX_API_KEY",
        "FIFTY_TWO_MX_API_KEY",
    )
    if not api_key:
        raise ValueError(
            "未配置模型 API Key。请登录后在「模型配置」中添加配置，或设置 LLM_API_KEY 等环境变量"
        )

    base_url = _env_first(
        "LLM_BASE_URL",
        "OPENAI_BASE_URL",
        "DEEPSEEK_BASE_URL",
        "MX52_BASE_URL",
        "ANTHROPIC_BASE_URL",
        "CODEX_BASE_URL",
        default="https://api.openai.com/v1",
    )
    try:
        from api_model_config import normalize_llm_base_url

        base_url = normalize_llm_base_url(base_url)
    except Exception:
        base_url = (base_url or "").rstrip("/")
        if base_url and not re.search(r"/v\d+$", base_url):
            base_url = f"{base_url}/v1"

    model = _env_first(
        "LLM_MODEL",
        "OPENAI_MODEL",
        "DEEPSEEK_MODEL",
        "MX52_MODEL",
        "CLAUDE_MODEL",
        "CODEX_MODEL",
        default="gpt-4o-mini",
    )

    return OpenAICompatibleProvider(
        name="relay",
        api_key=api_key,
        base_url=base_url,
        model=model,
    )


class VideoSummarizer:
    """使用配置的大模型供应商生成视频总结、思维导图、问答"""

    def __init__(self, operation: str = "default"):
        self.provider = _build_llm_provider(operation)
        self.model = self.provider.model
        self.provider_name = self.provider.name

    def summarize_stream(self, subtitle_text: str, language: str = "zh"):
        """流式生成包含原视频示例的深度总结，yield 每个 token。"""
        prompt = self._build_summary_prompt(subtitle_text, language)
        messages = [
            {
                "role": "system",
                "content": (
                    "你是一个严谨的视频学习内容分析助手，擅长提取关键信息、讲解案例和可迁移的理解。"
                    "所有示例和细节都必须忠实来自字幕，绝不补造视频中没有的内容。"
                ),
            },
            {"role": "user", "content": prompt},
        ]
        yield from self.provider.stream_chat(
            messages,
            temperature=0.45,
            max_tokens=6144,
        )

    def generate_mindmap(self, subtitle_text: str, language: str = "zh") -> str:
        """生成思维导图 Markdown（非流式，一次性返回）"""
        prompt = self._build_mindmap_prompt(subtitle_text, language)
        messages = [
            {
                "role": "system",
                "content": (
                    "你是一个专业的思维导图生成助手，擅长将内容组织为清晰的层级结构。"
                    "只输出纯 Markdown 标题和列表，禁止使用代码块（```）。"
                ),
            },
            {"role": "user", "content": prompt},
        ]
        raw = self.provider.complete_chat(
            messages,
            temperature=0.5,
            max_tokens=4096,
        )
        return sanitize_mindmap_markdown(raw)

    def chat_stream(self, subtitle_text: str, question: str):
        """基于视频内容的 AI 问答，流式返回"""
        prompt = self._build_chat_prompt(subtitle_text, question)
        messages = [
            {
                "role": "system",
                "content": "你是一个视频内容问答助手。根据提供的视频字幕内容来回答用户的问题。如果问题超出视频内容范围，请诚实告知。",
            },
            {"role": "user", "content": prompt},
        ]
        yield from self.provider.stream_chat(
            messages,
            temperature=0.7,
            max_tokens=2048,
        )

    def diagnose_mistake(self, question: dict, answer) -> dict:
        """分析错误根因，并给出一个可立即执行的补救动作。"""
        prompt = f"""请分析下面这道错题。只输出合法 JSON，不要输出其他文字。

分类只能从以下五项选择：概念未理解、记忆模糊、题意误读、知识混淆、表达不完整。
JSON 格式：{{"category":"分类","diagnosis":"具体错因，60字以内","action":"下一步行动，60字以内"}}

题目：{json.dumps(question, ensure_ascii=False)}
学习者答案：{json.dumps(answer, ensure_ascii=False)}"""
        raw = self.provider.complete_chat(
            [
                {"role": "system", "content": "你是严谨的学习诊断教师，关注错误根因而不是泛泛鼓励。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=512,
        )
        data = _parse_json_object(raw)
        allowed = {"概念未理解", "记忆模糊", "题意误读", "知识混淆", "表达不完整"}
        category = str(data.get("category") or "概念未理解")
        return {
            "category": category if category in allowed else "概念未理解",
            "diagnosis": str(data.get("diagnosis") or "需要重新核对课程证据。").strip()[:160],
            "action": str(data.get("action") or "回看来源片段并完成专项训练。").strip()[:160],
        }

    def organize_notes(self, notes: list[dict]) -> str:
        prompt = f"""请将以下课程时间点笔记整理为简洁的复习提纲。
保留视频标题和时间点，合并重复观点，使用 Markdown 二级标题和项目符号。
不要添加笔记之外的知识。

笔记：{json.dumps(notes, ensure_ascii=False)}"""
        return self.provider.complete_chat(
            [
                {"role": "system", "content": "你是课程笔记编辑，擅长压缩重复内容并保留可追溯来源。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=2048,
        ).strip()

    def generate_quiz(self, subtitle_text: str, language: str = "zh") -> dict:
        """根据视频文本生成包含多种题型的标准化题卷。"""
        truncated = subtitle_text[:15000]
        lang_hint = "中文" if language.startswith("zh") else "与原文相同的语言"
        prompt = f"""请根据下面的视频内容生成一份用于检验学习效果的考试题卷，使用{lang_hint}。

出题要求：
1. 共 16 题、总分 100 分：5 道单选题（每题 4 分）、3 道多选题（每题 6 分）、3 道判断题（每题 4 分）、3 道简答题（每题 10 分）、2 道分析题（每题 10 分）。
2. 题型必须严格包含以上五类；分析题要求结合视频中的多个观点进行推理、比较、因果解释、方案设计或迁移应用。
3. 难度覆盖基础理解、概念辨析、实际应用和综合分析，避免只考无意义细节。
4. 所有答案必须能从视频内容直接推导，不得引入视频之外的知识。
5. 单选和多选均提供 A-D 四个选项；多选至少有两个正确答案。
6. 判断题使用 A=正确、B=错误。
7. 简答题和分析题提供可用于阅卷的参考答案和评分要点。
8. 只输出合法 JSON，不要 Markdown 代码块或其他说明。

JSON 格式：
{{
  "title": "题卷标题",
  "questions": [
    {{
      "id": 1,
      "type": "single|multiple|true_false|short_answer|analysis",
      "question": "题干",
      "options": [{{"key": "A", "text": "选项内容"}}],
      "answer": ["A"],
      "reference_answer": "仅简答题填写",
      "explanation": "答案解析或评分要点",
      "points": 10
    }}
  ]
}}

视频内容：
{truncated}"""
        messages = [
            {
                "role": "system",
                "content": "你是一名严谨的考试命题教师，擅长基于指定材料命制有效、可评分的测试题。",
            },
            {"role": "user", "content": prompt},
        ]
        raw = self.provider.complete_chat(
            messages,
            temperature=0.4,
            max_tokens=8192,
        )
        return self._normalize_quiz(_parse_json_object(raw))

    def generate_quiz_batch(
        self,
        subtitle_text: str,
        language: str,
        spec: dict,
        start_id: int,
        previous_questions: list[dict] | None = None,
    ) -> dict:
        """生成一个题型批次，供 SSE 在每批完成后立即返回。"""
        truncated = subtitle_text[:15000]
        lang_hint = "中文" if language.startswith("zh") else "与原文相同的语言"
        question_type = spec["type"]
        type_label = spec["label"]
        count = spec["count"]
        points = spec["points"]
        previous_stems = [
            str(item.get("question") or "").strip()
            for item in (previous_questions or [])
            if str(item.get("question") or "").strip()
        ]
        avoid_section = ""
        if previous_stems:
            avoid_section = "\n已经生成过以下题目，请勿重复：\n" + "\n".join(
                f"- {stem}" for stem in previous_stems
            )

        format_requirements = {
            "single": "每题提供 A-D 四个选项，answer 只含一个正确选项。",
            "multiple": "每题提供 A-D 四个选项，answer 至少包含两个正确选项。",
            "true_false": "每题使用 A=正确、B=错误两个选项，answer 只含 A 或 B。",
            "short_answer": "不提供选项；提供具体 reference_answer 和可评分的 explanation。",
            "analysis": "不提供选项；题目需综合多个观点，提供具体 reference_answer 和分点评分 explanation。",
        }[question_type]

        prompt = f"""请根据下面的视频内容生成一批{type_label}，使用{lang_hint}。

要求：
1. 必须且只能生成 {count} 道 type={question_type} 的题目，每题 {points} 分。
2. {format_requirements}
3. 所有答案必须能从视频内容直接推导，不得引入材料之外的知识。
4. 题目覆盖理解、辨析和应用，避免无意义细节，并与已生成题目保持差异。
5. 每题必须标注 knowledge_point（简短知识点）、source_video_title（材料中的视频标题）、
   evidence_quote（能直接支持答案的原文短句）和 evidence_time_seconds（对应 [时:分:秒] 的秒数）。
6. 只输出合法 JSON，不要 Markdown 代码块或其他说明。

JSON 格式：
{{
  "title": "视频内容理解测试",
  "questions": [
    {{
      "type": "{question_type}",
      "question": "题干",
      "options": [{{"key": "A", "text": "选项内容"}}],
      "answer": ["A"],
      "reference_answer": "简答题或分析题的参考答案",
      "explanation": "答案解析或评分要点",
      "knowledge_point": "知识点名称",
      "source_video_title": "课程视频标题",
      "evidence_quote": "支持答案的原文",
      "evidence_time_seconds": 0
    }}
  ]
}}
{avoid_section}

视频内容：
{truncated}"""
        raw = self.provider.complete_chat(
            [
                {
                    "role": "system",
                    "content": "你是一名严谨的考试命题教师，只按指定题型和数量输出可评分的 JSON 题目。",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.35,
            max_tokens=spec["max_tokens"],
        )
        data = _parse_json_object(raw)
        candidates = [
            item
            for item in self._normalize_quiz_questions(data)
            if item["type"] == question_type
        ]
        if len(candidates) < count:
            raise ValueError(f"模型生成的{type_label}数量不足（需要 {count} 题，得到 {len(candidates)} 题）")

        questions = candidates[:count]
        for offset, question in enumerate(questions):
            question["id"] = start_id + offset
            question["points"] = points
        return {
            "title": str(data.get("title") or "视频内容理解测试").strip(),
            "questions": questions,
        }

    def grade_quiz(self, quiz: dict, answers: dict) -> dict:
        """客观题确定性判分，简答题和分析题由模型按参考答案给分。"""
        questions = quiz.get("questions") or []
        results = []
        subjective = []

        for question in questions:
            question_id = str(question.get("id"))
            question_type = question.get("type")
            points = int(question.get("points") or 10)
            user_answer = answers.get(question_id, answers.get(question.get("id"), ""))

            if question_type in {"short_answer", "analysis"}:
                if str(user_answer or "").strip():
                    subjective.append({
                        "id": question.get("id"),
                        "question": question.get("question", ""),
                        "user_answer": str(user_answer).strip(),
                        "reference_answer": question.get("reference_answer", ""),
                        "scoring_points": question.get("explanation", ""),
                        "max_points": points,
                    })
                else:
                    results.append({
                        "id": question.get("id"),
                        "awarded_points": 0,
                        "max_points": points,
                        "correct": False,
                        "feedback": "未作答。",
                    })
                continue

            expected = {str(item) for item in question.get("answer") or []}
            if isinstance(user_answer, list):
                actual = {str(item) for item in user_answer}
            elif user_answer:
                actual = {str(user_answer)}
            else:
                actual = set()
            correct = actual == expected
            results.append({
                "id": question.get("id"),
                "awarded_points": points if correct else 0,
                "max_points": points,
                "correct": correct,
                "feedback": "回答正确。" if correct else "回答不正确，请结合解析复习。",
            })

        grading_warning = ""
        if subjective:
            try:
                subjective_results = self._grade_subjective_questions(subjective)
                by_id = {str(item.get("id")): item for item in subjective_results}
                for item in subjective:
                    graded = by_id.get(str(item["id"]), {})
                    awarded = max(0, min(
                        item["max_points"],
                        int(round(float(graded.get("awarded_points", 0)))),
                    ))
                    results.append({
                        "id": item["id"],
                        "awarded_points": awarded,
                        "max_points": item["max_points"],
                        "correct": awarded >= item["max_points"] * 0.6,
                        "feedback": str(graded.get("feedback") or "请参考标准答案复习。"),
                    })
            except Exception as exc:
                grading_warning = f"主观题 AI 阅卷失败：{exc}"
                for item in subjective:
                    results.append({
                        "id": item["id"],
                        "awarded_points": 0,
                        "max_points": item["max_points"],
                        "correct": False,
                        "feedback": "暂未完成 AI 评分，请根据参考答案自行核对。",
                    })

        result_by_id = {str(item.get("id")): item for item in results}
        ordered_results = [
            result_by_id[str(question.get("id"))]
            for question in questions
            if str(question.get("id")) in result_by_id
        ]
        total_score = sum(item["awarded_points"] for item in ordered_results)
        max_score = sum(item["max_points"] for item in ordered_results)
        return {
            "total_score": total_score,
            "max_score": max_score,
            "percentage": round(total_score * 100 / max_score) if max_score else 0,
            "results": ordered_results,
            "grading_warning": grading_warning,
        }

    def _grade_subjective_questions(self, questions: list[dict]) -> list[dict]:
        prompt = f"""请作为考试阅卷老师，严格按照每题参考答案、评分要点和最高分评阅考生的简答题与分析题。
允许意思相近的表达和合理的部分得分。只输出合法 JSON，不要输出其他文字。

JSON 格式：
{{"results":[{{"id":1,"awarded_points":8,"feedback":"具体、简洁的评分意见"}}]}}

待评阅内容：
{json.dumps(questions, ensure_ascii=False)}"""
        raw = self.provider.complete_chat(
            [
                {"role": "system", "content": "你是一名公平、严格且善于给出改进建议的阅卷教师。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=2048,
        )
        data = _parse_json_object(raw)
        return data.get("results") if isinstance(data.get("results"), list) else []

    @staticmethod
    def _normalize_quiz_questions(data: dict) -> list[dict]:
        allowed_types = {"single", "multiple", "true_false", "short_answer", "analysis"}
        type_aliases = {
            "单选": "single", "单选题": "single",
            "多选": "multiple", "多选题": "multiple",
            "判断": "true_false", "判断题": "true_false",
            "简答": "short_answer", "简答题": "short_answer",
            "分析": "analysis", "分析题": "analysis",
        }
        normalized = []
        for index, raw_question in enumerate(data.get("questions") or [], start=1):
            if not isinstance(raw_question, dict):
                continue
            question_type = str(raw_question.get("type", "")).strip()
            question_type = type_aliases.get(question_type, question_type)
            question_text = str(raw_question.get("question", "")).strip()
            if question_type not in allowed_types or not question_text:
                continue

            options = []
            raw_options = raw_question.get("options") or []
            if isinstance(raw_options, dict):
                raw_options = [
                    {"key": key, "text": value}
                    for key, value in raw_options.items()
                ]
            for option in raw_options:
                if isinstance(option, dict) and option.get("key") and option.get("text"):
                    options.append({
                        "key": str(option["key"]).strip().upper(),
                        "text": str(option["text"]).strip(),
                    })
            if question_type == "true_false" and len(options) < 2:
                options = [{"key": "A", "text": "正确"}, {"key": "B", "text": "错误"}]
            if question_type in {"single", "multiple", "true_false"} and not options:
                continue

            answer = raw_question.get("answer")
            if isinstance(answer, bool) and question_type == "true_false":
                answer = ["A" if answer else "B"]
            elif isinstance(answer, str):
                answer = re.split(r"[,，、\s]+", answer)
            elif not isinstance(answer, list):
                answer = []
            answer = [str(item).strip().upper() for item in answer if str(item).strip()]
            if question_type not in {"short_answer", "analysis"} and not answer:
                continue
            if question_type in {"short_answer", "analysis"} and not (
                raw_question.get("reference_answer") or raw_question.get("explanation")
            ):
                continue
            normalized.append({
                "id": index,
                "type": question_type,
                "question": question_text,
                "options": options,
                "answer": answer,
                "reference_answer": str(raw_question.get("reference_answer") or "").strip(),
                "explanation": str(raw_question.get("explanation") or "").strip(),
                "knowledge_point": str(raw_question.get("knowledge_point") or "课程综合").strip()[:80],
                "source_video_title": str(raw_question.get("source_video_title") or "").strip()[:200],
                "evidence_quote": str(raw_question.get("evidence_quote") or "").strip()[:500],
                "evidence_time_seconds": VideoSummarizer._safe_evidence_seconds(
                    raw_question.get("evidence_time_seconds")
                ),
                "points": 10,
            })

        return normalized

    @staticmethod
    def _safe_evidence_seconds(value) -> float:
        try:
            return max(0.0, float(value or 0))
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _normalize_quiz(data: dict) -> dict:
        normalized = VideoSummarizer._normalize_quiz_questions(data)
        type_names = {
            "single": "单选题",
            "multiple": "多选题",
            "true_false": "判断题",
            "short_answer": "简答题",
            "analysis": "分析题",
        }

        required_counts = {
            "single": 5,
            "multiple": 3,
            "true_false": 3,
            "short_answer": 3,
            "analysis": 2,
        }
        point_values = {
            "single": 4,
            "multiple": 6,
            "true_false": 4,
            "short_answer": 10,
            "analysis": 10,
        }
        selected = []
        for question_type, count in required_counts.items():
            candidates = [item for item in normalized if item["type"] == question_type]
            if len(candidates) < count:
                raise ValueError(
                    f"模型生成的{type_names[question_type]}数量不足，请重新生成"
                )
            selected.extend(candidates[:count])

        for index, question in enumerate(selected, start=1):
            question["id"] = index
            question["points"] = point_values[question["type"]]
        return {
            "title": str(data.get("title") or "视频内容理解测试").strip(),
            "questions": selected,
            "max_score": 100,
        }

    @staticmethod
    def _build_summary_prompt(subtitle_text: str, language: str) -> str:
        truncated = subtitle_text[:24000]
        lang_hint = "中文" if language.startswith("zh") else "与原文相同的语言"
        return f"""请对以下带时间点的视频字幕进行深度学习型总结，使用{lang_hint}输出。

总原则：
1. 所有观点、数字、步骤和示例必须来自字幕；不得用常识自行补充或编造视频未讲过的案例。
2. 优先保留讲者用于解释抽象概念的具体例子，包括演示、类比、故事、场景、代码、算例、反例、案例分析和操作过程。
3. 不要只复述例子的表面内容，要说明它对应哪个知识点、讲者借此说明了什么，以及学习者应如何理解或迁移。
4. 输入含有 `[HH:MM:SS]` 时间点时，引用内容要保留最接近的时间点；输入没有明确时间点时写 `[时间点未知]`，绝不能猜测时间。
5. 若字幕确实没有具体例子，在“视频中的讲解示例”下明确写“本视频以概念讲解为主，未提供明确的具体示例”，禁止为了凑数量而虚构。

严格按以下 Markdown 结构输出：
## 视频概述
用 2-3 句话概括视频主题、目标和核心结论。

## 内容大纲
按视频讲解顺序列出主要章节。每项包含：时间点、章节主题和主要内容。

## 核心知识要点
用编号列表提取最重要的知识点、观点、方法或结论。必要时说明前提、步骤和适用场景。

## 视频中的讲解示例
优先提取 2-6 个最有助于理解的真实示例；数量以字幕实际内容为准。每个示例严格使用：
### 示例 N：简短标题 `[HH:MM:SS]`（原字幕无时间点时写 `[时间点未知]`）
- **例子内容**：忠实复述讲者给出的具体情境、输入输出、操作或对比。
- **对应知识点**：这个例子对应的概念或方法。
- **它说明了什么**：解释讲者为何举这个例子，以及例子如何支撑结论。
- **理解与迁移**：说明学习者遇到什么类似问题时可以套用这种思路；不得引入字幕之外的新结论。

## 易混淆点或注意事项
列出视频明确提及或可由上下文直接确定的限制、反例、常见误区和使用条件。没有则写“视频未特别强调”。

## 总结
用 2-3 句话串联核心知识与主要示例，形成便于复习的整体理解。

---
带时间点的视频字幕：
{truncated}"""

    @staticmethod
    def _build_mindmap_prompt(subtitle_text: str, language: str) -> str:
        truncated = subtitle_text[:15000]
        lang_hint = "中文" if language.startswith("zh") else "与原文相同的语言"
        return f"""请将以下视频字幕内容整理为思维导图结构，使用{lang_hint}输出。

要求：
1. 使用 Markdown 标题层级格式（# 一级标题，## 二级标题，### 三级标题）
2. 最外层是视频主题
3. 第二层是主要章节/模块
4. 第三层是各章节的要点
5. 可以有第四层做更细的展开
6. 每个节点的文字要简洁精炼
7. 只输出纯 Markdown 标题和列表，不要前言、后记或其他说明
8. 禁止使用 Markdown 代码块（不要输出 ``` 或 ```markdown）
9. 第一行必须是以 # 开头的主题标题

正确示例：
# 主题
## 分支一
### 要点
- 细节

错误示例（禁止）：
```markdown
# 主题
```

---
视频字幕内容：
{truncated}"""

    @staticmethod
    def _build_chat_prompt(subtitle_text: str, question: str) -> str:
        truncated = subtitle_text[:12000]
        return f"""以下是一个视频的字幕内容，请根据这些内容回答用户的问题。

视频字幕内容：
{truncated}

---
用户问题：{question}

请基于视频内容给出准确、详细的回答。如果视频内容中没有相关信息，请诚实说明。"""


def _time_to_seconds(time_str: str) -> float:
    """将 HH:MM:SS.mmm 转为秒数"""
    parts = time_str.split(":")
    hours = int(parts[0])
    minutes = int(parts[1])
    seconds = float(parts[2])
    return hours * 3600 + minutes * 60 + seconds
