"""搜尋評估：拿考卷（`eval/questions.json`）考搜尋，算 Hit Rate@k、MRR@10、Recall@10、nDCG@10。

用法（容器裡）：`python -m services.search.evaluate --label 基準線`
報告寫到 `services/search/eval/reports/<時間>-<名稱>.json`（設定、各模式的分數、每題正確答案排第幾、
搜尋回了哪些文件）；表格只印到畫面。結論與數字記在 `AI_HANDOFF_AND_TODO.md` 的 `mcp-search-tools` 區塊，
不另存 Markdown 報告（使用者 2026-10-08：markdown 收成一份就好）。

兩種模式（預設兩種都考）：
  - 原句：群友怎麼問就怎麼搜，整句丟進去——沒有人幫忙改寫時，搜尋本身找不找得到
  - 關鍵字：用 `eval/keyword_queries.json` 裡的關鍵字搜——模擬呼叫搜尋的 LLM 先把問題改寫成關鍵字，
    並附上原句（MCP `search` 的 `question`，只給重新排序用；2026-10-08 起，之前的報告重排用的是關鍵字）
排名看的是搜尋實際回傳的那一串（含每種來源的筆數上限），也就是模型真正會看到的結果。
「只答一半」的文件不算命中（考卷的 `partial`）。
"""
from __future__ import annotations

import argparse
import json
import math
import logging
import time
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from services.search.index import SearchIndex
from services.search.text import normalizer_id
from sys_settings.time_settings import APP_TZ

logger = logging.getLogger(__name__)

EVAL_DIR = Path(__file__).resolve().parent / "eval"
DEFAULT_QUESTIONS = EVAL_DIR / "questions.json"
DEFAULT_KEYWORDS = EVAL_DIR / "keyword_queries.json"
MODES = ("原句", "關鍵字")
HIT_KS = (1, 5, 10)
MRR_K = 10
#: Recall@k 與 nDCG@k 的 k
LIST_K = 10


@dataclass(frozen=True)
class QuestionResult:
    qid: str
    question: str
    query: str                   # 實際送進搜尋的字串（原句模式＝question）
    category: str
    origin: str
    type: str
    rank: Optional[int]          # 第一篇正確答案排第幾（從 1 開始）；沒出現在結果裡是 None
    vector_covered: Optional[bool]  # 正確答案裡有沒有已算過向量的；沒開向量是 None
    returned: list[str]          # 搜尋回傳的文件 id，照順序
    relevant: list[str]
    elapsed_ms: float


def first_relevant_rank(returned: Iterable[str], relevant: Iterable[str]) -> Optional[int]:
    wanted = set(relevant)
    for position, doc_id in enumerate(returned, 1):
        if doc_id in wanted:
            return position
    return None


def recall_at(returned: list[str], relevant: list[str], k: int = LIST_K) -> float:
    """前 k 名找回了幾成的正確答案。一題有很多篇正確答案時（例如同一則公告被轉貼十幾次），上限是 k／正確答案數。"""
    wanted = set(relevant)
    return len(wanted & set(returned[:k])) / len(wanted) if wanted else 0.0


def ndcg_at(returned: list[str], relevant: list[str], k: int = LIST_K) -> float:
    """nDCG@k（相關只有「是／否」兩級）：每篇正確答案依名次打折（第 i 名乘 1／log2(i＋1)）加總，
    再除以「正確答案全部排在最前面」時的分數。和 MRR 的差別：MRR 只看第一篇，nDCG 看所有正確答案排得好不好。"""
    wanted = set(relevant)
    if not wanted:
        return 0.0
    dcg = sum(1 / math.log2(i + 1) for i, doc_id in enumerate(returned[:k], 1) if doc_id in wanted)
    ideal = sum(1 / math.log2(i + 1) for i in range(1, min(len(wanted), k) + 1))
    return dcg / ideal


def summarize(results: list[QuestionResult]) -> dict:
    """Hit@k：前 k 名有正確答案的題目比例。MRR@10：第一篇正確答案名次的倒數平均，前 10 名外算 0。
    Recall@10、nDCG@10：見 `recall_at`、`ndcg_at`，都是每題算完再平均。"""
    n = len(results)
    if n == 0:
        return {"n": 0, **{f"hit@{k}": 0.0 for k in HIT_KS}, f"mrr@{MRR_K}": 0.0,
                f"recall@{LIST_K}": 0.0, f"ndcg@{LIST_K}": 0.0}
    summary = {"n": n}
    for k in HIT_KS:
        summary[f"hit@{k}"] = sum(r.rank is not None and r.rank <= k for r in results) / n
    summary[f"mrr@{MRR_K}"] = sum(1 / r.rank for r in results if r.rank is not None and r.rank <= MRR_K) / n
    summary[f"recall@{LIST_K}"] = sum(recall_at(r.returned, r.relevant) for r in results) / n
    summary[f"ndcg@{LIST_K}"] = sum(ndcg_at(r.returned, r.relevant) for r in results) / n
    return summary


def evaluate(index: SearchIndex, questions: list[dict], queries: Optional[dict[str, str]] = None,
             embedded: Optional[set[str]] = None) -> list[QuestionResult]:
    """`queries` 給了就用它（題號 → 查詢字，關鍵字模式），沒給就用原句。
    兩種模式都把原句當 `question` 傳進去（只有重新排序會用）：MCP 的客戶端拆關鍵字搜尋時，也會附上使用者的原句。
    `embedded` 是已算過向量的文件 id；給了就標出每題的正確答案在不在向量範圍內。"""
    index.sync()
    results = []
    for q in questions:
        query = queries[q["qid"]] if queries is not None else q["question"]
        started = time.perf_counter()
        hits = index.search(query, limit=index.max_limit, question=q["question"])
        elapsed = (time.perf_counter() - started) * 1000
        returned = [h.doc_id for h in hits]
        results.append(QuestionResult(
            qid=q["qid"], question=q["question"], query=query, category=q.get("category", "情報"),
            origin=q.get("origin", ""),
            type=q.get("type", ""), rank=first_relevant_rank(returned, q["relevant"]),
            vector_covered=None if embedded is None else any(d in embedded for d in q["relevant"]),
            returned=returned,
            relevant=list(q["relevant"]), elapsed_ms=round(elapsed, 1),
        ))
    return results


def _group(results: list[QuestionResult], key) -> dict[str, list[QuestionResult]]:
    groups: dict[str, list[QuestionResult]] = defaultdict(list)
    for r in results:
        groups[key(r)].append(r)
    return dict(sorted(groups.items()))


def _table(title: str, groups: dict[str, list[QuestionResult]]) -> list[str]:
    header = ["| " + title + " | 題數 | " + " | ".join(f"Hit@{k}" for k in HIT_KS)
              + f" | MRR@{MRR_K} | Recall@{LIST_K} | nDCG@{LIST_K} |",
              "|---|---:|" + "---:|" * (len(HIT_KS) + 3)]
    rows = []
    for name, items in groups.items():
        s = summarize(items)
        rows.append(f"| {name} | {s['n']} | " + " | ".join(f"{s[f'hit@{k}']:.0%}" for k in HIT_KS)
                    + f" | {s[f'mrr@{MRR_K}']:.3f} | {s[f'recall@{LIST_K}']:.0%} | {s[f'ndcg@{LIST_K}']:.3f} |")
    return header + rows


def _mode_section(mode: str, results: list[QuestionResult]) -> list[str]:
    times = sorted(r.elapsed_ms for r in results)
    p95 = times[min(len(times) - 1, int(len(times) * 0.95))] if times else 0
    lines = [f"## {mode}模式", "", f"速度：平均 {sum(times) / max(len(times), 1):.0f} ms、p95 {p95:.0f} ms", ""]
    lines += _table("分類", _group(results, lambda r: r.category)) + [""]
    lines += _table("出題依據的來源", _group(results, lambda r: r.origin)) + [""]
    lines += _table("題型", _group(results, lambda r: r.type)) + [""]
    if any(r.vector_covered is not None for r in results):
        lines += _table("正確答案已算向量", _group(results, lambda r: "是" if r.vector_covered else "否")) + [""]
    missed = [r for r in results if r.rank is None or r.rank > 5]
    lines += [f"### 前 5 名沒有正確答案的題目（{len(missed)} 題）", ""]
    for r in missed:
        where = "不在結果裡" if r.rank is None else f"排第 {r.rank}"
        shown = r.question if r.query == r.question else f"{r.question}（查詢：{r.query}）"
        lines.append(f"- {r.qid}（{r.category}／{r.type}）{shown} → {where}")
    return lines + [""]


def render_markdown(by_mode: dict[str, list[QuestionResult]], *, label: str, index: SearchIndex,
                    when: datetime) -> str:
    n = len(next(iter(by_mode.values()), []))
    lines = [
        f"# 搜尋評估：{label}",
        "",
        f"- 時間：{when:%Y-%m-%d %H:%M}；題數 {n}",
        f"- 設定：每種來源最多 {index.per_source_limit} 筆、總共最多 {index.max_limit} 筆；正規化 `{normalizer_id()}`",
        f"- 向量：{'開（關鍵字與向量用 RRF 合併）' if index.vector_store is not None else '關（只用關鍵字）'}"
        + (f"；向量權重 {index.fusion_weights['向量']}、門檻 {index.vector_max_distance}"
           if index.vector_store is not None else ""),
        f"- 重新排序：{f'開（前 {index.rerank_candidates} 篇）' if index.reranker is not None else '關'}",
        "",
    ]
    lines += _table("模式", by_mode) + [""]
    lines += ["| 模式 | 情報 Hit@5 | 攻略 Hit@5 |", "|---|---:|---:|"]
    for mode, results in by_mode.items():
        info = summarize([r for r in results if r.category == "情報"])
        build = summarize([r for r in results if r.category.startswith("攻略")])
        lines.append(f"| {mode} | {info['hit@5']:.0%} | {build['hit@5']:.0%} |")
    lines.append("")
    for mode, results in by_mode.items():
        lines += _mode_section(mode, results)
    return "\n".join(lines)


def split_questions(questions: list[dict], part: str) -> list[dict]:
    """把考卷固定拆成 A、B 兩半：每個分類各自照題號交錯分配，兩半的題型比例才接近。

    為什麼要拆：調參數（門檻、權重）時在 A 上選，再看 B 是不是同樣的結論——在同一份題目上挑最高分
    再拿同一份題目宣稱效果，會把「剛好在這幾題運氣好」算成實力（過度擬合評估集）。"""
    if part == "全部":
        return list(questions)
    by_category: dict[str, list[dict]] = defaultdict(list)
    for q in sorted(questions, key=lambda q: q["qid"]):
        by_category[q.get("category", "情報")].append(q)
    picked = {q["qid"] for items in by_category.values() for i, q in enumerate(items) if (i % 2 == 0) == (part == "A")}
    return [q for q in questions if q["qid"] in picked]


def diagnose_vectors(store, questions: list[dict], queries: Optional[dict[str, str]] = None, k: int = 20) -> list[dict]:
    """每題向量前 k 名的距離與是否為正確答案：門檻要看真實的距離分布來定。"""
    from services.search.text import normalize

    rows = []
    for q in questions:
        query = queries[q["qid"]] if queries is not None else q["question"]
        hits = store.search_with_distances(normalize(query), sources=["article", "fb", "ptt", "bahamut"],
                                           start="", end="9999-12-31", k=k)
        relevant = set(q["relevant"])
        rows.append({"qid": q["qid"], "query": query,
                     "hits": [{"doc_id": d, "distance": round(dist, 4), "relevant": d in relevant} for d, dist in hits]})
    return rows


def load_questions(path: Path, *, reviewed_only: bool = True) -> list[dict]:
    questions = json.loads(path.read_text(encoding="utf-8"))["questions"]
    return [q for q in questions if q.get("reviewed") or not reviewed_only]


def load_keyword_queries(path: Path) -> dict[str, str]:
    return json.loads(path.read_text(encoding="utf-8"))["queries"]


def main(argv: Optional[list[str]] = None) -> Path:
    parser = argparse.ArgumentParser(description="拿考卷考搜尋，算 Hit Rate 與 MRR")
    parser.add_argument("--label", default="評估", help="這次評估的名稱，會寫進報告標題與檔名")
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    parser.add_argument("--keywords", type=Path, default=DEFAULT_KEYWORDS)
    parser.add_argument("--mode", choices=(*MODES, "兩者"), default="兩者")
    parser.add_argument("--vector", choices=("on", "off"), default="on", help="off＝只用關鍵字（對照組）")
    parser.add_argument("--vector-weight", type=float, default=None, help="向量那一路在 RRF 的權重（預設照設定檔）")
    parser.add_argument("--max-distance", type=float, default=None,
                        help="向量門檻：餘弦距離超過就不算；不給＝照設定檔，inf＝不設門檻（對照組）")
    parser.add_argument("--split", choices=("全部", "A", "B"), default="全部", help="只考考卷的 A 或 B 半（調參用）")
    parser.add_argument("--diagnose-vectors", action="store_true", help="只輸出每題向量前 20 名的距離，不評分")
    parser.add_argument("--rerank", choices=("on", "off"), default="off", help="on＝合併後的前幾十篇再用 reranker 重排")
    args = parser.parse_args(argv)

    # 評估不看 switches.json：要比的就是開與關，由參數決定
    reranker = None
    if args.rerank == "on":
        from services.search.rerank import LemonadeReranker

        # 評估要量的是 reranker 本身：GPU 等久一點也沒關係，不要因為剛好碰上 bot 在回答就跳過重排
        reranker = LemonadeReranker(max_wait_seconds=600)
    if args.vector == "on":
        from services.search.vectors import PgVectorStore

        index = SearchIndex(vector_store=PgVectorStore(), vector_weight=args.vector_weight,
                            vector_max_distance=args.max_distance, reranker=reranker)
        # 同上：問句向量也不要因為碰上 bot 在回答就退回只用關鍵字，否則量到的不是向量的效果
        index.vector_store.embedder.query_gpu_wait_seconds = 600
    else:
        index = SearchIndex(reranker=reranker)
    embedded = None
    if index.vector_store is not None:
        try:
            embedded = index.vector_store.embedded_doc_ids()
        except Exception as exc:
            logger.warning("讀不到已算向量的文件清單：%s", exc)
    questions = split_questions(load_questions(args.questions), args.split)
    if args.diagnose_vectors:
        return _write_diagnosis(index, questions, load_keyword_queries(args.keywords), args.label)
    by_mode: dict[str, list[QuestionResult]] = {}
    if args.mode in ("原句", "兩者"):
        by_mode["原句"] = evaluate(index, questions, embedded=embedded)
    if args.mode in ("關鍵字", "兩者"):
        by_mode["關鍵字"] = evaluate(index, questions, load_keyword_queries(args.keywords), embedded=embedded)
    when = datetime.now(APP_TZ)
    out_dir = EVAL_DIR / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{when:%Y%m%d-%H%M}-{args.label}"
    report = render_markdown(by_mode, label=args.label, index=index, when=when)
    report = report.replace("\n- 向量：", f"\n- 考卷：{args.split}（{len(questions)} 題）\n- 向量：", 1)
    (out_dir / f"{stem}.json").write_text(
        json.dumps({"label": args.label, "when": when.isoformat(),
                    "settings": {"split": args.split, "vector": args.vector, "rerank": args.rerank,
                                 "vector_weight": index.fusion_weights["向量"] if index.vector_store else None,
                                 "max_distance": index.vector_max_distance if index.vector_store else None,
                                 "embedded_docs": len(embedded) if embedded is not None else None},
                    "modes": {mode: {"summary": summarize(results), "results": [asdict(r) for r in results]}
                              for mode, results in by_mode.items()}}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    logger.info("評估結果：\n%s", report)
    for mode, results in by_mode.items():
        s = summarize(results)
        logger.info("%s模式（%d 題）：Hit@5 %.0f%%、MRR@10 %.3f", mode, s["n"], s["hit@5"] * 100, s[f"mrr@{MRR_K}"])
    logger.info("報告：%s", out_dir / f"{stem}.json")
    return out_dir / f"{stem}.json"


def _write_diagnosis(index: SearchIndex, questions: list[dict], keyword_queries: dict[str, str], label: str) -> Path:
    if index.vector_store is None:
        raise SystemExit("距離診斷要開向量（--vector on）")
    when = datetime.now(APP_TZ)
    data = {"原句": diagnose_vectors(index.vector_store, questions),
            "關鍵字": diagnose_vectors(index.vector_store, questions, keyword_queries)}
    out = EVAL_DIR / "reports" / f"{when:%Y%m%d-%H%M}-{label}-向量距離.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    for mode, rows in data.items():
        relevant = sorted(h["distance"] for r in rows for h in r["hits"] if h["relevant"])
        others = sorted(h["distance"] for r in rows for h in r["hits"][:5] if not h["relevant"])
        def pct(values, p):
            return values[min(len(values) - 1, int(len(values) * p))] if values else float("nan")
        logger.info("%s：正確答案的距離 中位數 %.3f、90%% 在 %.3f 以內（%d 筆）；前 5 名的非答案 中位數 %.3f、"
                    "10%% 小於 %.3f（%d 筆）", mode, pct(relevant, 0.5), pct(relevant, 0.9), len(relevant),
                    pct(others, 0.5), pct(others, 0.1), len(others))
    logger.info("距離診斷：%s", out)
    return out


if __name__ == "__main__":
    from utils.logger_config import configure_logging

    # 從 docker exec 手動執行：只印到畫面，不寫 bot 的輪替 log
    configure_logging(force=True, root_handlers=["console"])
    main()
