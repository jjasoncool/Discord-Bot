"""搜尋索引：從 scraper 的 articles.db 唯讀增量同步到自己的 SQLite FTS5 索引，再做關鍵字搜尋。

為什麼另開一個索引檔、不在 articles.db 上建 FTS：articles.db 是 scraper 的資料（使用者資料），
這裡**只准唯讀開**；索引是可以刪掉重建的衍生資料，放在 `services/search/data/`。

搜尋分兩段（常見的「召回＋重排」）：
  1. 召回：全詞（三字組索引，含全部長關鍵字）、兩字組 BM25（整句或關鍵字切成兩字一組）、
     一個字的關鍵字（走 LIKE）三路各撈一批
  2. 重排：先比「含了幾個關鍵字」，同分再比兩字組那一路的 BM25 名次，最後新的在前
  3. 有向量（P3）時，關鍵字的名次再和向量（語意）的名次用 RRF 合併，見 `vectors.py`
  4. 有 reranker（P4）時，合併後的前幾十篇再讓 reranker 逐篇讀過、重新排序，見 `rerank.py`；
     呼叫端給了使用者的原句（`question`）就用原句判斷，不用拆成關鍵字的查詢字
兩份索引分工：三字組（trigram）擅長整段比對長詞；兩字組讓沒有空格的中文句子也能靠 BM25
自動壓低常見詞、拉高少見詞（2026-10-08 加，原句模式的評估從這裡開始改善，見 AI_HANDOFF_AND_TODO.md 的 mcp-search-tools 區塊）。
"""
from __future__ import annotations

import logging
import re
import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Iterable, Optional

from services.search.sources import SOURCES, Doc, Source
from services.search.text import bigram_tokens, normalize, normalizer_id
from services.search.rerank import Reranker, best_passage
from services.search.vectors import VectorSearcher
from sys_settings.search_settings import SEARCH_SETTINGS
from utils.rank_fusion import fuse_rankings
from utils.user_dates import parse_user_date

logger = logging.getLogger(__name__)

#: 索引結構改了就加一。索引比這個數字舊就整份重建；**比這個數字新就停下**（見 `IndexTooNew`）
SCHEMA_VERSION = 2
#: 正規化方式的新舊（數字大的較新）：裝上 opencc 之後是升級，舊環境的行程不能把它降回去
_NORMALIZER_RANK = {"nfkc": 1, "nfkc+s2t": 2}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS docs (
    id INTEGER PRIMARY KEY,
    doc_id TEXT NOT NULL UNIQUE,
    source TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT,
    published_at TEXT NOT NULL,
    raw_hash TEXT NOT NULL,
    search_text TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS docs_source_published ON docs (source, published_at);
CREATE VIRTUAL TABLE IF NOT EXISTS docs_fts USING fts5(
    search_text, content='docs', content_rowid='id', tokenize='trigram'
);
CREATE TRIGGER IF NOT EXISTS docs_ai AFTER INSERT ON docs BEGIN
    INSERT INTO docs_fts (rowid, search_text) VALUES (new.id, new.search_text);
END;
CREATE TRIGGER IF NOT EXISTS docs_ad AFTER DELETE ON docs BEGIN
    INSERT INTO docs_fts (docs_fts, rowid, search_text) VALUES ('delete', old.id, old.search_text);
END;
CREATE TRIGGER IF NOT EXISTS docs_au AFTER UPDATE ON docs BEGIN
    INSERT INTO docs_fts (docs_fts, rowid, search_text) VALUES ('delete', old.id, old.search_text);
    INSERT INTO docs_fts (rowid, search_text) VALUES (new.id, new.search_text);
END;
-- 兩字組索引：中文先在 Python 切好（bigram_tokens）再用空白隔開存入；不存原文（content=''），
-- 只拿來排名。觸發器做不了切詞，所以由同步程式自己維護
CREATE VIRTUAL TABLE IF NOT EXISTS docs_bigram USING fts5(tokens, content='', contentless_delete=1, tokenize='unicode61');
CREATE TABLE IF NOT EXISTS cursors (source TEXT PRIMARY KEY, updated_at TEXT NOT NULL, row_id INTEGER NOT NULL);
"""
_DROP = """
DROP TRIGGER IF EXISTS docs_ai; DROP TRIGGER IF EXISTS docs_ad; DROP TRIGGER IF EXISTS docs_au;
DROP TABLE IF EXISTS docs_fts; DROP TABLE IF EXISTS docs_bigram; DROP TABLE IF EXISTS docs; DROP TABLE IF EXISTS cursors; DROP TABLE IF EXISTS meta;
"""

# 查詢字的分隔：空白與常見中英文標點
_TERM_SPLIT = re.compile(r"[\s,，。、！？!?;；:：「」『』（）()\[\]【】\"'“”‘’|/]+")
#: 兩字組那一路最多用幾組；一整段話丟進來時不讓查詢無限長
_MAX_GRAMS = 64


class DocumentNotFound(LookupError):
    """`fetch` 的 id 不存在或格式不對。"""


class IndexTooNew(RuntimeError):
    """索引是比這個行程新的程式建的。

    src 是即時掛載的：Claude Code 開著的 MCP 行程跑的是它啟動當時的程式。若它看到新版索引就照舊版重建，
    新程式下次同步又建回新版——兩邊輪流整份重建、每次十萬多列，期間別人的搜尋會卡住或是空的。
    所以只升不降：舊行程遇到新索引就停下，請它重開。"""


@dataclass(frozen=True)
class SyncReport:
    added: int = 0
    updated: int = 0
    removed: int = 0
    rebuilt: bool = False
    skipped: bool = False      # 距離上次同步太近，這次沒做


@dataclass(frozen=True)
class SearchHit:
    doc_id: str
    source: str
    source_label: str
    official: bool
    title: str
    url: Optional[str]
    published_at: str
    snippet: str


@dataclass(frozen=True)
class FetchedDoc:
    doc_id: str
    source: str
    source_label: str
    official: bool
    title: str
    url: Optional[str]
    published_at: str
    text: str
    page: int
    total_pages: int


def parse_terms(query: str) -> list[str]:
    """查詢字正規化後依空白與標點切成關鍵字，去重、保留順序。"""
    seen: dict[str, None] = {}
    for part in _TERM_SPLIT.split(normalize(query)):
        if part and part.lower() not in seen:
            seen[part.lower()] = None
    return list(seen)


def _phrase(term: str) -> str:
    return '"' + term.replace('"', '""') + '"'


def _like_pattern(term: str) -> str:
    return "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


class SearchIndex:
    """情報搜尋的索引。每次搜尋前自動做增量同步（有最短間隔），也可以手動 `sync()`。"""

    def __init__(
        self,
        *,
        index_path: Optional[Path] = None,
        articles_db_path: Optional[Path] = None,
        sources: Optional[dict[str, Source]] = None,
        per_source_limit: Optional[int] = None,
        max_limit: Optional[int] = None,
        candidate_pool: Optional[int] = None,
        snippet_chars: Optional[int] = None,
        fetch_page_chars: Optional[int] = None,
        sync_min_interval_seconds: Optional[float] = None,
        vector_store: Optional[VectorSearcher] = None,
        vector_enabled: Callable[[], bool] = lambda: True,
        vector_weight: Optional[float] = None,
        vector_max_distance: Optional[float] = None,
        reranker: Optional[Reranker] = None,
        rerank_enabled: Callable[[], bool] = lambda: True,
    ):
        s = SEARCH_SETTINGS
        self.index_path = Path(index_path or s.index_path)
        self.articles_db_path = Path(articles_db_path or s.articles_db_path)
        self.sources = sources or SOURCES
        self.per_source_limit = per_source_limit or s.per_source_limit
        self.max_limit = max_limit or s.max_limit
        self.candidate_pool = candidate_pool or s.candidate_pool
        self.snippet_chars = snippet_chars or s.snippet_chars
        self.fetch_page_chars = fetch_page_chars or s.fetch_page_chars
        self.sync_min_interval = (s.sync_min_interval_seconds if sync_min_interval_seconds is None
                                  else sync_min_interval_seconds)
        self._last_sync = float("-inf")
        #: 向量那一路；None＝只用關鍵字（單元測試、或 SEARCH_SETTINGS.vector_enabled 關掉時）
        self.vector_store = vector_store
        #: 每次搜尋都問一次（正式環境接 settings/switches.json 的 search_vector_mode，改了就生效）
        self.vector_enabled = vector_enabled
        self.vector_candidates = s.vector_candidates
        self.rrf_k = s.rrf_k
        self.fusion_weights = {"關鍵字": s.lexical_weight,
                               "向量": s.vector_weight if vector_weight is None else vector_weight}
        self.vector_max_distance = s.vector_max_distance if vector_max_distance is None else vector_max_distance
        #: 重新排序；None＝不重排。開關每次搜尋都問（正式環境接 switches.json 的 search_rerank_mode）
        self.reranker = reranker
        self.rerank_enabled = rerank_enabled
        self.rerank_candidates = s.rerank_candidates
        self.rerank_passage_chars = s.rerank_passage_chars

    # ---------- 連線 ----------

    def _open_source(self) -> sqlite3.Connection:
        """scraper 的資料庫只能唯讀開。用 mode=ro 而不是 immutable=1：WAL 裡還沒寫回的新資料也要看得到。"""
        if not self.articles_db_path.exists():
            raise FileNotFoundError(f"找不到 scraper 的資料庫：{self.articles_db_path}")
        con = sqlite3.connect(f"file:{self.articles_db_path}?mode=ro", uri=True, timeout=30)
        con.row_factory = sqlite3.Row
        return con

    def _open_index(self) -> sqlite3.Connection:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        # 自己管交易（BEGIN IMMEDIATE），兩個行程同時同步時靠 SQLite 的寫入鎖排隊
        con = sqlite3.connect(self.index_path, timeout=60, isolation_level=None)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        return con

    @staticmethod
    def _ensure_schema(con: sqlite3.Connection) -> bool:
        """建立或檢查索引結構；索引比這個行程舊（結構版本或正規化方式）就清掉重建，比較新就丟
        `IndexTooNew`。回傳是否清掉了舊索引。"""
        normalizer = normalizer_id()
        has_meta = con.execute("SELECT 1 FROM sqlite_master WHERE name='meta'").fetchone()
        current = dict(con.execute("SELECT key, value FROM meta").fetchall()) if has_meta else {}
        rebuilt = False
        if current:
            try:
                their_schema = int(current.get("schema") or 0)
            except ValueError:
                their_schema = 0
            mine = (SCHEMA_VERSION, _NORMALIZER_RANK.get(normalizer, 0))
            theirs = (their_schema, _NORMALIZER_RANK.get(current.get("normalizer"), 0))
            if theirs > mine:
                raise IndexTooNew(
                    f"搜尋索引是比這個行程新的程式建的（索引：結構 {theirs[0]}、正規化 {current.get('normalizer')}；"
                    f"這個行程：結構 {SCHEMA_VERSION}、正規化 {normalizer}）。請重開這個行程"
                    f"（MCP 的話重開 Claude Code）。")
            if theirs < mine or current.get("normalizer") != normalizer:
                logger.info("搜尋索引比這個行程舊（%s → 結構 %s、正規化 %s），整份重建", current, SCHEMA_VERSION, normalizer)
                con.executescript(_DROP)
                rebuilt = True
        con.executescript(_SCHEMA)
        con.executemany("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                        [("schema", str(SCHEMA_VERSION)), ("normalizer", normalizer)])
        return rebuilt

    # ---------- 同步 ----------

    def sync(self, *, force: bool = False) -> SyncReport:
        """把 scraper 資料庫的新增、修改、刪除跟上。`force=False` 時距離上次太近就跳過。"""
        if not force and time.monotonic() - self._last_sync < self.sync_min_interval:
            return SyncReport(skipped=True)
        started = time.monotonic()
        added = updated = removed = 0
        with closing(self._open_source()) as src, closing(self._open_index()) as con:
            # 建表要在開交易之前：executescript 會先自動 COMMIT，把交易提早結束
            rebuilt = self._ensure_schema(con)
            con.execute("BEGIN IMMEDIATE")
            try:
                for source in self.sources.values():
                    a, u, r = self._sync_source(con, src, source)
                    added, updated, removed = added + a, updated + u, removed + r
                con.execute("COMMIT")
            except BaseException:
                if con.in_transaction:
                    con.execute("ROLLBACK")
                raise
        self._last_sync = time.monotonic()
        if added or updated or removed or rebuilt:
            logger.info("搜尋索引同步：新增 %d、更新 %d、移除 %d%s（%.1f 秒）", added, updated, removed,
                        "、整份重建" if rebuilt else "", time.monotonic() - started)
        return SyncReport(added, updated, removed, rebuilt)

    def _sync_source(self, con, src, source: Source) -> tuple[int, int, int]:
        row = con.execute("SELECT updated_at, row_id FROM cursors WHERE source = ?", (source.key,)).fetchone()
        cursor = (row["updated_at"], row["row_id"]) if row else ("", 0)
        added = updated = removed = 0
        last = cursor
        for change in source.scan(src, cursor):
            last = change.cursor
            existing = con.execute("SELECT id, raw_hash FROM docs WHERE doc_id = ?", (change.doc_id,)).fetchone()
            if change.deleted:
                if existing:
                    con.execute("DELETE FROM docs WHERE id = ?", (existing["id"],))
                    con.execute("DELETE FROM docs_bigram WHERE rowid = ?", (existing["id"],))
                    removed += 1
                continue
            if existing and existing["raw_hash"] == change.raw_hash:
                continue
            doc = change.build()
            search_text = self._search_text(doc)
            values = (doc.source, doc.title, doc.url, doc.published_at, change.raw_hash, search_text)
            if existing:
                doc_pk = existing["id"]
                con.execute("UPDATE docs SET source=?, title=?, url=?, published_at=?, raw_hash=?, search_text=?"
                            " WHERE id = ?", (*values, doc_pk))
                con.execute("DELETE FROM docs_bigram WHERE rowid = ?", (doc_pk,))
                updated += 1
            else:
                doc_pk = con.execute("INSERT INTO docs (source, title, url, published_at, raw_hash, search_text,"
                                     " doc_id) VALUES (?, ?, ?, ?, ?, ?, ?)", (*values, change.doc_id)).lastrowid
                added += 1
            con.execute("INSERT INTO docs_bigram (rowid, tokens) VALUES (?, ?)",
                        (doc_pk, " ".join(bigram_tokens(search_text))))
        if last != cursor:
            con.execute("INSERT OR REPLACE INTO cursors (source, updated_at, row_id) VALUES (?, ?, ?)",
                        (source.key, *last))
        return added, updated, removed

    @staticmethod
    def _search_text(doc: Doc) -> str:
        return normalize("\n".join(part for part in (doc.title, doc.body) if part))

    # ---------- 搜尋 ----------

    def resolve_sources(self, sources: Optional[Iterable[str]]) -> list[str]:
        if not sources:
            return list(self.sources)
        keys = list(dict.fromkeys(sources))
        unknown = [k for k in keys if k not in self.sources]
        if unknown:
            raise ValueError(f"不認得的來源：{', '.join(unknown)}；可用的有：{', '.join(self.sources)}")
        return keys

    @staticmethod
    def _date_range(since: Optional[str], until: Optional[str]) -> tuple[str, str]:
        def parse(value, name) -> Optional[date]:
            if value in (None, ""):
                return None
            parsed = parse_user_date(str(value))
            if parsed is None:
                raise ValueError(f"{name} 要是 YYYY-MM-DD 格式的日期，收到：{value}")
            return parsed
        start, end = parse(since, "since"), parse(until, "until")
        # 起訖都含當天：until 那天的 23:59:59 也要算進去。模型想表達「不設上限」時可能傳 9999-12-31，
        # 加一天會超出日期範圍——那就等於沒有上限
        try:
            end_text = (end + timedelta(days=1)).isoformat() if end else "9999-12-31"
        except OverflowError:
            end_text = "9999-12-31"
        return (start.isoformat() if start else "", end_text)

    def search(self, query: str, *, sources: Optional[Iterable[str]] = None, since: Optional[str] = None,
               until: Optional[str] = None, limit: Optional[int] = None,
               question: Optional[str] = None) -> list[SearchHit]:
        """`query` 是查詢字（關鍵字或整句都可以）；`question` 是使用者的原句，只給重新排序用。

        為什麼分開：關鍵字適合找（全詞、BM25），reranker 是拿自然語言的問句訓練的，拿「卜靈 身分」這種
        斷片去判斷哪篇在回答，反而排不準（2026-10-08 評估：關鍵字模式加上重排，MRR 0.559 → 0.483）。"""
        keys = self.resolve_sources(sources)
        start, end = self._date_range(since, until)
        limit = max(1, min(int(limit or self.max_limit), self.max_limit))
        terms = parse_terms(query)
        self.sync()
        if not terms:
            return []
        vector_ids = self._vector_doc_ids(query, keys, start, end)

        long_terms = [t for t in terms if len(t) >= 3]
        # 兩個字的詞本身就是一組兩字組，交給兩字組索引；只有一個字的才走 LIKE
        single_chars = [t for t in terms if len(t) == 1]
        grams = list(dict.fromkeys(bigram_tokens(normalize(query))))[:_MAX_GRAMS]
        marks = ",".join("?" * len(keys))
        where = f"d.source IN ({marks}) AND d.published_at >= ? AND d.published_at < ?"
        params = [*keys, start, end]
        pool = self.candidate_pool

        with closing(self._open_index()) as con:
            candidate_ids: dict[int, None] = {}
            fuzzy_rank: dict[int, int] = {}

            def fts(table: str, match: str) -> list[int]:
                return [r[0] for r in con.execute(
                    f"SELECT d.id FROM {table} JOIN docs d ON d.id = {table}.rowid"
                    f" WHERE {table} MATCH ? AND {where} ORDER BY bm25({table}) LIMIT ?",
                    (match, *params, pool))]

            if long_terms:
                # 全詞：每個長關鍵字都要整段出現（三字組索引）
                candidate_ids.update(dict.fromkeys(fts("docs_fts", " AND ".join(_phrase(t) for t in long_terms))))
            if grams:
                # 兩字組：任一組命中就進來，BM25 依命中多寡與稀有程度排名（常見詞權重自動變低）
                for rank, doc_pk in enumerate(fts("docs_bigram", " OR ".join(_phrase(g) for g in grams))):
                    fuzzy_rank[doc_pk] = rank
                    candidate_ids.setdefault(doc_pk, None)
            for term in single_chars:
                # 一個字的詞兩字組查不到（例如角色名「椿」），改用 LIKE（掃整張表，十萬列約一秒內）
                candidate_ids.update(dict.fromkeys(r[0] for r in con.execute(
                    f"SELECT d.id FROM docs d WHERE d.search_text LIKE ? ESCAPE '\\' AND {where}"
                    f" ORDER BY d.published_at DESC LIMIT ?", (_like_pattern(term), *params, pool))))
            if not candidate_ids and not vector_ids:
                return []

            rows = []
            columns = "id, doc_id, source, title, url, published_at, search_text"
            ids = list(candidate_ids)
            for i in range(0, len(ids), 500):
                chunk = ids[i:i + 500]
                rows += con.execute(f"SELECT {columns} FROM docs WHERE id IN ({','.join('?' * len(chunk))})",
                                    chunk).fetchall()
            vector_rows = []
            for i in range(0, len(vector_ids), 500):
                chunk = vector_ids[i:i + 500]
                # 向量那邊理應已照來源、日期篩過；這裡再篩一次，不讓範圍外的文件混進結果
                vector_rows += con.execute(
                    f"SELECT {columns} FROM docs d WHERE doc_id IN ({','.join('?' * len(chunk))}) AND {where}",
                    (*chunk, *params)).fetchall()

        lowered = [t.lower() for t in terms]
        scored = []
        for row in rows:
            text = row["search_text"].lower()
            scored.append((row, sum(t in text for t in lowered)))
        # 新的在前當最後的決勝，所以先依日期排，再用穩定排序依主要條件排
        scored.sort(key=lambda item: item[0]["published_at"], reverse=True)
        scored.sort(key=lambda item: (-item[1], fuzzy_rank.get(item[0]["id"], pool)))
        ordered = [row for row, _ in scored]
        if vector_ids:
            # 關鍵字與向量各自的名次用 RRF 合併：兩邊都排前面的浮上來，只有一邊找到的也不會被埋掉
            by_doc = {row["doc_id"]: row for row in [*ordered, *vector_rows]}
            fused = fuse_rankings(
                {"關鍵字": [row["doc_id"] for row in ordered], "向量": [d for d in vector_ids if d in by_doc]},
                weights=self.fusion_weights, k=self.rrf_k)
            ordered = [by_doc[doc_id] for doc_id in fused]
        # 重排在來源上限之前：先決定誰最相關，再每種來源取前幾筆
        ordered = self._rerank(query, ordered, question=question)

        hits: list[SearchHit] = []
        per_source: dict[str, int] = {}
        for row in ordered:
            if per_source.get(row["source"], 0) >= self.per_source_limit:
                continue
            per_source[row["source"]] = per_source.get(row["source"], 0) + 1
            source = self.sources[row["source"]]
            hits.append(SearchHit(
                doc_id=row["doc_id"], source=source.key, source_label=source.label, official=source.official,
                title=row["title"], url=row["url"], published_at=row["published_at"],
                snippet=self._snippet(row["search_text"], terms),
            ))
            if len(hits) >= limit:
                break
        return hits

    def _rerank(self, query: str, rows: list, *, question: Optional[str] = None) -> list:
        """前 `rerank_candidates` 篇照 reranker 的分數重排，其餘照舊接在後面。
        有原句就讓 reranker 讀原句；每篇挑哪一段還是看查詢字（關鍵字就是要找的詞，原句多了「是什麼」這類虛字）。
        reranker 壞掉、GPU 等太久、回傳筆數不對，都照原本的名次（搜尋本身不能因此失敗）。"""
        if self.reranker is None or len(rows) < 2 or not self.rerank_enabled():
            return rows
        head, tail = rows[:self.rerank_candidates], rows[self.rerank_candidates:]
        passages = [best_passage(query, row["search_text"], self.rerank_passage_chars) for row in head]
        try:
            scores = self.reranker.rerank(normalize((question or "").strip() or query), passages)
        except Exception as exc:
            logger.warning("重新排序失敗，這次照原本的名次：%s", exc)
            return rows
        if len(scores) != len(head):
            logger.warning("重新排序回傳 %d 個分數、送了 %d 篇，這次照原本的名次", len(scores), len(head))
            return rows
        # 同分照原本的名次（sorted 是穩定排序）
        order = sorted(range(len(head)), key=lambda i: -scores[i])
        return [head[i] for i in order] + tail

    def _vector_doc_ids(self, query: str, keys: list[str], start: str, end: str) -> list[str]:
        """向量那一路的名次。壞掉（pgvector、embedding 連不上）就退回只用關鍵字，搜尋本身不能因此失敗。"""
        if self.vector_store is None or not self.vector_enabled():
            return []
        try:
            return self.vector_store.search(normalize(query), sources=keys, start=start, end=end,
                                            k=self.vector_candidates, max_distance=self.vector_max_distance)
        except Exception as exc:
            logger.warning("向量搜尋失敗，這次只用關鍵字：%s", exc)
            return []

    def _snippet(self, text: str, terms: list[str]) -> str:
        """命中的關鍵字前後各取一段；沒有整段命中（模糊那一路）就取開頭。"""
        lowered = text.lower()
        positions = [lowered.find(t.lower()) for t in sorted(terms, key=len, reverse=True)]
        positions = [p for p in positions if p >= 0]
        pos = min(positions) if positions else 0
        half = self.snippet_chars // 2
        start = max(0, pos - half // 2)
        piece = " ".join(text[start:start + self.snippet_chars].split())
        return ("…" if start > 0 else "") + piece + ("…" if start + self.snippet_chars < len(text) else "")

    # ---------- 讀全文 ----------

    def fetch(self, doc_id: str, page: int = 1) -> FetchedDoc:
        """直接從 scraper 的資料庫讀最新的全文（附推文、留言），不經過索引。"""
        source_key, _, native_key = (doc_id or "").partition(":")
        source = self.sources.get(source_key)
        if not source or not native_key:
            raise DocumentNotFound(f"沒有這份文件：{doc_id}（格式是「來源:編號」，來源有 {', '.join(self.sources)}）")
        with closing(self._open_source()) as src:
            loaded = source.load(src, native_key)
        if not loaded:
            raise DocumentNotFound(f"沒有這份文件：{doc_id}")
        doc, extras = loaded
        full = doc.body + (f"\n\n{extras}" if extras else "")
        pages = [full[i:i + self.fetch_page_chars] for i in range(0, len(full), self.fetch_page_chars)] or [""]
        if not 1 <= page <= len(pages):
            raise ValueError(f"頁數超出範圍：這份文件共 {len(pages)} 頁")
        return FetchedDoc(
            doc_id=doc.doc_id, source=source.key, source_label=source.label, official=source.official,
            title=doc.title, url=doc.url, published_at=doc.published_at, text=pages[page - 1],
            page=page, total_pages=len(pages),
        )


_default: Optional[SearchIndex] = None


def default_index() -> SearchIndex:
    """照 `SEARCH_SETTINGS` 建的共用索引（MCP 與之後 bot 的工具呼叫都用這一個）。"""
    global _default
    if _default is None:
        from services.search.rerank import LemonadeReranker
        from services.search.vectors import PgVectorStore
        from sys_settings import switches

        # 建立 PgVectorStore、LemonadeReranker 都不會連線；開關關著時一次都不會碰 pgvector、embedding、reranker
        _default = SearchIndex(vector_store=PgVectorStore(),
                               vector_enabled=lambda: switches.current().search_vector_mode == "on",
                               reranker=LemonadeReranker(),
                               rerank_enabled=lambda: switches.current().search_rerank_mode == "on")
    return _default
