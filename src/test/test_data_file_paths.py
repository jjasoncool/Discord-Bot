"""資料檔的位置不能因為搬動程式檔而改變。

守的底線：
  下面這幾個模組用「自己這個程式檔所在的位置」去找資料檔。只要有人搬動或改名這些程式檔，
  算出來的就會是另一個位置——最危險的是 `services/state_db.py`：它會默默開一個新的空
  `sent_articles.db`，所有轉發都以為沒發過，把舊文章重發一遍。這裡把每個資料檔的實際位置
  釘死，搬檔時啟動 gate 就擋下來（bot 起不來），而不是上線後才發現。
  真的要搬這些程式檔時，把路徑改成不依賴程式檔位置的寫法，並確認資料檔本身不動。

只比對位置、不要求檔案存在：這些多半是不進版控的執行期資料，乾淨的副本裡本來就沒有。
"""

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC_DIR = HERE.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


class DataFileLocationTests(unittest.TestCase):

    def assertLocation(self, actual, *expected_parts):
        self.assertEqual(Path(actual).resolve(), SRC_DIR.joinpath(*expected_parts).resolve())

    def test_sent_articles_db(self):
        from services import state_db
        self.assertLocation(state_db.DEFAULT_DB_PATH, "services", "sent_articles.db")

    def test_article_runtime_config(self):
        from services.relay import base_monitor
        self.assertLocation(base_monitor._ARTICLE_RUNTIME_PATH, "settings", "article_runtime.json")

    def test_rollcall_runtime(self):
        from services.community import rollcall_service
        self.assertLocation(rollcall_service.RUNTIME_FILE, "settings", "rollcall_runtime.json")

    def test_scraper_articles_db(self):
        from services.events import event_scheduler
        self.assertLocation(event_scheduler._ARTICLES_DB, "scraper", "articles.db")

    def test_logging_config(self):
        from utils import logger_config
        self.assertLocation(logger_config.CONFIG_PATH, "settings", "logging.json")

    def test_music_cache_dir(self):
        from music import ytdl
        self.assertLocation(ytdl.CACHE_DIR, "music", "cache")


if __name__ == "__main__":
    unittest.main()
