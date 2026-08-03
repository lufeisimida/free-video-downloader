"""登录用户的视频资料库、目录树和课程组卷 API。"""

import asyncio
import hashlib
import json
import re
from collections.abc import AsyncIterable
from datetime import date, datetime, timezone
from difflib import SequenceMatcher
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel, Field

from auth import get_current_user
from content_store import content_store
from database import (
    create_video_folder,
    create_video_note,
    delete_question_bank_item,
    delete_video_note,
    delete_library_video,
    delete_video_folder,
    get_folder_descendant_ids,
    get_latest_course_quiz,
    get_learning_dashboard,
    get_learning_goal,
    get_library_video,
    get_video_folder,
    ensure_flashcard,
    list_flashcards,
    list_folder_library_videos,
    list_knowledge_mastery,
    list_library_videos,
    list_completed_daily_tasks,
    list_knowledge_relations,
    list_mistake_diagnoses,
    list_question_bank,
    list_video_folders,
    list_video_notes,
    list_video_notes_for_video,
    list_video_progress,
    list_wrong_questions,
    move_library_video,
    review_flashcard,
    rebuild_knowledge_relations,
    save_course_quiz,
    save_quiz_attempt,
    set_daily_task_completion,
    upsert_learning_goal,
    upsert_mistake_diagnosis,
    upsert_question_bank_item,
    upsert_library_video,
    upsert_video_progress,
    update_video_folder,
)
from settings import is_superuser_email


router = APIRouter(prefix="/api/library", tags=["课程资料库"])


class FolderCreateRequest(BaseModel):
    name: str
    parent_id: int | None = None


class FolderUpdateRequest(BaseModel):
    name: str | None = None
    parent_id: int | None = None


class VideoMoveRequest(BaseModel):
    folder_id: int | None = None


class CourseQuizRequest(BaseModel):
    language: str = "zh"
    force: bool = False
    mode: str = "standard"
    phase: str = "practice"
    knowledge_point: str | None = None


class QuizAttemptRequest(BaseModel):
    quiz_id: int | None = None
    quiz: dict
    answers: dict = Field(default_factory=dict)
    grading: dict
    mode: str = "standard"
    phase: str = "practice"


class FlashcardReviewRequest(BaseModel):
    remembered: bool


class VideoProgressRequest(BaseModel):
    progress_seconds: float = 0
    duration_seconds: float = 0
    completion_percent: float = 0
    status: str = "in_progress"


class VideoNoteRequest(BaseModel):
    video_id: int
    time_seconds: float = 0
    content: str


class LearningGoalRequest(BaseModel):
    exam_date: str | None = None
    target_score: float = 80
    daily_minutes: int = 30


class DailyTaskRequest(BaseModel):
    task_key: str
    completed: bool = True


class BatchImportRequest(BaseModel):
    urls: list[str] = Field(default_factory=list)
    folder_name: str | None = None
    parent_id: int | None = None
    expand_playlists: bool = True


class MistakeDiagnosisRequest(BaseModel):
    question_bank_id: int
    answer: str | list | None = None


class CourseSearchRequest(BaseModel):
    query: str
    limit: int = 12


QUIZ_MODE_COUNTS = {
    "quick": 8,
    "standard": 16,
    "exam": 20,
    "adaptive": 12,
    "wrong": 16,
}
QUIZ_PHASES = {"pre", "practice", "post"}


def _validate_quiz_options(mode: str, phase: str) -> tuple[str, str]:
    if mode not in QUIZ_MODE_COUNTS:
        raise HTTPException(status_code=400, detail="不支持的组卷模式")
    if phase not in QUIZ_PHASES:
        raise HTTPException(status_code=400, detail="不支持的测试阶段")
    return mode, phase


def _format_timestamp(seconds: float) -> str:
    value = max(0, int(seconds or 0))
    hours, remainder = divmod(value, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _subtitle_text(subtitle: dict) -> str:
    segments = subtitle.get("segments") or []
    lines = []
    for segment in segments:
        if not isinstance(segment, dict) or not str(segment.get("text") or "").strip():
            continue
        try:
            start = float(segment.get("start") or 0)
        except (TypeError, ValueError):
            start = 0
        lines.append(
            f"[{_format_timestamp(start)}] {str(segment['text']).strip()}"
        )
    return "\n".join(lines) or str(subtitle.get("full_text") or "").strip()


def _question_fingerprint(question: dict) -> str:
    raw = "|".join([
        str(question.get("type") or ""),
        str(question.get("question") or "").strip().casefold(),
        str(question.get("reference_answer") or "").strip().casefold(),
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _prepare_question(question: dict, sources: list[tuple[dict, str]]) -> dict:
    item = dict(question)
    requested_title = str(item.get("source_video_title") or "").strip().casefold()
    source = next(
        (
            video for video, _ in sources
            if requested_title and (
                requested_title in str(video["title"]).casefold()
                or str(video["title"]).casefold() in requested_title
            )
        ),
        sources[0][0],
    )
    item["knowledge_point"] = str(item.get("knowledge_point") or "课程综合").strip()[:80]
    item["source_video_title"] = source["title"]
    item["source_video_url"] = source["url"]
    item["evidence_quote"] = str(item.get("evidence_quote") or "").strip()[:500]
    try:
        item["evidence_time_seconds"] = max(0, float(item.get("evidence_time_seconds") or 0))
    except (TypeError, ValueError):
        item["evidence_time_seconds"] = 0
    item["fingerprint"] = _question_fingerprint(item)
    return item


def _persist_questions(user_id: int, folder_id: int, questions: list[dict],
                       source_text: str = "") -> dict[str, int]:
    from learning_efficiency import (
        assess_question_quality,
        canonicalize_knowledge_point,
        save_question_quality,
    )

    result = {}
    existing = list_question_bank(user_id, folder_id, limit=1000)
    existing_by_fingerprint = {
        str(item.get("fingerprint") or ""): int(item["id"])
        for item in existing
        if item.get("fingerprint")
    }
    for question in questions:
        fingerprint = str(question.get("fingerprint") or _question_fingerprint(question))
        question["fingerprint"] = fingerprint
        existing_id = existing_by_fingerprint.get(fingerprint)
        if existing_id:
            result[fingerprint] = existing_id
            continue
        question["knowledge_point"] = canonicalize_knowledge_point(
            user_id, folder_id, question.get("knowledge_point") or "课程综合"
        )
        quality = assess_question_quality(question, existing, source_text)
        if quality["status"] != "approved":
            continue
        bank_item = upsert_question_bank_item(user_id, folder_id, fingerprint, question)
        bank_item_id = int(bank_item["id"])
        save_question_quality(bank_item_id, quality)
        ensure_flashcard(user_id, folder_id, question)
        result[fingerprint] = bank_item_id
        existing_by_fingerprint[fingerprint] = bank_item_id
        existing.append({"question": question})
    return result


def _mode_specs(mode: str, base_specs: list[dict]) -> list[dict]:
    target = QUIZ_MODE_COUNTS[mode]
    if mode == "standard":
        return [dict(item) for item in base_specs]
    if mode == "quick":
        counts = [3, 2, 2, 1, 0]
    elif mode == "exam":
        counts = [6, 4, 4, 4, 2]
    else:
        counts = [4, 2, 2, 3, 1]
    specs = []
    for spec, count in zip(base_specs, counts):
        if count:
            item = dict(spec)
            item["count"] = count
            specs.append(item)
    assert sum(item["count"] for item in specs) == target
    return specs


def _tokenize(text: str) -> set[str]:
    value = str(text or "").casefold()
    latin = re.findall(r"[a-z0-9_+#.-]{2,}", value)
    chinese = re.findall(r"[\u4e00-\u9fff]", value)
    chinese_pairs = ["".join(chinese[index:index + 2]) for index in range(len(chinese) - 1)]
    return set(latin + chinese + chinese_pairs)


def _search_score(query: str, text: str) -> float:
    query_tokens = _tokenize(query)
    text_tokens = _tokenize(text)
    overlap = len(query_tokens & text_tokens) / max(len(query_tokens), 1)
    phrase = 1.0 if query.casefold() in text.casefold() else 0.0
    fuzzy = SequenceMatcher(None, query.casefold(), text[:400].casefold()).ratio()
    return round(overlap * 0.65 + phrase * 0.25 + fuzzy * 0.1, 4)


def _course_search(user_id: int, folder_id: int, query: str, limit: int = 12) -> list[dict]:
    results = []
    for video in list_folder_library_videos(user_id, folder_id):
        subtitle = content_store.load(video["url"]).get("subtitle") or {}
        segments = subtitle.get("segments") or []
        if segments:
            for segment in segments:
                text = str(segment.get("text") or "").strip()
                score = _search_score(query, text)
                if text and score >= 0.08:
                    results.append({
                        "type": "subtitle", "score": score, "text": text,
                        "video_id": video["id"], "video_title": video["title"],
                        "video_url": video["url"],
                        "time_seconds": float(segment.get("start") or 0),
                    })
        else:
            text = str(subtitle.get("full_text") or "").strip()
            for chunk_index in range(0, len(text), 240):
                chunk = text[chunk_index:chunk_index + 320]
                score = _search_score(query, chunk)
                if chunk and score >= 0.08:
                    results.append({
                        "type": "subtitle", "score": score, "text": chunk,
                        "video_id": video["id"], "video_title": video["title"],
                        "video_url": video["url"], "time_seconds": 0,
                    })
    for item in list_question_bank(user_id, folder_id, limit=500):
        question = item["question"]
        text = " ".join([
            str(question.get("question") or ""),
            str(question.get("reference_answer") or ""),
            str(question.get("explanation") or ""),
        ])
        score = _search_score(query, text)
        if score >= 0.08:
            results.append({
                "type": "question", "score": score,
                "text": str(question.get("question") or ""),
                "answer": str(question.get("reference_answer") or question.get("explanation") or ""),
                "knowledge_point": item["knowledge_point"],
                "video_title": item["source_video_title"],
                "video_url": item["source_video_url"],
                "time_seconds": item["evidence_time_seconds"],
            })
    return sorted(results, key=lambda item: item["score"], reverse=True)[:max(1, min(limit, 30))]


def _diagnose_mistake(question: dict, answer) -> tuple[str, str, str]:
    actual = " ".join(answer) if isinstance(answer, list) else str(answer or "").strip()
    qtype = question.get("type")
    expected = question.get("answer") or []
    if not actual:
        return "记忆模糊", "本题未作答，知识点尚未形成可提取记忆。", "先复习闪卡，再回到原视频证据处重看。"
    if qtype == "multiple":
        return "知识混淆", f"多选题需要完整区分 {len(expected)} 个正确要素，当前答案存在漏选或混选。", "对比每个选项与原文证据，完成一次同知识点专项训练。"
    if qtype in {"short_answer", "analysis"}:
        return "表达不完整", "答案未覆盖参考答案中的关键评分点，概念可能理解但输出结构不足。", "按“结论—依据—应用”重写答案，再进行一次复述。"
    if len(actual) <= 2:
        return "题意误读", "选择结果与标准答案不符，可能忽略了题干中的限定条件。", "重读题干限定词，并回看证据时间点。"
    return "概念未理解", "当前回答与核心概念存在偏差，需要重新建立概念和例子的连接。", "回看来源片段，创建一张自己的例子闪卡。"


def _goal_prediction(user_id: int, folder_id: int) -> dict:
    dashboard = get_learning_dashboard(user_id, folder_id)
    goal = get_learning_goal(user_id, folder_id) or {
        "exam_date": None, "target_score": 80, "daily_minutes": 30,
    }
    mastery_values = [float(item["mastery_score"]) for item in dashboard["mastery"]]
    mastery_average = sum(mastery_values) / len(mastery_values) if mastery_values else dashboard["average_score"]
    current = max(float(dashboard["average_score"]), mastery_average * 0.75)
    days_left = None
    if goal.get("exam_date"):
        try:
            days_left = max(0, (date.fromisoformat(goal["exam_date"]) - date.today()).days)
        except ValueError:
            days_left = None
    daily_minutes = int(goal.get("daily_minutes") or 30)
    potential_gain = min(25, ((days_left if days_left is not None else 14) * daily_minutes / 60) * 0.75)
    predicted = round(min(100, current + potential_gain), 1)
    target = float(goal.get("target_score") or 80)
    required_minutes = max(0, round((target - current) / 0.75 * 60))
    required_daily = round(required_minutes / max(days_left or 14, 1))
    return {
        "goal": goal, "current_score": round(current, 1),
        "predicted_score": predicted, "target_score": target,
        "days_left": days_left, "required_daily_minutes": required_daily,
        "on_track": predicted >= target,
    }


def _looks_like_playlist(url: str) -> bool:
    value = url.casefold()
    return any(marker in value for marker in (
        "list=", "/playlist", "/playlists/", "/collection/", "/series/", "合集",
    ))


def _expand_playlist_url(url: str) -> list[dict]:
    import yt_dlp

    from cookies import common_ydl_opts

    with yt_dlp.YoutubeDL({
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "playlistend": 200,
        "skip_download": True,
        **common_ydl_opts(),
    }) as ydl:
        info = ydl.extract_info(url, download=False)
    entries = (info or {}).get("entries") or []
    result = []
    for entry in entries:
        if not entry:
            continue
        item_url = str(entry.get("webpage_url") or entry.get("original_url") or entry.get("url") or "")
        if item_url and not item_url.startswith(("http://", "https://")):
            extractor = str(entry.get("extractor_key") or entry.get("extractor") or "").casefold()
            if "youtube" in extractor:
                item_url = f"https://www.youtube.com/watch?v={item_url}"
        if item_url:
            result.append({
                "url": item_url,
                "title": str(entry.get("title") or "待解析视频")[:200],
                "thumbnail": str(entry.get("thumbnail") or ""),
                "uploader": str(entry.get("uploader") or entry.get("channel") or ""),
                "platform": str(entry.get("extractor_key") or entry.get("extractor") or ""),
            })
    return result


def _clean_folder_name(name: str) -> str:
    value = " ".join((name or "").strip().split())
    if not value:
        raise HTTPException(status_code=400, detail="目录名称不能为空")
    if len(value) > 80:
        raise HTTPException(status_code=400, detail="目录名称不能超过 80 个字符")
    return value


def _ensure_parent(user_id: int, parent_id: int | None) -> None:
    if parent_id is not None and not get_video_folder(user_id, parent_id):
        raise HTTPException(status_code=404, detail="父目录不存在")


def _ensure_unique_name(user_id: int, name: str, parent_id: int | None, exclude_id: int | None = None) -> None:
    duplicate = next(
        (
            item for item in list_video_folders(user_id)
            if item["name"].casefold() == name.casefold()
            and item["parent_id"] == parent_id
            and item["id"] != exclude_id
        ),
        None,
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="同级目录下已存在同名目录")


def _migrate_existing_history(user: dict) -> None:
    """旧内容缓存没有用户字段，仅迁移给内置/显式超级账号。"""
    if not is_superuser_email(user.get("email")):
        return
    existing_urls = {item["url"] for item in list_library_videos(user["id"])}
    for item in content_store.list_items():
        url = str(item.get("url") or "").strip()
        if not url or url in existing_urls:
            continue
        subtitle = item.get("subtitle") or {}
        if not (subtitle.get("has_subtitle") or item.get("summary") or item.get("quiz")):
            continue
        host = urlparse(url).netloc.removeprefix("www.")
        upsert_library_video(user["id"], url, {
            "title": item.get("title") or host or "历史视频",
            "platform": host,
        })
        existing_urls.add(url)


def _library_payload(user: dict) -> dict:
    _migrate_existing_history(user)
    folders = list_video_folders(user["id"])
    videos = list_library_videos(user["id"])
    for video in videos:
        stored = content_store.load(video["url"])
        subtitle = stored.get("subtitle") or {}
        video["has_subtitle"] = bool(
            subtitle.get("has_subtitle") and str(subtitle.get("full_text") or "").strip()
        )
        video["has_summary"] = bool(str(stored.get("summary") or "").strip())
    return {"folders": folders, "videos": videos}


@router.get("")
async def get_library(user: dict = Depends(get_current_user)):
    return {"success": True, "data": _library_payload(user)}


@router.post("/folders")
async def create_folder(req: FolderCreateRequest, user: dict = Depends(get_current_user)):
    name = _clean_folder_name(req.name)
    _ensure_parent(user["id"], req.parent_id)
    _ensure_unique_name(user["id"], name, req.parent_id)
    folder = create_video_folder(user["id"], name, req.parent_id)
    return {"success": True, "data": folder}


@router.patch("/folders/{folder_id}")
async def update_folder(
    folder_id: int,
    req: FolderUpdateRequest,
    user: dict = Depends(get_current_user),
):
    existing = get_video_folder(user["id"], folder_id)
    if not existing:
        raise HTTPException(status_code=404, detail="目录不存在")

    fields_set = req.model_fields_set
    update_parent = "parent_id" in fields_set
    parent_id = req.parent_id if update_parent else existing["parent_id"]
    if update_parent:
        _ensure_parent(user["id"], parent_id)
        if parent_id == folder_id or parent_id in get_folder_descendant_ids(user["id"], folder_id):
            raise HTTPException(status_code=400, detail="不能把目录移动到自身或其子目录")

    name = _clean_folder_name(req.name) if req.name is not None else existing["name"]
    _ensure_unique_name(user["id"], name, parent_id, exclude_id=folder_id)
    folder = update_video_folder(
        user["id"],
        folder_id,
        name=name,
        parent_id=parent_id,
        update_parent=update_parent,
    )
    return {"success": True, "data": folder}


@router.delete("/folders/{folder_id}")
async def remove_folder(folder_id: int, user: dict = Depends(get_current_user)):
    removed = delete_video_folder(user["id"], folder_id)
    if not removed:
        raise HTTPException(status_code=404, detail="目录不存在")
    return {"success": True, "data": _library_payload(user)}


@router.patch("/videos/{video_id}")
async def move_video(
    video_id: int,
    req: VideoMoveRequest,
    user: dict = Depends(get_current_user),
):
    _ensure_parent(user["id"], req.folder_id)
    video = move_library_video(user["id"], video_id, req.folder_id)
    if not video:
        raise HTTPException(status_code=404, detail="视频记录不存在")
    return {"success": True, "data": video}


@router.delete("/videos/{video_id}")
async def remove_video(video_id: int, user: dict = Depends(get_current_user)):
    if not delete_library_video(user["id"], video_id):
        raise HTTPException(status_code=404, detail="视频记录不存在")
    return {"success": True}


@router.get("/folders/{folder_id}/quiz/latest")
async def latest_course_quiz(folder_id: int, user: dict = Depends(get_current_user)):
    if not get_video_folder(user["id"], folder_id):
        raise HTTPException(status_code=404, detail="目录不存在")
    saved = get_latest_course_quiz(user["id"], folder_id)
    if not saved:
        return {"success": True, "data": None}
    return {
        "success": True,
        "data": {
            "id": saved["id"],
            "quiz": json.loads(saved["quiz_json"]),
            "source_count": saved["source_count"],
            "created_at": saved["created_at"],
        },
    }


@router.post("/folders/{folder_id}/quiz/generate-stream", response_class=EventSourceResponse)
async def generate_course_quiz(
    folder_id: int,
    req: CourseQuizRequest,
    user: dict = Depends(get_current_user),
) -> AsyncIterable[ServerSentEvent]:
    """递归汇总目录及子目录的视频字幕，按题型分批生成课程综合测试。"""
    try:
        mode, phase = _validate_quiz_options(req.mode, req.phase)
        folder = get_video_folder(user["id"], folder_id)
        if not folder:
            yield ServerSentEvent(
                raw_data=json.dumps({"message": "目录不存在"}, ensure_ascii=False),
                event="error",
            )
            return

        videos = list_folder_library_videos(user["id"], folder_id)
        sources = []
        missing_titles = []
        for video in videos:
            subtitle = (content_store.load(video["url"]).get("subtitle") or {})
            text = _subtitle_text(subtitle)
            if text:
                sources.append((video, text))
            else:
                missing_titles.append(video["title"])

        if not sources:
            yield ServerSentEvent(
                raw_data=json.dumps({
                    "message": "该目录没有已完成字幕提取的视频，请先打开视频完成内容解析",
                }, ensure_ascii=False),
                event="error",
            )
            return

        per_source_limit = max(400, 14000 // len(sources))
        course_text = "\n\n".join(
            f"### 课程视频：{video['title']}\n{text[:per_source_limit]}"
            for video, text in sources
        )
        if req.knowledge_point:
            course_text = (
                f"专项训练要求：重点考查知识点“{req.knowledge_point[:80]}”。\n\n"
                + course_text
            )

        from api_summarize import _get_summarizer
        from summarizer import QUIZ_BATCH_SPECS

        target_count = QUIZ_MODE_COUNTS[mode]
        bank_questions = []
        if mode == "wrong":
            bank_questions = [item["question"] for item in list_wrong_questions(
                user["id"], folder_id, due_only=True
            )]
            if not bank_questions:
                yield ServerSentEvent(
                    raw_data=json.dumps({"message": "当前没有到期错题"}, ensure_ascii=False),
                    event="error",
                )
                return
        elif not req.force:
            weak_points = None
            if req.knowledge_point:
                weak_points = [req.knowledge_point[:80]]
            elif mode == "adaptive":
                weak_points = [
                    item["knowledge_point"]
                    for item in list_knowledge_mastery(user["id"], folder_id)[:5]
                ] or None
            bank_questions = [
                item["question"] for item in list_question_bank(
                    user["id"], folder_id, limit=target_count, knowledge_points=weak_points
                )
            ]

        if len(bank_questions) >= min(target_count, 1) and (
            mode in {"wrong", "adaptive"} or len(bank_questions) >= target_count
        ):
            selected = [dict(item) for item in bank_questions[:target_count]]
            for index, question in enumerate(selected, start=1):
                question["id"] = index
                question["fingerprint"] = str(
                    question.get("fingerprint") or _question_fingerprint(question)
                )
            quiz_title = f"{folder['name']} - { {'wrong': '错题复习', 'adaptive': '自适应测试'}.get(mode, '课程综合测试') }"
            quiz = {
                "title": quiz_title,
                "questions": selected,
                "max_score": sum(int(item.get("points") or 0) for item in selected),
                "mode": mode,
                "phase": phase,
                "source_videos": [
                    {"title": video["title"], "url": video["url"]}
                    for video, _ in sources
                ],
            }
            quiz_id = save_course_quiz(
                user["id"], folder_id, json.dumps(quiz, ensure_ascii=False), len(sources)
            )
            total_batches = (len(selected) + 3) // 4
            for batch_index in range(total_batches):
                chunk = selected[batch_index * 4:(batch_index + 1) * 4]
                completed = min((batch_index + 1) * 4, len(selected))
                yield ServerSentEvent(
                    raw_data=json.dumps({
                        "title": quiz_title,
                        "questions": chunk,
                        "type_label": "题库复习",
                        "batch_index": batch_index + 1,
                        "total_batches": total_batches,
                        "completed_questions": completed,
                        "total_questions": len(selected),
                        "source_count": len(sources),
                        "percent": round(completed * 100 / len(selected)),
                    }, ensure_ascii=False),
                    event="quiz_batch",
                )
            yield ServerSentEvent(
                raw_data=json.dumps({
                    "quiz": quiz, "quiz_id": quiz_id, "source_count": len(sources),
                    "reused_from_bank": True, "missing_videos": missing_titles,
                }, ensure_ascii=False),
                event="quiz_complete",
            )
            yield ServerSentEvent(raw_data="[DONE]", event="done")
            return

        loop = asyncio.get_running_loop()
        summarizer = _get_summarizer("quiz")
        all_questions = []
        quiz_specs = _mode_specs(mode, QUIZ_BATCH_SPECS)
        total_batches = len(quiz_specs)
        total_questions = sum(spec["count"] for spec in quiz_specs)
        quiz_title = f"{folder['name']} - 课程综合测试"

        yield ServerSentEvent(
            raw_data=json.dumps({
                "message": f"已汇总 {len(sources)} 个视频，开始生成课程试卷",
                "source_count": len(sources),
                "missing_count": len(missing_titles),
                "total_questions": total_questions,
                "percent": 0,
            }, ensure_ascii=False),
            event="quiz_progress",
        )

        for batch_index, spec in enumerate(quiz_specs, start=1):
            yield ServerSentEvent(
                raw_data=json.dumps({
                    "message": f"正在生成第 {batch_index}/{total_batches} 批：{spec['label']}...",
                    "batch_index": batch_index,
                    "total_batches": total_batches,
                    "completed_questions": len(all_questions),
                    "total_questions": total_questions,
                    "source_count": len(sources),
                    "percent": round((batch_index - 1) * 100 / total_batches),
                }, ensure_ascii=False),
                event="quiz_progress",
            )
            batch = await loop.run_in_executor(
                None,
                summarizer.generate_quiz_batch,
                course_text,
                req.language,
                spec,
                len(all_questions) + 1,
                list(all_questions),
            )
            prepared_questions = [
                _prepare_question(question, sources) for question in batch["questions"]
            ]
            all_questions.extend(prepared_questions)
            yield ServerSentEvent(
                raw_data=json.dumps({
                    "title": quiz_title,
                    "questions": prepared_questions,
                    "type_label": spec["label"],
                    "batch_index": batch_index,
                    "total_batches": total_batches,
                    "completed_questions": len(all_questions),
                    "total_questions": total_questions,
                    "source_count": len(sources),
                    "percent": round(batch_index * 100 / total_batches),
                }, ensure_ascii=False),
                event="quiz_batch",
            )

        quiz = {
            "title": quiz_title,
            "questions": all_questions,
            "max_score": sum(int(item.get("points") or 0) for item in all_questions),
            "mode": mode,
            "phase": phase,
            "source_videos": [
                {"id": video["id"], "title": video["title"], "url": video["url"]}
                for video, _ in sources
            ],
        }
        quiz_id = save_course_quiz(
            user["id"], folder_id, json.dumps(quiz, ensure_ascii=False), len(sources)
        )
        _persist_questions(user["id"], folder_id, all_questions, course_text)
        yield ServerSentEvent(
            raw_data=json.dumps({
                "quiz": quiz,
                "quiz_id": quiz_id,
                "source_count": len(sources),
                "missing_videos": missing_titles,
            }, ensure_ascii=False),
            event="quiz_complete",
        )
        yield ServerSentEvent(raw_data="[DONE]", event="done")
    except Exception as exc:
        yield ServerSentEvent(
            raw_data=json.dumps({"message": f"课程组卷失败: {exc}"}, ensure_ascii=False),
            event="error",
        )


@router.post("/folders/{folder_id}/attempts")
async def record_quiz_attempt(
    folder_id: int,
    req: QuizAttemptRequest,
    user: dict = Depends(get_current_user),
):
    if not get_video_folder(user["id"], folder_id):
        raise HTTPException(status_code=404, detail="目录不存在")
    mode, phase = _validate_quiz_options(req.mode, req.phase)
    questions = req.quiz.get("questions") or []
    results = req.grading.get("results") or []
    if not questions or not results:
        raise HTTPException(status_code=400, detail="答卷或阅卷结果为空")
    bank_items = _persist_questions(user["id"], folder_id, questions)
    attempt_id = save_quiz_attempt(
        user["id"],
        folder_id,
        quiz_id=req.quiz_id,
        mode=mode,
        phase=phase,
        total_score=float(req.grading.get("total_score") or 0),
        max_score=float(req.grading.get("max_score") or req.quiz.get("max_score") or 0),
        answers=req.answers,
        results=results,
        bank_items=bank_items,
        questions=questions,
    )
    result_by_id = {str(item.get("id")): item for item in results}
    for question in questions:
        result = result_by_id.get(str(question.get("id")))
        if not result or result.get("correct"):
            continue
        fingerprint = str(question.get("fingerprint") or _question_fingerprint(question))
        bank_id = bank_items.get(fingerprint)
        if not bank_id:
            continue
        answer = req.answers.get(str(question.get("id")), req.answers.get(question.get("id")))
        category, diagnosis, action = _diagnose_mistake(question, answer)
        upsert_mistake_diagnosis(
            user["id"], folder_id, bank_id, category, diagnosis, action
        )
    return {
        "success": True,
        "data": {
            "attempt_id": attempt_id,
            "dashboard": get_learning_dashboard(user["id"], folder_id),
        },
    }


@router.get("/folders/{folder_id}/learning/dashboard")
async def learning_dashboard(folder_id: int, user: dict = Depends(get_current_user)):
    if not get_video_folder(user["id"], folder_id):
        raise HTTPException(status_code=404, detail="目录不存在")
    data = get_learning_dashboard(user["id"], folder_id)
    videos = list_folder_library_videos(user["id"], folder_id)
    parsed_count = 0
    for video in videos:
        subtitle = content_store.load(video["url"]).get("subtitle") or {}
        if str(subtitle.get("full_text") or "").strip():
            parsed_count += 1
    data["video_count"] = len(videos)
    data["parsed_video_count"] = parsed_count
    return {"success": True, "data": data}


@router.get("/folders/{folder_id}/learning/question-bank")
async def question_bank(folder_id: int, user: dict = Depends(get_current_user)):
    if not get_video_folder(user["id"], folder_id):
        raise HTTPException(status_code=404, detail="目录不存在")
    return {
        "success": True,
        "data": list_question_bank(user["id"], folder_id),
    }


@router.get("/folders/{folder_id}/learning/wrong-questions")
async def wrong_questions(
    folder_id: int,
    due_only: bool = False,
    user: dict = Depends(get_current_user),
):
    if not get_video_folder(user["id"], folder_id):
        raise HTTPException(status_code=404, detail="目录不存在")
    return {
        "success": True,
        "data": list_wrong_questions(user["id"], folder_id, due_only=due_only),
    }


@router.get("/folders/{folder_id}/learning/flashcards")
async def flashcards(
    folder_id: int,
    due_only: bool = False,
    user: dict = Depends(get_current_user),
):
    if not get_video_folder(user["id"], folder_id):
        raise HTTPException(status_code=404, detail="目录不存在")
    return {
        "success": True,
        "data": list_flashcards(user["id"], folder_id, due_only=due_only),
    }


@router.post("/learning/flashcards/{card_id}/review")
async def submit_flashcard_review(
    card_id: int,
    req: FlashcardReviewRequest,
    user: dict = Depends(get_current_user),
):
    card = review_flashcard(user["id"], card_id, req.remembered)
    if not card:
        raise HTTPException(status_code=404, detail="闪卡不存在")
    return {"success": True, "data": card}


@router.get("/folders/{folder_id}/learning/today")
async def today_learning_plan(
    folder_id: int,
    minutes: int | None = None,
    user: dict = Depends(get_current_user),
):
    if not get_video_folder(user["id"], folder_id):
        raise HTTPException(status_code=404, detail="目录不存在")
    goal = get_learning_goal(user["id"], folder_id) or {"daily_minutes": 30}
    budget = max(10, min(int(minutes or goal.get("daily_minutes") or 30), 180))
    wrong = list_wrong_questions(user["id"], folder_id, due_only=True)
    cards = list_flashcards(user["id"], folder_id, due_only=True)
    mastery = list_knowledge_mastery(user["id"], folder_id)
    progress = list_video_progress(user["id"], folder_id)
    completed = list_completed_daily_tasks(
        user["id"], folder_id, date.today().isoformat()
    )
    candidates = []
    if wrong:
        candidates.append({
            "key": "wrong-review", "type": "wrong", "title": f"复习 {len(wrong)} 道到期错题",
            "description": "优先处理即将遗忘且曾经答错的内容",
            "minutes": min(15, max(5, len(wrong) * 3)), "priority": 100,
        })
    if cards:
        candidates.append({
            "key": "flashcard-review", "type": "flashcard",
            "title": f"复习 {len(cards)} 张到期闪卡",
            "description": "快速提取练习，巩固长期记忆",
            "minutes": min(10, max(3, len(cards))), "priority": 90,
        })
    if mastery:
        weak = mastery[0]
        candidates.append({
            "key": f"weak:{weak['knowledge_point']}", "type": "adaptive",
            "knowledge_point": weak["knowledge_point"],
            "title": f"专项训练：{weak['knowledge_point']}",
            "description": f"当前掌握度 {weak['mastery_score']}%，从薄弱处开始",
            "minutes": 12, "priority": 80,
        })
    next_video = next(
        (item for item in progress if item["status"] != "completed"), None
    )
    if next_video:
        candidates.append({
            "key": f"video:{next_video['video_id']}", "type": "video",
            "video_id": next_video["video_id"], "video_url": next_video["url"],
            "title": ("继续学习：" if next_video["status"] == "in_progress" else "开始学习：") + next_video["title"],
            "description": f"当前进度 {round(float(next_video['completion_percent']))}%",
            "minutes": min(25, max(10, budget // 2)), "priority": 70,
        })
    if not candidates:
        candidates.append({
            "key": "standard-practice", "type": "adaptive",
            "title": "完成一次课程自适应测试",
            "description": "积累掌握度数据后将自动生成个性化计划",
            "minutes": min(20, budget), "priority": 60,
        })
    tasks = []
    used = 0
    for task in sorted(candidates, key=lambda item: item["priority"], reverse=True):
        if used and used + task["minutes"] > budget:
            continue
        task["completed"] = task["key"] in completed
        tasks.append(task)
        used += task["minutes"]
    due_total = len(wrong) + len(cards)
    risk = "high" if due_total >= 10 else "medium" if due_total else "low"
    return {
        "success": True,
        "data": {
            "date": date.today().isoformat(), "budget_minutes": budget,
            "planned_minutes": used, "tasks": tasks,
            "completed_count": sum(1 for item in tasks if item["completed"]),
            "forgetting_risk": risk, "due_review_count": due_total,
        },
    }


@router.post("/folders/{folder_id}/learning/today/complete")
async def complete_today_task(
    folder_id: int,
    req: DailyTaskRequest,
    user: dict = Depends(get_current_user),
):
    if not get_video_folder(user["id"], folder_id):
        raise HTTPException(status_code=404, detail="目录不存在")
    task_key = req.task_key.strip()[:160]
    if not task_key:
        raise HTTPException(status_code=400, detail="任务标识不能为空")
    set_daily_task_completion(
        user["id"], folder_id, date.today().isoformat(), task_key, req.completed
    )
    return {"success": True}


@router.post("/folders/{folder_id}/learning/search")
async def search_course(
    folder_id: int,
    req: CourseSearchRequest,
    user: dict = Depends(get_current_user),
):
    if not get_video_folder(user["id"], folder_id):
        raise HTTPException(status_code=404, detail="目录不存在")
    query = req.query.strip()
    if len(query) < 2:
        raise HTTPException(status_code=400, detail="搜索内容至少需要 2 个字符")
    return {
        "success": True,
        "data": {"query": query, "results": _course_search(
            user["id"], folder_id, query, req.limit
        )},
    }


@router.get("/folders/{folder_id}/learning/progress")
async def course_video_progress(folder_id: int, user: dict = Depends(get_current_user)):
    if not get_video_folder(user["id"], folder_id):
        raise HTTPException(status_code=404, detail="目录不存在")
    return {"success": True, "data": list_video_progress(user["id"], folder_id)}


@router.patch("/learning/videos/{video_id}/progress")
async def update_course_video_progress(
    video_id: int,
    req: VideoProgressRequest,
    user: dict = Depends(get_current_user),
):
    if req.status not in {"not_started", "in_progress", "completed", "review"}:
        raise HTTPException(status_code=400, detail="不支持的学习状态")
    progress = upsert_video_progress(
        user["id"], video_id,
        progress_seconds=req.progress_seconds,
        duration_seconds=req.duration_seconds,
        completion_percent=req.completion_percent,
        status=req.status,
    )
    if not progress:
        raise HTTPException(status_code=404, detail="视频记录不存在")
    return {"success": True, "data": progress}


@router.get("/folders/{folder_id}/learning/notes")
async def course_notes(folder_id: int, user: dict = Depends(get_current_user)):
    if not get_video_folder(user["id"], folder_id):
        raise HTTPException(status_code=404, detail="目录不存在")
    return {"success": True, "data": list_video_notes(user["id"], folder_id)}


@router.get("/learning/videos/{video_id}/notes")
async def video_notes(video_id: int, user: dict = Depends(get_current_user)):
    if not get_library_video(user["id"], video_id):
        raise HTTPException(status_code=404, detail="视频记录不存在")
    return {
        "success": True,
        "data": list_video_notes_for_video(user["id"], video_id),
    }


@router.post("/learning/notes")
async def add_course_note(
    req: VideoNoteRequest,
    user: dict = Depends(get_current_user),
):
    content = req.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="笔记内容不能为空")
    note = create_video_note(user["id"], req.video_id, content[:4000], req.time_seconds)
    if not note:
        raise HTTPException(status_code=404, detail="视频记录不存在")
    return {"success": True, "data": note}


@router.delete("/learning/notes/{note_id}")
async def remove_course_note(note_id: int, user: dict = Depends(get_current_user)):
    if not delete_video_note(user["id"], note_id):
        raise HTTPException(status_code=404, detail="笔记不存在")
    return {"success": True}


@router.post("/folders/{folder_id}/learning/notes/organize")
async def organize_course_notes(
    folder_id: int,
    user: dict = Depends(get_current_user),
):
    notes = list_video_notes(user["id"], folder_id)
    if not notes:
        raise HTTPException(status_code=400, detail="当前课程还没有笔记")
    from api_summarize import _get_summarizer
    try:
        loop = asyncio.get_running_loop()
        markdown = await loop.run_in_executor(
            None, _get_summarizer().organize_notes, notes[:100]
        )
        return {"success": True, "data": {"markdown": markdown}}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"整理笔记失败: {exc}") from exc


@router.post("/learning/notes/{note_id}/flashcard")
async def note_to_flashcard(note_id: int, user: dict = Depends(get_current_user)):
    with_notes = []
    for folder in list_video_folders(user["id"]):
        with_notes.extend(list_video_notes(user["id"], folder["id"]))
    note = next((item for item in with_notes if item["id"] == note_id), None)
    if not note or not note.get("folder_id"):
        raise HTTPException(status_code=404, detail="笔记不存在或尚未归档")
    question = {
        "question": f"复述笔记：{note['content'][:80]}",
        "reference_answer": note["content"],
        "explanation": "能准确复述笔记中的关键观点即可。",
        "knowledge_point": "个人笔记",
        "source_video_title": note["video_title"],
        "source_video_url": note["video_url"],
        "evidence_time_seconds": note["time_seconds"],
    }
    ensure_flashcard(user["id"], note["folder_id"], question)
    return {"success": True}


@router.get("/folders/{folder_id}/learning/goal")
async def learning_goal(folder_id: int, user: dict = Depends(get_current_user)):
    if not get_video_folder(user["id"], folder_id):
        raise HTTPException(status_code=404, detail="目录不存在")
    return {"success": True, "data": _goal_prediction(user["id"], folder_id)}


@router.put("/folders/{folder_id}/learning/goal")
async def save_learning_goal(
    folder_id: int,
    req: LearningGoalRequest,
    user: dict = Depends(get_current_user),
):
    if not get_video_folder(user["id"], folder_id):
        raise HTTPException(status_code=404, detail="目录不存在")
    if req.exam_date:
        try:
            date.fromisoformat(req.exam_date)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="考试日期格式不正确") from exc
    upsert_learning_goal(
        user["id"], folder_id, exam_date=req.exam_date,
        target_score=req.target_score, daily_minutes=req.daily_minutes,
    )
    return {"success": True, "data": _goal_prediction(user["id"], folder_id)}


@router.get("/folders/{folder_id}/learning/knowledge-graph")
async def knowledge_graph(folder_id: int, user: dict = Depends(get_current_user)):
    if not get_video_folder(user["id"], folder_id):
        raise HTTPException(status_code=404, detail="目录不存在")
    mastery = list_knowledge_mastery(user["id"], folder_id)
    points = [item["knowledge_point"] for item in mastery]
    if not points:
        points = [
            item["knowledge_point"]
            for item in list_question_bank(user["id"], folder_id, limit=100)
        ]
    relations = list_knowledge_relations(user["id"], folder_id)
    if points and not relations:
        relations = rebuild_knowledge_relations(user["id"], folder_id, points)
    mastery_map = {item["knowledge_point"]: item for item in mastery}
    nodes = [{
        "id": point, "label": point,
        "mastery_score": float(mastery_map.get(point, {}).get("mastery_score", 0)),
        "attempts": int(mastery_map.get(point, {}).get("attempts", 0)),
    } for point in dict.fromkeys(points)]
    edges = [{
        "source": item["source_point"], "target": item["target_point"],
        "relation": item["relation"],
    } for item in relations]
    return {"success": True, "data": {"nodes": nodes, "edges": edges}}


@router.get("/folders/{folder_id}/learning/diagnoses")
async def mistake_diagnoses(folder_id: int, user: dict = Depends(get_current_user)):
    if not get_video_folder(user["id"], folder_id):
        raise HTTPException(status_code=404, detail="目录不存在")
    return {"success": True, "data": list_mistake_diagnoses(user["id"], folder_id)}


@router.post("/folders/{folder_id}/learning/diagnose")
async def ai_mistake_diagnosis(
    folder_id: int,
    req: MistakeDiagnosisRequest,
    user: dict = Depends(get_current_user),
):
    items = list_question_bank(user["id"], folder_id, limit=500)
    item = next((row for row in items if row["id"] == req.question_bank_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="题目不存在")
    from api_summarize import _get_summarizer
    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, _get_summarizer("diagnosis").diagnose_mistake, item["question"], req.answer
        )
    except Exception:
        category, diagnosis, action = _diagnose_mistake(item["question"], req.answer)
        result = {"category": category, "diagnosis": diagnosis, "action": action}
    saved = upsert_mistake_diagnosis(
        user["id"], folder_id, item["id"], result["category"],
        result["diagnosis"], result["action"],
    )
    return {"success": True, "data": saved}


@router.post("/folders/batch-import")
async def batch_import_courses(
    req: BatchImportRequest,
    user: dict = Depends(get_current_user),
):
    _ensure_parent(user["id"], req.parent_id)
    folder_id = req.parent_id
    if req.folder_name and req.folder_name.strip():
        name = _clean_folder_name(req.folder_name)
        existing = next((
            folder for folder in list_video_folders(user["id"])
            if folder["parent_id"] == req.parent_id and folder["name"].casefold() == name.casefold()
        ), None)
        folder = existing or create_video_folder(user["id"], name, req.parent_id)
        folder_id = folder["id"]
    imported = []
    rejected = []
    warnings = []
    loop = asyncio.get_running_loop()
    for raw_url in req.urls[:200]:
        url = str(raw_url or "").strip()
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https", "local"} or not url:
            rejected.append(url)
            continue
        candidates = []
        if req.expand_playlists and _looks_like_playlist(url):
            try:
                candidates = await loop.run_in_executor(None, _expand_playlist_url, url)
                if not candidates:
                    warnings.append(f"播放列表未返回条目，已保留原链接：{url}")
            except Exception as exc:
                warnings.append(f"播放列表展开失败，已保留原链接：{exc}")
        if not candidates:
            title = parsed.path.rstrip("/").split("/")[-1] or parsed.netloc or "待解析视频"
            candidates = [{
                "url": url, "title": title[:200],
                "platform": parsed.netloc.removeprefix("www."),
            }]
        for candidate in candidates:
            item_url = candidate.pop("url")
            video = upsert_library_video(user["id"], item_url, candidate)
            if folder_id is not None:
                video = move_library_video(user["id"], video["id"], folder_id) or video
            imported.append(video)
    pipeline_job = None
    if folder_id is not None and imported:
        from learning_efficiency import create_processing_job

        pipeline_job = create_processing_job(
            user["id"], folder_id, [item["id"] for item in imported], 50, True, False,
        )
        from api_efficiency import _schedule_pipeline

        _schedule_pipeline(pipeline_job, user["id"], folder_id, True, False)
    return {
        "success": True,
        "data": {
            "folder_id": folder_id, "imported": imported,
            "rejected": rejected, "warnings": warnings, "pipeline_job": pipeline_job,
        },
    }
