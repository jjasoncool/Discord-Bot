"""管理主控台（commands/admin_console.py）、各 cog 配合主控台的畫面（角色管理、伺服器資訊、文章、AI）、共用的畫面工具。

守的底線：
- 主控台是一則訊息、幾個畫面：主選單列七組（機器人狀態、頻道設定、角色管理、伺服器資訊、文章轉發、幽靈點名、AI），每組一顆按鈕，
  custom_id `console:<畫面>[:<動作>[:<頁碼>]]` 重啟後解析得回；是新版版面、元件不超過 40
- 每個操作都改主控台這一則（沒有 send_message、沒有 followup）：子畫面有「回主控台」或「回上一層」、結果寫在標題下那一行、
  要等的先切「處理中」（按鈕全灰）；做壞了換回主選單並標錯誤
- 入口 `send_console`：伺服器裡只有本人看得到、私訊裡一般訊息並刪掉私訊裡上一則主控台（只刪 bot 自己發、上面有主控台或其子畫面
  按鈕的；點名面板、警報私訊、別人的不動）；每個畫面的 custom_id 不重複（`screen_view` 擋）；
  只有群主能用（選單、每顆按鈕、每個表單都擋）；私訊裡用 bot 唯一的伺服器，不只一個就請到伺服器裡操作
- 機器人狀態、頻道設定直接畫在主控台那一則上；角色管理交給 ManagementCommands 畫在同一則上；模組沒載入要講
- 伺服器資訊：列出頻道、列出身份組是分頁畫面（一頁一頁翻、每頁都放得下、一個不漏不重、分組標題跟著頁走），不連發訊息
- 文章轉發：監控狀態寫在畫面上；測 API 先選哪個、處理中、結果換成一頁文字；重送一篇用表單、結果寫回畫面；巴哈同步結果寫回畫面
- AI：立即寫日記在背景跑、畫面立刻講「開始寫了」、結果私訊一行（等模型可能超過互動 token 的 15 分鐘）；人格測試用表單找成員
  （名稱或 ID，撞名要講）、主控台只講「開始跑了」
- 幽靈點名面板另發到群主私訊（刪舊發新），主控台只在自己畫面上回連結
- 角色管理：主畫面列 Trader、Moderator 目前對應的身份組，新增／移除進勾選畫面（bot 自己列、分頁、多選），寫 config.json 的 role_mapping；
  舊設定的 [0] 當沒設
- 舊版選單（伺服器管理三顆、伺服器資訊兩顆、角色管理三顆）的按鈕按了把那則換成主控台；舊的文章／AI 子選單 custom_id 也接得回
- `/server_manager`、`/server_info` 允許在私訊裡用；私訊裡傳文字不會叫出選單
- 幽靈點名面板只在群主私訊、而且只有一則訊息（見 RollCallPanelInDmTests）
- 共用工具：`paginate` 夾頁碼、身份組清單的幾支、`message_custom_ids` 走進新版版面、`edit_screen` 看回應過沒、`guarded_screen` 救回畫面

執行：
    cd src && python -m unittest test.test_admin_console -v
"""
import logging
import os
import re
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import discord

from commands import admin_console, channel_panel, management_commands
from utils import discord_content, discord_members
from utils.discord_content import layout_text
from utils.utils import paginate

OWNER = 42
TEXT = discord.ChannelType.text


def member(uid, display_name, name=None, global_name=None):
    return SimpleNamespace(id=uid, display_name=display_name, name=name or display_name, global_name=global_name)


def role(rid, name, position, default=False):
    return SimpleNamespace(id=rid, name=name, position=position, managed=False, is_default=lambda: default)


def ids_of(view):
    return [getattr(getattr(c, "item", c), "custom_id", None) for c in view.walk_children()]


def assert_unique_ids(testcase, view):
    """同一則訊息的 custom_id 不能重複（Discord 會整則退件、錯誤看不出是哪兩顆撞）。"""
    ids = [i for i in ids_of(view) if i]
    testcase.assertEqual(len(ids), len(set(ids)), f"custom_id 重複：{sorted(i for i in set(ids) if ids.count(i) > 1)}")


def buttons_of(view):
    return {getattr(c, "item", c).custom_id: getattr(c, "item", c) for c in view.walk_children()
            if isinstance(getattr(c, "item", c), discord.ui.Button)}


def select_of(view):
    """畫面上的選單本體（DynamicItem 包著的取 `.item`）。"""
    return next(c.item for c in view.walk_children() if isinstance(getattr(c, "item", None), discord.ui.Select))


def dynamic_select_of(view):
    """畫面上包著選單的 DynamicItem（要按它的 callback 用）。"""
    return next(c for c in view.walk_children() if isinstance(getattr(c, "item", None), discord.ui.Select))


def guild_channel(kind, cid, name, position=0, category=None):
    channel = mock.Mock(spec=kind, position=position, category=category)
    channel.name, channel.id = name, cid
    return channel


class FakeConfig:
    """config.json 的替身：同一份 dict 給讀與寫。"""

    def __init__(self, data):
        self.data = data
        self.writes = 0

    def load_config(self, *args, **kwargs):
        import copy
        return copy.deepcopy(self.data)

    async def update_config(self, apply, *args, **kwargs):
        apply(self.data)
        self.writes += 1
        import copy
        return copy.deepcopy(self.data)


class ConsoleTestBase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.members = [member(1, "阿狗", "dog"), member(2, "米拉"), member(3, "米拉", "mira2")]
        category = guild_channel(discord.CategoryChannel, 100, "公告區")
        self.channels = [category, guild_channel(discord.TextChannel, 77, "幽靈點名", 0, category),
                         guild_channel(discord.VoiceChannel, 78, "點歌台", 1, category)]
        self.roles = [role(1, "@everyone", 0, default=True), role(5, "觀星者", 2), role(6, "旅人", 1)]
        self.guild = SimpleNamespace(
            id=1, name="觀星台", members=self.members, channels=self.channels, roles=self.roles,
            get_channel=lambda cid: next((c for c in self.channels if c.id == cid), None),
            get_member=lambda uid: next((m for m in self.members if m.id == uid), None),
            get_role=lambda rid: next((r for r in self.roles if r.id == rid), None))
        self.cogs = {}
        self.me = SimpleNamespace(id=999)
        self.history = []

        async def history(limit=None):
            for message in list(self.history):
                yield message
        self.dm = SimpleNamespace(id=555, history=history)
        self.bot = SimpleNamespace(guilds=[self.guild], get_cog=lambda name: self.cogs.get(name), user=self.me,
                                   add_view=mock.Mock(), add_dynamic_items=mock.Mock())
        patcher = mock.patch.dict(os.environ, {"OWNER_ID": str(OWNER)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def interaction(self, *, user_id=OWNER, dm=True):
        state = {"done": False}

        async def mark_done(*args, **kwargs):
            state["done"] = True
        # 回應過（defer、send_message、edit_message、send_modal）之後 is_done 變 True，後面的換畫面才會像真的一樣改原訊息
        return SimpleNamespace(
            guild=None if dm else self.guild, client=self.bot, data={}, channel=self.dm if dm else SimpleNamespace(id=5),
            user=SimpleNamespace(id=user_id, display_name="群主"),
            message=SimpleNamespace(id=4242, content="", flags=SimpleNamespace(ephemeral=not dm), edit=mock.AsyncMock()),
            response=SimpleNamespace(edit_message=mock.AsyncMock(side_effect=mark_done), send_message=mock.AsyncMock(side_effect=mark_done),
                                     defer=mock.AsyncMock(side_effect=mark_done), send_modal=mock.AsyncMock(side_effect=mark_done),
                                     is_done=lambda: state["done"]),
            followup=SimpleNamespace(send=mock.AsyncMock()),
            edit_original_response=mock.AsyncMock(),
            original_response=mock.AsyncMock(return_value=SimpleNamespace(id=4243)),
        )

    @staticmethod
    def shown(interaction):
        """最後一次換畫面的 kwargs：改原訊息（處理中之後）優先，否則就是用回應改的那次。"""
        call = interaction.edit_original_response.await_args or interaction.response.edit_message.await_args
        return call.kwargs

    def view(self, interaction):
        kwargs = self.shown(interaction)
        self.assertIsInstance(kwargs["view"], discord.ui.LayoutView)
        self.assertIsNone(kwargs["content"])
        self.assertIsNone(kwargs["embed"])
        assert_unique_ids(self, kwargs["view"])
        return kwargs["view"]

    async def press(self, custom_id, interaction=None):
        """照 custom_id 做出那顆按鈕（和重啟後從 custom_id 還原一樣）按下去。"""
        m = re.fullmatch(admin_console.CONSOLE_TEMPLATE, custom_id)
        self.assertIsNotNone(m, custom_id)
        interaction = interaction or self.interaction()
        await admin_console.ConsoleButton(m["screen"], m["action"], m["page"], label="x").callback(interaction)
        return interaction

    def assertNoNewMessages(self, interaction):
        interaction.response.send_message.assert_not_awaited()
        interaction.followup.send.assert_not_awaited()

    def assertBusy(self, interaction, hint):
        """第一次改畫面是「處理中」：有那行字、按鈕全灰。"""
        busy = interaction.response.edit_message.await_args.kwargs["view"]
        self.assertIn(hint, layout_text(busy))
        self.assertTrue(all(b.disabled for b in buttons_of(busy).values()), "處理中按鈕全灰")


class MenuTests(ConsoleTestBase):
    def test_menu_lists_every_group_with_a_button(self):
        view = admin_console.render_console()
        self.assertIsInstance(view, discord.ui.LayoutView)
        self.assertTrue(view.is_persistent())
        text = layout_text(view)
        for _, title, _, _ in admin_console.ACTIONS:
            self.assertIn(f"**{title}**", text)
        self.assertEqual([i for i in ids_of(view) if i], [f"console:{screen}" for screen, *_ in admin_console.ACTIONS])
        self.assertLessEqual(view._total_children, 40)
        assert_unique_ids(self, view)
        self.assertNotIn("⏳", text)
        busy = admin_console.render_console(notice="⏳ 正在把點名管理面板私訊給你…", busy=True)
        self.assertIn("⏳ 正在把點名管理面板私訊給你…", layout_text(busy).split("\n")[2], "結果寫在標題下那一行")
        self.assertTrue(all(b.disabled for b in buttons_of(busy).values()))

    def test_custom_ids_round_trip(self):
        for custom_id, expected in (("console:rollcall", ("rollcall", None, None)),
                                    ("console:info:channels:3", ("info", "channels", "3")),
                                    ("console:ai:diary", ("ai", "diary", None)),
                                    ("console:articles:test_fb", ("articles", "test_fb", None)),
                                    ("console:articles:status", ("articles", "status", None))):
            m = admin_console.ConsoleButton.__discord_ui_compiled_template__.fullmatch(custom_id)
            self.assertEqual((m["screen"], m["action"], m["page"]), expected, custom_id)
        self.assertEqual(admin_console.ConsoleButton("info", "channels", 3, label="x").item.custom_id, "console:info:channels:3")
        self.assertEqual(admin_console.back_button().item.custom_id, "console:home")
        for action in ("role_manager", "set_channel", "bot_status", "list_channels", "list_roles",
                       "set_role_permissions", "list_role_permissions", "remove_role_permissions"):
            self.assertIsNotNone(admin_console.LegacyMenuButton.__discord_ui_compiled_template__.fullmatch(action), action)
        self.assertEqual(admin_console.DYNAMIC_ITEMS, (admin_console.ConsoleButton, admin_console.LegacyMenuButton))

    async def test_send_console_is_owner_only_and_ephemeral_in_guild(self):
        dm = self.interaction()
        await admin_console.send_console(dm)
        kwargs = dm.response.send_message.await_args.kwargs
        self.assertFalse(kwargs["ephemeral"])
        self.assertIn("伺服器管理", layout_text(kwargs["view"]))
        in_guild = self.interaction(dm=False)
        await admin_console.send_console(in_guild)
        self.assertTrue(in_guild.response.send_message.await_args.kwargs["ephemeral"])
        in_guild.original_response.assert_not_awaited()
        stranger = self.interaction(user_id=7)
        await admin_console.send_console(stranger)
        self.assertIn("擁有者", stranger.response.send_message.await_args.kwargs["content"])
        info = self.interaction()
        await admin_console.send_console(info, screen="info")
        self.assertIn("伺服器資訊", layout_text(info.response.send_message.await_args.kwargs["view"]))

    async def test_dm_keeps_only_the_newest_console(self):
        """私訊裡再打 /server_manager：上一則主控台（不管停在哪個畫面）與舊版選單刪掉；別人的、bot 的其他訊息、剛發的這則不動。"""
        def message(mid, author, *custom_ids, nested=True):
            if nested:
                components = [SimpleNamespace(children=[SimpleNamespace(children=[], accessory=SimpleNamespace(custom_id=cid))
                                                        for cid in custom_ids])]
            else:
                components = [SimpleNamespace(children=[SimpleNamespace(custom_id=cid) for cid in custom_ids])]
            return SimpleNamespace(id=mid, author=SimpleNamespace(id=author), components=components, delete=mock.AsyncMock())
        self.history = [
            message(1, 999, "console:status", "console:channels"),
            message(2, 999, "owner:status:refresh", "console:home", nested=False),
            message(3, 999, "role_manager", "set_channel", nested=False),
            message(4, 999, "rollcall:btn:home", nested=False),
            message(5, 7, "console:status"),
            message(6, 999, "roles:sel:trader:add:0", "roles:home", nested=False),
            message(7, 999, "chpanel:chansel:0:交易頻道:0", "chpanel:refresh:0", nested=False),
            message(8, 999, "owner:status:details1:2", nested=False),
            message(9, 999, "owner:retest:lemonade:emb", nested=False),
            message(4243, 999, "console:status"),
        ]
        interaction = self.interaction()
        await admin_console.send_console(interaction)
        deleted = [m.id for m in self.history if m.delete.await_count]
        self.assertEqual(deleted, [1, 2, 3, 6, 7, 8],
                         "舊主控台、停在狀態／角色勾選／選頻道／看詳細畫面的主控台、舊版選單都刪；點名面板、別人的、警報私訊、剛發的不動")

    async def test_dm_cleanup_failure_is_logged_not_raised(self):
        bad = SimpleNamespace(id=1, author=SimpleNamespace(id=999), delete=mock.AsyncMock(
            side_effect=discord.Forbidden(SimpleNamespace(status=403, reason="Forbidden"), {"message": "nope"})),
            components=[SimpleNamespace(children=[SimpleNamespace(custom_id="console:status")])])
        self.history = [bad]
        interaction = self.interaction()
        with self.assertLogs("commands.admin_console", "WARNING"):
            await admin_console.send_console(interaction)
        interaction.response.send_message.assert_awaited_once()


class ScreenTests(ConsoleTestBase):
    async def test_status_and_channels_are_drawn_on_the_console_message(self):
        status_view = discord.ui.LayoutView(timeout=None)
        status_view.add_item(discord.ui.TextDisplay("## 機器人狀態"))
        with mock.patch("commands.admin_status.render_status", mock.AsyncMock(return_value=status_view)) as render:
            interaction = await self.press("console:status")
        render.assert_awaited_once_with()
        self.assertIs(self.view(interaction), status_view)
        self.assertNoNewMessages(interaction)
        panel = discord.ui.LayoutView(timeout=None)
        panel.add_item(discord.ui.TextDisplay("## 頻道綁定"))
        with mock.patch("commands.channel_panel.render", mock.AsyncMock(return_value=(panel, 0))) as render:
            interaction = await self.press("console:channels")
        render.assert_awaited_once_with(self.guild, 0)
        self.assertIs(self.view(interaction), panel)

    async def test_roles_go_to_the_management_cog(self):
        management = SimpleNamespace(open_roles=mock.AsyncMock())
        self.cogs["ManagementCommands"] = management
        interaction = await self.press("console:roles")
        management.open_roles.assert_awaited_once_with(interaction, self.guild)

    async def test_missing_cog_and_unknown_screen_are_explained_on_the_console(self):
        interaction = await self.press("console:roles")
        self.assertIn("沒有載入", layout_text(self.view(interaction)))
        self.assertNoNewMessages(interaction)
        interaction = self.interaction()
        await admin_console.ConsoleButton("nothing", label="x").callback(interaction)
        self.assertIn("沒有「nothing」這個功能", layout_text(self.view(interaction)))

    async def test_strangers_and_multi_guild_dms_are_refused(self):
        stranger = await self.press("console:status", self.interaction(user_id=7))
        self.assertIn("擁有者", stranger.response.send_message.await_args.kwargs["content"])
        stranger.response.edit_message.assert_not_awaited()
        self.bot.guilds.append(SimpleNamespace(id=2))
        interaction = await self.press("console:status")
        self.assertIn("伺服器", interaction.response.send_message.await_args.kwargs["content"])
        interaction.response.edit_message.assert_not_awaited()

    async def test_home_button_and_legacy_buttons_turn_the_message_into_the_console(self):
        interaction = await self.press("console:home")
        self.assertIn("伺服器管理", layout_text(self.view(interaction)))
        for action in ("role_manager", "list_channels", "remove_role_permissions"):
            interaction = self.interaction()
            await admin_console.LegacyMenuButton(action).callback(interaction)
            self.assertIn("伺服器管理", layout_text(self.view(interaction)))
            self.assertNoNewMessages(interaction)

    async def test_a_failing_action_restores_the_console(self):
        self.cogs["ArticleCommands"] = SimpleNamespace(monitor_status_text=lambda: "📊", api_test_report=mock.AsyncMock(side_effect=RuntimeError("boom")))
        with self.assertLogs("commands.admin_console", "ERROR"):
            interaction = await self.press("console:articles:test_all")
        self.assertBusy(interaction, "正在測試")
        view = self.view(interaction)
        self.assertIn("操作失敗（RuntimeError）", layout_text(view))
        self.assertIn("console:status", ids_of(view), "換回主選單")
        self.assertNoNewMessages(interaction)

    # ── 伺服器資訊 ──

    async def test_info_lists_channels_and_roles_in_pages(self):
        interaction = await self.press("console:info")
        view = self.view(interaction)
        self.assertIn("頻道 3 個 · 身份組 2 個", layout_text(view))
        self.assertEqual([i for i in ids_of(view) if i], ["console:info:channels:0", "console:info:roles:0", "console:home"])

        interaction = await self.press("console:info:channels:0")
        text = layout_text(self.view(interaction))
        self.assertIn("**📁 類別（1）**\n公告區（ID: 100）", text)
        self.assertIn("**📝 文字頻道（1）**\n幽靈點名（ID: 77）", text)
        self.assertIn("**🔊 語音頻道（1）**\n點歌台（ID: 78）", text)
        self.assertIn("第 1／1 頁", text)
        self.assertEqual([i for i in ids_of(self.view(interaction)) if i], ["console:info"], "一頁放得下只有回上一層")
        self.assertNoNewMessages(interaction)

        interaction = await self.press("console:info:roles:0")
        text = layout_text(self.view(interaction))
        self.assertIn("**🎭 身份組（2）**\n觀星者（ID: 5）\n旅人（ID: 6）", text, "由高到低、@everyone 不列")

    async def test_long_channel_list_pages_without_losing_anything(self):
        """1 個類別加 120 個文字頻道、每頁 40 行＝4 頁：每頁都放得下、一個不漏不重、分組標題跟著頁走；第一頁沒有上一頁、
        最後一頁沒有下一頁、頁碼超過夾回。"""
        category = self.channels[0]
        self.channels[1:] = [guild_channel(discord.TextChannel, 2000 + n, f"觀星台-{n:03d}-公告轉發", n, category) for n in range(120)]
        with mock.patch.object(admin_console, "ADMIN_CONSOLE_SETTINGS", SimpleNamespace(list_page_size=40)):
            pages = [admin_console.render_info_list(self.guild, "channels", p) for p in range(4)]
            clamped = admin_console.render_info_list(self.guild, "channels", 99)
            interaction = await self.press("console:info:channels:1")
        texts = [layout_text(v) for v in pages]
        self.assertIn("第 1／4 頁", texts[0])
        self.assertIn("第 4／4 頁", texts[3])
        self.assertEqual(texts[3], layout_text(clamped), "超過的頁碼夾回最後一頁")
        for view in pages:
            self.assertLessEqual(view.content_length(), 4000)
        joined = "\n".join(texts)
        self.assertIn("**📁 類別（1）**\n公告區（ID: 100）", texts[0])
        self.assertIn("**📝 文字頻道（120）**\n觀星台-000", texts[0])
        self.assertIn("**📝 文字頻道（120）**（續）\n觀星台-039", texts[1], "從上一頁接著的組別標「續」")
        self.assertIn("**📝 文字頻道（120）**（續）\n觀星台-119", texts[3])
        for n in range(120):
            self.assertEqual(joined.count(f"觀星台-{n:03d}-公告轉發（ID: {2000 + n}）"), 1)
        first, last = buttons_of(pages[0]), buttons_of(pages[3])
        self.assertTrue(first["console:info:channels:0"].disabled, "第一頁沒有上一頁")
        self.assertFalse(first["console:info:channels:1"].disabled)
        self.assertTrue(last["console:info:channels:3"].disabled, "最後一頁沒有下一頁")
        self.assertFalse(last["console:info:channels:2"].disabled)
        self.assertEqual(first["console:info"].label, "↩️ 回上一層")
        self.assertIn("第 2／4 頁", layout_text(self.view(interaction)))
        self.assertNoNewMessages(interaction)

    # ── 文章轉發 ──

    def article_cog(self):
        cog = SimpleNamespace(
            monitor_status_text=lambda: "📊 官方文章更新：✅ 更新中\n更新頻道：<#77>",
            api_test_report=mock.AsyncMock(return_value=SimpleNamespace(text=lambda: "✅ 全部通過（4/4）\n✅ **健康檢查**：status=ok")),
            resend_result=mock.AsyncMock(return_value="✅ 已成功將 FB 貼文 `123` 重新發送到 1 個頻道"),
            baha_sync_result=mock.AsyncMock(return_value="⏳ 開始背景同步 3 個巴哈討論串，完成後會在論壇頻道看到結果。"),
        )
        self.cogs["ArticleCommands"] = cog
        return cog

    async def test_article_screen_shows_the_status_and_runs_tools_in_place(self):
        cog = self.article_cog()
        interaction = await self.press("console:articles")
        view = self.view(interaction)
        self.assertIn("更新頻道：<#77>", layout_text(view))
        self.assertEqual([i for i in ids_of(view) if i], ["console:articles", "console:articles:test", "console:articles:resend",
                                                           "console:articles:baha", "console:home"])
        legacy = await self.press("console:articles:status")
        self.assertIn("更新頻道：<#77>", layout_text(self.view(legacy)), "舊子選單的「監控狀態」接回同一個畫面")

        interaction = await self.press("console:articles:test")
        view = self.view(interaction)
        self.assertEqual([i for i in ids_of(view) if i], ["console:articles:test_article", "console:articles:test_fb",
                                                           "console:articles:test_ptt", "console:articles:test_all", "console:articles"])
        interaction = await self.press("console:articles:test_fb")
        cog.api_test_report.assert_awaited_once_with("fb")
        self.assertBusy(interaction, "正在測試")
        view = self.view(interaction)
        self.assertIn("✅ 全部通過（4/4）", layout_text(view))
        self.assertEqual([i for i in ids_of(view) if i], ["console:articles:test", "console:articles"], "再測、回上一層")
        self.assertNoNewMessages(interaction)

        interaction = await self.press("console:articles:baha")
        cog.baha_sync_result.assert_awaited_once_with()
        self.assertBusy(interaction, "正在抓最近 3 天")
        self.assertIn("開始背景同步 3 個", layout_text(self.view(interaction)))
        self.assertNoNewMessages(interaction)

    async def test_resend_uses_a_form_and_writes_the_result_back(self):
        cog = self.article_cog()
        interaction = await self.press("console:articles:resend")
        modal = interaction.response.send_modal.await_args.args[0]
        self.assertIsInstance(modal, admin_console.ResendModal)
        modal.kind._values = ["fb"]
        modal.ident._value = " 123 "
        submit = self.interaction()
        await modal.on_submit(submit)
        cog.resend_result.assert_awaited_once_with("123", "fb")
        self.assertBusy(submit, "正在重送 fb 123")
        self.assertIn("✅ 已成功將 FB 貼文 `123`", layout_text(self.view(submit)))
        self.assertNoNewMessages(submit)
        stranger = self.interaction(user_id=7)
        await modal.on_submit(stranger)
        self.assertEqual(cog.resend_result.await_count, 1)
        self.assertIn("擁有者", stranger.response.send_message.await_args.kwargs["content"])

    # ── AI ──

    async def test_ai_screen_runs_the_diary_in_the_background_and_starts_the_persona_test(self):
        """寫日記要等模型、可能超過互動 token 的 15 分鐘：背景跑、畫面立刻講「開始寫了」、結果私訊一行；畫面不留在「處理中」。"""
        import asyncio
        llm = SimpleNamespace(write_diary_now=mock.AsyncMock(return_value="🖊️ 今天的日記寫好、發到日記頻道了。"),
                              start_persona_test=mock.AsyncMock(return_value="🔬 persona agent 開始跑 **阿狗**"))
        self.cogs[admin_console.AI_COG] = llm
        interaction = await self.press("console:ai")
        self.assertEqual([i for i in ids_of(self.view(interaction)) if i], ["console:ai:diary", "console:ai:persona", "console:home"])

        informed = []
        started = asyncio.Event()

        async def slow_diary():
            await started.wait()
            return "🖊️ 今天的日記寫好、發到日記頻道了。"
        llm.write_diary_now = mock.AsyncMock(side_effect=slow_diary)
        spawned = []
        with mock.patch.object(admin_console, "spawn", lambda coro, name: spawned.append(asyncio.ensure_future(coro))), \
                mock.patch.object(admin_console.owner_alerts, "inform", lambda *a: informed.append(a)):
            # 日記還在寫就要回來：原地等的話這裡會等到逾時（不能讓測試掛住）
            interaction = await asyncio.wait_for(self.press("console:ai:diary"), timeout=2)
            view = self.view(interaction)
            self.assertIn("開始寫今天的日記", layout_text(view), "日記還沒寫完畫面就先回來")
            self.assertFalse(buttons_of(view)["console:ai:diary"].disabled, "不留在「處理中」")
            self.assertEqual(informed, [])
            started.set()
            await asyncio.gather(*spawned)
        llm.write_diary_now.assert_awaited_once_with()
        self.assertEqual(informed, [("ai_diary", "manual", "🖊️ 今天的日記寫好、發到日記頻道了。")], "結果私訊一行")
        self.assertNoNewMessages(interaction)

        interaction = await self.press("console:ai:persona")
        modal = interaction.response.send_modal.await_args.args[0]
        modal.target._value = "阿狗"
        modal.model._value = ""
        modal.save._values = ["yes"]
        submit = self.interaction()
        await modal.on_submit(submit)
        llm.start_persona_test.assert_awaited_once_with(submit, self.members[0], None, True)
        self.assertIn("persona agent 開始跑", layout_text(self.view(submit)))
        self.assertNoNewMessages(submit)
        modal.target._value = "米拉"
        submit = self.interaction()
        await modal.on_submit(submit)
        self.assertIn("好幾個人叫這個名字", layout_text(self.view(submit)))
        self.assertEqual(llm.start_persona_test.await_count, 1)

    def test_ai_cog_name_matches_the_real_cog(self):
        """日記與人格測試在 llm_commands 的第二個 cog：主控台查的名字要對得上真的類別，方法也要在那上面。"""
        from commands import llm_commands
        self.assertEqual(admin_console.AI_COG, llm_commands.PersonalityCommands.__cog_name__)
        for name in ("write_diary_now", "start_persona_test", "run_diary", "run_persona_test"):
            self.assertTrue(hasattr(llm_commands.PersonalityCommands, name), name)
        self.assertFalse(hasattr(llm_commands.LLMCommands, "write_diary_now"))

    def test_cog_methods_the_console_calls_exist(self):
        """主控台用名字叫各 cog 的方法：改名就會變成按了沒反應，這裡釘住。"""
        from commands import article_commands, rollcall_commands
        for name in ("monitor_status_text", "api_test_report", "resend_result", "baha_sync_result"):
            self.assertTrue(hasattr(article_commands.ArticleCommands, name), name)
        self.assertTrue(hasattr(rollcall_commands.RollCallCommands, "deliver_admin_panel"))
        self.assertTrue(hasattr(management_commands.ManagementCommands, "open_roles"))
        self.assertTrue(hasattr(article_commands.ApiTestReport, "text"))
        import inspect
        from commands import llm_commands
        self.assertEqual(inspect.signature(llm_commands.PersonalityCommands.write_diary_now).return_annotation, str,
                         "主控台把回傳當結果一句私訊出去")

    # ── 幽靈點名 ──

    async def test_rollcall_delivers_the_dm_panel_and_reports_on_the_console(self):
        rollcall = SimpleNamespace(deliver_admin_panel=mock.AsyncMock(return_value="✅ 點名管理面板已私訊給你：https://x/9001"))
        self.cogs["RollCallCommands"] = rollcall
        interaction = await self.press("console:rollcall")
        rollcall.deliver_admin_panel.assert_awaited_once_with(interaction.user, self.guild)
        self.assertBusy(interaction, "正在把點名管理面板私訊給你")
        view = self.view(interaction)
        self.assertIn("https://x/9001", layout_text(view))
        self.assertFalse(buttons_of(view)["console:rollcall"].disabled, "做完按鈕要回來")
        self.assertNoNewMessages(interaction)

    async def test_find_member_by_id_mention_or_name(self):
        with mock.patch.object(admin_console, "resolve_member", mock.AsyncMock(side_effect=lambda g, uid: g.get_member(uid))):
            self.assertIs(await admin_console.find_member(self.guild, "2"), self.members[1])
            self.assertIs(await admin_console.find_member(self.guild, "<@!1>"), self.members[0])
        self.assertIs(await admin_console.find_member(self.guild, "DOG"), self.members[0], "帳號名稱不分大小寫")
        self.assertIsNone(await admin_console.find_member(self.guild, "米拉"), "撞名回 None")
        self.assertIsNone(await admin_console.find_member(self.guild, ""))


class RolesScreenTests(ConsoleTestBase):
    """角色管理畫在主控台那一則上：列現況、勾選畫面分頁多選、寫 role_mapping。"""

    def setUp(self):
        super().setUp()
        self.roles.extend(role(10 + i, f"身分組{i:02d}", 10 + i) for i in range(30))
        self.config = FakeConfig({"role_mapping": {"Trader": [5], "Moderator": [0]}})
        patcher = mock.patch.object(management_commands, "ChannelConfig", self.config)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.cog = management_commands.ManagementCommands(self.bot, intro_profile_service=mock.Mock())
        self.cogs["ManagementCommands"] = self.cog

    async def press_role(self, custom_id, interaction=None):
        interaction = interaction or self.interaction()
        if custom_id.startswith("roles:sel:"):
            raise AssertionError("選單用 select_of 拿")
        m = re.fullmatch(management_commands.ROLE_TEMPLATE, custom_id)
        self.assertIsNotNone(m, custom_id)
        await management_commands.RoleButton(m["action"], m["kind"], m["mode"], m["page"], label="x").callback(interaction)
        return interaction

    async def test_home_lists_the_mapping_and_opens_from_the_console(self):
        interaction = await self.press("console:roles")
        view = self.view(interaction)
        text = layout_text(view)
        self.assertIn("**Trader**　觀星者", text)
        self.assertIn("**Moderator**　未設定", text, "[0] 當沒設")
        buttons = buttons_of(view)
        self.assertEqual(list(buttons), ["roles:pick:trader:add:0", "roles:pick:trader:remove:0",
                                         "roles:pick:moderator:add:0", "roles:pick:moderator:remove:0", "console:home"])
        self.assertFalse(buttons["roles:pick:trader:remove:0"].disabled)
        self.assertTrue(buttons["roles:pick:moderator:remove:0"].disabled, "沒得減的那顆灰掉")
        self.assertNoNewMessages(interaction)

    async def test_pick_pages_past_25_and_applies_one_page(self):
        interaction = await self.press_role("roles:pick:trader:add:0")
        view = self.view(interaction)
        assert_unique_ids(self, view)
        select = select_of(view)
        self.assertEqual(select.custom_id, "roles:sel:trader:add:0")
        self.assertEqual(len(select.options), 25, "32 個身分組扣掉已設定的 1 個與 @everyone＝31 個，第一頁 25 個")
        self.assertEqual(select.max_values, 25)
        self.assertEqual(select.options[0].label, "身分組29", "由高到低列")
        self.assertIn("第 1／2 頁", layout_text(view))
        buttons = buttons_of(view)
        self.assertEqual(list(buttons), ["roles:pick:trader:add:0", "roles:pick:trader:add:1", "roles:home"])
        self.assertTrue(buttons["roles:pick:trader:add:0"].disabled)
        self.assertEqual(buttons["roles:home"].label, "↩️ 回上一層")
        self.assertNoNewMessages(interaction)

        interaction = await self.press_role("roles:pick:trader:add:1")
        view = self.view(interaction)
        self.assertEqual([o.label for o in select_of(view).options], ["身分組04", "身分組03", "身分組02", "身分組01", "身分組00", "旅人"])
        chooser = dynamic_select_of(view)
        chooser.item._values = ["6", "10"]
        chosen = self.interaction()
        await chooser.callback(chosen)
        self.assertEqual(self.config.data["role_mapping"]["Trader"], [5, 6, 10])
        text = layout_text(self.view(chosen))
        self.assertIn("Trader 已新增 2 個身份組：**旅人**, **身分組00**", text)
        self.assertIn("**Trader**　身分組00、觀星者、旅人", text, "回主畫面、現況已更新，照伺服器裡的高低排")
        self.assertNoNewMessages(chosen)

    async def test_remove_lists_only_configured_and_drops_the_zero_sentinel(self):
        self.config.data["role_mapping"]["Moderator"] = [0, 6]
        interaction = await self.press_role("roles:pick:moderator:remove:0")
        view = self.view(interaction)
        self.assertEqual([o.value for o in select_of(view).options], ["6"], "只列已設定的，[0] 不算")
        chooser = dynamic_select_of(view)
        chooser.item._values = ["6"]
        chosen = self.interaction()
        await chooser.callback(chosen)
        self.assertEqual(self.config.data["role_mapping"]["Moderator"], [], "移除後舊的 0 也一起清掉")
        self.assertIn("Moderator 已移除 1 個身份組", layout_text(self.view(chosen)))
        interaction = await self.press_role("roles:pick:moderator:remove:0")
        self.assertIn("沒有已設定的身份組可移除", layout_text(self.view(interaction)), "沒得選退回主畫面並說原因")

    async def test_nothing_changes_when_the_picked_roles_are_already_there(self):
        chooser = management_commands.RoleSelect("trader", "add", 0, options=[discord.SelectOption(label="觀星者", value="5")])
        chooser.item._values = ["5"]
        chosen = self.interaction()
        await chooser.callback(chosen)
        self.assertEqual(self.config.writes, 0)
        self.assertIn("都已經在設定裡了", layout_text(self.view(chosen)))

    async def test_strangers_are_refused_and_failures_restore_the_screen(self):
        stranger = await self.press_role("roles:home", self.interaction(user_id=7))
        self.assertIn("擁有者", stranger.response.send_message.await_args.kwargs["content"])
        stranger.response.edit_message.assert_not_awaited()
        with mock.patch.object(management_commands, "render_role_pick", side_effect=RuntimeError("boom")):
            with self.assertLogs("commands.management_commands", "ERROR"):
                interaction = await self.press_role("roles:pick:trader:add:0")
        text = layout_text(self.view(interaction))
        self.assertIn("操作失敗（RuntimeError）", text)
        self.assertIn("**Trader**", text, "換回角色管理主畫面")

    def test_custom_ids_round_trip_and_cog_registers_everything(self):
        m = re.fullmatch(management_commands.ROLE_TEMPLATE, "roles:pick:moderator:remove:3")
        self.assertEqual((m["action"], m["kind"], m["mode"], m["page"]), ("pick", "moderator", "remove", "3"))
        self.assertEqual(management_commands.RoleButton("home", label="x").item.custom_id, "roles:home")
        m = re.fullmatch(management_commands.ROLE_SELECT_TEMPLATE, management_commands.RoleSelect("trader", "add", 1).item.custom_id)
        self.assertEqual((m["kind"], m["mode"], m["page"]), ("trader", "add", "1"))
        import asyncio
        asyncio.run(self.cog.cog_load())
        # 名單寫死：少登記一個就是重啟後「此互動失敗」
        self.bot.add_dynamic_items.assert_called_once_with(
            channel_panel.PanelButton, channel_panel.PanelPickSelect, channel_panel.ChannelSelect, channel_panel.UnbindSelect,
            admin_console.ConsoleButton, admin_console.LegacyMenuButton, management_commands.RoleButton, management_commands.RoleSelect)
        self.assertEqual(self.bot.add_view.call_count, 1, "只剩自我介紹面板是整張 persistent View")
        self.assertFalse(hasattr(management_commands, "ServerInfoView"))
        self.assertFalse(hasattr(management_commands, "RoleManagerView"))

    async def test_server_info_and_server_manager_open_the_console(self):
        with mock.patch.object(management_commands.admin_console, "send_console", mock.AsyncMock()) as send:
            interaction = self.interaction()
            await self.cog.server_info_cmd.callback(self.cog, interaction)
            send.assert_awaited_once_with(interaction, screen="info")
            contexts = self.cog.server_info_cmd.allowed_contexts
            self.assertTrue(contexts.guild and contexts.dm_channel and not contexts.private_channel)
            send.reset_mock()
            interaction = self.interaction()
            await self.cog.server_manager_cmd.callback(self.cog, interaction)
            send.assert_awaited_once_with(interaction)
        contexts = self.cog.server_manager_cmd.allowed_contexts
        self.assertTrue(contexts.guild and contexts.dm_channel and not contexts.private_channel)
        self.assertFalse(hasattr(self.cog, "set_channel_cmd"), "頻道設定只剩主控台這一條路")


class SharedHelperTests(unittest.IsolatedAsyncioTestCase):
    """面板共用的小工具。"""

    def test_paginate_clamps_the_page(self):
        self.assertEqual(paginate([], 3, 25), ([], 0, 1))
        self.assertEqual(paginate(list(range(30)), 5, 25), (list(range(25, 30)), 1, 2))
        self.assertEqual(paginate(list(range(30)), -1, 25), (list(range(25)), 0, 2))
        self.assertEqual(paginate(list(range(5)), 0, 0)[2], 5, "每頁至少 1 個")

    def test_role_helpers(self):
        roles = [role(1, "@everyone", 0, default=True), role(5, "觀星者", 2), role(6, "旅人", 1), role(7, "新人", 3)]
        guild = SimpleNamespace(roles=roles, get_role=lambda rid: next((r for r in roles if r.id == rid), None))
        self.assertEqual(discord_members.role_name(guild, 5), "觀星者")
        self.assertEqual(discord_members.role_name(guild, 404), "未知（ID: 404）")
        self.assertEqual(discord_members.roles_by_position(guild, [6, 404, 7]), [7, 6, 404], "不存在的排最後")
        self.assertEqual(discord_members.addable_role_ids(guild, [7]), [5, 6], "由高到低、@everyone 與已設定的不算")
        options = discord_members.role_select_options(guild, [5])
        self.assertEqual((options[0].label, options[0].value, options[0].description), ("觀星者", "5", "ID: 5"))
        self.assertEqual(discord_members.role_ids_changed([5], [5, 6], "add"), [6])
        self.assertEqual(discord_members.role_ids_changed([5], [5, 6], "remove"), [5])
        self.assertEqual(discord_members.role_ids_after([5], "add", [6, 6, 5]), [5, 6])
        self.assertEqual(discord_members.role_ids_after([5, 6], "remove", [5]), [6])
        self.assertEqual(discord_members.role_ids_after("bad", "add", [1]), [1], "設定檔裡不是清單當空的")

    def test_message_custom_ids_walks_into_the_new_layout(self):
        message = SimpleNamespace(components=[
            SimpleNamespace(children=[SimpleNamespace(children=[SimpleNamespace(content="x")], accessory=SimpleNamespace(custom_id="console:status")),
                                      SimpleNamespace(children=[SimpleNamespace(custom_id="chpanel:pick:0")])]),
            SimpleNamespace(children=[SimpleNamespace(custom_id="console:home"), SimpleNamespace(url="https://x", custom_id=None)]),
        ])
        self.assertEqual(discord_content.message_custom_ids(message), {"console:status", "chpanel:pick:0", "console:home"})
        self.assertEqual(discord_content.message_custom_ids(SimpleNamespace(components=None)), set())

    def test_screen_view_refuses_duplicate_custom_ids(self):
        box = admin_console.screen_box("## x")
        with self.assertRaises(ValueError) as caught:
            admin_console.screen_view(box, [admin_console.ConsoleButton("info", label="a")], [admin_console.ConsoleButton("info", label="b")])
        self.assertIn("console:info", str(caught.exception))
        view = admin_console.screen_view(admin_console.screen_box("## x"), [admin_console.ConsoleButton("info", label="a"), admin_console.back_button()])
        self.assertEqual([i for i in ids_of(view) if i], ["console:info", "console:home"])

    async def test_edit_screen_edits_the_response_or_the_original_message(self):
        fresh = SimpleNamespace(response=SimpleNamespace(is_done=lambda: False, edit_message=mock.AsyncMock()), edit_original_response=mock.AsyncMock())
        await discord_content.edit_screen(fresh, view="v")
        fresh.response.edit_message.assert_awaited_once_with(content=None, embed=None, view="v")
        fresh.edit_original_response.assert_not_awaited()
        done = SimpleNamespace(response=SimpleNamespace(is_done=lambda: True, edit_message=mock.AsyncMock()), edit_original_response=mock.AsyncMock())
        await discord_content.edit_screen(done, view="v", embed="e")
        done.edit_original_response.assert_awaited_once_with(content=None, embed="e", view="v")
        done.response.edit_message.assert_not_awaited()

    async def test_guarded_screen_rescues_and_logs_with_the_callers_logger(self):
        rescued = []
        log = logging.getLogger("guarded_screen_test")

        async def boom():
            raise RuntimeError("boom")

        async def rescue(notice):
            rescued.append(notice)
        with self.assertLogs("guarded_screen_test", "ERROR") as logs:
            await discord_content.guarded_screen(SimpleNamespace(), "面板：x", boom, rescue=rescue, log=log)
        self.assertIn("面板：x 失敗", logs.output[0])
        self.assertEqual(len(rescued), 1)
        self.assertIn("操作失敗（RuntimeError）", rescued[0])

        async def rescue_fails(notice):
            raise discord.NotFound(SimpleNamespace(status=404, reason="Not Found"), {"message": "Unknown Message"})
        with self.assertLogs("guarded_screen_test", "WARNING") as logs:
            await discord_content.guarded_screen(SimpleNamespace(), "面板：y", boom, rescue=rescue_fails, log=log)
        self.assertEqual([r.levelname for r in logs.records], ["ERROR", "WARNING"])
        self.assertIn("面板可能已被刪", logs.output[-1])

        ok = mock.AsyncMock()
        await discord_content.guarded_screen(SimpleNamespace(), "面板：z", ok, rescue=rescue, log=log)
        ok.assert_awaited_once()
        self.assertEqual(len(rescued), 1, "沒出錯不救援")


class RollCallPanelInDmTests(unittest.IsolatedAsyncioTestCase):
    """點名管理面板只在群主私訊，而且只有一則訊息：入口私訊給按的人並刪掉公開頻道那張；每個操作都改面板這一則、
    子畫面有「回上一層」、要等的先變「處理中」；身分組選單由 bot 自己列、分頁；按鈕狀態在 custom_id 裡，重啟後照樣能按。"""

    def setUp(self):
        from commands import rollcall_commands
        from services.community import rollcall_service
        self.rc = rollcall_commands
        self.roles = [SimpleNamespace(id=100 + i, name=f"身分組{i:02d}", position=i + 1, managed=False, is_default=lambda: False)
                      for i in range(30)]
        everyone = SimpleNamespace(id=1, name="@everyone", position=0, managed=False, is_default=lambda: True)
        self.members = []

        async def fetch_members(limit=None):
            for m in self.members:
                yield m
        self.rollcall_channel = SimpleNamespace(id=77, name="幽靈點名", mention="<#77>", fetch_message=mock.AsyncMock())
        self.guild = SimpleNamespace(id=1, name="觀星台", roles=[everyone, *self.roles], fetch_members=fetch_members,
                                     get_role=lambda rid: next((r for r in self.roles if r.id == rid), None),
                                     get_member=lambda uid: next((m for m in self.members if m.id == uid), None),
                                     fetch_member=mock.AsyncMock(side_effect=discord.NotFound(SimpleNamespace(status=404, reason="Not Found"), {"message": "Unknown Member"})))
        self.channels = {77: self.rollcall_channel}
        self.bot = SimpleNamespace(guilds=[self.guild], add_view=mock.Mock(), add_dynamic_items=mock.Mock(), remove_dynamic_items=mock.Mock(),
                                   get_channel=lambda cid: self.channels.get(cid),
                                   get_cog=lambda name: self.cog if name == "RollCallCommands" else None)
        self.panel = SimpleNamespace(id=9001, jump_url="https://discord.com/channels/@me/555/9001",
                                     edit=mock.AsyncMock(), delete=mock.AsyncMock())
        # 私訊頻道：故意沒有 mention（DMChannel 本來就沒有）
        self.dm = SimpleNamespace(id=555, send=mock.AsyncMock(return_value=self.panel), fetch_message=mock.AsyncMock(return_value=self.panel))
        self.data = {"rollcall_channel_id": 77, "rollcall_target_role_ids": [100, 101], "rollcall_exclude_role_ids": [102]}

        async def apply(fn, *args, **kwargs):
            fn(self.data)
            return dict(self.data)
        config = SimpleNamespace(load_config=lambda *a, **k: dict(self.data), update_config=mock.AsyncMock(side_effect=apply))
        self.runtime = SimpleNamespace(enabled=True, admin_panel_message_id=None, channel_id=None, pending={}, immunity={},
                                       stats={"total_kicked": 3, "total_passed": 8}, save=mock.Mock(),
                                       get_pending_list=lambda: [], is_pending=lambda uid: False, is_immune=lambda uid: False)
        for patcher in (mock.patch.object(rollcall_service, "RollCallRuntime", lambda: self.runtime),   # 不碰 settings/runtime/rollcall.json
                        mock.patch.object(rollcall_service, "ChannelConfig", config),
                        mock.patch.object(rollcall_commands, "ChannelConfig", config),
                        mock.patch.dict(os.environ, {"OWNER_ID": str(OWNER)})):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.cog = rollcall_commands.RollCallCommands(self.bot)

    def interaction(self, *, user_id=OWNER, dm=True):
        state = {"done": False}

        async def mark_done(*args, **kwargs):
            state["done"] = True
        # 回應過（defer、send_message 或 edit_message）之後 is_done 變 True，後面的換畫面才會像真的一樣改原訊息
        return SimpleNamespace(
            guild=None if dm else self.guild, client=self.bot, data={},
            channel=self.dm if dm else self.rollcall_channel, channel_id=555 if dm else 77,
            user=SimpleNamespace(id=user_id, display_name="群主", create_dm=mock.AsyncMock(return_value=self.dm)),
            message=self.panel,
            response=SimpleNamespace(edit_message=mock.AsyncMock(side_effect=mark_done), send_message=mock.AsyncMock(side_effect=mark_done),
                                     defer=mock.AsyncMock(side_effect=mark_done), is_done=lambda: state["done"]),
            edit_original_response=mock.AsyncMock(),
            followup=SimpleNamespace(send=mock.AsyncMock()),
        )

    # ── 小工具 ──

    def home(self):
        return self.rc.render_home(self.cog.service, self.guild)[1]

    @staticmethod
    def item(view, custom_id):
        return next(c for c in view.children if c.custom_id == custom_id)

    @staticmethod
    def select(view):
        return next(c for c in view.children if isinstance(c.item, discord.ui.Select))

    @staticmethod
    def shown(interaction):
        """最後一次換畫面的 (embed, view)：改原訊息（處理中之後）優先，否則就是用回應改的那次。"""
        call = interaction.edit_original_response.await_args or interaction.response.edit_message.await_args
        return call.kwargs["embed"], call.kwargs["view"]

    async def press(self, view, custom_id, interaction=None):
        interaction = interaction or self.interaction()
        await self.item(view, custom_id).callback(interaction)
        return interaction

    def assertNoNewMessages(self, interaction):
        """面板操作不另發訊息：沒有回應新訊息、沒有 followup。"""
        interaction.response.send_message.assert_not_awaited()
        interaction.followup.send.assert_not_awaited()

    @staticmethod
    def field(embed, name):
        return next(f.value for f in embed.fields if f.name == name)

    # ── 入口 ──

    async def test_open_admin_panel_dms_the_owner_and_removes_the_public_panel(self):
        """從伺服器裡按：面板發到自己的私訊、公開頻道那張刪掉、位置記進 runtime、回連結（私訊頻道沒有 mention 也不炸）。"""
        old = SimpleNamespace(delete=mock.AsyncMock())
        self.runtime.admin_panel_message_id, self.runtime.channel_id = 1234, 77
        self.rollcall_channel.fetch_message = mock.AsyncMock(return_value=old)
        interaction = self.interaction(dm=False)
        await self.cog.open_admin_panel(interaction)
        interaction.response.defer.assert_awaited_once_with(thinking=True, ephemeral=True)
        self.rollcall_channel.fetch_message.assert_awaited_once_with(1234)
        old.delete.assert_awaited_once()
        sent = self.dm.send.await_args.kwargs
        ids = [c.custom_id for c in sent["view"].children]
        self.assertIn("rollcall:btn:home", ids)
        self.assertIn("rollcall:btn:roles:target", ids)
        self.assertEqual(self.field(sent["embed"], "目標身份組"), "身分組00, 身分組01", "私訊裡 <@&id> 顯示不出來，要印名稱")
        self.assertEqual(self.field(sent["embed"], "點名頻道"), "<#77>")
        self.assertEqual((self.runtime.admin_panel_message_id, self.runtime.channel_id), (9001, 555))
        self.runtime.save.assert_called()
        reply = interaction.followup.send.await_args.args[0]
        self.assertIn("已私訊給你", reply)
        self.assertIn(self.panel.jump_url, reply)
        self.assertNotIn("⚠️", reply)

    async def test_old_panel_that_cannot_be_deleted_is_reported_not_swallowed(self):
        self.runtime.admin_panel_message_id, self.runtime.channel_id = 1234, 77
        response = SimpleNamespace(status=403, reason="Forbidden")
        self.rollcall_channel.fetch_message = mock.AsyncMock(side_effect=discord.Forbidden(response, {"message": "Missing Access"}))
        interaction = self.interaction()
        with self.assertLogs("commands.rollcall_commands", "WARNING"):
            await self.cog.open_admin_panel(interaction)
        self.dm.send.assert_awaited_once()
        reply = interaction.followup.send.await_args.args[0]
        self.assertIn("舊面板刪不掉", reply)
        self.assertIn("1234", reply)
        self.assertIn("<#77>", reply)

    async def test_closed_dm_is_reported_instead_of_hanging(self):
        response = SimpleNamespace(status=403, reason="Forbidden")
        self.dm.send = mock.AsyncMock(side_effect=discord.Forbidden(response, {"message": "Cannot send messages to this user"}))
        interaction = self.interaction()
        with self.assertLogs("commands.rollcall_commands", "WARNING"):
            await self.cog.open_admin_panel(interaction)
        reply = interaction.followup.send.await_args.args[0]
        self.assertIn("私訊發不出去", reply)
        self.assertIn("Cannot send messages to this user", reply)

    async def test_old_panel_button_moves_the_panel_to_dm(self):
        """重啟後舊面板（點名頻道那張）的按鈕還在：按了不是「此互動失敗」，而是把面板搬到私訊；一樣只有群主。"""
        match = re.fullmatch(self.rc.LEGACY_TEMPLATE, "rollcall_admin_refresh")
        legacy = await self.rc.LegacyPanelButton.from_custom_id(
            self.interaction(), discord.ui.Button(label="🔄 刷新狀態", custom_id="rollcall_admin_refresh"), match)
        self.assertIn(self.rc.LegacyPanelButton, self.rc.DYNAMIC_ITEMS, "沒登記就會變成「此互動失敗」")
        self.cog.open_admin_panel = mock.AsyncMock()
        stranger = self.interaction(user_id=7, dm=False)
        await legacy.callback(stranger)
        self.cog.open_admin_panel.assert_not_awaited()
        owner = self.interaction(dm=False)
        await legacy.callback(owner)
        self.cog.open_admin_panel.assert_awaited_once_with(owner)

    # ── 一則訊息、幾個畫面 ──

    async def test_panel_buttons_work_in_dm_for_the_owner_only(self):
        stranger = await self.press(self.home(), "rollcall:btn:home", self.interaction(user_id=7))
        self.assertIn("擁有者", stranger.response.send_message.await_args.kwargs["content"])
        stranger.response.edit_message.assert_not_awaited()

        owner = await self.press(self.home(), "rollcall:btn:home")
        embed, view = self.shown(owner)
        self.assertEqual(self.field(embed, "排除身份組"), "身分組02")
        self.assertTrue(self.item(view, "rollcall:btn:enable").item.disabled, "已開啟：「開啟」那顆灰掉")
        self.assertFalse(self.item(view, "rollcall:btn:disable").item.disabled)
        self.assertNoNewMessages(owner)

    async def test_toggle_updates_the_same_message_and_flips_the_buttons(self):
        owner = await self.press(self.home(), "rollcall:btn:disable")
        self.assertFalse(self.runtime.enabled)
        self.runtime.save.assert_called()
        embed, view = self.shown(owner)
        self.assertIn("已關閉", embed.description)
        self.assertFalse(self.item(view, "rollcall:btn:enable").item.disabled)
        self.assertTrue(self.item(view, "rollcall:btn:disable").item.disabled)
        self.assertNoNewMessages(owner)

    async def test_sub_screens_replace_the_panel_and_go_back_up(self):
        """待回覆、身分組設定、勾選都換在面板這一則上；每個子畫面都有「回上一層」，回到上一個畫面。"""
        step = await self.press(self.home(), "rollcall:btn:pending")
        embed, view = self.shown(step)
        self.assertIn("待回覆", embed.title)
        self.assertIn("目前沒有待回覆", embed.description)
        self.assertEqual([c.custom_id for c in view.children], ["rollcall:btn:pending", "rollcall:btn:home"])
        self.assertEqual([c.item.label for c in view.children], ["🔄 刷新", "↩️ 回上一層"])
        self.assertNoNewMessages(step)

        back = await self.press(view, "rollcall:btn:home")
        embed, view = self.shown(back)
        self.assertIn("幽靈點名系統", embed.title)
        self.assertNoNewMessages(back)

        step = await self.press(view, "rollcall:btn:roles:target")
        embed, view = self.shown(step)
        self.assertEqual(embed.title, "🎯 目標身份組")
        self.assertIn("• 身分組01\n• 身分組00", embed.description, "目前設定由高到低列")
        self.assertEqual([c.custom_id for c in view.children],
                         ["rollcall:btn:pick:target:add:0", "rollcall:btn:pick:target:remove:0", "rollcall:btn:home"])
        self.assertNoNewMessages(step)

        step = await self.press(view, "rollcall:btn:pick:target:add:0")
        embed, view = self.shown(step)
        self.assertEqual(self.item(view, "rollcall:btn:roles:target").item.label, "↩️ 回上一層", "勾選畫面的上一層是那一組的設定畫面")
        back = await self.press(view, "rollcall:btn:roles:target")
        self.assertEqual(self.shown(back)[0].title, "🎯 目標身份組")
        self.assertNoNewMessages(back)

    async def test_scope_shows_busy_then_the_result_on_the_same_message(self):
        def member(uid, *roles):
            return SimpleNamespace(id=uid, bot=False, guild_permissions=SimpleNamespace(administrator=False), roles=list(roles))
        self.members = [member(1, self.roles[0]), member(2, self.roles[0], self.roles[5]), member(3, self.roles[0], self.roles[2])]
        interaction = await self.press(self.home(), "rollcall:btn:scope")
        busy = interaction.response.edit_message.await_args.kwargs
        self.assertIn("⏳", busy["embed"].description)
        self.assertTrue(all(c.item.disabled for c in busy["view"].children), "處理中按鈕全灰，不會以為沒按到再按一次")
        embed, view = self.shown(interaction)
        self.assertIn("點名範圍", embed.title)
        self.assertIn("身分組00（1 人）", embed.description)
        self.assertIn("身分組00 + 身分組05（1 人）", embed.description)
        self.assertNotIn("身分組02", embed.description, "排除身份組的人不算")
        self.assertEqual([c.custom_id for c in view.children], ["rollcall:btn:scope", "rollcall:btn:home"])
        self.assertNoNewMessages(interaction)

    async def test_manual_pick_explains_a_missing_rollcall_channel_on_the_panel(self):
        self.cog.service.do_roll_call = mock.AsyncMock(return_value=[])
        self.data["rollcall_channel_id"] = None
        interaction = await self.press(self.home(), "rollcall:btn:manual")
        embed, view = self.shown(interaction)
        self.assertIn("還沒綁點名頻道", embed.description)
        self.assertIn("未綁定", self.field(embed, "點名頻道"))
        self.cog.service.do_roll_call.assert_not_awaited()
        interaction.edit_original_response.assert_not_awaited()   # 擋下來就不用走「處理中」
        self.assertNoNewMessages(interaction)

        self.data["rollcall_channel_id"] = 77
        interaction = await self.press(self.home(), "rollcall:btn:manual")
        self.cog.service.do_roll_call.assert_awaited_once_with(manual=True)
        self.assertIn("⏳", interaction.response.edit_message.await_args.kwargs["embed"].description)
        embed, view = self.shown(interaction)
        self.assertIn("沒有符合資格", embed.description)
        self.assertFalse(self.item(view, "rollcall:btn:manual").item.disabled, "做完按鈕要回來")
        self.assertNoNewMessages(interaction)

        self.cog.service.do_roll_call = mock.AsyncMock(return_value=[SimpleNamespace(display_name="阿狗"), SimpleNamespace(display_name="米拉")])
        interaction = await self.press(self.home(), "rollcall:btn:manual")
        self.assertIn("已手動點名 2 人：阿狗, 米拉", self.shown(interaction)[0].description)

    async def test_picker_pages_past_25_and_applies_one_page(self):
        step = await self.press(self.rc.render_roles(self.cog.service, self.guild, "target")[1], "rollcall:btn:pick:target:add:0")
        embed, view = self.shown(step)
        self.assertFalse(any(isinstance(c.item, discord.ui.RoleSelect) for c in view.children), "原生身分組選單在私訊裡列不出東西")
        select = self.select(view)
        self.assertEqual(len(select.item.options), 25, "30 個身分組扣掉已設定的 2 個＝28 個，第一頁 25 個")
        self.assertEqual(select.item.max_values, 25)
        self.assertEqual(select.item.options[0].label, "身分組29", "由高到低列")
        self.assertEqual(select.custom_id, "rollcall:pick:target:add:0")
        self.assertIn("第 1／2 頁", embed.description)
        buttons = {c.item.label: c for c in view.children if isinstance(c.item, discord.ui.Button)}
        self.assertEqual(set(buttons), {"上一頁", "下一頁", "↩️ 回上一層"})
        self.assertTrue(buttons["上一頁"].item.disabled)
        self.assertEqual(buttons["下一頁"].custom_id, "rollcall:btn:pick:target:add:1")

        step = await self.press(view, "rollcall:btn:pick:target:add:1")
        embed, view = self.shown(step)
        select = self.select(view)
        self.assertEqual([o.label for o in select.item.options], ["身分組04", "身分組03", "身分組02"])
        self.assertEqual(select.custom_id, "rollcall:pick:target:add:1")
        self.assertTrue(self.item(view, "rollcall:btn:pick:target:add:1").item.disabled, "最後一頁「下一頁」灰掉")
        self.assertNoNewMessages(step)

        select.item._values = ["103", "104"]
        chosen = self.interaction()
        await select.callback(chosen)
        self.assertEqual(self.data["rollcall_target_role_ids"], [100, 101, 103, 104])
        embed, view = self.shown(chosen)
        self.assertEqual(embed.title, "🎯 目標身份組", "送出後回到那一組的設定畫面")
        self.assertIn("已新增 2 個身份組", embed.description)
        self.assertIn("身分組03", embed.description)
        self.assertNoNewMessages(chosen)

    async def test_remove_picker_lists_only_configured_roles(self):
        step = await self.press(self.rc.render_roles(self.cog.service, self.guild, "exclude")[1], "rollcall:btn:pick:exclude:remove:0")
        embed, view = self.shown(step)
        select = self.select(view)
        self.assertEqual([o.label for o in select.item.options], ["身分組02"])
        self.assertEqual([c.item.label for c in view.children if isinstance(c.item, discord.ui.Button)], ["↩️ 回上一層"], "一頁放得下就不放翻頁")
        select.item._values = ["102"]
        chosen = self.interaction()
        await select.callback(chosen)
        self.assertEqual(self.data["rollcall_exclude_role_ids"], [])
        embed, view = self.shown(chosen)
        self.assertIn("已移除 1 個身份組", embed.description)
        self.assertTrue(self.item(view, "rollcall:btn:pick:exclude:remove:0").item.disabled, "沒東西可移除那顆灰掉")
        self.assertNoNewMessages(chosen)

    async def test_picker_clamps_the_page_and_explains_when_nothing_to_pick(self):
        embed, view = self.rc.render_pick(self.cog.service, self.guild, "target", "add", 99)
        self.assertIn("第 2／2 頁", embed.description, "頁碼超過就夾回最後一頁（身分組刪掉後頁數會變少）")
        self.data["rollcall_target_role_ids"] = [r.id for r in self.roles]
        embed, view = self.rc.render_pick(self.cog.service, self.guild, "target", "add", 0)
        self.assertEqual(embed.title, "🎯 目標身份組", "沒得選就退回設定畫面")
        self.assertIn("沒有可新增的", embed.description)
        self.assertTrue(self.item(view, "rollcall:btn:pick:target:add:0").item.disabled)

    async def test_pending_list_names_the_members(self):
        """私訊裡 <@id> 要靠客戶端快取才顯示得出名字：清單自己印名字，離開的人也要看得出來。"""
        self.members = [SimpleNamespace(id=1, display_name="阿狗")]
        self.runtime.get_pending_list = lambda: [
            {"user_id": 1, "deadline": "2099-01-08T14:00:00+08:00"},
            {"user_id": 2, "deadline": "2099-01-09T14:00:00+08:00"},
        ]
        interaction = await self.press(self.home(), "rollcall:btn:pending")
        text = self.shown(interaction)[0].description
        self.assertIn("阿狗（<@1>）", text)
        self.assertIn("已離開？（<@2>）", text)
        self.assertNoNewMessages(interaction)

    async def test_a_failing_action_restores_the_panel_instead_of_leaving_it_grey(self):
        self.cog.service.do_roll_call = mock.AsyncMock(side_effect=RuntimeError("boom"))
        with self.assertLogs("commands.rollcall_commands", "ERROR"):
            interaction = await self.press(self.home(), "rollcall:btn:manual")
        embed, view = self.shown(interaction)
        self.assertIn("操作失敗", embed.description)
        self.assertIn("RuntimeError", embed.description)
        self.assertFalse(self.item(view, "rollcall:btn:manual").item.disabled, "不能停在「處理中」全灰")
        self.assertNoNewMessages(interaction)

    async def test_rescue_failing_too_is_logged_once_not_raised(self):
        """做到一半面板被刪（群主重開面板、手動刪掉）：救援畫面也改不了時只記一行，例外不再往外丟。"""
        self.cog.service.do_roll_call = mock.AsyncMock(return_value=[])
        interaction = self.interaction()
        interaction.edit_original_response = mock.AsyncMock(
            side_effect=discord.NotFound(SimpleNamespace(status=404, reason="Not Found"), {"message": "Unknown Message"}))
        with self.assertLogs("commands.rollcall_commands", "WARNING") as logs:
            await self.press(self.home(), "rollcall:btn:manual", interaction)
        self.assertEqual([r.levelname for r in logs.records], ["ERROR", "WARNING"])
        self.assertIn("面板可能已被刪", logs.output[-1])

    async def test_manual_pick_is_refused_while_another_pick_is_running(self):
        """自動排程或另一個裝置的手動點名還在跑：面板講原因，不再抽一批。"""
        self.cog.service.do_roll_call = mock.AsyncMock(return_value=[])
        async with self.cog.service._pick_lock:
            interaction = await self.press(self.home(), "rollcall:btn:manual")
        self.assertIn("正在抽選中", self.shown(interaction)[0].description)
        self.cog.service.do_roll_call.assert_not_awaited()
        self.assertNoNewMessages(interaction)

    # ── 重啟 ──

    async def test_buttons_and_select_survive_a_restart(self):
        """狀態都在 custom_id 裡：每個畫面的 custom_id 都對得上樣板、從 custom_id 還原得回同一顆；cog 登記的是 DynamicItem，不是整張 View。"""
        service = self.cog.service
        for _, view in (self.rc.render_home(service, self.guild), self.rc.render_roles(service, self.guild, "exclude"),
                        self.rc.render_pick(service, self.guild, "target", "add", 1), (await self.rc.render_pending(service, self.guild))):
            for c in view.children:
                template = self.rc.PICK_TEMPLATE if isinstance(c.item, discord.ui.Select) else self.rc.BUTTON_TEMPLATE
                self.assertIsNotNone(re.fullmatch(template, c.custom_id), c.custom_id)
            ids = [c.custom_id for c in view.children]
            self.assertEqual(len(ids), len(set(ids)), f"同一則訊息的 custom_id 不能重複：{ids}")

        match = re.fullmatch(self.rc.BUTTON_TEMPLATE, "rollcall:btn:pick:exclude:remove:3")
        button = await self.rc.RollCallButton.from_custom_id(
            self.interaction(), discord.ui.Button(label="下一頁", custom_id="rollcall:btn:pick:exclude:remove:3"), match)
        self.assertEqual((button.action, button.key, button.mode, button.page), ("pick", "exclude", "remove", 3))
        match = re.fullmatch(self.rc.BUTTON_TEMPLATE, "rollcall:btn:roles:target")
        button = await self.rc.RollCallButton.from_custom_id(
            self.interaction(), discord.ui.Button(label="x", custom_id="rollcall:btn:roles:target"), match)
        self.assertEqual((button.action, button.key, button.mode, button.page), ("roles", "target", None, 0))
        match = re.fullmatch(self.rc.PICK_TEMPLATE, "rollcall:pick:target:add:1")
        select = await self.rc.RollCallPickSelect.from_custom_id(
            self.interaction(), discord.ui.Select(custom_id="rollcall:pick:target:add:1",
                                                  options=[discord.SelectOption(label="身分組04", value="104")]), match)
        self.assertEqual((select.key, select.mode, select.page), ("target", "add", 1))
        self.assertEqual([o.value for o in select.item.options], ["104"])

        service.start = mock.AsyncMock()
        await self.cog.cog_load()
        # 名單寫死：拿 DYNAMIC_ITEMS 比自己什麼都過，少登記一個就是重啟後「此互動失敗」
        self.bot.add_dynamic_items.assert_called_once_with(
            self.rc.RollCallButton, self.rc.RollCallPickSelect, self.rc.LegacyPanelButton)
        self.assertEqual(self.bot.add_view.call_count, 1, "只有點名訊息的回覆按鈕是整張 persistent View")
        self.assertIsInstance(self.bot.add_view.call_args.args[0], self.rc.RollCallResponseView)

    async def test_slash_command_is_owner_only_and_allowed_in_dm(self):
        command = self.cog.send_admin_panel
        self.assertTrue(command.allowed_contexts.dm_channel and command.allowed_contexts.guild)
        self.cog.open_admin_panel = mock.AsyncMock()
        stranger = self.interaction(user_id=7)
        await command.callback(self.cog, stranger)
        self.cog.open_admin_panel.assert_not_awaited()
        owner = self.interaction()
        await command.callback(self.cog, owner)
        self.cog.open_admin_panel.assert_awaited_once_with(owner)


if __name__ == "__main__":
    unittest.main()
