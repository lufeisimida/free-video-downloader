import json
import unittest

from api_summarize import (
    SUMMARY_FORMAT_VERSION,
    _summary_cache_is_current,
    _summary_source_text,
)
from summarizer import QUIZ_BATCH_SPECS, VideoSummarizer


class FakeProvider:
    def __init__(self, payload):
        self.payload = payload
        self.max_tokens = None

    def complete_chat(self, messages, *, temperature, max_tokens):
        self.max_tokens = max_tokens
        return json.dumps(self.payload, ensure_ascii=False)


class QuizBatchTests(unittest.TestCase):
    def test_summary_prompt_requires_grounded_video_examples(self):
        prompt = VideoSummarizer._build_summary_prompt(
            "[00:00:12] 讲者用订单处理演示状态变化。", "zh"
        )

        self.assertIn("## 视频中的讲解示例", prompt)
        self.assertIn("例子内容", prompt)
        self.assertIn("对应知识点", prompt)
        self.assertIn("理解与迁移", prompt)
        self.assertIn("不得用常识自行补充或编造", prompt)
        self.assertIn("本视频以概念讲解为主，未提供明确的具体示例", prompt)
        self.assertGreaterEqual(SUMMARY_FORMAT_VERSION, 2)

    def test_summary_source_preserves_segment_timestamps(self):
        source = _summary_source_text({
            "full_text": "回退文本",
            "segments": [
                {"start": 12.8, "text": "第一个例子"},
                {"start": 3661, "text": "跨小时案例"},
            ],
        })

        self.assertEqual(
            source,
            "[00:00:12] 第一个例子\n[01:01:01] 跨小时案例",
        )
        self.assertEqual(
            _summary_source_text({"full_text": "只有纯文本", "segments": []}),
            "只有纯文本",
        )

    def test_summary_cache_version_refreshes_legacy_content(self):
        self.assertFalse(_summary_cache_is_current({"summary": "旧摘要"}))
        self.assertFalse(_summary_cache_is_current({
            "summary": "异常版本摘要", "summary_format_version": "unknown",
        }))
        self.assertTrue(_summary_cache_is_current({
            "summary": "含示例的新摘要",
            "summary_format_version": SUMMARY_FORMAT_VERSION,
        }))

    def test_batch_specs_keep_full_quiz_at_one_hundred_points(self):
        self.assertEqual(sum(spec["count"] for spec in QUIZ_BATCH_SPECS), 16)
        self.assertEqual(
            sum(spec["count"] * spec["points"] for spec in QUIZ_BATCH_SPECS),
            100,
        )

    def test_legacy_quiz_normalizer_keeps_clear_count_error(self):
        with self.assertRaisesRegex(ValueError, "单选题数量不足"):
            VideoSummarizer._normalize_quiz({"questions": []})

    def test_single_choice_batch_assigns_continuous_ids_and_points(self):
        spec = QUIZ_BATCH_SPECS[0]
        payload = {
            "title": "测试题卷",
            "questions": [
                {
                    "type": "single",
                    "question": f"第 {index} 题",
                    "options": [
                        {"key": "A", "text": "正确项"},
                        {"key": "B", "text": "干扰项"},
                        {"key": "C", "text": "干扰项"},
                        {"key": "D", "text": "干扰项"},
                    ],
                    "answer": ["A"],
                    "explanation": "来自视频内容。",
                }
                for index in range(1, 6)
            ],
        }
        summarizer = VideoSummarizer.__new__(VideoSummarizer)
        summarizer.provider = FakeProvider(payload)

        batch = summarizer.generate_quiz_batch("视频文本", "zh", spec, 6)

        self.assertEqual(batch["title"], "测试题卷")
        self.assertEqual([item["id"] for item in batch["questions"]], [6, 7, 8, 9, 10])
        self.assertTrue(all(item["points"] == 4 for item in batch["questions"]))
        self.assertEqual(summarizer.provider.max_tokens, spec["max_tokens"])


if __name__ == "__main__":
    unittest.main()
