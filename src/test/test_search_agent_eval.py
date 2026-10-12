"""Agent 評估的算分（`services/search/eval/agent_eval.py`）：正式模型跑完 /askai 工具輪之後，從每題的經過算分數。

守的底線：
  - 工具呼叫從模型實際收到的對話整理：第幾輪、名稱、模型自己寫的參數、對上的那一份結果；參數壞掉也留著
  - 名次看模型實際看到的結果；「第一次 search」與「任一次 search 裡最好的」分開算
  - 該查卻沒查的題目算沒找到（分母是全部題目）；只查網路不算查了遊戲情報
  - Hit／MRR 的算法和搜尋評估（`evaluate.py`）是同一份
  - 回答的連結：附到正確答案那一篇才算；工具結果的網址欄位與內文都沒出現過的連結要列出來（內文裡有的不算
    模型自己生的）；`<…>`、Markdown 括號只取網址本身
  - 用 fetch 讀到正確答案的全文要記到
  - 不該查的閒聊叫了工具要被數到
  - 報告裡的 `queries` 可以直接當搜尋評估的關鍵字檔（沒查的題目是空字串）；報告不含回答全文

執行：
    cd src && python -m unittest test.test_search_agent_eval -v
"""

import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from llm.client.tool_calls import assistant_message, tool_message  # noqa: E402
from services.search.eval.agent_eval import (  # noqa: E402
    build_report,
    score_question,
    summarize_agent,
    summarize_controls,
    tool_calls_from_messages,
    urls_in,
)
from services.search.eval.evaluate import load_keyword_queries  # noqa: E402

QUESTION = {"qid": "q01", "question": "深塔多久重置？", "category": "情報", "origin": "ptt", "type": "字面",
            "relevant": ["ptt:9", "article:7"], "partial": ["bahamut:5"]}


def hit(doc_id):
    return {"id": doc_id, "title": doc_id, "url": f"https://example.com/{doc_id.replace(':', '/')}"}


def search(*doc_ids, query="深塔 重置", round_no=1):
    return {"round": round_no, "name": "search", "arguments": {"query": query},
            "output": {"results": [hit(d) for d in doc_ids]}}


def record(*calls, reply="", **extra):
    return {"qid": "q01", "question": QUESTION["question"], "reply": reply, "error_kind": None, "elapsed_s": 12.5,
            "tool_calls": list(calls), **extra}


def call(call_id, name, arguments):
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": arguments}}


class ToolCallsFromMessagesTests(unittest.TestCase):
    def test_rounds_names_arguments_and_matching_outputs(self):
        first, second, third = (call("c1", "search", '{"query": "深塔 重置"}'),
                                call("c2", "web_search", '{"query": "tower", "kind": "general"}'),
                                call("c3", "fetch", {"id": "ptt:9"}))
        messages = [
            {"role": "system", "content": "你是 bot"}, {"role": "user", "content": "深塔多久重置？"},
            assistant_message("", [first, second]),
            # 回覆的順序和呼叫的順序相反：要靠 tool_call_id 對上，不能靠位置
            tool_message(second, json.dumps({"results": [{"url": "https://web.example/a"}]})),
            tool_message(first, json.dumps({"results": [hit("ptt:9")]})),
            assistant_message("我再看全文", [third]),
            tool_message(third, json.dumps({"id": "ptt:9", "url": "https://example.com/ptt/9", "text": "全文"})),
        ]

        calls = tool_calls_from_messages(messages)

        self.assertEqual([(c["round"], c["name"]) for c in calls], [(1, "search"), (1, "web_search"), (2, "fetch")])
        self.assertEqual(calls[0]["arguments"], {"query": "深塔 重置"})
        self.assertEqual(calls[0]["output"]["results"][0]["id"], "ptt:9")
        self.assertEqual(calls[1]["output"]["results"][0]["url"], "https://web.example/a")
        self.assertEqual(calls[2]["arguments"], {"id": "ptt:9"})

    def test_broken_arguments_and_missing_output_are_kept_not_dropped(self):
        broken = call("c1", "search", '{"query": ')
        calls = tool_calls_from_messages([assistant_message("", [broken])])

        self.assertEqual(len(calls), 1)
        self.assertIn("_raw", calls[0]["arguments"])
        self.assertEqual(calls[0]["output"], {})

    def test_no_tool_calls_means_an_empty_list(self):
        self.assertEqual(tool_calls_from_messages([{"role": "user", "content": "晚安"}]), [])


class ScoreQuestionTests(unittest.TestCase):
    def test_first_and_best_rank_are_separate(self):
        r = score_question(QUESTION, record(search("fb:1", "fb:2", "ptt:9"),
                                            search("article:7", "fb:3", query="深淵 重置 時間", round_no=2)))

        self.assertTrue(r.searched)
        self.assertEqual(r.queries, ["深塔 重置", "深淵 重置 時間"])
        self.assertEqual((r.first_rank, r.first_returned), (3, ["fb:1", "fb:2", "ptt:9"]))
        self.assertEqual((r.best_rank, r.best_returned), (1, ["article:7", "fb:3"]))
        self.assertEqual(r.tool_rounds, 2)

    def test_partial_answers_do_not_count(self):
        r = score_question(QUESTION, record(search("bahamut:5", "fb:1")))

        self.assertIsNone(r.first_rank)
        self.assertIsNone(r.best_rank)
        self.assertEqual(r.best_returned, ["bahamut:5", "fb:1"])

    def test_web_only_is_not_an_intel_search(self):
        web = {"round": 1, "name": "web_search", "arguments": {"query": "深塔"},
               "output": {"results": [{"url": "https://web.example/a"}]}}
        r = score_question(QUESTION, record(web))

        self.assertFalse(r.searched)
        self.assertEqual(r.tools_used, ["web_search"])
        self.assertIsNone(r.first_rank)
        self.assertEqual(r.queries, [])

    def test_failed_search_counts_as_searched_but_not_found(self):
        failed = {"round": 1, "name": "search", "arguments": {"query": "深塔"}, "output": {"error": "這次查不到"}}
        r = score_question(QUESTION, record(failed))

        self.assertTrue(r.searched)
        self.assertEqual(r.first_returned, [])
        self.assertIsNone(r.first_rank)

    def test_citing_the_relevant_document(self):
        reply = "深塔每兩週重置。\n來源：<https://example.com/ptt/9>"
        r = score_question(QUESTION, record(search("fb:1", "ptt:9"), reply=reply))

        self.assertEqual(r.reply_urls, ["https://example.com/ptt/9"])
        self.assertTrue(r.cited_relevant)
        self.assertEqual(r.unseen_urls, [])

    def test_citing_only_other_results_is_not_citing_the_answer(self):
        r = score_question(QUESTION, record(search("fb:1", "ptt:9"), reply="見 https://example.com/fb/1"))

        self.assertFalse(r.cited_relevant)
        self.assertEqual(r.unseen_urls, [])

    def test_links_that_were_never_in_a_tool_result_are_listed(self):
        reply = "見 https://example.com/fb/1 和 https://made-up.example/post/123"
        r = score_question(QUESTION, record(search("fb:1"), reply=reply))

        self.assertEqual(r.unseen_urls, ["https://made-up.example/post/123"])

    def test_links_copied_from_the_text_of_a_result_are_not_made_up(self):
        found = search("fb:1")
        found["output"]["results"][0]["snippet"] = "直播連結 https://youtu.be/abc123 當天放送"
        r = score_question(QUESTION, record(found, reply="直播在 <https://youtu.be/abc123>"))

        self.assertEqual(r.reply_urls, ["https://youtu.be/abc123"])
        self.assertEqual(r.unseen_urls, [])
        self.assertFalse(r.cited_relevant)

    def test_fetching_the_relevant_document(self):
        fetch = {"round": 2, "name": "fetch", "arguments": {"id": "article:7"},
                 "output": {"id": "article:7", "url": "https://example.com/article/7", "text": "全文"}}
        other = {"round": 2, "name": "fetch", "arguments": {"id": "fb:1"},
                 "output": {"id": "fb:1", "url": "https://example.com/fb/1", "text": "全文"}}

        self.assertTrue(score_question(QUESTION, record(search("fb:1"), fetch)).fetched_relevant)
        self.assertFalse(score_question(QUESTION, record(search("fb:1"), other)).fetched_relevant)
        # fetch 讀到的全文也算「模型看過的網址」，附了它就是附到正確答案
        cited = score_question(QUESTION, record(search("fb:1"), fetch, reply="見 https://example.com/article/7"))
        self.assertTrue(cited.cited_relevant)


class UrlTests(unittest.TestCase):
    def test_only_the_url_itself_is_taken(self):
        text = ("官方公告 <https://a.example/x?id=1&p=2>，另見 [巴哈](https://b.example/C.php?bsn=1&snA=2)。"
                "還有 https://c.example/post。再貼一次 https://a.example/x?id=1&p=2")

        self.assertEqual(urls_in(text), ["https://a.example/x?id=1&p=2", "https://b.example/C.php?bsn=1&snA=2",
                                         "https://c.example/post"])

    def test_no_urls(self):
        self.assertEqual(urls_in(""), [])
        self.assertEqual(urls_in("查不到相關資料"), [])


class SummaryTests(unittest.TestCase):
    def setUp(self):
        self.questions = [dict(QUESTION, qid=f"q{i:02d}") for i in range(1, 5)]
        self.records = [
            # q01：第一次就排第 1，附了正確答案
            dict(record(search("ptt:9"), reply="見 https://example.com/ptt/9"), qid="q01"),
            # q02：第一次沒找到，第二次排第 2
            dict(record(search("fb:1"), search("fb:2", "article:7", query="換個說法", round_no=2)), qid="q02"),
            # q03：只查網路
            dict(record({"round": 1, "name": "web_search", "arguments": {"query": "x"},
                         "output": {"results": [{"url": "https://web.example/a"}]}},
                        reply="見 https://nowhere.example/z"), qid="q03"),
            # q04：完全沒查
            dict(record(reply="我記得是兩週"), qid="q04"),
        ]

    def test_unsearched_questions_count_as_misses(self):
        s = summarize_agent([score_question(q, r) for q, r in zip(self.questions, self.records)])

        self.assertEqual((s["n"], s["searched"], s["web_only"], s["no_tool"]), (4, 2, 1, 1))
        # 和搜尋評估同一份算法：第一次 search 名次是 1、沒找到、沒查、沒查
        self.assertAlmostEqual(s["first_search"]["hit@5"], 1 / 4)
        self.assertAlmostEqual(s["first_search"]["mrr@10"], 1 / 4)
        # 任一次 search：名次 1、2
        self.assertAlmostEqual(s["any_search"]["hit@5"], 2 / 4)
        self.assertAlmostEqual(s["any_search"]["mrr@10"], (1 + 1 / 2) / 4)
        # 只算有查的兩題
        self.assertEqual(s["first_search_when_searched"]["n"], 2)
        self.assertAlmostEqual(s["first_search_when_searched"]["hit@5"], 1 / 2)

    def test_citation_counts(self):
        s = summarize_agent([score_question(q, r) for q, r in zip(self.questions, self.records)])

        self.assertEqual(s["cited_any"], 2)                     # q01、q03 有附連結
        self.assertEqual(s["cited_relevant"], 1)                # 只有 q01 附到正確答案
        self.assertEqual(s["replies_with_unseen_urls"], 1)      # q03 的連結不在任何工具結果裡
        self.assertEqual(s["tool_rounds"], {"0": 1, "1": 2, "2": 1})

    def test_errors_are_counted(self):
        failed = dict(record(), qid="q01", error_kind="timeout")
        s = summarize_agent([score_question(self.questions[0], failed)])

        self.assertEqual(s["errors"], 1)

    def test_controls_that_used_tools_are_reported(self):
        quiet = {"qid": "c01", "question": "晚安", "tool_calls": []}
        noisy = {"qid": "c02", "question": "講個笑話", "tool_calls": [
            {"round": 1, "name": "web_search", "arguments": {"query": "笑話"}, "output": {"results": []}}]}

        c = summarize_controls([quiet, noisy])

        self.assertEqual((c["n"], c["used_tools"]), (2, 1))
        self.assertEqual(c["which"], [{"question": "講個笑話", "tools": ["web_search"]}])

    def test_report_queries_replay_through_the_search_evaluation(self):
        report = build_report(self.questions, self.records, [])

        self.assertEqual(report["queries"], {"q01": "深塔 重置", "q02": "深塔 重置", "q03": "", "q04": ""})
        self.assertEqual(report["by_category"]["情報"]["n"], 4)
        self.assertNotIn("攻略", report["by_category"])
        # 報告要能公開：不含回答全文
        self.assertNotIn("我記得是兩週", json.dumps(report, ensure_ascii=False))

    def test_report_file_is_accepted_as_a_keyword_file(self):
        import tempfile
        from pathlib import Path

        report = build_report(self.questions, self.records, [])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.json"
            path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(load_keyword_queries(path)["q02"], "深塔 重置")

    def test_questions_without_a_record_are_left_out(self):
        report = build_report(self.questions, self.records[:1], [])

        self.assertEqual(report["summary"]["n"], 1)
        self.assertEqual([r["qid"] for r in report["results"]], ["q01"])


if __name__ == "__main__":
    unittest.main()
