"""Persistence and deterministic services for the learning-efficiency features."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import smtplib
import time
from collections import Counter
from datetime import date, datetime, timezone
from difflib import SequenceMatcher
from email.message import EmailMessage
from typing import Iterable

import httpx

from database import get_db


VECTOR_DIMENSIONS = 384
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small").strip()
EMBEDDING_DIMENSIONS = max(64, int(os.getenv("EMBEDDING_DIMENSIONS", "384")))


def _add_column_if_missing(conn, table: str, definition: str) -> None:
    column = definition.split()[0]
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")


def init_efficiency_db() -> None:
    with get_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS processing_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                folder_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued',
                stage TEXT NOT NULL DEFAULT 'queued',
                priority INTEGER NOT NULL DEFAULT 50,
                progress REAL NOT NULL DEFAULT 0,
                total_items INTEGER NOT NULL DEFAULT 0,
                completed_items INTEGER NOT NULL DEFAULT 0,
                error TEXT NOT NULL DEFAULT '',
                created_at TEXT DEFAULT (datetime('now')),
                started_at TEXT,
                finished_at TEXT,
                updated_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (folder_id) REFERENCES video_folders(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS processing_job_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL,
                video_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued',
                stage TEXT NOT NULL DEFAULT 'queued',
                progress REAL NOT NULL DEFAULT 0,
                error TEXT NOT NULL DEFAULT '',
                updated_at TEXT DEFAULT (datetime('now')),
                UNIQUE(job_id, video_id),
                FOREIGN KEY (job_id) REFERENCES processing_jobs(id) ON DELETE CASCADE,
                FOREIGN KEY (video_id) REFERENCES library_videos(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS course_chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                folder_id INTEGER NOT NULL,
                video_id INTEGER,
                material_id INTEGER,
                source_type TEXT NOT NULL DEFAULT 'video',
                source_title TEXT NOT NULL DEFAULT '',
                source_url TEXT NOT NULL DEFAULT '',
                start_seconds REAL NOT NULL DEFAULT 0,
                end_seconds REAL NOT NULL DEFAULT 0,
                content TEXT NOT NULL,
                vector_json TEXT NOT NULL DEFAULT '{}',
                fingerprint TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(user_id, folder_id, fingerprint),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (folder_id) REFERENCES video_folders(id) ON DELETE CASCADE,
                FOREIGN KEY (video_id) REFERENCES library_videos(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS learning_materials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                folder_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                material_type TEXT NOT NULL,
                source_url TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'ready',
                error TEXT NOT NULL DEFAULT '',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (folder_id) REFERENCES video_folders(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS reminder_preferences (
                user_id INTEGER PRIMARY KEY,
                enabled INTEGER NOT NULL DEFAULT 0,
                reminder_time TEXT NOT NULL DEFAULT '20:00',
                browser_enabled INTEGER NOT NULL DEFAULT 1,
                email_enabled INTEGER NOT NULL DEFAULT 0,
                wecom_enabled INTEGER NOT NULL DEFAULT 0,
                last_notified_date TEXT,
                updated_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS reminder_deliveries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                channel TEXT NOT NULL,
                reminder_date TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                error TEXT NOT NULL DEFAULT '',
                created_at TEXT DEFAULT (datetime('now')),
                sent_at TEXT,
                UNIQUE(user_id, channel, reminder_date),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS knowledge_point_aliases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                folder_id INTEGER NOT NULL,
                alias TEXT NOT NULL,
                canonical TEXT NOT NULL,
                similarity REAL NOT NULL DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(user_id, folder_id, alias),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (folder_id) REFERENCES video_folders(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS question_quality (
                question_bank_id INTEGER PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'review',
                quality_score REAL NOT NULL DEFAULT 0,
                duplicate_score REAL NOT NULL DEFAULT 0,
                evidence_score REAL NOT NULL DEFAULT 0,
                answer_score REAL NOT NULL DEFAULT 0,
                issues_json TEXT NOT NULL DEFAULT '[]',
                checked_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (question_bank_id) REFERENCES question_bank(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS model_usage_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                operation TEXT NOT NULL,
                model TEXT NOT NULL DEFAULT '',
                input_tokens INTEGER NOT NULL DEFAULT 0,
                output_tokens INTEGER NOT NULL DEFAULT 0,
                estimated_cost REAL NOT NULL DEFAULT 0,
                latency_ms INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'success',
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
            );
            CREATE INDEX IF NOT EXISTS idx_processing_jobs_user_folder
                ON processing_jobs(user_id, folder_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_processing_items_job
                ON processing_job_items(job_id, status);
            CREATE INDEX IF NOT EXISTS idx_course_chunks_folder
                ON course_chunks(user_id, folder_id, source_type);
            CREATE INDEX IF NOT EXISTS idx_materials_folder
                ON learning_materials(user_id, folder_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_aliases_folder
                ON knowledge_point_aliases(user_id, folder_id, canonical);
            CREATE INDEX IF NOT EXISTS idx_usage_date
                ON model_usage_logs(user_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_reminder_deliveries
                ON reminder_deliveries(user_id, reminder_date, status);
            """
        )
        _add_column_if_missing(conn, "processing_jobs", "generate_questions INTEGER NOT NULL DEFAULT 1")
        _add_column_if_missing(conn, "processing_jobs", "force INTEGER NOT NULL DEFAULT 0")
        _add_column_if_missing(conn, "course_chunks", "embedding_model TEXT NOT NULL DEFAULT ''")
        _add_column_if_missing(conn, "reminder_preferences", "wecom_enabled INTEGER NOT NULL DEFAULT 0")
        _add_column_if_missing(conn, "question_quality", "scope_score REAL NOT NULL DEFAULT 0")
        _add_column_if_missing(conn, "question_quality", "ambiguity_score REAL NOT NULL DEFAULT 0")
        # A process that died mid-job must not leave an unrecoverable state.
        conn.execute(
            "UPDATE processing_jobs SET status='queued', stage='queued', "
            "error='服务重启，等待重试', updated_at=datetime('now') "
            "WHERE status='running'"
        )
        conn.execute(
            "UPDATE processing_job_items SET status='queued', stage='queued', "
            "updated_at=datetime('now') WHERE status='running'"
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def tokenize(text: str) -> list[str]:
    value = str(text or "").casefold()
    latin = re.findall(r"[a-z0-9_+#.-]{2,}", value)
    chinese = re.findall(r"[\u4e00-\u9fff]", value)
    pairs = ["".join(chinese[index:index + 2]) for index in range(len(chinese) - 1)]
    return latin + chinese + pairs


def vectorize(text: str) -> dict[str, float]:
    """Deterministic lexical fallback used only when no embedding API is configured."""
    counts = Counter(tokenize(text))
    vector: dict[str, float] = {}
    for token, count in counts.items():
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=4).digest()
        index = int.from_bytes(digest, "big") % VECTOR_DIMENSIONS
        key = str(index)
        vector[key] = vector.get(key, 0.0) + 1.0 + math.log(count)
    norm = math.sqrt(sum(value * value for value in vector.values())) or 1.0
    return {key: round(value / norm, 6) for key, value in vector.items()}


def _embedding_config() -> dict:
    try:
        from api_model_config import get_resolved_model_config

        resolved = get_resolved_model_config()
    except Exception:
        resolved = {}
    reuse_llm = os.getenv("EMBEDDING_REUSE_LLM", "false").strip().lower() in {"1", "true", "yes", "on"}
    base_url = (os.getenv("EMBEDDING_BASE_URL") or (resolved.get("base_url") if reuse_llm else "") or "").rstrip("/")
    api_key = os.getenv("EMBEDDING_API_KEY") or (resolved.get("api_key") if reuse_llm else "") or ""
    model = os.getenv("EMBEDDING_MODEL") or EMBEDDING_MODEL
    return {"base_url": base_url, "api_key": api_key, "model": model}


def embed_texts(texts: list[str]) -> tuple[list[list[float]] | None, str]:
    """Create neural embeddings through an OpenAI-compatible endpoint."""
    if not texts:
        return [], EMBEDDING_MODEL
    config = _embedding_config()
    if not config["base_url"] or not config["api_key"]:
        return None, "lexical-fallback"
    started = time.perf_counter()
    status = "success"
    try:
        response = httpx.post(
            f"{config['base_url']}/embeddings",
            headers={"Authorization": f"Bearer {config['api_key']}", "Content-Type": "application/json"},
            json={"model": config["model"], "input": texts, "dimensions": EMBEDDING_DIMENSIONS},
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()
        ordered = sorted(payload.get("data") or [], key=lambda item: item.get("index", 0))
        vectors = [item.get("embedding") or [] for item in ordered]
        if len(vectors) != len(texts) or any(not vector for vector in vectors):
            raise ValueError("Embedding API 返回数据不完整")
        usage = payload.get("usage") or {}
        record_model_usage(
            None, "embedding", config["model"], int(usage.get("prompt_tokens") or 0), 0,
            round((time.perf_counter() - started) * 1000), status,
        )
        return vectors, config["model"]
    except Exception:
        status = "failed"
        record_model_usage(
            None, "embedding", config["model"], sum(len(text) for text in texts) // 4, 0,
            round((time.perf_counter() - started) * 1000), status,
        )
        return None, "lexical-fallback"


def cosine(left, right) -> float:
    if isinstance(left, dict) and isinstance(right, dict):
        if len(left) > len(right):
            left, right = right, left
        return sum(value * right.get(key, 0.0) for key, value in left.items())
    if not left or not right or len(left) != len(right):
        return 0.0
    left_norm = math.sqrt(sum(float(value) ** 2 for value in left)) or 1.0
    right_norm = math.sqrt(sum(float(value) ** 2 for value in right)) or 1.0
    return sum(float(a) * float(b) for a, b in zip(left, right)) / (left_norm * right_norm)


def subtitle_chunks(subtitle: dict, max_chars: int = 900) -> list[dict]:
    segments = subtitle.get("segments") or []
    if not segments:
        text = str(subtitle.get("full_text") or "").strip()
        return [{"start": 0, "end": 0, "text": text}] if text else []
    chunks: list[dict] = []
    current: list[str] = []
    start = end = 0.0
    for segment in segments:
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        if not current:
            start = float(segment.get("start") or 0)
        if current and sum(map(len, current)) + len(text) > max_chars:
            chunks.append({"start": start, "end": end, "text": " ".join(current)})
            current = []
            start = float(segment.get("start") or 0)
        current.append(text)
        end = float(segment.get("end") or segment.get("start") or 0)
    if current:
        chunks.append({"start": start, "end": end, "text": " ".join(current)})
    return chunks


def index_source(
    user_id: int,
    folder_id: int,
    *,
    content: str,
    source_title: str,
    source_url: str = "",
    source_type: str = "material",
    video_id: int | None = None,
    material_id: int | None = None,
    timed_chunks: Iterable[dict] | None = None,
) -> int:
    chunks = list(timed_chunks or []) or [
        {"start": 0, "end": 0, "text": content[index:index + 900]}
        for index in range(0, len(content), 800)
    ]
    prepared = []
    for chunk in chunks:
        text = str(chunk.get("text") or "").strip()
        if text:
            prepared.append((chunk, text))
    neural_vectors, model = embed_texts([text for _, text in prepared])
    vectors = neural_vectors or [vectorize(text) for _, text in prepared]
    inserted = 0
    with get_db() as conn:
        for (chunk, text), vector in zip(prepared, vectors):
            fingerprint = hashlib.sha256(
                f"{source_type}|{source_url}|{text}".encode("utf-8")
            ).hexdigest()
            cursor = conn.execute(
                """
                INSERT INTO course_chunks
                (user_id, folder_id, video_id, material_id, source_type,
                 source_title, source_url, start_seconds, end_seconds,
                 content, vector_json, fingerprint, embedding_model)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, folder_id, fingerprint) DO UPDATE SET
                    vector_json=excluded.vector_json, embedding_model=excluded.embedding_model,
                    source_title=excluded.source_title, start_seconds=excluded.start_seconds,
                    end_seconds=excluded.end_seconds
                """,
                (
                    user_id, folder_id, video_id, material_id, source_type,
                    source_title, source_url, float(chunk.get("start") or 0),
                    float(chunk.get("end") or 0), text,
                    json.dumps(vector, separators=(",", ":")), fingerprint, model,
                ),
            )
            inserted += max(cursor.rowcount, 0)
    return inserted


def semantic_search(user_id: int, folder_id: int, query: str, limit: int = 8) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM course_chunks WHERE user_id=? AND folder_id=?",
            (user_id, folder_id),
        ).fetchall()
    if not rows:
        return []
    query_vectors, query_model = embed_texts([query])
    neural_query = query_vectors[0] if query_vectors else None
    lexical_query = vectorize(query)
    results = []
    for row in rows:
        item = dict(row)
        stored = json.loads(item.pop("vector_json") or "{}")
        stored_model = item.get("embedding_model") or "lexical-fallback"
        if neural_query is not None and isinstance(stored, list) and stored_model == query_model:
            score = cosine(neural_query, stored)
            method = "embedding"
        else:
            score = cosine(lexical_query, stored if isinstance(stored, dict) else vectorize(item["content"]))
            method = "lexical-fallback"
        if score <= 0:
            continue
        item["score"] = round(score, 4)
        item["retrieval_method"] = method
        results.append(item)
    return sorted(results, key=lambda item: item["score"], reverse=True)[: max(1, min(limit, 30))]


def create_processing_job(user_id: int, folder_id: int, video_ids: list[int], priority: int = 50,
                          generate_questions: bool = True, force: bool = False) -> dict:
    now = _now()
    with get_db() as conn:
        cursor = conn.execute(
            """INSERT INTO processing_jobs
               (user_id, folder_id, priority, total_items, generate_questions, force, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, folder_id, max(1, min(priority, 100)), len(video_ids),
             int(generate_questions), int(force), now, now),
        )
        job_id = cursor.lastrowid
        conn.executemany(
            "INSERT INTO processing_job_items (job_id, video_id) VALUES (?, ?)",
            [(job_id, video_id) for video_id in video_ids],
        )
    return get_processing_job(user_id, job_id)


def get_processing_job(user_id: int, job_id: int) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM processing_jobs WHERE id=? AND user_id=?", (job_id, user_id)
        ).fetchone()
        if not row:
            return None
        job = dict(row)
        items = conn.execute(
            """SELECT i.*, v.title, v.url FROM processing_job_items i
               JOIN library_videos v ON v.id=i.video_id
               WHERE i.job_id=? ORDER BY i.id""", (job_id,)
        ).fetchall()
        job["items"] = [dict(item) for item in items]
        return job


def list_processing_jobs(user_id: int, folder_id: int) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM processing_jobs WHERE user_id=? AND folder_id=?
               ORDER BY id DESC LIMIT 30""", (user_id, folder_id)
        ).fetchall()
    return [get_processing_job(user_id, row["id"]) for row in rows]


def list_queued_processing_jobs(limit: int = 100) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT id, user_id FROM processing_jobs WHERE status='queued'
               ORDER BY priority DESC, created_at ASC LIMIT ?""", (max(1, min(limit, 500)),)
        ).fetchall()
    return [get_processing_job(row["user_id"], row["id"]) for row in rows]


def update_job(job_id: int, *, status: str | None = None, stage: str | None = None,
               progress: float | None = None, completed_items: int | None = None,
               error: str | None = None) -> None:
    fields = ["updated_at=?"]
    values: list = [_now()]
    for name, value in (("status", status), ("stage", stage), ("progress", progress),
                        ("completed_items", completed_items), ("error", error)):
        if value is not None:
            fields.append(f"{name}=?")
            values.append(value)
    if status == "running":
        fields.append("started_at=COALESCE(started_at, ?)")
        values.append(_now())
    if status in {"completed", "failed"}:
        fields.append("finished_at=?")
        values.append(_now())
    values.append(job_id)
    with get_db() as conn:
        conn.execute(f"UPDATE processing_jobs SET {', '.join(fields)} WHERE id=?", values)


def update_job_item(job_id: int, video_id: int, *, status: str, stage: str,
                    progress: float, error: str = "") -> None:
    with get_db() as conn:
        conn.execute(
            """UPDATE processing_job_items SET status=?, stage=?, progress=?, error=?,
               updated_at=? WHERE job_id=? AND video_id=?""",
            (status, stage, progress, error[:1000], _now(), job_id, video_id),
        )


def create_material(user_id: int, folder_id: int, name: str, material_type: str,
                    content: str, source_url: str = "", status: str = "ready",
                    error: str = "") -> dict:
    with get_db() as conn:
        cursor = conn.execute(
            """INSERT INTO learning_materials
               (user_id, folder_id, name, material_type, source_url, content, status, error)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, folder_id, name[:240], material_type, source_url, content, status, error[:1000]),
        )
        row = conn.execute("SELECT * FROM learning_materials WHERE id=?", (cursor.lastrowid,)).fetchone()
        return dict(row)


def get_material(user_id: int, material_id: int) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM learning_materials WHERE user_id=? AND id=?", (user_id, material_id)
        ).fetchone()
    return dict(row) if row else None


def update_material_status(material_id: int, status: str, error: str = "") -> None:
    with get_db() as conn:
        conn.execute(
            "UPDATE learning_materials SET status=?, error=?, updated_at=? WHERE id=?",
            (status, error[:1000], _now(), material_id),
        )


def list_materials(user_id: int, folder_id: int) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT id, folder_id, name, material_type, source_url, status, error,
                      length(content) AS character_count, created_at
               FROM learning_materials WHERE user_id=? AND folder_id=? ORDER BY id DESC""",
            (user_id, folder_id),
        ).fetchall()
        return [dict(row) for row in rows]


def delete_material(user_id: int, material_id: int) -> bool:
    with get_db() as conn:
        conn.execute("DELETE FROM course_chunks WHERE user_id=? AND material_id=?", (user_id, material_id))
        cursor = conn.execute("DELETE FROM learning_materials WHERE user_id=? AND id=?", (user_id, material_id))
        return cursor.rowcount > 0


def get_reminder_preferences(user_id: int) -> dict:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM reminder_preferences WHERE user_id=?", (user_id,)).fetchone()
        return dict(row) if row else {
            "user_id": user_id, "enabled": 0, "reminder_time": "20:00",
            "browser_enabled": 1, "email_enabled": 0, "wecom_enabled": 0,
            "last_notified_date": None,
        }


def save_reminder_preferences(user_id: int, enabled: bool, reminder_time: str,
                              browser_enabled: bool, email_enabled: bool,
                              wecom_enabled: bool = False) -> dict:
    with get_db() as conn:
        conn.execute(
            """INSERT INTO reminder_preferences
               (user_id, enabled, reminder_time, browser_enabled, email_enabled, wecom_enabled, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET enabled=excluded.enabled,
               reminder_time=excluded.reminder_time, browser_enabled=excluded.browser_enabled,
               email_enabled=excluded.email_enabled, wecom_enabled=excluded.wecom_enabled,
               updated_at=excluded.updated_at""",
            (user_id, int(enabled), reminder_time, int(browser_enabled), int(email_enabled),
             int(wecom_enabled), _now()),
        )
    return get_reminder_preferences(user_id)


def mark_reminder_notified(user_id: int) -> None:
    with get_db() as conn:
        conn.execute(
            "UPDATE reminder_preferences SET last_notified_date=?, updated_at=? WHERE user_id=?",
            (date.today().isoformat(), _now(), user_id),
        )


def due_reminder_preferences(now: datetime | None = None) -> list[dict]:
    current = now or datetime.now().astimezone()
    today = current.date().isoformat()
    current_hm = current.strftime("%H:%M")
    with get_db() as conn:
        rows = conn.execute(
            """SELECT r.*, u.email FROM reminder_preferences r JOIN users u ON u.id=r.user_id
               WHERE r.enabled=1 AND r.reminder_time<=?
               AND COALESCE(r.last_notified_date, '')<>?""",
            (current_hm, today),
        ).fetchall()
    return [dict(row) for row in rows]


def create_reminder_delivery(user_id: int, channel: str, title: str, body: str,
                             reminder_date: str | None = None) -> dict:
    reminder_date = reminder_date or date.today().isoformat()
    with get_db() as conn:
        conn.execute(
            """INSERT INTO reminder_deliveries
               (user_id, channel, reminder_date, title, body)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(user_id, channel, reminder_date) DO UPDATE SET
                   title=excluded.title, body=excluded.body""",
            (user_id, channel, reminder_date, title, body),
        )
        row = conn.execute(
            "SELECT * FROM reminder_deliveries WHERE user_id=? AND channel=? AND reminder_date=?",
            (user_id, channel, reminder_date),
        ).fetchone()
    return dict(row)


def update_reminder_delivery(delivery_id: int, status: str, error: str = "") -> None:
    with get_db() as conn:
        conn.execute(
            """UPDATE reminder_deliveries SET status=?, error=?,
               sent_at=CASE WHEN ?='sent' THEN ? ELSE sent_at END WHERE id=?""",
            (status, error[:1000], status, _now(), delivery_id),
        )


def list_pending_browser_reminders(user_id: int) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM reminder_deliveries WHERE user_id=? AND channel='browser'
               AND status='pending' ORDER BY id""", (user_id,)
        ).fetchall()
    return [dict(row) for row in rows]


def acknowledge_browser_reminders(user_id: int, delivery_ids: list[int]) -> None:
    if not delivery_ids:
        return
    placeholders = ",".join("?" for _ in delivery_ids)
    with get_db() as conn:
        conn.execute(
            f"""UPDATE reminder_deliveries SET status='sent', sent_at=?
                WHERE user_id=? AND channel='browser' AND id IN ({placeholders})""",
            (_now(), user_id, *delivery_ids),
        )
    mark_reminder_notified(user_id)


def send_email_reminder(to_email: str, title: str, body: str) -> None:
    host = os.getenv("SMTP_HOST", "").strip()
    if not host:
        raise RuntimeError("未配置 SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USERNAME", "").strip()
    password = os.getenv("SMTP_PASSWORD", "")
    sender = os.getenv("SMTP_FROM", username).strip()
    if not sender:
        raise RuntimeError("未配置 SMTP_FROM")
    message = EmailMessage()
    message["Subject"] = title
    message["From"] = sender
    message["To"] = to_email
    message.set_content(body)
    with smtplib.SMTP(host, port, timeout=20) as client:
        if os.getenv("SMTP_STARTTLS", "true").strip().lower() in {"1", "true", "yes", "on"}:
            client.starttls()
        if username:
            client.login(username, password)
        client.send_message(message)


def send_wecom_reminder(title: str, body: str) -> None:
    webhook = os.getenv("WECOM_WEBHOOK_URL", "").strip()
    if not webhook:
        raise RuntimeError("未配置 WECOM_WEBHOOK_URL")
    response = httpx.post(webhook, json={"msgtype": "text", "text": {"content": f"{title}\n{body}"}}, timeout=20)
    response.raise_for_status()
    payload = response.json()
    if payload.get("errcode") not in {0, None}:
        raise RuntimeError(payload.get("errmsg") or "企业微信发送失败")


def normalize_knowledge_point(value: str) -> str:
    return re.sub(r"[\s\-_—:：/]+", "", str(value or "").casefold()).strip(".,，。()（）")


def canonicalize_knowledge_point(user_id: int, folder_id: int, value: str) -> str:
    point = str(value or "课程综合").strip()[:80] or "课程综合"
    normalized = normalize_knowledge_point(point)
    with get_db() as conn:
        alias = conn.execute(
            "SELECT canonical FROM knowledge_point_aliases WHERE user_id=? AND folder_id=? AND alias=?",
            (user_id, folder_id, normalized),
        ).fetchone()
        if alias:
            return alias["canonical"]
        rows = conn.execute(
            """SELECT knowledge_point FROM question_bank WHERE user_id=? AND folder_id=?
               UNION SELECT canonical AS knowledge_point FROM knowledge_point_aliases
               WHERE user_id=? AND folder_id=?""",
            (user_id, folder_id, user_id, folder_id),
        ).fetchall()
        best = point
        best_score = 0.0
        point_tokens = set(tokenize(point))
        for row in rows:
            candidate = row["knowledge_point"]
            candidate_normalized = normalize_knowledge_point(candidate)
            exact = normalized == candidate_normalized
            candidate_tokens = set(tokenize(candidate))
            jaccard = len(point_tokens & candidate_tokens) / max(len(point_tokens | candidate_tokens), 1)
            score = 1.0 if exact else max(jaccard, SequenceMatcher(None, normalized, candidate_normalized).ratio())
            if score > best_score:
                best, best_score = candidate, score
        if best_score >= 0.82 and best != point:
            conn.execute(
                """INSERT OR REPLACE INTO knowledge_point_aliases
                   (user_id, folder_id, alias, canonical, similarity) VALUES (?, ?, ?, ?, ?)""",
                (user_id, folder_id, normalized, best, round(best_score, 4)),
            )
            return best
    return point


def list_knowledge_aliases(user_id: int, folder_id: int) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM knowledge_point_aliases WHERE user_id=? AND folder_id=? ORDER BY canonical, alias",
            (user_id, folder_id),
        ).fetchall()
        return [dict(row) for row in rows]


def deduplicate_knowledge_points(user_id: int, folder_id: int) -> dict:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT knowledge_point FROM question_bank WHERE user_id=? AND folder_id=?",
            (user_id, folder_id),
        ).fetchall()
    merged = 0
    for row in rows:
        original = row["knowledge_point"]
        canonical = canonicalize_knowledge_point(user_id, folder_id, original)
        if canonical == original:
            continue
        with get_db() as conn:
            conn.execute(
                "UPDATE question_bank SET knowledge_point=? WHERE user_id=? AND folder_id=? AND knowledge_point=?",
                (canonical, user_id, folder_id, original),
            )
            conn.execute(
                "UPDATE flashcards SET knowledge_point=? WHERE user_id=? AND folder_id=? AND knowledge_point=?",
                (canonical, user_id, folder_id, original),
            )
            old = conn.execute(
                "SELECT * FROM knowledge_mastery WHERE user_id=? AND folder_id=? AND knowledge_point=?",
                (user_id, folder_id, original),
            ).fetchone()
            target = conn.execute(
                "SELECT * FROM knowledge_mastery WHERE user_id=? AND folder_id=? AND knowledge_point=?",
                (user_id, folder_id, canonical),
            ).fetchone()
            if old and target:
                attempts = old["attempts"] + target["attempts"]
                earned = old["earned_points"] + target["earned_points"]
                possible = old["possible_points"] + target["possible_points"]
                conn.execute(
                    """UPDATE knowledge_mastery SET attempts=?, correct_count=?, earned_points=?,
                       possible_points=?, mastery_score=?, updated_at=? WHERE id=?""",
                    (attempts, old["correct_count"] + target["correct_count"], earned, possible,
                     round(earned * 100 / possible, 2) if possible else 0, _now(), target["id"]),
                )
                conn.execute("DELETE FROM knowledge_mastery WHERE id=?", (old["id"],))
            elif old:
                conn.execute("UPDATE knowledge_mastery SET knowledge_point=? WHERE id=?", (canonical, old["id"]))
        merged += 1
    return {"merged": merged, "aliases": list_knowledge_aliases(user_id, folder_id)}


def assess_question_quality(question: dict, existing_questions: Iterable[dict] = (),
                            source_text: str = "") -> dict:
    text = str(question.get("question") or "").strip()
    evidence = str(question.get("evidence_quote") or "").strip()
    question_type = question.get("type")
    answer = question.get("reference_answer") if question_type in {"short_answer", "analysis"} else question.get("answer")
    issues: list[str] = []
    evidence_score = 1.0 if len(evidence) >= 8 else 0.4 if evidence else 0.0
    if evidence_score == 0:
        issues.append("缺少课程证据")
    answer_score = 1.0 if answer and (not isinstance(answer, list) or len(answer) > 0) else 0.0
    if answer_score == 0:
        issues.append("缺少有效答案")
    options = question.get("options") or []
    option_keys = {str(item.get("key")) for item in options if isinstance(item, dict)}
    ambiguity_score = 0.0
    if question_type in {"single", "true_false"}:
        selected = answer if isinstance(answer, list) else [answer] if answer else []
        if len(selected) != 1 or (option_keys and str(selected[0]) not in option_keys):
            ambiguity_score = 1.0
            issues.append("答案不唯一或不在选项中")
    elif question_type == "multiple":
        selected = answer if isinstance(answer, list) else []
        if not selected or len(set(map(str, selected))) != len(selected) or (option_keys and not set(map(str, selected)) <= option_keys):
            ambiguity_score = 1.0
            issues.append("多选答案集合无效")
    if len(text) < 6:
        issues.append("题干过短")
    duplicate_score = 0.0
    normalized = normalize_knowledge_point(text)
    for item in existing_questions:
        other_value = item.get("question")
        other = other_value if isinstance(other_value, str) else (other_value or {}).get("question", "")
        duplicate_score = max(duplicate_score, SequenceMatcher(None, normalized, normalize_knowledge_point(other)).ratio())
    if duplicate_score >= 0.9:
        issues.append("与题库已有题目高度重复")
    scope_score = 1.0
    if source_text:
        normalized_source = normalize_knowledge_point(source_text)
        normalized_evidence = normalize_knowledge_point(evidence)
        scope_score = 1.0 if normalized_evidence and normalized_evidence in normalized_source else 0.0
        if scope_score == 0:
            issues.append("证据不在课程资料范围内")
    clarity = 1.0 if 6 <= len(text) <= 500 else 0.4
    quality = round((evidence_score * 0.22 + answer_score * 0.25 + clarity * 0.18 +
                     (1 - duplicate_score) * 0.12 + scope_score * 0.15 +
                     (1 - ambiguity_score) * 0.08) * 100, 1)
    hard_failure = answer_score == 0 or len(text) < 3 or ambiguity_score > 0 or scope_score == 0 or evidence_score == 0
    status = "rejected" if hard_failure or duplicate_score >= 0.9 else "approved" if quality >= 75 else "review"
    return {
        "status": status, "quality_score": quality,
        "duplicate_score": round(duplicate_score, 4),
        "evidence_score": evidence_score, "answer_score": answer_score,
        "scope_score": scope_score, "ambiguity_score": ambiguity_score,
        "issues": issues,
    }


def save_question_quality(question_bank_id: int, quality: dict) -> None:
    with get_db() as conn:
        conn.execute(
            """INSERT INTO question_quality
               (question_bank_id, status, quality_score, duplicate_score,
                evidence_score, answer_score, scope_score, ambiguity_score, issues_json, checked_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(question_bank_id) DO UPDATE SET status=excluded.status,
               quality_score=excluded.quality_score, duplicate_score=excluded.duplicate_score,
               evidence_score=excluded.evidence_score, answer_score=excluded.answer_score,
               scope_score=excluded.scope_score, ambiguity_score=excluded.ambiguity_score,
               issues_json=excluded.issues_json, checked_at=excluded.checked_at""",
            (question_bank_id, quality["status"], quality["quality_score"], quality["duplicate_score"],
             quality["evidence_score"], quality["answer_score"], quality.get("scope_score", 0),
             quality.get("ambiguity_score", 0), json.dumps(quality["issues"], ensure_ascii=False), _now()),
        )


def list_question_quality(user_id: int, folder_id: int) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT q.*, qb.knowledge_point, qb.question_json FROM question_quality q
               JOIN question_bank qb ON qb.id=q.question_bank_id
               WHERE qb.user_id=? AND qb.folder_id=? ORDER BY q.quality_score, q.question_bank_id""",
            (user_id, folder_id),
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["issues"] = json.loads(item.pop("issues_json") or "[]")
        item["question"] = json.loads(item.pop("question_json") or "{}")
        result.append(item)
    return result


def record_model_usage(user_id: int | None, operation: str, model: str,
                       input_tokens: int, output_tokens: int, latency_ms: int,
                       status: str = "success") -> None:
    input_rate = 0.15 / 1_000_000
    output_rate = 0.60 / 1_000_000
    cost = input_tokens * input_rate + output_tokens * output_rate
    try:
        with get_db() as conn:
            conn.execute(
                """INSERT INTO model_usage_logs
                   (user_id, operation, model, input_tokens, output_tokens,
                    estimated_cost, latency_ms, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (user_id, operation[:80], model[:120], max(input_tokens, 0), max(output_tokens, 0),
                 round(cost, 8), max(latency_ms, 0), status),
            )
    except Exception:
        # Usage telemetry must never break the model call.
        pass


def usage_summary(user_id: int, days: int = 30) -> dict:
    days = max(1, min(days, 365))
    with get_db() as conn:
        rows = conn.execute(
            """SELECT substr(created_at, 1, 10) AS day, COUNT(*) AS requests,
                      SUM(input_tokens) AS input_tokens, SUM(output_tokens) AS output_tokens,
                      SUM(estimated_cost) AS estimated_cost, AVG(latency_ms) AS avg_latency_ms,
                      SUM(CASE WHEN status!='success' THEN 1 ELSE 0 END) AS failures
               FROM model_usage_logs
               WHERE (user_id=? OR user_id IS NULL) AND created_at >= datetime('now', ?)
               GROUP BY substr(created_at, 1, 10) ORDER BY day""",
            (user_id, f"-{days - 1} days"),
        ).fetchall()
    daily = [dict(row) for row in rows]
    return {
        "days": days,
        "daily": daily,
        "totals": {
            "requests": sum(int(row["requests"] or 0) for row in daily),
            "input_tokens": sum(int(row["input_tokens"] or 0) for row in daily),
            "output_tokens": sum(int(row["output_tokens"] or 0) for row in daily),
            "estimated_cost": round(sum(float(row["estimated_cost"] or 0) for row in daily), 6),
            "failures": sum(int(row["failures"] or 0) for row in daily),
        },
    }
