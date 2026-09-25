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
        changes = [
            {"trait": "口頭禪", "text": "「何意味」是固定口頭禪"},
            {"trait": "貼圖", "text": "貼圖使用極少"},
        ]
        fetch = FakeFetch(results=[[("已經是 agent 寫的第 3 版", 3, changes)]])
        payload = json.loads(tools.get_current_persona(ctx(fetch), user_id=ALICE))
        self.assertEqual(payload["source"], "v3")
        self.assertEqual(len(fetch.calls), 1, "有自己的版本就不該再查 production")
        self.assertEqual([i["n"] for i in payload["items"]], [1, 2],
                         "要給編號，模型才有辦法說「第 2 項不動」")
        self.assertEqual(payload["items"][0]["text"], "「何意味」是固定口頭禪")

    def test_items_skip_entries_without_text(self):
        """沒有文字的項目不該佔掉編號——編號要對得上模型看到的清單。"""
        changes = [{"trait": "a", "text": "有內容"}, {"trait": "b", "text": "  "},
                   {"trait": "c", "text": "第三項"}]
        fetch = FakeFetch(results=[[("x", 5, changes)]])
        items = json.loads(tools.get_current_persona(ctx(fetch), user_id=ALICE))["items"]
        self.assertEqual([i["text"] for i in items], ["有內容", "第三項"])
        self.assertEqual([i["n"] for i in items], [1, 3], "編號沿用原始位置，不重新編")

    def test_items_carry_last_seen_from_their_evidence(self):
        """keep 不再被逼著每晚重附證據——模型要改看「最後一次有佐證」判斷是否過時。

        日期直接從訊息 id（Discord snowflake）解出，不多查 DB：有自己的版本時
        仍然只有一次查詢。兩個 id 是「糯糯」那項的真實證據（09-01、09-09）。
        """
        changes = [
            {"trait": "糯糯", "text": "「糯糯」是他的專屬梗",
             "evidence_msg_ids": ["1544302219510292480", "1547184851646423110"]},
            {"trait": "舊資料", "text": "沒有可解析的 id", "evidence_msg_ids": ["m1"]},
        ]
        fetch = FakeFetch(results=[[("x", 5, changes)]])
        items = json.loads(tools.get_current_persona(ctx(fetch), user_id=ALICE))["items"]
        self.assertEqual(len(fetch.calls), 1, "日期由 id 解出，不該多一次查詢")
        self.assertRegex(items[0]["last_seen"], r"^09-09（\d+ 天前）$", "取最新的那一則")
        self.assertNotIn("last_seen", items[1], "解不出日期就不給，不要給錯的")

    def test_snowflake_time_matches_the_db_timestamp(self):
        """DB 裡這則的 timestamp 是 2026-09-09T10:00:13.937+00:00。"""
        t = tools._snowflake_time("1547184851646423110")
        self.assertEqual(t.isoformat(), "2026-09-09T10:00:13.937000+00:00")
        for bad in ("m1", "", None, "-5", "0"):
            self.assertIsNone(tools._snowflake_time(bad), repr(bad))

    def test_out_of_range_ids_do_not_crash(self):
        """審查重現：`1` 接 22 個 0 會讓 fromtimestamp 丟 ValueError，整個人那晚失敗。"""
        from datetime import datetime, timezone
        now = datetime(2026, 9, 24, tzinfo=timezone.utc)
        for bad in ("1" + "0" * 22, str(2**63), str(2**64), "9" * 26):
            self.assertIsNone(tools._snowflake_time(bad), bad[:8])
            self.assertIsNone(tools._last_seen([bad], now=now), bad[:8])

    def test_last_seen_ignores_non_list_and_future_ids(self):
        """字串會被逐字元拆成 id "1"（算出 2015-01-01）；未來的時間只可能是錯的 id。"""
        from datetime import datetime, timezone
        now = datetime(2026, 9, 24, tzinfo=timezone.utc)
        self.assertIsNone(tools._last_seen("1547184851646423110", now=now))
        future = str(2**63 - 1)   # 2084 年
        self.assertEqual(tools._last_seen([future, "1547184851646423110"], now=now),
                         "09-09（15 天前）", "未來的 id 不算，其餘照算")

    def test_last_seen_counts_days_in_taipei_time(self):
        """UTC 16:30 已經是台北隔天——天數要照群組作息的本地日期算。"""
        from datetime import datetime, timezone
        # 1547184851646423110 → 台北 09-09 18:00
        now = datetime(2026, 9, 24, 16, 30, tzinfo=timezone.utc)  # 台北 09-25 00:30
        self.assertEqual(tools._last_seen(["1547184851646423110"], now=now),
                         "09-09（16 天前）")
        self.assertIsNone(tools._last_seen([], now=now))
        self.assertIsNone(tools._last_seen(None, now=now))

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

    def test_conversation_distinguishes_speakers_without_citable_ids(self):
        """現場要分得出誰是誰，但旁人不可以帶 `id`。

        原本這條驗的是「保留 author_id」，理由是作者會變、是判讀互動的關鍵。
        那個意圖仍然成立，只是換了載體：本人留 `id`（可引用）、旁人留 `by` 代號
        （可辨識但引用不到）。改結構的原因見 `tools._mask_other_authors`——
        51 個假 id 裡 19 個是「真訊息但作者是別人」，prompt 警告過仍然會犯。
        """
        fetch = FakeFetch(results=[
            [row("m2", "c1", "2026-08-01T22:10:00+08:00", ALICE, "你也太廢")],
            [row("m1", "c1", "2026-08-01T22:09:00+08:00", "OTHER", "我剛剛又死了")],
            [row("m3", "c1", "2026-08-01T22:11:00+08:00", "OTHER", "閉嘴啦")],
        ])
        msgs = json.loads(
            tools.get_conversation(ctx(fetch), around_msg_id="m2")
        )["messages"]
        mine = [m for m in msgs if "id" in m]
        others = [m for m in msgs if "id" not in m]
        self.assertEqual([m["id"] for m in mine], ["m2"], "只有本人的訊息可引用")
        self.assertTrue(all("author_id" not in m for m in msgs), "雪花號一律不外露")
        self.assertEqual([m["by"] for m in others], ["他人1", "他人1"],
                         "同一個旁人要是同一個代號，否則分不出互動")

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


class MaskOtherAuthorsTests(unittest.TestCase):
    """旁人的訊息不可以帶 `id`——引用不到才引用不錯。

    `final_prompt` 當時就警告過「引用不屬於這位使用者的 id，整筆結果都會被丟棄」，
    但實測 51 個被擋下的假 id 裡有 **19 個（37%）是真訊息、只是作者是別人**。
    指令下過還是會犯 → 改結構：沒有 id 欄位就抄不到。
    """

    def _ctx(self):
        from llm.persona_agent.tools import ToolContext
        return ToolContext.build(guild_id=1, allowed_ids=["SELF"])

    def test_self_keeps_id_and_drops_redundant_author(self):
        from llm.persona_agent.tools import _mask_other_authors
        out = _mask_other_authors(self._ctx(), [
            {"id": "m1", "ts": "10:00", "text": "我說的", "author_id": "SELF"},
        ])
        self.assertEqual(out[0]["id"], "m1")
        self.assertNotIn("author_id", out[0], "單人查詢時作者恆定，留著只是燒 context")

    def test_other_loses_id(self):
        from llm.persona_agent.tools import _mask_other_authors
        out = _mask_other_authors(self._ctx(), [
            {"id": "m2", "ts": "10:01", "text": "別人說的", "author_id": "OTHER"},
        ])
        self.assertNotIn("id", out[0], "沒有 id 才引用不到")
        self.assertNotIn("author_id", out[0])
        self.assertEqual(out[0]["by"], "他人1")

    def test_same_other_keeps_the_same_label(self):
        """互動判讀要分得出「A 講完 B 接話」與「同一人自言自語」。"""
        from llm.persona_agent.tools import _mask_other_authors
        out = _mask_other_authors(self._ctx(), [
            {"id": "a", "ts": "1", "text": "x", "author_id": "B"},
            {"id": "b", "ts": "2", "text": "y", "author_id": "C"},
            {"id": "c", "ts": "3", "text": "z", "author_id": "B"},
        ])
        self.assertEqual([m["by"] for m in out], ["他人1", "他人2", "他人1"])

    def test_anchor_flag_survives(self):
        from llm.persona_agent.tools import _mask_other_authors
        out = _mask_other_authors(self._ctx(), [
            {"id": "m", "ts": "1", "text": "t", "author_id": "SELF", "is_anchor": True},
        ])
        self.assertTrue(out[0]["is_anchor"])
