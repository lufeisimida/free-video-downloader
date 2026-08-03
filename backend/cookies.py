"""统一的解析 Cookie 管理。

供 downloader / summarizer 等所有需要访问 B 站等平台的模块共享，
确保 yt-dlp 调用（cookiefile）和 httpx 直接请求（Cookie 头）都带上同一份登录 Cookie，
从而绕过服务器 IP 的网页风控（HTTP 412）。

Cookie 由前端「Cookie 配置」保存到 app_settings，键为 VIDEO_COOKIES。
"""

import logging
import os
import tempfile
from typing import Optional

logger = logging.getLogger("fvd.cookies")

# 前端「Cookie 配置」保存的键
COOKIE_SETTING_KEY = "VIDEO_COOKIES"
# 写到系统临时目录，避免项目目录属主/权限问题导致写入失败
_RUNTIME_COOKIE_FILE = os.path.join(tempfile.gettempdir(), "fvd_runtime_cookies.txt")
_ENV_COOKIE_FILE = os.environ.get("COOKIES_FILE", "").strip() or None

# 缓存已落盘的 cookie 文本，避免每次解析都重写文件
_cache: dict = {"text": "", "path": None}


def get_cookie_text() -> str:
    """读取用户保存的 cookie 原文（Netscape 或 `k=v; k=v` 均可）。"""
    try:
        from database import get_app_setting

        return (get_app_setting(COOKIE_SETTING_KEY) or "").strip()
    except Exception as e:  # noqa: BLE001 - 数据库异常不应阻断解析
        logger.warning("读取数据库 cookie 失败: %r", e)
        return ""


def _looks_like_netscape(text: str) -> bool:
    """判断内容是 Netscape cookies.txt 还是 `k=v; k=v` 原始请求头。"""
    if text.lstrip().startswith("#"):
        return True
    return any("\t" in line for line in text.splitlines())


def _raw_header_to_netscape(header: str, domain: str = ".bilibili.com") -> str:
    """把浏览器复制的 `buvid3=x; SESSDATA=y` 之类字符串转成 Netscape 格式。"""
    lines = ["# Netscape HTTP Cookie File"]
    for part in header.split(";"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        key, value = key.strip(), value.strip()
        if not key:
            continue
        lines.append("\t".join([domain, "TRUE", "/", "FALSE", "0", key, value]))
    return "\n".join(lines) + "\n"


def _materialize_cookie_file(text: str) -> Optional[str]:
    """把 cookie 文本落盘成 yt-dlp 可读的 Netscape 文件，返回路径。"""
    text = (text or "").strip()
    if not text:
        return None
    if _looks_like_netscape(text):
        content = text if text.lstrip().startswith("#") else "# Netscape HTTP Cookie File\n" + text
    else:
        content = _raw_header_to_netscape(text)
    if not content.endswith("\n"):
        content += "\n"
    try:
        with open(_RUNTIME_COOKIE_FILE, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
        return _RUNTIME_COOKIE_FILE
    except OSError as e:
        logger.warning("写入 cookie 文件失败: %r path=%s", e, _RUNTIME_COOKIE_FILE)
        return None


def resolve_cookie_file() -> Optional[str]:
    """返回 yt-dlp 可用的 cookiefile 路径：优先用户保存的，其次 COOKIES_FILE 环境变量。"""
    text = get_cookie_text()
    if text:
        if text == _cache["text"] and _cache["path"] and os.path.exists(_cache["path"]):
            return _cache["path"]
        path = _materialize_cookie_file(text)
        _cache["text"], _cache["path"] = text, path
        return path
    if _ENV_COOKIE_FILE and os.path.exists(_ENV_COOKIE_FILE):
        return _ENV_COOKIE_FILE
    return None


def cookie_header() -> str:
    """把保存的 cookie 转成 `k=v; k=v` 形式，供 httpx 直接请求 B 站 API 时携带。"""
    text = get_cookie_text()
    if not text:
        return ""

    pairs: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("#HttpOnly_"):
            line = line[len("#HttpOnly_"):]
        elif not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 7 and parts[5]:
            pairs.append(f"{parts[5]}={parts[6]}")
    if pairs:
        return "; ".join(pairs)

    # 本身就是 `k=v; k=v` 形式
    if "=" in text and "\t" not in text:
        return " ".join(text.split()).strip()
    return ""


def common_ydl_opts() -> dict:
    """所有 yt-dlp 调用共享的基础项：只挂 cookie，请求头交给 yt-dlp 默认处理。

    注意：不要覆盖 http_headers（自定义 UA/Referer 反而会触发 B 站网页风控 412）。
    """
    opts: dict = {}
    path = resolve_cookie_file()
    if path:
        opts["cookiefile"] = path
    return opts
