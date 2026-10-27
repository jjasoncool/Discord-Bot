"""聊天紀錄搜尋做成給模型的工具（`llm/retrievers/chat_search.py` 的 `ChatSearchTools`）：/askai 的 `askai_chat_search_mode=on`。

守的底線：
  - 宣告一個 chat_search 工具，query 必填、mode（phrase／topic）、author、channel 選填；使用規則讀 `askai_chat_search_rules.txt`
    （正式環境的預設路徑讀得到）
  - phrase：ILIKE 子字串（% 與 _ 會跳脫）、一次掃描同時算計數與最近幾則、有逾時上限、按人與頻道計數、每人附最近幾則原文；人標「名字#尾碼」、頻道標名稱、
    時間換成本地時間；bot 自己的訊息不算；一筆都沒有就改走 topic 並註明不是一字不差
  - topic：走 `search_chat` 全庫（不限頻道、折疊、過品質閘），回誰、哪個頻道、何時、說過幾次
  - author／channel 用模型看到的名字對：對到一個就過濾；對不到或對到好幾個回錯誤（列出候選）
  - 任何失敗（參數錯、不認得的工具、DB 壞）都回 `{"error": ...}`，不往外丟；經過記在 `calls`

hermetic：假的連線、假的 search_chat，不碰模型與資料庫。

執行：
    cd src && python -m unittest test.test_chat_search_tool -v
"""

import asyncio
import json
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from llm.retrievers import chat_search as cs  # noqa: E402

MING, HUA, GE, BOT = "100000000000000111", "100000000000000222", "100000000000000333", "100000000000000999"
MEMBERS = {MING: ["小明", "ming"], HUA: ["小華"], GE: ["明哥"]}
CHANNELS = {"77": "閒聊", "88": "鳴潮"}
T = "2026-10-20T13:03:00+00:00"          # 本地（+08:00）21:03
GROUPS = [(MING, "77", 80, T), (MING, "88", 17, "2026-10-01T00:00:00+00:00"),
          (HUA, "77", 3, "2026-09-01T00:00:00+00:00"), (BOT, "77", 5, T)]
RECENT = [(MING, "77", T, "好了啦  又在裝"), (MING, "77", "2026-10-19T01:00:00+00:00", "好了啦！"),
          (MING, "88", "2026-10-01T00:00:00+00:00", "好了啦 第三則"), (HUA, "77", "2026-09-01T00:00:00+00:00", "好了啦喔")]


def combined(groups, recent):
    """一次掃描的回傳：計數列與最近幾則混在同一個結果裡，用第一欄分。"""
    return [("count", a, c, str(n), last) for a, c, n, last in groups] + [("recent", a, c, ts, t) for a, c, ts, t in recent]


class _Cursor:
    def __init__(self, rows):
        self.queue = [list(rows)]
        self.executed: list[tuple[str, tuple]] = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchall(self):
        return self.queue.pop(0) if self.queue else []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _Conn:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def topic_row(mid, text, author, *, channel="77", repeat=1, dist=0.2):
    return {"message_id": mid, "text": text, "author_id": author, "channel_id": channel, "distance": dist,
            "timestamp": T, "repeat_count": repeat}


class ChatSearchToolsTests(unittest.TestCase):
    def setUp(self):
        self.cursor = _Cursor(combined(GROUPS, RECENT))
        self.search_calls = []
        self.topic_rows = [topic_row("1", ":吃瓜看戲:", MING), topic_row("2", "我幾乎不喝水的", BOT),
                           topic_row("3", "我一天喝不到一杯水", HUA, channel="88", repeat=3), topic_row("4", "水喝太少會頭痛", MING)]

        def fake_search(**kwargs):
            self.search_calls.append(kwargs)
            return list(self.topic_rows)

        for patcher in (mock.patch.object(cs, "_connect", lambda: _Conn(self.cursor)),
                        mock.patch.object(cs.context_retriever, "search_chat", side_effect=fake_search)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def tools(self, **kwargs):
        kwargs.setdefault("instructions", "【聊天紀錄搜尋規則】")
        return cs.ChatSearchTools(member_names=MEMBERS, channel_names=CHANNELS, self_id=BOT, **kwargs)

    def run_tool(self, runner, arguments, name="chat_search"):
        return json.loads(asyncio.run(runner.execute(name, arguments)))

    def test_declares_one_tool_with_a_required_query_and_two_modes(self):
        (tool,) = self.tools().tools
        params = tool["function"]["parameters"]
        self.assertEqual(tool["function"]["name"], "chat_search")
        self.assertEqual(params["required"], ["query"])
        self.assertEqual(params["properties"]["mode"]["enum"], ["phrase", "topic"])
        self.assertIn("author", params["properties"])
        self.assertIn("channel", params["properties"])

    def test_rules_file_is_readable_from_the_default_path(self):
        runner = cs.ChatSearchTools(member_names=MEMBERS, channel_names=CHANNELS)
        self.assertIn("【聊天紀錄搜尋規則】", runner.instructions)

    def test_phrase_counts_per_speaker_and_channel_and_labels_people_places_and_local_time(self):
        payload = self.run_tool(self.tools(), {"query": "好了啦", "mode": "phrase"})
        self.assertEqual(payload["mode"], "phrase")
        self.assertEqual(payload["total"], 100, "bot 自己的 5 則不算")
        first, second = payload["speakers"]
        self.assertTrue(first["name"].startswith("小明#") and first["name"].endswith("111"))
        self.assertEqual(first["count"], 97)
        self.assertEqual(first["channels"], ["閒聊 80", "鳴潮 17"])
        self.assertEqual(first["latest"], "2026-10-20")
        self.assertEqual(first["examples"], ["[2026-10-20 21:03 #閒聊] 好了啦 又在裝", "[2026-10-19 09:00 #閒聊] 好了啦！"])
        self.assertTrue(second["name"].startswith("小華#"))
        self.assertEqual(second["count"], 3)
        timeout_sql, (timeout_ms,) = self.cursor.executed[0]
        self.assertIn("SET LOCAL statement_timeout", timeout_sql)
        self.assertEqual(timeout_ms, 20000)
        sql, params = self.cursor.executed[1]
        self.assertIn("ILIKE %s ESCAPE", sql)
        self.assertIn("GROUP BY author, channel", sql)
        self.assertIn("ORDER BY ts DESC LIMIT %s", sql)
        self.assertEqual(len(self.cursor.executed), 2, "計數與最近幾則同一次掃描")
        self.assertEqual(params, ("%好了啦%", cs.AskAIChatSearchSettings().phrase_scan_rows))

    def test_phrase_escapes_like_wildcards(self):
        self.run_tool(self.tools(), {"query": "100%_x", "mode": "phrase"})
        self.assertEqual(self.cursor.executed[1][1][0], "%100\\%\\_x%")

    def test_author_and_channel_filters_resolve_names_to_ids(self):
        runner = self.tools()
        self.run_tool(runner, {"query": "好了啦", "mode": "phrase", "author": "小明#0111", "channel": "#鳴潮"})
        _, params = self.cursor.executed[1]
        self.assertEqual(params, ("%好了啦%", MING, "88", cs.AskAIChatSearchSettings().phrase_scan_rows))
        self.assertEqual(runner.calls[0]["author_id"], MING)
        self.assertEqual(runner.calls[0]["channel_id"], "88")

    def test_author_resolution_errors_name_the_candidates(self):
        runner = self.tools()
        ambiguous = self.run_tool(runner, {"query": "x", "author": "明"})
        self.assertIn("小明#", ambiguous["error"])
        self.assertIn("明哥#", ambiguous["error"])
        unknown = self.run_tool(runner, {"query": "x", "author": "阿花"})
        self.assertIn("找不到", unknown["error"])
        no_channel = self.run_tool(runner, {"query": "x", "channel": "語音"})
        self.assertIn("沒有叫", no_channel["error"])
        self.assertEqual(self.search_calls, [], "對不到人或頻道就不查")
        self.assertEqual([c["error"][:3] for c in runner.calls], ["有好幾", "找不到", "沒有叫"])

    def test_phrase_without_hits_falls_back_to_topic_with_a_note(self):
        self.cursor.queue = [[]]
        runner = self.tools()
        payload = self.run_tool(runner, {"query": "不喝水", "mode": "phrase"})
        self.assertEqual(payload["mode"], "topic")
        self.assertIn("不是一字不差", payload["note"])
        self.assertEqual(len(self.search_calls), 1)
        self.assertEqual(runner.calls[0]["fallback"], "topic")

    def test_topic_searches_the_whole_corpus_and_renders_who_where_when(self):
        runner = self.tools()
        payload = self.run_tool(runner, {"query": "不喝水", "author": "小華"})
        call = self.search_calls[0]
        self.assertIsNone(call["candidate_ids"])
        self.assertEqual(call["author_id"], HUA)
        self.assertIsNone(call["channel_id"])
        self.assertTrue(call["collapse"] and call["return_meta"])
        self.assertEqual(call["limit"], cs.AskAIChatSearchSettings().topic_limit * 2)
        texts = [r["text"] for r in payload["results"]]
        self.assertEqual(texts, ["我一天喝不到一杯水", "水喝太少會頭痛"], "純表情與 bot 自己的不回")
        hit = payload["results"][0]
        self.assertEqual((hit["when"], hit["channel"], hit["repeats"]), ("2026-10-20 21:03", "鳴潮", 3))
        self.assertTrue(hit["name"].startswith("小華#"))
        self.assertNotIn("repeats", payload["results"][1])
        self.assertEqual(runner.calls[0]["result_count"], 2)

    def test_failures_become_error_payloads(self):
        runner = self.tools()
        self.assertIn("error", self.run_tool(runner, {"query": ""}))
        self.assertIn("error", self.run_tool(runner, {"query": "x", "mode": "regex"}))
        self.assertIn("error", self.run_tool(runner, {"query": "x"}, name="other_tool"))
        with mock.patch.object(cs, "_connect", side_effect=RuntimeError("db down")):
            broken = self.run_tool(runner, {"query": "x", "mode": "phrase"})
        self.assertIn("查不到", broken["error"])
        self.assertEqual(len(runner.calls), 4)
        self.assertIn("db down", "") if False else self.assertTrue(all("error" in c for c in runner.calls))


if __name__ == "__main__":
    unittest.main()
