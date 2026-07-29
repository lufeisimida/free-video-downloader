"""Persistent daily reminder dispatcher for browser, email and WeCom channels."""

from __future__ import annotations

import asyncio
import os
from datetime import datetime

from database import get_db
from learning_efficiency import (
    create_reminder_delivery,
    due_reminder_preferences,
    mark_reminder_notified,
    send_email_reminder,
    send_wecom_reminder,
    update_reminder_delivery,
)


def _learning_counts(user_id: int) -> tuple[int, int, int]:
    now = datetime.now().astimezone().isoformat()
    with get_db() as conn:
        folders = conn.execute(
            "SELECT COUNT(*) count FROM video_folders WHERE user_id=?", (user_id,)
        ).fetchone()["count"]
        wrong = conn.execute(
            "SELECT COUNT(*) count FROM wrong_question_reviews WHERE user_id=? AND due_at<=?",
            (user_id, now),
        ).fetchone()["count"]
        cards = conn.execute(
            "SELECT COUNT(*) count FROM flashcards WHERE user_id=? AND due_at<=?",
            (user_id, now),
        ).fetchone()["count"]
    return int(folders), int(wrong), int(cards)


def dispatch_due_reminders(now: datetime | None = None) -> int:
    dispatched = 0
    for preference in due_reminder_preferences(now):
        user_id = int(preference["user_id"])
        folders, wrong, cards = _learning_counts(user_id)
        title = "今日学习任务已就绪"
        body = f"你有 {wrong} 道到期错题、{cards} 张到期闪卡，覆盖 {folders} 个课程目录。打开连续学习即可开始。"
        channels_created = 0
        if preference.get("browser_enabled"):
            create_reminder_delivery(user_id, "browser", title, body)
            channels_created += 1
        if preference.get("email_enabled"):
            delivery = create_reminder_delivery(user_id, "email", title, body)
            try:
                send_email_reminder(preference["email"], title, body)
                update_reminder_delivery(delivery["id"], "sent")
            except Exception as exc:
                update_reminder_delivery(delivery["id"], "failed", str(exc))
            channels_created += 1
        if preference.get("wecom_enabled"):
            delivery = create_reminder_delivery(user_id, "wecom", title, body)
            try:
                send_wecom_reminder(title, body)
                update_reminder_delivery(delivery["id"], "sent")
            except Exception as exc:
                update_reminder_delivery(delivery["id"], "failed", str(exc))
            channels_created += 1
        if channels_created and not preference.get("browser_enabled"):
            mark_reminder_notified(user_id)
        dispatched += channels_created
    return dispatched


async def reminder_scheduler_loop() -> None:
    interval = max(15, int(os.getenv("REMINDER_POLL_SECONDS", "60")))
    while True:
        try:
            await asyncio.to_thread(dispatch_due_reminders)
        except Exception:
            pass
        await asyncio.sleep(interval)
