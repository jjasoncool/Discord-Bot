"""插話上網查（`llm.ambient.ambient_search`）：琇紫判斷要不要插話的同一次生成裡，可以先查一次。

守的底線：
  - 開關 off → 不給工具；dry_run（記錄模式）→ 工具照宣告（情報只有 search、沒有 fetch，加 web_search），
    規則讀插話自己的規則檔（不是 /askai 要附網址那份）；on → 宣告與規則和記錄模式一字不差（提示詞快取不失效）
  - 同一次插話只執行第一個呼叫，第二個回「只能查一次」
  - 每天額度：用完當天不宣告工具；每次有查的插話扣一次（記錄模式也扣，成本在多出來的那一輪）
  - web_search 的查詢字含群友名字或識別碼就擋下，不碰內層工具；情報查詢只到本機、不檢查
  - 記錄模式：不呼叫內層工具、回固定說明、記下查詢字與判定
  - 準備情報工具逾時 → 只剩網路搜尋；工具失敗回錯誤給模型、不往外丟
  - 名字檢查的名單：全伺服器 Discord 名字加在場的人的自介、印象暱稱；查不到暱稱只用 Discord 名字
  - 聊天紀錄搜尋（chat_search）：`ambient_chat_search_mode` 開著、呼叫端也交了建它的函式才宣告，用的是沒有 channel 參數
    的那份宣告（不隨頻道與觸發的人變）；它的規則是同一份規則檔的最後一段，只在這時給；真的要查才建工具；查詢字不做名字檢查
    （只查本機，本來就要填群友的名字）；和另外兩個工具共用「一次插話只查一次」與每天的額度；記錄模式一樣只記不查

執行：
    cd src && python -m unittest test.test_ambient_search -v
"""

import asyncio
import json
import os
import sys
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from llm.ambient import ambient_search  # noqa: E402
from sys_settings.llm_settings import AmbientSearchSettings  # noqa: E402

NOON = datetime(2026, 10, 17, 12, 0)


class FakeIntel:
    def __init__(self):
        self.executed = []
        self.tools = [
            {"type": "function", "function": {"name": "search", "description": "查情報", "parameters": {}}},
            {"type": "function", "function": {"name": "fetch", "description": "讀全文", "parameters": {}}},
        ]

    async def execute(self, name, arguments):
        self.executed.append((name, arguments))
        return json.dumps({"results": [{"id": "a:1"}]})


class FakeWeb:
    def __init__(self):
        self.executed = []
        self.instructions = ""
        self.tools = [{"type": "function", "function": {"name": "web_search", "description": "查網路", "parameters": {}}}]

    async def execute(self, name, arguments):
        self.executed.append((name, arguments))
        return json.dumps({"results": [{"title": "t"}]})


async def NAMES():
    return ["糯糯", "一野"]


class FakeChat:
    def __init__(self):
        self.executed = []

    async def execute(self, name, arguments):
        self.executed.append((name, arguments))
        return json.dumps({"mode": "phrase", "total": 3, "speakers": []})


def _switch(chat):
    return mock.patch.object(ambient_search.switches, "current",
                             lambda: SimpleNamespace(ambient_chat_search_mode=chat, ambient_search_mode="on"))


class PrepareTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        ambient_search._QUOTA.reset()
        self.addCleanup(ambient_search._QUOTA.reset)
        self.intel = FakeIntel()
        for patcher in (
            mock.patch.object(ambient_search, "mode", return_value="dry_run"),
            mock.patch.object(ambient_search, "prepare_intel_session", mock.AsyncMock(return_value=self.intel)),
            mock.patch.object(ambient_search, "WebSearchTools", lambda **kw: FakeWeb()),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    async def prepare(self, **kw):
        return await ambient_search.prepare("這波是標準的何意味", now=lambda: NOON, names=NAMES, **kw)

    async def test_off_means_no_tools(self):
        with mock.patch.object(ambient_search, "mode", return_value="off"):
            self.assertIsNone(await self.prepare())

    async def test_record_mode_declares_intel_search_and_web_search_with_the_ambient_rules(self):
        tools = await self.prepare()
        self.assertEqual("dry_run", tools.mode)
        self.assertEqual(["search", "web_search"], [t["function"]["name"] for t in tools.tools])   # 沒有 fetch
        self.assertIn("插話", tools.instructions)                 # 插話自己的規則檔（正式路徑讀得到）
        self.assertNotIn("附引用的網址", tools.instructions)      # 不是 /askai 那份

    async def test_on_declares_the_same_tools_and_rules_as_record_mode(self):
        record_mode = await self.prepare()
        with mock.patch.object(ambient_search, "mode", return_value="on"):
            on = await self.prepare()
        self.assertEqual("on", on.mode)
        self.assertEqual(record_mode.tools, on.tools)
        self.assertEqual(record_mode.instructions, on.instructions)

    async def test_quota_exhausted_means_no_tools_today(self):
        for _ in range(AmbientSearchSettings().daily_limit):
            ambient_search._QUOTA.take(NOON)
        self.assertIsNone(await self.prepare())

    async def test_intel_taking_too_long_leaves_only_web_search(self):
        async def slow(**kwargs):
            await asyncio.sleep(1)

        with mock.patch.object(ambient_search, "prepare_intel_session", slow):
            tools = await self.prepare(settings=AmbientSearchSettings(intel_prepare_seconds=0.01))
        self.assertEqual(["web_search"], [t["function"]["name"] for t in tools.tools])


    # ── 聊天紀錄搜尋 ──
    async def test_chat_search_is_declared_when_its_switch_is_on_and_a_builder_is_given(self):
        built = []
        with _switch("on"):
            tools = await self.prepare(chat=lambda: built.append(1))
        self.assertEqual(["search", "web_search", "chat_search"], [t["function"]["name"] for t in tools.tools])
        declared = tools.tools[-1]["function"]
        self.assertNotIn("channel", declared["parameters"]["properties"], "插話只查所在的頻道，不讓模型選")
        self.assertIn("插話時的查詢規則", tools.instructions)
        self.assertIn("查這個頻道的聊天紀錄", tools.instructions)     # 兩份規則檔在正式路徑都讀得到
        self.assertLess(tools.instructions.index("插話時的查詢規則"), tools.instructions.index("查這個頻道的聊天紀錄"))
        self.assertEqual([], built, "宣告時不建工具：建它要掃整個伺服器的成員名單")

    async def test_chat_search_is_not_declared_with_its_switch_off_or_without_a_builder(self):
        with _switch("off"):
            off = await self.prepare(chat=FakeChat)
        with _switch("on"):
            no_builder = await self.prepare()
        for tools in (off, no_builder):
            self.assertEqual(["search", "web_search"], [t["function"]["name"] for t in tools.tools])
            self.assertNotIn("chat_search", tools.instructions, "工具沒宣告，規則就不能提到它")

    async def test_without_chat_search_the_rules_stop_before_its_section(self):
        with _switch("on"):
            with_chat = await self.prepare(chat=FakeChat)
            without = await self.prepare()
        heading = ambient_search.CHAT_RULES_HEADING
        self.assertIn(heading, with_chat.instructions, "正式的規則檔裡要有這個標題")
        self.assertEqual(with_chat.instructions.split(heading)[0].rstrip(), without.instructions)
        self.assertTrue(without.instructions.endswith("不要插。"), without.instructions[-40:])

    async def test_the_chat_search_declaration_does_not_depend_on_who_triggered_it(self):
        with _switch("on"):
            first, second = await self.prepare(chat=FakeChat), await self.prepare(chat=lambda: None)
        self.assertEqual(first.tools, second.tools)
        self.assertEqual(first.instructions, second.instructions)


class ExecuteTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        ambient_search._QUOTA.reset()
        self.addCleanup(ambient_search._QUOTA.reset)
        self.intel, self.web = FakeIntel(), FakeWeb()

    def tools(self, mode="dry_run", limit=30, chat=None):
        return ambient_search.AmbientSearchTools(
            mode=mode, intel=self.intel, web=self.web, names=NAMES, now=lambda: NOON,
            settings=AmbientSearchSettings(daily_limit=limit), chat=chat,
        )

    def _chat(self):
        self.chat, self.chat_built = FakeChat(), 0

        def build():
            self.chat_built += 1
            return self.chat

        return build

    async def test_chat_search_goes_to_the_channel_locked_tool_and_may_name_a_member(self):
        tools = self.tools(mode="on", chat=self._chat())
        member = (await NAMES())[0]      # 名字檢查名單上的人
        payload = await self.call(tools, "chat_search", {"query": "好了啦", "mode": "phrase", "author": member})
        self.assertEqual(3, payload["total"])
        self.assertEqual(1, len(self.chat.executed))
        self.assertEqual("chat_search", self.chat.executed[0][0])
        self.assertEqual(([], []), (self.web.executed, self.intel.executed))
        self.assertEqual(("好了啦", "ok"), (tools.records[0]["query"], tools.records[0]["verdict"]))
        self.assertEqual(1, ambient_search._QUOTA.used(NOON), "和另外兩個工具共用每天的額度")

    async def test_a_chat_search_whose_query_names_a_member_is_not_blocked(self):
        tools = self.tools(mode="on", chat=self._chat())
        member = (await NAMES())[0]
        payload = await self.call(tools, "chat_search", {"query": f"{member} 好了啦"})
        self.assertNotIn("error", payload, "只查本機，名字檢查是給會出網的那個用的")

    async def test_chat_search_shares_the_one_call_per_pass(self):
        tools = self.tools(mode="on", chat=self._chat())
        await self.call(tools, "web_search", {"query": "何意味 梗 意思"})
        payload = await self.call(tools, "chat_search", {"query": "好了啦"})
        self.assertIn("只能查一次", payload["error"])
        self.assertEqual(0, self.chat_built)

    async def test_record_mode_does_not_search_the_chat_either(self):
        tools = self.tools(chat=self._chat())
        payload = await self.call(tools, "chat_search", {"query": "好了啦"})
        self.assertEqual(ambient_search.RECORD_MODE_NOTE, payload["note"])
        self.assertEqual(0, self.chat_built)
        self.assertEqual("recorded", tools.records[0]["verdict"])

    async def call(self, tools, name, args):
        return json.loads(await tools.execute(name, json.dumps(args, ensure_ascii=False)))

    async def test_record_mode_records_the_query_without_calling_anything(self):
        tools = self.tools()
        payload = await self.call(tools, "web_search", {"query": "何意味 梗 意思", "kind": "general"})
        self.assertEqual(([], ambient_search.RECORD_MODE_NOTE), (payload["results"], payload["note"]))
        self.assertEqual([], self.web.executed)
        self.assertEqual(("何意味 梗 意思", "recorded"), (tools.records[0]["query"], tools.records[0]["verdict"]))
        self.assertEqual(1, ambient_search._QUOTA.used(NOON), "記錄模式也扣額度")

    async def test_only_the_first_call_of_a_pass_is_executed(self):
        tools = self.tools()
        await self.call(tools, "web_search", {"query": "何意味 梗"})
        second = await self.call(tools, "search", {"query": "3.7 新角色"})
        self.assertIn("只能查一次", second["error"])
        self.assertEqual("second_call", tools.records[1]["verdict"])
        self.assertEqual(1, ambient_search._QUOTA.used(NOON))

    async def test_a_query_naming_a_member_is_blocked_before_leaving(self):
        tools = self.tools(mode="on")
        payload = await self.call(tools, "web_search", {"query": "糯糯 生日"})
        self.assertIn("群友的名字", payload["error"])
        self.assertEqual([], self.web.executed)
        self.assertEqual("blocked:群友名字", tools.records[0]["verdict"])

    async def test_the_whole_query_is_name_checked_even_though_the_log_is_cut(self):
        tools = self.tools(mode="on")
        payload = await self.call(tools, "web_search", {"query": "鳴潮 " * 110 + "糯糯 生日"})   # 名字在第 200 字之後
        self.assertIn("群友的名字", payload["error"])
        self.assertEqual([], self.web.executed)
        self.assertEqual(200, len(tools.records[0]["query"]), "紀錄才截短")

    async def test_intel_queries_are_not_name_checked(self):
        tools = self.tools(mode="on")
        payload = await self.call(tools, "search", {"query": "糯糯 生日"})
        self.assertEqual([{"id": "a:1"}], payload["results"])
        self.assertEqual(1, len(self.intel.executed))

    async def test_on_runs_the_web_tool_for_a_clean_query(self):
        tools = self.tools(mode="on")
        payload = await self.call(tools, "web_search", {"query": "何意味 梗 意思"})
        self.assertEqual([{"title": "t"}], payload["results"])
        self.assertEqual("ok", tools.records[0]["verdict"])

    async def test_quota_is_checked_at_execution_too(self):
        tools = self.tools(limit=1)
        ambient_search._QUOTA.take(NOON)
        payload = await self.call(tools, "web_search", {"query": "何意味"})
        self.assertIn("額度", payload["error"])
        self.assertEqual("quota", tools.records[0]["verdict"])

    async def test_unknown_tool_and_bad_arguments_come_back_as_errors(self):
        tools = self.tools()
        self.assertIn("沒有名為", (await self.call(tools, "fetch", {"id": "a:1"}))["error"])    # fetch 沒宣告
        self.assertIn("error", json.loads(await tools.execute("web_search", "not json")))

    async def test_tool_failure_does_not_escape(self):
        async def boom(name, arguments):
            raise RuntimeError("searxng down")

        self.web.execute = boom
        tools = self.tools(mode="on")
        with self.assertLogs("llm.ambient.ambient_search", level="WARNING"):
            payload = await self.call(tools, "web_search", {"query": "何意味"})
        self.assertIn("查不到", payload["error"])
        self.assertEqual("failed", tools.records[0]["verdict"])


class NamePartsTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def guild(*members):
        return SimpleNamespace(id=1, members=list(members))

    @staticmethod
    def member(uid, display, global_name=None, bot=False):
        return SimpleNamespace(id=uid, bot=bot, display_name=display, nick=None, global_name=global_name)

    async def test_discord_names_plus_profile_nicknames(self):
        guild = self.guild(self.member(10, "糯糯 弗糯糯", "一野shout死你"), self.member(99, "琇紫", bot=True))
        store = SimpleNamespace(aliases_for_users=lambda guild_id, user_ids: {"10": ["肥糯"]})
        with mock.patch("llm.storage.member_profile_store.get_member_profile_store", return_value=store):
            parts = await ambient_search.name_parts_for(guild, [10])
        self.assertTrue({"糯糯", "弗糯糯", "一野shout死你", "肥糯"} <= parts, parts)
        self.assertNotIn("琇紫", parts)

    async def test_profile_failure_falls_back_to_discord_names(self):
        guild = self.guild(self.member(10, "糯糯"))

        def broken():
            raise RuntimeError("db down")

        with mock.patch("llm.storage.member_profile_store.get_member_profile_store", broken):
            parts = await ambient_search.name_parts_for(guild, [10])
        self.assertIn("糯糯", parts)


if __name__ == "__main__":
    unittest.main()
