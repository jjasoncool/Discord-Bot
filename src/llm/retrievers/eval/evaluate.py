"""聊天檢索的評估：拿考卷考 `search_chat`（全庫、不限頻道），算 Hit@1／5／25 與名次中位數，報告寫成 JSON。

架構定位：服務層（`llm/retrievers`）的手動工具，不在 bot 行程裡跑。上層：沒有程式呼叫；在 discord-bot 容器裡
`python -m llm.retrievers.eval.evaluate --label 名稱`。下層：`context_retriever.embed_query`／`search_chat`（和 /askai、
插話同一條查詢路徑，含索引形狀的開關與 ef_search）、`llm.client.lemonade_gate.gpu_exclusive_sync`（算問句向量時排一次
GPU 的隊）、`llm.preprocess.tokenization.dedup_key`（口頭禪題比對句子）。

介面：
- `load_questions(path)`：讀考卷；沒有答案的題目直接報錯。
- `evaluate(questions, *, limit, collapse, embedding_column, embeddings)`：每題一次 `search_chat`，回 `QuestionResult` 清單。
- `embed_questions(questions)`：整份考卷的問句向量一次算完（拿 GPU 閘門一次）。
- `summarize(results)`／`by_category(results)`：Hit@k（題數）、名次中位數、耗時中位數；分類別各算一份。
- `write_report(results, label=, settings=)`：寫 `reports/<時間>-<名稱>.json`，回路徑。

規則：
- 考卷 `private/questions.json` 與報告 `reports/` 都不進 git：題目本身就是群友的聊天內容（口頭禪、習慣、作者 id），
  repo 有公開鏡像。考卷的格式照情報搜尋的評估（`services/search/eval`）：qid、question、category、relevant
  （`chat:<message_id>`）；口頭禪題改給 `author`＋`phrase`，答案是「那個人說過含那句話的任一則」（標點、空白不計）。
- 只讀資料庫。預設不折疊、top-25：量的是檢索本身；要看 /askai 實際拿到的名額再開 `--collapse`。
- 結論與數字記在交接檔「聊天檢索（RAG）」區塊，報告檔只留原始資料（每題名次、回了哪些 message_id）。

例外與決策：關掉 HNSW 的精確掃描要在 `search_chat` 的交易裡 SET LOCAL，這支不做；要量精確召回用交接檔記的 SQL。
"""
from __future__ import annotations

import argparse
import json
import logging
import statistics
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from llm.client.lemonade_gate import gpu_exclusive_sync
from llm.preprocess.tokenization import dedup_key
from llm.retrievers import context_retriever
from sys_settings import switches
from sys_settings.time_settings import APP_TZ

logger = logging.getLogger(__name__)

#: 考卷與報告和這支程式放在同一個資料夾（兩個子資料夾都在 .gitignore）
EVAL_DIR = Path(__file__).resolve().parent
DEFAULT_QUESTIONS = EVAL_DIR / "private" / "questions.json"
REPORTS_DIR = EVAL_DIR / "reports"
HIT_KS = (1, 5, 25)
DEFAULT_LIMIT = 25
#: 算整份考卷的問句向量最多等 GPU 幾秒（維護時段的人格萃取可能佔著）
EMBED_GATE_WAIT_SECONDS = 600.0


@dataclass(frozen=True)
class QuestionResult:
    qid: str
    question: str
    category: str
    rank: Optional[int]          # 第一則正確答案排第幾（從 1 開始）；沒出現在結果裡是 None
    returned: list[str]          # 回傳的 message_id，照名次
    elapsed_ms: float


def load_questions(path: Path | str = DEFAULT_QUESTIONS) -> list[dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    questions = data["questions"] if isinstance(data, dict) else data
    for q in questions:
        if not q.get("relevant") and not (q.get("author") and q.get("phrase")):
            raise ValueError(f"題目 {q.get('qid')!r} 沒有答案：要給 relevant（chat:<message_id>）或 author＋phrase")
    return list(questions)


def rank_of(rows: list[dict[str, Any]], question: dict[str, Any]) -> Optional[int]:
    """第一則正確答案的名次。relevant 比 message_id；口頭禪題比「同一個作者、句子包含那句話」（`dedup_key` 後比對）。"""
    wanted = {str(x).removeprefix("chat:") for x in question.get("relevant") or []}
    author = str(question.get("author") or "")
    phrase = dedup_key(str(question.get("phrase") or ""))
    for position, row in enumerate(rows, 1):
        if row["message_id"] in wanted:
            return position
        if author and phrase and row.get("author_id") == author and phrase in dedup_key(row.get("text") or ""):
            return position
    return None


def embed_questions(questions: list[dict[str, Any]], *, max_wait_seconds: float = EMBED_GATE_WAIT_SECONDS) -> dict[str, list[float]]:
    """整份考卷的問句向量一次算完：只排一次 GPU 的隊，之後逐題查都不再碰模型。算不出來的題目不放進結果（那題會回空）。"""
    embeddings: dict[str, list[float]] = {}
    with gpu_exclusive_sync(max_wait_seconds=max_wait_seconds):
        for q in questions:
            vector = context_retriever.embed_query(q["question"], logger)
            if vector:
                embeddings[q["qid"]] = vector
    return embeddings


def evaluate(questions: list[dict[str, Any]], *, limit: int = DEFAULT_LIMIT, collapse: bool = False,
             embedding_column: str = "embedding", embeddings: Optional[dict[str, list[float]]] = None) -> list[QuestionResult]:
    """每題跑一次 `search_chat`（全庫、不限頻道）。`embeddings` 沒給就先一次算完。"""
    if embeddings is None:
        embeddings = embed_questions(questions)
    results = []
    for q in questions:
        started = time.perf_counter()
        rows = context_retriever.search_chat(
            question=q["question"], limit=limit, logger=logger, return_meta=True, collapse=collapse,
            embedding_column=embedding_column, query_embedding=embeddings.get(q["qid"]),
        )
        elapsed = (time.perf_counter() - started) * 1000
        results.append(QuestionResult(
            qid=str(q["qid"]), question=q["question"], category=str(q.get("category") or ""),
            rank=rank_of(rows, q), returned=[row["message_id"] for row in rows], elapsed_ms=round(elapsed, 1),
        ))
    return results


def summarize(results: list[QuestionResult]) -> dict[str, Any]:
    """Hit@k 是「前 k 名有正確答案」的題數（不是比例：考卷才幾十題，題數比百分比好讀）。"""
    ranks = [r.rank for r in results if r.rank is not None]
    median = statistics.median(ranks) if ranks else None
    if median is not None and float(median).is_integer():
        median = int(median)
    return {
        "n": len(results),
        **{f"hit@{k}": sum(1 for r in results if r.rank is not None and r.rank <= k) for k in HIT_KS},
        "median_rank": median,
        "median_ms": round(statistics.median(r.elapsed_ms for r in results), 1) if results else None,
    }


def by_category(results: list[QuestionResult]) -> dict[str, dict[str, Any]]:
    categories = sorted({r.category for r in results})
    return {c: summarize([r for r in results if r.category == c]) for c in categories}


def format_table(results: list[QuestionResult]) -> str:
    rows = [f"{'類別':4} {'題數':>3} {'Hit@1':>5} {'Hit@5':>5} {'Hit@25':>6} {'名次中位':>6} {'耗時中位ms':>8}"]
    for name, s in list(by_category(results).items()) + [("all", summarize(results))]:
        rows.append(f"{name:4} {s['n']:>3} {s['hit@1']:>5} {s['hit@5']:>5} {s['hit@25']:>6} "
                    f"{str(s['median_rank'] if s['median_rank'] is not None else '-'):>6} {str(s['median_ms']):>8}")
    return "\n".join(rows)


def write_report(results: list[QuestionResult], *, label: str, settings: dict[str, Any]) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(APP_TZ)
    path = REPORTS_DIR / f"{now.strftime('%Y%m%d-%H%M')}-{label}.json"
    payload = {
        "label": label, "time": now.isoformat(timespec="seconds"), "settings": settings,
        "summary": summarize(results), "by_category": by_category(results),
        "questions": [asdict(r) for r in results],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="拿考卷考 search_chat（全庫），算 Hit@k 與名次中位數")
    parser.add_argument("--label", required=True, help="報告檔名的一部分（例：h512基準線）")
    parser.add_argument("--questions", default=str(DEFAULT_QUESTIONS))
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--collapse", action="store_true", help="同一人同一句折成一則（/askai 實際拿到的名額）")
    parser.add_argument("--column", default="embedding", help="查哪個向量欄（重算期間對影子欄比對用）")
    parser.add_argument("--only", default="", help="只考這些類別，逗號分隔（例：C,D）")
    parser.add_argument("--no-report", action="store_true", help="只印表格、不寫報告檔")
    args = parser.parse_args(argv)
    # 手動工具：結果直接印到畫面（和情報搜尋的評估一樣走 logger，不用 print）；其他模組只印 WARNING，
    # 免得 HTTP 客戶端每算一題向量就印一行
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    logger.setLevel(logging.INFO)

    questions = load_questions(args.questions)
    if args.only:
        wanted = {c.strip() for c in args.only.split(",") if c.strip()}
        questions = [q for q in questions if str(q.get("category") or "") in wanted]
    settings = {"chat_vector_index": switches.current().chat_vector_index, "embedding_column": args.column,
                "limit": args.limit, "collapse": args.collapse, "questions": len(questions)}
    started = time.monotonic()
    results = evaluate(questions, limit=args.limit, collapse=args.collapse, embedding_column=args.column)
    logger.info("%d 題，%.0f 秒；設定 %s\n\n%s", len(results), time.monotonic() - started, settings, format_table(results))
    misses = [r for r in results if r.rank is None or r.rank > 5]
    if misses:
        lines = [f"  {str(r.rank) if r.rank is not None else '-':>3}  {r.qid}  {r.question}" for r in misses]
        logger.info("\n前 5 名外的題目：\n%s", "\n".join(lines))
    if not args.no_report:
        logger.info("\n報告：%s", write_report(results, label=args.label, settings=settings))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
