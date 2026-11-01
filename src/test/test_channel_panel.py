"""頻道綁定面板（commands/channel_panel.py）與登記表的寫入點（settings/channel_registry.py 的 apply／unbind）。

守的底線：
- 面板是新版版面（LayoutView）：標題下一行頁碼與統計，列出登記表的每一項：依頻道型別分組（論壇、文字、語音，表單類最後）、
  每一項一行顯示目前綁的頻道（沒綁顯示「未綁定」）與說明、表單類顯示自己描述的現況；登記表多一筆，面板就多一列，不用改程式
- 超過每頁數量才分頁：第 1 頁「上一頁」不能按、最後一頁「下一頁」不能按；選單只列本頁的項目；頁碼超出範圍夾回來
- 每個操作都改面板這一則訊息（不另發訊息）：選了一項，面板換成「選頻道」的畫面，只列那一項允許的頻道型別（超過 25 個分頁）、
  有回上一層；選了頻道先切「處理中」（按鈕全灰）再寫進 config.json 的那個 key、跑綁定後動作，再換回面板、結果寫在標題下那一行；
  綁定後動作出錯要講、不能停在「處理中」；面板上有回主控台
- 表單類（Telegram 路由）：選了先開表單輸入來源；送出後面板換成選目標頻道（輸入正規化後帶在 custom_id、不可為空、不能太長或含冒號），
  選了交給登記的寫入函式、結果寫在面板上；同一個來源再設一次就多一個頻道、不重複；表單取消時私訊裡的面板用 bot 的身分重畫
- 每頁最多 25 項（一個選單的上限），設定超過也夾回來
- 解除綁定：換成只列本頁已綁項目的畫面，選了就刪 key、面板重畫
- 只有群主能操作；私訊裡也能用（bot 只在一個伺服器時）；只有本人看得到的面板 bot 不主動重畫
- 按鈕與選單的 custom_id 重啟後解析得回動作、頁碼、哪一項與表單輸入；做壞了換回面板並標錯誤

執行：
    cd src && python -m unittest test.test_channel_panel -v
"""
import copy
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import discord

from commands import channel_panel
from settings import channel_registry
from settings.channel_registry import ChannelSetting, InputSpec
from utils.discord_content import layout_text

OWNER = 42
TEXT, FORUM, VOICE = discord.ChannelType.text, discord.ChannelType.forum, discord.ChannelType.voice


class FakeConfig:
    """config.json 的替身：同一份 dict 給讀與寫。"""
    DEFAULT_ID = 1234567890

    def __init__(self, data):
        self.data = data
        self.writes = 0

    def load_config(self, caller="unknown"):
        return copy.deepcopy(self.data)

    async def get_configured_id(self, key, caller="unknown"):
        value = self.data.get(key)
        return int(value) if value and value != self.DEFAULT_ID else None

    async def update_config(self, apply, caller="unknown"):
        apply(self.data)
        self.writes += 1
        return copy.deepcopy(self.data)


def channel(cid, name, kind):
    return SimpleNamespace(id=cid, name=name, type=kind, mention=f"<#{cid}>")


class PanelTestBase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.on_set = mock.AsyncMock(return_value="\n🤖 已發面板")
        self.apply_input = mock.AsyncMock(side_effect=lambda text, cid: f"✅ 路由 {text} → {cid}")
        self.real_registry = channel_registry._REGISTRY
        self.registry = [
            ChannelSetting("交易頻道", FORUM, "trade_forum_channel_id", discord.Color.blue(), "交易"),
            ChannelSetting("AI 插話頻道", TEXT, "ambient_chat_channel_id", discord.Color.magenta(), "插話"),
            ChannelSetting("自我介紹頻道", TEXT, "intro_channel_id", discord.Color.purple(), "自介", on_set=self.on_set),
            ChannelSetting("Telegram 路由設定", None, None, discord.Color.teal(), "路由",
                           input=InputSpec("Telegram 來源", "例如 @Seele", TEXT, normalize=lambda t: t.strip().lstrip("@").lower()),
                           apply_input=self.apply_input, describe=lambda c: f"來源 → <#{c.get('route', 0)}>"),
            ChannelSetting("音樂語音頻道", VOICE, "music_voice_channel_id", discord.Color.red(), "音樂"),
            ChannelSetting("商品上架論壇", FORUM, "shop_forum_channel_id", discord.Color.gold(), "上架"),
            ChannelSetting("AI 日記頻道", TEXT, "ai_diary_channel_id", discord.Color.dark_purple(), "日記"),
        ]
        self.config = FakeConfig({"trade_forum_channel_id": 101, "ambient_chat_channel_id": 201,
                                  "music_voice_channel_id": 301, "route": 777})
        self.channels = [channel(101, "自由市場", FORUM), channel(102, "觀星者商店", FORUM),
                         channel(201, "閒聊", TEXT), channel(202, "雜談", TEXT), channel(301, "點歌台", VOICE)]
        self.guild = SimpleNamespace(id=1, channels=self.channels,
                                     get_channel=lambda cid: next((c for c in self.channels if c.id == cid), None))
        self.bot = SimpleNamespace(guilds=[self.guild], get_cog=lambda name: None)
        self._patchers = [
            mock.patch.object(channel_registry, "_REGISTRY", self.registry),
            mock.patch.object(channel_registry, "ChannelConfig", self.config),
            mock.patch.object(channel_panel, "ADMIN_CONSOLE_SETTINGS", SimpleNamespace(bindings_page_size=4)),
            mock.patch.dict(os.environ, {"OWNER_ID": str(OWNER)}),
        ]
        for p in self._patchers:
            p.start()
            self.addCleanup(p.stop)

    def interaction(self, *, user_id=OWNER, dm=True, ephemeral=False):
        state = {"done": False}

        async def mark_done(*args, **kwargs):
            state["done"] = True
        # 回應過（defer、send_message、edit_message、send_modal）之後 is_done 變 True，後面的換畫面才會像真的一樣改原訊息
        return SimpleNamespace(
            guild=None if dm else self.guild, client=self.bot, data={}, channel=SimpleNamespace(id=5),
            user=SimpleNamespace(id=user_id, display_name="群主"),
            message=SimpleNamespace(content="", flags=SimpleNamespace(ephemeral=ephemeral), edit=mock.AsyncMock()),
            response=SimpleNamespace(edit_message=mock.AsyncMock(side_effect=mark_done), send_message=mock.AsyncMock(side_effect=mark_done),
                                     defer=mock.AsyncMock(side_effect=mark_done), send_modal=mock.AsyncMock(side_effect=mark_done),
                                     is_done=lambda: state["done"]),
            followup=SimpleNamespace(send=mock.AsyncMock()),
            edit_original_response=mock.AsyncMock(),
        )

    def assert_layout_edit(self, kwargs):
        """改成新版版面的訊息：帶 view，並明確清掉 content 與 embed（舊的 embed 版面板才換得過去）。"""
        self.assertIsInstance(kwargs["view"], discord.ui.LayoutView)
        self.assertIn("content", kwargs)
        self.assertIsNone(kwargs["content"])
        self.assertIn("embed", kwargs)
        self.assertIsNone(kwargs["embed"])

    @staticmethod
    def items_of(view):
        """view 裡每一個元件本體（新版版面要走進 ActionRow；DynamicItem 包著的取 `.item`）。"""
        return [getattr(child, "item", child) for child in view.walk_children()]

    @classmethod
    def select_of(cls, view):
        """view 裡的選單本體。"""
        return next(item for item in cls.items_of(view) if isinstance(item, discord.ui.Select))

    def assert_unique_ids(self, view):
        """同一則訊息的 custom_id 不能重複（Discord 會整則退件）。"""
        ids = [getattr(i, "custom_id", None) for i in self.items_of(view)]
        ids = [i for i in ids if i]
        self.assertEqual(len(ids), len(set(ids)), f"custom_id 重複：{sorted(i for i in set(ids) if ids.count(i) > 1)}")

    @classmethod
    def button(cls, view, custom_id):
        for item in cls.items_of(view):
            if getattr(item, "custom_id", None) == custom_id:
                return item
        raise AssertionError(f"沒有 {custom_id}：{[getattr(i, 'custom_id', None) for i in cls.items_of(view)]}")


class RenderTests(PanelTestBase):
    async def test_lists_every_item_grouped_by_type_with_its_binding(self):
        with mock.patch.object(channel_panel, "ADMIN_CONSOLE_SETTINGS", SimpleNamespace(bindings_page_size=25)):
            view, page = await channel_panel.render(self.guild, 0)
        self.assertIsInstance(view, discord.ui.LayoutView)
        self.assertTrue(view.is_persistent(), "重啟後按鈕要能按")
        text = layout_text(view)
        order = [text.index(name) for name in ("**📌 論壇頻道（2）**", "交易頻道", "商品上架論壇",
                                               "**📝 文字頻道（3）**", "AI 插話頻道", "自我介紹頻道", "AI 日記頻道",
                                               "**🔊 語音頻道（1）**", "音樂語音頻道", "Telegram 路由設定")]
        self.assertEqual(order, sorted(order), "依型別分組、組內照登記順序、表單類最後")
        self.assertIn("**交易頻道**　<#101>　· 交易", text, "名稱、頻道、說明同一行")
        self.assertIn("**商品上架論壇**　未綁定", text)
        self.assertIn("**音樂語音頻道**　<#301>", text)
        self.assertIn("**Telegram 路由設定**　來源 → <#777>", text, "表單類顯示自己描述的現況")
        header = text.split("\n")[1]
        self.assertIn("第 1／1 頁", header)
        self.assertIn("共 7 項、已綁 3 項", header)
        self.assertIn("改了馬上生效", header)
        self.assertEqual(page, 0)
        self.assertLessEqual(len(view.to_components()), 40)
        self.assert_unique_ids(view)
        self.assertEqual([o.value for o in self.select_of(view).options],
                         [s.label for s in channel_registry.display_order()], "選單列的就是面板上的項目")

    async def test_registry_growth_adds_a_row(self):
        self.registry.append(ChannelSetting("歡迎頻道", TEXT, "welcome_channel_id", discord.Color.green(), "歡迎"))
        with mock.patch.object(channel_panel, "ADMIN_CONSOLE_SETTINGS", SimpleNamespace(bindings_page_size=25)):
            view, _ = await channel_panel.render(self.guild, 0)
        text = layout_text(view)
        self.assertIn("**歡迎頻道**　未綁定", text)
        self.assertIn("共 8 項", text)
        self.assertIn("**📝 文字頻道（4）**", text)

    async def test_pages_follow_the_page_size(self):
        view, page = await channel_panel.render(self.guild, 0)
        self.assertIn("第 1／2 頁", layout_text(view))
        self.assertTrue(self.button(view, "chpanel:prev:0").disabled, "第 1 頁沒有上一頁")
        self.assertFalse(self.button(view, "chpanel:next:0").disabled)
        self.assertEqual(self.button(view, "chpanel:unbind:0").label, "解除某一項")
        self.assertEqual([o.value for o in self.select_of(view).options],
                         ["交易頻道", "商品上架論壇", "AI 插話頻道", "自我介紹頻道"], "選單只列本頁")
        self.assertNotIn("音樂語音頻道", layout_text(view))

        view, page = await channel_panel.render(self.guild, 9)
        self.assertEqual(page, 1, "超出範圍夾回最後一頁")
        self.assertIn("第 2／2 頁", layout_text(view))
        self.assertTrue(self.button(view, "chpanel:next:1").disabled, "最後一頁沒有下一頁")
        self.assertFalse(self.button(view, "chpanel:prev:1").disabled)
        self.assertEqual([o.value for o in self.select_of(view).options],
                         ["AI 日記頻道", "音樂語音頻道", "Telegram 路由設定"])
        self.assertIn("**🔊 語音頻道（1）**", layout_text(view), "分組標題跟著項目走，不會因為翻頁消失")

    def test_custom_ids_round_trip(self):
        button = channel_panel.PanelButton("next", 1, label="下一頁 ▶")
        m = channel_panel.PanelButton.__discord_ui_compiled_template__.fullmatch(button.item.custom_id)
        self.assertEqual((m["action"], int(m["page"]), m["label"]), ("next", 1, None))
        button = channel_panel.PanelButton("chan", 0, "Telegram 路由設定", 1, "seele_ww_leak", label="下一頁 ▶")
        m = channel_panel.PanelButton.__discord_ui_compiled_template__.fullmatch(button.item.custom_id)
        self.assertEqual((m["action"], m["page"], m["label"], m["sub"], m["text"]), ("chan", "0", "Telegram 路由設定", "1", "seele_ww_leak"))
        select = channel_panel.PanelPickSelect(2)
        m = channel_panel.PanelPickSelect.__discord_ui_compiled_template__.fullmatch(select.item.custom_id)
        self.assertEqual(int(m["page"]), 2)
        self.assertTrue(select.item.disabled, "沒有項目時選單不能選")
        chooser = channel_panel.ChannelSelect(0, "交易頻道", 1)
        m = channel_panel.ChannelSelect.__discord_ui_compiled_template__.fullmatch(chooser.item.custom_id)
        self.assertEqual((m["page"], m["label"], m["sub"], m["text"]), ("0", "交易頻道", "1", None))
        m = channel_panel.UnbindSelect.__discord_ui_compiled_template__.fullmatch(channel_panel.UnbindSelect(3).item.custom_id)
        self.assertEqual(m["page"], "3")
        self.assertEqual(channel_panel.DYNAMIC_ITEMS, (channel_panel.PanelButton, channel_panel.PanelPickSelect,
                                                       channel_panel.ChannelSelect, channel_panel.UnbindSelect))


class FlowTests(PanelTestBase):
    """每個操作都改面板這一則：沒有 send_message、沒有 followup。"""

    @staticmethod
    def shown(interaction):
        """最後一次換畫面的 kwargs：改原訊息（處理中之後）優先，否則就是用回應改的那次。"""
        call = interaction.edit_original_response.await_args or interaction.response.edit_message.await_args
        return call.kwargs

    def assertNoNewMessages(self, interaction):
        interaction.response.send_message.assert_not_awaited()
        interaction.followup.send.assert_not_awaited()

    def pick_select(self, page=0, items=None):
        return channel_panel.PanelPickSelect(page, options=[channel_panel._option(s) for s in (items or self.registry[:4])])

    async def press_next(self, page):
        interaction = self.interaction()
        await channel_panel.PanelButton("next", page, label="下一頁 ▶").callback(interaction)
        return interaction

    async def test_next_page_redraws_the_same_message(self):
        interaction = await self.press_next(0)
        kwargs = interaction.response.edit_message.await_args.kwargs
        self.assert_layout_edit(kwargs)
        self.assertIn("第 2／2 頁", layout_text(kwargs["view"]))
        self.assertEqual(self.select_of(kwargs["view"]).custom_id, "chpanel:pick:1")
        self.assertNoNewMessages(interaction)

    async def test_pick_then_choose_channel_on_the_same_message_writes_the_key_and_runs_on_set(self):
        interaction = self.interaction()
        select = self.pick_select()
        select.item._values = ["自我介紹頻道"]
        await select.callback(interaction)
        kwargs = interaction.response.edit_message.await_args.kwargs
        self.assert_layout_edit(kwargs)
        text = layout_text(kwargs["view"])
        self.assertIn("改「自我介紹頻道」", text)
        self.assertIn("目前綁 未綁定", text)
        self.assertIn("只能綁📝 文字頻道", text)
        picker = self.select_of(kwargs["view"])
        self.assertEqual([o.value for o in picker.options], ["201", "202"], "只列文字頻道")
        self.assertEqual(picker.custom_id, "chpanel:chansel:0:自我介紹頻道:0")
        self.assertEqual([getattr(i, "custom_id", None) for i in self.items_of(kwargs["view"]) if isinstance(i, discord.ui.Button)],
                         ["chpanel:refresh:0"], "兩個頻道一頁放得下，只有回上一層")
        self.assertNoNewMessages(interaction)

        pick = self.interaction()
        chooser = next(c for c in kwargs["view"].walk_children() if isinstance(getattr(c, "item", None), discord.ui.Select))
        chooser.item._values = ["202"]
        await chooser.callback(pick)
        self.assertEqual(self.config.data["intro_channel_id"], 202)
        ctx = self.on_set.await_args.args[0]
        self.assertEqual((ctx.channel.id, ctx.guild, ctx.bot), (202, self.guild, self.bot))
        self.assertEqual(ctx.config["intro_channel_id"], 202, "綁定後動作讀設定檔就拿得到新頻道")
        busy = pick.response.edit_message.await_args.kwargs
        self.assertIn("正在寫入「自我介紹頻道」", layout_text(busy["view"]), "先切「處理中」再寫檔（3 秒限制）")
        self.assertTrue(all(getattr(i, "disabled", True) for i in self.items_of(busy["view"])
                            if isinstance(i, (discord.ui.Button, discord.ui.Select))), "處理中按鈕全灰")
        final = self.shown(pick)
        self.assert_layout_edit(final)
        text = layout_text(final["view"])
        self.assertIn("✅", text)
        self.assertIn("<#202>", text)
        self.assertIn("已發面板", text, "綁定後動作的附註接在後面")
        self.assertIn("**自我介紹頻道**　<#202>", text, "面板照現況重畫")
        self.assertNoNewMessages(pick)

    async def test_write_happens_after_the_first_reply(self):
        order = []
        self.on_set.side_effect = lambda ctx: order.append("on_set") or "\n🤖 已發面板"
        pick = self.interaction()
        pick.response.edit_message.side_effect = lambda **kw: order.append("reply")
        chooser = channel_panel.ChannelSelect(0, "自我介紹頻道", 0, options=[discord.SelectOption(label="雜談", value="202")])
        chooser.item._values = ["202"]
        await chooser.callback(pick)
        self.assertEqual(order[:2], ["reply", "on_set"], "第一次改畫面（處理中）在寫檔之前")

    async def test_on_set_error_is_reported_and_panel_still_redrawn(self):
        self.on_set.side_effect = RuntimeError("面板發不出去")
        pick = self.interaction()
        chooser = channel_panel.ChannelSelect(0, "自我介紹頻道", 0, options=[discord.SelectOption(label="雜談", value="202")])
        chooser.item._values = ["202"]
        with self.assertLogs("commands.channel_panel", "ERROR"):
            await chooser.callback(pick)
        self.assertEqual(self.config.data["intro_channel_id"], 202, "設定已經寫進去了")
        text = layout_text(self.shown(pick)["view"])
        self.assertIn("出錯", text)
        self.assertIn("**自我介紹頻道**　<#202>", text, "面板照現況重畫")
        self.assertNoNewMessages(pick)

    async def test_wrong_channel_type_is_refused_on_the_panel(self):
        pick = self.interaction()
        chooser = channel_panel.ChannelSelect(0, "自我介紹頻道", 0, options=[discord.SelectOption(label="自由市場", value="101")])
        chooser.item._values = ["101"]
        await chooser.callback(pick)
        self.assertNotIn("intro_channel_id", self.config.data)
        self.assertIn("不是文字頻道", layout_text(self.shown(pick)["view"]))

    async def test_channel_picker_pages_past_25(self):
        self.channels.extend(channel(1000 + n, f"聊天-{n:02d}", TEXT) for n in range(30))
        view = await channel_panel.render_channel_pick(self.guild, self.registry[1], 1, 0)
        self.assert_unique_ids(view)
        text = layout_text(view)
        self.assertIn("第 1／2 頁，共 32 個文字頻道", text)
        self.assertEqual(len(self.select_of(view).options), 25)
        self.assertEqual(self.select_of(view).custom_id, "chpanel:chansel:1:AI 插話頻道:0")
        self.assertTrue(self.button(view, "chpanel:chan:1:AI 插話頻道:0").disabled, "第一頁沒有上一頁")
        self.assertFalse(self.button(view, "chpanel:chan:1:AI 插話頻道:1").disabled)
        interaction = self.interaction()
        await channel_panel.PanelButton("chan", 1, "AI 插話頻道", 1, label="下一頁 ▶").callback(interaction)
        view = interaction.response.edit_message.await_args.kwargs["view"]
        self.assert_unique_ids(view)
        self.assertEqual(len(self.select_of(view).options), 7)
        self.assertEqual(self.select_of(view).custom_id, "chpanel:chansel:1:AI 插話頻道:1")
        self.assertTrue(self.button(view, "chpanel:chan:1:AI 插話頻道:1").disabled, "最後一頁沒有下一頁")
        self.assertEqual(self.button(view, "chpanel:refresh:1").label, "↩️ 回上一層", "回到面板原本那一頁")
        self.assertNoNewMessages(interaction)

    async def test_no_channel_of_that_type_falls_back_to_the_panel(self):
        self.channels[:] = [c for c in self.channels if c.type != VOICE]
        view = await channel_panel.render_channel_pick(self.guild, self.registry[4], 1, 0)
        self.assertIn("沒有語音頻道，沒辦法綁「音樂語音頻道」", layout_text(view))
        self.assertEqual(self.select_of(view).custom_id, "chpanel:pick:1", "退回面板那一頁")

    async def test_page_size_is_capped_by_the_select_limit(self):
        with mock.patch.object(channel_panel, "ADMIN_CONSOLE_SETTINGS", SimpleNamespace(bindings_page_size=99)):
            self.assertEqual(channel_panel.page_size(), 25)
        from pydantic import ValidationError
        from sys_settings.admin_console_settings import AdminConsoleSettings
        with self.assertRaises(ValidationError):
            AdminConsoleSettings(bindings_page_size=40)

    async def test_input_item_opens_a_form_then_picks_the_channel_on_the_same_message(self):
        """表單類（Telegram 路由）：選了先開表單；送出後面板換成選目標頻道（輸入帶在 custom_id）；選了就交給它的寫入函式。"""
        interaction = self.interaction()
        select = self.pick_select(1, self.registry[4:])
        select.item._values = ["Telegram 路由設定"]
        await select.callback(interaction)
        modal = interaction.response.send_modal.await_args.args[0]
        self.assertIsInstance(modal, channel_panel.InputModal)
        self.assertEqual((modal.text.placeholder, modal.text.max_length), ("例如 @Seele", 100), "欄位照登記的規格長")
        interaction.message.edit.assert_awaited_once()   # 私訊裡的面板用 bot 的身分重畫（表單取消也不會卡在選取狀態）
        interaction.response.edit_message.assert_not_awaited()

        modal.text._value = " @Seele_WW_leak "
        submit = self.interaction()
        await modal.on_submit(submit)
        kwargs = submit.response.edit_message.await_args.kwargs
        self.assert_layout_edit(kwargs)
        self.assertIn("Telegram 路由設定：seele_ww_leak", layout_text(kwargs["view"]), "輸入先正規化")
        picker = self.select_of(kwargs["view"])
        self.assertEqual(picker.custom_id, "chpanel:chansel:1:Telegram 路由設定:0:seele_ww_leak")
        self.assertEqual([o.value for o in picker.options], ["201", "202"], "只列文字頻道")
        self.assertNoNewMessages(submit)

        pick = self.interaction()
        chooser = next(c for c in kwargs["view"].walk_children() if isinstance(getattr(c, "item", None), discord.ui.Select))
        self.assertEqual((chooser.label_of, chooser.text), ("Telegram 路由設定", "seele_ww_leak"))
        chooser.item._values = ["202"]
        await chooser.callback(pick)
        self.apply_input.assert_awaited_once_with("seele_ww_leak", 202)
        self.assertIn("✅ 路由 seele_ww_leak → 202", layout_text(self.shown(pick)["view"]), "寫入函式回的那句寫在面板上")
        self.assertEqual(self.config.writes, 0, "表單類不走 apply")
        self.assertNoNewMessages(pick)

    async def test_input_is_validated_before_picking(self):
        for raw, hint in (("   ", "不可為空"), ("a:b", "含冒號"), ("x" * 61, "太長")):
            modal = channel_panel.InputModal(self.registry[3], 1)
            modal.text._value = raw
            submit = self.interaction()
            await modal.on_submit(submit)
            text = layout_text(submit.response.edit_message.await_args.kwargs["view"])
            self.assertIn(hint, text, raw)
            self.assertEqual(self.select_of(submit.response.edit_message.await_args.kwargs["view"]).custom_id, "chpanel:pick:1", "退回面板")

    async def test_ephemeral_panel_is_not_redrawn_by_the_bot(self):
        interaction = self.interaction(dm=False, ephemeral=True)
        select = self.pick_select(1, self.registry[4:])
        select.item._values = ["Telegram 路由設定"]
        await select.callback(interaction)
        interaction.response.send_modal.assert_awaited_once()
        interaction.message.edit.assert_not_awaited()

    async def test_unbind_is_a_screen_on_the_same_message(self):
        interaction = self.interaction()
        await channel_panel.PanelButton("unbind", 0, label="解除某一項").callback(interaction)
        kwargs = interaction.response.edit_message.await_args.kwargs
        self.assert_layout_edit(kwargs)
        chooser = self.select_of(kwargs["view"])
        self.assert_unique_ids(kwargs["view"])
        self.assertEqual(chooser.custom_id, "chpanel:unbsel:0")
        self.assertEqual([o.value for o in chooser.options], ["交易頻道", "AI 插話頻道"], "只列本頁已綁的")
        self.assertEqual(self.button(kwargs["view"], "chpanel:refresh:0").label, "↩️ 回上一層")
        self.assertNoNewMessages(interaction)

        pick = self.interaction()
        unbind = next(c for c in kwargs["view"].walk_children() if isinstance(getattr(c, "item", None), discord.ui.Select))
        unbind.item._values = ["AI 插話頻道"]
        await unbind.callback(pick)
        self.assertNotIn("ambient_chat_channel_id", self.config.data)
        self.assertEqual(self.config.data["trade_forum_channel_id"], 101, "其他 key 不動")
        self.assertIn("正在解除", layout_text(pick.response.edit_message.await_args.kwargs["view"]), "先切處理中再寫檔")
        text = layout_text(self.shown(pick)["view"])
        self.assertIn("已解除「AI 插話頻道」", text)
        self.assertIn("<#201>", text)
        self.assertIn("**AI 插話頻道**　未綁定", text, "面板照現況重畫")
        self.assertNoNewMessages(pick)

    async def test_unbind_with_nothing_bound_on_this_page(self):
        self.config.data.clear()
        interaction = self.interaction()
        await channel_panel.PanelButton("unbind", 0, label="解除某一項").callback(interaction)
        view = interaction.response.edit_message.await_args.kwargs["view"]
        self.assertIn("沒有已綁定", layout_text(view))
        self.assertEqual(self.select_of(view).custom_id, "chpanel:pick:0", "留在面板")

    async def test_stale_item_is_explained_on_the_panel(self):
        interaction = self.interaction()
        chooser = channel_panel.ChannelSelect(0, "已經不存在的項目", 0, options=[discord.SelectOption(label="雜談", value="202")])
        chooser.item._values = ["202"]
        await chooser.callback(interaction)
        self.assertIn("找不到這一項", layout_text(interaction.response.edit_message.await_args.kwargs["view"]))
        self.assertEqual(self.config.writes, 0)

    async def test_a_failing_action_restores_the_panel(self):
        with mock.patch.object(channel_panel, "render_unbind", mock.AsyncMock(side_effect=RuntimeError("boom"))):
            interaction = self.interaction()
            with self.assertLogs("commands.channel_panel", "ERROR"):
                await channel_panel.PanelButton("unbind", 1, label="解除某一項").callback(interaction)
        view = interaction.response.edit_message.await_args.kwargs["view"]
        self.assertIn("操作失敗（RuntimeError）", layout_text(view))
        self.assertEqual(self.select_of(view).custom_id, "chpanel:pick:1", "換回面板原本那一頁")

    async def test_non_owner_is_refused_everywhere(self):
        select = self.pick_select()
        select.item._values = ["AI 插話頻道"]
        chooser = channel_panel.ChannelSelect(0, "AI 插話頻道", 0, options=[discord.SelectOption(label="雜談", value="202")])
        chooser.item._values = ["202"]
        unbind = channel_panel.UnbindSelect(0, options=[discord.SelectOption(label="交易頻道", value="交易頻道")])
        unbind.item._values = ["交易頻道"]
        modal = channel_panel.InputModal(self.registry[3], 1)
        modal.text._value = "x"
        actions = (channel_panel.PanelButton("next", 0, label="下一頁 ▶").callback, select.callback, chooser.callback,
                   unbind.callback, modal.on_submit)
        with mock.patch.dict(os.environ, {"OWNER_ID": "1"}):
            for action in actions:
                interaction = self.interaction()
                await action(interaction)
                interaction.response.edit_message.assert_not_awaited()
                interaction.followup.send.assert_not_awaited()
                self.assertIn("擁有者", interaction.response.send_message.await_args.kwargs["content"])
        self.assertEqual(self.config.writes, 0)

    async def test_dm_with_several_guilds_asks_to_use_the_server(self):
        self.bot.guilds.append(SimpleNamespace(id=2))
        interaction = self.interaction()
        await channel_panel.PanelButton("refresh", 0, label="重新整理").callback(interaction)
        interaction.response.edit_message.assert_not_awaited()
        self.assertIn("伺服器", interaction.response.send_message.await_args.kwargs["content"])

    async def test_panel_has_a_way_back_to_the_console(self):
        view, _ = await channel_panel.render(self.guild, 0)
        self.assertEqual(self.button(view, "console:home").label, "↩️ 回主控台")
        view, _ = await channel_panel.render(self.guild, 0, notice="✅ 已將「交易頻道」設定為 <#101>", busy=True)
        self.assertIn("✅ 已將「交易頻道」設定為 <#101>", layout_text(view).split("\n")[2], "結果寫在標題下那一行")
        self.assertTrue(all(i.disabled for i in self.items_of(view) if isinstance(i, (discord.ui.Button, discord.ui.Select))))


class RegistryWriteTests(PanelTestBase):
    async def test_apply_refuses_custom_items(self):
        with self.assertRaises(ValueError):
            await channel_registry.apply(self.registry[3], bot=self.bot, guild=self.guild, channel=self.channels[2])

    async def test_telegram_route_is_registered_as_an_input_item_and_dedups(self):
        """真的登記表裡 Telegram 路由是表單類（先輸入來源、再選文字頻道）；寫入同一個頻道不重複、回目前幾個。"""
        telegram = next(s for s in self.real_registry if s.label == "Telegram 路由設定")
        self.assertIsNotNone(telegram.input)
        self.assertEqual(telegram.input.pick_type, TEXT)
        self.assertEqual(telegram.input.normalize(" @Seele_WW_leak "), "seele_ww_leak")
        self.assertEqual(telegram.input.normalize("https://t.me/Seele_WW_leak"), "seele_ww_leak")
        await telegram.apply_input("seele_ww_leak", 202)
        reply = await telegram.apply_input("seele_ww_leak", 202)
        self.assertEqual(self.config.data["telegram_channel_routes"], {"seele_ww_leak": [202]}, "同一個頻道不重複")
        self.assertIn("目前目標頻道數：1", reply, "重複加的那次也要講對數字")
        reply = await telegram.apply_input("seele_ww_leak", 201)
        self.assertEqual(self.config.data["telegram_channel_routes"], {"seele_ww_leak": [202, 201]})
        self.assertIn("目前目標頻道數：2", reply)
        self.assertIn("<#201>", reply)

    async def test_unbind_returns_previous_and_tolerates_missing(self):
        self.assertEqual(await channel_registry.unbind(self.registry[0]), 101)
        self.assertIsNone(await channel_registry.unbind(self.registry[0]))
        self.assertIsNone(await channel_registry.unbind(self.registry[3]), "表單類沒有 key 可以解除")

    def test_telegram_routes_normalises_values(self):
        routes = channel_registry.telegram_routes({"telegram_channel_routes": {
            "a": [1, "2", 2, "x", 0], "b": "7", "c": None, "d": 3}})
        self.assertEqual(routes, {"a": [1, 2], "b": [7], "c": [], "d": [3]})
        self.assertEqual(channel_registry.telegram_routes({"telegram_channel_routes": "bad"}), {})


if __name__ == "__main__":
    unittest.main()
