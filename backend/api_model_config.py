"""AI 模型配置 API：多配置档案 + Base URL / API Key / 模型名（适配中转站）。"""

import os
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import get_current_user
from database import (
    activate_model_profile,
    create_model_profile,
    delete_model_profile,
    get_active_model_profile,
    get_app_setting,
    get_model_profile,
    list_model_profiles,
    update_model_profile,
)

router = APIRouter(prefix="/api/model-config", tags=["model-config"])

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"

_LEGACY_BASE_URL_KEYS = (
    "LLM_BASE_URL",
    "OPENAI_BASE_URL",
    "DEEPSEEK_BASE_URL",
    "MX52_BASE_URL",
    "ANTHROPIC_BASE_URL",
    "CODEX_BASE_URL",
)
_LEGACY_API_KEY_KEYS = (
    "LLM_API_KEY",
    "OPENAI_API_KEY",
    "DEEPSEEK_API_KEY",
    "MX52_API_KEY",
    "ANTHROPIC_API_KEY",
    "CLAUDE_API_KEY",
    "CODEX_API_KEY",
    "FIFTY_TWO_MX_API_KEY",
)
_LEGACY_MODEL_KEYS = (
    "LLM_MODEL",
    "OPENAI_MODEL",
    "DEEPSEEK_MODEL",
    "MX52_MODEL",
    "CLAUDE_MODEL",
    "CODEX_MODEL",
)


class ModelProfileCreateRequest(BaseModel):
    name: str = ""
    base_url: str
    model: str
    api_key: str = ""
    activate: bool = True


class ModelProfileUpdateRequest(BaseModel):
    name: str | None = None
    base_url: str | None = None
    model: str | None = None
    api_key: str = ""


class ModelTestRequest(BaseModel):
    """可测某个档案，也可测未保存的临时表单值。"""

    profile_id: int | None = None
    base_url: str = ""
    model: str = ""
    api_key: str = ""


def _setting_or_env(key: str, default: str = "") -> str:
    value = (get_app_setting(key) or "").strip()
    if value:
        return value
    return os.getenv(key, default).strip()


def _first_setting_or_env(keys: tuple[str, ...], default: str = "") -> str:
    # 先扫 app_settings，避免 .env 占位符抢在真实中转站配置前面
    for key in keys:
        value = (get_app_setting(key) or "").strip()
        if value:
            return value
    for key in keys:
        value = os.getenv(key, "").strip()
        if value:
            return value
    return default


def _looks_like_placeholder_secret(value: str) -> bool:
    text = (value or "").strip().lower()
    if not text:
        return True
    placeholders = (
        "your-api-key",
        "your-openai",
        "your-deepseek",
        "your-52mx",
        "sk-your",
        "change-me",
        "changeme",
        "xxxxxx",
    )
    return any(token in text for token in placeholders)


def normalize_llm_base_url(base_url: str) -> str:
    """
    规范化中转站 Base URL。
    常见中转站（New API / One API）需要以 /v1 结尾；用户只填域名时自动补全。
    """
    value = (base_url or "").strip().rstrip("/")
    if not value:
        raise HTTPException(status_code=400, detail="Base URL 不能为空")
    if not value.startswith("http://") and not value.startswith("https://"):
        raise HTTPException(status_code=400, detail="Base URL 必须以 http:// 或 https:// 开头")

    # 已是标准 OpenAI 路径
    if re.search(r"/v\d+$", value):
        return value

    # 避免把官方 Anthropic 根域名误补 /v1
    host = value.split("://", 1)[-1].lower()
    if host in {"api.anthropic.com", "api.anthropic.com/"}:
        return value

    return f"{value}/v1"


def _normalize_model(model: str) -> str:
    value = (model or "").strip()
    if not value:
        raise HTTPException(status_code=400, detail="模型名称不能为空")
    return value


def _default_profile_name(model: str, base_url: str) -> str:
    model_name = (model or "").strip() or "未命名模型"
    host = ""
    try:
        host = base_url.split("://", 1)[-1].split("/", 1)[0]
    except Exception:
        host = ""
    return f"{model_name} @ {host}" if host else model_name


def _public_profile(profile: dict | None) -> dict | None:
    if not profile:
        return None
    return {
        "id": profile["id"],
        "name": profile["name"],
        "base_url": profile["base_url"],
        "model": profile["model"],
        "api_key_set": bool(profile.get("api_key_set") or (profile.get("api_key") or "").strip()),
        "is_active": bool(profile.get("is_active")),
        "created_at": profile.get("created_at"),
        "updated_at": profile.get("updated_at"),
    }


def _ensure_legacy_migrated() -> None:
    """把旧的单配置/环境变量迁移为第一个档案（仅在无档案时执行）。"""
    if list_model_profiles():
        return

    base_url = _first_setting_or_env(_LEGACY_BASE_URL_KEYS, "")
    model = _first_setting_or_env(_LEGACY_MODEL_KEYS, "")
    api_key = _first_setting_or_env(_LEGACY_API_KEY_KEYS, "")
    if _looks_like_placeholder_secret(api_key) and not any(
        (get_app_setting(k) or "").strip() for k in _LEGACY_API_KEY_KEYS
    ):
        # 只有 .env 占位符时不自动建档案，避免误迁移
        return
    if not (base_url or model or api_key) or _looks_like_placeholder_secret(api_key):
        # 再尝试直接读常见中转站键
        base_url = (get_app_setting("MX52_BASE_URL") or base_url or "").strip()
        model = (get_app_setting("MX52_MODEL") or model or "").strip()
        api_key = (get_app_setting("MX52_API_KEY") or api_key or "").strip()
    if not (base_url or model or api_key) or _looks_like_placeholder_secret(api_key):
        return

    try:
        base_url = normalize_llm_base_url(base_url or DEFAULT_BASE_URL)
    except HTTPException:
        base_url = DEFAULT_BASE_URL
    model = (model or DEFAULT_MODEL).strip() or DEFAULT_MODEL
    create_model_profile(
        name=_default_profile_name(model, base_url),
        base_url=base_url,
        model=model,
        api_key=api_key,
        activate=True,
    )


def get_resolved_model_config() -> dict:
    """当前生效的模型连接（优先 active profile，其次旧配置/环境变量）。"""
    _ensure_legacy_migrated()
    active = get_active_model_profile()
    if active:
        return {
            "id": active["id"],
            "name": active["name"],
            "base_url": active["base_url"],
            "model": active["model"],
            "api_key": active.get("api_key") or "",
            "api_key_set": bool((active.get("api_key") or "").strip()),
            "default_base_url": DEFAULT_BASE_URL,
            "default_model": DEFAULT_MODEL,
        }

    return {
        "id": None,
        "name": "",
        "base_url": _first_setting_or_env(_LEGACY_BASE_URL_KEYS, DEFAULT_BASE_URL),
        "model": _first_setting_or_env(_LEGACY_MODEL_KEYS, DEFAULT_MODEL),
        "api_key": _first_setting_or_env(_LEGACY_API_KEY_KEYS, ""),
        "api_key_set": bool(_first_setting_or_env(_LEGACY_API_KEY_KEYS, "")),
        "default_base_url": DEFAULT_BASE_URL,
        "default_model": DEFAULT_MODEL,
    }


def _payload() -> dict:
    _ensure_legacy_migrated()
    profiles = [_public_profile(item) for item in list_model_profiles()]
    active = next((item for item in profiles if item and item.get("is_active")), None)
    if not active and profiles:
        active = profiles[0]
    return {
        "active_profile_id": active["id"] if active else None,
        "active_profile": active,
        "profiles": profiles,
        "default_base_url": DEFAULT_BASE_URL,
        "default_model": DEFAULT_MODEL,
    }


@router.get("")
async def get_model_config(user: dict = Depends(get_current_user)):
    return {"success": True, "data": _payload()}


@router.post("/profiles")
async def create_profile(
    req: ModelProfileCreateRequest,
    user: dict = Depends(get_current_user),
):
    base_url = normalize_llm_base_url(req.base_url)
    model = _normalize_model(req.model)
    api_key = (req.api_key or "").strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="请填写 API Key")

    name = (req.name or "").strip() or _default_profile_name(model, base_url)
    # 若当前还没有任何档案，强制激活新建项
    activate = req.activate or not list_model_profiles()
    profile = create_model_profile(
        name=name,
        base_url=base_url,
        model=model,
        api_key=api_key,
        activate=activate,
    )

    if activate:
        from api_summarize import reset_summarizer

        reset_summarizer()

    return {"success": True, "data": {**_payload(), "profile": _public_profile(profile)}}


@router.put("/profiles/{profile_id}")
async def update_profile(
    profile_id: int,
    req: ModelProfileUpdateRequest,
    user: dict = Depends(get_current_user),
):
    existing = get_model_profile(profile_id)
    if not existing:
        raise HTTPException(status_code=404, detail="模型配置不存在")

    base_url = existing["base_url"]
    model = existing["model"]
    if req.base_url is not None:
        base_url = normalize_llm_base_url(req.base_url)
    if req.model is not None:
        model = _normalize_model(req.model)

    name = req.name
    if name is not None:
        name = name.strip() or _default_profile_name(model, base_url)

    api_key = req.api_key.strip() if req.api_key else None
    if not (existing.get("api_key") or "").strip() and not api_key:
        raise HTTPException(status_code=400, detail="请填写 API Key")

    profile = update_model_profile(
        profile_id,
        name=name,
        base_url=base_url if req.base_url is not None else None,
        model=model if req.model is not None else None,
        api_key=api_key,
    )

    if existing.get("is_active"):
        from api_summarize import reset_summarizer

        reset_summarizer()

    return {"success": True, "data": {**_payload(), "profile": _public_profile(profile)}}


@router.post("/profiles/{profile_id}/activate")
async def activate_profile(profile_id: int, user: dict = Depends(get_current_user)):
    profile = activate_model_profile(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="模型配置不存在")

    from api_summarize import reset_summarizer

    reset_summarizer()
    return {"success": True, "data": {**_payload(), "profile": _public_profile(profile)}}


@router.delete("/profiles/{profile_id}")
async def remove_profile(profile_id: int, user: dict = Depends(get_current_user)):
    existing = get_model_profile(profile_id)
    if not existing:
        raise HTTPException(status_code=404, detail="模型配置不存在")

    delete_model_profile(profile_id)

    if existing.get("is_active"):
        from api_summarize import reset_summarizer

        reset_summarizer()

    return {"success": True, "data": _payload()}


@router.post("/test")
async def test_model_config(
    req: ModelTestRequest = ModelTestRequest(),
    user: dict = Depends(get_current_user),
):
    try:
        from summarizer import OpenAICompatibleProvider

        base_url = (req.base_url or "").strip()
        model = (req.model or "").strip()
        api_key = (req.api_key or "").strip()

        if req.profile_id:
            profile = get_model_profile(req.profile_id)
            if not profile:
                raise HTTPException(status_code=404, detail="模型配置不存在")
            base_url = base_url or profile["base_url"]
            model = model or profile["model"]
            api_key = api_key or (profile.get("api_key") or "")
        elif not (base_url and model and api_key):
            saved = get_resolved_model_config()
            base_url = base_url or saved["base_url"]
            model = model or saved["model"]
            api_key = api_key or saved["api_key"]

        base_url = normalize_llm_base_url(base_url)
        model = _normalize_model(model)
        if not api_key:
            raise HTTPException(status_code=400, detail="请先配置 API Key")

        provider = OpenAICompatibleProvider(
            name="relay",
            api_key=api_key,
            base_url=base_url,
            model=model,
        )
        text = provider.complete_chat(
            [{"role": "user", "content": "请只回复 OK，用于测试模型连接。"}],
            temperature=0,
            max_tokens=32,
        )
        return {
            "success": True,
            "data": {
                "base_url": base_url,
                "model": model,
                "response": (text or "").strip(),
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"模型测试失败: {str(e)}")
