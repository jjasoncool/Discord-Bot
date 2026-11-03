"""機器人狀態面板（commands/admin_status.py）與 `utils.owner_alerts` 的燈號（`Status`／`status_of`）。

守的底線：
- 燈號：error 警報＝紅、warning 警報至少黃、狀態函式只回字串＝綠、回 `Status` 照它說的；狀態函式出錯是黃不是炸
- 面板是新版版面、是主控台的一個畫面：九項全部展開時元件不超過 40；正常的預設收成一行、按「展開」逐項列；每一項右邊一顆重測、
  custom_id 帶種類、key 與展開狀態；底下有全部重測、重新整理、展開／收合、看詳細、跑今天的 04:00 維護、回主控台
- 每個操作都改面板這一則：看詳細是分頁的子畫面（有上一頁／下一頁與回上一層）、補跑維護先換成確認畫面（確定跑／取消）；
  不另發訊息
- 面板整體顏色跟最壞的那項走；標題下寫幾項要處理、幾項觀察、幾項正常
- 全部重測：每一項各重測一次（模型後端排最後）、結果寫在面板最上面、整個面板重畫；一項出錯不中斷
- 九項各自的判準：爬蟲公告超過 45 分鐘沒推送＝紅、其他來源 3 小時＝黃；網路搜尋有引擎暫避＝黃、開關 off＝綠；
  顯示卡閘門等滿 15 分鐘硬闖中＝紅、別的行程拿著＝黃、bot 自己用＝綠；資料庫原始備份連續失敗 3 次＝紅；
  Telegram worker 沒在跑＝紅；設定缺 OWNER_ID＝紅、活動排程 dry_run＝黃；Discord 權限缺「發送訊息」＝紅、缺「附加檔案」＝黃
- 只有群主能按；私訊裡也能用
- 補跑 04:00 維護要先確認；確認後背景跑 `daily_maintenance.run_once`、面板最上面寫一行、做完一行通知；已經有一輪在跑就只講這件事

執行：
    cd src && python -m unittest test.test_admin_status -v
"""
import os
import sys
import time
import unittest
from types import SimpleNamespace
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import discord

from commands import admin_status
from settings import channel_registry
from settings.channel_registry import ChannelSetting
from utils import owner_alerts
from utils.discord_content import layout_text
from utils.owner_alerts import RetestResult, Status

OWNER = 42
TEXT, FORUM = discord.ChannelType.text, discord.ChannelType.forum


def make_interaction(*, user_id=OWNER, dm=True, guilds=()):
    state = {"done": False}

    async def mark_done(*args, **kwargs):
        state["done"] = True
    # 回應過（defer、send_message 或 edit_message）之後 is_done 變 True，後面的換畫面才會像真的一樣改原訊息
    return SimpleNamespace(
        guild=None if dm else SimpleNamespace(id=1), data={}, channel=SimpleNamespace(id=5),
        client=SimpleNamespace(get_cog=lambda name: None, guilds=list(guilds)),
        user=SimpleNamespace(id=user_id, display_name="群主"),
        message=SimpleNamespace(content="", flags=SimpleNamespace(ephemeral=False), edit=mock.AsyncMock()),
        response=SimpleNamespace(edit_message=mock.AsyncMock(side_effect=mark_done), send_message=mock.AsyncMock(side_effect=mark_done),
                                 defer=mock.AsyncMock(side_effect=mark_done), send_modal=mock.AsyncMock(side_effect=mark_done),
                                 is_done=lambda: state["done"]),
        followup=SimpleNamespace(send=mock.AsyncMock()),
        edit_original_response=mock.AsyncMock(),
    )


def shown_view(interaction):
    """最後一次換畫面的 view：改原訊息（defer 之後）優先，否則就是用回應改的那次。"""
    call = interaction.edit_original_response.await_args or interaction.response.edit_message.await_args
    return call.kwargs["view"]


def ids_of(view):
    return [getattr(getattr(c, "item", c), "custom_id", None) for c in view.walk_children()]


def assert_unique_ids(testcase, view):
    """同一則訊息的 custom_id 不能重複（Discord 會整則退件、錯誤看不出是哪兩顆撞）。"""
    ids = [i for i in ids_of(view) if i]
    testcase.assertEqual(len(ids), len(set(ids)), f"custom_id 重複：{sorted(i for i in set(ids) if ids.count(i) > 1)}")


class StatusLevelTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        owner_alerts.reset()
        self.addCleanup(owner_alerts.reset)
        owner_alerts.set_listener(lambda alert: None)

    async def test_alerts_override_the_status_function(self):
        owner_alerts.register("k", title="K", status=lambda: "一切正常")
        self.assertEqual(await owner_alerts.status_of("k"), Status("ok", "一切正常"))
        owner_alerts.emit("k", "a", "有點怪", severity="warning")
        self.assertEqual((await owner_alerts.status_of("k")).level, "watch", "warning 警報至少黃")
        owner_alerts.emit("k", "a", "壞了", severity="error")
        self.assertEqual((await owner_alerts.status_of("k")).level, "alert")
        self.assertEqual(await owner_alerts.status_line("k"), "一切正常", "說明照狀態函式")

    async def test_status_object_and_failures(self):
        owner_alerts.register("w", title="W", status=lambda: Status("watch", "觀察中"))
        self.assertEqual(await owner_alerts.status_of("w"), Status("watch", "觀察中"))

        async def boom():
            raise RuntimeError("查不到")
        owner_alerts.register("x", title="X", status=boom)
        with self.assertLogs(owner_alerts.logger, "WARNING"):
            status = await owner_alerts.status_of("x")
        self.assertEqual(status.level, "watch")
        self.assertIn("RuntimeError", status.text)
        owner_alerts.register("n", title="N")
        owner_alerts.emit("n", "a", "沒狀態函式只有警報")
        self.assertEqual(await owner_alerts.status_of("n"), Status("alert", "沒狀態函式只有警報"))


class RenderTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        owner_alerts.reset()
        self.addCleanup(owner_alerts.reset)
        owner_alerts.set_listener(lambda alert: None)
        for kind in admin_status.KIND_ORDER:
            owner_alerts.register(kind, title=kind.upper(), status=lambda: "ok", retest=mock.AsyncMock(return_value=RetestResult(True, "好")))
        patcher = mock.patch.dict(os.environ, {"OWNER_ID": str(OWNER)})
        patcher.start()
        self.addCleanup(patcher.stop)

    async def test_collapsed_panel_groups_the_green_ones(self):
        owner_alerts.emit("scraper", "article", "2 小時沒推送")
        owner_alerts.register("web_search", title="WEB", status=lambda: Status("watch", "duckduckgo 暫避"),
                              retest=mock.AsyncMock(return_value=RetestResult(True, "好")))
        view = await admin_status.render_status()
        self.assertTrue(view.is_persistent())
        text = layout_text(view)
        self.assertIn("1 項要你處理、1 項觀察中、7 項正常", text)
        self.assertIn("🔴 **SCRAPER**", text)
        self.assertIn("🟡 **WEB**", text)
        self.assertIn("🟢 正常 7 項：", text)
        self.assertNotIn("🟢 **DISCORD_PERM**", text, "正常的收成一行")
        ids = ids_of(view)
        self.assertIn("owner:panel:0:scraper:article", ids, "有警報的那項重測帶那一把的 key")
        self.assertIn("owner:panel:0:web_search:*", ids)
        self.assertIn("owner:status:expand", ids)
        for action in ("all", "refresh", "details", "maintenance"):
            self.assertIn(f"owner:status:{action}", ids)
        self.assertNotIn("owner:status:collapse", ids)
        self.assertIn("console:home", ids, "面板是主控台的一個畫面，要有回主控台")
        self.assertEqual(ids.count("owner:status:expand"), 1, "「展開」只在收合那一列右邊；底排再放一顆同 id 的，Discord 會整則退件")
        assert_unique_ids(self, view)
        all_red = await admin_status.render_status()
        assert_unique_ids(self, all_red)
        self.assertEqual(view.children[0].accent_colour, discord.Color.red(), "整體顏色跟最壞的走")

    async def test_expanded_panel_lists_everything_within_the_component_limit(self):
        view = await admin_status.render_status(expanded=True, headline="🔁 全部重測：9 項正常")
        text = layout_text(view)
        for kind in admin_status.KIND_ORDER:
            self.assertIn(f"🟢 **{kind.upper()}**", text)
        self.assertIn("全部重測：9 項正常", text, "結果寫在面板最上面")
        ids = ids_of(view)
        self.assertIn("owner:status:collapse", ids)
        for action in ("refresh1", "all1", "details1", "maintenance1"):
            self.assertIn(f"owner:status:{action}", ids, "按鈕記得面板是展開的")
        self.assertIn("owner:panel:1:pgvector:*", ids)
        self.assertEqual(view.children[0].accent_colour, discord.Color.green())
        components = view.to_components()
        self.assertLessEqual(view._total_children, 40)
        self.assertEqual(len(components), 3, "一個容器加兩排按鈕（一排最多 5 顆）")
        assert_unique_ids(self, view)
        self.assertNotIn("owner:status:expand", ids, "展開中沒有「展開」")
        self.assertLessEqual(view.content_length(), 4000)

    def test_custom_ids_round_trip(self):
        button = admin_status.PanelRetestButton("pgvector", "raw flush", True)
        m = admin_status.PanelRetestButton.__discord_ui_compiled_template__.fullmatch(button.item.custom_id)
        self.assertEqual((m["expanded"], m["kind"], m["key"]), ("1", "pgvector", "raw_flush"))
        self.assertIsNotNone(admin_status.StatusButton.__discord_ui_compiled_template__.fullmatch(admin_status.STATUS_REFRESH_ID),
                             "舊面板上的重新整理照樣能按")
        m = admin_status.StatusButton.__discord_ui_compiled_template__.fullmatch("owner:status:details1:2")
        self.assertEqual((m["action"], m["expanded"], m["page"]), ("details", "1", "2"))
        button = admin_status.StatusButton("details", True, 2, label="下一頁 ▶")
        self.assertEqual(button.item.custom_id, "owner:status:details1:2")
        self.assertEqual(admin_status.StatusButton("refresh", False, label="重新整理").item.custom_id, "owner:status:refresh")

    async def test_buttons_refuse_strangers_and_redraw_for_the_owner(self):
        stranger = make_interaction(user_id=7)
        await admin_status.StatusButton("refresh", label="重新整理").callback(stranger)
        stranger.response.edit_message.assert_not_awaited()
        self.assertIn("擁有者", stranger.response.send_message.await_args.kwargs["content"])
        stranger = make_interaction(user_id=7)
        await admin_status.PanelRetestButton("pgvector", "*", False).callback(stranger)
        self.assertIn("擁有者", stranger.response.send_message.await_args.kwargs["content"])
        owner = make_interaction()
        await admin_status.StatusButton("expand", label="展開").callback(owner)
        kwargs = owner.response.edit_message.await_args.kwargs
        self.assertEqual(set(kwargs), {"view", "content", "embed"}, "舊的 embed 版面板按下去也要換得成新版版面")
        self.assertIsNone(kwargs["content"])
        self.assertIsNone(kwargs["embed"])
        self.assertIn("owner:status:collapse", ids_of(kwargs["view"]))

    async def test_more_kinds_than_fit_are_folded_into_one_line(self):
        """登記表是開放的：第十、十一項登記進來，面板不能炸（40 個元件上限），放不下的收成一行請按看詳細。"""
        for extra in ("ytdlp", "loop_crash", "backup"):
            owner_alerts.register(extra, title=extra.upper(), status=lambda: Status("alert", "x"), retest=mock.AsyncMock())
        view = await admin_status.render_status(expanded=True, headline="🔁 全部重測")
        self.assertLessEqual(view._total_children, 40)
        text = layout_text(view)
        for kind in list(admin_status.KIND_ORDER) + ["ytdlp", "loop_crash", "backup"]:
            self.assertIn(kind.upper(), text, f"{kind} 要出現在面板上（列或收成的那行）")
        self.assertIn("放不下，按「看詳細」", text)
        view = await admin_status.render_status(expanded=False)
        self.assertLessEqual(view._total_children, 40)

    async def test_text_stays_within_the_discord_limit(self):
        for kind in admin_status.KIND_ORDER:
            owner_alerts.register(kind, title=kind.upper(), status=lambda: Status("alert", "壞" * 700), retest=mock.AsyncMock())
        view = await admin_status.render_status(expanded=True, headline="h" * 600)
        text = layout_text(view)
        self.assertLessEqual(len(text), 4000)
        self.assertIn("…（看詳細）", text, "截掉的要說完整內容在看詳細")

    async def test_retest_all_runs_every_kind_and_redraws(self):
        order = []

        def retest_for(kind, ok=True):
            async def run(key):
                order.append(kind)
                return RetestResult(ok, "好" if ok else "還是壞")
            return run
        for kind in admin_status.KIND_ORDER:
            owner_alerts.register(kind, title=kind.upper(), status=lambda: "ok", retest=retest_for(kind, ok=kind != "intel"))
        interaction = make_interaction()
        await admin_status.retest_all(interaction)
        interaction.response.defer.assert_awaited_once()
        self.assertEqual(order[-1], "lemonade", "模型後端最後測（它會拿顯示卡）")
        self.assertEqual(sorted(order), sorted(admin_status.KIND_ORDER))
        interaction.response.edit_message.assert_not_awaited()
        text = layout_text(interaction.edit_original_response.await_args.kwargs["view"])
        self.assertIn("全部重測：8 項正常、1 項還是壞、0 項沒測到（INTEL）", text)

    async def test_details_is_a_paged_screen_on_the_same_message(self):
        """看詳細換在面板這一則上：每一項的完整說明、還沒解除的警報；太長就分頁（上一頁／下一頁），回上一層回到面板。"""
        owner_alerts.emit("pgvector", "raw", "原始備份連續 3 輪寫不進去")
        interaction = make_interaction()
        await admin_status.StatusButton("details", True, label="看詳細").callback(interaction)
        interaction.response.send_message.assert_not_awaited()
        interaction.followup.send.assert_not_awaited()
        kwargs = interaction.response.edit_message.await_args.kwargs
        self.assertIsNone(kwargs["content"])
        text = layout_text(kwargs["view"])
        self.assertIn("🔴 **PGVECTOR**", text)
        self.assertIn("還沒解除的警報", text)
        self.assertIn("原始備份連續 3 輪寫不進去", text)
        self.assertIn("第 1／1 頁", text)
        self.assertEqual([i for i in ids_of(kwargs["view"]) if i], ["owner:status:refresh1"], "一頁放得下就只有回上一層，回去時面板還是展開的")

        for kind in admin_status.KIND_ORDER:
            owner_alerts.register(kind, title=kind.upper(), status=lambda: Status("alert", "壞" * 900), retest=mock.AsyncMock())
        view = await admin_status.render_details(page=99)
        text = layout_text(view)
        self.assertLessEqual(view.content_length(), 4000)
        self.assertIn("第 3／3 頁", text, "頁碼超過夾回最後一頁")
        ids = ids_of(view)
        self.assertIn("owner:status:details:1", ids, "上一頁")
        self.assertIn("owner:status:details:2", ids, "最後一頁的下一頁指著自己、灰掉")
        buttons = {getattr(c, "item", c).custom_id: getattr(c, "item", c) for c in view.walk_children() if isinstance(getattr(c, "item", c), discord.ui.Button)}
        self.assertTrue(buttons["owner:status:details:2"].disabled)
        self.assertFalse(buttons["owner:status:details:1"].disabled)
        first = layout_text(await admin_status.render_details(page=0))
        self.assertIn("第 1／3 頁", first)
        self.assertNotEqual(first, text, "每頁內容不同")

    async def test_a_failing_screen_is_rescued_with_a_minimal_panel(self):
        """畫面算到一半出錯：不能漏到 discord.py 變「此互動失敗」，換成只剩「重新整理」「回主控台」的畫面並標錯誤。"""
        with mock.patch.object(admin_status, "render_details", mock.AsyncMock(side_effect=RuntimeError("boom"))):
            interaction = make_interaction()
            with self.assertLogs("commands.admin_status", "ERROR"):
                await admin_status.StatusButton("details", True, label="看詳細").callback(interaction)
        view = interaction.response.edit_message.await_args.kwargs["view"]
        self.assertIn("操作失敗（RuntimeError）", layout_text(view))
        self.assertEqual([i for i in ids_of(view) if i], ["owner:status:refresh1", "console:home"], "救援畫面不再算狀態，不會再失敗")
        interaction.response.send_message.assert_not_awaited()

    async def test_maintenance_confirms_on_the_same_message_then_runs(self):
        """「跑今天的 04:00 維護」先把面板換成確認畫面（確定跑／取消都在這一則上）；確定後背景跑、面板最上面寫一行。"""
        interaction = make_interaction(guilds=[SimpleNamespace(id=1)])
        await admin_status.StatusButton("maintenance", True, label="跑今天的 04:00 維護").callback(interaction)
        interaction.response.send_message.assert_not_awaited()
        view = interaction.response.edit_message.await_args.kwargs["view"]
        self.assertIn("補跑今天的 04:00 維護", layout_text(view))
        self.assertEqual([i for i in ids_of(view) if i], ["owner:status:go1", "owner:status:refresh1"], "確定跑、取消（回展開的面板）")

        run_once = mock.AsyncMock(return_value=True)
        informed = []
        with mock.patch("llm.persona.daily_maintenance.run_once", run_once), \
                mock.patch("llm.persona.daily_maintenance.is_running", return_value=False), \
                mock.patch.object(admin_status.owner_alerts, "inform", lambda *a: informed.append(a)), \
                mock.patch.object(admin_status, "spawn", lambda coro, name=None: __import__("asyncio").ensure_future(coro)):
            confirm = make_interaction(guilds=[SimpleNamespace(id=1)])
            await admin_status.StatusButton("go", True, label="確定跑").callback(confirm)
            await __import__("asyncio").sleep(0)
        panel = confirm.response.edit_message.await_args.kwargs["view"]
        self.assertIn("開始跑維護", layout_text(panel))
        self.assertIn("owner:status:collapse", ids_of(panel), "回到展開的面板")
        confirm.response.send_message.assert_not_awaited()
        run_once.assert_awaited_once()
        self.assertEqual(informed[0][:2], ("maintenance", "manual"))
        self.assertIn("做完了", informed[0][2])

        with mock.patch("llm.persona.daily_maintenance.is_running", return_value=True), \
                mock.patch("llm.persona.daily_maintenance.run_once", run_once):
            again = make_interaction(guilds=[SimpleNamespace(id=1)])
            await admin_status.StatusButton("go", False, label="確定跑").callback(again)
        self.assertIn("已經有一輪維護在跑", layout_text(again.response.edit_message.await_args.kwargs["view"]))
        self.assertEqual(run_once.await_count, 1, "有一輪在跑就不再跑")


class FakeConfig:
    def __init__(self, data):
        self.data = data

    def load_config(self, caller="unknown"):
        return dict(self.data)

    async def get_configured_id(self, key, caller="unknown"):
        value = self.data.get(key)
        return int(value) if value else None


def perms(**overrides):
    base = dict(view_channel=True, send_messages=True, embed_links=True, attach_files=True,
                send_messages_in_threads=True, create_public_threads=True, connect=True, speak=True)
    base.update(overrides)
    return SimpleNamespace(**base)


class KindTests(unittest.IsolatedAsyncioTestCase):
    """九項各自的判準，用假的 bot 與假的現況。"""

    def setUp(self):
        admin_status._LAST_PROBE.clear()
        self.addCleanup(admin_status._LAST_PROBE.clear)
        self.config = FakeConfig({"article_monitor_channel_id": 11, "trade_forum_channel_id": 22,
                                  "event_schedule_enabled": True, "event_schedule_dry_run": True})
        self.registry = [
            ChannelSetting("官方文章更新", TEXT, "article_monitor_channel_id", discord.Color.blue(), "公告"),
            ChannelSetting("交易頻道", FORUM, "trade_forum_channel_id", discord.Color.blue(), "交易"),
            ChannelSetting("AI 插話頻道", TEXT, "ambient_chat_channel_id", discord.Color.blue(), "插話"),
        ]
        self.channel_perms = {11: perms(), 22: perms()}
        channels = {cid: SimpleNamespace(id=cid, type=TEXT if cid == 11 else FORUM,
                                         permissions_for=lambda me, cid=cid: self.channel_perms[cid]) for cid in (11, 22)}
        self.guild = SimpleNamespace(id=1, channels=list(channels.values()), get_channel=channels.get,
                                     me=SimpleNamespace(guild_permissions=SimpleNamespace(manage_events=True, kick_members=True)))
        self.bot = SimpleNamespace(guilds=[self.guild], get_cog=lambda name: None, _notify_server=object(),
                                   telegram_relay_worker=None, failed_extensions=[])
        for p in (mock.patch.object(channel_registry, "_REGISTRY", self.registry),
                  mock.patch.object(channel_registry, "ChannelConfig", self.config),
                  mock.patch.object(admin_status, "ChannelConfig", self.config),
                  mock.patch.dict(os.environ, {"OWNER_ID": str(OWNER)})):
            p.start()
            self.addCleanup(p.stop)

    async def test_discord_permissions(self):
        self.assertEqual((await admin_status.discord_perm_status(self.bot)).level, "ok")
        self.channel_perms[22] = perms(attach_files=False)
        status = await admin_status.discord_perm_status(self.bot)
        self.assertEqual(status.level, "watch")
        self.assertIn("附加檔案", status.text)
        self.channel_perms[11] = perms(send_messages=False)
        status = await admin_status.discord_perm_status(self.bot)
        self.assertEqual(status.level, "alert")
        self.assertIn("官方文章更新（<#11>）缺「發送訊息」", status.text)
        self.channel_perms[11] = perms()
        self.guild.me.guild_permissions.manage_events = False
        self.assertEqual((await admin_status.discord_perm_status(self.bot)).level, "watch", "dry_run 中缺管理活動只是觀察")
        self.config.data["event_schedule_dry_run"] = False
        status = await admin_status.discord_perm_status(self.bot)
        self.assertEqual(status.level, "alert")
        self.assertIn("管理活動", status.text)
        self.guild.get_channel = lambda cid: None
        self.assertIn("找不到頻道", (await admin_status.discord_perm_status(self.bot)).text)

    def test_scraper_quiet_thresholds(self):
        now = time.time()
        with mock.patch.object(admin_status.notify_server, "last_notify_at",
                               return_value={"article": now - 60, "bahamut": now - 4 * 3600}), \
                mock.patch.object(admin_status.notify_server, "rejected_count", return_value=0), \
                mock.patch.object(admin_status, "_STARTED", now - 60):
            status = admin_status.scraper_status(self.bot)
        self.assertEqual(status.level, "watch", "巴哈 4 小時沒推送＝觀察")
        self.assertIn("bahamut", status.text)
        with mock.patch.object(admin_status.notify_server, "last_notify_at", return_value={"article": now - 3600}), \
                mock.patch.object(admin_status.notify_server, "rejected_count", return_value=0), \
                mock.patch.object(admin_status, "_STARTED", now - 60):
            status = admin_status.scraper_status(self.bot)
        self.assertEqual(status.level, "alert", "公告 1 小時沒推送＝紅")
        self.bot._notify_server = None
        self.assertEqual(admin_status.scraper_status(self.bot).level, "alert")

    def test_web_search_levels(self):
        with mock.patch.object(admin_status.switches, "current", return_value=SimpleNamespace(askai_web_search_mode="off")):
            self.assertEqual(admin_status.web_search_status(self.bot).level, "ok")
        with mock.patch.object(admin_status.switches, "current", return_value=SimpleNamespace(askai_web_search_mode="tool")), \
                mock.patch.object(admin_status.searxng, "blocked_engines", return_value={"duckduckgo": 600.0}):
            status = admin_status.web_search_status(self.bot)
        self.assertEqual(status.level, "watch")
        self.assertIn("duckduckgo 暫避到", status.text)

    def test_gpu_lock_levels(self):
        cases = [
            ({"holder": None, "locked_here": False, "other_process": False, "skip_remaining_s": 0.0}, "ok"),
            ({"holder": "llm", "locked_here": True, "other_process": None, "skip_remaining_s": 0.0}, "ok"),
            ({"holder": None, "locked_here": False, "other_process": True, "skip_remaining_s": 0.0}, "watch"),
            ({"holder": "imagegen", "locked_here": True, "other_process": None, "skip_remaining_s": 0.0}, "watch"),
            ({"holder": None, "locked_here": False, "other_process": True, "skip_remaining_s": 500.0}, "alert"),
        ]
        for state, level in cases:
            with mock.patch.object(admin_status.gpu_gate, "cross_process_status", return_value=state):
                self.assertEqual(admin_status.gpu_lock_status(self.bot).level, level, state)

    def test_pgvector_levels(self):
        with mock.patch.object(admin_status.raw_message_store, "flush_health",
                               return_value={"last_ok_at": time.time() - 30, "consecutive_failures": 0, "buffered": 2}), \
                mock.patch.object(admin_status.store_chat, "buffer_status",
                                  return_value={"size": 0, "edits": 0, "paused_s": 0.0, "dropped": 0}):
            self.assertEqual(admin_status.pgvector_status(self.bot).level, "ok")
        with mock.patch.object(admin_status.raw_message_store, "flush_health",
                               return_value={"last_ok_at": None, "consecutive_failures": 3, "buffered": 80}), \
                mock.patch.object(admin_status.store_chat, "buffer_status",
                                  return_value={"size": 17, "edits": 0, "paused_s": 120.0, "dropped": 0}):
            status = admin_status.pgvector_status(self.bot)
        self.assertEqual(status.level, "alert")
        self.assertIn("連續 3 輪寫不進去", status.text)
        self.assertIn("放回 17 則", status.text)

    def test_telegram_levels(self):
        self.assertEqual(admin_status.telegram_status(self.bot).level, "alert", "worker 沒在跑")
        self.bot.telegram_relay_worker = SimpleNamespace(
            running=True, status=lambda: {"running": True, "listening": True, "queued": 3, "processing": 0, "last_polled_pk": 9})
        self.assertEqual(admin_status.telegram_status(self.bot).level, "ok")
        admin_status._LAST_PROBE["telegram_scraper"] = (time.time() - 60, Status("alert", "查 telegram_messages 失敗"))
        status = admin_status.telegram_status(self.bot)
        self.assertEqual(status.level, "alert", "一小時內的探測失敗算")
        self.assertIn("探測：查 telegram_messages 失敗", status.text)
        admin_status._LAST_PROBE["telegram_scraper"] = (time.time() - 7200, Status("alert", "查 telegram_messages 失敗"))
        status = admin_status.telegram_status(self.bot)
        self.assertEqual(status.level, "ok", "兩小時前的探測不再影響燈號，只留註記")
        self.assertIn("探測：", status.text)
        self.bot.telegram_relay_worker.status = lambda: {"running": True, "listening": False, "queued": 0, "processing": 0, "last_polled_pk": 9}
        self.assertEqual(admin_status.telegram_status(self.bot).level, "alert")

    async def test_telegram_retest_restarts_through_the_bot_hook(self):
        latest = SimpleNamespace(timestamp=lambda: time.time() - 600, astimezone=lambda tz: SimpleNamespace(strftime=lambda f: "11-01 09:00"))
        worker = SimpleNamespace(running=True, repository=SimpleNamespace(latest_message_time=mock.AsyncMock(return_value=latest)))

        async def start():
            self.bot.telegram_relay_worker = worker
        self.bot.start_telegram_relay = mock.AsyncMock(side_effect=start)
        result = await admin_status.telegram_retest(self.bot, "*")
        self.bot.start_telegram_relay.assert_awaited_once()
        self.assertTrue(result.ok)
        self.assertIn("11-01 09:00", result.text)

    def test_scraper_rejections_only_count_when_recent(self):
        now = time.time()
        with mock.patch.object(admin_status.notify_server, "last_notify_at", return_value={"article": now - 60}), \
                mock.patch.object(admin_status.notify_server, "rejected_count", return_value=3), \
                mock.patch.object(admin_status.notify_server, "last_rejected_at", return_value=now - 2 * 3600):
            self.assertEqual(admin_status.scraper_status(self.bot).level, "ok", "兩小時前被拒的不算，修好就會綠")
        with mock.patch.object(admin_status.notify_server, "last_notify_at", return_value={"article": now - 60}), \
                mock.patch.object(admin_status.notify_server, "rejected_count", return_value=3), \
                mock.patch.object(admin_status.notify_server, "last_rejected_at", return_value=now - 60):
            status = admin_status.scraper_status(self.bot)
        self.assertEqual(status.level, "watch")
        self.assertIn("密鑰不符被拒", status.text)

    async def test_settings_levels(self):
        with mock.patch.object(admin_status.switches, "current", return_value=SimpleNamespace(
                telegram_filter_mode="on", ambient_search_mode="dry_run", askai_intel_search_mode="on", askai_web_search_mode="tool")):
            status = await admin_status.settings_status(self.bot)
            self.assertEqual(status.level, "watch", "活動排程 dry_run＝觀察")
            self.assertIn("dry_run", status.text)
            self.assertIn("AI 插話頻道沒綁", status.text)
            self.bot.failed_extensions = ["commands.llm_commands"]
            status = await admin_status.settings_status(self.bot)
            self.assertEqual(status.level, "alert")
            self.assertIn("llm_commands", status.text)
            self.bot.failed_extensions = []
            with mock.patch.dict(os.environ, {"OWNER_ID": "0"}):
                self.assertIn("OWNER_ID 沒設", (await admin_status.settings_status(self.bot)).text)
            self.assertNotIn("別款遊戲名單", status.text)
            with mock.patch.object(admin_status, "other_games_problem", return_value="ValidationError"):
                status = await admin_status.settings_status(self.bot)
            self.assertIn("別款遊戲名單讀不到", status.text)
            self.assertIn("ValidationError", status.text)

    async def test_probe_results_feed_the_status_line(self):
        with mock.patch.object(admin_status.switches, "current", return_value=SimpleNamespace(askai_intel_search_mode="on", ambient_search_mode="off")):
            self.assertIn("還沒探測過", admin_status.intel_status(self.bot).text)
            with mock.patch.object(admin_status, "prepare_intel_session", mock.AsyncMock(return_value=None)):
                result = await admin_status.intel_retest(self.bot, "*")
            self.assertFalse(result.ok)
            self.assertEqual(admin_status.intel_status(self.bot).level, "alert", "探測失敗後狀態列也紅")
            with mock.patch.object(admin_status, "prepare_intel_session",
                                   mock.AsyncMock(return_value=SimpleNamespace(tool_names=["search", "fetch"]))):
                result = await admin_status.intel_retest(self.bot, "*")
            self.assertTrue(result.ok)
            self.assertEqual(admin_status.intel_status(self.bot).level, "ok")
            self.assertIn("2 個工具", admin_status.intel_status(self.bot).text)


if __name__ == "__main__":
    unittest.main()
