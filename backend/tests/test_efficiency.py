import asyncio
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

import database
from api_efficiency import _run_pipeline
from auth import get_current_user
from learning_efficiency import (
    canonicalize_knowledge_point,
    create_processing_job,
    get_processing_job,
    index_source,
    record_model_usage,
    semantic_search,
    assess_question_quality,
)
from main import app


class FakeProvider:
    model = "fake-model"

    def complete_chat(self, messages, *, temperature, max_tokens):
        return "函数用于封装重复逻辑。[证据1]"


class FakeSummarizer:
    provider = FakeProvider()


class FakeWhisperModel:
    def transcribe(self, path, **kwargs):
        return [SimpleNamespace(text="函数 封装 重复 逻辑")], SimpleNamespace(language="zh")


class FakeTranscriber:
    language = "zh"
    beam_size = 1

    def _get_model(self):
        return FakeWhisperModel()


class EfficiencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.original_db_path = database.DB_PATH
        database.DB_PATH = f"{cls.temp_dir.name}/efficiency.db"
        database.init_db()
        cls.user = database.create_user("efficiency@example.com", "unused")
        app.dependency_overrides[get_current_user] = lambda: cls.user
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.pop(get_current_user, None)
        database.DB_PATH = cls.original_db_path
        cls.temp_dir.cleanup()

    def setUp(self):
        with database.get_db() as conn:
            for table in (
                "reminder_deliveries", "model_usage_logs", "question_quality", "knowledge_point_aliases",
                "course_chunks", "learning_materials", "processing_job_items",
                "processing_jobs", "reminder_preferences", "flashcards",
                "question_bank", "library_videos", "video_folders",
            ):
                conn.execute(f"DELETE FROM {table}")
        self.folder = database.create_video_folder(self.user["id"], "效率课程")

    def test_new_routes_require_login(self):
        app.dependency_overrides.pop(get_current_user, None)
        try:
            for method, url in (
                ("get", f"/api/library/efficiency/folders/{self.folder['id']}/pipeline"),
                ("get", "/api/library/efficiency/reminders"),
                ("get", "/api/library/efficiency/usage"),
            ):
                self.assertEqual(getattr(self.client, method)(url).status_code, 401)
        finally:
            app.dependency_overrides[get_current_user] = lambda: self.user

    def test_pipeline_indexes_subtitle_and_persists_state(self):
        video = database.upsert_library_video(
            self.user["id"], "https://example.com/lesson", {"title": "函数课"}
        )
        database.move_library_video(self.user["id"], video["id"], self.folder["id"])
        job = create_processing_job(self.user["id"], self.folder["id"], [video["id"]])
        subtitle = {
            "has_subtitle": True,
            "full_text": "函数可以封装重复逻辑，参数用于接收输入。",
            "segments": [{"start": 5, "end": 10, "text": "函数可以封装重复逻辑"}],
        }
        with patch("api_efficiency.content_store.load", return_value={"subtitle": subtitle}):
            asyncio.run(_run_pipeline(job["id"], self.user["id"], self.folder["id"], False, False))
        saved = get_processing_job(self.user["id"], job["id"])
        self.assertEqual(saved["status"], "completed")
        self.assertEqual(saved["items"][0]["stage"], "completed")
        self.assertTrue(semantic_search(self.user["id"], self.folder["id"], "函数封装"))

    def test_grounded_qa_material_reminders_and_usage(self):
        index_source(
            self.user["id"], self.folder["id"], content="函数可以封装重复逻辑。",
            source_title="函数课", source_url="https://example.com/lesson", source_type="video",
        )
        with patch("api_summarize._get_summarizer", return_value=FakeSummarizer()):
            response = self.client.post(
                f"/api/library/efficiency/folders/{self.folder['id']}/ask",
                json={"query": "函数有什么作用？", "limit": 3},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["citations"][0]["source_title"], "函数课")

        upload = self.client.post(
            f"/api/library/efficiency/folders/{self.folder['id']}/materials/upload",
            files={"file": ("notes.txt", "课程资料包含函数定义和参数。".encode(), "text/plain")},
        )
        self.assertEqual(upload.status_code, 200)
        materials = self.client.get(
            f"/api/library/efficiency/folders/{self.folder['id']}/materials"
        ).json()["data"]
        self.assertEqual(materials[0]["material_type"], "txt")

        reminder = self.client.put(
            "/api/library/efficiency/reminders",
            json={"enabled": True, "reminder_time": "19:30", "browser_enabled": True},
        )
        self.assertTrue(reminder.json()["data"]["enabled"])
        record_model_usage(self.user["id"], "quiz", "fake", 100, 50, 20)
        usage = self.client.get("/api/library/efficiency/usage").json()["data"]
        self.assertEqual(usage["totals"]["requests"], 1)

    def test_neural_embedding_path_and_quality_rejection(self):
        with patch("learning_efficiency.embed_texts", return_value=([[1.0, 0.0]], "fake-embedding")):
            index_source(
                self.user["id"], self.folder["id"], content="面向对象通过封装管理状态。",
                source_title="设计课程", source_type="material",
            )
            results = semantic_search(self.user["id"], self.folder["id"], "对象状态")
        self.assertEqual(results[0]["retrieval_method"], "embedding")
        ambiguous = assess_question_quality({
            "type": "single", "question": "以下哪些说法正确？",
            "options": [{"key": "A", "text": "甲"}, {"key": "B", "text": "乙"}],
            "answer": ["A", "B"], "evidence_quote": "课程只支持一个正确答案",
        }, source_text="课程只支持一个正确答案")
        self.assertEqual(ambiguous["status"], "rejected")
        self.assertIn("答案不唯一或不在选项中", ambiguous["issues"])

    def test_quality_dedup_continuous_and_voice_recall(self):
        question = {
            "type": "short_answer", "question": "函数有什么作用？",
            "reference_answer": "封装重复逻辑", "knowledge_point": "函数定义",
            "evidence_quote": "函数可以封装重复逻辑",
        }
        database.upsert_question_bank_item(
            self.user["id"], self.folder["id"], "fingerprint", question
        )
        database.ensure_flashcard(self.user["id"], self.folder["id"], question)
        quality = self.client.post(
            f"/api/library/efficiency/folders/{self.folder['id']}/quality/check"
        )
        self.assertEqual(quality.status_code, 200)
        self.assertEqual(quality.json()["data"][0]["status"], "approved")
        self.assertEqual(
            canonicalize_knowledge_point(self.user["id"], self.folder["id"], "函数 定义"),
            "函数定义",
        )
        queue = self.client.get(
            f"/api/library/efficiency/folders/{self.folder['id']}/continuous"
        ).json()["data"]
        self.assertEqual(queue["items"][0]["type"], "flashcard")

        with patch("api_summarize._get_transcriber", return_value=FakeTranscriber()):
            voice = self.client.post(
                "/api/library/efficiency/voice/recall",
                files={"audio": ("recall.webm", b"fake-audio", "audio/webm")},
                data={"reference": "函数封装重复逻辑", "question": "函数有什么作用"},
            )
        self.assertEqual(voice.status_code, 200)
        self.assertGreaterEqual(voice.json()["data"]["score"], 60)


if __name__ == "__main__":
    unittest.main()
