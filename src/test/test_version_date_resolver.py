"""版本時間解析（services.events.event_scheduler.VersionDateResolver）。

守的底線：
- bot 長時間不重啟：啟動後才發的版本公告，`refresh()` 之後就看得到（活動自動發布、週期提醒都靠它）
- articles.db 是 WAL 模式、爬蟲一直在寫：還沒合併回主檔的新公告也要讀得到（不能用 immutable 開檔）
- 讀取失敗時保留上一次的結果，不把已知的版本洗掉
- 版本更新開始時刻＝官方維護時間，或下半卡池結束日隔天 04:00；官方時間優先，只看時間不看版本號

執行：
    cd src && python -m unittest test.test_version_date_resolver -v
"""

import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from services.events.event_scheduler import VersionDateResolver  # noqa: E402
from services.events.event_time_parser import SERVER_TZ  # noqa: E402


def T(month, day, hour=0, minute=0, year=2026):
    return datetime(year, month, day, hour, minute, tzinfo=SERVER_TZ)


MAINT_36 = ("《鳴潮》3.6版本更新維護預告",
            "<p>✦更新維護時間： 2026年8月20日04:00 ~ 2026年8月20日11:00（UTC+8）</p>")
MAINT_37 = ("《鳴潮》3.7版本更新維護預告",
            "<p>✦更新維護時間： 2026年9月30日04:00 ~ 2026年9月30日11:00（UTC+8）</p>")
BANNER_36 = ("【3.6版本】[角色/武器活動喚取・第二期]",
             "✦活動時間：2026年9月10日10:00 ~ 2026年9月29日11:59（伺服器時間）")
BANNER_37 = ("【3.7版本】[角色/武器活動喚取・第二期]",
             "✦活動時間：2026年10月21日10:00 ~ 2026年11月11日11:59（伺服器時間）")


class DbTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name, "articles.db")

    def write(self, rows, *, con=None):
        own = con is None
        con = con or sqlite3.connect(self.path)
        con.execute("CREATE TABLE IF NOT EXISTS article_details (article_title TEXT, article_content TEXT)")
        con.executemany("INSERT INTO article_details VALUES (?, ?)", rows)
        con.commit()
        if own:
            con.close()
        return con


class LongRunningBotTests(DbTestBase):
    def test_refresh_sees_version_announced_after_start(self):
        self.write([MAINT_36])
        resolver = VersionDateResolver(db_path=self.path)
        resolver.refresh()
        self.assertIsNone(resolver.update_time("3.7"))
        self.write([MAINT_37])  # bot 啟動後才發的公告
        resolver.refresh()
        self.assertEqual(resolver.update_time("3.7"), T(9, 30, 11))

    def test_update_time_does_not_touch_db_once_loaded(self):
        self.write([MAINT_36])
        resolver = VersionDateResolver(db_path=self.path)
        resolver.refresh()
        with patch.object(resolver, "_load", wraps=resolver._load) as load:
            resolver.update_time("3.6")
            resolver.update_time("9.9")
        load.assert_not_called()  # 規劃活動時在 event loop 裡，不能碰 DB

    def test_failed_refresh_keeps_known_versions(self):
        self.write([MAINT_36])
        resolver = VersionDateResolver(db_path=self.path)
        resolver.refresh()
        resolver.db_path = Path(self.tmp.name, "missing.db")
        resolver.refresh()
        self.assertEqual(resolver.update_time("3.6"), T(8, 20, 11))


class WalVisibilityTests(DbTestBase):
    def test_reads_rows_still_in_wal(self):
        writer = sqlite3.connect(self.path)
        self.addCleanup(writer.close)
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("PRAGMA wal_autocheckpoint=0")  # 不自動合併，資料只在 WAL 裡
        self.write([MAINT_37], con=writer)
        self.assertTrue(Path(str(self.path) + "-wal").stat().st_size > 0)

        resolver = VersionDateResolver(db_path=self.path)
        resolver.refresh()
        self.assertEqual(resolver.update_time("3.7"), T(9, 30, 11))
        self.assertEqual(resolver.update_starts(), [T(9, 30, 4)])


class UpdateStartsTests(DbTestBase):
    """版本更新開始時刻：官方維護時間＋下半卡池結束日隔天 04:00；只看時間、不看版本號。"""

    def test_official_and_banner_derived(self):
        self.write([MAINT_37, BANNER_36, BANNER_37,
                    ("伺服器停機維護公告", "更新維護時間：2026年10月15日04:00 ~ 06:00")])
        self.assertEqual(VersionDateResolver(db_path=self.path).update_starts(), [T(9, 30, 4), T(11, 12, 4)])

    def test_official_notice_wins_over_banner(self):
        delayed = ("《鳴潮》4.0版本更新維護預告", "更新維護時間：2026年11月13日04:00 ~ 2026年11月13日11:00")
        self.write([MAINT_37, BANNER_37, delayed])
        self.assertEqual(VersionDateResolver(db_path=self.path).update_starts(), [T(9, 30, 4), T(11, 13, 4)])

    def test_unreadable_db_returns_empty(self):
        self.assertEqual(VersionDateResolver(db_path=Path(self.tmp.name, "missing.db")).update_starts(), [])


if __name__ == "__main__":
    unittest.main()
