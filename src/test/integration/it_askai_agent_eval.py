"""Agent 評估：拿搜尋考卷（42 題）加幾題不該查的閒聊，用真的模型跑完整的 /askai 工具輪，量「模型實際用起來」的結果。

和 `python -m services.search.eval.evaluate` 的差別：那邊的查詢字是群友原句或外部 agent 改寫的關鍵字，量的是搜尋本身；
這裡的查詢字是正式模型自己寫的，還會量該查的有沒有查、回答附的連結對不對、閒聊有沒有亂查。
走的路和 `it_askai_intel` 同一條（`answer`）：/askai 工具模式，沒有聊天紀錄與人物卡；每題只跑一次。

會呼叫主模型（每題約 1～2 分鐘，全部約 1 小時，排同一把 GPU 鎖），不要在 04:00～07:30 維護時段跑。

執行（容器內）：
    docker exec -w /app discord-bot python -m test.integration.it_askai_agent_eval --label Agent評估
    docker exec -w /app discord-bot python -m test.integration.it_askai_agent_eval --limit 2 --label 試跑
    … --resume services/search/eval/private/<檔名>-經過.jsonl     # 中斷後接著跑（跑過的題目跳過）
    … --score-only services/search/eval/private/<檔名>-經過.jsonl # 不跑模型，只重算分數

輸出：
  - 每題的經過（回答全文、模型看到的工具結果）：`services/search/eval/private/<時間>-<名稱>-經過.jsonl`
    ——含論壇原文，不進 git；一題跑完就寫一行，中斷不會白跑
  - 報告（分數、模型寫的查詢字、文件 id）：`services/search/eval/reports/<時間>-<名稱>.json`
    報告裡的 `queries` 可以直接交給搜尋評估重放，和外部 agent 改寫的那一份用同一把尺比：
        docker exec -w /app search-mcp python -m services.search.eval.evaluate --mode 關鍵字 --rerank on \\
            --keywords services/search/eval/reports/<報告檔> --label Agent-模型自己寫的查詢
回答內容對不對要人看（對照 `services/search/eval/private/questions_with_evidence.json` 的證據句），這支腳本不判。
"""
import argparse
import asyncio
import json
import time
from datetime import datetime
from pathlib import Path

from commands.llm_commands import INTEL_SETTINGS
from services.llm_service import LLMService
from services.search.eval.agent_eval import build_report, tool_calls_from_messages
from services.search.eval.evaluate import DEFAULT_QUESTIONS, EVAL_DIR, HIT_KS, MRR_K, load_questions
from sys_settings.time_settings import APP_TZ
from test.integration.it_askai_intel import answer

#: 不該查的題目：純閒聊，沒有要查的事實
NO_SEARCH_QUESTIONS = [
    "今天好累喔，你今天過得怎樣？",
    "幫我想一個好笑的隊伍名字",
    "你覺得早起好還是熬夜好？",
    "講一個冷笑話",
    "1 加 1 等於多少？",
    "謝謝你，晚安",
]

PRIVATE_DIR = EVAL_DIR / "private"
REPORT_DIR = EVAL_DIR / "reports"
_SUFFIX = "-經過.jsonl"


async def ask_one(service: LLMService, qid: str, question: str, kind: str, limit: float) -> dict:
    started = time.monotonic()
    record: dict = {"qid": qid, "kind": kind, "question": question}
    try:
        # 一題的時間上限：模型偶爾會寫個不停（2026-10-12 有一題的最後一次回答跑了 14 分鐘還沒停），那段時間
        # 顯示卡被這個行程佔著，bot 自己的工作只能等。超過就中止這一題（連線一斷後端就停），記成逾時
        result, meta, web = await asyncio.wait_for(answer(service, question, trace_id=f"agent-eval-{qid}"), limit)
    except Exception as exc:  # 一題出錯或逾時不讓整份考卷中斷；照實記下來
        record.update(reply="", error_kind=f"exception:{type(exc).__name__}", error=str(exc)[:300], tool_calls=[])
    else:
        record.update(
            reply=result.reply, error_kind=result.error_kind, connected=meta.get("connected"),
            tool_calls=tool_calls_from_messages(result.messages_sent),
            # 每次呼叫花多久、有沒有出錯（客戶端記的；和 tool_calls 同順序但欄位較少）
            intel_calls=meta.get("calls") or [], web_calls=web.calls,
        )
    record["elapsed_s"] = round(time.monotonic() - started, 1)
    return record


def _progress(record: dict) -> str:
    calls = record.get("tool_calls") or []
    names = [call["name"] for call in calls]
    used = "、".join(f"{name}×{names.count(name)}" for name in dict.fromkeys(names)) or "沒查"
    queries = [str(call["arguments"].get("query") or "") for call in calls if call["name"] == "search"]
    extra = f"，錯誤 {record['error_kind']}" if record.get("error_kind") else ""
    return f"{record['qid']} {record['elapsed_s']:>6.1f} 秒  {used}  {queries[:2]}{extra}"


async def run(items: list[tuple[str, str, str]], out_path: Path, done: set[str], limit: float) -> None:
    service = LLMService()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    todo = [item for item in items if item[0] not in done]
    # 獨立行程、一題才寫一行：直接寫檔，不必丟執行緒
    with out_path.open("a", encoding="utf-8") as fh:
        for position, (qid, question, kind) in enumerate(todo, 1):
            record = await ask_one(service, qid, question, kind, limit)
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            fh.flush()
            print(f"[{position}/{len(todo)}] {_progress(record)}", flush=True)


def load_records(path: Path) -> list[dict]:
    """同一題出現兩次（中斷後重跑）時用後面那一筆。"""
    records: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            records[record["qid"]] = record
    return list(records.values())


def _print_summary(report: dict) -> None:
    s = report["summary"]
    if not s.get("n"):
        print("沒有可以算分的題目")
        return

    def line(title: str, block: dict) -> str:
        return (f"{title}（{block['n']} 題）：" + "、".join(f"Hit@{k} {block[f'hit@{k}']:.0%}" for k in HIT_KS)
                + f"、MRR@{MRR_K} {block[f'mrr@{MRR_K}']:.3f}")

    print("=" * 70)
    print(f"考卷 {s['n']} 題：有查遊戲情報 {s['searched']} 題、只查網路 {s['web_only']} 題、"
          f"完全沒查 {s['no_tool']} 題、出錯 {s['errors']} 題")
    print(line("第一次 search", s["first_search"]))
    print(line("任一次 search", s["any_search"]))
    print(line("第一次 search，只算有查的題目", s["first_search_when_searched"]))
    for name, block in report["by_category"].items():
        print(f"  {name} {block['n']} 題：有查 {block['searched']}、第一次 Hit@5 {block['first_search']['hit@5']:.0%}、"
              f"任一次 Hit@5 {block['any_search']['hit@5']:.0%}")
    print(f"回答：有附連結 {s['cited_any']} 題、附到正確答案那篇 {s['cited_relevant']} 題、"
          f"附了不在查詢結果裡的連結 {s['replies_with_unseen_urls']} 題；用 fetch 讀到正確答案 {s['fetched_relevant']} 題")
    print(f"查了幾輪（輪數: 題數）：{s['tool_rounds']}；每題中位數 {s['elapsed_s_median']} 秒、最久 {s['elapsed_s_max']} 秒")
    c = report["controls"]
    print(f"閒聊 {c['n']} 題：叫了工具的有 {c['used_tools']} 題 {c['which'] or ''}")


def main(argv: list[str] | None = None) -> Path:
    parser = argparse.ArgumentParser(description="用真的模型跑完整的 /askai 工具輪，量模型實際用起來的結果")
    parser.add_argument("--label", default="Agent評估", help="這次評估的名稱，會寫進報告與檔名")
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    parser.add_argument("--limit", type=int, default=None, help="只跑考卷前幾題、閒聊前 1 題（試跑用）")
    parser.add_argument("--resume", type=Path, default=None, help="接著這份經過檔繼續跑（跑過的題目跳過）")
    parser.add_argument("--score-only", type=Path, default=None, help="不跑模型，只拿這份經過檔重算分數")
    parser.add_argument("--question-timeout", type=float, default=600.0,
                        help="一題最多跑幾秒，超過就中止這一題、記成逾時（要比 bot 等顯示卡的放行上限 15 分鐘短）")
    args = parser.parse_args(argv)

    questions = load_questions(args.questions)
    controls = [(f"c{i:02d}", text) for i, text in enumerate(NO_SEARCH_QUESTIONS, 1)]
    if args.limit is not None:
        questions, controls = questions[:args.limit], controls[:1]

    existing = args.score_only or args.resume
    if existing is not None:
        out_path = existing
        stem = existing.name.removesuffix(_SUFFIX)
    else:
        stem = f"{datetime.now(APP_TZ):%Y%m%d-%H%M}-{args.label}"
        out_path = PRIVATE_DIR / f"{stem}{_SUFFIX}"

    if args.score_only is None:
        done = {record["qid"] for record in load_records(out_path)} if out_path.exists() else set()
        items = [(q["qid"], q["question"], "考卷") for q in questions] + [(qid, text, "閒聊") for qid, text in controls]
        asyncio.run(run(items, out_path, done, args.question_timeout))

    records = load_records(out_path)
    report = build_report(questions, [r for r in records if r["kind"] == "考卷"],
                          [r for r in records if r["kind"] == "閒聊"])
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / f"{stem}.json"
    report_path.write_text(json.dumps({
        "label": args.label, "when": datetime.now(APP_TZ).isoformat(),
        "settings": {
            "path": "/askai 工具模式（遊戲情報＋網路搜尋），沒有聊天紀錄與人物卡；每題跑一次",
            "search_limit": INTEL_SETTINGS.search_limit, "max_tool_rounds": INTEL_SETTINGS.max_tool_rounds,
            "note": f"名次看模型實際看到的前 {INTEL_SETTINGS.search_limit} 筆；要和搜尋評估（前 20 筆）用同一把尺比，"
                    "把這份報告當 --keywords 重放",
        },
        **report,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    _print_summary(report)
    print(f"經過（不進 git）：{out_path}")
    print(f"報告：{report_path}")
    return report_path


if __name__ == "__main__":
    main()
