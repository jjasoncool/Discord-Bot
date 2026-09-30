"""scraper 抓網頁的瀏覽器特徵與每輪統計（services.base_scraper_client 共用層＋各爬蟲）。

守的底線：
  1. 不自己送 Sec-CH-UA／Platform／Mobile，交給 curl_cffi 依瀏覽器目標送出與 UA 一致的值。
     以前手寫的一律報 "Linux"，而 Chrome 目標的 UA 是 macOS、Edge 是 Windows——真瀏覽器不會這樣矛盾。
  2. 共用層預設只用 Firefox 系、且都是目前 curl_cffi 認得的目標（逐站實測只有 Firefox 系在每個網站都不被擋）；
     認不得的會被剔除，全都認不得時退回 "firefox"；curl_cffi 將來拿掉 BrowserType 時照樣 import（不過濾）。
  3. 一輪共用一個 session（run_session）：區塊內每次拿到的都是同一個、呼叫端的 with 不會把它關掉、
     離開區塊才關；巢狀沿用外層；區塊外照舊每次新建。HKEPC、PTT、官網一輪都只建一個 session。
  4. 巴哈每輪回報統計（請求次數含留言 XHR、成功頁數、等待秒數、耗時），每輪重新計、不累加，
     每一處等待都算進去，並寫進「任務完成」那行 log；中途拋例外時也記一行「中斷」與做到哪。

不連網、不碰資料庫：請求與 session 都以假物件取代。
"""

import ast
import importlib
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from curl_cffi.requests import BrowserType

from services import api_service as api_module
from services import bahamut_scraper_service as bahamut_module
from services import base_scraper_client as base_module
from services import hkepc_scraper_service as hkepc_module
from services import ptt_scraper_service as ptt_module
from services import scraper_service as scraper_module


def _client_hint_keys(headers):
    return [k for k in headers if k.lower().startswith("sec-ch-ua")]


class _FakeSession:
    def __init__(self, response=None):
        self.closed = False
        self.response = response
        self.get = mock.MagicMock(return_value=response)
        self.cookies = {}

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


class ClientHintTests(unittest.TestCase):

    def test_headers_leave_client_hints_to_curl_cffi(self):
        client = base_module.BaseScraperClient()
        for target in ["chrome150", "safari2601", *base_module.DEFAULT_IMPERSONATE_POOL]:
            client._current_impersonate = target
            client._current_local_fp = None
            with self.subTest(target=target):
                self.assertEqual(_client_hint_keys(client._build_page_headers()), [])
                self.assertEqual(_client_hint_keys(client._build_page_headers(referer="https://www.hkepc.com/")), [])
                self.assertEqual(_client_hint_keys(client._build_xhr_headers("https://forum.gamer.com.tw/C.php?bsn=1")), [])


class ImpersonatePoolTests(unittest.TestCase):

    def test_default_pool_is_supported_firefox_only(self):
        supported = {b.value for b in BrowserType}
        pool = base_module.DEFAULT_IMPERSONATE_POOL
        self.assertTrue(pool)
        self.assertEqual([t for t in pool if t not in supported], [])
        self.assertEqual([t for t in pool if not t.startswith("firefox")], [])

    def test_unknown_targets_are_dropped_and_fall_back_to_firefox(self):
        self.assertEqual(base_module._supported_only(["firefox147", "no_such_browser1"]), ["firefox147"])
        self.assertEqual(base_module._supported_only(["no_such_browser1"]), ["firefox"])

    def test_without_a_supported_list_targets_are_kept(self):
        self.assertEqual(base_module._supported_only(["firefox147", "x"], supported=None), ["firefox147", "x"])

    def test_module_still_imports_when_curl_cffi_drops_browser_type(self):
        import curl_cffi.requests as cr
        saved = cr.BrowserType
        try:
            del cr.BrowserType
            mod = importlib.reload(base_module)
            self.assertEqual(mod.DEFAULT_IMPERSONATE_POOL, mod.FIREFOX_TARGETS)
        finally:
            cr.BrowserType = saved
            importlib.reload(base_module)


class RunSessionTests(unittest.TestCase):

    def setUp(self):
        self.client = base_module.BaseScraperClient()
        self.made = []

        def new_session():
            s = _FakeSession()
            self.made.append(s)
            return s
        patcher = mock.patch.object(self.client, "_new_session", side_effect=new_session)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_one_session_inside_a_run_and_closed_only_at_the_end(self):
        with self.client.run_session():
            with self.client._build_session() as a:
                pass
            with self.client._build_session() as b:
                self.assertFalse(a.closed)  # 呼叫端的 with 結束不會關掉本輪共用的 session
            with self.client.run_session() as nested:
                pass
            self.assertFalse(a.closed)
        self.assertIs(a, b)
        self.assertIs(nested, a)
        self.assertEqual(len(self.made), 1)
        self.assertTrue(a.closed)

    def test_outside_a_run_each_call_builds_a_new_session(self):
        with self.client._build_session() as a:
            pass
        with self.client._build_session() as b:
            pass
        self.assertIsNot(a, b)
        self.assertEqual(len(self.made), 2)
        self.assertTrue(a.closed and b.closed)


class OneSessionPerRunTests(unittest.TestCase):
    """三個原本「每個請求開新 session」的爬蟲，跑一輪都只建一個 session。"""

    LISTING = """
      <div class="item"><a class="heading" href="/26838/a">標題一</a>
        <div class="introduction">摘要一</div><div class="date">2026-09-30</div></div>
      <div class="item"><a class="heading" href="/26837/b">標題二</a>
        <div class="introduction">摘要二</div><div class="date">2026-09-30</div></div>
    """
    DETAIL = '<div class="content"><div class="text">完整內文</div></div>'

    def _count_sessions(self, svc):
        made = []

        def new_session():
            s = _FakeSession()
            made.append(s)
            return s
        return made, mock.patch.object(svc, "_new_session", side_effect=new_session)

    def test_hkepc_listing_and_detail_pages_share_one_session(self):
        db = mock.MagicMock()
        db.get_hardware_news_ids_with_content.return_value = set()
        svc = hkepc_module.HkepcScraperService(db_manager=db)
        svc.tags = ["IT快訊"]
        svc.pages_per_tag = 2
        used = []

        def fake_fetch(sess, url, **kwargs):
            used.append(sess)
            html = self.LISTING if "/tag/" in url else self.DETAIL
            return SimpleNamespace(text=html, raise_for_status=lambda: None)

        made, patch_new = self._count_sessions(svc)
        with patch_new, mock.patch.object(svc, "_fetch_with_retry", side_effect=fake_fetch), \
             mock.patch.object(hkepc_module, "human_sleep"):
            items = svc.fetch_hkepc_articles()

        self.assertEqual(len(made), 1)
        self.assertEqual(len(used), 4)  # 列表 2 頁＋內頁 2 篇
        self.assertTrue(all(s is made[0] for s in used))
        self.assertEqual(sorted(i["hkepc_id"] for i in items), [26837, 26838])
        self.assertTrue(all(i["content"] == "完整內文" for i in items))

    def test_ptt_run_shares_one_session(self):
        svc = ptt_module.PTTScraperService(db_manager=mock.MagicMock())
        used = []

        def fake_fetch(sess, url, **kwargs):
            used.append(sess)
            return SimpleNamespace(text="<html></html>", raise_for_status=lambda: None)

        def fake_run():
            svc._fetch_html("https://www.ptt.cc/bbs/C_Chat/search?page=1")
            svc._fetch_html("https://www.ptt.cc/bbs/C_Chat/M.1.A.1.html")
            return {"ok": True, "articles": []}

        made, patch_new = self._count_sessions(svc)
        with patch_new, mock.patch.object(svc, "_fetch_with_retry", side_effect=fake_fetch), \
             mock.patch.object(svc, "_fetch_articles_with_content", side_effect=fake_run):
            svc.fetch_ptt_articles_with_content()

        self.assertEqual(len(made), 1)
        self.assertEqual(len(used), 2)
        self.assertTrue(all(s is made[0] for s in used))

    def test_official_article_run_shares_one_session(self):
        api = api_module.APIService(timeout=5, default_delay=0)
        response = SimpleNamespace(headers={"content-type": "application/json"}, json=lambda: {"ok": 1},
                                   raise_for_status=lambda: None)
        made = []

        def new_session():
            s = _FakeSession(response)
            made.append(s)
            return s

        scraper = scraper_module.ScraperService(db_manager=mock.MagicMock(), api_service=api, file_service=mock.MagicMock())

        def fake_run():
            api.fetch_data("https://example.invalid/menu.json")
            api.fetch_data("https://example.invalid/article/1.json")
            return True

        with mock.patch.object(api, "_new_session", side_effect=new_session), \
             mock.patch.object(api_module.time, "sleep"), \
             mock.patch.object(scraper, "_scrape_articles", side_effect=fake_run):
            self.assertTrue(scraper.scrape_articles())

        self.assertEqual(len(made), 1)
        self.assertEqual(made[0].get.call_count, 2)
        self.assertTrue(made[0].closed)


class BahamutStatsTests(unittest.TestCase):

    def setUp(self):
        self.clock = [0.0]
        self.svc = bahamut_module.BahamutScraperService()
        page = SimpleNamespace(status_code=200, url="https://forum.gamer.com.tw/B.php?bsn=74934",
                               text="<html></html>", history=[], headers={})
        self.session = SimpleNamespace(get=mock.MagicMock(return_value=page), cookies={})
        self.broken_session = SimpleNamespace(get=mock.MagicMock(side_effect=RuntimeError("boom")), cookies={})

    def _fake_run(self):
        svc = self.svc
        svc._fetch_html(self.session, "https://forum.gamer.com.tw/B.php?bsn=74934")
        svc._sleep(2, 5)
        svc._fetch_html(self.session, "https://forum.gamer.com.tw/C.php?bsn=74934&snA=1")
        svc._fetch_comments_via_xhr(self.broken_session, "74934", "123", "https://forum.gamer.com.tw/")
        self.clock[0] += 1.5  # 請求本身花的時間
        return {"ok": True, "articles": []}

    def _run_once(self):
        def fake_sleep(a, b):
            self.clock[0] += a
        with mock.patch.object(bahamut_module, "human_sleep", side_effect=fake_sleep), \
             mock.patch.object(bahamut_module.time, "monotonic", side_effect=lambda: self.clock[0]), \
             mock.patch.object(self.svc, "_fetch_articles_with_content", side_effect=self._fake_run):
            return self.svc.fetch_bahamut_articles_with_content()

    def test_run_reports_requests_pages_sleep_and_elapsed(self):
        stats = self._run_once()["stats"]
        self.assertEqual(stats["requests"], 3)       # 2 頁＋1 次留言 XHR（失敗也算一次請求）
        self.assertEqual(stats["xhr_requests"], 1)
        self.assertEqual(stats["pages"], 2)
        self.assertAlmostEqual(stats["sleep_seconds"], 2.0)
        self.assertAlmostEqual(stats["elapsed_seconds"], 3.5)

    def test_every_wait_goes_through_the_counter(self):
        # 等待只准經過 _sleep，否則那段時間不會算進「等待」；新增等待時直接呼叫 human_sleep 會被擋
        tree = ast.parse(Path(bahamut_module.__file__).read_text(encoding="utf-8"))
        offenders = [
            f"{fn.name}:{node.lineno}"
            for fn in ast.walk(tree) if isinstance(fn, ast.FunctionDef) and fn.name != "_sleep"
            for node in ast.walk(fn)
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "human_sleep"
        ]
        self.assertEqual(offenders, [])

    def test_interrupted_run_keeps_its_stats(self):
        def broken_run():
            self.svc._fetch_html(self.session, "https://forum.gamer.com.tw/B.php?bsn=74934")
            raise RuntimeError("Bahamut 抓取失敗（重試耗盡）")
        with mock.patch.object(self.svc, "_fetch_articles_with_content", side_effect=broken_run):
            with self.assertRaises(RuntimeError):
                self.svc.fetch_bahamut_articles_with_content()
        self.assertEqual(self.svc.last_stats["requests"], 1)

    def test_each_run_starts_from_zero(self):
        self._run_once()
        stats = self._run_once()["stats"]
        self.assertEqual(stats["requests"], 3)
        self.assertEqual(stats["pages"], 2)

    def test_completion_log_line_shows_the_stats(self):
        import main
        line = main._format_bahamut_stats(
            {"elapsed_seconds": 4440, "sleep_seconds": 3100, "requests": 950, "xhr_requests": 120, "pages": 830},
            save_seconds=240,
        )
        for part in ("抓取 4440 秒", "等待 3100 秒", "寫入 240 秒", "請求 950 次", "XHR 120 次", "頁面 830 頁"):
            self.assertIn(part, line)
        self.assertEqual(main._format_bahamut_stats(None), "（無統計）")

    def test_interrupted_run_is_logged_with_its_stats(self):
        import main
        def boom():
            raise RuntimeError("boom")
        service = SimpleNamespace(fetch_bahamut_articles_with_content=boom,
                                  last_stats={"elapsed_seconds": 60, "sleep_seconds": 40, "requests": 25, "xhr_requests": 0, "pages": 24})
        with mock.patch.object(main, "logger") as log:
            with self.assertRaises(RuntimeError):
                main._run_bahamut_scrape(service, "公開看板")
        line = log.warning.call_args.args[0] % log.warning.call_args.args[1:]
        self.assertIn("中斷", line)
        self.assertIn("請求 25 次", line)


if __name__ == "__main__":
    unittest.main()
