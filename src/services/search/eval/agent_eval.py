"""Agent 評估的算分：正式模型跑完整的 /askai 工具輪之後，從每題的經過算「模型實際用起來」的分數。

和 `evaluate.py` 的差別：那邊量搜尋本身（查詢字是群友原句，或外部 agent 改寫的關鍵字）；這裡量的是
  - 該查的題目有沒有查、查的是遊戲情報還是網路
  - 模型自己寫的查詢找不找得到（名次看它實際看到的那幾筆，Hit／MRR 的算法沿用 `evaluate.py`）
  - 回答附的連結是不是它查到的、有沒有附到正確答案那一篇
  - 不該查的閒聊有沒有亂查

這個檔只算分，不碰模型也不碰索引；跑題目的是 `test/integration/it_askai_agent_eval.py`（要真的模型與
search-mcp）。回答內容對不對要人看，不在這裡算。

每題的經過（`record`）長這樣，由跑題目的那支腳本從模型實際收到的訊息整理出來：
    {"qid", "question", "reply", "error_kind", "elapsed_s",
     "tool_calls": [{"round": 1, "name": "search", "arguments": {...}, "output": {...}}, ...]}
`output` 是模型實際看到的工具結果（search 是 `{"results": [{"id", "url", ...}]}`，失敗是 `{"error": ...}`）。
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from statistics import median
from typing import Any, Iterable, Optional

from llm.client.tool_calls import ToolArgumentError, call_name_and_arguments, parse_arguments
from services.search.eval.evaluate import QuestionResult, first_relevant_rank, summarize

#: 遊戲情報的搜尋工具（search-mcp 的工具名稱）
INTEL_SEARCH = "search"
INTEL_FETCH = "fetch"

_URL = re.compile(r"https?://[^\s<>\"'）」』】，。、；]+")
#: 網址後面常黏著的標點（Markdown 的右括號、句尾符號）不算網址的一部分
_URL_TRAILING = ".,;:!?)]*_~"


@dataclass(frozen=True)
class AgentQuestionResult:
    qid: str
    question: str
    category: str
    origin: str
    type: str
    relevant: list[str]
    tools_used: list[str]              # 照呼叫順序的工具名稱
    tool_rounds: int                   # 查了幾輪（一輪可以同時叫好幾個工具）
    searched: bool                     # 有沒有查遊戲情報（search 至少一次）
    queries: list[str]                 # 每次 search 模型自己寫的查詢字
    first_returned: list[str]          # 第一次 search 模型看到的文件 id
    first_rank: Optional[int]          # 第一次 search 裡，第一篇正確答案排第幾；沒查或沒找到是 None
    best_returned: list[str]           # 名次最好的那次 search 看到的文件 id
    best_rank: Optional[int]           # 任一次 search 裡最好的名次
    fetched_relevant: bool             # 有沒有用 fetch 讀到正確答案的全文
    reply_urls: list[str]              # 回答裡的網址
    cited_relevant: bool               # 回答有沒有附到正確答案那一篇的網址
    unseen_urls: list[str]             # 回答裡的網址，工具結果的網址欄位與內文都沒出現過的（模型自己生的）
    error_kind: Optional[str]
    elapsed_s: float


def tool_calls_from_messages(messages: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """模型實際收到的對話（`GenerateReplyResult.messages_sent`）→ 每個工具呼叫：第幾輪、名稱、模型給的參數、
    它看到的結果。參數是模型自己寫的原樣（客戶端代補的原句不算），壞掉的 JSON 留原文不丟掉。"""
    messages = list(messages)
    outputs = {m.get("tool_call_id"): m.get("content") for m in messages if m.get("role") == "tool"}
    calls: list[dict[str, Any]] = []
    round_no = 0
    for message in messages:
        if message.get("role") != "assistant" or not message.get("tool_calls"):
            continue
        round_no += 1
        for call in message["tool_calls"]:
            name, raw = call_name_and_arguments(call)
            try:
                arguments = parse_arguments(raw)
            except ToolArgumentError:
                arguments = {"_raw": str(raw)}
            calls.append({"round": round_no, "name": name, "arguments": arguments,
                          "output": _parse_output(outputs.get(call.get("id")))})
    return calls


def _parse_output(content: Any) -> dict[str, Any]:
    if isinstance(content, dict):
        return content
    try:
        parsed = json.loads(content or "{}")
    except (TypeError, json.JSONDecodeError):
        return {"_raw": str(content)}
    return parsed if isinstance(parsed, dict) else {"_raw": str(content)}


def urls_in(text: str) -> list[str]:
    """文字裡的網址，照出現順序、不重複。Discord 的 `<網址>` 與 Markdown 的 `(網址)` 都只取網址本身。"""
    found = [match.group(0).rstrip(_URL_TRAILING) for match in _URL.finditer(text or "")]
    return list(dict.fromkeys(found))


def _documents(output: Any) -> Iterable[dict[str, Any]]:
    """一個工具結果裡的文件：search／web_search 是 `results` 清單，fetch 是結果本身。"""
    if not isinstance(output, dict):
        return []
    results = output.get("results")
    if isinstance(results, list):
        return [hit for hit in results if isinstance(hit, dict)]
    return [output] if output.get("url") else []


def _search_ids(call: dict[str, Any]) -> list[str]:
    return [str(doc["id"]) for doc in _documents(call.get("output")) if doc.get("id")]


def score_question(question: dict[str, Any], record: dict[str, Any]) -> AgentQuestionResult:
    """一題的經過 → 這題的分數。名次看模型實際看到的結果；「只答一半」的文件不算（和 `evaluate.py` 一樣）。"""
    relevant = list(question["relevant"])
    calls = list(record.get("tool_calls") or [])
    searches = [call for call in calls if call.get("name") == INTEL_SEARCH]
    ranked = [(first_relevant_rank(_search_ids(call), relevant), _search_ids(call)) for call in searches]
    found = [(rank, ids) for rank, ids in ranked if rank is not None]
    best_rank, best_returned = min(found, key=lambda item: item[0]) if found else (None, ranked[0][1] if ranked else [])

    seen_urls: set[str] = set()
    relevant_urls: set[str] = set()
    for call in calls:
        for doc in _documents(call.get("output")):
            url = str(doc.get("url") or "")
            if not url:
                continue
            seen_urls.add(url)
            if str(doc.get("id") or "") in relevant:
                relevant_urls.add(url)
    # 公告、貼文的內文裡也有網址（例：直播連結）：模型照著內文附上不算自己生的
    seen_text = "\n".join(json.dumps(call.get("output"), ensure_ascii=False) for call in calls)
    reply_urls = urls_in(record.get("reply") or "")
    fetched = {str((call.get("output") or {}).get("id") or "") for call in calls
               if call.get("name") == INTEL_FETCH and isinstance(call.get("output"), dict)}
    return AgentQuestionResult(
        qid=question["qid"], question=question["question"], category=question.get("category", "情報"),
        origin=question.get("origin", ""), type=question.get("type", ""), relevant=relevant,
        tools_used=[str(call.get("name") or "") for call in calls],
        tool_rounds=len({call.get("round") for call in calls}),
        searched=bool(searches),
        queries=[str((call.get("arguments") or {}).get("query") or "") for call in searches],
        first_returned=ranked[0][1] if ranked else [], first_rank=ranked[0][0] if ranked else None,
        best_returned=best_returned, best_rank=best_rank,
        fetched_relevant=bool(fetched & set(relevant)),
        reply_urls=reply_urls, cited_relevant=bool(relevant_urls & set(reply_urls)),
        unseen_urls=[url for url in reply_urls if url not in seen_urls and url not in seen_text],
        error_kind=record.get("error_kind"), elapsed_s=float(record.get("elapsed_s") or 0.0),
    )


def _as_search_result(r: AgentQuestionResult, *, rank: Optional[int], returned: list[str]) -> QuestionResult:
    """換成 `evaluate.py` 的格式，Hit／MRR 才用同一份算法。沒查的題目名次是 None，算沒找到。"""
    return QuestionResult(qid=r.qid, question=r.question, query=r.queries[0] if r.queries else "",
                          category=r.category, origin=r.origin, type=r.type, rank=rank, vector_covered=None,
                          returned=returned, relevant=r.relevant, elapsed_ms=round(r.elapsed_s * 1000, 1))


def summarize_agent(results: list[AgentQuestionResult]) -> dict[str, Any]:
    """整份考卷的分數。Hit／MRR 的分母是全部題目：該查卻沒查的題目算沒找到（那也是模型實際用起來的結果）。"""
    n = len(results)
    if n == 0:
        return {"n": 0}
    first = [_as_search_result(r, rank=r.first_rank, returned=r.first_returned) for r in results]
    best = [_as_search_result(r, rank=r.best_rank, returned=r.best_returned) for r in results]
    searched = [r for r in results if r.searched]
    answered = [r for r in results if not r.error_kind]
    with_urls = [r for r in results if r.reply_urls]
    return {
        "n": n,
        "searched": len(searched),
        "web_only": sum(1 for r in results if not r.searched and r.tools_used),
        "no_tool": sum(1 for r in results if not r.tools_used),
        "errors": n - len(answered),
        "first_search": summarize(first),
        "any_search": summarize(best),
        # 只看有查的題目：分開「沒查」和「查了但查詢字寫不好」
        "first_search_when_searched": summarize([x for x, r in zip(first, results) if r.searched]),
        "fetched_relevant": sum(1 for r in results if r.fetched_relevant),
        "cited_any": len(with_urls),
        "cited_relevant": sum(1 for r in results if r.cited_relevant),
        "replies_with_unseen_urls": sum(1 for r in results if r.unseen_urls),
        "tool_rounds": {str(k): sum(1 for r in results if r.tool_rounds == k)
                        for k in sorted({r.tool_rounds for r in results})},
        "elapsed_s_median": round(median(r.elapsed_s for r in results), 1),
        "elapsed_s_max": round(max(r.elapsed_s for r in results), 1),
    }


def summarize_controls(records: list[dict[str, Any]]) -> dict[str, Any]:
    """不該查的題目（閒聊）：有幾題還是叫了工具、叫了什麼。"""
    used = [{"question": record.get("question"),
             "tools": [str(call.get("name") or "") for call in record.get("tool_calls") or []]}
            for record in records if record.get("tool_calls")]
    return {"n": len(records), "used_tools": len(used), "which": used}


def first_queries(results: list[AgentQuestionResult]) -> dict[str, str]:
    """題號 → 模型第一次 search 寫的查詢字，格式同 `keyword_queries.json` 的 `queries`：
    可以原封不動交給 `python -m services.search.eval.evaluate --mode 關鍵字 --keywords <報告檔>` 重放，
    和外部 agent 改寫的那一份用同一把尺比。沒查的題目給空字串（搜尋回空的，算沒找到）。"""
    return {r.qid: (r.queries[0] if r.queries else "") for r in results}


def build_report(questions: list[dict[str, Any]], records: list[dict[str, Any]],
                 controls: list[dict[str, Any]]) -> dict[str, Any]:
    """考卷＋每題的經過 → 可以公開的報告內容（分數、查詢字、文件 id；不含回答與論壇原文）。"""
    by_qid = {record["qid"]: record for record in records}
    results = [score_question(q, by_qid[q["qid"]]) for q in questions if q["qid"] in by_qid]
    groups = {
        "情報": [r for r in results if r.category == "情報"],
        "攻略": [r for r in results if r.category.startswith("攻略")],
    }
    return {
        "summary": summarize_agent(results),
        "by_category": {name: summarize_agent(items) for name, items in groups.items() if items},
        "controls": summarize_controls(controls),
        "queries": first_queries(results),
        "results": [asdict(r) for r in results],
    }
