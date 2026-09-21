"""活動排程副作用層：建立 / 升級 / 指紋遷移 的行為測試。

守的是「確保活動不會重複發，且後到的更好來源能把既有活動補完整」這件事：
  - 同一活動被不同來源二度報導 → 升級既有活動，不再建第二個
  - 匯總帖先到（無圖）、FB 專屬貼文後到（有圖）→ 封面與描述都補上（實測相隔 7~28 天）
  - 後到的來源內容比較差 → 不准把既有內容洗掉
  - 官方改期（同活動名、區間重疊）→ 改既有活動的時間，不新建
  - 不同檔期（同活動名、區間不重疊）→ 各自建，不可誤併
  - 活動已被使用者從 Discord 刪掉 → 不重建

執行：
    cd src && python -m unittest test.test_event_upgrade -v
"""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from services import event_scheduler as ES

CHANNEL_ID = 1276503458291126335
GUILD_ID = 1276158257576284274

# 單一活動公告（一則訊息＝一個活動），含敘述段落供片段抽取
POST_WITH_BODY = (
    "[群聲共振模擬域]戰鬥活動\n"
    "這是一場針對能力多樣性的開放式測試\n"
    "活動時間：2027年8月22日10:00 ~ 2027年9月29日11:59（伺服器時間）\n"
)
# 同一活動、同檔期，但沒有敘述段落（內容較差的來源）
POST_NO_BODY = (
    "[群聲共振模擬域]戰鬥活動\n"
    "活動時間：2027年8月22日10:00 ~ 2027年9月29日11:59（伺服器時間）\n"
)
# 同一活動被官方延長（區間與原檔期重疊）
POST_RESCHEDULED = (
    "[群聲共振模擬域]戰鬥活動\n"
    "這是一場針對能力多樣性的開放式測試\n"
    "活動時間：2027年8月22日10:00 ~ 2027年10月15日11:59（伺服器時間）\n"
)
# 片段明顯更長的來源（匯總帖常寫玩法與獎勵，專屬帖開頭反而只有劇情導言）
POST_LONG_BODY = (
    "[群聲共振模擬域]戰鬥活動\n"
    "這是一場針對能力多樣性的開放式測試，泰緹斯系統將持續提供不同類型的干涉源，"
    "供參與者自由接入、組合，並探索更豐富的能力結構。每日完成挑戰可獲得聲弦點數，"
    "累積一定數量可兌換豐厚獎勵，所有關卡皆可進行多人匹配。\n"
    "活動時間：2027年8月22日10:00 ~ 2027年9月29日11:59（伺服器時間）\n"
)
# 進行中的活動（起點已過）；延長版只改結束時間
POST_ONGOING = (
    "[群聲共振模擬域]戰鬥活動\n"
    "這是一場針對能力多樣性的開放式測試\n"
    "活動時間：2020年8月22日10:00 ~ 2099年9月29日11:59（伺服器時間）\n"
)
POST_ONGOING_EXTENDED = (
    "[群聲共振模擬域]戰鬥活動\n"
    "這是一場針對能力多樣性的開放式測試\n"
    "活動時間：2020年8月22日10:00 ~ 2099年12月31日11:59（伺服器時間）\n"
)
# 預告帖：標題會被拿來當活動名，正式公告到了必須換掉
PREVIEW_TITLE = "活動預告 | <群聲共振模擬域> 戰鬥活動即將開啟！"
POST_PREVIEW = (
    f"{PREVIEW_TITLE}\n"
    "✦活動時間✦\n"
    "2027年8月22日10:00 ~ 2027年9月29日11:59（伺服器時間）\n"
)
# 官方把同一篇公告的結束時間延長後重送（/resend_article，source_id 不變）
POST_RESENT_EXTENDED = (
    "[群聲共振模擬域]戰鬥活動\n"
    "這是一場針對能力多樣性的開放式測試\n"
    "活動時間：2027年8月22日10:00 ~ 2027年10月6日03:59（伺服器時間）\n"
)
# 同活動名但完全不同檔期（不重疊）——例如 [聲弦滌蕩] 每隔幾週開一次
POST_NEXT_SEASON = (
    "[群聲共振模擬域]戰鬥活動\n"
    "這是一場針對能力多樣性的開放式測試\n"
    "活動時間：2027年11月1日10:00 ~ 2027年11月20日11:59（伺服器時間）\n"
)


class FakeScheduledEvent:
    def __init__(self, event_id):
        self.id = event_id
        self.edits = []

    async def edit(self, **kwargs):
        self.edits.append(kwargs)


class _FakeResponse:
    status = 404
    reason = "Not Found"


class FakeGuild:
    def __init__(self, fail_create=False, flaky_fetch=False):
        self.id = GUILD_ID
        self.created = []
        self.events = {}
        self._next_id = 9000
        self._fail_create = fail_create
        self.flaky_fetch = flaky_fetch   # True＝fetch 丟暫時性錯誤（不是 NotFound）

    async def create_scheduled_event(self, **kwargs):
        if self._fail_create:
            raise RuntimeError("boom")
        self._next_id += 1
        self.created.append(kwargs)
        ev = FakeScheduledEvent(self._next_id)
        self.events[ev.id] = ev
        return ev

    def get_scheduled_event(self, event_id):
        return self.events.get(int(event_id))

    async def fetch_scheduled_event(self, event_id):
        import discord
        if self.flaky_fetch:
            raise discord.HTTPException(_FakeResponse(), "503 Service Unavailable")
        ev = self.events.get(int(event_id))
        if ev is None:
            raise discord.NotFound(_FakeResponse(), "Unknown Guild Scheduled Event")
        return ev


class FakeChannel:
    def __init__(self, guild):
        self.guild = guild


class FakeBot:
    def __init__(self, guild):
        self._channel = FakeChannel(guild)

    def get_channel(self, _cid):
        return self._channel


class FakeStateDB:
    """created_events 的記憶體版，語意對齊 StateDB 的同名方法。"""

    def __init__(self):
        self.rows = {}
        self.record_fails = False
        self._seq = 0

    async def list_created_events(self):
        return list(self.rows.values())

    async def get_created_event(self, fingerprint):
        return self.rows.get(fingerprint)

    async def find_overlapping_event(self, core_name, start_utc8, end_utc8, *,
                                     exclude_fingerprints=None):
        if not core_name:
            return None
        excluded = exclude_fingerprints or set()
        hits = [r for r in self.rows.values()
                if r["core_name"] == core_name
                and r["event_fingerprint"] not in excluded
                and r["start_utc8"] < end_utc8 and start_utc8 < r["end_utc8"]]
        # 正本優先，其次後建者優先（對齊 SQL 的 superseded_by / rowid 排序）
        hits.sort(key=lambda r: (r.get("superseded_by") is None, r["_seq"]), reverse=True)
        return hits[0] if hits else None

    async def find_same_name_events(self, core_name):
        return [r for r in self.rows.values() if r["core_name"] == core_name]

    async def clear_event_tombstone(self, fingerprint):
        row = self.rows.get(fingerprint)
        if row is None:
            return False
        row["user_deleted"] = False
        return True

    async def delete_created_event(self, fingerprint):
        return self.rows.pop(fingerprint, None) is not None

    async def mark_created_event_deleted(self, discord_event_id):
        marked = 0
        for row in self.rows.values():
            if row["discord_event_id"] == discord_event_id and not row["user_deleted"]:
                row["user_deleted"] = True
                marked += 1
        return marked

    async def record_created_event(self, fingerprint, **kw):
        if self.record_fails:
            raise RuntimeError("db down")
        self._seq += 1
        self.rows[fingerprint] = {
            "event_fingerprint": fingerprint,
            "discord_event_id": kw["discord_event_id"],
            "guild_id": kw["guild_id"], "source": kw["source"],
            "source_id": kw["source_id"], "title": kw["title"],
            "start_utc8": kw["start_utc8"], "end_utc8": kw["end_utc8"],
            "core_name": kw.get("core_name", ""),
            "has_image": bool(kw.get("has_image")),
            "body": kw.get("body", ""), "superseded_by": None, "user_deleted": False,
            "_seq": self._seq,
        }

    async def update_created_event(self, fingerprint, *, new_fingerprint=None, **kw):
        row = self.rows.get(fingerprint)
        if row is None:
            return False
        for key, val in kw.items():
            if val is not None:
                row[key] = val
        if new_fingerprint and new_fingerprint != fingerprint:
            if new_fingerprint in self.rows:
                raise RuntimeError("UNIQUE constraint failed")
            del self.rows[fingerprint]
            row["event_fingerprint"] = new_fingerprint
            self.rows[new_fingerprint] = row
        return True


class _StubResolver:
    def ensure_loaded(self):
        pass

    def update_time(self, _version):
        return None


class SchedulerCaseBase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.guild = FakeGuild()
        self.bot = FakeBot(self.guild)
        self.db = FakeStateDB()
        ES._fp_migration_done = False

    async def run_post(self, text, *, source="article", source_id="1",
                       image=None, message_url="https://discord.com/x/y/z",
                       guild=None, title="[群聲共振模擬域]戰鬥活動", force=False):
        """跑一次完整的『轉發後偵測活動』流程，image=bytes 代表該來源有封面。"""
        guild = guild or self.guild
        config = {"article_monitor_channel_id": CHANNEL_ID,
                  "event_schedule_enabled": True, "event_schedule_dry_run": False}
        with patch("utils.utils.ChannelConfig.load_config", return_value=config), \
             patch("services.base_monitor.get_shared_state_db", return_value=self.db), \
             patch.object(ES, "_version_resolver", _StubResolver()), \
             patch.object(ES, "_download_image_bytes", side_effect=self._fake_download(image)):
            await ES.maybe_schedule_events(
                FakeBot(guild), source=source, source_id=source_id,
                title=title, text=text,
                post_time=datetime(2027, 8, 19, tzinfo=ES.SERVER_TZ),
                url="https://official/detail/1", channel_id=CHANNEL_ID, is_html=False,
                image_url=("https://img/x.png" if image else None),
                message_url=message_url, force=force,
            )

    @staticmethod
    def _fake_download(image):
        async def _dl(url, **_kw):
            return image if url else None
        return _dl


class CreateTests(SchedulerCaseBase):
    """首次建立。"""

    async def test_creates_event_with_body_and_both_links(self):
        await self.run_post(POST_WITH_BODY)
        self.assertEqual(len(self.guild.created), 1)
        desc = self.guild.created[0]["description"]
        self.assertIn("這是一場針對能力多樣性的開放式測試", desc)      # 方案3：活動段落片段
        self.assertIn("公告出處：https://discord.com/x/y/z", desc)
        self.assertIn("官方原文：https://official/detail/1", desc)    # 站內訊息只有前段，全文在官網

    async def test_records_the_signals_the_upgrade_path_reads(self):
        """只存「之後真的會被讀」的訊號：核心名、有沒有封面、目前片段。"""
        await self.run_post(POST_WITH_BODY, image=b"img")
        row = list(self.db.rows.values())[0]
        self.assertEqual(row["core_name"], "群聲共振模擬域")
        self.assertTrue(row["has_image"])
        self.assertEqual(row["body"], "這是一場針對能力多樣性的開放式測試")

    async def test_second_identical_post_does_not_create_again(self):
        await self.run_post(POST_WITH_BODY)
        await self.run_post(POST_WITH_BODY, source="fb", source_id="2")
        self.assertEqual(len(self.guild.created), 1, "同一活動不可建第二個")


class UpgradeTests(SchedulerCaseBase):
    """後到的來源如何影響既有活動。"""

    async def test_later_source_with_image_adds_the_cover(self):
        """匯總帖先到（無圖）→ FB 專屬貼文後到（有圖）：補封面，不建第二個活動。

        片段一樣時**不重寫描述** —— 內容沒變好就重傳是白打一次 API。
        """
        await self.run_post(POST_WITH_BODY, source="article", source_id="5340")
        event_id = list(self.db.rows.values())[0]["discord_event_id"]
        await self.run_post(POST_WITH_BODY, source="fb", source_id="807", image=b"cover")

        self.assertEqual(len(self.guild.created), 1, "不可建第二個活動")
        edits = self.guild.events[event_id].edits
        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0], {"image": b"cover"})
        row = list(self.db.rows.values())[0]
        self.assertTrue(row["has_image"])
        self.assertEqual(row["source"], "fb")

    async def test_better_source_upgrades_cover_and_description_together(self):
        """後到的來源同時有圖又有更完整的片段 → 封面與描述一起補（使用者要的「都更新」）。"""
        await self.run_post(POST_NO_BODY, source="article", source_id="5340")
        event_id = list(self.db.rows.values())[0]["discord_event_id"]
        await self.run_post(POST_LONG_BODY, source="fb", source_id="807", image=b"cover")
        edits = self.guild.events[event_id].edits
        self.assertEqual(len(edits), 1)
        self.assertIn("description", edits[0])
        self.assertEqual(edits[0]["image"], b"cover")
        self.assertIn("累積一定數量可兌換豐厚獎勵", edits[0]["description"])

    async def test_existing_cover_is_never_replaced(self):
        """既有已有封面就不動 —— 換圖對使用者沒價值，只會反覆重傳。"""
        await self.run_post(POST_NO_BODY, source="fb", source_id="807", image=b"first")
        event_id = list(self.db.rows.values())[0]["discord_event_id"]
        await self.run_post(POST_LONG_BODY, source="article", source_id="5340", image=b"second")
        edits = self.guild.events[event_id].edits
        self.assertIn("description", edits[-1])
        self.assertNotIn("image", edits[-1])

    async def test_shorter_body_does_not_overwrite(self):
        """專屬帖的短導言不可覆蓋匯總帖的長玩法說明（實測有 370 → 118 字的真實案例）。"""
        await self.run_post(POST_LONG_BODY, source="article", source_id="5340")
        event_id = list(self.db.rows.values())[0]["discord_event_id"]
        await self.run_post(POST_WITH_BODY, source="fb", source_id="807")
        self.assertEqual(self.guild.events[event_id].edits, [],
                         "較短的片段不可覆蓋既有較完整的描述")

    async def test_longer_body_upgrades_even_without_image(self):
        """後到的正式公告只要片段更完整就要補上，不需要總分變高。"""
        await self.run_post(POST_WITH_BODY, image=b"cover", source="fb", source_id="807")
        event_id = list(self.db.rows.values())[0]["discord_event_id"]
        await self.run_post(POST_LONG_BODY, source="article", source_id="5340")
        edits = self.guild.events[event_id].edits
        self.assertEqual(len(edits), 1)
        self.assertIn("description", edits[0])
        self.assertNotIn("image", edits[0], "既有封面不可被沒有圖的來源清掉")

    async def test_upgrade_without_new_image_keeps_existing_cover(self):
        await self.run_post(POST_NO_BODY, source="article", source_id="5340")
        event_id = list(self.db.rows.values())[0]["discord_event_id"]
        # 後到的有片段但沒有圖 → 只換描述，不可傳 image（否則會把既有封面洗掉）
        await self.run_post(POST_WITH_BODY, source="fb", source_id="807")
        edits = self.guild.events[event_id].edits
        self.assertEqual(len(edits), 1)
        self.assertIn("description", edits[0])
        self.assertNotIn("image", edits[0])

    async def test_official_reschedule_updates_existing_event(self):
        await self.run_post(POST_WITH_BODY, source="article", source_id="5340")
        event_id = list(self.db.rows.values())[0]["discord_event_id"]
        await self.run_post(POST_RESCHEDULED, source="article", source_id="5399")

        self.assertEqual(len(self.guild.created), 1, "官方改期不可變成兩個活動")
        edits = self.guild.events[event_id].edits
        self.assertIn("start_time", edits[-1])
        self.assertIn("end_time", edits[-1])
        row = list(self.db.rows.values())[0]
        self.assertEqual(row["end_utc8"], "2027-10-15 11:59")

    async def test_non_overlapping_season_creates_new_event(self):
        await self.run_post(POST_WITH_BODY, source="article", source_id="5340")
        await self.run_post(POST_NEXT_SEASON, source="fb", source_id="900")
        self.assertEqual(len(self.guild.created), 2,
                         "同名但不同檔期是不同活動，不可被誤併")

    async def test_same_post_two_spans_are_not_merged(self):
        """同一則公告列出的兩個區間必然是不同活動，不可因為同名就被當成改期而吃掉。

        真實案例：article 995「往歲乘霄醒驚蟄」1.1版本內容說明，3 個活動的章節標題
        都抽不出來、一起退用貼文標題 → 同核心名、區間互相重疊。
        """
        post = (
            "「往歲乘霄醒驚蟄」1.1版本內容說明\n"
            "活動時間：2027年7月4日04:00 ~ 2027年8月13日03:59（伺服器時間）\n"
            "活動時間：2027年7月20日10:00 ~ 2027年8月8日03:59（伺服器時間）\n"
        )
        await self.run_post(post, source="article", source_id="995")
        self.assertEqual(len(self.guild.created), 2)
        self.assertEqual(len(self.db.rows), 2)

    async def test_deleted_event_is_not_recreated(self):
        await self.run_post(POST_WITH_BODY, source="article", source_id="5340")
        event_id = list(self.db.rows.values())[0]["discord_event_id"]
        del self.guild.events[event_id]          # 使用者把活動從 Discord 刪掉
        await self.run_post(POST_WITH_BODY, source="fb", source_id="807", image=b"cover")
        self.assertEqual(len(self.guild.created), 1, "使用者刪掉的活動不可被復活")


class RescheduleTests(SchedulerCaseBase):
    """官方改期：描述必須跟著重建，且不可動到進行中活動的起點。"""

    async def test_reschedule_rebuilds_description(self):
        """描述第一行就是「活動時間：…」，改期卻不重建描述的話，活動頁會自相矛盾。"""
        await self.run_post(POST_WITH_BODY, source="article", source_id="5340")
        event_id = list(self.db.rows.values())[0]["discord_event_id"]
        await self.run_post(POST_RESCHEDULED, source="article", source_id="5399")
        edits = self.guild.events[event_id].edits[-1]
        self.assertIn("description", edits)
        self.assertIn("2027/10/15 11:59", edits["description"])
        self.assertNotIn("2027/09/29 11:59", edits["description"])

    async def test_reschedule_keeps_the_better_body(self):
        """為了修時間而重建描述時，不可順手把片段換成比較差的版本。"""
        await self.run_post(POST_LONG_BODY, source="article", source_id="5340")
        event_id = list(self.db.rows.values())[0]["discord_event_id"]
        await self.run_post(POST_RESCHEDULED, source="article", source_id="5399")
        desc = self.guild.events[event_id].edits[-1]["description"]
        self.assertIn("累積一定數量可兌換豐厚獎勵", desc, "應沿用既有的較長片段")

    async def test_ongoing_event_only_syncs_end_time(self):
        """p.start 是 clamp 過的 max(now+5min, …)，送給進行中的活動會把起點推到 5 分鐘後。"""
        await self.run_post(POST_ONGOING, source="article", source_id="5340")
        event_id = list(self.db.rows.values())[0]["discord_event_id"]
        await self.run_post(POST_ONGOING_EXTENDED, source="article", source_id="5399")
        edits = self.guild.events[event_id].edits[-1]
        self.assertIn("end_time", edits)
        self.assertNotIn("start_time", edits, "已開始的活動不可被改起點")

    async def test_resend_with_changed_times_updates_instead_of_creating(self):
        """同一則公告改期後重送（source_id 不變）必須對到自己先前那一列。"""
        await self.run_post(POST_WITH_BODY, source="article", source_id="5340")
        await self.run_post(POST_RESENT_EXTENDED, source="article", source_id="5340")
        self.assertEqual(len(self.guild.created), 1, "重送改期公告不可建出第二個活動")
        self.assertEqual(len(self.db.rows), 1)
        self.assertEqual(list(self.db.rows.values())[0]["end_utc8"], "2027-10-06 03:59")


class TombstoneTests(SchedulerCaseBase):
    """使用者從 Discord 刪掉的活動，任何來源都不准復活。"""

    async def test_user_deleted_event_is_never_recreated(self):
        await self.run_post(POST_WITH_BODY, source="article", source_id="5340")
        event_id = list(self.db.rows.values())[0]["discord_event_id"]
        # 模擬 on_scheduled_event_delete：立墓碑（不是刪列），並從 Discord 移除
        await self.db.mark_created_event_deleted(event_id)
        del self.guild.events[event_id]
        # 7~28 天後 FB 才報同一個活動
        await self.run_post(POST_WITH_BODY, source="fb", source_id="807", image=b"cover")
        self.assertEqual(len(self.guild.created), 1, "被刪掉的活動不可被另一個來源復活")

    async def test_resend_rebuilds_a_deleted_event(self):
        """`/resend_article` 是人明確要求重抓 → 解得開墓碑並重建。"""
        await self.run_post(POST_WITH_BODY, source="article", source_id="5340")
        event_id = list(self.db.rows.values())[0]["discord_event_id"]
        await self.db.mark_created_event_deleted(event_id)
        del self.guild.events[event_id]

        await self.run_post(POST_WITH_BODY, source="article", source_id="5340", force=True)
        self.assertEqual(len(self.guild.created), 2, "/resend 應重建活動")
        self.assertFalse(list(self.db.rows.values())[0]["user_deleted"], "墓碑應已解除")

    async def test_resend_upgrades_when_the_event_still_exists(self):
        """活動只是被取消、還在伺服器上 → 解除墓碑後走升級，不可再建一個。"""
        await self.run_post(POST_NO_BODY, source="article", source_id="5340")
        event_id = list(self.db.rows.values())[0]["discord_event_id"]
        await self.db.mark_created_event_deleted(event_id)   # 活動仍留在 self.guild.events

        await self.run_post(POST_LONG_BODY, source="article", source_id="5340", force=True)
        self.assertEqual(len(self.guild.created), 1, "活動還在就不可重建")
        self.assertIn("description", self.guild.events[event_id].edits[-1])
        self.assertFalse(list(self.db.rows.values())[0]["user_deleted"])

    async def test_automatic_sources_never_unlock_the_tombstone(self):
        """排程／推送路徑（force=False）不得解除墓碑 —— 否則墓碑就白立了。"""
        await self.run_post(POST_WITH_BODY, source="article", source_id="5340")
        event_id = list(self.db.rows.values())[0]["discord_event_id"]
        await self.db.mark_created_event_deleted(event_id)
        del self.guild.events[event_id]
        await self.run_post(POST_LONG_BODY, source="fb", source_id="807", image=b"cover")
        self.assertEqual(len(self.guild.created), 1)
        self.assertTrue(list(self.db.rows.values())[0]["user_deleted"], "墓碑必須還在")

    async def test_tombstone_only_blocks_that_exact_run(self):
        """墓碑綁在「這個活動這個檔期」；下一個檔期是不同指紋，照常建立。"""
        await self.run_post(POST_WITH_BODY, source="article", source_id="5340")
        event_id = list(self.db.rows.values())[0]["discord_event_id"]
        await self.db.mark_created_event_deleted(event_id)
        await self.run_post(POST_NEXT_SEASON, source="fb", source_id="900")
        self.assertEqual(len(self.guild.created), 2)


class RenameTests(SchedulerCaseBase):
    """預告帖先建的活動，正式公告到了要改名。"""

    async def test_preview_title_is_replaced_by_official_title(self):
        await self.run_post(POST_PREVIEW, source="article", source_id="5351",
                            title=PREVIEW_TITLE, image=b"cover")
        row = list(self.db.rows.values())[0]
        self.assertEqual(row["title"], PREVIEW_TITLE)
        event_id = row["discord_event_id"]

        await self.run_post(POST_WITH_BODY, source="article", source_id="5340")
        edits = self.guild.events[event_id].edits[-1]
        self.assertEqual(edits.get("name"), "[群聲共振模擬域]戰鬥活動")
        self.assertEqual(len(self.guild.created), 1, "預告帖與正式公告是同一個活動")
        self.assertEqual(list(self.db.rows.values())[0]["title"], "[群聲共振模擬域]戰鬥活動")


class TransientFailureTests(SchedulerCaseBase):
    """暫時性 API 失敗不可被當成「活動已被刪除」。"""

    async def test_flaky_fetch_is_not_treated_as_deleted(self):
        await self.run_post(POST_WITH_BODY, source="article", source_id="5340")
        self.guild.events.clear()          # 逼 _fetch_event 走 API
        self.guild.flaky_fetch = True      # API 回 503（不是 404）
        with self.assertLogs("discord_bot", level="WARNING") as caught:
            await self.run_post(POST_LONG_BODY, source="fb", source_id="807", image=b"cover")
        joined = "\n".join(caught.output)
        self.assertNotIn("已不存在", joined, "暫時性失敗不可宣稱活動被刪除")
        self.assertIn("處理活動時例外", joined)
        self.assertEqual(len(self.guild.created), 1, "不可因為查不到就再建一個")


class FailureIsolationTests(SchedulerCaseBase):
    """失敗處理：不可謊報、不可一顆壞掉拖垮整篇。"""

    async def test_record_failure_keeps_created_event_and_logs_error(self):
        self.db.record_fails = True
        with self.assertLogs("discord_bot", level="ERROR") as caught:
            await self.run_post(POST_WITH_BODY)
        self.assertEqual(len(self.guild.created), 1)
        joined = "\n".join(caught.output)
        self.assertIn("已建立但指紋寫入失敗", joined)
        self.assertNotIn("建立活動失敗", joined, "活動明明建起來了，不可謊報建立失敗")

    async def test_create_error_does_not_raise_to_caller(self):
        guild = FakeGuild(fail_create=True)
        await self.run_post(POST_WITH_BODY, guild=guild)   # 不可往上拋，否則會拖垮轉發


class FingerprintMigrationTests(unittest.IsolatedAsyncioTestCase):
    """normalize_title 改動後，既有指紋必須被遷移，否則舊活動會整批重建。"""

    def setUp(self):
        ES._fp_migration_done = False
        self.db = FakeStateDB()

    def _add(self, fingerprint, title, start, end, event_id):
        self.db.rows[fingerprint] = {
            "event_fingerprint": fingerprint, "discord_event_id": event_id,
            "guild_id": GUILD_ID, "source": "article", "source_id": "1",
            "title": title, "start_utc8": start, "end_utc8": end,
            "core_name": "", "has_image": False,
            "body": "", "superseded_by": None, "user_deleted": False, "_seq": event_id,
        }

    async def test_angle_bracket_fingerprint_is_migrated(self):
        self._add("活動預告<群聲共振模擬域>戰鬥活動即將開啟|202608221000|202609291159",
                  "活動預告 | <群聲共振模擬域> 戰鬥活動即將開啟！",
                  "2026-08-22 10:00", "2026-09-29 11:59", 111)
        await ES._migrate_fingerprints_once(self.db)
        self.assertIn("群聲共振模擬域|202608221000|202609291159", self.db.rows)
        self.assertEqual(self.db.rows["群聲共振模擬域|202608221000|202609291159"]["core_name"],
                         "群聲共振模擬域")

    async def test_collision_keeps_both_rows_and_reports(self):
        self._add("群聲共振模擬域|202608221000|202609291159", "[群聲共振模擬域]戰鬥活動",
                  "2026-08-22 10:00", "2026-09-29 11:59", 111)
        self._add("活動預告<群聲共振模擬域>戰鬥活動即將開啟|202608221000|202609291159",
                  "活動預告 | <群聲共振模擬域> 戰鬥活動即將開啟！",
                  "2026-08-22 10:00", "2026-09-29 11:59", 222)
        with self.assertLogs("discord_bot", level="ERROR") as caught:
            await ES._migrate_fingerprints_once(self.db)
        self.assertEqual(len(self.db.rows), 2, "碰撞時不可默默砍掉任何一列")
        self.assertIn("指紋遷移發現重複活動", "\n".join(caught.output))

    async def test_failed_migration_is_retried_and_blocks_creation(self):
        """遷移沒跑成功就不可以往下建活動 —— 拿新指紋去比對未遷移的舊列 = 舊活動整批重建。"""
        class Broken(FakeStateDB):
            async def list_created_events(self):
                raise RuntimeError("db locked")

        broken = Broken()
        with self.assertRaises(RuntimeError):
            await ES._migrate_fingerprints_once(broken)
        self.assertFalse(ES._fp_migration_done, "失敗後必須可以重試")

    async def test_migration_is_idempotent(self):
        self._add("群聲共振模擬域|202608221000|202609291159", "[群聲共振模擬域]戰鬥活動",
                  "2026-08-22 10:00", "2026-09-29 11:59", 111)
        await ES._migrate_fingerprints_once(self.db)
        before = dict(self.db.rows)
        ES._fp_migration_done = False
        await ES._migrate_fingerprints_once(self.db)
        self.assertEqual(self.db.rows.keys(), before.keys())


class DescriptionBudgetTests(unittest.TestCase):
    """描述長度預算：片段是輔助，連結是退路，超長時不可把連結截掉。"""

    def _desc(self, body):
        return ES._build_description(
            datetime(2027, 8, 22, 10, 0, tzinfo=ES.SERVER_TZ),
            datetime(2027, 9, 29, 11, 59, tzinfo=ES.SERVER_TZ),
            "https://discord.com/channels/1/2/3",
            body=body, source_url="https://official/detail/1",
        )

    def test_links_survive_a_very_long_body(self):
        desc = self._desc("長" * 5000)
        self.assertLessEqual(len(desc), ES.DESCRIPTION_LIMIT)
        self.assertIn("公告出處：https://discord.com/channels/1/2/3", desc)
        self.assertIn("官方原文：https://official/detail/1", desc)

    def test_no_body_still_has_time_and_links(self):
        desc = self._desc("")
        self.assertIn("活動時間：2027/08/22 10:00 ~ 2027/09/29 11:59", desc)
        self.assertIn("公告出處：", desc)


if __name__ == "__main__":
    unittest.main()
