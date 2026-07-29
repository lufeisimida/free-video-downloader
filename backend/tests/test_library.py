import json
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

import database
from auth import get_current_user
from main import app
from summarizer import QUIZ_BATCH_SPECS


class FakeSummarizer:
    def generate_quiz_batch(self, subtitle_text, language, spec, start_id, previous_questions):
        questions = []
        for offset in range(spec["count"]):
            question = {
                "id": start_id + offset,
                "type": spec["type"],
                "question": f"{spec['label']} {start_id + offset}",
                "options": [],
                "answer": [],
                "reference_answer": "课程参考答案",
                "explanation": "课程评分要点",
                "knowledge_point": "函数定义" if offset % 2 == 0 else "参数传递",
                "source_video_title": "函数基础",
                "evidence_quote": "函数可以封装重复逻辑",
                "evidence_time_seconds": 12,
                "points": spec["points"],
            }
            if spec["type"] in {"single", "multiple", "true_false"}:
                question["options"] = [
                    {"key": "A", "text": "正确"},
                    {"key": "B", "text": "错误"},
                ]
                question["answer"] = ["A"]
            questions.append(question)
        return {"title": "测试", "questions": questions}

    def organize_notes(self, notes):
        return "## 整理结果\n- 函数可以封装逻辑"

    def diagnose_mistake(self, question, answer):
        return {
            "category": "概念未理解",
            "diagnosis": "没有区分函数定义与调用。",
            "action": "回看证据并完成专项练习。",
        }


class LibraryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.original_db_path = database.DB_PATH
        database.DB_PATH = f"{cls.temp_dir.name}/library.db"
        database.init_db()
        cls.user = database.create_user("library@example.com", "unused")
        app.dependency_overrides[get_current_user] = lambda: cls.user
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.pop(get_current_user, None)
        database.DB_PATH = cls.original_db_path
        cls.temp_dir.cleanup()

    def setUp(self):
        with database.get_db() as conn:
            conn.execute("DELETE FROM daily_task_completions")
            conn.execute("DELETE FROM mistake_diagnoses")
            conn.execute("DELETE FROM knowledge_relations")
            conn.execute("DELETE FROM video_notes")
            conn.execute("DELETE FROM video_learning_progress")
            conn.execute("DELETE FROM learning_goals")
            conn.execute("DELETE FROM wrong_question_reviews")
            conn.execute("DELETE FROM quiz_attempts")
            conn.execute("DELETE FROM knowledge_mastery")
            conn.execute("DELETE FROM flashcards")
            conn.execute("DELETE FROM question_bank")
            conn.execute("DELETE FROM course_quizzes")
            conn.execute("DELETE FROM library_videos")
            conn.execute("DELETE FROM video_folders")

    def test_nested_folders_history_deduplication_and_safe_delete(self):
        root = database.create_video_folder(self.user["id"], "课程")
        child = database.create_video_folder(self.user["id"], "第一章", root["id"])
        first = database.upsert_library_video(
            self.user["id"],
            "https://example.com/1",
            {"title": "第一课", "platform": "Test"},
        )
        database.upsert_library_video(
            self.user["id"],
            "https://example.com/1",
            {"title": "第一课（更新）", "platform": "Test"},
        )
        second = database.upsert_library_video(
            self.user["id"],
            "https://example.com/2",
            {"title": "第二课", "platform": "Test"},
        )
        database.move_library_video(self.user["id"], first["id"], root["id"])
        database.move_library_video(self.user["id"], second["id"], child["id"])

        self.assertEqual(len(database.list_library_videos(self.user["id"])), 2)
        self.assertEqual(len(database.list_folder_library_videos(self.user["id"], root["id"])), 2)

        database.delete_video_folder(self.user["id"], root["id"])
        folders = database.list_video_folders(self.user["id"])
        videos = database.list_library_videos(self.user["id"])
        self.assertIsNone(next(item for item in folders if item["id"] == child["id"])["parent_id"])
        self.assertIsNone(next(item for item in videos if item["id"] == first["id"])["folder_id"])
        self.assertEqual(next(item for item in videos if item["id"] == second["id"])["folder_id"], child["id"])

    def test_folder_quiz_streams_five_batches_and_saves_latest_quiz(self):
        folder_response = self.client.post("/api/library/folders", json={"name": "Python 课程"})
        self.assertEqual(folder_response.status_code, 200)
        folder_id = folder_response.json()["data"]["id"]
        video = database.upsert_library_video(
            self.user["id"],
            "https://example.com/python",
            {"title": "函数基础", "platform": "Test"},
        )
        database.move_library_video(self.user["id"], video["id"], folder_id)

        with (
            patch("api_library.content_store.load", return_value={
                "subtitle": {"has_subtitle": True, "full_text": "函数可以封装重复逻辑。"},
            }),
            patch("api_summarize._get_summarizer", return_value=FakeSummarizer()),
        ):
            response = self.client.post(
                f"/api/library/folders/{folder_id}/quiz/generate-stream",
                json={"language": "zh"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text.count("event: quiz_batch"), len(QUIZ_BATCH_SPECS))
        latest = self.client.get(f"/api/library/folders/{folder_id}/quiz/latest")
        self.assertEqual(latest.status_code, 200)
        quiz = latest.json()["data"]["quiz"]
        self.assertEqual(len(quiz["questions"]), 16)
        self.assertEqual(quiz["max_score"], 100)
        self.assertEqual(quiz["source_videos"][0]["title"], "函数基础")
        self.assertEqual(quiz["questions"][0]["knowledge_point"], "函数定义")
        self.assertEqual(quiz["questions"][0]["evidence_time_seconds"], 12)
        self.assertEqual(len(database.list_question_bank(self.user["id"], folder_id)), 16)
        self.assertEqual(len(database.list_flashcards(self.user["id"], folder_id)), 16)

    def _create_generated_course(self):
        folder = database.create_video_folder(self.user["id"], "算法课程")
        video = database.upsert_library_video(
            self.user["id"],
            "https://example.com/algorithm",
            {"title": "函数基础", "platform": "Test"},
        )
        database.move_library_video(self.user["id"], video["id"], folder["id"])
        subtitle = {
            "subtitle": {
                "has_subtitle": True,
                "full_text": "函数可以封装重复逻辑。参数用于接收输入。",
                "segments": [
                    {"start": 12, "end": 15, "text": "函数可以封装重复逻辑。"},
                    {"start": 18, "end": 21, "text": "参数用于接收输入。"},
                ],
            },
        }
        with (
            patch("api_library.content_store.load", return_value=subtitle),
            patch("api_summarize._get_summarizer", return_value=FakeSummarizer()),
        ):
            response = self.client.post(
                f"/api/library/folders/{folder['id']}/quiz/generate-stream",
                json={"language": "zh", "mode": "standard", "phase": "pre"},
            )
        self.assertEqual(response.status_code, 200)
        saved = database.get_latest_course_quiz(self.user["id"], folder["id"])
        return folder, json.loads(saved["quiz_json"]), saved["id"], subtitle

    def _record_attempt(self, folder_id, quiz, quiz_id, phase, wrong_ids=()):
        wrong_ids = {str(item) for item in wrong_ids}
        results = []
        answers = {}
        for question in quiz["questions"]:
            correct = str(question["id"]) not in wrong_ids
            points = question["points"]
            results.append({
                "id": question["id"],
                "awarded_points": points if correct else 0,
                "max_points": points,
                "correct": correct,
                "feedback": "测试反馈",
            })
            answers[str(question["id"])] = question.get("answer") or "参考答案"
        total = sum(item["awarded_points"] for item in results)
        response = self.client.post(
            f"/api/library/folders/{folder_id}/attempts",
            json={
                "quiz_id": quiz_id,
                "quiz": quiz,
                "answers": answers,
                "grading": {
                    "total_score": total,
                    "max_score": quiz["max_score"],
                    "results": results,
                },
                "mode": "standard",
                "phase": phase,
            },
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["data"]

    def test_attempt_updates_mastery_wrong_review_and_pre_post_dashboard(self):
        folder, quiz, quiz_id, _ = self._create_generated_course()
        self._record_attempt(folder["id"], quiz, quiz_id, "pre", wrong_ids={1, 2})
        wrong = database.list_wrong_questions(self.user["id"], folder["id"])
        self.assertEqual(len(wrong), 2)
        first_due = datetime.fromisoformat(wrong[0]["due_at"])
        self.assertAlmostEqual(
            (first_due - datetime.now(timezone.utc)).total_seconds(),
            timedelta(days=1).total_seconds(),
            delta=10,
        )

        self._record_attempt(folder["id"], quiz, quiz_id, "post")
        dashboard = self.client.get(
            f"/api/library/folders/{folder['id']}/learning/dashboard"
        ).json()["data"]
        self.assertEqual(dashboard["attempt_count"], 2)
        self.assertGreater(dashboard["post_score"], dashboard["pre_score"])
        self.assertGreater(dashboard["improvement"], 0)
        self.assertTrue(dashboard["mastery"])

    def test_wrong_review_intervals_and_adaptive_bank_reuse(self):
        folder, quiz, quiz_id, subtitle = self._create_generated_course()
        self._record_attempt(folder["id"], quiz, quiz_id, "practice", wrong_ids={1})
        wrong = database.list_wrong_questions(self.user["id"], folder["id"])[0]
        question = wrong["question"]
        question["id"] = 1
        review_quiz = {
            "title": "错题复习",
            "questions": [question],
            "max_score": question["points"],
        }
        for expected_days in (3, 7, 14):
            response = self.client.post(
                f"/api/library/folders/{folder['id']}/attempts",
                json={
                    "quiz": review_quiz,
                    "answers": {"1": question.get("answer") or "参考答案"},
                    "grading": {
                        "total_score": question["points"],
                        "max_score": question["points"],
                        "results": [{
                            "id": 1, "awarded_points": question["points"],
                            "max_points": question["points"], "correct": True,
                            "feedback": "正确",
                        }],
                    },
                    "mode": "wrong",
                    "phase": "practice",
                },
            )
            self.assertEqual(response.status_code, 200)
            current = database.list_wrong_questions(self.user["id"], folder["id"])[0]
            due = datetime.fromisoformat(current["due_at"])
            self.assertAlmostEqual(
                (due - datetime.now(timezone.utc)).total_seconds(),
                timedelta(days=expected_days).total_seconds(),
                delta=10,
            )

        with patch("api_library.content_store.load", return_value=subtitle):
            response = self.client.post(
                f"/api/library/folders/{folder['id']}/quiz/generate-stream",
                json={"mode": "adaptive", "phase": "practice"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn('"reused_from_bank": true', response.text)

    def test_learning_efficiency_workflow(self):
        folder, quiz, quiz_id, subtitle = self._create_generated_course()
        folder_id = folder["id"]
        video = database.list_folder_library_videos(self.user["id"], folder_id)[0]

        progress = self.client.patch(
            f"/api/library/learning/videos/{video['id']}/progress",
            json={"completion_percent": 50, "status": "in_progress", "progress_seconds": 300},
        )
        self.assertEqual(progress.status_code, 200)
        listed_progress = self.client.get(
            f"/api/library/folders/{folder_id}/learning/progress"
        ).json()["data"]
        self.assertEqual(listed_progress[0]["completion_percent"], 50)

        note = self.client.post(
            "/api/library/learning/notes",
            json={"video_id": video["id"], "time_seconds": 12, "content": "函数可以封装逻辑"},
        )
        self.assertEqual(note.status_code, 200)
        note_id = note.json()["data"]["id"]
        self.assertEqual(
            len(self.client.get(f"/api/library/learning/videos/{video['id']}/notes").json()["data"]),
            1,
        )
        self.assertEqual(
            self.client.post(f"/api/library/learning/notes/{note_id}/flashcard").status_code,
            200,
        )
        with patch("api_summarize._get_summarizer", return_value=FakeSummarizer()):
            organized = self.client.post(
                f"/api/library/folders/{folder_id}/learning/notes/organize"
            )
        self.assertEqual(organized.status_code, 200)
        self.assertIn("整理结果", organized.json()["data"]["markdown"])

        exam_date = (date.today() + timedelta(days=30)).isoformat()
        goal = self.client.put(
            f"/api/library/folders/{folder_id}/learning/goal",
            json={"exam_date": exam_date, "target_score": 90, "daily_minutes": 60},
        )
        self.assertEqual(goal.status_code, 200)
        self.assertEqual(goal.json()["data"]["days_left"], 30)

        with patch("api_library.content_store.load", return_value=subtitle):
            search = self.client.post(
                f"/api/library/folders/{folder_id}/learning/search",
                json={"query": "函数封装"},
            )
        self.assertEqual(search.status_code, 200)
        self.assertTrue(search.json()["data"]["results"])
        self.assertEqual(search.json()["data"]["results"][0]["time_seconds"], 12)

        graph = self.client.get(
            f"/api/library/folders/{folder_id}/learning/knowledge-graph"
        ).json()["data"]
        self.assertTrue(graph["nodes"])
        today = self.client.get(
            f"/api/library/folders/{folder_id}/learning/today?minutes=60"
        ).json()["data"]
        self.assertTrue(today["tasks"])
        video_task = next(item for item in today["tasks"] if item["type"] == "video")
        self.assertIn("继续学习", video_task["title"])
        completed = self.client.post(
            f"/api/library/folders/{folder_id}/learning/today/complete",
            json={"task_key": video_task["key"], "completed": True},
        )
        self.assertEqual(completed.status_code, 200)

        with patch("api_efficiency._schedule_pipeline"):
            imported = self.client.post(
                "/api/library/folders/batch-import",
                json={
                    "folder_name": "补充课程",
                    "urls": ["https://example.com/lesson-1", "invalid-url"],
                },
            )
            with patch("api_library._expand_playlist_url", return_value=[
                {"url": "https://example.com/p1", "title": "第一课", "platform": "Test"},
                {"url": "https://example.com/p2", "title": "第二课", "platform": "Test"},
            ]):
                playlist = self.client.post(
                    "/api/library/folders/batch-import",
                    json={"folder_name": "播放列表", "urls": ["https://example.com/playlist?id=1"]},
                )
        self.assertEqual(imported.status_code, 200)
        self.assertEqual(len(imported.json()["data"]["imported"]), 1)
        self.assertEqual(len(imported.json()["data"]["rejected"]), 1)
        self.assertEqual(playlist.status_code, 200)
        self.assertEqual(len(playlist.json()["data"]["imported"]), 2)

        self._record_attempt(folder_id, quiz, quiz_id, "practice", wrong_ids={1})
        diagnoses = self.client.get(
            f"/api/library/folders/{folder_id}/learning/diagnoses"
        ).json()["data"]
        self.assertEqual(len(diagnoses), 1)
        self.assertIn(diagnoses[0]["category"], {
            "概念未理解", "记忆模糊", "题意误读", "知识混淆", "表达不完整",
        })

    def test_flashcard_review_and_new_learning_routes_require_login(self):
        folder, _, _, _ = self._create_generated_course()
        card = database.list_flashcards(self.user["id"], folder["id"])[0]
        video = database.list_folder_library_videos(self.user["id"], folder["id"])[0]
        response = self.client.post(
            f"/api/library/learning/flashcards/{card['id']}/review",
            json={"remembered": True},
        )
        self.assertEqual(response.status_code, 200)
        updated = response.json()["data"]
        self.assertEqual(updated["stage"], 1)
        self.assertIsNotNone(updated["due_at"])

        app.dependency_overrides.pop(get_current_user, None)
        try:
            routes = [
                f"/api/library/folders/{folder['id']}/learning/dashboard",
                f"/api/library/folders/{folder['id']}/learning/question-bank",
                f"/api/library/folders/{folder['id']}/learning/wrong-questions",
                f"/api/library/folders/{folder['id']}/learning/flashcards",
                f"/api/library/folders/{folder['id']}/learning/today",
                f"/api/library/folders/{folder['id']}/learning/progress",
                f"/api/library/folders/{folder['id']}/learning/notes",
                f"/api/library/folders/{folder['id']}/learning/goal",
                f"/api/library/folders/{folder['id']}/learning/knowledge-graph",
                f"/api/library/folders/{folder['id']}/learning/diagnoses",
                f"/api/library/learning/videos/{video['id']}/notes",
            ]
            for route in routes:
                self.assertEqual(self.client.get(route).status_code, 401)
            self.assertEqual(
                self.client.post(
                    f"/api/library/folders/{folder['id']}/attempts",
                    json={"quiz": {}, "grading": {}},
                ).status_code,
                401,
            )
            self.assertEqual(
                self.client.post(
                    f"/api/library/learning/flashcards/{card['id']}/review",
                    json={"remembered": True},
                ).status_code,
                401,
            )
        finally:
            app.dependency_overrides[get_current_user] = lambda: self.user


if __name__ == "__main__":
    unittest.main()
