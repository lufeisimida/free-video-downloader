import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "app.db")


def get_db_path():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    return DB_PATH


@contextmanager
def get_db():
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """初始化数据库表结构"""
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                is_vip INTEGER DEFAULT 0,
                vip_expire_at TEXT,
                daily_summary_count INTEGER DEFAULT 0,
                last_summary_date TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_no TEXT UNIQUE NOT NULL,
                user_id INTEGER NOT NULL,
                amount INTEGER NOT NULL,
                currency TEXT DEFAULT 'cny',
                status TEXT DEFAULT 'pending',
                plan_type TEXT DEFAULT 'monthly',
                stripe_session_id TEXT UNIQUE,
                stripe_payment_intent_id TEXT,
                paid_at TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS model_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                base_url TEXT NOT NULL,
                model TEXT NOT NULL,
                api_key TEXT NOT NULL DEFAULT '',
                is_active INTEGER NOT NULL DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS video_folders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                parent_id INTEGER,
                name TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (parent_id) REFERENCES video_folders(id) ON DELETE RESTRICT
            );

            CREATE TABLE IF NOT EXISTS library_videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                folder_id INTEGER,
                url TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                thumbnail TEXT NOT NULL DEFAULT '',
                platform TEXT NOT NULL DEFAULT '',
                uploader TEXT NOT NULL DEFAULT '',
                duration_string TEXT NOT NULL DEFAULT '',
                parsed_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')),
                UNIQUE(user_id, url),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (folder_id) REFERENCES video_folders(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS course_quizzes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                folder_id INTEGER NOT NULL,
                quiz_json TEXT NOT NULL,
                source_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (folder_id) REFERENCES video_folders(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS question_bank (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                folder_id INTEGER NOT NULL,
                fingerprint TEXT NOT NULL,
                question_json TEXT NOT NULL,
                knowledge_point TEXT NOT NULL DEFAULT '课程综合',
                source_video_title TEXT NOT NULL DEFAULT '',
                source_video_url TEXT NOT NULL DEFAULT '',
                evidence_quote TEXT NOT NULL DEFAULT '',
                evidence_time_seconds REAL NOT NULL DEFAULT 0,
                times_used INTEGER NOT NULL DEFAULT 0,
                correct_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')),
                UNIQUE(user_id, folder_id, fingerprint),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (folder_id) REFERENCES video_folders(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS quiz_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                folder_id INTEGER NOT NULL,
                quiz_id INTEGER,
                mode TEXT NOT NULL DEFAULT 'standard',
                phase TEXT NOT NULL DEFAULT 'practice',
                total_score REAL NOT NULL DEFAULT 0,
                max_score REAL NOT NULL DEFAULT 0,
                answers_json TEXT NOT NULL DEFAULT '{}',
                results_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (folder_id) REFERENCES video_folders(id) ON DELETE CASCADE,
                FOREIGN KEY (quiz_id) REFERENCES course_quizzes(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS knowledge_mastery (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                folder_id INTEGER NOT NULL,
                knowledge_point TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                correct_count INTEGER NOT NULL DEFAULT 0,
                earned_points REAL NOT NULL DEFAULT 0,
                possible_points REAL NOT NULL DEFAULT 0,
                mastery_score REAL NOT NULL DEFAULT 0,
                updated_at TEXT DEFAULT (datetime('now')),
                UNIQUE(user_id, folder_id, knowledge_point),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (folder_id) REFERENCES video_folders(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS wrong_question_reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                folder_id INTEGER NOT NULL,
                question_bank_id INTEGER NOT NULL,
                stage INTEGER NOT NULL DEFAULT 0,
                review_count INTEGER NOT NULL DEFAULT 0,
                due_at TEXT,
                last_correct INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT DEFAULT (datetime('now')),
                UNIQUE(user_id, question_bank_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (folder_id) REFERENCES video_folders(id) ON DELETE CASCADE,
                FOREIGN KEY (question_bank_id) REFERENCES question_bank(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS flashcards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                folder_id INTEGER NOT NULL,
                knowledge_point TEXT NOT NULL DEFAULT '课程综合',
                front TEXT NOT NULL,
                back TEXT NOT NULL,
                source_video_title TEXT NOT NULL DEFAULT '',
                source_video_url TEXT NOT NULL DEFAULT '',
                evidence_time_seconds REAL NOT NULL DEFAULT 0,
                stage INTEGER NOT NULL DEFAULT 0,
                review_count INTEGER NOT NULL DEFAULT 0,
                due_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')),
                UNIQUE(user_id, folder_id, front),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (folder_id) REFERENCES video_folders(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS video_learning_progress (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                video_id INTEGER NOT NULL,
                progress_seconds REAL NOT NULL DEFAULT 0,
                duration_seconds REAL NOT NULL DEFAULT 0,
                completion_percent REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'not_started',
                last_studied_at TEXT,
                updated_at TEXT DEFAULT (datetime('now')),
                UNIQUE(user_id, video_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (video_id) REFERENCES library_videos(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS video_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                folder_id INTEGER,
                video_id INTEGER NOT NULL,
                time_seconds REAL NOT NULL DEFAULT 0,
                content TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (folder_id) REFERENCES video_folders(id) ON DELETE SET NULL,
                FOREIGN KEY (video_id) REFERENCES library_videos(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS learning_goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                folder_id INTEGER NOT NULL,
                exam_date TEXT,
                target_score REAL NOT NULL DEFAULT 80,
                daily_minutes INTEGER NOT NULL DEFAULT 30,
                updated_at TEXT DEFAULT (datetime('now')),
                UNIQUE(user_id, folder_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (folder_id) REFERENCES video_folders(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS daily_task_completions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                folder_id INTEGER NOT NULL,
                task_date TEXT NOT NULL,
                task_key TEXT NOT NULL,
                completed_at TEXT DEFAULT (datetime('now')),
                UNIQUE(user_id, folder_id, task_date, task_key),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (folder_id) REFERENCES video_folders(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS mistake_diagnoses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                folder_id INTEGER NOT NULL,
                question_bank_id INTEGER NOT NULL,
                category TEXT NOT NULL,
                diagnosis TEXT NOT NULL,
                action TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')),
                UNIQUE(user_id, question_bank_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (folder_id) REFERENCES video_folders(id) ON DELETE CASCADE,
                FOREIGN KEY (question_bank_id) REFERENCES question_bank(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS knowledge_relations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                folder_id INTEGER NOT NULL,
                source_point TEXT NOT NULL,
                target_point TEXT NOT NULL,
                relation TEXT NOT NULL DEFAULT 'prerequisite',
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(user_id, folder_id, source_point, target_point),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (folder_id) REFERENCES video_folders(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
            CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id);
            CREATE INDEX IF NOT EXISTS idx_orders_order_no ON orders(order_no);
            CREATE INDEX IF NOT EXISTS idx_orders_stripe_session_id ON orders(stripe_session_id);
            CREATE INDEX IF NOT EXISTS idx_model_profiles_active ON model_profiles(is_active);
            CREATE INDEX IF NOT EXISTS idx_video_folders_user_parent ON video_folders(user_id, parent_id);
            CREATE INDEX IF NOT EXISTS idx_library_videos_user_folder ON library_videos(user_id, folder_id);
            CREATE INDEX IF NOT EXISTS idx_course_quizzes_user_folder ON course_quizzes(user_id, folder_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_question_bank_user_folder ON question_bank(user_id, folder_id, knowledge_point);
            CREATE INDEX IF NOT EXISTS idx_quiz_attempts_user_folder ON quiz_attempts(user_id, folder_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_mastery_user_folder ON knowledge_mastery(user_id, folder_id, mastery_score);
            CREATE INDEX IF NOT EXISTS idx_wrong_reviews_due ON wrong_question_reviews(user_id, folder_id, due_at);
            CREATE INDEX IF NOT EXISTS idx_flashcards_due ON flashcards(user_id, folder_id, due_at);
            CREATE INDEX IF NOT EXISTS idx_video_progress_user ON video_learning_progress(user_id, updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_video_notes_folder ON video_notes(user_id, folder_id, video_id, time_seconds);
            CREATE INDEX IF NOT EXISTS idx_daily_tasks ON daily_task_completions(user_id, folder_id, task_date);
            CREATE INDEX IF NOT EXISTS idx_diagnoses_folder ON mistake_diagnoses(user_id, folder_id);
            CREATE INDEX IF NOT EXISTS idx_knowledge_relations_folder ON knowledge_relations(user_id, folder_id);
        """)
    # Efficiency tables live in a separate module to keep this core schema readable.
    # Import lazily so tests that redirect DB_PATH receive the complete schema too.
    from learning_efficiency import init_efficiency_db
    init_efficiency_db()


FREE_DAILY_SUMMARY_LIMIT = 3


def get_user_by_email(email: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return dict(row) if row else None


def get_user_by_id(user_id: int) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None


def create_user(email: str, password_hash: str) -> dict:
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO users (email, password_hash) VALUES (?, ?)",
            (email, password_hash),
        )
        return {"id": cursor.lastrowid, "email": email}


def update_user_password(user_id: int, password_hash: str) -> None:
    with get_db() as conn:
        conn.execute(
            "UPDATE users SET password_hash = ?, updated_at = datetime('now') WHERE id = ?",
            (password_hash, user_id),
        )


def list_video_folders(user_id: int) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM video_folders WHERE user_id = ? ORDER BY name COLLATE NOCASE, id",
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def get_video_folder(user_id: int, folder_id: int) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM video_folders WHERE id = ? AND user_id = ?",
            (folder_id, user_id),
        ).fetchone()
        return dict(row) if row else None


def create_video_folder(user_id: int, name: str, parent_id: int | None = None) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO video_folders (user_id, parent_id, name, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, parent_id, name, now, now),
        )
        row = conn.execute("SELECT * FROM video_folders WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return dict(row)


def update_video_folder(
    user_id: int,
    folder_id: int,
    *,
    name: str | None = None,
    parent_id: int | None = None,
    update_parent: bool = False,
) -> dict | None:
    existing = get_video_folder(user_id, folder_id)
    if not existing:
        return None
    next_name = name if name is not None else existing["name"]
    next_parent = parent_id if update_parent else existing["parent_id"]
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute(
            "UPDATE video_folders SET name = ?, parent_id = ?, updated_at = ? WHERE id = ? AND user_id = ?",
            (next_name, next_parent, now, folder_id, user_id),
        )
        row = conn.execute("SELECT * FROM video_folders WHERE id = ?", (folder_id,)).fetchone()
        return dict(row) if row else None


def get_folder_descendant_ids(user_id: int, folder_id: int) -> list[int]:
    with get_db() as conn:
        rows = conn.execute(
            """
            WITH RECURSIVE descendants(id) AS (
                SELECT id FROM video_folders WHERE id = ? AND user_id = ?
                UNION ALL
                SELECT child.id FROM video_folders child
                JOIN descendants parent ON child.parent_id = parent.id
                WHERE child.user_id = ?
            )
            SELECT id FROM descendants
            """,
            (folder_id, user_id, user_id),
        ).fetchall()
        return [int(row["id"]) for row in rows]


def delete_video_folder(user_id: int, folder_id: int) -> dict | None:
    existing = get_video_folder(user_id, folder_id)
    if not existing:
        return None
    with get_db() as conn:
        conn.execute(
            "UPDATE video_folders SET parent_id = ? WHERE user_id = ? AND parent_id = ?",
            (existing["parent_id"], user_id, folder_id),
        )
        conn.execute(
            "UPDATE library_videos SET folder_id = ?, updated_at = datetime('now') WHERE user_id = ? AND folder_id = ?",
            (existing["parent_id"], user_id, folder_id),
        )
        conn.execute("DELETE FROM video_folders WHERE id = ? AND user_id = ?", (folder_id, user_id))
    return existing


def list_library_videos(user_id: int) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM library_videos WHERE user_id = ? ORDER BY parsed_at DESC, id DESC",
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def upsert_library_video(user_id: int, url: str, video: dict) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    values = (
        str(video.get("title") or "未命名视频"),
        str(video.get("thumbnail") or ""),
        str(video.get("platform") or ""),
        str(video.get("uploader") or ""),
        str(video.get("duration_string") or ""),
    )
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO library_videos (
                user_id, url, title, thumbnail, platform, uploader, duration_string, parsed_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, url) DO UPDATE SET
                title = excluded.title,
                thumbnail = excluded.thumbnail,
                platform = excluded.platform,
                uploader = excluded.uploader,
                duration_string = excluded.duration_string,
                parsed_at = excluded.parsed_at,
                updated_at = excluded.updated_at
            """,
            (user_id, url, *values, now, now),
        )
        row = conn.execute(
            "SELECT * FROM library_videos WHERE user_id = ? AND url = ?",
            (user_id, url),
        ).fetchone()
        return dict(row)


def move_library_video(user_id: int, video_id: int, folder_id: int | None) -> dict | None:
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute(
            "UPDATE library_videos SET folder_id = ?, updated_at = ? WHERE id = ? AND user_id = ?",
            (folder_id, now, video_id, user_id),
        )
        row = conn.execute(
            "SELECT * FROM library_videos WHERE id = ? AND user_id = ?",
            (video_id, user_id),
        ).fetchone()
        return dict(row) if row else None


def delete_library_video(user_id: int, video_id: int) -> bool:
    with get_db() as conn:
        cursor = conn.execute(
            "DELETE FROM library_videos WHERE id = ? AND user_id = ?",
            (video_id, user_id),
        )
        return cursor.rowcount > 0


def list_folder_library_videos(user_id: int, folder_id: int) -> list[dict]:
    folder_ids = get_folder_descendant_ids(user_id, folder_id)
    if not folder_ids:
        return []
    placeholders = ",".join("?" for _ in folder_ids)
    with get_db() as conn:
        rows = conn.execute(
            f"SELECT * FROM library_videos WHERE user_id = ? AND folder_id IN ({placeholders}) ORDER BY parsed_at",
            (user_id, *folder_ids),
        ).fetchall()
        return [dict(row) for row in rows]


def save_course_quiz(user_id: int, folder_id: int, quiz_json: str, source_count: int) -> int:
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO course_quizzes (user_id, folder_id, quiz_json, source_count) VALUES (?, ?, ?, ?)",
            (user_id, folder_id, quiz_json, source_count),
        )
        return int(cursor.lastrowid)


def get_latest_course_quiz(user_id: int, folder_id: int) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM course_quizzes WHERE user_id = ? AND folder_id = ? ORDER BY id DESC LIMIT 1",
            (user_id, folder_id),
        ).fetchone()
        return dict(row) if row else None


REVIEW_INTERVAL_DAYS = (1, 3, 7, 14)


def _adaptive_interval_days(stage: int, review_count: int, accuracy: float = 0.7) -> int:
    """前四阶段稳定执行 1/3/7/14 天，之后按表现动态延长或收紧。"""
    if stage < len(REVIEW_INTERVAL_DAYS):
        return REVIEW_INTERVAL_DAYS[stage]
    stability = 0.75 + max(0.0, min(accuracy, 1.0)) * 0.75
    growth = 30 * (1.55 ** max(0, stage - len(REVIEW_INTERVAL_DAYS)))
    fatigue_penalty = 0.9 if review_count > 10 and accuracy < 0.65 else 1.0
    return max(14, min(180, round(growth * stability * fatigue_penalty)))


def upsert_question_bank_item(
    user_id: int,
    folder_id: int,
    fingerprint: str,
    question: dict,
) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO question_bank (
                user_id, folder_id, fingerprint, question_json, knowledge_point,
                source_video_title, source_video_url, evidence_quote,
                evidence_time_seconds, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, folder_id, fingerprint) DO UPDATE SET
                question_json = excluded.question_json,
                knowledge_point = excluded.knowledge_point,
                source_video_title = excluded.source_video_title,
                source_video_url = excluded.source_video_url,
                evidence_quote = excluded.evidence_quote,
                evidence_time_seconds = excluded.evidence_time_seconds,
                updated_at = excluded.updated_at
            """,
            (
                user_id,
                folder_id,
                fingerprint,
                json.dumps(question, ensure_ascii=False),
                str(question.get("knowledge_point") or "课程综合"),
                str(question.get("source_video_title") or ""),
                str(question.get("source_video_url") or ""),
                str(question.get("evidence_quote") or ""),
                float(question.get("evidence_time_seconds") or 0),
                now,
                now,
            ),
        )
        row = conn.execute(
            "SELECT * FROM question_bank WHERE user_id = ? AND folder_id = ? AND fingerprint = ?",
            (user_id, folder_id, fingerprint),
        ).fetchone()
        return dict(row)


def delete_question_bank_item(user_id: int, question_bank_id: int) -> bool:
    with get_db() as conn:
        cursor = conn.execute(
            "DELETE FROM question_bank WHERE id=? AND user_id=?", (question_bank_id, user_id)
        )
        return cursor.rowcount > 0


def list_question_bank(
    user_id: int,
    folder_id: int,
    *,
    limit: int = 200,
    knowledge_points: list[str] | None = None,
) -> list[dict]:
    params: list = [user_id, folder_id]
    where = "user_id = ? AND folder_id = ?"
    if knowledge_points:
        placeholders = ",".join("?" for _ in knowledge_points)
        where += f" AND knowledge_point IN ({placeholders})"
        params.extend(knowledge_points)
    params.append(max(1, min(limit, 500)))
    with get_db() as conn:
        rows = conn.execute(
            f"SELECT * FROM question_bank WHERE {where} ORDER BY times_used ASC, updated_at DESC LIMIT ?",
            params,
        ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["question"] = json.loads(item.pop("question_json"))
            items.append(item)
        return items


def list_knowledge_mastery(user_id: int, folder_id: int) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM knowledge_mastery
            WHERE user_id = ? AND folder_id = ?
            ORDER BY mastery_score ASC, attempts DESC, knowledge_point
            """,
            (user_id, folder_id),
        ).fetchall()
        return [dict(row) for row in rows]


def _schedule_review(conn, user_id: int, folder_id: int, question_bank_id: int, correct: bool) -> None:
    now = datetime.now(timezone.utc)
    row = conn.execute(
        "SELECT * FROM wrong_question_reviews WHERE user_id = ? AND question_bank_id = ?",
        (user_id, question_bank_id),
    ).fetchone()
    if not row and correct:
        return
    current_stage = int(row["stage"]) if row else 0
    next_stage = current_stage + 1 if correct else 0
    stats = conn.execute(
        "SELECT times_used, correct_count FROM question_bank WHERE id = ?",
        (question_bank_id,),
    ).fetchone()
    accuracy = (
        float(stats["correct_count"]) / max(int(stats["times_used"]), 1)
        if stats else 0.7
    )
    due_at = (
        now + timedelta(days=_adaptive_interval_days(
            next_stage, int(row["review_count"]) if row else 0, accuracy
        ))
    ).isoformat()
    if row:
        conn.execute(
            """
            UPDATE wrong_question_reviews
            SET stage = ?, review_count = review_count + 1, due_at = ?,
                last_correct = ?, updated_at = ? WHERE id = ?
            """,
            (next_stage, due_at, 1 if correct else 0, now.isoformat(), row["id"]),
        )
    else:
        conn.execute(
            """
            INSERT INTO wrong_question_reviews (
                user_id, folder_id, question_bank_id, stage, review_count,
                due_at, last_correct, updated_at
            ) VALUES (?, ?, ?, 0, 0, ?, 0, ?)
            """,
            (
                user_id,
                folder_id,
                question_bank_id,
                (now + timedelta(days=_adaptive_interval_days(0, 0, 0))).isoformat(),
                now.isoformat(),
            ),
        )


def save_quiz_attempt(
    user_id: int,
    folder_id: int,
    *,
    quiz_id: int | None,
    mode: str,
    phase: str,
    total_score: float,
    max_score: float,
    answers: dict,
    results: list[dict],
    bank_items: dict[str, int],
    questions: list[dict],
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    result_by_id = {str(item.get("id")): item for item in results}
    with get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO quiz_attempts (
                user_id, folder_id, quiz_id, mode, phase, total_score,
                max_score, answers_json, results_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id, folder_id, quiz_id, mode, phase, total_score, max_score,
                json.dumps(answers, ensure_ascii=False),
                json.dumps(results, ensure_ascii=False), now,
            ),
        )
        for question in questions:
            result = result_by_id.get(str(question.get("id")))
            if not result:
                continue
            fingerprint = str(question.get("fingerprint") or "")
            bank_id = bank_items.get(fingerprint)
            if not bank_id:
                continue
            correct = bool(result.get("correct"))
            earned = float(result.get("awarded_points") or 0)
            possible = float(result.get("max_points") or question.get("points") or 0)
            point = str(question.get("knowledge_point") or "课程综合")
            conn.execute(
                "UPDATE question_bank SET times_used = times_used + 1, correct_count = correct_count + ?, updated_at = ? WHERE id = ?",
                (1 if correct else 0, now, bank_id),
            )
            conn.execute(
                """
                INSERT INTO knowledge_mastery (
                    user_id, folder_id, knowledge_point, attempts, correct_count,
                    earned_points, possible_points, mastery_score, updated_at
                ) VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, folder_id, knowledge_point) DO UPDATE SET
                    attempts = attempts + 1,
                    correct_count = correct_count + excluded.correct_count,
                    earned_points = earned_points + excluded.earned_points,
                    possible_points = possible_points + excluded.possible_points,
                    mastery_score = ROUND(
                        (earned_points + excluded.earned_points) * 100.0 /
                        MAX(possible_points + excluded.possible_points, 1), 1
                    ),
                    updated_at = excluded.updated_at
                """,
                (
                    user_id, folder_id, point, 1 if correct else 0, earned, possible,
                    round(earned * 100 / possible, 1) if possible else 0, now,
                ),
            )
            if not correct or mode == "wrong":
                _schedule_review(conn, user_id, folder_id, bank_id, correct)
        return int(cursor.lastrowid)


def list_wrong_questions(user_id: int, folder_id: int, *, due_only: bool = False) -> list[dict]:
    where_due = "AND w.due_at IS NOT NULL AND w.due_at <= ?" if due_only else ""
    params = [user_id, folder_id]
    if due_only:
        params.append(datetime.now(timezone.utc).isoformat())
    with get_db() as conn:
        rows = conn.execute(
            f"""
            SELECT w.*, q.question_json, q.knowledge_point, q.source_video_title,
                   q.source_video_url, q.evidence_quote, q.evidence_time_seconds
            FROM wrong_question_reviews w
            JOIN question_bank q ON q.id = w.question_bank_id
            WHERE w.user_id = ? AND w.folder_id = ? {where_due}
            ORDER BY CASE WHEN w.due_at IS NULL THEN 1 ELSE 0 END, w.due_at, w.updated_at DESC
            """,
            params,
        ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["question"] = json.loads(item.pop("question_json"))
            items.append(item)
        return items


def ensure_flashcard(user_id: int, folder_id: int, question: dict) -> None:
    front = str(question.get("question") or "").strip()
    if not front:
        return
    answer = str(question.get("reference_answer") or "").strip()
    if not answer:
        keys = set(question.get("answer") or [])
        answer = "；".join(
            f"{item.get('key')}. {item.get('text')}"
            for item in question.get("options") or []
            if item.get("key") in keys
        )
    back = answer or str(question.get("explanation") or "").strip()
    if not back:
        return
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO flashcards (
                user_id, folder_id, knowledge_point, front, back,
                source_video_title, source_video_url, evidence_time_seconds
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, folder_id, front) DO UPDATE SET
                back = excluded.back,
                knowledge_point = excluded.knowledge_point,
                source_video_title = excluded.source_video_title,
                source_video_url = excluded.source_video_url,
                evidence_time_seconds = excluded.evidence_time_seconds
            """,
            (
                user_id, folder_id, str(question.get("knowledge_point") or "课程综合"),
                front, back, str(question.get("source_video_title") or ""),
                str(question.get("source_video_url") or ""),
                float(question.get("evidence_time_seconds") or 0),
            ),
        )


def list_flashcards(user_id: int, folder_id: int, *, due_only: bool = False) -> list[dict]:
    where_due = "AND due_at IS NOT NULL AND due_at <= ?" if due_only else ""
    params = [user_id, folder_id]
    if due_only:
        params.append(datetime.now(timezone.utc).isoformat())
    with get_db() as conn:
        rows = conn.execute(
            f"""
            SELECT * FROM flashcards WHERE user_id = ? AND folder_id = ? {where_due}
            ORDER BY CASE WHEN due_at IS NULL THEN 1 ELSE 0 END, due_at, id
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]


def review_flashcard(user_id: int, card_id: int, remembered: bool) -> dict | None:
    now = datetime.now(timezone.utc)
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM flashcards WHERE id = ? AND user_id = ?", (card_id, user_id)
        ).fetchone()
        if not row:
            return None
        current_stage = int(row["stage"])
        next_stage = current_stage + 1 if remembered else 0
        remembered_ratio = 0.85 if remembered else 0.2
        due_at = (
            now + timedelta(days=_adaptive_interval_days(
                next_stage, int(row["review_count"]), remembered_ratio
            ))
        ).isoformat()
        conn.execute(
            """
            UPDATE flashcards SET stage = ?, review_count = review_count + 1,
                due_at = ?, updated_at = ? WHERE id = ? AND user_id = ?
            """,
            (next_stage, due_at, now.isoformat(), card_id, user_id),
        )
        updated = conn.execute("SELECT * FROM flashcards WHERE id = ?", (card_id,)).fetchone()
        return dict(updated)


def get_learning_dashboard(user_id: int, folder_id: int) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        attempts = conn.execute(
            "SELECT * FROM quiz_attempts WHERE user_id = ? AND folder_id = ? ORDER BY created_at DESC LIMIT 30",
            (user_id, folder_id),
        ).fetchall()
        pre = conn.execute(
            "SELECT AVG(total_score * 100.0 / MAX(max_score, 1)) score FROM quiz_attempts WHERE user_id = ? AND folder_id = ? AND phase = 'pre'",
            (user_id, folder_id),
        ).fetchone()["score"]
        post = conn.execute(
            "SELECT AVG(total_score * 100.0 / MAX(max_score, 1)) score FROM quiz_attempts WHERE user_id = ? AND folder_id = ? AND phase = 'post'",
            (user_id, folder_id),
        ).fetchone()["score"]
        bank_count = conn.execute(
            "SELECT COUNT(*) count FROM question_bank WHERE user_id = ? AND folder_id = ?",
            (user_id, folder_id),
        ).fetchone()["count"]
        due_wrong = conn.execute(
            "SELECT COUNT(*) count FROM wrong_question_reviews WHERE user_id = ? AND folder_id = ? AND due_at IS NOT NULL AND due_at <= ?",
            (user_id, folder_id, now),
        ).fetchone()["count"]
        due_cards = conn.execute(
            "SELECT COUNT(*) count FROM flashcards WHERE user_id = ? AND folder_id = ? AND due_at IS NOT NULL AND due_at <= ?",
            (user_id, folder_id, now),
        ).fetchone()["count"]
        card_count = conn.execute(
            "SELECT COUNT(*) count FROM flashcards WHERE user_id = ? AND folder_id = ?",
            (user_id, folder_id),
        ).fetchone()["count"]
    mastery = list_knowledge_mastery(user_id, folder_id)
    history = [
        {
            "id": row["id"], "mode": row["mode"], "phase": row["phase"],
            "score": round(float(row["total_score"]) * 100 / max(float(row["max_score"]), 1), 1),
            "created_at": row["created_at"],
        }
        for row in attempts
    ]
    average = round(sum(item["score"] for item in history) / len(history), 1) if history else 0
    return {
        "attempt_count": len(history), "average_score": average,
        "pre_score": round(float(pre), 1) if pre is not None else None,
        "post_score": round(float(post), 1) if post is not None else None,
        "improvement": round(float(post) - float(pre), 1) if pre is not None and post is not None else None,
        "question_count": int(bank_count), "due_wrong_count": int(due_wrong),
        "flashcard_count": int(card_count), "due_flashcard_count": int(due_cards),
        "mastery": mastery, "history": history,
    }


def get_library_video(user_id: int, video_id: int) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM library_videos WHERE id = ? AND user_id = ?",
            (video_id, user_id),
        ).fetchone()
        return dict(row) if row else None


def list_video_progress(user_id: int, folder_id: int) -> list[dict]:
    folder_ids = get_folder_descendant_ids(user_id, folder_id)
    if not folder_ids:
        return []
    placeholders = ",".join("?" for _ in folder_ids)
    with get_db() as conn:
        rows = conn.execute(
            f"""
            SELECT v.id video_id, v.title, v.url, v.folder_id, v.duration_string,
                   COALESCE(p.progress_seconds, 0) progress_seconds,
                   COALESCE(p.duration_seconds, 0) duration_seconds,
                   COALESCE(p.completion_percent, 0) completion_percent,
                   COALESCE(p.status, 'not_started') status,
                   p.last_studied_at
            FROM library_videos v
            LEFT JOIN video_learning_progress p
              ON p.video_id = v.id AND p.user_id = v.user_id
            WHERE v.user_id = ? AND v.folder_id IN ({placeholders})
            ORDER BY CASE COALESCE(p.status, 'not_started')
                WHEN 'in_progress' THEN 0 WHEN 'not_started' THEN 1 ELSE 2 END,
                COALESCE(p.last_studied_at, v.parsed_at) DESC
            """,
            (user_id, *folder_ids),
        ).fetchall()
        return [dict(row) for row in rows]


def upsert_video_progress(
    user_id: int,
    video_id: int,
    *,
    progress_seconds: float = 0,
    duration_seconds: float = 0,
    completion_percent: float = 0,
    status: str = "in_progress",
) -> dict | None:
    if not get_library_video(user_id, video_id):
        return None
    now = datetime.now(timezone.utc).isoformat()
    percent = max(0.0, min(float(completion_percent or 0), 100.0))
    if percent >= 95:
        status = "completed"
        percent = 100.0
    elif percent > 0 and status == "not_started":
        status = "in_progress"
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO video_learning_progress (
                user_id, video_id, progress_seconds, duration_seconds,
                completion_percent, status, last_studied_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, video_id) DO UPDATE SET
                progress_seconds = excluded.progress_seconds,
                duration_seconds = MAX(video_learning_progress.duration_seconds, excluded.duration_seconds),
                completion_percent = excluded.completion_percent,
                status = excluded.status,
                last_studied_at = excluded.last_studied_at,
                updated_at = excluded.updated_at
            """,
            (
                user_id, video_id, max(0, float(progress_seconds or 0)),
                max(0, float(duration_seconds or 0)), percent, status, now, now,
            ),
        )
        row = conn.execute(
            "SELECT * FROM video_learning_progress WHERE user_id = ? AND video_id = ?",
            (user_id, video_id),
        ).fetchone()
        return dict(row)


def list_video_notes(user_id: int, folder_id: int) -> list[dict]:
    folder_ids = get_folder_descendant_ids(user_id, folder_id)
    if not folder_ids:
        return []
    placeholders = ",".join("?" for _ in folder_ids)
    with get_db() as conn:
        rows = conn.execute(
            f"""
            SELECT n.*, v.title video_title, v.url video_url
            FROM video_notes n JOIN library_videos v ON v.id = n.video_id
            WHERE n.user_id = ? AND n.folder_id IN ({placeholders})
            ORDER BY n.updated_at DESC, n.id DESC
            """,
            (user_id, *folder_ids),
        ).fetchall()
        return [dict(row) for row in rows]


def list_video_notes_for_video(user_id: int, video_id: int) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT n.*, v.title video_title, v.url video_url
            FROM video_notes n JOIN library_videos v ON v.id = n.video_id
            WHERE n.user_id = ? AND n.video_id = ?
            ORDER BY n.time_seconds, n.created_at
            """,
            (user_id, video_id),
        ).fetchall()
        return [dict(row) for row in rows]


def create_video_note(
    user_id: int,
    video_id: int,
    content: str,
    time_seconds: float = 0,
) -> dict | None:
    video = get_library_video(user_id, video_id)
    if not video:
        return None
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO video_notes (
                user_id, folder_id, video_id, time_seconds, content, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id, video.get("folder_id"), video_id,
                max(0, float(time_seconds or 0)), content.strip(), now, now,
            ),
        )
        row = conn.execute(
            """
            SELECT n.*, v.title video_title, v.url video_url
            FROM video_notes n JOIN library_videos v ON v.id = n.video_id
            WHERE n.id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()
        return dict(row)


def delete_video_note(user_id: int, note_id: int) -> bool:
    with get_db() as conn:
        cursor = conn.execute(
            "DELETE FROM video_notes WHERE id = ? AND user_id = ?", (note_id, user_id)
        )
        return cursor.rowcount > 0


def get_learning_goal(user_id: int, folder_id: int) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM learning_goals WHERE user_id = ? AND folder_id = ?",
            (user_id, folder_id),
        ).fetchone()
        return dict(row) if row else None


def upsert_learning_goal(
    user_id: int,
    folder_id: int,
    *,
    exam_date: str | None,
    target_score: float,
    daily_minutes: int,
) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO learning_goals (
                user_id, folder_id, exam_date, target_score, daily_minutes, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, folder_id) DO UPDATE SET
                exam_date = excluded.exam_date,
                target_score = excluded.target_score,
                daily_minutes = excluded.daily_minutes,
                updated_at = excluded.updated_at
            """,
            (
                user_id, folder_id, exam_date,
                max(0, min(float(target_score), 100)),
                max(5, min(int(daily_minutes), 480)), now,
            ),
        )
        row = conn.execute(
            "SELECT * FROM learning_goals WHERE user_id = ? AND folder_id = ?",
            (user_id, folder_id),
        ).fetchone()
        return dict(row)


def list_completed_daily_tasks(user_id: int, folder_id: int, task_date: str) -> set[str]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT task_key FROM daily_task_completions
            WHERE user_id = ? AND folder_id = ? AND task_date = ?
            """,
            (user_id, folder_id, task_date),
        ).fetchall()
        return {str(row["task_key"]) for row in rows}


def set_daily_task_completion(
    user_id: int,
    folder_id: int,
    task_date: str,
    task_key: str,
    completed: bool,
) -> None:
    with get_db() as conn:
        if completed:
            conn.execute(
                """
                INSERT OR IGNORE INTO daily_task_completions (
                    user_id, folder_id, task_date, task_key
                ) VALUES (?, ?, ?, ?)
                """,
                (user_id, folder_id, task_date, task_key),
            )
        else:
            conn.execute(
                """
                DELETE FROM daily_task_completions
                WHERE user_id = ? AND folder_id = ? AND task_date = ? AND task_key = ?
                """,
                (user_id, folder_id, task_date, task_key),
            )


def upsert_mistake_diagnosis(
    user_id: int,
    folder_id: int,
    question_bank_id: int,
    category: str,
    diagnosis: str,
    action: str,
) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO mistake_diagnoses (
                user_id, folder_id, question_bank_id, category,
                diagnosis, action, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, question_bank_id) DO UPDATE SET
                category = excluded.category,
                diagnosis = excluded.diagnosis,
                action = excluded.action,
                updated_at = excluded.updated_at
            """,
            (
                user_id, folder_id, question_bank_id, category,
                diagnosis, action, now, now,
            ),
        )
        row = conn.execute(
            "SELECT * FROM mistake_diagnoses WHERE user_id = ? AND question_bank_id = ?",
            (user_id, question_bank_id),
        ).fetchone()
        return dict(row)


def list_mistake_diagnoses(user_id: int, folder_id: int) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT d.*, q.knowledge_point, q.source_video_title,
                   q.source_video_url, q.evidence_time_seconds, q.question_json
            FROM mistake_diagnoses d
            JOIN question_bank q ON q.id = d.question_bank_id
            WHERE d.user_id = ? AND d.folder_id = ?
            ORDER BY d.updated_at DESC
            """,
            (user_id, folder_id),
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["question"] = json.loads(item.pop("question_json"))
            result.append(item)
        return result


def rebuild_knowledge_relations(user_id: int, folder_id: int, points: list[str]) -> list[dict]:
    clean_points = list(dict.fromkeys(str(point).strip() for point in points if str(point).strip()))
    with get_db() as conn:
        conn.execute(
            "DELETE FROM knowledge_relations WHERE user_id = ? AND folder_id = ?",
            (user_id, folder_id),
        )
        for source, target in zip(clean_points, clean_points[1:]):
            conn.execute(
                """
                INSERT OR IGNORE INTO knowledge_relations (
                    user_id, folder_id, source_point, target_point, relation
                ) VALUES (?, ?, ?, ?, 'prerequisite')
                """,
                (user_id, folder_id, source, target),
            )
    return list_knowledge_relations(user_id, folder_id)


def list_knowledge_relations(user_id: int, folder_id: int) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM knowledge_relations
            WHERE user_id = ? AND folder_id = ? ORDER BY id
            """,
            (user_id, folder_id),
        ).fetchall()
        return [dict(row) for row in rows]


def get_app_setting(key: str) -> str | None:
    with get_db() as conn:
        try:
            row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
        except sqlite3.OperationalError:
            return None
        return row["value"] if row else None


def get_app_settings(keys: list[str] | None = None) -> dict[str, str]:
    with get_db() as conn:
        try:
            if keys:
                placeholders = ",".join("?" for _ in keys)
                rows = conn.execute(
                    f"SELECT key, value FROM app_settings WHERE key IN ({placeholders})",
                    keys,
                ).fetchall()
            else:
                rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
        except sqlite3.OperationalError:
            return {}
        return {row["key"]: row["value"] for row in rows}


def set_app_settings(values: dict[str, str]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        for key, value in values.items():
            conn.execute(
                """
                INSERT INTO app_settings (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (key, value, now),
            )


def _row_to_profile(row: sqlite3.Row | None) -> dict | None:
    if not row:
        return None
    data = dict(row)
    data["is_active"] = bool(data.get("is_active"))
    data["api_key_set"] = bool((data.get("api_key") or "").strip())
    return data


def list_model_profiles() -> list[dict]:
    with get_db() as conn:
        try:
            rows = conn.execute(
                "SELECT * FROM model_profiles ORDER BY is_active DESC, id ASC"
            ).fetchall()
        except sqlite3.OperationalError:
            return []
        return [_row_to_profile(row) for row in rows]


def get_model_profile(profile_id: int) -> dict | None:
    with get_db() as conn:
        try:
            row = conn.execute(
                "SELECT * FROM model_profiles WHERE id = ?",
                (profile_id,),
            ).fetchone()
        except sqlite3.OperationalError:
            return None
        return _row_to_profile(row)


def get_active_model_profile() -> dict | None:
    with get_db() as conn:
        try:
            row = conn.execute(
                "SELECT * FROM model_profiles WHERE is_active = 1 ORDER BY id ASC LIMIT 1"
            ).fetchone()
        except sqlite3.OperationalError:
            return None
        return _row_to_profile(row)


def create_model_profile(
    *,
    name: str,
    base_url: str,
    model: str,
    api_key: str = "",
    activate: bool = False,
) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        if activate:
            conn.execute("UPDATE model_profiles SET is_active = 0")
        cursor = conn.execute(
            """
            INSERT INTO model_profiles (name, base_url, model, api_key, is_active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (name, base_url, model, api_key, 1 if activate else 0, now, now),
        )
        row = conn.execute(
            "SELECT * FROM model_profiles WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
        return _row_to_profile(row)


def update_model_profile(
    profile_id: int,
    *,
    name: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
) -> dict | None:
    existing = get_model_profile(profile_id)
    if not existing:
        return None

    next_name = name if name is not None else existing["name"]
    next_base_url = base_url if base_url is not None else existing["base_url"]
    next_model = model if model is not None else existing["model"]
    next_api_key = existing["api_key"]
    if api_key is not None and api_key.strip():
        next_api_key = api_key.strip()

    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute(
            """
            UPDATE model_profiles
            SET name = ?, base_url = ?, model = ?, api_key = ?, updated_at = ?
            WHERE id = ?
            """,
            (next_name, next_base_url, next_model, next_api_key, now, profile_id),
        )
        row = conn.execute(
            "SELECT * FROM model_profiles WHERE id = ?",
            (profile_id,),
        ).fetchone()
        return _row_to_profile(row)


def delete_model_profile(profile_id: int) -> dict | None:
    existing = get_model_profile(profile_id)
    if not existing:
        return None

    with get_db() as conn:
        conn.execute("DELETE FROM model_profiles WHERE id = ?", (profile_id,))
        if existing.get("is_active"):
            row = conn.execute(
                "SELECT * FROM model_profiles ORDER BY id ASC LIMIT 1"
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE model_profiles SET is_active = 1, updated_at = ? WHERE id = ?",
                    (datetime.now(timezone.utc).isoformat(), row["id"]),
                )

    return existing


def activate_model_profile(profile_id: int) -> dict | None:
    existing = get_model_profile(profile_id)
    if not existing:
        return None

    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute("UPDATE model_profiles SET is_active = 0")
        conn.execute(
            "UPDATE model_profiles SET is_active = 1, updated_at = ? WHERE id = ?",
            (now, profile_id),
        )
        row = conn.execute(
            "SELECT * FROM model_profiles WHERE id = ?",
            (profile_id,),
        ).fetchone()
        return _row_to_profile(row)


def check_and_increment_summary(user_id: int) -> tuple[bool, int]:
    """
    检查用户是否可以使用 AI 总结，并自增计数。
    返回 (allowed, remaining_count)
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            return False, 0

        if user["is_vip"] and user["vip_expire_at"]:
            expire = datetime.fromisoformat(user["vip_expire_at"])
            if expire > datetime.now(timezone.utc):
                return True, -1  # -1 means unlimited

        if user["last_summary_date"] != today:
            conn.execute(
                "UPDATE users SET daily_summary_count = 1, last_summary_date = ? WHERE id = ?",
                (today, user_id),
            )
            return True, FREE_DAILY_SUMMARY_LIMIT - 1

        current = user["daily_summary_count"]
        if current >= FREE_DAILY_SUMMARY_LIMIT:
            return False, 0

        conn.execute(
            "UPDATE users SET daily_summary_count = daily_summary_count + 1 WHERE id = ?",
            (user_id,),
        )
        return True, FREE_DAILY_SUMMARY_LIMIT - current - 1


def create_order(user_id: int, order_no: str, amount: int, currency: str = "cny", plan_type: str = "monthly") -> dict:
    with get_db() as conn:
        conn.execute(
            "INSERT INTO orders (order_no, user_id, amount, currency, plan_type) VALUES (?, ?, ?, ?, ?)",
            (order_no, user_id, amount, currency, plan_type),
        )
        return {"order_no": order_no, "user_id": user_id, "amount": amount}


def update_order_stripe_session(order_no: str, session_id: str):
    with get_db() as conn:
        conn.execute(
            "UPDATE orders SET stripe_session_id = ?, updated_at = datetime('now') WHERE order_no = ?",
            (session_id, order_no),
        )


def complete_order(session_id: str, payment_intent_id: str) -> dict | None:
    """
    支付完成时更新订单状态、激活 VIP。
    使用事务保证幂等：只有 pending 状态的订单才会被更新。
    """
    with get_db() as conn:
        order = conn.execute(
            "SELECT * FROM orders WHERE stripe_session_id = ? AND status = 'pending'",
            (session_id,),
        ).fetchone()

        if not order:
            return None

        now = datetime.now(timezone.utc).isoformat()

        from dateutil.relativedelta import relativedelta
        user = conn.execute("SELECT * FROM users WHERE id = ?", (order["user_id"],)).fetchone()

        current_expire = None
        if user["vip_expire_at"]:
            try:
                current_expire = datetime.fromisoformat(user["vip_expire_at"])
            except ValueError:
                pass

        base_time = datetime.now(timezone.utc)
        if current_expire and current_expire > base_time:
            base_time = current_expire

        if order["plan_type"] == "monthly":
            new_expire = base_time + relativedelta(months=1)
        elif order["plan_type"] == "yearly":
            new_expire = base_time + relativedelta(years=1)
        else:
            new_expire = base_time + relativedelta(months=1)

        conn.execute(
            "UPDATE orders SET status = 'paid', stripe_payment_intent_id = ?, paid_at = ?, updated_at = ? WHERE id = ?",
            (payment_intent_id, now, now, order["id"]),
        )

        conn.execute(
            "UPDATE users SET is_vip = 1, vip_expire_at = ?, updated_at = ? WHERE id = ?",
            (new_expire.isoformat(), now, order["user_id"]),
        )

        return dict(order)


def get_order_by_no(order_no: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM orders WHERE order_no = ?", (order_no,)).fetchone()
        return dict(row) if row else None


def get_user_orders(user_id: int) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]
