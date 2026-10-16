"""通知伺服器的共用密鑰（services/notify_server：NOTIFY_SHARED_SECRET、header X-Notify-Secret）。

守的底線：
  - 有設密鑰：沒帶或帶錯的通知回 401、不會排進處理；帶對的照常受理
  - 沒設密鑰：照常受理（升級順序不受限），但啟動時警告一次
  - 健康檢查不需要密鑰

不開 port：直接呼叫處理函式，請求是假物件；背景處理用假的 spawn 接住。
"""
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from services import notify_server  # noqa: E402
from sys_settings.notify_settings import NotifyServerSettings  # noqa: E402


def request(source="fb", headers=None):
    async def body():
        return {}
    return SimpleNamespace(match_info={"source": source}, headers=headers or {}, remote="172.18.0.3", json=body)


class NotifySecretTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.spawned = []

        def fake_spawn(coro, name=None):
            coro.close()
            self.spawned.append(name)

        self.enterContext(mock.patch.object(notify_server, "spawn", fake_spawn))

    def server(self, secret):
        return notify_server.NotifyServer(SimpleNamespace(), settings=NotifyServerSettings(shared_secret=secret))

    async def test_missing_or_wrong_secret_is_rejected(self):
        server = self.server("s3cret")
        for headers in ({}, {notify_server.SECRET_HEADER: "wrong"}):
            with self.subTest(headers=headers), self.assertLogs(notify_server.logger, "WARNING"):
                response = await server._handle_notify(request(headers=headers))
                self.assertEqual(401, response.status)
        self.assertEqual([], self.spawned, "沒通過驗證的通知不能排進處理")

    async def test_matching_secret_is_accepted(self):
        server = self.server("s3cret")
        response = await server._handle_notify(request(headers={notify_server.SECRET_HEADER: "s3cret"}))
        self.assertEqual(200, response.status)
        self.assertEqual(1, len(self.spawned))

    async def test_without_secret_everything_is_accepted_but_startup_warns(self):
        server = self.server("")
        response = await server._handle_notify(request())
        self.assertEqual(200, response.status)
        self.assertEqual(1, len(self.spawned))
        with self.assertLogs(notify_server.logger, "WARNING"):
            server._warn_if_unprotected()

    async def test_health_check_needs_no_secret(self):
        response = await self.server("s3cret")._handle_health(request())
        self.assertEqual(200, response.status)


class EverySenderCarriesTheSecretTests(unittest.TestCase):
    """爬蟲程式裡每一個打 bot /notify 的 POST 都要帶 notify_headers()：密鑰只做一半（有的呼叫帶、有的沒帶）等於沒做。"""

    def test_every_notify_post_in_the_scraper_sends_the_header(self):
        import ast
        from pathlib import Path

        scraper_dir = Path(SRC_DIR) / "scraper"
        notify_posts, missing = [], []
        for path in scraper_dir.rglob("*.py"):
            rel = path.relative_to(scraper_dir).as_posix()
            if rel.startswith("tests/") or "__pycache__" in rel:
                continue
            source = path.read_text(encoding="utf-8")
            # 以「函式」為單位看：網址常先放進變數再 post，所以只看 post 那一行會漏掉
            for func in ast.walk(ast.parse(source)):
                if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                body = ast.get_source_segment(source, func) or ""
                if "/notify" not in body and "NOTIFY_URL" not in body:
                    continue
                for node in ast.walk(func):
                    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "post"):
                        continue
                    notify_posts.append(f"{rel}:{node.lineno}")
                    headers = [kw.value for kw in node.keywords if kw.arg == "headers"]
                    carries = any(isinstance(v, ast.Call) and getattr(v.func, "id", getattr(v.func, "attr", "")) == "notify_headers"
                                  for v in headers)
                    if not carries:
                        missing.append(f"{rel}:{node.lineno}")
        self.assertGreaterEqual(len(notify_posts), 2, f"打 /notify 的地方應該不只這些：{notify_posts}（守衛掃錯位置了）")
        self.assertEqual([], missing, "這些 POST 沒帶 headers=notify_headers()，密鑰會做一半")


if __name__ == "__main__":
    unittest.main()
