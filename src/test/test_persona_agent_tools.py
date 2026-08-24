"""Persona agent 四支唯讀工具的單元測試（hermetic，不碰 DB）。

工具的 `fetch` 是可注入的 callable，這裡塞假的執行器，驗證三件在 handoff 被列為
硬性要求、且錯了很難察覺的事：

  ① 上限夾取     —— days ≤ 90 / limit ≤ 200 / 搜尋 ≤ 50 / 視窗 ≤ 30，夾住而非報錯
  ② 白名單拒絕   —— 樣本清單外的 user_id 一律擋下，且**不得**發出任何查詢
  ③ guild_id 必帶 —— 人格查詢漏帶 guild_id 會撈到舊格式殘留當 diff 基準（2026-08-18
                     清掉的 12 筆殭屍列就是實例），正確性不能靠資料剛好乾淨

外加：例外要變成 `{"error": ...}` 回給模型，不能拋出去中斷 agent loop。

執行：
    cd src && python -m unittest test.test_persona_agent_tools -v
"""

import json
import os
import sys
import unittest
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from llm.persona_agent import tools  # noqa: E402

GUILD = 1276158257576284274
ALICE = "1001"
BOB = "1002"
OUTSIDER = "9999"


class FakeFetch:
    """記錄每次查詢的 (sql, params)，並依序吐出預設好的結果。"""

    def __init__(self, results=None, raises=None):
        self.calls = []
        self._results = list(results or [])
        self._raises = raises

    def __call__(self, sql, params):
        self.calls.append((sql, list(params)))
        if self._raises:
            raise self._raises
        return self._results.pop(0) if self._results else []

    @property
    def last_params(self):
        return self.calls[-1][1]


def ctx(fetch, allowed=(ALICE, BOB)):
    return tools.ToolContext.build(guild_id=GUILD, allowed_ids=allowed, fetch=fetch)


def row(msg_id, channel, ts, author, text):
    return (msg_id, channel, ts, author, text)


def iso_param(params):
    """從 SQL 參數裡挑出時間界線字串（uid / limit 不會長這樣）。"""
    return next(p for p in params if isinstance(p, str) and p.startswith("20"))


class ClampTests(unittest.TestCase):
    """① 上限夾取：超過就夾住並在回傳註明，不報錯。"""

    def test_get_messages_clamps_days_and_limit(self):
        fetch = FakeFetch()
        payload = json.loads(
            tools.get_messages(ctx(fetch), user_id=ALICE, days=9999, limit=9999)
        )
        self.assertEqual(payload["days"], tools.MAX_DAYS)
        self.assertEqual(payload["limit"], tools.MAX_MESSAGE_LIMIT)
        self.assertTrue(payload["clamped"]["days"])
        self.assertTrue(payload["clamped"]["limit"])
        # 夾後的值必須真的進到 SQL 參數，不能只寫在回傳裡
        self.assertIn(tools.MAX_MESSAGE_LIMIT, fetch.last_params)
        # days 夾取後會轉成時間界線字串（為了吃得到表達式索引），驗證它真的是
        # 90 天前而不是 9999 天前
        cutoff = datetime.fromisoformat(iso_param(fetch.last_params))
        self.assertEqual((datetime.now(timezone.utc) - cutoff).days, tools.MAX_DAYS)

    def test_get_messages_keeps_values_within_limit(self):
        fetch = FakeFetch()
        payload = json.loads(
            tools.get_messages(ctx(fetch), user_id=ALICE, days=14, limit=50)
        )
        self.assertEqual(payload["days"], 14)
        self.assertEqual(payload["limit"], 50)
        self.assertFalse(payload["clamped"]["days"])
        self.assertFalse(payload["clamped"]["limit"])

    def test_days_becomes_cutoff_string_not_raw_number(self):
        """時間條件必須是字串界線，否則 (author_id, timestamp) 表達式索引吃不到。"""
        fetch = FakeFetch()
        tools.get_messages(ctx(fetch), user_id=ALICE, days=7)
        sql, params = fetch.calls[0]
        self.assertNotIn("::timestamptz", sql)
        self.assertNotIn("make_interval", sql)
        cutoff = datetime.fromisoformat(iso_param(params))
        self.assertEqual((datetime.now(timezone.utc) - cutoff).days, 7)

    def test_get_messages_falls_back_on_garbage(self):
        """模型偶爾會塞非數字；退回預設值而不是炸掉。"""
        fetch = FakeFetch()
        payload = json.loads(
            tools.get_messages(ctx(fetch), user_id=ALICE, days="七天", limit=None)
        )
        self.assertEqual(payload["days"], tools.DEFAULT_MESSAGE_DAYS)
        self.assertEqual(payload["limit"], tools.DEFAULT_MESSAGE_LIMIT)

    def test_search_messages_clamps_to_its_own_limit(self):
        fetch = FakeFetch()
        payload = json.loads(
            tools.search_messages(ctx(fetch), user_id=ALICE, keyword="抽卡", limit=500)
        )
        self.assertEqual(payload["limit"], tools.MAX_SEARCH_LIMIT)
        self.assertTrue(payload["clamped"]["limit"])

    def test_get_conversation_clamps_window(self):
        fetch = FakeFetch(results=[
            [row("m5", "c1", "2026-08-01T10:00:00+08:00", ALICE, "你開他")],
            [],
            [],
        ])
        payload = json.loads(
            tools.get_conversation(ctx(fetch), around_msg_id="m5", before=999, after=999)
        )
        self.assertEqual(payload["before"], tools.MAX_CONVERSATION_WINDOW)
        self.assertEqual(payload["after"], tools.MAX_CONVERSATION_WINDOW)
        self.assertTrue(payload["clamped"]["before"])


class WhitelistTests(unittest.TestCase):
    """② 白名單：清單外一律拒絕，而且不能送出任何查詢。"""

    def test_get_messages_rejects_outsider_without_querying(self):
        fetch = FakeFetch()
        payload = json.loads(tools.get_messages(ctx(fetch), user_id=OUTSIDER))
        self.assertIn("error", payload)
        self.assertEqual(fetch.calls, [], "白名單拒絕時不得發出查詢")

    def test_all_user_scoped_tools_reject_outsider(self):
        for call in (
            lambda c: tools.get_current_persona(c, user_id=OUTSIDER),
            lambda c: tools.get_messages(c, user_id=OUTSIDER),
            lambda c: tools.search_messages(c, user_id=OUTSIDER, keyword="x"),
        ):
            fetch = FakeFetch()
            self.assertIn("error", json.loads(call(ctx(fetch))))
            self.assertEqual(fetch.calls, [])

    def test_empty_user_id_rejected(self):
        fetch = FakeFetch()
        self.assertIn("error", json.loads(tools.get_messages(ctx(fetch), user_id="")))
        self.assertEqual(fetch.calls, [])

    def test_get_conversation_checks_anchor_author(self):
        """白名單套在錨點訊息的作者上——不能拿來瀏覽任意對話。"""
        fetch = FakeFetch(results=[
            [row("m9", "c1", "2026-08-01T10:00:00+08:00", OUTSIDER, "路人發言")],
        ])
        payload = json.loads(tools.get_conversation(ctx(fetch), around_msg_id="m9"))
        self.assertIn("error", payload)
        # 只查了錨點就擋下，沒有繼續撈前後文
        self.assertEqual(len(fetch.calls), 1)


class GuildScopeTests(unittest.TestCase):
    """③ guild_id 必帶：漏掉會撈到殭屍列當 diff 基準。"""

    def test_get_current_persona_filters_guild(self):
        """沒有自己的版本時退回 production，且兩段查詢都要帶 guild_id。"""
        fetch = FakeFetch(results=[
            [],  # persona_agent_versions：還沒有自己的版本
            [("[Auto Personality]\nalias: 米拉\npersonality: 直球型吐槽擔當",
              "米拉", "2026-08-17T20:13:26+00:00")],
        ])
        payload = json.loads(tools.get_current_persona(ctx(fetch), user_id=ALICE))
        for sql, params in fetch.calls:
            self.assertIn("guild_id", sql)
            self.assertIn(str(GUILD), params)
        self.assertEqual(payload["persona_text"], "直球型吐槽擔當")
        self.assertEqual(payload["source"], "production_auto_personality")

    def test_own_version_wins_over_production(self):
        """有自己的版本就用自己的——diff 要疊在上一版之上，不是每次都跟 production 比。"""
        fetch = FakeFetch(results=[[("已經是 agent 寫的第 3 版", 3)]])
        payload = json.loads(tools.get_current_persona(ctx(fetch), user_id=ALICE))
        self.assertEqual(payload["persona_text"], "已經是 agent 寫的第 3 版")
        self.assertEqual(payload["source"], "v3")
        self.assertEqual(len(fetch.calls), 1, "有自己的版本就不該再查 production")

    def test_get_current_persona_handles_missing_row(self):
        fetch = FakeFetch(results=[[]])
        payload = json.loads(tools.get_current_persona(ctx(fetch), user_id=ALICE))
        self.assertIsNone(payload["persona_text"])
        self.assertIsNone(payload["source"])


class BehaviourTests(unittest.TestCase):
    """其餘契約：排序、跳脫、錯誤轉 JSON。"""

    def test_get_messages_returns_oldest_first(self):
        """SQL 取「最近 N 則」（DESC）避免截掉新訊息，回傳前要轉回正序。"""
        fetch = FakeFetch(results=[[
            row("m3", "c1", "2026-08-03T10:00:00+08:00", ALICE, "第三"),
            row("m2", "c1", "2026-08-02T10:00:00+08:00", ALICE, "第二"),
            row("m1", "c1", "2026-08-01T10:00:00+08:00", ALICE, "第一"),
        ]])
        payload = json.loads(tools.get_messages(ctx(fetch), user_id=ALICE))
        self.assertEqual([m["id"] for m in payload["messages"]], ["m1", "m2", "m3"])

    def test_get_messages_payload_omits_constant_fields(self):
        """單人查詢時 author/channel 恆定，留著只是燒 context（實測差一倍）。"""
        fetch = FakeFetch(results=[[
            row("m1", "c1", "2026-08-01T14:00:00+00:00", ALICE, "先忙"),
        ]])
        msg = json.loads(tools.get_messages(ctx(fetch), user_id=ALICE))["messages"][0]
        self.assertEqual(sorted(msg.keys()), ["id", "text", "ts"])
        self.assertEqual(msg["ts"], "08-01 22:00", "時間要轉台北並砍到分鐘")

    def test_conversation_keeps_author_because_it_varies(self):
        fetch = FakeFetch(results=[
            [row("m2", "c1", "2026-08-01T22:10:00+08:00", ALICE, "你也太廢")],
            [], [],
        ])
        msg = json.loads(
            tools.get_conversation(ctx(fetch), around_msg_id="m2")
        )["messages"][0]
        self.assertIn("author_id", msg)

    def test_text_is_cleaned_like_production_extraction(self):
        """共用了萃取的 prompt 規則，就必須共用它的前處理。

        prompt 整段在教「`:xxx:` 是自訂表情、不可逐字引用」；若這裡回傳原始文字，
        模型看到的是 `<:name:123>`，那段規則就成了對模型說謊。URL 同理——萃取刻意
        整段移除，一條網址還要吃掉五十幾個字元的 context。
        """
        fetch = FakeFetch(results=[[
            row("m1", "c1", "2026-08-01T14:00:00+00:00", ALICE,
                "看這個 https://example.com/a?b=1 <@123456789> 真的假的"),
        ]])
        text = json.loads(
            tools.get_messages(ctx(fetch), user_id=ALICE)
        )["messages"][0]["text"]
        self.assertNotIn("http", text)
        self.assertNotIn("<@", text)
        self.assertIn("@某人", text)

    def test_messages_emptied_by_cleaning_are_dropped(self):
        """只有一條網址的訊息，清理後空白 → 對「找線索」是純雜訊。"""
        fetch = FakeFetch(results=[[
            row("m1", "c1", "2026-08-01T14:00:00+00:00", ALICE, "https://example.com/x"),
            row("m2", "c1", "2026-08-01T14:01:00+00:00", ALICE, "這個好笑"),
        ]])
        msgs = json.loads(tools.get_messages(ctx(fetch), user_id=ALICE))["messages"]
        self.assertEqual([m["id"] for m in msgs], ["m2"])

    def test_truncated_sample_says_so(self):
        """模型要 30 天、limit 砍成 5 小時，卻只看到 count → 會誤判「不再出現」。"""
        rows = [
            row(f"m{i}", "c1", f"2026-08-01T{10 + i // 30:02d}:{i % 60:02d}:00+00:00",
                ALICE, f"第{i}則")
            for i in range(5)
        ]
        fetch = FakeFetch(results=[rows])
        payload = json.loads(
            tools.get_messages(ctx(fetch), user_id=ALICE, days=30, limit=5)
        )
        self.assertTrue(payload["truncated"], "拿滿 limit 就是被截斷")
        self.assertIn("covers", payload)
        self.assertIn("search_messages", payload["hint"], "要指路到正確的工具")
        self.assertIn("30 天", payload["hint"])

    def test_untruncated_sample_has_no_scary_hint(self):
        fetch = FakeFetch(results=[[
            row("m1", "c1", "2026-08-01T10:00:00+00:00", ALICE, "只有一則"),
        ]])
        payload = json.loads(
            tools.get_messages(ctx(fetch), user_id=ALICE, days=30, limit=60)
        )
        self.assertFalse(payload["truncated"])
        self.assertNotIn("hint", payload)

    def test_search_escapes_like_wildcards(self):
        fetch = FakeFetch()
        tools.search_messages(ctx(fetch), user_id=ALICE, keyword="100%_純")
        pattern = [p for p in fetch.last_params if isinstance(p, str) and p.startswith("%")][0]
        self.assertIn("100\\%\\_純", pattern)

    def test_search_rejects_empty_keyword(self):
        fetch = FakeFetch()
        self.assertIn("error", json.loads(
            tools.search_messages(ctx(fetch), user_id=ALICE, keyword="   ")
        ))
        self.assertEqual(fetch.calls, [])

    def test_get_conversation_assembles_window_in_order(self):
        anchor_ts = "2026-08-01T22:10:00+08:00"
        fetch = FakeFetch(results=[
            [row("m2", "c1", anchor_ts, ALICE, "你也太廢")],
            [row("m1", "c1", "2026-08-01T22:09:00+08:00", BOB, "靠 我又摔死了")],
            [row("m3", "c1", "2026-08-01T22:11:00+08:00", BOB, "笑死 我認")],
        ])
        payload = json.loads(
            tools.get_conversation(ctx(fetch), around_msg_id="m2", before=1, after=1)
        )
        self.assertEqual([m["id"] for m in payload["messages"]], ["m1", "m2", "m3"])
        self.assertTrue(payload["messages"][1].get("is_anchor"))
        self.assertNotIn("is_anchor", payload["messages"][0])

    def test_get_conversation_rejects_channel_mismatch(self):
        fetch = FakeFetch(results=[
            [row("m2", "c1", "2026-08-01T22:10:00+08:00", ALICE, "你也太廢")],
        ])
        payload = json.loads(
            tools.get_conversation(ctx(fetch), around_msg_id="m2", channel_id="c-other")
        )
        self.assertIn("error", payload)

    def test_get_conversation_missing_anchor(self):
        fetch = FakeFetch(results=[[]])
        payload = json.loads(tools.get_conversation(ctx(fetch), around_msg_id="nope"))
        self.assertIn("error", payload)

    def test_db_failure_becomes_error_json(self):
        """DB 掛掉要回錯誤 JSON 給模型自行修正，不能拋例外中斷整個 loop。"""
        fetch = FakeFetch(raises=RuntimeError("connection refused"))
        payload = json.loads(tools.get_messages(ctx(fetch), user_id=ALICE))
        self.assertIn("error", payload)
        self.assertIn("RuntimeError", payload["error"])


class SchemaTests(unittest.TestCase):
    """diff schema 的形狀（strict 模式要求 required 齊全 + 禁止額外欄位）。"""

    def test_response_format_is_strict(self):
        from llm.persona_agent.schema import build_response_format

        fmt = build_response_format()
        self.assertEqual(fmt["type"], "json_schema")
        self.assertTrue(fmt["json_schema"]["strict"])
        schema = fmt["json_schema"]["schema"]
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            sorted(schema["required"]), ["changes", "confidence", "notes", "user_id"]
        )
        change = schema["properties"]["changes"]["items"]
        self.assertIn("evidence_msg_ids", change["required"])
        self.assertFalse(change["additionalProperties"])


if __name__ == "__main__":
    unittest.main()
