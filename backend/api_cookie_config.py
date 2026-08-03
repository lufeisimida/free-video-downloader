"""视频解析 Cookie 配置 API。

持久化到 app_settings（与模型配置同一套存储），登录后可在前端修改。
主要用于绕过 B 站等平台对服务器 IP 的网页风控（HTTP 412）。
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from auth import get_admin_user
from cookies import COOKIE_SETTING_KEY
from database import get_app_setting, set_app_settings
from downloader import VideoDownloader

router = APIRouter(prefix="/api/cookie-config", tags=["cookie-config"])

UPDATED_AT_KEY = "VIDEO_COOKIES_UPDATED_AT"
DEFAULT_TEST_URL = "https://www.bilibili.com/video/BV1HM7C6BEnF"

# 复用一个实例即可：cookie 每次解析时都从 app_settings 动态读取
_downloader = VideoDownloader()


class CookieUpdateRequest(BaseModel):
    cookies: str = ""


class CookieTestRequest(BaseModel):
    url: str = ""


def _cookie_names(text: str) -> str:
    """从 cookie 文本里提取 key 名做脱敏预览，不回显具体值。"""
    names: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 7 and parts[5]:
            names.append(parts[5])
    if not names and "=" in text:
        names = [p.split("=", 1)[0].strip() for p in text.split(";") if "=" in p]
    # 去重保序
    seen: set[str] = set()
    unique = [n for n in names if not (n in seen or seen.add(n))]
    return ", ".join(unique[:15])


def _payload() -> dict:
    text = (get_app_setting(COOKIE_SETTING_KEY) or "").strip()
    return {
        "cookie_set": bool(text),
        "cookie_names": _cookie_names(text),
        "length": len(text),
        "updated_at": get_app_setting(UPDATED_AT_KEY) or "",
        "test_url": DEFAULT_TEST_URL,
    }


@router.get("")
async def get_cookie_config(user: dict = Depends(get_admin_user)):
    return {"success": True, "data": _payload()}


@router.put("")
async def update_cookie_config(
    req: CookieUpdateRequest,
    user: dict = Depends(get_admin_user),
):
    cookies = (req.cookies or "").strip()
    set_app_settings({
        COOKIE_SETTING_KEY: cookies,
        UPDATED_AT_KEY: datetime.now(timezone.utc).isoformat(),
    })
    return {"success": True, "data": _payload()}


@router.delete("")
async def clear_cookie_config(user: dict = Depends(get_admin_user)):
    set_app_settings({
        COOKIE_SETTING_KEY: "",
        UPDATED_AT_KEY: datetime.now(timezone.utc).isoformat(),
    })
    return {"success": True, "data": _payload()}


@router.post("/test")
async def test_cookie_config(
    req: CookieTestRequest = CookieTestRequest(),
    user: dict = Depends(get_admin_user),
):
    """用当前已保存的 cookie 实际解析一条链接，验证是否能绕过风控。"""
    if not (get_app_setting(COOKIE_SETTING_KEY) or "").strip():
        raise HTTPException(status_code=400, detail="请先保存 Cookie 再测试")

    url = (req.url or "").strip() or DEFAULT_TEST_URL
    try:
        info = await run_in_threadpool(_downloader.parse_video, url)
    except Exception as e:
        message = str(e)
        if "412" in message:
            message = "仍被平台风控拦截（412），Cookie 可能无效或已过期，请重新导出登录后的 Cookie"
        raise HTTPException(status_code=400, detail=f"测试失败: {message}")

    return {
        "success": True,
        "data": {
            "url": url,
            "title": info.get("title", ""),
            "platform": info.get("platform", ""),
        },
    }
