"""批次算向量：把搜尋索引裡的文件切段、算向量、存進 pgvector。

用法（search-mcp 容器裡；每天 03:00 也會自動補算新文章，見 `background.py`）：
  python -m services.search.embed --dry-run            # 只算要做多少（不呼叫 GPU）
  python -m services.search.embed --limit 1000         # 先做最新的 1000 份，量速度
  python -m services.search.embed                      # 做完 SEARCH_SETTINGS.vector_since 之後的全部

  - 範圍：只做 `vector_since` 之後的文件（先做最近的，比例原則；舊資料之後再補），新的先做；
    巴哈只做攻略、心得、情報、問題四類討論串
  - 增量：每段有內容 hash，沒變的不重算；文件改短、段數變少時刪掉多出來的舊段（只刪結尾、前面沒變也算）
  - 排隊：每批都經過 GPU 閘門（在 `vectors.Embedder` 裡），和 bot 的插話、`/askai` 排同一個隊——
    2026-10-08 曾在 embedding 與長回答同時跑時發生顯示卡斷線
  - 文字從自己的索引讀（已轉純文字、已簡轉繁），不再開 scraper 的資料庫
"""
from __future__ import annotations

import argparse
import logging
import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass
from typing import Optional, Sequence

from services.search.chunking import Chunk, chunk_document
from services.search.index import SearchIndex
from sys_settings.paths import sqlite_readonly_uri
from sys_settings.search_settings import SEARCH_SETTINGS

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PlannedDoc:
    doc_id: str
    source: str
    published_at: str
    chunks: list[Chunk]


@dataclass
class EmbedReport:
    docs: int = 0
    chunks: int = 0
    embedded: int = 0
    skipped: int = 0
    removed: int = 0             # 文件改短而刪掉的舊段
    chars: int = 0
    seconds: float = 0.0


def eligible(source: str, title: str, categories: Sequence[str]) -> bool:
    """巴哈只收指定類別的討論串（標題開頭的【攻略】等；回覆樓層的標題就是討論串標題）。"""
    if source != "bahamut":
        return True
    return any(title.startswith(f"【{category}】") for category in categories)


def plan(index_path, *, since: str, categories: Sequence[str] = SEARCH_SETTINGS.vector_bahamut_categories,
         max_chars: int = SEARCH_SETTINGS.chunk_max_chars, overlap: int = SEARCH_SETTINGS.chunk_overlap_chars,
         limit: Optional[int] = None) -> list[PlannedDoc]:
    planned: list[PlannedDoc] = []
    with closing(sqlite3.connect(sqlite_readonly_uri(index_path), uri=True)) as con:
        rows = con.execute("SELECT doc_id, source, published_at, search_text FROM docs WHERE published_at >= ?"
                           " ORDER BY published_at DESC, id DESC", (since,))
        for doc_id, source, published_at, search_text in rows:
            # 索引的 search_text 是「標題\n內文」（已正規化）：第一行就是標題
            title, _, body = search_text.partition("\n")
            if not eligible(source, title, categories):
                continue
            planned.append(PlannedDoc(doc_id, source, published_at,
                                      chunk_document(doc_id, title, body, max_chars=max_chars, overlap=overlap)))
            if limit and len(planned) >= limit:
                break
    return planned


def run(planned: Sequence[PlannedDoc], store, embedder, *, batch_size: int = SEARCH_SETTINGS.embed_batch_size,
        dry_run: bool = False) -> EmbedReport:
    started = time.monotonic()
    report = EmbedReport(docs=len(planned))
    existing = store.existing_chunks([doc.doc_id for doc in planned])
    todo: list[tuple[PlannedDoc, Chunk]] = []
    for doc in planned:
        report.chunks += len(doc.chunks)
        old = existing.get(doc.doc_id, {})
        changed = [c for c in doc.chunks if old.get(c.chunk_id) != c.text_hash]
        report.skipped += len(doc.chunks) - len(changed)
        todo += [(doc, c) for c in changed]
        # 段數變少時刪掉多出來的舊段。只刪掉結尾時前面各段一字不差、沒有段落要重算，也要刪
        stale = set(old) - {c.chunk_id for c in doc.chunks}
        if stale:
            report.removed += len(stale)
            if not dry_run:
                store.delete_stale(doc.doc_id, [c.chunk_id for c in doc.chunks])
    report.chars = sum(len(c.text) for _, c in todo)
    if dry_run:
        report.seconds = time.monotonic() - started
        return report

    for start in range(0, len(todo), batch_size):
        batch = todo[start:start + batch_size]
        vectors = embedder.embed_documents([c.text for _, c in batch])
        store.upsert([(c.chunk_id, doc.doc_id, doc.source, doc.published_at, c.text_hash, vector)
                      for (doc, c), vector in zip(batch, vectors)])
        report.embedded += len(batch)
        if report.embedded % (batch_size * 50) < batch_size:
            elapsed = time.monotonic() - started
            logger.info("已算 %d／%d 段（%.0f 秒）", report.embedded, len(todo), elapsed)
    report.seconds = time.monotonic() - started
    return report


def embed_pending(index: Optional[SearchIndex] = None, store=None, *, since: str = SEARCH_SETTINGS.vector_since,
                  limit: Optional[int] = None, dry_run: bool = False) -> EmbedReport:
    """同步索引、把還沒算過（或內容改過）的段落算完。手動指令和 search-mcp 的每日維護都走這裡。"""
    if store is None:
        from services.search.vectors import PgVectorStore

        store = PgVectorStore()
    index = index or SearchIndex()
    index.sync(force=True)
    report = run(plan(index.index_path, since=since, limit=limit), store, store.embedder, dry_run=dry_run)
    rate = report.chars / report.seconds if report.seconds and report.embedded else 0
    logger.info("算向量%s：%d 份文件、%d 段（要算 %d、沒變跳過 %d、刪掉多出來的舊段 %d）、%d 字；花 %.0f 秒%s",
                "試算" if dry_run else "完成", report.docs, report.chunks, report.chunks - report.skipped,
                report.skipped, report.removed, report.chars, report.seconds,
                f"；約 {rate:.0f} 字／秒（含排隊等 bot）" if rate else "")
    return report


def main(argv: Optional[list[str]] = None) -> EmbedReport:
    parser = argparse.ArgumentParser(description="把搜尋索引的文件切段、算向量、存進 pgvector")
    parser.add_argument("--since", default=SEARCH_SETTINGS.vector_since, help="只做這天之後的文件（YYYY-MM-DD）")
    parser.add_argument("--limit", type=int, default=None, help="最多做幾份文件（新的先做）")
    parser.add_argument("--dry-run", action="store_true", help="只算要做多少，不呼叫 GPU")
    args = parser.parse_args(argv)
    return embed_pending(since=args.since, limit=args.limit, dry_run=args.dry_run)


if __name__ == "__main__":
    from utils.logger_config import configure_logging

    # 從 docker exec 手動執行：只印到畫面，不寫 bot 的輪替 log
    configure_logging(force=True, root_handlers=["console"])
    main()
