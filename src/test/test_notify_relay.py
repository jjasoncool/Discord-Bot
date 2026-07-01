"""notify_server 共用來源模組（_process_relay / _RELAY_SOURCES）守門測試。

守的是「fb / article / it_article 收斂成單一 _process_relay」這次重構，避免改壞現役
FB / IT 推送，並確認巴哈維持自有 handler（不被併進泛用表）。

執行：
    cd src && python -m unittest test.test_notify_relay -v
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from services.notify_server import NotifyServer, _RELAY_SOURCES


class _DummyBot:
    def get_channel(self, _cid):
        return None


class RelayRegistryTests(unittest.TestCase):
    """_RELAY_SOURCES 註冊表結構。"""

    def test_expected_sources_present(self):
        self.assertEqual(set(_RELAY_SOURCES), {"fb", "article", "it_article"})

    def test_bahamut_not_in_relay(self):
        # 巴哈是真特例（單篇/批次＋forum slot/edit），不可被併進泛用表
        self.assertNotIn("bahamut", _RELAY_SOURCES)

    def test_each_source_has_required_fields(self):
        for src, spec in _RELAY_SOURCES.items():
            for key in ("config_key", "module", "cls", "method"):
                self.assertIn(key, spec, f"{src} 缺欄位 {key}")

    def test_fb_article_share_channel_key(self):
        # FB 與 Article 都發進 article_monitor_channel_id（活動偵測閘門依賴此一致性）
        self.assertEqual(_RELAY_SOURCES["fb"]["config_key"], "article_monitor_channel_id")
        self.assertEqual(_RELAY_SOURCES["article"]["config_key"], "article_monitor_channel_id")

    def test_it_article_uses_hardware_channel(self):
        self.assertEqual(_RELAY_SOURCES["it_article"]["config_key"], "hardware_news_channel_id")


class HandlerWiringTests(unittest.TestCase):
    """dispatch table 接線：四個來源都在、巴哈仍指自有 handler。"""

    def setUp(self):
        self.server = NotifyServer(_DummyBot())

    def test_all_sources_registered(self):
        self.assertEqual(set(self.server._handlers), {"bahamut", "fb", "article", "it_article"})

    def test_bahamut_uses_own_handler(self):
        self.assertEqual(self.server._handlers["bahamut"], self.server._process_bahamut)

    def test_relay_sources_are_callable(self):
        for src in ("fb", "article", "it_article"):
            self.assertTrue(callable(self.server._handlers[src]))


if __name__ == "__main__":
    unittest.main()
