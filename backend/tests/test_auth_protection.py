import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app
from auth import sync_builtin_account
from settings import get_builtin_account_config


class AuthProtectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_health_stays_public(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)

    def test_registration_is_disabled_but_can_be_reenabled(self):
        config_response = self.client.get("/api/auth/config")
        self.assertEqual(config_response.status_code, 200)
        self.assertFalse(config_response.json()["data"]["registration_enabled"])

        disabled_response = self.client.post(
            "/api/auth/register",
            json={"email": "new-user@example.com", "password": "strong-password"},
        )
        self.assertEqual(disabled_response.status_code, 403)
        self.assertEqual(disabled_response.json()["detail"], "注册功能已关闭")

        with (
            patch.dict("os.environ", {"REGISTRATION_ENABLED": "true"}),
            patch("api_auth.get_user_by_email", return_value=None),
            patch("api_auth.create_user", return_value={"id": 999, "email": "new-user@example.com"}),
            patch("api_auth.hash_password", return_value="password-hash"),
        ):
            enabled_response = self.client.post(
                "/api/auth/register",
                json={"email": "new-user@example.com", "password": "strong-password"},
            )
        self.assertEqual(enabled_response.status_code, 200)

    def test_builtin_account_can_login_with_all_features(self):
        sync_builtin_account()
        email, password = get_builtin_account_config()
        response = self.client.post(
            "/api/auth/login",
            json={"email": email, "password": password},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertTrue(data["token"])
        self.assertEqual(data["user"]["email"], email)
        self.assertTrue(data["user"]["is_vip"])

    def test_video_endpoints_require_login(self):
        cases = (
            ("post", "/api/parse", {"json": {"url": "https://example.com/video"}}),
            ("post", "/api/direct-url", {"json": {"url": "https://example.com/video"}}),
            ("post", "/api/download", {"json": {"url": "https://example.com/video"}}),
            ("get", "/api/proxy/thumbnail", {"params": {"url": "https://example.com/a.jpg"}}),
        )
        for method, path, kwargs in cases:
            with self.subTest(path=path):
                response = getattr(self.client, method)(path, **kwargs)
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.json()["detail"], "请先登录")

    def test_ai_and_model_config_require_login(self):
        cases = (
            ("post", "/api/summarize", {"json": {"url": "https://example.com/video"}}),
            ("post", "/api/chat", {"json": {"url": "https://example.com/video", "question": "测试"}}),
            ("post", "/api/quiz/generate-stream", {"json": {"url": "https://example.com/video"}}),
            ("get", "/api/model-config", {}),
            ("post", "/api/model-config/test", {"json": {}}),
            ("get", "/api/library", {}),
            ("post", "/api/library/folders", {"json": {"name": "课程"}}),
        )
        for method, path, kwargs in cases:
            with self.subTest(path=path):
                response = getattr(self.client, method)(path, **kwargs)
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.json()["detail"], "请先登录")


if __name__ == "__main__":
    unittest.main()
