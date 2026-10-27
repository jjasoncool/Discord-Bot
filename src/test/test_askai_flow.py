"""/askai 的處理流程（`LLMCommands._handle_askai_request`）：收集上下文 → 生成 → 記錄 → 送出。

守的底線（使用者看得到、或接到下游的約定）：
  - 給模型的東西：問題裡的 <@id> 換成「名字#尾碼」；聊天紀錄逐行、bot 自己的回覆另一段；人物卡分三路——
    發問者的進 asker_profile、被 @ 的進 target_profiles、其餘進 persona_context；名字對照接在 persona_context 尾端；
    被 @ 但沒有卡的人給一句「沒有紀錄」提示
  - 有圖時：聊天紀錄縮到 5 則、圖以 base64 交給模型、回覆附圖片網址；圖不合格就什麼都不送、不叫模型
  - 網路搜尋：keyword 模式先查好塞 web_context；tool 模式把工具交給工具輪，不先查；off 兩邊都不做
  - 取消：模型呼叫前已取消就不叫模型、不送回覆；生成途中取消就中斷、不送；不是使用者按的取消（底層連帶取消）
    回「這次沒有順利回答」而且不往外丟
  - 記錄：回應歷史帶 trace_id、模型、think、三種 meta、錯誤類型；prompt 紀錄與 debug 紀錄各寫一筆
  - 送出：回覆經 send_followup_in_parts（@ 發問者、問題、回答），完成後把「思考中」改成「已回覆」；
    准 @ 的只有發問者和他在問題裡點名的人，回答裡那些人的「名字#尾碼」換回真的 @，其他人不通知

hermetic：Discord 互動、檢索、網搜、情報、模型服務全換成假的；不碰網路與資料庫。

執行：
    cd src && python -m unittest test.test_askai_flow -v
"""

import asyncio
import contextlib
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from commands import llm_commands as lc  # noqa: E402
from services.llm_service import GenerateReplyResult  # noqa: E402


class _Msg:
    def __init__(self):
        self.edits = []

    async def edit(self, **kwargs):
        self.edits.append(kwargs)


class _Followup:
    def __init__(self):
        self.sent = []
        self.last_msg = None

    async def send(self, content=None, **kwargs):
        self.sent.append((content, kwargs))
        self.last_msg = _Msg()
        return self.last_msg


class _FakeView:
    def __init__(self, user_id, cancel_event):
        self.children = []
        self.stopped = False

    def stop(self):
        self.stopped = True


class _FakeLLM:
    def __init__(self):
        self.calls = []
        self.result = GenerateReplyResult(reply="回答在這", prompt_record_log="PROMPT LOG",
                                          messages_sent=[{"role": "user", "content": "x"}])
        self.block: asyncio.Event | None = None
        self.raise_cancel = False

    def resolve_request_model(self):
        return "主模型"

    def resolve_request_think(self):
        return True

    async def generate_reply(self, **kwargs):
        self.calls.append(kwargs)
        if self.raise_cancel:
            raise asyncio.CancelledError()
        if self.block is not None:
            await self.block.wait()
        return self.result


def _interaction():
    asker = SimpleNamespace(id=1111, display_name="甲", name="jia", mention="<@1111>")
    members = {1111: asker, 2222: SimpleNamespace(id=2222, display_name="乙", name="yi")}
    me = SimpleNamespace(id=5555, display_name="柔喵", name="bot")   # 錨點取 id 末四碼，太短的 id 不會有錨點
    guild = SimpleNamespace(id=9, name="觀星台", me=me, get_member=lambda uid: members.get(uid))
    return SimpleNamespace(user=asker, guild=guild, channel=SimpleNamespace(id=77, name="閒聊"),
                           client=SimpleNamespace(user=me), followup=_Followup())


DISCORD_CONTEXT = [
    {"content": "[2026-10-13 10:00] 乙#2222: 哈囉", "author_id": "2222"},
    {"content": "[2026-10-13 10:01] 甲#1111: 嗨", "author_id": "1111"},
]
BOT_HISTORY = [{"content": "[2026-10-13 09:50] 柔喵#5555: 我之前說過"}]
RAG_CONTEXT = [
    {"content": "人物卡", "metadata": "persona_card_header"},
    {"content": "甲#1111：愛講冷笑話", "person_id": "1111"},
    {"content": "乙#2222：很會吐槽", "person_id": "2222"},
    {"content": "丙#3333：常常潛水", "person_id": "3333"},
]
NAME_MAP = ["【名字對照】", "- 乙#2222 也叫：小乙"]


class _Harness:
    """把 /askai 流程周邊全換成假的，留下紀錄給測試看。"""

    def __init__(self, *, web_mode="off", intel_mode="off", web_triggered=False, chat_mode="off"):
        self.llm = _FakeLLM()
        self.cog = lc.LLMCommands.__new__(lc.LLMCommands)
        self.cog.bot = None
        self.cog.llm_service = self.llm
        self.cog._askai_worker_task = None
        self.discord_kwargs = None
        self.rag_call = None
        self.web_calls = []
        self.intel_calls = []
        self.history = []
        self.sent = []
        self.file_logs = {}
        self.debug_kwargs = None
        self.image_payload = ["B64"]
        self.switch = SimpleNamespace(askai_web_search_mode=web_mode, askai_intel_search_mode=intel_mode,
                                      askai_rerank_mode="off", askai_chat_search_mode=chat_mode)
        self.chat_tool_kwargs = None
        self.intent = SimpleNamespace(triggered=web_triggered, reason="r", trigger_keyword="天氣" if web_triggered else None,
                                      cleaned_query="台北 天氣" if web_triggered else None,
                                      categories=["general"], time_range="day", language="zh-TW")
        self.web_outcome = SimpleNamespace(
            results=[SimpleNamespace(title="天氣預報", url="https://w/1", engine="bing", published_date="2026-10-13")],
            answers=[], meta={"engines": ["bing"]})

    async def _discord(self, interaction, question, **kwargs):
        self.discord_kwargs = {"question": question, **kwargs}
        return list(DISCORD_CONTEXT), list(BOT_HISTORY), {"fetched_count": 2, "retrieval_debug": {"bm25": []}}

    def _rag(self, *args, **kwargs):
        self.rag_call = (args, kwargs)
        return list(RAG_CONTEXT), {"sent_count": 3}

    async def _search_web(self, query, **kwargs):
        self.web_calls.append((query, kwargs))
        return self.web_outcome

    async def _run_with_intel(self, generate, *, question, enabled, meta, settings, also=()):
        self.intel_calls.append({"question": question, "enabled": enabled, "also": list(also)})
        meta["connected"] = False
        return await generate(None)

    def _chat_tools(self, **kwargs):
        self.chat_tool_kwargs = kwargs
        return SimpleNamespace(calls=[{"mode": "phrase", "query": "好了啦", "result_count": 3}])

    def _file_logger(self, *, name, **kwargs):
        return self.file_logs.setdefault(name, mock.Mock())

    async def _send(self, interaction, text, **kwargs):
        self.sent.append(text)

    async def _prepare_image(self, interaction, image):
        return self.image_payload

    def patches(self):
        return [
            mock.patch.object(lc, "load_system_prompt", lambda: "SYSTEM"),
            mock.patch.object(lc, "note_foreground_activity", lambda: None),
            mock.patch.object(lc, "retrieve_discord_context", self._discord),
            mock.patch.object(lc, "retrieve_rag_context_sync", self._rag),
            mock.patch.object(lc, "member_names_from_guild", lambda guild: {"1111": ["甲"], "2222": ["乙", "小乙"]}),
            mock.patch.object(lc, "name_map_lines", lambda guild_id, ids, names: list(NAME_MAP)),
            mock.patch.object(lc, "expand_tweets", self._none_pair),
            mock.patch.object(lc, "external_emoji_context", self._none_pair),
            mock.patch.object(lc, "run_with_intel", self._run_with_intel),
            mock.patch.object(lc.switches, "current", lambda: self.switch),
            mock.patch.object(lc, "should_search", lambda q: self.intent),
            mock.patch.object(lc, "search_web", self._search_web),
            mock.patch.object(lc, "format_web_context_lines", lambda results, answers: [f"[網] {r.title} {r.url}" for r in results]),
            mock.patch.object(lc, "WebSearchTools", lambda settings: SimpleNamespace(calls=[{"kind": "general", "query": "q"}])),
            mock.patch.object(lc, "ChatSearchTools", self._chat_tools),
            mock.patch.object(lc, "get_or_create_file_logger", self._file_logger),
            mock.patch.object(lc, "build_askai_prompt_log", self._debug_log),
            mock.patch.object(lc, "append_askai_response_log", lambda **kwargs: self.history.append(kwargs)),
            mock.patch.object(lc, "send_followup_in_parts", self._send),
            mock.patch.object(lc, "_AskaiCancelButton", _FakeView),
            mock.patch.object(lc.LLMCommands, "_prepare_image_payload", self._prepare_image),
        ]

    async def _none_pair(self, text):
        return [], []

    def _debug_log(self, **kwargs):
        self.debug_kwargs = kwargs
        return "DEBUG"

    async def run(self, question="今汐怎麼配隊", image=None, cancel_event=None):
        # 排隊工作者一定會給 cancel_event（取消按鈕靠它），所以預設也給一個
        self.interaction = _interaction()
        await self.cog._handle_askai_request(self.interaction, question, image, cancel_event or asyncio.Event())
        return self

    @property
    def prompt(self):
        return self.llm.calls[0]


class AskaiFlowTests(unittest.IsolatedAsyncioTestCase):
    def _harness(self, **kwargs):
        h = _Harness(**kwargs)
        stack = contextlib.ExitStack()
        for patch in h.patches():
            stack.enter_context(patch)
        self.addCleanup(stack.close)
        return h

    async def test_answer_length_cap_is_sent_with_the_request(self):
        """一題寫不停會拿著顯示卡寫到逾時：/askai 每次請求都帶回答長度上限（設定值）。"""
        h = await self._harness().run(question="深塔多久重置", cancel_event=asyncio.Event())
        self.assertGreater(lc.ASKAI_SETTINGS.answer_max_tokens, 0)
        self.assertEqual(lc.ASKAI_SETTINGS.answer_max_tokens, h.prompt["max_tokens"])

    async def test_prompt_is_assembled_from_the_three_contexts(self):
        h = await self._harness().run(question="<@2222> 是誰", cancel_event=asyncio.Event())
        p = h.prompt
        self.assertEqual(p["prompt"], "乙#2222 是誰", "問題裡的 <@id> 要換成名字#尾碼")
        self.assertEqual(p["system"], "SYSTEM")
        self.assertEqual(p["chat_context"], [item["content"] for item in DISCORD_CONTEXT])
        self.assertEqual(p["bot_history"], [BOT_HISTORY[0]["content"]])
        self.assertEqual(p["target_profiles"], ["乙#2222：很會吐槽"], "被 @ 的人的卡放 target_profiles")
        self.assertEqual(p["persona_context"], ["丙#3333：常常潛水", *NAME_MAP], "其餘人物卡＋名字對照")
        self.assertIn("persona_summary: 甲#1111：愛講冷笑話", p["asker_profile"], "發問者自己的卡進 asker_profile")
        for line in ("display_name: 甲#", "user_id: 1111", "guild_name: 觀星台", "channel_name: 閒聊", "current_time:"):
            self.assertIn(line, p["asker_profile"])
        self.assertTrue(p["asker_display_name"].startswith("甲#"))
        self.assertTrue(p["bot_display_name"].startswith("柔喵#"))
        self.assertEqual((p["model"], p["think"], p["images"], p["web_context"]), ("主模型", True, None, None))
        self.assertEqual(h.discord_kwargs["question"], "乙#2222 是誰", "檢索也用換過名字的問題")
        args, kwargs = h.rag_call
        self.assertEqual(args[3], [2222, 1111], "聊天裡的發言者（去重、照出現順序）交給人物卡檢索")
        self.assertEqual(kwargs["mentioned_user_ids"], ["2222"])

    async def test_mentioned_person_without_a_card_gets_a_hint(self):
        h = await self._harness().run(question="<@4444> 是誰")
        self.assertEqual(len(h.prompt["target_profiles"]), 1)
        self.assertIn("4444", h.prompt["target_profiles"][0])
        self.assertIn("尚無此人的 persona 紀錄", h.prompt["target_profiles"][0])

    async def test_reply_is_sent_and_recorded(self):
        h = await self._harness().run(question="今汐怎麼配隊")
        self.assertEqual(len(h.sent), 1)
        for piece in ("<@1111>", "今汐怎麼配隊", "回答在這"):
            self.assertIn(piece, h.sent[0])
        self.assertNotIn("🖼️", h.sent[0])
        record = h.history[0]
        self.assertEqual((record["question"], record["reply"], record["model"], record["think"]), ("今汐怎麼配隊", "回答在這", "主模型", True))
        self.assertTrue(record["trace_id"].startswith("ask-1111-"))
        self.assertEqual(record["error_kind"], None)
        self.assertEqual(record["intel_meta"]["mode"], "off")
        self.assertEqual(record["web_meta"]["mode"], "off")
        self.assertEqual(h.file_logs["askai_prompt_trace"].info.call_count, 1)
        self.assertIn("PROMPT LOG", h.file_logs["askai_prompt_trace"].info.call_args.args[0])
        self.assertEqual(h.file_logs["askai_prompt_debug"].info.call_count, 1)
        self.assertEqual(h.debug_kwargs["question"], "今汐怎麼配隊")
        self.assertEqual(h.interaction.followup.sent[0][0], "🔄 AI 思考中，請耐心等候...")
        self.assertEqual([edit.get("content") for edit in h.interaction.followup.last_msg.edits], ["✅ AI 已回覆。"],
                         "回覆完把「思考中」改成「已回覆」")

    async def test_image_shrinks_the_context_and_reaches_the_model(self):
        image = SimpleNamespace(filename="a.png", size=100, url="https://cdn/x.png")
        h = await self._harness().run(image=image)
        self.assertEqual(h.discord_kwargs["max_context_to_send"], 5)
        self.assertEqual(h.discord_kwargs["max_context_messages"], 20)
        self.assertEqual(h.prompt["images"], ["B64"])
        self.assertEqual(h.debug_kwargs["image_meta"], {"attached": True, "count": 1, "filename": "a.png", "size_bytes": 100})
        self.assertIn("🖼️ **圖片：** https://cdn/x.png", h.sent[0])

    async def test_bad_image_stops_before_the_model(self):
        h = self._harness()
        h.image_payload = None
        await h.run(image=SimpleNamespace(filename="a.txt", size=1, url="u"))
        self.assertEqual(h.llm.calls, [])
        self.assertEqual(h.sent, [])
        self.assertEqual(h.history, [])

    async def test_keyword_web_search_runs_first_and_feeds_the_prompt(self):
        h = await self._harness(web_mode="keyword", web_triggered=True).run(question="台北明天天氣")
        self.assertEqual(len(h.web_calls), 1)
        self.assertEqual(h.web_calls[0][0], "台北 天氣", "送 SearXNG 的是改寫過的關鍵字")
        self.assertEqual(h.prompt["web_context"], ["[網] 天氣預報 https://w/1"])
        web_meta = h.history[0]["web_meta"]
        self.assertEqual((web_meta["mode"], web_meta["triggered"], web_meta["engines"]), ("keyword", True, ["bing"]))
        self.assertEqual(web_meta["results_preview"][0]["url"], "https://w/1")
        self.assertEqual(h.intel_calls[0]["also"], [], "keyword 模式不把網搜當工具")

    async def test_chat_search_tool_joins_the_tool_round_when_its_switch_is_on(self):
        """聊天紀錄搜尋是第三個工具：和網搜一起交給工具輪；成員名字、頻道、bot 自己的 id 由指令層交進去；經過進回應紀錄。"""
        h = await self._harness(web_mode="tool", intel_mode="on", chat_mode="on").run()
        self.assertEqual(len(h.intel_calls[0]["also"]), 2, "網搜與聊天搜尋都交給工具輪")
        self.assertEqual(h.chat_tool_kwargs["self_id"], "5555")
        self.assertEqual(h.chat_tool_kwargs["member_names"], {"1111": ["甲"], "2222": ["乙", "小乙"]})
        self.assertEqual(h.history[0]["chat_search_meta"]["calls"], [{"mode": "phrase", "query": "好了啦", "result_count": 3}])

    async def test_chat_search_tool_stays_out_when_its_switch_is_off(self):
        h = await self._harness(web_mode="tool", intel_mode="on").run()
        self.assertEqual(len(h.intel_calls[0]["also"]), 1)
        self.assertIsNone(h.chat_tool_kwargs)
        self.assertIsNone(h.history[0]["chat_search_meta"])

    async def test_tool_mode_hands_web_tools_to_the_tool_round(self):
        h = await self._harness(web_mode="tool", intel_mode="on", web_triggered=True).run()
        self.assertEqual(h.web_calls, [], "tool 模式不先查")
        self.assertEqual(h.prompt["web_context"], None)
        self.assertEqual(h.intel_calls[0]["enabled"], True)
        self.assertEqual(len(h.intel_calls[0]["also"]), 1, "網搜工具交給工具輪")
        self.assertEqual(h.history[0]["web_meta"]["calls"], [{"kind": "general", "query": "q"}])
        self.assertEqual(h.history[0]["intel_meta"]["connected"], False)

    async def test_cancel_before_generation_skips_the_model(self):
        cancel = asyncio.Event()
        cancel.set()
        h = await self._harness().run(cancel_event=cancel)
        self.assertEqual(h.llm.calls, [])
        self.assertEqual(h.sent, [])
        self.assertEqual(h.history, [])

    async def test_cancel_during_generation_sends_nothing(self):
        h = self._harness()
        h.llm.block = asyncio.Event()
        cancel = asyncio.Event()
        task = asyncio.ensure_future(h.run(cancel_event=cancel))
        for _ in range(200):                      # 檢索那幾步走執行緒池，要給一點真實時間
            await asyncio.sleep(0.01)
            if h.llm.calls:
                break
        self.assertEqual(len(h.llm.calls), 1, "模型已經在生成")
        cancel.set()
        with self.assertNoLogs("commands.llm_commands", level="ERROR"):   # 使用者自己按的取消不是錯誤
            await task
        self.assertEqual(h.sent, [])
        self.assertEqual(h.history, [])
        edits = [edit.get("content") or "" for edit in h.interaction.followup.last_msg.edits]
        self.assertFalse(any("✅" in text or "沒有順利回答" in text for text in edits),
                         "取消按鈕自己會把訊息改成「已取消」，流程不該再改成已回覆或失敗")

    async def test_unexpected_cancellation_is_reported_not_raised(self):
        h = self._harness()
        h.llm.raise_cancel = True
        with self.assertLogs("commands.llm_commands", level="ERROR"):
            await h.run()
        self.assertEqual(h.sent, [])
        self.assertTrue(any("沒有順利回答" in (edit.get("content") or "") for edit in h.interaction.followup.last_msg.edits))

    async def test_failed_generation_is_still_sent_and_recorded_with_its_kind(self):
        h = self._harness()
        h.llm.result = GenerateReplyResult(reply="抱歉，這次沒接到", prompt_record_log="LOG", messages_sent=[{"role": "user", "content": "x"}],
                                           error_kind="timeout")
        await h.run()
        self.assertIn("抱歉，這次沒接到", h.sent[0])
        self.assertEqual(h.history[0]["error_kind"], "timeout")
        self.assertEqual(h.history[0]["messages_sent"], [{"role": "user", "content": "x"}])


if __name__ == "__main__":
    unittest.main()


class AskaiMentionTests(unittest.IsolatedAsyncioTestCase):
    """送出時只 @ 發問者與他在問題裡點名的人；回答裡那些人的錨點換回真的 @。"""

    async def test_named_people_are_pinged_and_their_anchor_becomes_a_mention(self):
        sent = []

        async def send(content, **kwargs):
            sent.append((content, kwargs["allowed_mentions"]))

        asker = SimpleNamespace(id=1111, mention="<@1111>")
        interaction = SimpleNamespace(user=asker, followup=SimpleNamespace(send=send))
        inputs = SimpleNamespace(question="問 <@2222> 晚餐吃什麼", mention_anchors={"2222": "乙#2222"})
        await lc._askai_send(interaction, inputs, "乙#2222 說吃滷肉飯；甲#1111 沒說。<@3333> 也沒說", None, None, None)

        content, mentions = sent[0]
        self.assertIn("<@2222> 說吃滷肉飯", content, "點名的人換回真的 @")
        self.assertIn("甲#1111 沒說", content, "沒點名的人照原樣")
        self.assertEqual({1111, 2222}, {u.id for u in mentions.users}, "只 @ 發問者與他點名的人")
        self.assertFalse(mentions.everyone or mentions.roles)

    async def test_without_named_people_only_the_asker_is_pinged(self):
        sent = []

        async def send(content, **kwargs):
            sent.append(kwargs["allowed_mentions"])

        asker = SimpleNamespace(id=1111, mention="<@1111>")
        interaction = SimpleNamespace(user=asker, followup=SimpleNamespace(send=send))
        await lc._askai_send(interaction, SimpleNamespace(question="嗨", mention_anchors={}), "<@3333> 嗨", None, None, None)
        self.assertEqual([1111], [u.id for u in sent[0].users])

