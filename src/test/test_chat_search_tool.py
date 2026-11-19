"""聊天紀錄搜尋做成給模型的工具（`llm/retrievers/chat_search.py` 的 `ChatSearchTools`）：/askai 的 `askai_chat_search_mode=on`。

守的底線：
  - 宣告一個 chat_search 工具，query 必填、mode（phrase／topic）、author、channel 選填；使用規則讀 `askai_chat_search_rules.txt`
    （正式環境的預設路徑讀得到）
  - phrase：ILIKE 子字串（% 與 _ 會跳脫）、一次掃描同時算計數與最近幾則、有逾時上限、按人與頻道計數、每人附最近幾則原文；人標「名字#尾碼」、頻道標名稱、
    時間換成本地時間；bot 自己的訊息不算；一筆都沒有就改走 topic 並註明不是一字不差
  - topic：走 `search_chat` 全庫（不限頻道、折疊、過品質閘），回最像的幾則例句，加上「最像的 N 句裡誰說了幾句」的統計：
    距離超過上限的不算、同一句重複講的算次數、bot 自己的不算
  - contains 把兩種模式的範圍鎖在含某個詞的句子（phrase 多一個 ILIKE、topic 交給 search_chat 的 text_contains）
  - author／channel 用模型看到的名字對：對到一個就過濾；對不到或對到好幾個回錯誤（列出候選）
  - 任何失敗（參數錯、不認得的工具、DB 壞）都回 `{"error": ...}`，不往外丟；經過記在 `calls`
  - 給了固定頻道（插話用）：宣告裡沒有 channel 參數、說明不講全部頻道，兩種模式都只查那個頻道，模型填別的頻道也不看；
    原本那份全伺服器的宣告不受影響
  - 群友已經刪掉的訊息不給模型看原文（照原始訊息表的軟刪記號）：topic 對撈回來的查一次、濾掉；phrase 只查要附的例句
    （每人多留幾則備用，刪掉的由下一則補上），掃描的 SQL 不碰原始訊息表、計數不扣
  - topic 帶查詢的時間上限；查詢失敗回錯誤給模型，不回「0 句」

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
RECENT = [(MING, "77", T, "好了啦  又在裝", "901"), (MING, "77", "2026-10-19T01:00:00+00:00", "好了啦！", "902"),
          (MING, "88", "2026-10-01T00:00:00+00:00", "好了啦 第三則", "903"), (HUA, "77", "2026-09-01T00:00:00+00:00", "好了啦喔", "904")]


def combined(groups, recent):
    """一次掃描的回傳：計數列與最近幾則混在同一個結果裡，用第一欄分。"""
    return ([("count", a, c, str(n), last, None) for a, c, n, last in groups]
            + [("recent", a, c, ts, t, mid) for a, c, ts, t, mid in recent])


class _Cursor:
    def __init__(self, rows):
        self.queue = [list(rows)]
        self.executed: list[tuple[str, tuple]] = []      # 對聊天表下的查詢（連同它前面設的時間上限）
        self.deleted: set[str] = set()                   # 原始訊息表標成已刪的訊息
        self.deleted_lookups: list[list[str]] = []       # 問過「這幾則有沒有被刪」的 id
        self.deleted_sql: list[str] = []                 # 那幾次查詢的 SQL
        self.deleted_limits: list[tuple] = []            # 那幾次查詢前設的時間上限（毫秒）；沒設是 None
        self._limit = None                               # 剛設、還不知道是替哪一條查詢設的時間上限
        self._asked_deleted = False

    def execute(self, sql, params=None):
        if sql.lstrip().startswith("SET LOCAL statement_timeout"):
            self._limit = (sql, params)
            return
        self._asked_deleted = sql.lstrip().startswith("SELECT message_id FROM discord_messages_raw")
        if self._asked_deleted:
            self.deleted_lookups.append(list(params[0]))
            self.deleted_sql.append(sql)
            self.deleted_limits.append(self._limit[1] if self._limit else None)
        else:
            if self._limit:
                self.executed.append(self._limit)
            self.executed.append((sql, params))
        self._limit = None

    def fetchall(self):
        if self._asked_deleted:
            return [(mid,) for mid in self.deleted_lookups[-1] if mid in self.deleted]
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
                           topic_row("3", "我一天喝不到一杯水", HUA, channel="88", repeat=3), topic_row("4", "水喝太少會頭痛", MING),
                           topic_row("5", "水費又漲價了", GE, dist=0.9)]   # 太遠：不算像

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
        self.assertIn("contains", params["properties"])

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
        self.assertIn("照字面找不到", payload["note"])
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
        self.assertEqual(call["limit"], cs.AskAIChatSearchSettings().topic_tally_limit)
        self.assertIsNone(call["text_contains"])
        texts = [r["text"] for r in payload["results"]]
        self.assertEqual(texts, ["我一天喝不到一杯水", "水喝太少會頭痛"], "純表情、bot 自己的、太遠的都不回")
        hit = payload["results"][0]
        self.assertEqual((hit["when"], hit["channel"], hit["repeats"]), ("2026-10-20 21:03", "鳴潮", 3))
        self.assertTrue(hit["name"].startswith("小華#"))
        self.assertNotIn("repeats", payload["results"][1])
        # 統計：同一句重複講的算次數（小華 3）、太遠的不算（明哥 0）、bot 不算
        self.assertEqual([(s["name"][:2], s["count"]) for s in payload["speakers"]], [("小華", 3), ("小明", 1)])
        self.assertEqual(payload["speakers"][0]["examples"], ["[2026-10-20 21:03 #鳴潮] 我一天喝不到一杯水"])
        self.assertEqual(payload["counted"], 4)
        self.assertIn("最像的 2 句", payload["note"])
        self.assertEqual(runner.calls[0]["result_count"], 4)

    def test_contains_narrows_both_modes_to_sentences_with_that_word(self):
        runner = self.tools()
        self.run_tool(runner, {"query": "嘲笑阿喵 阿喵好廢", "mode": "topic", "contains": "阿喵"})
        self.assertEqual(self.search_calls[0]["text_contains"], "阿喵")
        self.assertEqual(runner.calls[0]["contains"], "阿喵")
        self.run_tool(runner, {"query": "好了啦", "mode": "phrase", "contains": "50%_"})
        sql, params = self.cursor.executed[1]
        self.assertEqual(sql.count("text ILIKE %s ESCAPE"), 2)
        self.assertEqual(params[:2], ("%好了啦%", "%50\\%\\_%"))

    # ── 鎖在一個頻道（插話用） ──
    def test_one_channel_tools_declare_no_channel_and_always_search_that_channel(self):
        runner = self.tools(fixed_channel_id=77)
        (tool,) = runner.tools
        self.assertNotIn("channel", tool["function"]["parameters"]["properties"])
        self.assertIn("這個頻道的聊天紀錄", tool["function"]["description"])
        self.assertNotIn("全部頻道", tool["function"]["description"])
        for other in ("query", "mode", "author", "contains"):
            self.assertIn(other, tool["function"]["parameters"]["properties"])

        payload = self.run_tool(runner, {"query": "好了啦", "mode": "phrase", "channel": "鳴潮"})
        self.assertNotIn("error", payload, "模型填了別的頻道也不看、不報錯")
        sql, params = self.cursor.executed[1]
        self.assertIn("metadata_->>'channel_id' = %s", sql)
        self.assertEqual(params, ("%好了啦%", "77", cs.AskAIChatSearchSettings().phrase_scan_rows))
        self.run_tool(runner, {"query": "不喝水", "channel": "沒有這個頻道"})
        self.assertEqual("77", self.search_calls[0]["channel_id"])
        self.assertEqual(["77", "77"], [call["channel_id"] for call in runner.calls])

    def test_the_whole_server_declaration_keeps_its_channel_parameter(self):
        self.tools(fixed_channel_id=77).tools
        (tool,) = self.tools().tools
        self.assertIn("channel", tool["function"]["parameters"]["properties"])
        self.assertIn("全部頻道", tool["function"]["description"])
        self.assertEqual(self.tools(fixed_channel_id=77).tools, self.tools(fixed_channel_id=88).tools, "宣告不隨頻道變，提示詞快取才穩")

    # ── 群友已經刪掉的訊息 ──
    def test_messages_members_deleted_are_left_out_of_what_topic_returns(self):
        self.cursor.deleted = {"3"}
        payload = self.run_tool(self.tools(), {"query": "不喝水"})
        self.assertEqual(["水喝太少會頭痛"], [r["text"] for r in payload["results"]])
        self.assertEqual([("小明", 1)], [(s["name"][:2], s["count"]) for s in payload["speakers"]], "刪掉的那則也不進統計")
        self.assertEqual([["1", "2", "3", "4", "5"]], self.cursor.deleted_lookups, "只對撈回來的那幾則問一次")
        sql = " ".join(self.cursor.deleted_sql[0].split())
        self.assertIn("WHERE message_id = ANY(%s) AND is_deleted", sql, "只認標成已刪的；少了這個條件，表裡有的每一則都會被當成已刪")
        self.assertEqual([(20000,)], self.cursor.deleted_limits, "這條查詢也有時間上限")

    def test_a_message_deleted_moments_ago_is_left_out_before_the_database_knows(self):
        # 刪除記號是批次寫進資料庫的：上層交進「收到刪除事件、還沒寫進去」的 id，兩邊合起來算
        runner = self.tools(pending_deleted=lambda: {"4", "999"})
        payload = self.run_tool(runner, {"query": "不喝水"})
        self.assertEqual(["我一天喝不到一杯水"], [r["text"] for r in payload["results"]])
        self.cursor.deleted = {"3"}
        payload = self.run_tool(runner, {"query": "不喝水"})
        self.assertEqual([], payload["results"], "資料庫裡的和還沒寫進去的都算")

    def test_phrase_leaves_deleted_messages_out_of_the_examples_and_fills_from_the_next_one(self):
        self.cursor.deleted = {"901"}
        payload = self.run_tool(self.tools(), {"query": "好了啦", "mode": "phrase"})
        first = payload["speakers"][0]
        self.assertEqual(["[2026-10-19 09:00 #閒聊] 好了啦！", "[2026-10-01 08:00 #鳴潮] 好了啦 第三則"], first["examples"],
                         "刪掉的那則不給看，由下一則補上")
        self.assertEqual(97, first["count"], "計數不扣：逐筆去查每一則有沒有被刪太貴")
        self.assertEqual([["901", "902", "903", "904"]], self.cursor.deleted_lookups, "只問要附的那幾則，一次問完")

    def test_the_phrase_scan_itself_does_not_touch_the_raw_message_table(self):
        # 掃描時逐筆回原始訊息表查，資料不在快取時把查詢時間加倍、常見詞會撞逾時
        self.run_tool(self.tools(), {"query": "好了啦", "mode": "phrase"})
        sql, _params = self.cursor.executed[1]
        self.assertNotIn("discord_messages_raw", sql)
        self.assertNotIn("is_deleted", sql)
        self.assertIn("metadata_->>'message_id' AS mid", sql)

    # ── 時間上限、查詢失敗 ──
    def test_topic_has_a_time_limit_and_reports_a_failed_search_as_an_error(self):
        runner = self.tools()
        self.run_tool(runner, {"query": "不喝水"})
        call = self.search_calls[0]
        self.assertEqual(cs.AskAIChatSearchSettings().statement_timeout_seconds, call["timeout_seconds"])
        self.assertTrue(call["raise_errors"])

        with mock.patch.object(cs.context_retriever, "search_chat", side_effect=RuntimeError("statement timeout")):
            payload = self.run_tool(runner, {"query": "不喝水"})
        self.assertIn("查不到", payload["error"], "沒查成要讓模型知道，不能回成 0 句")
        self.assertNotIn("counted", payload)

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
