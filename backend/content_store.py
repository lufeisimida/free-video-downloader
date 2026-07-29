"""基于 JSON 文件的本地内容持久化。"""

import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Optional


BASE_DIR = Path(__file__).resolve().parent
CONTENT_DIR = BASE_DIR / "data" / "content"
STORE_VERSION = 1
_STORE_LOCK = threading.RLock()


def owner_key(user: Optional[dict]) -> str:
    """登录用户按 id 隔离；自用未登录模式使用 anonymous 命名空间。"""
    if user and user.get("id") is not None:
        return f"user:{user['id']}"
    return "anonymous"


class ContentStore:
    """每个视频一个 JSON 文件，所有写入使用临时文件原子替换。"""

    def __init__(self, root: Path = CONTENT_DIR):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _video_key(url: str) -> str:
        return hashlib.sha256((url or "").strip().encode("utf-8")).hexdigest()

    def _path(self, url: str) -> Path:
        return self.root / f"{self._video_key(url)}.json"

    def load(self, url: str) -> dict:
        path = self._path(url)
        with _STORE_LOCK:
            try:
                with path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("version") != STORE_VERSION:
                    return {}
                return data if isinstance(data, dict) else {}
            except (OSError, json.JSONDecodeError, TypeError):
                return {}

    def update(self, url: str, **fields) -> dict:
        with _STORE_LOCK:
            data = self.load(url)
            data.update(fields)
            data["version"] = STORE_VERSION
            data["url"] = url
            data["updated_at"] = time.time()
            self._write(url, data)
            return data

    def list_items(self) -> list[dict]:
        """读取全部有效内容记录，用于单账号部署迁移历史解析数据。"""
        items = []
        with _STORE_LOCK:
            for path in self.root.glob("*.json"):
                try:
                    with path.open("r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict) and data.get("version") == STORE_VERSION and data.get("url"):
                        items.append(data)
                except (OSError, json.JSONDecodeError, TypeError):
                    continue
        return items

    def append_chat(self, url: str, question: str, answer: str, user: Optional[dict]) -> None:
        if not question.strip() or not answer.strip():
            return
        data = self.load(url)
        chats = data.setdefault("chats", [])
        chats.append({
            "owner": owner_key(user),
            "question": question.strip(),
            "answer": answer.strip(),
            "created_at": time.time(),
        })
        data["chats"] = chats[-50:]
        self.update(url, chats=data["chats"])

    def clear_chats(self, url: str, user: Optional[dict] = None) -> int:
        """清空问答历史。传入 user 时只清该用户；否则清空全部。"""
        data = self.load(url)
        chats = data.get("chats") or []
        if not chats:
            return 0
        if user is None:
            removed = len(chats)
            self.update(url, chats=[])
            return removed
        owner = owner_key(user)
        kept = [item for item in chats if item.get("owner") != owner]
        removed = len(chats) - len(kept)
        if removed:
            self.update(url, chats=kept)
        return removed

    def load_quiz_state(self, url: str, user: Optional[dict]) -> dict:
        data = self.load(url)
        states = data.get("quiz_states") or {}
        return states.get(owner_key(user), {"current": None, "history": []})

    def save_quiz_state(self, url: str, user: Optional[dict], state: dict) -> None:
        data = self.load(url)
        states = data.get("quiz_states") or {}
        states[owner_key(user)] = {
            "current": state.get("current"),
            "history": (state.get("history") or [])[:10],
        }
        self.update(url, quiz_states=states)

    def _write(self, url: str, data: dict) -> None:
        path = self._path(url)
        temp_path = path.with_suffix(f".{threading.get_ident()}.tmp")
        try:
            with temp_path.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            temp_path.replace(path)
        finally:
            temp_path.unlink(missing_ok=True)


content_store = ContentStore()
