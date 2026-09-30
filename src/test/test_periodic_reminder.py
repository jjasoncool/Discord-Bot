"""週期活動提醒（深塔／海墟）：日期推算、發送時機、文案、發送與訂閱行為。

守的底線：
- 推算出的重置日要對得上使用者的手記（標準答案，見 ManualNotesTests）
- 結束前提醒正常 @、重置提醒靜音 @；只允許 @ 訂閱身份組
- 錯過的提醒只在補發時限內補，已發過的不重發
- 身份組建立時不可被一般成員 @、沒有任何權限，名稱以設定為準
- 終焉矩陣跟著版本走：開放日要對得上巴哈各階段隊伍分享串的時程；不知道下一次更新時不發結束提醒

執行：
    cd src && python -m unittest test.test_periodic_reminder -v
"""

import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import discord

from services.events.event_time_parser import SERVER_TZ
from services.events.periodic_reminder import (
    KIND_ENDING,
    KIND_RESET,
    build_panel_description,
    build_reminder_text,
    due_reminders,
    format_moment,
    last_reset,
    next_reset,
    reminders_for,
    stage_open_at,
    stage_panel_line,
    upcoming_reminders,
)
from sys_settings.periodic_reminder_settings import PeriodicReminderSettings

SETTINGS = PeriodicReminderSettings()
TOWER = next(c for c in SETTINGS.cycles if c.key == "tower")
SEA = next(c for c in SETTINGS.cycles if c.key == "sea")
MATRIX = next(s for s in SETTINGS.version_stages if s.key == "matrix")


def T(month, day, hour=0, minute=0, year=2026):
    return datetime(year, month, day, hour, minute, tzinfo=SERVER_TZ)


class ManualNotesTests(unittest.TestCase):
    """標準答案＝使用者在「新功能」討論串的手記（2026-08-03 ~ 09-28）。"""

    def assert_is_reset(self, cycle, moment):
        self.assertEqual(last_reset(cycle, moment), moment, f"{cycle.name} 應在 {moment} 重置")
        self.assertEqual(moment.weekday(), 0, "重置日一律是週一")

    def test_sea_resets_match_notes(self):
        # 8/3「海墟 28天」、8/31「預計 9/28 reset」、9/28「10/26 reset 海墟」
        for moment in (T(8, 3, 4), T(8, 31, 4), T(9, 28, 4), T(10, 26, 4)):
            self.assert_is_reset(SEA, moment)

    def test_tower_resets_match_notes(self):
        # 8/17「深塔 28天 含今日 9/14 reset」
        for moment in (T(8, 17, 4), T(9, 14, 4), T(10, 12, 4)):
            self.assert_is_reset(TOWER, moment)

    def test_two_cycles_are_offset_by_two_weeks(self):
        self.assertEqual(next_reset(SEA, T(10, 12, 4)) - T(10, 12, 4), timedelta(days=14))


class ResetMathTests(unittest.TestCase):
    def test_next_reset_from_today(self):
        now = T(9, 29, 1)
        self.assertEqual(next_reset(TOWER, now), T(10, 12, 4))
        self.assertEqual(next_reset(SEA, now), T(10, 26, 4))

    def test_exact_reset_moment_belongs_to_new_period(self):
        self.assertEqual(last_reset(SEA, T(9, 28, 4)), T(9, 28, 4))
        self.assertEqual(next_reset(SEA, T(9, 28, 4)), T(10, 26, 4))
        self.assertEqual(last_reset(SEA, T(9, 28, 3, 59)), T(8, 31, 4))

    def test_moment_before_anchor(self):
        self.assertEqual(last_reset(SEA, T(1, 20)), T(1, 19, 4))

    def test_utc_input(self):
        # 10/11 12:00 UTC ＝ 10/11 20:00 伺服器時間
        now = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)
        due = due_reminders(now, SETTINGS)
        self.assertEqual([(r.item.key, r.kind) for r in due], [("tower", KIND_ENDING)])


class ReminderScheduleTests(unittest.TestCase):
    def test_reminder_times(self):
        ending, reset = reminders_for(TOWER, T(10, 12, 4), SETTINGS)
        self.assertEqual((ending.send_at, ending.expires_at), (T(10, 11, 20), T(10, 12, 4)))
        self.assertEqual((reset.send_at, reset.expires_at), (T(10, 12, 4), T(10, 12, 12)))
        self.assertFalse(ending.silent)
        self.assertTrue(reset.silent)
        self.assertEqual(ending.dedup_key, "tower:2026-10-12:ending")
        self.assertEqual(reset.dedup_key, "tower:2026-10-12:reset")

    def due_at(self, moment):
        return [(r.item.key, r.kind) for r in due_reminders(moment, SETTINGS)]

    def test_due_boundaries(self):
        self.assertEqual(self.due_at(T(10, 11, 19, 59)), [])
        self.assertEqual(self.due_at(T(10, 11, 20)), [("tower", KIND_ENDING)])
        # 錯過的結束前提醒補到重置前
        self.assertEqual(self.due_at(T(10, 12, 3, 59)), [("tower", KIND_ENDING)])
        # 重置當下：結束前提醒已過期，只剩重置提醒
        self.assertEqual(self.due_at(T(10, 12, 4)), [("tower", KIND_RESET)])
        self.assertEqual(self.due_at(T(10, 12, 11, 59)), [("tower", KIND_RESET)])
        self.assertEqual(self.due_at(T(10, 12, 12)), [])

    def test_already_past_reset_is_not_resent_after_deadline(self):
        # 9/28 海墟重置提醒只補到 9/28 12:00；隔天部署不會補發
        self.assertEqual(self.due_at(T(9, 29, 1)), [])

    def test_upcoming_order_from_today(self):
        upcoming = upcoming_reminders(T(9, 29, 1), SETTINGS)
        self.assertEqual(
            [(r.item.key, r.kind, r.send_at) for r in upcoming[:4]],
            [
                ("tower", KIND_ENDING, T(10, 11, 20)),
                ("tower", KIND_RESET, T(10, 12, 4)),
                ("sea", KIND_ENDING, T(10, 25, 20)),
                ("sea", KIND_RESET, T(10, 26, 4)),
            ],
        )


class TextTests(unittest.TestCase):
    """只檢查文案裡的關鍵資訊（誰、哪個項目、哪天幾點、今天／明天），不逐字比對：
    改措辭不該讓啟動 gate 變紅。日期格式只在 test_moment_format 釘一次。"""

    def setUp(self):
        self.ending, self.reset = reminders_for(TOWER, T(10, 12, 4), SETTINGS)
        self.reset_moment = format_moment(T(10, 12, 4))

    def test_moment_format(self):
        self.assertEqual(format_moment(T(10, 12, 4)), "10/12（週一）04:00")

    def assert_mentions(self, text, *parts, absent=()):
        for part in parts:
            self.assertIn(part, text)
        for part in absent:
            self.assertNotIn(part, text)

    def test_ending_text_says_tomorrow(self):
        text = build_reminder_text(self.ending, "<@&9>", T(10, 11, 20))
        self.assert_mentions(text, "<@&9>", "逆境深塔", "明天", self.reset_moment, absent=("今天",))

    def test_ending_text_caught_up_after_midnight_says_today(self):
        text = build_reminder_text(self.ending, "<@&9>", T(10, 12, 1))
        self.assert_mentions(text, "今天", self.reset_moment, absent=("明天",))

    def test_ending_text_far_away_has_no_relative_word(self):
        text = build_reminder_text(self.ending, "<@&9>", T(9, 29, 1))
        self.assert_mentions(text, "逆境深塔", self.reset_moment, absent=("今天", "明天"))

    def test_reset_text_shows_period_end(self):
        text = build_reminder_text(self.reset, "<@&9>", T(10, 12, 4))
        self.assert_mentions(text, "<@&9>", "逆境深塔", format_moment(T(11, 9, 4)))

    def test_panel_lists_next_resets_soonest_first(self):
        desc = build_panel_description(T(9, 29, 1), SETTINGS)
        self.assert_mentions(desc, "20:00")  # 結束前提醒的時刻要寫在面板上
        tower_line = desc.index(format_moment(T(10, 12, 4)))
        sea_line = desc.index(format_moment(T(10, 26, 4)))
        self.assertLess(tower_line, sea_line)


# ── 終焉矩陣（跟著版本走）──

#: 3.2～3.7 版本更新維護開始時刻（官網「更新維護時間」）
UPDATES = [T(3, 19, 4), T(4, 30, 4), T(6, 8, 4), T(7, 10, 4), T(8, 20, 4), T(9, 30, 4)]


class MatrixScheduleTests(unittest.TestCase):
    def keys(self, reminders):
        return [(r.item.key, r.kind) for r in reminders if r.item.key == "matrix"]

    def test_stage_opens_match_bahamut_threads(self):
        # 巴哈「終焉矩陣」各階段隊伍分享串主文寫的開放時間（S1-1～S2-2）
        opens = [stage_open_at(MATRIX, u) for u in UPDATES[:5]]
        self.assertEqual(opens, [T(3, 26, 4), T(5, 7, 4), T(6, 15, 4), T(7, 17, 4), T(8, 27, 4)])

    def test_ending_reminder_the_night_before_update(self):
        due = [r for r in due_reminders(T(9, 29, 20), SETTINGS, UPDATES) if r.item.key == "matrix"]
        self.assertEqual(self.keys(due), [("matrix", KIND_ENDING)])
        self.assertEqual(due[0].reset_at, T(9, 30, 4))
        self.assertFalse(due[0].silent)
        self.assertEqual(due[0].dedup_key, "matrix:2026-09-30:ending")

    def test_open_reminder_is_silent(self):
        due = [r for r in due_reminders(T(10, 7, 4), SETTINGS, UPDATES) if r.item.key == "matrix"]
        self.assertEqual(self.keys(due), [("matrix", KIND_RESET)])
        self.assertTrue(due[0].silent)
        self.assertEqual(due[0].dedup_key, "matrix:2026-10-07:reset")

    def test_gap_week_has_nothing_due(self):
        self.assertEqual(self.keys(due_reminders(T(10, 3, 12), SETTINGS, UPDATES)), [])

    def test_unknown_next_update_sends_no_ending_reminder(self):
        upcoming = upcoming_reminders(T(10, 8), SETTINGS, UPDATES)
        self.assertEqual(self.keys(upcoming), [])
        self.assertTrue(any(r.item.key == "tower" for r in upcoming), "深塔海墟照常排程")

    def test_known_next_update_schedules_ending(self):
        upcoming = [r for r in upcoming_reminders(T(10, 8), SETTINGS, UPDATES + [T(11, 12, 4)])
                    if r.item.key == "matrix"]
        self.assertEqual([(r.kind, r.send_at) for r in upcoming][:1], [(KIND_ENDING, T(11, 11, 20))])

    def test_no_version_data_means_no_matrix(self):
        self.assertEqual(self.keys(upcoming_reminders(T(10, 8), SETTINGS, ())), [])


class MatrixTextAndPanelTests(unittest.TestCase):
    def test_ending_text(self):
        ending, _ = reminders_for(MATRIX, T(11, 12, 4), SETTINGS)
        text = build_reminder_text(ending, "<@&9>", T(11, 11, 20))
        for part in ("<@&9>", "終焉矩陣", "明天", format_moment(T(11, 12, 4)), "版本更新"):
            self.assertIn(part, text)

    def test_open_text_has_no_end_date(self):
        _, opening = reminders_for(MATRIX, T(10, 7, 4), SETTINGS)
        text = build_reminder_text(opening, "<@&9>", T(10, 7, 4))
        self.assertIn("新階段開放", text)
        self.assertIn("下次版本更新前", text)
        self.assertNotIn("/", text, "開放時還不知道結束日，不寫日期")

    def test_panel_line_gap_week(self):
        line = stage_panel_line(MATRIX, T(10, 1), UPDATES)
        self.assertIn("新階段", line)
        self.assertIn(format_moment(T(10, 7, 4)), line)

    def test_panel_line_open_unknown_end(self):
        self.assertEqual(stage_panel_line(MATRIX, T(10, 8), UPDATES), "🧩 終焉矩陣：本階段開放中，於版本末結束")

    def test_panel_line_open_known_end(self):
        line = stage_panel_line(MATRIX, T(10, 8), UPDATES + [T(11, 12, 4)])
        self.assertIn("本階段開放中", line)
        self.assertIn(format_moment(T(11, 12, 4)), line)

    def test_panel_includes_all_items(self):
        desc = build_panel_description(T(10, 1), SETTINGS, UPDATES)
        for part in ("逆境深塔", "冥歌海墟", "終焉矩陣", format_moment(T(10, 7, 4))):
            self.assertIn(part, desc)


# ── Cog 行為（Discord 物件全用 mock）──

from commands.periodic_reminder_commands import PeriodicReminderCommands  # noqa: E402


def _role(role_id=900, name=None):
    role = MagicMock(spec=discord.Role)
    role.id = role_id
    role.name = name or SETTINGS.role_name
    role.edit = AsyncMock()
    role.mention = f"<@&{role_id}>"
    return role


def _guild(role=None, roles=()):
    guild = MagicMock(spec=discord.Guild)
    guild.get_role.side_effect = lambda rid: role if role is not None and rid == role.id else None
    guild.roles = list(roles)
    guild.create_role = AsyncMock(return_value=_role(901))
    return guild


def _channel(guild, channel_id=500):
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = channel_id
    channel.guild = guild
    channel.send = AsyncMock(return_value=MagicMock(id=777))
    return channel


class CogTestBase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = os.path.join(self.tmp.name, "periodic_reminder_runtime.json")
        self.settings = PeriodicReminderSettings(runtime_path=self.runtime)
        self.bot = MagicMock()
        self.cog = PeriodicReminderCommands(self.bot, settings=self.settings)

    def tearDown(self):
        self.tmp.cleanup()


class SendReminderTests(CogTestBase):
    async def test_reset_is_silent_and_only_pings_role(self):
        role = _role()
        self.cog.ensure_role = AsyncMock(return_value=role)
        channel = _channel(_guild(role))
        _, reset = reminders_for(TOWER, T(10, 12, 4), SETTINGS)

        self.assertTrue(await self.cog.send_reminder(channel, reset, T(10, 12, 4)))

        kwargs = channel.send.await_args.kwargs
        self.assertTrue(kwargs["silent"])
        mentions = kwargs["allowed_mentions"]
        self.assertFalse(mentions.everyone)
        self.assertFalse(mentions.users)
        self.assertEqual(mentions.roles, [role])

    async def test_ending_is_not_silent(self):
        self.cog.ensure_role = AsyncMock(return_value=_role())
        channel = _channel(_guild())
        ending, _ = reminders_for(TOWER, T(10, 12, 4), SETTINGS)
        await self.cog.send_reminder(channel, ending, T(10, 11, 20))
        self.assertFalse(channel.send.await_args.kwargs["silent"])


class RunDueTests(CogTestBase):
    def setUp(self):
        super().setUp()
        self.channel = _channel(_guild())
        self.cog.reminder_channel = MagicMock(return_value=self.channel)
        self.cog.send_reminder = AsyncMock(return_value=True)
        self.cog.panel.bump_safe = AsyncMock()
        self.db = MagicMock()
        self.db.is_content_sent = AsyncMock(return_value=False)
        self.db.mark_content_as_sent = AsyncMock()
        patcher = patch("commands.periodic_reminder_commands.get_shared_state_db",
                        AsyncMock(return_value=self.db))
        patcher.start()
        self.addCleanup(patcher.stop)

    async def test_sends_marks_and_bumps_panel(self):
        self.assertEqual(await self.cog.run_due(T(10, 11, 20)), 1)
        self.db.mark_content_as_sent.assert_awaited_once_with("periodic_reminder", "tower:2026-10-12:ending")
        self.cog.panel.bump_safe.assert_awaited_once_with(self.channel)

    async def test_already_sent_is_skipped_without_bump(self):
        self.db.is_content_sent.return_value = True
        self.assertEqual(await self.cog.run_due(T(10, 11, 20)), 0)
        self.cog.send_reminder.assert_not_awaited()
        self.cog.panel.bump_safe.assert_not_awaited()

    async def test_failed_send_is_not_marked(self):
        self.cog.send_reminder.return_value = False
        await self.cog.run_due(T(10, 11, 20))
        self.db.mark_content_as_sent.assert_not_awaited()
        self.cog.panel.bump_safe.assert_not_awaited()

    async def test_unbound_channel_does_nothing(self):
        self.cog.reminder_channel.return_value = None
        self.assertEqual(await self.cog.run_due(T(10, 11, 20)), 0)
        self.cog.send_reminder.assert_not_awaited()

    async def test_nothing_due_skips_channel_lookup(self):
        self.assertEqual(await self.cog.run_due(T(9, 29, 1)), 0)
        self.cog.reminder_channel.assert_not_called()


class EnsureRoleTests(CogTestBase):
    async def test_creates_unmentionable_role_without_permissions(self):
        guild = _guild()
        role = await self.cog.ensure_role(guild)
        kwargs = guild.create_role.await_args.kwargs
        self.assertEqual(kwargs["name"], "週期活動提醒")
        self.assertFalse(kwargs["mentionable"])
        self.assertEqual(kwargs["permissions"].value, 0)
        # 記住 id，下次直接用
        guild2 = _guild(role)
        self.assertIs(await self.cog.ensure_role(guild2), role)
        guild2.create_role.assert_not_awaited()

    async def test_adopts_existing_role_by_name(self):
        existing = _role(555)
        guild = _guild(roles=[_role(1, "別的身份組"), existing])
        self.assertIs(await self.cog.ensure_role(guild), existing)
        guild.create_role.assert_not_awaited()


class PanelTests(CogTestBase):
    async def test_panel_embed_and_buttons(self):
        channel = _channel(_guild())
        await self.cog._send_panel(channel)
        kwargs = channel.send.await_args.kwargs
        self.assertEqual(kwargs["embed"].title, "🔔 週期活動提醒")
        self.assertEqual({c.custom_id for c in kwargs["view"].children},
                         {"periodic_reminder:subscribe", "periodic_reminder:unsubscribe"})


class OnMessageBumpTests(CogTestBase):
    """提醒頻道有人講話就立即置底；bot 自己的訊息、其他頻道不觸發。"""

    def setUp(self):
        super().setUp()
        self.bot.user.id = 1
        self.cog.panel.request_bump = MagicMock()
        patcher = patch("commands.periodic_reminder_commands.ChannelConfig.load_config",
                        return_value={"periodic_reminder_channel_id": 500})
        patcher.start()
        self.addCleanup(patcher.stop)

    def message(self, *, channel_id=500, author_id=42):
        message = MagicMock()
        message.channel.id = channel_id
        message.author.id = author_id
        return message

    async def test_member_message_in_reminder_channel_bumps(self):
        message = self.message()
        await self.cog.on_message(message)
        self.cog.panel.request_bump.assert_called_once_with(message.channel)

    async def test_bot_own_message_does_not_bump(self):
        await self.cog.on_message(self.message(author_id=1))
        self.cog.panel.request_bump.assert_not_called()

    async def test_other_channel_does_not_bump(self):
        await self.cog.on_message(self.message(channel_id=501))
        self.cog.panel.request_bump.assert_not_called()


class SubscriptionTests(CogTestBase):
    def make_interaction(self, has_role):
        role = _role()
        self.cog.ensure_role = AsyncMock(return_value=role)
        member = MagicMock(spec=discord.Member)
        member.id = 42
        member.get_role.return_value = role if has_role else None
        member.add_roles = AsyncMock()
        member.remove_roles = AsyncMock()
        interaction = MagicMock()
        interaction.guild = _guild(role)
        interaction.user = member
        interaction.response.defer = AsyncMock()
        interaction.followup.send = AsyncMock()
        return interaction, member, role

    async def test_subscribe_adds_role(self):
        interaction, member, role = self.make_interaction(has_role=False)
        await self.cog.handle_subscription(interaction, subscribe=True)
        member.add_roles.assert_awaited_once()
        self.assertIs(member.add_roles.await_args.args[0], role)
        kwargs = interaction.followup.send.await_args.kwargs
        self.assertTrue(kwargs["ephemeral"])
        self.assertIn("已訂閱", interaction.followup.send.await_args.args[0])

    async def test_subscribe_twice_does_not_readd(self):
        interaction, member, _ = self.make_interaction(has_role=True)
        await self.cog.handle_subscription(interaction, subscribe=True)
        member.add_roles.assert_not_awaited()

    async def test_unsubscribe_removes_role(self):
        interaction, member, _ = self.make_interaction(has_role=True)
        await self.cog.handle_subscription(interaction, subscribe=False)
        member.remove_roles.assert_awaited_once()
        self.assertIn("已取消訂閱", interaction.followup.send.await_args.args[0])


class RoleNameSyncTests(CogTestBase):
    async def test_recorded_role_is_renamed_to_setting(self):
        from utils.panel_bump import update_runtime
        update_runtime(self.runtime, role_id=900)
        old = _role(900, name="深塔海墟提醒")
        await self.cog.ensure_role(_guild(old))
        old.edit.assert_awaited_once()
        self.assertEqual(old.edit.await_args.kwargs["name"], "週期活動提醒")

    async def test_same_name_is_left_alone(self):
        from utils.panel_bump import update_runtime
        update_runtime(self.runtime, role_id=900)
        role = _role(900)
        await self.cog.ensure_role(_guild(role))
        role.edit.assert_not_awaited()


class PanelRefreshTests(CogTestBase):
    async def test_refresh_only_when_content_changes(self):
        channel = _channel(_guild())
        await self.cog._send_panel(channel)  # 記下目前顯示的內容
        self.cog.panel.bump_safe = AsyncMock(return_value=MagicMock())
        self.assertFalse(await self.cog.refresh_panel_if_changed(channel))
        self.cog.panel.bump_safe.assert_not_awaited()
        # 新公告帶來下一次版本更新時刻 → 矩陣那一行改變 → 重發
        self.cog._update_starts = [datetime(2099, 1, 1, 4, 0, tzinfo=SERVER_TZ)]
        self.assertTrue(await self.cog.refresh_panel_if_changed(channel))
        self.cog.panel.bump_safe.assert_awaited_once_with(channel)


if __name__ == "__main__":
    unittest.main()
