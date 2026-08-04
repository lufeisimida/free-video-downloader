"""AI 视频总结相关 API 路由（独立模块，通过 include_router 挂载）"""

import asyncio
import json
from collections.abc import AsyncIterable

from fastapi import APIRouter, Depends, HTTPException
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel, Field

from auth import get_current_user
from content_store import content_store, owner_key
from database import check_and_increment_summary, FREE_DAILY_SUMMARY_LIMIT
from settings import is_summary_paywall_disabled, is_superuser_email

router = APIRouter(prefix="/api", tags=["AI 总结"])

SUMMARY_FORMAT_VERSION = 2


class SummarizeRequest(BaseModel):
    url: str
    language: str = "zh"
    title: str = ""
    force: bool = False
    # 指定要重新生成的部分：summary / mindmap；为空则按缓存策略
    parts: list[str] | None = None


class ChatRequest(BaseModel):
    url: str
    question: str
    subtitle_text: str = ""


class ClearChatRequest(BaseModel):
    url: str


class QuizGenerateRequest(BaseModel):
    url: str
    subtitle_text: str = ""
    language: str = "zh"
    force: bool = False


class QuizGradeRequest(BaseModel):
    quiz: dict
    answers: dict


class QuizStateRequest(BaseModel):
    url: str
    state: dict = Field(default_factory=dict)


def _check_summary_permission(user: dict | None):
    """
    检查 AI 总结权限。
    未登录用户：不允许使用。
    免费用户：每日限制次数。
    VIP 用户：无限制。
    返回 (allowed, remaining, message)
    """
    if is_summary_paywall_disabled():
        return True, -1, None

    if not user:
        return False, 0, "请先登录后使用 AI 总结功能"

    if is_superuser_email(user.get("email")):
        return True, -1, None

    allowed, remaining = check_and_increment_summary(user["id"])
    if not allowed:
        return False, 0, f"今日免费 AI 总结次数已用完（每日 {FREE_DAILY_SUMMARY_LIMIT} 次），开通 VIP 可无限使用"

    return True, remaining, None


def _get_summarizer(operation: str = "default"):
    """延迟初始化按任务路由的 VideoSummarizer。"""
    from summarizer import VideoSummarizer
    instances = getattr(_get_summarizer, "_instances", {})
    if operation not in instances:
        try:
            instances[operation] = VideoSummarizer(operation)
        except ValueError as e:
            raise HTTPException(status_code=500, detail=str(e))
        _get_summarizer._instances = instances
    return instances[operation]


def reset_summarizer():
    """清理已缓存的大模型客户端，下一次请求会按最新配置重新创建。"""
    if hasattr(_get_summarizer, "_instances"):
        delattr(_get_summarizer, "_instances")


def _get_extractor():
    """延迟初始化 SubtitleExtractor"""
    from summarizer import SubtitleExtractor
    if not hasattr(_get_extractor, "_instance"):
        _get_extractor._instance = SubtitleExtractor()
    return _get_extractor._instance


def _get_transcriber():
    """延迟初始化 AudioTranscriber，只有无平台字幕时才加载 faster-whisper。"""
    from summarizer import AudioTranscriber
    if not hasattr(_get_transcriber, "_instance"):
        _get_transcriber._instance = AudioTranscriber()
    return _get_transcriber._instance


async def _transcribe_with_progress(url: str, force: bool = False):
    """在线程中执行转写，并把线程回调桥接为异步进度事件。"""
    loop = asyncio.get_running_loop()
    progress_queue: asyncio.Queue[dict] = asyncio.Queue()
    transcriber = _get_transcriber()

    def on_progress(data: dict) -> None:
        loop.call_soon_threadsafe(progress_queue.put_nowait, data)

    future = loop.run_in_executor(
        None, transcriber.transcribe_url, url, on_progress, force
    )

    while not future.done() or not progress_queue.empty():
        try:
            progress = await asyncio.wait_for(progress_queue.get(), timeout=0.25)
            yield "progress", progress
        except asyncio.TimeoutError:
            continue

    yield "result", await future


def _has_usable_subtitle(data: object) -> bool:
    return (
        isinstance(data, dict)
        and bool(data.get("has_subtitle"))
        and bool(str(data.get("full_text") or "").strip())
    )


def _format_summary_timestamp(seconds: object) -> str:
    try:
        total = max(0, int(float(seconds or 0)))
    except (TypeError, ValueError):
        total = 0
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _summary_source_text(subtitle_data: dict) -> str:
    """为摘要模型保留字幕时间点，便于示例可追溯。"""
    lines = []
    for segment in subtitle_data.get("segments") or []:
        if not isinstance(segment, dict):
            continue
        text = str(segment.get("text") or "").strip()
        if text:
            lines.append(
                f"[{_format_summary_timestamp(segment.get('start'))}] {text}"
            )
    return "\n".join(lines) or str(subtitle_data.get("full_text") or "").strip()


def _summary_cache_is_current(stored: dict) -> bool:
    if not str(stored.get("summary") or "").strip():
        return False
    try:
        version = int(stored.get("summary_format_version") or 0)
    except (TypeError, ValueError):
        return False
    return version >= SUMMARY_FORMAT_VERSION


def _saved_chat_messages(url: str, user: dict | None) -> list[dict]:
    current_owner = owner_key(user)
    messages = []
    for item in content_store.load(url).get("chats") or []:
        if item.get("owner") != current_owner:
            continue
        messages.extend([
            {"role": "user", "content": item.get("question", "")},
            {"role": "assistant", "content": item.get("answer", "")},
        ])
    return messages


@router.post("/summarize", response_class=EventSourceResponse)
async def summarize_video(req: SummarizeRequest, user: dict = Depends(get_current_user)) -> AsyncIterable[ServerSentEvent]:
    """
    AI 视频总结（SSE 流式）
    事件类型: subtitle / progress / summary / mindmap / done / error / quota
    """
    allowed, remaining, message = _check_summary_permission(user)
    if not allowed:
        yield ServerSentEvent(
            raw_data=json.dumps({"message": message, "need_login": user is None, "need_vip": user is not None}, ensure_ascii=False),
            event="error",
        )
        return

    try:
        loop = asyncio.get_running_loop()
        stored = content_store.load(req.url)
        # force=True 时不复用已存字幕/转写，强制重新提取，避免旧的错误缓存串用
        saved_subtitle = None if req.force else stored.get("subtitle")

        yield ServerSentEvent(
            raw_data=json.dumps({"messages": _saved_chat_messages(req.url, user)}, ensure_ascii=False),
            event="history",
        )

        if _has_usable_subtitle(saved_subtitle):
            subtitle_data = dict(saved_subtitle)
            subtitle_data["cache_hit"] = True
            yield ServerSentEvent(
                raw_data=json.dumps({
                    "stage": "disk_cache",
                    "message": "已从磁盘读取字幕历史",
                    "percent": 100,
                }, ensure_ascii=False),
                event="progress",
            )
            yield ServerSentEvent(
                raw_data=json.dumps(subtitle_data, ensure_ascii=False),
                event="subtitle",
            )
        else:
            yield ServerSentEvent(
                raw_data=json.dumps({
                    "stage": "subtitle",
                    "message": "正在检查平台字幕...",
                    "percent": 2,
                }, ensure_ascii=False),
                event="progress",
            )
            extractor = _get_extractor()
            subtitle_data = await loop.run_in_executor(None, extractor.extract, req.url, req.force)

            if subtitle_data.get("cache_hit"):
                yield ServerSentEvent(
                    raw_data=json.dumps({
                        "stage": "subtitle_cache",
                        "message": "已读取字幕历史缓存",
                        "percent": 100,
                    }, ensure_ascii=False),
                    event="progress",
                )
            yield ServerSentEvent(
                raw_data=json.dumps(subtitle_data, ensure_ascii=False),
                event="subtitle",
            )

            if not _has_usable_subtitle(subtitle_data):
                async for event_type, event_data in _transcribe_with_progress(req.url, req.force):
                    if event_type == "progress":
                        yield ServerSentEvent(
                            raw_data=json.dumps(event_data, ensure_ascii=False),
                            event="progress",
                        )
                    else:
                        subtitle_data = event_data
                yield ServerSentEvent(
                    raw_data=json.dumps(subtitle_data, ensure_ascii=False),
                    event="subtitle",
                )

            if _has_usable_subtitle(subtitle_data):
                content_store.update(req.url, title=req.title, subtitle=subtitle_data)

        if not _has_usable_subtitle(subtitle_data):
            yield ServerSentEvent(
                raw_data=json.dumps({"message": "该视频没有可用字幕，且语音转写没有得到有效内容"}, ensure_ascii=False),
                event="error",
            )
            return

        full_text = subtitle_data["full_text"]
        summary_source = _summary_source_text(subtitle_data)
        summarizer = None

        requested_parts = {
            str(item).strip().lower()
            for item in (req.parts or [])
            if str(item).strip()
        }
        # force=True：总结 + 思维导图都重生成
        # parts 指定：只重生成对应部分
        # 都未指定：有缓存用缓存，没有再生成
        if req.force:
            refresh_summary = True
            refresh_mindmap = True
        elif requested_parts:
            refresh_summary = "summary" in requested_parts
            refresh_mindmap = "mindmap" in requested_parts
        else:
            refresh_summary = not _summary_cache_is_current(stored)
            refresh_mindmap = not str(stored.get("mindmap") or "").strip()

        summary_text = "" if refresh_summary else str(stored.get("summary") or "")
        mindmap_md = "" if refresh_mindmap else str(stored.get("mindmap") or "")

        if summary_text and not refresh_summary:
            yield ServerSentEvent(
                raw_data=json.dumps({
                    "stage": "content_cache",
                    "message": "已从磁盘读取历史总结",
                    "percent": 100,
                }, ensure_ascii=False),
                event="progress",
            )
            yield ServerSentEvent(raw_data=json.dumps(summary_text, ensure_ascii=False), event="summary")
        elif refresh_summary:
            yield ServerSentEvent(
                raw_data=json.dumps({
                    "stage": "summary",
                    "message": "正在重新生成总结..." if (requested_parts or req.force) else "AI 正在分析视频内容...",
                    "percent": None,
                }, ensure_ascii=False),
                event="progress",
            )
            summarizer = _get_summarizer()
            summary_parts = []
            for token in summarizer.summarize_stream(summary_source, req.language):
                summary_parts.append(token)
                yield ServerSentEvent(raw_data=json.dumps(token, ensure_ascii=False), event="summary")
            summary_text = "".join(summary_parts)
        elif summary_text:
            yield ServerSentEvent(raw_data=json.dumps(summary_text, ensure_ascii=False), event="summary")

        from summarizer import sanitize_mindmap_markdown

        if mindmap_md and not refresh_mindmap:
            mindmap_md = sanitize_mindmap_markdown(mindmap_md)
            yield ServerSentEvent(
                raw_data=json.dumps({
                    "stage": "mindmap_cache",
                    "message": "已从磁盘读取历史思维导图",
                    "percent": 100,
                }, ensure_ascii=False),
                event="progress",
            )
        elif refresh_mindmap:
            yield ServerSentEvent(
                raw_data=json.dumps({
                    "stage": "mindmap",
                    "message": "正在重新生成思维导图..." if (requested_parts or req.force) else "正在生成思维导图...",
                    "percent": None,
                }, ensure_ascii=False),
                event="progress",
            )
            summarizer = summarizer or _get_summarizer()
            mindmap_md = await loop.run_in_executor(
                None, summarizer.generate_mindmap, full_text, req.language
            )
            mindmap_md = sanitize_mindmap_markdown(mindmap_md)
        else:
            mindmap_md = sanitize_mindmap_markdown(mindmap_md)

        if mindmap_md:
            yield ServerSentEvent(
                raw_data=json.dumps({"markdown": mindmap_md}, ensure_ascii=False),
                event="mindmap",
            )

        update_fields = {
            "title": req.title or stored.get("title", ""),
            "subtitle": subtitle_data,
        }
        if refresh_summary or summary_text:
            update_fields["summary"] = summary_text
        if refresh_summary:
            update_fields["summary_format_version"] = SUMMARY_FORMAT_VERSION
        if refresh_mindmap or mindmap_md:
            update_fields["mindmap"] = mindmap_md
        content_store.update(req.url, **update_fields)

        quota_info = {"remaining": remaining, "limit": FREE_DAILY_SUMMARY_LIMIT}
        yield ServerSentEvent(
            raw_data=json.dumps(quota_info, ensure_ascii=False),
            event="quota",
        )

        yield ServerSentEvent(raw_data="[DONE]", event="done")

    except Exception as e:
        yield ServerSentEvent(
            raw_data=json.dumps({"message": f"总结失败: {str(e)}"}, ensure_ascii=False),
            event="error",
        )


@router.post("/chat", response_class=EventSourceResponse)
async def chat_with_video(req: ChatRequest, user: dict = Depends(get_current_user)) -> AsyncIterable[ServerSentEvent]:
    """AI 视频问答（SSE 流式）"""
    try:
        if not req.subtitle_text.strip():
            loop = asyncio.get_running_loop()
            subtitle_data = content_store.load(req.url).get("subtitle")
            if not _has_usable_subtitle(subtitle_data):
                extractor = _get_extractor()
                subtitle_data = await loop.run_in_executor(
                    None, extractor.extract, req.url
                )
                if not _has_usable_subtitle(subtitle_data):
                    async for event_type, event_data in _transcribe_with_progress(req.url):
                        if event_type == "progress":
                            yield ServerSentEvent(
                                raw_data=json.dumps(event_data, ensure_ascii=False),
                                event="progress",
                            )
                        else:
                            subtitle_data = event_data
                if _has_usable_subtitle(subtitle_data):
                    content_store.update(req.url, subtitle=subtitle_data)
            if not _has_usable_subtitle(subtitle_data):
                yield ServerSentEvent(
                    raw_data=json.dumps({"message": "该视频没有可用字幕，且语音转写没有得到有效内容"}, ensure_ascii=False),
                    event="error",
                )
                return
            subtitle_text = subtitle_data["full_text"]
        else:
            subtitle_text = req.subtitle_text

        summarizer = _get_summarizer()
        answer_parts = []
        for token in summarizer.chat_stream(subtitle_text, req.question):
            answer_parts.append(token)
            yield ServerSentEvent(raw_data=json.dumps(token, ensure_ascii=False), event="answer")

        content_store.append_chat(req.url, req.question, "".join(answer_parts), user)

        yield ServerSentEvent(raw_data="[DONE]", event="done")

    except Exception as e:
        yield ServerSentEvent(
            raw_data=json.dumps({"message": f"回答失败: {str(e)}"}, ensure_ascii=False),
            event="error",
        )


@router.post("/chat/clear")
async def clear_video_chat(req: ClearChatRequest, user: dict = Depends(get_current_user)):
    """清空当前用户在该视频下的 AI 问答历史。"""
    removed = content_store.clear_chats(req.url, user)
    return {
        "success": True,
        "data": {
            "removed": removed,
            "messages": [],
        },
    }


@router.post("/quiz/generate")
async def generate_video_quiz(
    req: QuizGenerateRequest,
    user: dict = Depends(get_current_user),
):
    """根据已提取的视频文本生成理解测试题卷。"""
    try:
        stored = content_store.load(req.url)
        if not req.force and isinstance(stored.get("quiz"), dict):
            if stored["quiz"].get("questions"):
                return stored["quiz"]

        subtitle_text = req.subtitle_text.strip()
        if not subtitle_text:
            loop = asyncio.get_running_loop()
            subtitle_data = stored.get("subtitle")
            if not _has_usable_subtitle(subtitle_data):
                extractor = _get_extractor()
                subtitle_data = await loop.run_in_executor(
                    None, extractor.extract, req.url
                )
                if not _has_usable_subtitle(subtitle_data):
                    transcriber = _get_transcriber()
                    subtitle_data = await loop.run_in_executor(
                        None, transcriber.transcribe_url, req.url
                    )
                if _has_usable_subtitle(subtitle_data):
                    content_store.update(req.url, subtitle=subtitle_data)
            subtitle_text = subtitle_data.get("full_text", "").strip()

        if not subtitle_text:
            raise HTTPException(status_code=400, detail="没有可用于出题的视频文本")

        loop = asyncio.get_running_loop()
        summarizer = _get_summarizer()
        quiz = await loop.run_in_executor(
            None, summarizer.generate_quiz, subtitle_text, req.language
        )
        content_store.update(req.url, quiz=quiz)
        return quiz
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"生成理解测试失败: {exc}") from exc


@router.post("/quiz/generate-stream", response_class=EventSourceResponse)
async def generate_video_quiz_stream(
    req: QuizGenerateRequest,
    user: dict = Depends(get_current_user),
) -> AsyncIterable[ServerSentEvent]:
    """按题型分批生成题卷，每完成一批便通过 SSE 返回。"""
    try:
        stored = content_store.load(req.url)
        cached_quiz = stored.get("quiz")
        if not req.force and isinstance(cached_quiz, dict) and cached_quiz.get("questions"):
            yield ServerSentEvent(
                raw_data=json.dumps({"quiz": cached_quiz, "cache_hit": True}, ensure_ascii=False),
                event="quiz_complete",
            )
            yield ServerSentEvent(raw_data="[DONE]", event="done")
            return

        subtitle_text = req.subtitle_text.strip()
        if not subtitle_text:
            loop = asyncio.get_running_loop()
            subtitle_data = stored.get("subtitle")
            if not _has_usable_subtitle(subtitle_data):
                yield ServerSentEvent(
                    raw_data=json.dumps({
                        "stage": "subtitle",
                        "message": "正在准备视频文本...",
                        "percent": 0,
                    }, ensure_ascii=False),
                    event="quiz_progress",
                )
                extractor = _get_extractor()
                subtitle_data = await loop.run_in_executor(None, extractor.extract, req.url)
                if not _has_usable_subtitle(subtitle_data):
                    transcriber = _get_transcriber()
                    subtitle_data = await loop.run_in_executor(
                        None, transcriber.transcribe_url, req.url
                    )
                if _has_usable_subtitle(subtitle_data):
                    content_store.update(req.url, subtitle=subtitle_data)
            subtitle_text = str((subtitle_data or {}).get("full_text") or "").strip()

        if not subtitle_text:
            yield ServerSentEvent(
                raw_data=json.dumps({"message": "没有可用于出题的视频文本"}, ensure_ascii=False),
                event="error",
            )
            return

        from summarizer import QUIZ_BATCH_SPECS

        loop = asyncio.get_running_loop()
        summarizer = _get_summarizer()
        all_questions: list[dict] = []
        quiz_title = "视频内容理解测试"
        total_batches = len(QUIZ_BATCH_SPECS)
        total_questions = sum(spec["count"] for spec in QUIZ_BATCH_SPECS)

        for batch_index, spec in enumerate(QUIZ_BATCH_SPECS, start=1):
            yield ServerSentEvent(
                raw_data=json.dumps({
                    "stage": spec["type"],
                    "type": spec["type"],
                    "type_label": spec["label"],
                    "batch_index": batch_index,
                    "total_batches": total_batches,
                    "completed_questions": len(all_questions),
                    "total_questions": total_questions,
                    "percent": round((batch_index - 1) * 100 / total_batches),
                    "message": f"正在生成第 {batch_index}/{total_batches} 批：{spec['label']}...",
                }, ensure_ascii=False),
                event="quiz_progress",
            )

            batch = await loop.run_in_executor(
                None,
                summarizer.generate_quiz_batch,
                subtitle_text,
                req.language,
                spec,
                len(all_questions) + 1,
                list(all_questions),
            )
            if batch_index == 1 and batch.get("title"):
                quiz_title = batch["title"]
            all_questions.extend(batch["questions"])

            yield ServerSentEvent(
                raw_data=json.dumps({
                    "title": quiz_title,
                    "questions": batch["questions"],
                    "type": spec["type"],
                    "type_label": spec["label"],
                    "batch_index": batch_index,
                    "total_batches": total_batches,
                    "completed_questions": len(all_questions),
                    "total_questions": total_questions,
                    "percent": round(batch_index * 100 / total_batches),
                }, ensure_ascii=False),
                event="quiz_batch",
            )

        quiz = {
            "title": quiz_title,
            "questions": all_questions,
            "max_score": sum(int(item.get("points") or 0) for item in all_questions),
        }
        content_store.update(req.url, quiz=quiz)
        yield ServerSentEvent(
            raw_data=json.dumps({"quiz": quiz, "cache_hit": False}, ensure_ascii=False),
            event="quiz_complete",
        )
        yield ServerSentEvent(raw_data="[DONE]", event="done")
    except Exception as exc:
        yield ServerSentEvent(
            raw_data=json.dumps({"message": f"生成理解测试失败: {exc}"}, ensure_ascii=False),
            event="error",
        )


@router.post("/quiz/state/get")
async def get_quiz_state(
    req: QuizStateRequest,
    user: dict = Depends(get_current_user),
):
    """从磁盘读取当前用户在指定视频上的答题草稿和历史答卷。"""
    return content_store.load_quiz_state(req.url, user)


@router.post("/quiz/state/save")
async def save_quiz_state(
    req: QuizStateRequest,
    user: dict = Depends(get_current_user),
):
    """将当前用户的答题草稿和历史答卷原子写入磁盘。"""
    content_store.save_quiz_state(req.url, user, req.state)
    return {"success": True}


@router.post("/quiz/grade")
async def grade_video_quiz(
    req: QuizGradeRequest,
    user: dict = Depends(get_current_user),
):
    """客观题自动判分，简答题使用当前模型按评分点阅卷。"""
    if not req.quiz.get("questions"):
        raise HTTPException(status_code=400, detail="题卷内容为空")
    try:
        loop = asyncio.get_running_loop()
        summarizer = _get_summarizer()
        return await loop.run_in_executor(
            None, summarizer.grade_quiz, req.quiz, req.answers
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"理解测试阅卷失败: {exc}") from exc
