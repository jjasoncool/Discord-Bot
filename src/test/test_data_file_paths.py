"""資料檔的位置只由專案根目錄（`sys_settings.paths.APP_ROOT`）決定，不隨程式檔搬動而變。

守的底線：
  這幾個資料檔以前用「自己這個程式檔所在的位置」去找，搬動或改名程式檔就會算到另一個位置——
  最危險的是 `services/state_db.py`：它會默默開一個新的空 `sent_articles.db`，所有轉發都以為沒發過，
  把舊文章重發一遍。現在它們都從 `APP_ROOT` 推（容器裡是 /app），這裡釘住每個檔相對根目錄的位置：
  有人改回看程式檔位置、或把檔搬到別的子目錄，啟動 gate 就擋下來，而不是上線後才發現。

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
        from sys_settings.paths import APP_ROOT
        self.assertEqual(Path(actual), APP_ROOT.joinpath(*expected_parts))

    def test_sent_articles_db(self):
        from services import state_db
        self.assertLocation(state_db.DEFAULT_DB_PATH, "services", "sent_articles.db")

    def test_article_relay_config(self):
        from services.relay import base_monitor
        self.assertLocation(base_monitor._ARTICLE_RUNTIME_PATH, "settings", "article_relay.json")

    def test_rollcall_state(self):
        from services.community import rollcall_service
        self.assertLocation(rollcall_service.RUNTIME_FILE, "settings", "runtime", "rollcall.json")

    def test_scraper_articles_db(self):
        from services.events import event_scheduler
        self.assertLocation(event_scheduler._ARTICLES_DB, "scraper", "articles.db")

    def test_logging_config(self):
        from utils import logger_config
        self.assertLocation(logger_config.CONFIG_PATH, "settings", "logging.json")

    def test_music_cache_dir(self):
        from music import ytdl
        self.assertLocation(ytdl.CACHE_DIR, "music", "cache")

    def test_music_playlists_and_state(self):
        from music import config
        self.assertLocation(config.MUSIC_PLAYLISTS_PATH, "settings", "music_playlists.json")
        self.assertLocation(config.MUSIC_STATE_PATH, "settings", "runtime", "music.json")

    def test_switches_and_item_prices(self):
        from services.community import item_prices
        from sys_settings import switches
        self.assertLocation(switches.SWITCHES_PATH, "settings", "switches.json")
        self.assertLocation(item_prices.PRICES_PATH, "settings", "runtime", "item_prices.json")

    def test_every_runtime_file_lives_in_the_runtime_folder(self):
        """bot 執行時寫的檔全部在 settings/runtime/（整個資料夾不進版控）；誰放到別處就會又出現在 git 清單裡。"""
        from commands import community_lookup_commands, management_commands, telegram_quarantine_commands, user_commands
        from services.relay import telegram_quarantine
        from sys_settings.periodic_reminder_settings import PeriodicReminderSettings
        for actual, name in (
            (management_commands.INTRO_PANEL_RUNTIME_FILE, "intro_panel.json"),
            (management_commands.INTRO_SUBMISSION_RUNTIME_FILE, "intro_submissions.json"),
            (community_lookup_commands.COMMUNITY_PANEL_RUNTIME_FILE, "community_panel.json"),
            (telegram_quarantine_commands.PANEL_RUNTIME_PATH, "telegram_quarantine_panel.json"),
            (telegram_quarantine.RUNTIME_PATH, "telegram_quarantine.json"),
            (user_commands.monitored_channels_file, "monitored_channels.json"),
            (PeriodicReminderSettings().runtime_path, "periodic_reminder.json"),
        ):
            with self.subTest(name=name):
                self.assertLocation(actual, "settings", "runtime", name)


if __name__ == "__main__":
    unittest.main()
