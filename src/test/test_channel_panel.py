"""頻道綁定面板（commands/channel_panel.py）與登記表的寫入點（settings/channel_registry.py 的 apply／unbind）。

守的底線：
- 面板列出登記表的每一項：依頻道型別分組（論壇、文字、語音，表單類最後）、每一項顯示目前綁的頻道（沒綁顯示「未綁定」）、
  表單類顯示自己描述的現況；登記表多一筆，面板就多一列，不用改程式
- 超過每頁數量才分頁：第 1 頁「上一頁」不能按、最後一頁「下一頁」不能按；選單只列本頁的項目；頁碼超出範圍夾回來
- 選了一項：面板重畫成沒選取，另回一則只有本人看得到的頻道清單，只列那一項允許的頻道型別；選了頻道先回「寫入中」再寫進
  config.json 的那個 key、跑綁定後動作、面板重畫；綁定後動作出錯要講、不能停在「寫入中」；表單類的項目開它自己的流程
- Telegram 路由：表單只輸入來源，目標頻道用 bot 自己列的文字頻道清單選（私訊裡也能用）；同一個來源再設一次就多一個頻道、不重複
- 每頁最多 25 項（一個選單的上限），設定超過也夾回來
- 解除綁定：只列本頁已綁的項目，選了就刪 key、面板重畫
- 只有群主能操作；私訊裡也能用（bot 只在一個伺服器時）；只有本人看得到的面板 bot 不主動重畫
- 按鈕與選單的 custom_id 重啟後解析得回動作與頁碼

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
from settings.channel_registry import ChannelSetting

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
        self.custom_handler = mock.AsyncMock()
        self.registry = [
            ChannelSetting("交易頻道", FORUM, "trade_forum_channel_id", discord.Color.blue(), "交易"),
            ChannelSetting("AI 插話頻道", TEXT, "ambient_chat_channel_id", discord.Color.magenta(), "插話"),
            ChannelSetting("自我介紹頻道", TEXT, "intro_channel_id", discord.Color.purple(), "自介", on_set=self.on_set),
            ChannelSetting("Telegram 路由設定", None, None, discord.Color.teal(), "路由",
                           custom_handler=self.custom_handler, describe=lambda c: f"來源 → <#{c.get('route', 0)}>"),
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
        return SimpleNamespace(
            guild=None if dm else self.guild, client=self.bot, data={}, channel=SimpleNamespace(id=5),
            user=SimpleNamespace(id=user_id, display_name="群主"),
            message=SimpleNamespace(content="", flags=SimpleNamespace(ephemeral=ephemeral), edit=mock.AsyncMock()),
            response=SimpleNamespace(edit_message=mock.AsyncMock(), send_message=mock.AsyncMock(),
                                     defer=mock.AsyncMock(), send_modal=mock.AsyncMock(), is_done=lambda: False),
            followup=SimpleNamespace(send=mock.AsyncMock()),
            edit_original_response=mock.AsyncMock(),
        )

    @staticmethod
    def select_of(view):
        """view 裡的選單本體（DynamicItem 包著的取 `.item`）。"""
        return next(getattr(child, "item", child) for child in view.children
                    if isinstance(getattr(child, "item", child), discord.ui.Select))

    @staticmethod
    def button(view, custom_id):
        for child in view.children:
            item = getattr(child, "item", child)
            if getattr(item, "custom_id", None) == custom_id:
                return item
        raise AssertionError(f"沒有 {custom_id}：{[getattr(getattr(c, 'item', c), 'custom_id', None) for c in view.children]}")


class RenderTests(PanelTestBase):
    async def test_lists_every_item_grouped_by_type_with_its_binding(self):
        with mock.patch.object(channel_panel, "ADMIN_CONSOLE_SETTINGS", SimpleNamespace(bindings_page_size=25)):
            embed, view, page = await channel_panel.render(self.guild, 0)
        text = embed.description
        order = [text.index(name) for name in ("📌 **論壇頻道**（2）", "交易頻道", "商品上架論壇",
                                               "📝 **文字頻道**（3）", "AI 插話頻道", "自我介紹頻道", "AI 日記頻道",
                                               "🔊 **語音頻道**（1）", "音樂語音頻道", "Telegram 路由設定")]
        self.assertEqual(order, sorted(order), "依型別分組、組內照登記順序、表單類最後")
        self.assertIn("**交易頻道**　<#101>", text)
        self.assertIn("**商品上架論壇**　未綁定", text)
        self.assertIn("**音樂語音頻道**　<#301>", text)
        self.assertIn("**Telegram 路由設定**　來源 → <#777>", text, "表單類顯示自己描述的現況")
        self.assertIn("-# 插話", text, "說明放在那一列底下")
        self.assertIn("共 7 項、已綁 3 項", embed.footer.text)
        self.assertIn("第 1／1 頁", embed.footer.text)
        self.assertEqual(page, 0)
        self.assertEqual([o.value for o in self.select_of(view).options],
                         [s.label for s in channel_registry.display_order()], "選單列的就是面板上的項目")

    async def test_registry_growth_adds_a_row(self):
        self.registry.append(ChannelSetting("歡迎頻道", TEXT, "welcome_channel_id", discord.Color.green(), "歡迎"))
        with mock.patch.object(channel_panel, "ADMIN_CONSOLE_SETTINGS", SimpleNamespace(bindings_page_size=25)):
            embed, _, _ = await channel_panel.render(self.guild, 0)
        self.assertIn("**歡迎頻道**　未綁定", embed.description)
        self.assertIn("共 8 項", embed.footer.text)
        self.assertIn("📝 **文字頻道**（4）", embed.description)

    async def test_pages_follow_the_page_size(self):
        embed, view, page = await channel_panel.render(self.guild, 0)
        self.assertIn("第 1／2 頁", embed.footer.text)
        self.assertTrue(self.button(view, "chpanel:prev:0").disabled, "第 1 頁沒有上一頁")
        self.assertFalse(self.button(view, "chpanel:next:0").disabled)
        self.assertEqual([o.value for o in self.select_of(view).options],
                         ["交易頻道", "商品上架論壇", "AI 插話頻道", "自我介紹頻道"], "選單只列本頁")
        self.assertNotIn("音樂語音頻道", embed.description)

        embed, view, page = await channel_panel.render(self.guild, 9)
        self.assertEqual(page, 1, "超出範圍夾回最後一頁")
        self.assertIn("第 2／2 頁", embed.footer.text)
        self.assertTrue(self.button(view, "chpanel:next:1").disabled, "最後一頁沒有下一頁")
        self.assertFalse(self.button(view, "chpanel:prev:1").disabled)
        self.assertEqual([o.value for o in self.select_of(view).options],
                         ["AI 日記頻道", "音樂語音頻道", "Telegram 路由設定"])
        self.assertIn("🔊 **語音頻道**（1）", embed.description, "分組標題跟著項目走，不會因為翻頁消失")

    def test_custom_ids_round_trip(self):
        button = channel_panel.PanelButton("next", 1, label="下一頁 ▶")
        m = channel_panel.PanelButton.__discord_ui_compiled_template__.fullmatch(button.item.custom_id)
        self.assertEqual((m["action"], int(m["page"])), ("next", 1))
        select = channel_panel.PanelPickSelect(2)
        m = channel_panel.PanelPickSelect.__discord_ui_compiled_template__.fullmatch(select.item.custom_id)
        self.assertEqual(int(m["page"]), 2)
        self.assertTrue(select.item.disabled, "沒有項目時選單不能選")


class FlowTests(PanelTestBase):
    async def press_next(self, page):
        interaction = self.interaction()
        await channel_panel.PanelButton("next", page, label="下一頁 ▶").callback(interaction)
        return interaction

    async def test_next_page_redraws_the_same_message(self):
        interaction = await self.press_next(0)
        kwargs = interaction.response.edit_message.await_args.kwargs
        self.assertIn("第 2／2 頁", kwargs["embed"].footer.text)
        self.assertEqual(self.select_of(kwargs["view"]).custom_id, "chpanel:pick:1")

    async def test_pick_then_choose_channel_writes_the_key_and_runs_on_set(self):
        interaction = self.interaction()
        select = channel_panel.PanelPickSelect(0, options=[channel_panel._option(s) for s in self.registry[:4]])
        select.item._values = ["自我介紹頻道"]
        await select.callback(interaction)
        self.assertIn("embed", interaction.response.edit_message.await_args.kwargs, "面板先重畫成沒選取")
        sent = interaction.followup.send.await_args.kwargs
        self.assertTrue(sent["ephemeral"])
        self.assertIn("目前綁 未綁定", sent["embed"].description)
        self.assertIn("只能綁📝 文字頻道", sent["embed"].description)
        picker = self.select_of(sent["view"])
        self.assertEqual([o.value for o in picker.options], ["201", "202"], "只列文字頻道")

        pick = self.interaction()
        picker._values = ["202"]
        await picker.callback(pick)
        self.assertEqual(self.config.data["intro_channel_id"], 202)
        ctx = self.on_set.await_args.args[0]
        self.assertEqual((ctx.channel.id, ctx.guild, ctx.bot), (202, self.guild, self.bot))
        self.assertEqual(ctx.config["intro_channel_id"], 202, "綁定後動作讀設定檔就拿得到新頻道")
        self.assertIn("寫入", pick.response.edit_message.await_args.kwargs["content"], "先回應再寫檔（3 秒限制）")
        reply = pick.edit_original_response.await_args.kwargs["content"]
        self.assertIn("✅", reply)
        self.assertIn("<#202>", reply)
        self.assertIn("已發面板", reply, "綁定後動作的附註接在後面")
        interaction.message.edit.assert_awaited_once()
        self.assertIn("**自我介紹頻道**　<#202>", interaction.message.edit.await_args.kwargs["embed"].description)

    async def test_write_happens_after_the_first_reply(self):
        order = []
        self.on_set.side_effect = lambda ctx: order.append("on_set") or "\n🤖 已發面板"
        interaction = self.interaction()
        select = channel_panel.PanelPickSelect(0, options=[channel_panel._option(s) for s in self.registry[:4]])
        select.item._values = ["自我介紹頻道"]
        await select.callback(interaction)
        picker = self.select_of(interaction.followup.send.await_args.kwargs["view"])
        pick = self.interaction()
        pick.response.edit_message.side_effect = lambda **kw: order.append("reply")
        picker._values = ["202"]
        await picker.callback(pick)
        self.assertEqual(order, ["reply", "on_set"])

    async def test_on_set_error_is_reported_and_panel_still_redrawn(self):
        self.on_set.side_effect = RuntimeError("面板發不出去")
        interaction = self.interaction()
        select = channel_panel.PanelPickSelect(0, options=[channel_panel._option(s) for s in self.registry[:4]])
        select.item._values = ["自我介紹頻道"]
        await select.callback(interaction)
        picker = self.select_of(interaction.followup.send.await_args.kwargs["view"])
        pick = self.interaction()
        picker._values = ["202"]
        with self.assertLogs("commands.channel_panel", "ERROR"):
            await picker.callback(pick)
        self.assertEqual(self.config.data["intro_channel_id"], 202, "設定已經寫進去了")
        self.assertIn("出錯", pick.edit_original_response.await_args.kwargs["content"])
        interaction.message.edit.assert_awaited_once()

    async def test_page_size_is_capped_by_the_select_limit(self):
        with mock.patch.object(channel_panel, "ADMIN_CONSOLE_SETTINGS", SimpleNamespace(bindings_page_size=99)):
            self.assertEqual(channel_panel.page_size(), 25)
        from pydantic import ValidationError
        from sys_settings.admin_console_settings import AdminConsoleSettings
        with self.assertRaises(ValidationError):
            AdminConsoleSettings(bindings_page_size=40)

    async def test_telegram_route_is_set_with_the_bot_built_channel_list(self):
        interaction = self.interaction()
        await channel_registry._handle_telegram_route(interaction)
        modal = interaction.response.send_modal.await_args.args[0]
        self.assertIs(modal.guild, self.guild, "私訊裡用 bot 唯一的伺服器")
        modal.telegram_source._value = "@Seele_WW_leak"
        submit = self.interaction()
        await modal.on_submit(submit)
        sent = submit.response.send_message.await_args.kwargs
        self.assertTrue(sent["ephemeral"])
        picker = self.select_of(sent["view"])
        self.assertEqual([o.value for o in picker.options], ["201", "202"], "只列文字頻道")
        for value in ("202", "202", "201"):
            pick = self.interaction()
            picker._values = [value]
            await picker.callback(pick)
        self.assertEqual(self.config.data["telegram_channel_routes"], {"seele_ww_leak": [202, 201]}, "同一個頻道不重複")
        self.assertIn("目前目標頻道數：2", pick.response.edit_message.await_args.kwargs["content"])

    async def test_telegram_route_needs_a_single_guild(self):
        self.bot.guilds.append(SimpleNamespace(id=2))
        interaction = self.interaction()
        await channel_registry._handle_telegram_route(interaction)
        interaction.response.send_modal.assert_not_awaited()
        self.assertIn("伺服器", interaction.response.send_message.await_args.kwargs["content"])

    async def test_ephemeral_panel_is_left_for_manual_refresh(self):
        interaction = self.interaction(dm=False, ephemeral=True)
        select = channel_panel.PanelPickSelect(0, options=[channel_panel._option(s) for s in self.registry[:4]])
        select.item._values = ["AI 插話頻道"]
        await select.callback(interaction)
        picker = self.select_of(interaction.followup.send.await_args.kwargs["view"])
        pick = self.interaction(dm=False)
        picker._values = ["202"]
        await picker.callback(pick)
        self.assertEqual(self.config.data["ambient_chat_channel_id"], 202)
        interaction.message.edit.assert_not_awaited()
        self.assertIn("✅", pick.edit_original_response.await_args.kwargs["content"])

    async def test_custom_item_opens_its_own_flow(self):
        interaction = self.interaction()
        select = channel_panel.PanelPickSelect(1, options=[channel_panel._option(s) for s in self.registry[4:]])
        select.item._values = ["Telegram 路由設定"]
        await select.callback(interaction)
        self.custom_handler.assert_awaited_once_with(interaction)
        interaction.message.edit.assert_awaited_once()
        self.assertEqual(self.config.writes, 0)

    async def test_unbind_removes_the_key(self):
        interaction = self.interaction()
        await channel_panel.PanelButton("unbind", 0, label="解除綁定").callback(interaction)
        sent = interaction.response.send_message.await_args.kwargs
        self.assertTrue(sent["ephemeral"])
        chooser = self.select_of(sent["view"])
        self.assertEqual([o.value for o in chooser.options], ["交易頻道", "AI 插話頻道"], "只列本頁已綁的")
        pick = self.interaction()
        chooser._values = ["AI 插話頻道"]
        await chooser.callback(pick)
        self.assertNotIn("ambient_chat_channel_id", self.config.data)
        self.assertEqual(self.config.data["trade_forum_channel_id"], 101, "其他 key 不動")
        self.assertIn("解除", pick.response.edit_message.await_args.kwargs["content"], "先回應再寫檔")
        reply = pick.edit_original_response.await_args.kwargs["content"]
        self.assertIn("已解除「AI 插話頻道」", reply)
        self.assertIn("<#201>", reply)
        interaction.message.edit.assert_awaited_once()

    async def test_unbind_with_nothing_bound_on_this_page(self):
        self.config.data.clear()
        interaction = self.interaction()
        await channel_panel.PanelButton("unbind", 0, label="解除綁定").callback(interaction)
        self.assertIn("沒有已綁定", interaction.response.send_message.await_args.kwargs["content"])

    async def test_non_owner_is_refused_everywhere(self):
        with mock.patch.dict(os.environ, {"OWNER_ID": "1"}):
            interaction = self.interaction()
            await channel_panel.PanelButton("next", 0, label="下一頁 ▶").callback(interaction)
            select = channel_panel.PanelPickSelect(0, options=[channel_panel._option(s) for s in self.registry[:4]])
            select.item._values = ["AI 插話頻道"]
            await select.callback(interaction)
            await channel_panel.send_panel(interaction)
        interaction.response.edit_message.assert_not_awaited()
        interaction.followup.send.assert_not_awaited()
        replies = [c.kwargs.get("content", "") for c in interaction.response.send_message.await_args_list]
        self.assertEqual(len(replies), 3)
        self.assertTrue(all("擁有者" in r for r in replies), replies)

    async def test_send_panel_in_dm_uses_the_only_guild(self):
        interaction = self.interaction()
        await channel_panel.send_panel(interaction)
        kwargs = interaction.response.send_message.await_args.kwargs
        self.assertFalse(kwargs["ephemeral"], "私訊裡是一般訊息，之後才能重畫")
        self.assertIn("**交易頻道**　<#101>", kwargs["embed"].description)

        in_guild = self.interaction(dm=False)
        await channel_panel.send_panel(in_guild)
        self.assertTrue(in_guild.response.send_message.await_args.kwargs["ephemeral"], "伺服器裡只有本人看得到")

    async def test_dm_with_several_guilds_asks_to_use_the_server(self):
        self.bot.guilds.append(SimpleNamespace(id=2))
        interaction = self.interaction()
        await channel_panel.send_panel(interaction)
        self.assertIn("伺服器", interaction.response.send_message.await_args.kwargs["content"])


class RegistryWriteTests(PanelTestBase):
    async def test_apply_refuses_custom_items(self):
        with self.assertRaises(ValueError):
            await channel_registry.apply(self.registry[3], bot=self.bot, guild=self.guild, channel=self.channels[2])

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
