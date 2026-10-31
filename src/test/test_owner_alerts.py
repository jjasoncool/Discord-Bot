"""要群主介入的狀況：`utils/owner_alerts.py` 的警報匯流排、`commands/owner_alert_commands.py` 的私訊＋「重新偵測」與
「機器人狀態」、`utils/discord_members.require_access(allow_dm=)`、`utils/dm_notifier.send_dm(view=)`、`LLMService.probe`。

守的底線：
- 下層任何執行緒 `emit` 一把警報，群主收到一則私訊、底下一顆「重新偵測」；同一把一小時內只送一次，嚴重度升高照送，
  解除後再壞會再送
- listener 還沒接上時發的警報不會丟，接上就補送（一直沒接上的行程只留最近幾則）；接的人出錯不影響發警報的那條請求
- 按鈕只有群主能按（私訊裡也是）；按了跑那種狀況登記的重測，結果補在同一則訊息底下：成功就解除警報、按鈕變「已恢復」停用，
  失敗按鈕留著（那則還記著，之後後端自己好了要回寫）；重測函式出錯也要把按鈕還回去；同一次重測順便解除的其他警報，
  它們的私訊也標成已恢復；從「機器人狀態」面板按的，結果寫在面板上、整個面板重畫（重新整理與各項目的按鈕都還在）
- 通知一則一則依序送：同一把先「壞了」後「好了」，「好了」回寫得到「壞了」那則
- 自癒成功那種一行通知沒有按鈕，順便把放棄那則標成已恢復
- 「機器人狀態」列每一種登記過的狀況：紅＝有警報、綠＝正常，有重測的掛按鈕；重啟後舊按鈕的 custom_id 解析得回種類與 key
- 群主在私訊裡傳任何一句話就拿到管理選單；別人與伺服器裡的訊息不理
- Lemonade 的重測：清自癒紀錄、向量與聊天模型各真的算一次，各自照結果解除自己的警報；按的那一把照它那顆的結果回報；
  向量模型好了才回填向量、聊天模型好了才叫醒 Telegram 補判
- 自癒放棄中的模型行程換了（群主重啟 Lemonade）：自動重新偵測；好了一行通知、舊警報標已恢復；還是壞就重發一則警報
- `LLMService.probe` 真的算一次：拿著閘門、不重試；碰到後端壞掉的 5xx（叫過重開）再探一次；失敗回報原因（帶後端講的那句話）
  不往外丟；等不到閘門也回報；用完就丟的連線池會關掉
- `OWNER_ID` 沒設：不送、不炸

執行：
    cd src && python -m unittest test.test_owner_alerts -v
"""
import asyncio
import contextlib
import os
import sys
import threading
import time
import unittest
from types import SimpleNamespace
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import discord

from commands import owner_alert_commands as oac
from services import llm_service
from services.llm_service import LLMService, ProbeResult
from utils import discord_members, dm_notifier, owner_alerts
from utils.owner_alerts import RetestResult

OWNER = 42


class BusTests(unittest.TestCase):
    def setUp(self):
        owner_alerts.reset()
        self.addCleanup(owner_alerts.reset)
        self.now = 0.0
        patcher = mock.patch.object(owner_alerts, "_clock", lambda: self.now)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.got = []
        owner_alerts.set_listener(self.got.append)

    def test_emit_once_per_hour_until_resolved(self):
        self.assertTrue(owner_alerts.emit("lemonade", "emb", "壞了"))
        self.assertFalse(owner_alerts.emit("lemonade", "emb", "還是壞"), "一小時內同一把不重送")
        self.assertEqual([a.text for a in self.got], ["壞了"])
        self.assertEqual([a.text for a in owner_alerts.active()], ["還是壞"], "狀態面板看得到最新的文字")
        self.now = owner_alerts.RESEND_SECONDS + 1
        self.assertTrue(owner_alerts.emit("lemonade", "emb", "一小時後還壞"))
        owner_alerts.resolve("lemonade", "emb")
        self.assertTrue(owner_alerts.emit("lemonade", "emb", "解除後又壞"), "解除後再壞馬上再送")
        self.assertEqual(len(self.got), 3)
        self.assertEqual(self.got[-1].since, self.now, "解除後是新的一把，時間重算")

    def test_escalation_is_sent_despite_the_hourly_dedupe(self):
        """先送了「還會再試」的警告，之後「放棄了、要你處理」不能被一小時去重吃掉；降級或同級照舊不重送。"""
        self.assertTrue(owner_alerts.emit("lemonade", "emb", "重開了還是壞", severity="warning"))
        self.assertFalse(owner_alerts.emit("lemonade", "emb", "第二次還是壞", severity="warning"))
        self.assertTrue(owner_alerts.emit("lemonade", "emb", "放棄", severity="error"))
        self.assertFalse(owner_alerts.emit("lemonade", "emb", "放棄（更新）", severity="error"))
        self.assertFalse(owner_alerts.emit("lemonade", "emb", "又一次警告", severity="warning"))
        self.assertFalse(owner_alerts.emit("lemonade", "emb", "又放棄", severity="error"),
                         "中間被去重的警告不算：最後送出去的已經是放棄，同級不重送")
        self.assertEqual([a.text for a in self.got], ["重開了還是壞", "放棄"])

    def test_backlog_without_a_listener_is_capped(self):
        """沒接 listener 的行程（search-mcp 這類）通知送不出去：待送的只留最近幾則，不會一直長。"""
        owner_alerts.set_listener(None)
        for i in range(owner_alerts._PENDING_MAX + 20):
            owner_alerts.inform("lemonade", f"m{i}", f"第 {i} 則")
        late = []
        owner_alerts.set_listener(late.append)
        self.assertEqual(len(late), owner_alerts._PENDING_MAX)
        self.assertEqual(late[-1].text, f"第 {owner_alerts._PENDING_MAX + 19} 則", "留的是最近的")

    def test_backlog_is_delivered_when_listener_attaches(self):
        owner_alerts.set_listener(None)
        owner_alerts.emit("pgvector", "raw", "連不上")
        owner_alerts.inform("pgvector", "raw", "好了")
        late = []
        owner_alerts.set_listener(late.append)
        self.assertEqual([(a.severity, a.text) for a in late], [("error", "連不上"), ("info", "好了")])
        self.assertEqual(owner_alerts.active(), [], "一行通知順便解除")

    def test_inform_resolves_and_has_no_button_semantics(self):
        owner_alerts.emit("lemonade", "emb", "壞了")
        owner_alerts.inform("lemonade", "emb", "救回來了")
        self.assertEqual([a.severity for a in self.got], ["error", "info"])
        self.assertEqual(owner_alerts.active(), [])

    def test_retest_resolves_only_on_success(self):
        calls = []

        async def retest(key):
            calls.append(key)
            return RetestResult(key == "good", "詳情")

        owner_alerts.register("x", title="X", retest=retest)
        owner_alerts.emit("x", "good", "a")
        owner_alerts.emit("x", "bad", "b")
        self.assertTrue(asyncio.run(owner_alerts.retest("x", "good")).ok)
        self.assertFalse(asyncio.run(owner_alerts.retest("x", "bad")).ok)
        self.assertEqual(calls, ["good", "bad"])
        self.assertEqual([a.key for a in owner_alerts.active()], ["bad"])
        self.assertFalse(asyncio.run(owner_alerts.retest("nope", "k")).ok, "沒登記的沒有重測")
        self.assertEqual(owner_alerts.title("x"), "X")
        self.assertEqual(owner_alerts.title("nope"), "nope")

    def test_status_line_accepts_sync_async_and_failures(self):
        async def slow():
            return "async 狀態"

        def boom():
            raise RuntimeError("查不到")

        owner_alerts.register("a", title="A", status=lambda: "同步狀態")
        owner_alerts.register("b", title="B", status=slow)
        owner_alerts.register("c", title="C", status=boom)
        owner_alerts.register("d", title="D")
        self.assertEqual(asyncio.run(owner_alerts.status_line("a")), "同步狀態")
        self.assertEqual(asyncio.run(owner_alerts.status_line("b")), "async 狀態")
        with self.assertLogs("utils.owner_alerts", "WARNING"):
            self.assertIn("RuntimeError", asyncio.run(owner_alerts.status_line("c")))
        self.assertEqual(asyncio.run(owner_alerts.status_line("d")), "")
        self.assertEqual([k.kind for k in owner_alerts.kinds()], ["a", "b", "c", "d"], "照登記順序")

    def test_key_is_made_safe_for_custom_ids(self):
        self.assertEqual(owner_alerts.clean_key("Qwen3-Embedding-0.6B-GGUF"), "Qwen3-Embedding-0.6B-GGUF")
        self.assertEqual(owner_alerts.clean_key("a b:c/d"), "a_b_c_d")
        self.assertEqual(len(owner_alerts.clean_key("x" * 200)), 60)
        self.assertEqual(owner_alerts.clean_key(""), "_")
        owner_alerts.emit("k", "a b", "t")
        self.assertEqual(owner_alerts.active()[0].key, "a_b")
        self.assertIsNotNone(owner_alerts.resolve("k", "a b"), "解除時用原本的 key 也找得到")

    def test_listener_errors_are_swallowed(self):
        owner_alerts.set_listener(lambda alert: (_ for _ in ()).throw(RuntimeError("dm broke")))
        with self.assertLogs("utils.owner_alerts", "WARNING"):
            self.assertTrue(owner_alerts.emit("k", "a", "t"))

    def test_emit_from_another_thread(self):
        thread = threading.Thread(target=owner_alerts.emit, args=("k", "a", "從別的執行緒"))
        thread.start()
        thread.join(2)
        self.assertEqual([a.text for a in self.got], ["從別的執行緒"])


def make_interaction(*, user_id=OWNER, dm=True, content="🛑 放棄了", panel=False):
    return SimpleNamespace(
        guild=None if dm else SimpleNamespace(id=1), data={}, channel=SimpleNamespace(id=5),
        client=SimpleNamespace(get_cog=lambda name: None, guilds=[]),
        user=SimpleNamespace(id=user_id, display_name="群主"),
        message=SimpleNamespace(content="" if panel else content, embeds=["status-embed"] if panel else [],
                                flags=SimpleNamespace(ephemeral=False), edit=mock.AsyncMock()),
        response=SimpleNamespace(edit_message=mock.AsyncMock(), send_message=mock.AsyncMock(),
                                 defer=mock.AsyncMock(), is_done=lambda: False),
        followup=SimpleNamespace(send=mock.AsyncMock()),
        edit_original_response=mock.AsyncMock(),
    )


def button_of(view):
    [child] = [c for c in view.children if isinstance(getattr(c, "item", c), discord.ui.Button)]
    return getattr(child, "item", child)


class CogTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        owner_alerts.reset()
        self.addCleanup(owner_alerts.reset)
        self.sent = []
        self.owner_user = SimpleNamespace(id=OWNER, name="群主")

        async def fake_send_dm(user, *, content=None, embed=None, file=None, view=None):
            await asyncio.sleep(0)      # 真的送要等 Discord 回來，讓別的通知有機會插隊
            message = SimpleNamespace(content=content, view=view, edit=mock.AsyncMock())
            self.sent.append(message)
            return message

        self.manager = SimpleNamespace(manager_menu=lambda: ("menu-embed", "menu-view"))
        self.bot = SimpleNamespace(
            add_dynamic_items=mock.Mock(), remove_dynamic_items=mock.Mock(),
            get_cog=lambda name: self.manager if name == "ManagementCommands" else None,
            telegram_relay_worker=None,
        )
        self.cog = oac.OwnerAlertCommands(self.bot)
        # 重測成功會回填正式資料庫的向量：每個測試都換成替身，程式改壞了也碰不到正式資料
        self.backfill = mock.Mock(return_value=0)
        for p in (mock.patch.object(oac, "send_dm", fake_send_dm),
                  mock.patch.object(oac, "resolve_user", mock.AsyncMock(return_value=self.owner_user)),
                  mock.patch("llm.storage.ai_interactions_store.backfill_embeddings", self.backfill),
                  mock.patch.dict(os.environ, {"OWNER_ID": str(OWNER)})):
            p.start()
            self.addCleanup(p.stop)

    async def asyncSetUp(self):
        self.bot.loop = asyncio.get_running_loop()
        await self.cog.cog_load()
        self.addAsyncCleanup(self.cog.cog_unload)
        self.bot.add_dynamic_items.assert_called_once_with(oac.RetestButton, oac.StatusRefreshButton)

    async def test_alert_becomes_a_dm_with_a_retest_button(self):
        await self.cog.deliver(owner_alerts.Alert("lemonade", "emb", "🛑 放棄", "error", 0.0, 0.0))
        [message] = self.sent
        self.assertEqual(message.content, "🛑 放棄")
        button = button_of(message.view)
        self.assertEqual(button.custom_id, "owner:retest:lemonade:emb")
        self.assertFalse(button.disabled)
        m = oac.RetestButton.__discord_ui_compiled_template__.fullmatch(button.custom_id)
        self.assertEqual((m["kind"], m["key"]), ("lemonade", "emb"), "重啟後從 custom_id 解析得回")

    async def test_emit_from_a_thread_reaches_the_owner(self):
        done = asyncio.Event()
        original = self.cog.deliver

        async def deliver(alert):
            await original(alert)
            done.set()
        self.cog.deliver = deliver
        threading.Thread(target=owner_alerts.emit, args=("lemonade", "emb", "從執行緒")).start()
        await asyncio.wait_for(done.wait(), 5)
        self.assertEqual([m.content for m in self.sent], ["從執行緒"])

    async def test_info_marks_the_old_alert_message_as_recovered(self):
        await self.cog.deliver(owner_alerts.Alert("lemonade", "emb", "🛑 放棄", "error", 0.0, 0.0))
        old = self.sent[0]
        await self.cog.deliver(owner_alerts.Alert("lemonade", "emb", "🔧 救回來了", "info", 0.0, 0.0))
        self.assertEqual(self.sent[1].content, "🔧 救回來了")
        self.assertIsNone(self.sent[1].view, "一行通知沒有按鈕")
        kwargs = old.edit.await_args.kwargs
        self.assertIn("已恢復", kwargs["content"])
        self.assertTrue(button_of(kwargs["view"]).disabled)

    async def test_pressing_retest_runs_it_and_writes_back(self):
        retest = mock.AsyncMock(return_value=RetestResult(True, "向量模型 0.4 秒"))
        owner_alerts.register("lemonade", title="模型後端", retest=retest)
        owner_alerts.emit("lemonade", "emb", "🛑 放棄")
        interaction = make_interaction()
        await self.cog.handle_retest(interaction, "lemonade", "emb")
        retest.assert_awaited_once_with("emb")
        busy = interaction.response.edit_message.await_args.kwargs
        self.assertTrue(button_of(busy["view"]).disabled, "跑的時候按鈕先停用，不能連按")
        final = interaction.edit_original_response.await_args.kwargs
        self.assertIn("🛑 放棄", final["content"], "原本的文字留著")
        self.assertIn("重新偵測：正常", final["content"])
        self.assertIn("向量模型 0.4 秒", final["content"])
        button = button_of(final["view"])
        self.assertTrue(button.disabled)
        self.assertEqual(button.label, "已恢復")
        self.assertEqual(owner_alerts.active(), [], "成功就解除")

    async def test_untested_retest_is_not_written_as_broken(self):
        """顯示卡被佔著、這次根本沒測到：不能寫「❌ 還是壞」，按鈕留著讓群主晚點再按。"""
        retest = mock.AsyncMock(return_value=RetestResult(False, "向量模型沒測到（顯示卡被別的工作佔著）", untested=True))
        owner_alerts.register("lemonade", title="模型後端", retest=retest)
        owner_alerts.emit("lemonade", "emb", "🛑 放棄")
        interaction = make_interaction()
        await self.cog.handle_retest(interaction, "lemonade", "emb")
        final = interaction.edit_original_response.await_args.kwargs
        self.assertIn("⏳", final["content"])
        self.assertIn("這次沒測到", final["content"])
        self.assertNotIn("還是壞", final["content"])
        self.assertFalse(button_of(final["view"]).disabled)

    async def test_a_newer_dm_for_the_same_alert_closes_the_older_one(self):
        """同一把先送了警告、後來升級成放棄又送一則：舊那則收掉（按鈕停用、指向新那則），只留一顆能按的按鈕。"""
        owner_alerts.emit("lemonade", "emb", "⚠️ 重開了還是壞", severity="warning")
        await asyncio.sleep(0.01)
        owner_alerts.emit("lemonade", "emb", "🛑 放棄", severity="error")
        await asyncio.sleep(0.01)
        self.assertEqual(len(self.sent), 2)
        old = self.sent[0].edit.await_args.kwargs
        self.assertIn("見下一則", old["content"])
        self.assertTrue(button_of(old["view"]).disabled)
        owner_alerts.inform("lemonade", "emb", "🔧 已重開並確認能算")
        await asyncio.sleep(0.01)
        self.assertIn("已恢復", self.sent[1].edit.await_args.kwargs["content"], "恢復時回寫的是最新那則")

    async def test_automatic_retest_closes_dms_of_alerts_it_resolves_on_the_side(self):
        """自動重測順便測好了另一顆（它還掛著之前的警告）：那則私訊也要補「已恢復」，不能面板綠燈、私訊還叫人處理。"""
        owner_alerts.emit("lemonade", "chat", "⚠️ 重開了還是壞", severity="warning")
        await asyncio.sleep(0.01)
        probes = {True: ProbeResult(True, "emb", 0.4), False: ProbeResult(True, "chat", 1.0)}
        self.cog._llm = SimpleNamespace(probe=mock.AsyncMock(side_effect=lambda *, embedding: probes[embedding]),
                                        replaced_backends=mock.Mock(return_value=["emb"]))
        await self.cog.check_backend_restarts()
        await asyncio.sleep(0.01)
        self.assertEqual(owner_alerts.active(), [])
        self.assertIn("已恢復", self.sent[0].edit.await_args.kwargs["content"])

    async def test_failed_retest_keeps_the_button(self):
        owner_alerts.register("lemonade", title="模型後端", retest=mock.AsyncMock(return_value=RetestResult(False, "還是 5xx")))
        owner_alerts.emit("lemonade", "emb", "🛑 放棄")
        interaction = make_interaction()
        await self.cog.handle_retest(interaction, "lemonade", "emb")
        final = interaction.edit_original_response.await_args.kwargs
        self.assertIn("還是壞", final["content"])
        self.assertIn("還是 5xx", final["content"])
        self.assertFalse(button_of(final["view"]).disabled)
        self.assertEqual([a.key for a in owner_alerts.active()], ["emb"])

    async def test_retest_resolving_other_alerts_marks_their_messages_too(self):
        async def retest(key):
            owner_alerts.resolve("lemonade", "chat")
            return RetestResult(True)
        owner_alerts.register("lemonade", title="模型後端", retest=retest)
        owner_alerts.emit("lemonade", "emb", "emb 壞")
        owner_alerts.emit("lemonade", "chat", "chat 壞")
        await self.cog.deliver(owner_alerts.active()[1])
        chat_message = self.sent[0]
        await self.cog.handle_retest(make_interaction(), "lemonade", "emb")
        self.assertIn("已恢復", chat_message.edit.await_args.kwargs["content"])

    async def test_retest_from_the_status_panel_redraws_the_panel(self):
        owner_alerts.register("lemonade", title="模型後端", retest=mock.AsyncMock(return_value=RetestResult(True, "都正常")),
                              status=lambda: "這一小時沒有重開過")
        owner_alerts.emit("lemonade", "emb", "🛑 放棄")
        await self.cog.deliver(owner_alerts.active()[0])
        dm = self.sent[0]
        panel = make_interaction(panel=True)
        await self.cog.handle_retest(panel, "lemonade", "emb")
        panel.response.defer.assert_awaited_once()
        panel.response.edit_message.assert_not_awaited()
        kwargs = panel.edit_original_response.await_args.kwargs
        self.assertIn("重新偵測：正常——都正常", kwargs["content"])
        self.assertIn("🟢 **模型後端**", kwargs["embed"].description, "面板重畫成現況")
        ids = [getattr(getattr(c, "item", c), "custom_id", None) for c in kwargs["view"].children]
        self.assertIn(oac.STATUS_REFRESH_ID, ids, "重新整理還在")
        self.assertIn("owner:retest:lemonade:*", ids, "沒警報了，重測按鈕的 key 變回 *")
        self.assertIn("已恢復", dm.edit.await_args.kwargs["content"], "警報那則私訊也標成已恢復")

    async def test_failed_retest_keeps_the_dm_for_a_later_heal(self):
        owner_alerts.register("lemonade", title="模型後端", retest=mock.AsyncMock(return_value=RetestResult(False, "還是 5xx")))
        owner_alerts.emit("lemonade", "emb", "🛑 放棄")
        await self.cog.deliver(owner_alerts.active()[0])
        dm = self.sent[0]
        press = make_interaction()
        press.message = dm
        await self.cog.handle_retest(press, "lemonade", "emb")
        await self.cog.deliver(owner_alerts.Alert("lemonade", "emb", "🔧 自己好了", "info", 0.0, 0.0))
        content = dm.edit.await_args.kwargs["content"]
        self.assertIn("還是 5xx", content, "回寫在重測失敗那一行之後")
        self.assertIn("已恢復", content)

    async def test_retest_exception_restores_the_button(self):
        owner_alerts.register("lemonade", title="模型後端", retest=mock.AsyncMock(side_effect=RuntimeError("rules file missing")))
        owner_alerts.emit("lemonade", "emb", "🛑 放棄")
        interaction = make_interaction()
        with self.assertLogs("commands.owner_alert_commands", "ERROR"):
            await self.cog.handle_retest(interaction, "lemonade", "emb")
        final = interaction.edit_original_response.await_args.kwargs
        self.assertIn("重測出錯：RuntimeError", final["content"])
        self.assertFalse(button_of(final["view"]).disabled, "不能停在「偵測中」")
        self.assertEqual([a.key for a in owner_alerts.active()], ["emb"])

    async def test_notifications_are_delivered_in_order(self):
        error = owner_alerts.Alert("lemonade", "emb", "🛑 壞了", "error", 0.0, 0.0)
        info = owner_alerts.Alert("lemonade", "emb", "🔧 好了", "info", 0.0, 0.0)
        await asyncio.gather(self.cog.deliver(error), self.cog.deliver(info))
        self.assertEqual([m.content for m in self.sent], ["🛑 壞了", "🔧 好了"])
        self.assertIn("已恢復", self.sent[0].edit.await_args.kwargs["content"], "「好了」回寫得到「壞了」那則")

    async def test_only_the_owner_can_press(self):
        retest = mock.AsyncMock(return_value=RetestResult(True))
        owner_alerts.register("lemonade", title="模型後端", retest=retest)
        stranger = make_interaction(user_id=7)
        await self.cog.handle_retest(stranger, "lemonade", "emb")
        retest.assert_not_awaited()
        stranger.response.edit_message.assert_not_awaited()
        self.assertIn("擁有者", stranger.response.send_message.await_args.kwargs["content"])
        with mock.patch.dict(os.environ, {"OWNER_ID": "0"}):
            nobody = make_interaction()
            await self.cog.handle_retest(nobody, "lemonade", "emb")
        retest.assert_not_awaited()

    async def test_status_lists_every_kind(self):
        owner_alerts.register("lemonade", title="模型後端", retest=mock.AsyncMock(), status=lambda: "這一小時沒有重開過")
        owner_alerts.register("owner_id", title="群主通知", status=lambda: "OWNER_ID 已設定")
        owner_alerts.emit("lemonade", "emb", "🛑 放棄")
        embed, view = await self.cog.status_message()
        self.assertIn("🔴 **模型後端**", embed.description)
        self.assertIn("-# 🛑 放棄", embed.description)
        self.assertIn("🟢 **群主通知**　OWNER_ID 已設定", embed.description)
        ids = [getattr(getattr(c, "item", c), "custom_id", None) for c in view.children]
        self.assertEqual(ids, ["owner:retest:lemonade:emb", oac.STATUS_REFRESH_ID])

        interaction = make_interaction()
        await self.cog.show_status(interaction)
        self.assertFalse(interaction.response.send_message.await_args.kwargs["ephemeral"], "私訊裡是一般訊息")
        in_guild = make_interaction(dm=False)
        await self.cog.show_status(in_guild)
        self.assertTrue(in_guild.response.send_message.await_args.kwargs["ephemeral"])

    async def test_owner_dm_gets_the_manager_menu(self):
        channel = SimpleNamespace(send=mock.AsyncMock())

        def message(user_id, guild=None, bot=False):
            return SimpleNamespace(guild=guild, author=SimpleNamespace(id=user_id, bot=bot), channel=channel)

        await self.cog.on_dm(message(OWNER))
        channel.send.assert_awaited_once_with(embed="menu-embed", view="menu-view")
        await self.cog.on_dm(message(7))
        await self.cog.on_dm(message(OWNER, guild=SimpleNamespace(id=1)))
        await self.cog.on_dm(message(OWNER, bot=True))
        self.assertEqual(channel.send.await_count, 1, "別人、伺服器裡、bot 自己的都不理")

    async def test_without_owner_id_nothing_is_sent(self):
        with mock.patch.dict(os.environ, {"OWNER_ID": "0"}):
            self.assertIsNone(await self.cog.deliver(owner_alerts.Alert("k", "a", "t", "error", 0.0, 0.0)))
        self.assertEqual(self.sent, [])

    async def test_lemonade_retest_resets_probes_and_wakes_things_up(self):
        probes = {True: ProbeResult(True, "emb", 0.4), False: ProbeResult(True, "chat", 1.3)}
        self.cog._llm = SimpleNamespace(probe=mock.AsyncMock(side_effect=lambda *, embedding: probes[embedding]))
        worker = SimpleNamespace(running=True, wake_recheck=mock.Mock())
        self.bot.telegram_relay_worker = worker
        owner_alerts.emit("lemonade", "emb", "a")
        owner_alerts.emit("lemonade", "chat", "b")
        with mock.patch.object(oac.lemonade_admin, "reset_cache") as reset, \
             mock.patch("llm.storage.ai_interactions_store.backfill_embeddings") as backfill, \
             mock.patch.object(oac, "spawn") as spawn:
            result = await self.cog.retest_lemonade("emb")
        reset.assert_called_once()
        self.assertTrue(result.ok)
        self.assertIn("向量模型 0.4 秒", result.text)
        self.assertIn("聊天模型 1.3 秒", result.text)
        self.assertEqual(owner_alerts.active(), [], "兩顆模型的警報一起解除")
        # spawn 也用來送通知：只看回填那一筆；沒真的跑的 coroutine 收掉
        names = [c.kwargs.get("name") for c in spawn.call_args_list]
        self.assertEqual(names.count("ai_interactions 向量回填"), 1, names)
        for c in spawn.call_args_list:
            c.args[0].close()
        worker.wake_recheck.assert_called_once()

    async def test_lemonade_retest_judges_each_model_on_its_own(self):
        """向量好了、聊天還壞：向量那把解除並回填，聊天那把留著、不叫醒補判；按哪一把就回報那顆的結果。"""
        probes = {True: ProbeResult(True, "emb", 0.4), False: ProbeResult(False, "chat", 60.0, "LlmTimeoutError: 60s")}
        self.cog._llm = SimpleNamespace(probe=mock.AsyncMock(side_effect=lambda *, embedding: probes[embedding]))
        self.bot.telegram_relay_worker = SimpleNamespace(running=True, wake_recheck=mock.Mock())
        owner_alerts.emit("lemonade", "emb", "a")
        owner_alerts.emit("lemonade", "chat", "b")
        with mock.patch.object(oac.lemonade_admin, "reset_cache"), mock.patch.object(oac, "spawn") as spawn:
            on_chat = await self.cog.retest_lemonade("chat")
            on_emb = await self.cog.retest_lemonade("emb")
            on_other = await self.cog.retest_lemonade("*")
        self.assertFalse(on_chat.ok)
        self.assertTrue(on_emb.ok, "向量那把只看向量模型")
        self.assertFalse(on_other.ok, "不是這兩顆的要兩顆都好")
        self.assertIn("聊天模型失敗（LlmTimeoutError: 60s）", on_chat.text)
        names = [c.kwargs.get("name") for c in spawn.call_args_list]
        self.assertIn("ai_interactions 向量回填", names, "向量模型好了就回填")
        for c in spawn.call_args_list:
            c.args[0].close()
        self.bot.telegram_relay_worker.wake_recheck.assert_not_called()
        self.assertEqual([a.key for a in owner_alerts.active()], ["chat"])

    async def test_backend_restart_is_noticed_and_retested(self):
        """放棄中的模型行程換了（群主重啟了 Lemonade）：自動重新偵測；好了一行通知、舊警報那則標已恢復。"""
        owner_alerts.emit("lemonade", "emb", "🛑 放棄")
        await asyncio.sleep(0.01)
        probes = {True: ProbeResult(True, "emb", 0.4), False: ProbeResult(True, "chat", 1.0)}
        self.cog._llm = SimpleNamespace(probe=mock.AsyncMock(side_effect=lambda *, embedding: probes[embedding]),
                                        replaced_backends=mock.Mock(return_value=["emb"]))
        with mock.patch.object(oac.lemonade_admin, "reset_cache"), \
             mock.patch("llm.storage.ai_interactions_store.backfill_embeddings"):
            await self.cog.check_backend_restarts()
            await asyncio.sleep(0.01)
        self.assertEqual(owner_alerts.active(), [])
        self.assertIn("偵測到 emb 的行程換了", self.sent[-1].content)
        self.assertIn("正常", self.sent[-1].content)
        self.sent[0].edit.assert_awaited()
        self.assertIn("已恢復", self.sent[0].edit.await_args.kwargs["content"])

    async def test_backend_restart_that_did_not_help_is_a_new_alert(self):
        """重啟了還是壞：當新的一輪重發警報（一小時去重不擋），群主才知道重啟沒解決。"""
        owner_alerts.emit("lemonade", "emb", "🛑 放棄")
        await asyncio.sleep(0.01)
        probes = {True: ProbeResult(False, "emb", 0.4, "LlmAPIError: HTTP 500：ErrorDeviceLost"),
                  False: ProbeResult(True, "chat", 1.0)}
        self.cog._llm = SimpleNamespace(probe=mock.AsyncMock(side_effect=lambda *, embedding: probes[embedding]),
                                        replaced_backends=mock.Mock(return_value=["emb"]))
        with mock.patch.object(oac.lemonade_admin, "reset_cache"):
            await self.cog.check_backend_restarts()
            await asyncio.sleep(0.01)
        self.backfill.assert_not_called()      # 向量模型還壞：回填只會每筆都失敗
        self.assertEqual(len(self.sent), 2, "重啟後還是壞要再送一則")
        self.assertIn("還是壞", self.sent[-1].content)
        self.assertIn("ErrorDeviceLost", self.sent[-1].content)
        self.assertIsNotNone(self.sent[-1].view, "要人介入的警報帶重新偵測按鈕")
        self.assertEqual([a.key for a in owner_alerts.active()], ["emb"])

    async def test_no_given_up_model_means_nothing_happens(self):
        self.cog._llm = SimpleNamespace(probe=mock.AsyncMock(), replaced_backends=mock.Mock(return_value=[]))
        await self.cog.check_backend_restarts()
        self.cog._llm.probe.assert_not_awaited()
        self.assertEqual(self.sent, [])

    async def test_automatic_retest_keeps_other_models_given_up(self):
        """只有換了行程的那顆自動重測：不清全部紀錄（別顆沒人修，還是放棄著），只放測過能算的。"""
        probes = {True: ProbeResult(True, "emb", 0.4), False: ProbeResult(False, "chat", 1.0, "HTTP 500")}
        self.cog._llm = SimpleNamespace(probe=mock.AsyncMock(side_effect=lambda *, embedding: probes[embedding]),
                                        replaced_backends=mock.Mock(return_value=["emb"]))
        with mock.patch.object(oac.lemonade_admin, "reset_cache") as reset, \
             mock.patch.object(oac.lemonade_admin, "release") as release:
            await self.cog.check_backend_restarts()
            await asyncio.sleep(0.01)
        reset.assert_not_called()
        release.assert_called_once_with(["emb"])

    async def test_busy_gpu_is_retried_next_minute_not_reported_broken(self):
        """顯示卡被別的工作佔著、根本沒測到：不能叫群主去重開機，下一分鐘再測。"""
        busy = ProbeResult(False, "emb", 90.0, "顯示卡被別的工作佔著", busy=True)
        probes = {True: busy, False: ProbeResult(True, "chat", 1.0)}
        replaced = mock.Mock(return_value=["emb"])
        self.cog._llm = SimpleNamespace(probe=mock.AsyncMock(side_effect=lambda *, embedding: probes[embedding]),
                                        replaced_backends=replaced)
        await self.cog.check_backend_restarts()
        await asyncio.sleep(0.01)
        self.assertEqual(self.sent, [])
        replaced.return_value = []                   # 同一個行程只報一次：下一分鐘靠自己記著要再測
        probes[True] = ProbeResult(True, "emb", 0.4)
        await self.cog.check_backend_restarts()
        await asyncio.sleep(0.01)
        self.assertIn("正常", self.sent[-1].content)

    async def test_lemonade_retest_reports_untested_when_the_gpu_was_busy(self):
        probes = {True: ProbeResult(False, "emb", 90.0, "顯示卡被別的工作佔著", busy=True),
                  False: ProbeResult(True, "chat", 1.0)}
        self.cog._llm = SimpleNamespace(probe=mock.AsyncMock(side_effect=lambda *, embedding: probes[embedding]))
        with mock.patch.object(oac.lemonade_admin, "reset_cache"):
            on_emb = await self.cog.retest_lemonade("emb")
            on_chat = await self.cog.retest_lemonade("chat")
        self.assertFalse(on_emb.ok)
        self.assertTrue(on_emb.untested)
        self.assertIn("向量模型沒測到", on_emb.text)
        self.assertTrue(on_chat.ok)

    async def test_retest_of_another_model_tests_that_model(self):
        """按 reranker 的警報重測：要真的測 reranker，不能只看兩顆主模型就解除。"""
        probes = {True: ProbeResult(True, "emb", 0.4), False: ProbeResult(True, "chat", 1.0)}
        backend = mock.AsyncMock(return_value=ProbeResult(False, "rr", 0.1, "LlmAPIError: HTTP 500"))
        self.cog._llm = SimpleNamespace(probe=mock.AsyncMock(side_effect=lambda *, embedding: probes[embedding]),
                                        probe_backend=backend)
        owner_alerts.emit("lemonade", "rr", "壞了")
        with mock.patch.object(oac.lemonade_admin, "reset_cache"):
            result = await self.cog.retest_lemonade("rr")
        backend.assert_awaited_once_with("rr")
        self.assertFalse(result.ok)
        self.assertIn("rr失敗", result.text)
        self.assertEqual([a.key for a in owner_alerts.active()], ["rr"])

    async def test_this_process_heals_only_while_the_cog_is_loaded(self):
        self.assertTrue(oac.lemonade_admin._HEAL_ENABLED)
        await self.cog.cog_unload()
        self.assertFalse(oac.lemonade_admin._HEAL_ENABLED)
        await self.cog.cog_load()

    def test_appended_line_survives_a_long_message(self):
        """同一則重測很多次會一直變長：最新那行一定要看得到，截掉的是前面舊的。"""
        content = "🛑 放棄" + "x" * 3000
        out = oac._append_line(content, "❌ 21:00 重新偵測：還是壞")
        self.assertLessEqual(len(out), oac._MESSAGE_MAX)
        self.assertTrue(out.endswith("❌ 21:00 重新偵測：還是壞"))
        self.assertEqual(oac._append_line("短", "新"), "短\n新")


class AccessTests(unittest.IsolatedAsyncioTestCase):
    async def test_owner_passes_in_dm_only_with_allow_dm(self):
        with mock.patch.dict(os.environ, {"OWNER_ID": str(OWNER)}):
            owner = make_interaction()
            self.assertTrue(await discord_members.require_access(owner, owner_only=True, allow_dm=True))
            owner.response.send_message.assert_not_awaited()
            self.assertFalse(await discord_members.require_access(owner, owner_only=True))
            self.assertIn("伺服器", owner.response.send_message.await_args.kwargs["content"])
            stranger = make_interaction(user_id=7)
            self.assertFalse(await discord_members.require_access(stranger, owner_only=True, allow_dm=True))
            self.assertIn("擁有者", stranger.response.send_message.await_args.kwargs["content"])
            admin = make_interaction()
            self.assertFalse(await discord_members.require_access(admin, admin_only=True, allow_dm=True), "私訊裡看不到身分組")
        with mock.patch.dict(os.environ, {"OWNER_ID": "0"}):
            self.assertFalse(await discord_members.require_access(make_interaction(user_id=0), owner_only=True, allow_dm=True))

    def test_home_guild(self):
        guild = SimpleNamespace(id=1)
        self.assertIs(discord_members.home_guild(SimpleNamespace(guild=guild, client=SimpleNamespace(guilds=[]))), guild)
        self.assertIs(discord_members.home_guild(SimpleNamespace(guild=None, client=SimpleNamespace(guilds=[guild]))), guild)
        self.assertIsNone(discord_members.home_guild(SimpleNamespace(guild=None, client=SimpleNamespace(guilds=[guild, guild]))))
        self.assertIsNone(discord_members.home_guild(SimpleNamespace(guild=None, client=SimpleNamespace(guilds=[]))))


class SendDmTests(unittest.IsolatedAsyncioTestCase):
    async def test_view_is_passed_only_when_given(self):
        user = SimpleNamespace(id=1, name="u", send=mock.AsyncMock(return_value="message"))
        self.assertEqual(await dm_notifier.send_dm(user, content="hi"), "message")
        self.assertNotIn("view", user.send.await_args.kwargs)
        self.assertNotIn("file", user.send.await_args.kwargs)
        view = object()
        await dm_notifier.send_dm(user, content="hi", view=view)
        self.assertIs(user.send.await_args.kwargs["view"], view)
        user.send.side_effect = discord.Forbidden(SimpleNamespace(status=403, reason="Forbidden"), "closed")
        self.assertIsNone(await dm_notifier.send_dm(user, content="hi"))
        self.assertIsNone(await dm_notifier.send_dm(None, content="hi"))


class ProbeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.service = LLMService.__new__(LLMService)
        self.service.settings = SimpleNamespace(gated_embed_timeout=5)
        self.service.base_url = "http://backend.test"
        self.service._client = SimpleNamespace(admin="admin")
        self.runtime = SimpleNamespace(embed_model="emb", model="chat", backend="lemonade")
        self.service._load_runtime_config_cached = lambda: self.runtime
        self.service.resolve_request_model = lambda override=None: "chat"
        self.service._ensure_model_loaded = mock.AsyncMock()
        self.service._build_chat_extra_body = lambda **kw: {"chat_template_kwargs": {"enable_thinking": False}}
        self.gate_calls = []

        @contextlib.asynccontextmanager
        async def gate(owner="llm", lease_seconds=None):
            self.gate_calls.append(owner)
            yield
        patcher = mock.patch.object(llm_service, "gpu_exclusive", gate)
        patcher.start()
        self.addCleanup(patcher.stop)

    async def test_embedding_probe_holds_the_gate_and_does_not_retry(self):
        embed = SimpleNamespace(get_text_embedding=mock.Mock(return_value=[0.1]), close=mock.Mock())
        with mock.patch.object(llm_service, "make_safe_llm_embedding", return_value=embed) as factory:
            result = await self.service.probe(embedding=True)
        self.assertTrue(result.ok, result.detail)
        self.assertEqual(result.model, "emb")
        self.assertTrue(factory.call_args.kwargs["holding_gpu_gate"], "拿著閘門：短逾時、不重試")
        self.assertEqual(self.gate_calls, ["probe"])
        embed.get_text_embedding.assert_called_once_with("ping")

    async def test_embedding_failure_is_reported_not_raised(self):
        embed = SimpleNamespace(get_text_embedding=mock.Mock(side_effect=RuntimeError("ErrorDeviceLost")), close=mock.Mock())
        with mock.patch.object(llm_service, "make_safe_llm_embedding", return_value=embed):
            result = await self.service.probe(embedding=True)
        self.assertFalse(result.ok)
        self.assertIn("ErrorDeviceLost", result.detail)
        self.runtime = None
        self.assertFalse((await self.service.probe(embedding=True)).ok, "沒有 runtime 設定不知道要測哪顆")

    async def test_failure_reason_carries_what_the_backend_said(self):
        """`str(LlmAPIError)` 只有「HTTP 500」：群主要看得到後端講的那句話（ErrorDeviceLost）。"""
        from llm.client.http_client import LlmAPIError
        wrapped = ('{"error":{"code":500,"details":{"response":{"error":{"code":500,'
                   '"message":"decode() failed: vk::CommandBuffer::end: ErrorDeviceLost"}}},"message":"outer"}}')
        embed = SimpleNamespace(get_text_embedding=mock.Mock(side_effect=LlmAPIError("HTTP 500", status=500, detail=wrapped)),
                                close=mock.Mock())
        with mock.patch.object(llm_service, "make_safe_llm_embedding", return_value=embed):
            result = await self.service.probe(embedding=True)
        self.assertFalse(result.ok)
        self.assertIn("HTTP 500", result.detail)
        self.assertIn("vk::CommandBuffer::end: ErrorDeviceLost", result.detail)

    async def test_chat_probe_sends_one_token_without_retries(self):
        created = []

        class FakeClient:
            def __init__(self, **kwargs):
                created.append(kwargs)
                self.admin = kwargs["admin"]
                self.chat_completion = mock.AsyncMock(return_value={"choices": [{"message": {"content": "p"}}]})
                self.close = mock.Mock()
                self.aclose = mock.AsyncMock()

        with mock.patch.object(llm_service, "LlmHttpClient", FakeClient), \
             mock.patch.object(llm_service, "admin_for", return_value=SimpleNamespace(close=mock.Mock())):
            result = await self.service.probe(embedding=False)
        self.assertTrue(result.ok, result.detail)
        self.assertEqual(result.model, "chat")
        self.assertEqual(created[0]["max_retries"], 0)
        self.assertIsNotNone(created[0]["admin"], "後端壞掉的 5xx 照樣重載一次")
        self.service._ensure_model_loaded.assert_awaited_once_with("chat")
        self.assertEqual(created[0]["timeout"], 5.0)

    async def test_probe_tries_again_after_the_backend_was_reloaded(self):
        from llm.client.http_client import LlmAPIError
        broken = LlmAPIError("HTTP 500", status=500, detail='{"error":{"message":"decode() failed: vk::Queue::submit: ErrorDeviceLost"}}')
        embed = SimpleNamespace(get_text_embedding=mock.Mock(side_effect=[broken, [0.1]]), close=mock.Mock())
        with mock.patch.object(llm_service, "make_safe_llm_embedding", return_value=embed):
            result = await self.service.probe(embedding=True)
        self.assertTrue(result.ok, result.detail)
        self.assertEqual(embed.get_text_embedding.call_count, 2, "重載過的 5xx 再探一次")
        self.assertEqual(embed.close.call_count, 2, "每次探完都把連線池關掉")
        plain = SimpleNamespace(get_text_embedding=mock.Mock(side_effect=RuntimeError("boom")), close=mock.Mock())
        with mock.patch.object(llm_service, "make_safe_llm_embedding", return_value=plain):
            self.assertFalse((await self.service.probe(embedding=True)).ok)
        self.assertEqual(plain.get_text_embedding.call_count, 1, "不是後端壞掉的訊號就不再探")

    async def test_wedged_backend_is_probed_again_inside_the_same_gate(self):
        """卡死（拆信封認出來、當連不上丟）也會叫重開：重開救回來就要再探到；兩次在同一段閘門裡，中間不讓別人插隊。"""
        from llm.client.http_client import LlmConnectionError
        embed = SimpleNamespace(get_text_embedding=mock.Mock(side_effect=[LlmConnectionError("upstream 卡死"), [0.1]]),
                                close=mock.Mock())
        with mock.patch.object(llm_service, "make_safe_llm_embedding", return_value=embed):
            result = await self.service.probe(embedding=True)
        self.assertTrue(result.ok, result.detail)
        self.assertEqual(embed.get_text_embedding.call_count, 2)
        self.assertEqual(self.gate_calls, ["probe"], "再探不重新排閘門")

    async def test_chat_probe_closes_its_own_clients(self):
        created = []

        class FakeClient:
            def __init__(self, **kwargs):
                created.append(self)
                self.admin = kwargs["admin"]
                self.chat_completion = mock.AsyncMock(return_value={"choices": [{}]})
                self.close = mock.Mock()
                self.aclose = mock.AsyncMock()

        admin = SimpleNamespace(close=mock.Mock())
        with mock.patch.object(llm_service, "LlmHttpClient", FakeClient), \
             mock.patch.object(llm_service, "admin_for", return_value=admin) as factory:
            self.assertTrue((await self.service.probe(embedding=False)).ok)
        factory.assert_called_once_with("lemonade", "http://backend.test", heal_load_timeout=5.0)   # 自癒每一步照探測的短時限
        [client] = created
        client.close.assert_called_once()
        client.aclose.assert_awaited_once()
        admin.close.assert_called_once()
        self.assertIsNot(client.admin, self.service._client.admin, "探測用自己的 admin，關掉才不會關到正式的")

    async def test_chat_probe_reports_empty_and_timeout(self):
        class FakeClient:
            def __init__(self, **kwargs):
                self.admin = None
                self.chat_completion = mock.AsyncMock(return_value={"choices": []})
                self.close = mock.Mock()
                self.aclose = mock.AsyncMock()

        with mock.patch.object(llm_service, "LlmHttpClient", FakeClient), mock.patch.object(llm_service, "admin_for", return_value=None):
            result = await self.service.probe(embedding=False)
        self.assertFalse(result.ok)
        self.assertIn("choices", result.detail)

        @contextlib.asynccontextmanager
        async def taken(owner="llm", lease_seconds=None):
            await asyncio.sleep(10)                       # 別的工作一直佔著顯示卡
            yield

        with mock.patch.object(llm_service, "gpu_exclusive", taken), mock.patch.object(llm_service, "_PROBE_GATE_GRACE", 0.0):
            result = await self.service.probe(embedding=False, timeout=0.01)
        self.assertFalse(result.ok)
        self.assertTrue(result.busy, "沒測到不等於壞了")
        self.assertIn("沒測到", result.detail)

    async def test_time_limit_only_covers_waiting_for_the_gate(self):
        """拿到閘門之後不再整段限時：時間到在重開做到一半時取消，會先放掉閘門、執行緒裡的重開卻還在跑。"""
        released = []

        @contextlib.asynccontextmanager
        async def gate(owner="llm", lease_seconds=None):
            try:
                yield
            finally:
                released.append(owner)

        slow = SimpleNamespace(get_text_embedding=mock.Mock(side_effect=lambda text: (time.sleep(0.05), [0.1])[1]),
                               close=mock.Mock())
        with mock.patch.object(llm_service, "gpu_exclusive", gate), mock.patch.object(llm_service, "_PROBE_GATE_GRACE", 0.0), \
             mock.patch.object(llm_service, "make_safe_llm_embedding", return_value=slow):
            result = await self.service.probe(embedding=True, timeout=0.01)
        self.assertTrue(result.ok, result.detail)
        self.assertEqual(released, ["probe"])

    async def test_other_models_are_checked_through_the_admin(self):
        self.service._client = SimpleNamespace(admin=SimpleNamespace(check=mock.Mock()))
        self.assertTrue((await self.service.probe_backend("rr")).ok)
        self.service._client.admin.check.assert_called_once_with("rr")
        self.assertEqual(self.gate_calls, ["probe"])
        self.service._client = SimpleNamespace(admin=None)
        result = await self.service.probe_backend("rr")
        self.assertFalse(result.ok)
        self.assertIn("沒辦法單獨測", result.detail)


if __name__ == "__main__":
    unittest.main()
