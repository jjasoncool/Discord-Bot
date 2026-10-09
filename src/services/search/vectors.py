"""向量（語意）搜尋：段落的向量存在 pgvector，查詢時把問句也轉成向量，找意思最接近的段落。

關鍵字搜尋找不到「換句話說」的問句（例：問「冰棒口味」，文章寫「阿奇儂合作」），向量比的是意思。
兩邊的名次再用 RRF 合併（`utils.rank_fusion`），見 `index.SearchIndex.search`。

  - 存哪：沿用 bot 已有的 pgvector（同一個 Postgres，聊天記憶也在裡面），表名經
    `HYBRID_RETRIEVAL_SETTINGS.physical_table` 加前綴並消毒；HNSW 索引用餘弦距離
  - 算向量：沿用 bot 的 embedding 用戶端（`make_safe_llm_embedding`，和聊天記憶同一個模型），
    延後 import——MCP 行程只有真的要算向量時才載入
  - 查詢前面加任務說明，文件不加（這類 embedding 模型的用法；見 SEARCH_SETTINGS.query_instruction）
  - 打 embedding 一律經過 GPU 閘門（`lemonade_gate.gpu_exclusive_sync`），和 bot 的串流排同一個隊：
    這裡是另一個行程（search-mcp 容器、docker exec 的批次指令），只問「忙不忙」擋不住 bot 在我們算到一半時開始串流
"""
from __future__ import annotations

import logging
from contextlib import AbstractContextManager
from typing import Callable, Iterable, Optional, Protocol, Sequence

from sys_settings.search_settings import SEARCH_SETTINGS

logger = logging.getLogger(__name__)


class VectorSearcher(Protocol):
    """搜尋只需要這一個方法：問句 → 依相似度排好的文件 id（同一篇多段只留最前面那次）。
    `max_distance`：餘弦距離（1－相似度）超過這個值的段落不算，None＝不設門檻。
    `max_wait_seconds`：算問句向量最多等 GPU 幾秒（這次搜尋的等待額度），None＝用 embedder 的預設；等不到丟 `GpuBusy`。"""

    def search(self, query: str, *, sources: Sequence[str], start: str, end: str, k: int,
               max_distance: Optional[float] = None, max_wait_seconds: Optional[float] = None) -> list[str]:
        ...


class Embedder:
    """把文字轉成向量。第一次用到才建立用戶端（會載入 llama_index，約一兩秒）。"""

    def __init__(self, *, query_instruction: Optional[str] = None,
                 gate: Optional[Callable[[], AbstractContextManager]] = None):
        self.query_instruction = query_instruction if query_instruction is not None else SEARCH_SETTINGS.query_instruction
        self._model = None
        if gate is None:
            from llm.client.lemonade_gate import gpu_exclusive_sync

            gate = gpu_exclusive_sync
        self._gate = gate
        #: 問句向量最多等幾秒 GPU（互動式搜尋等不起）；文件批次照閘門預設規則一直等
        self.query_gpu_wait_seconds = SEARCH_SETTINGS.query_gpu_wait_seconds

    def _client(self):
        if self._model is None:
            from llm.client.embedding_client import make_safe_llm_embedding
            from sys_settings.llm_settings import LLMServiceSettings, load_llm_runtime_config

            settings = LLMServiceSettings()
            self._model = make_safe_llm_embedding(
                settings=settings, runtime_config=load_llm_runtime_config(settings.llm_runtime_model_path))
        return self._model

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        client = self._client()
        with self._gate():
            return client.get_text_embedding_batch(list(texts))

    def embed_query(self, text: str, *, max_wait_seconds: Optional[float] = None) -> list[float]:
        prompt = f"Instruct: {self.query_instruction}\nQuery:{text}" if self.query_instruction else text
        client = self._client()
        wait = self.query_gpu_wait_seconds if max_wait_seconds is None else max_wait_seconds
        with self._gate(max_wait_seconds=wait):
            return client.get_text_embedding(prompt)


def _vector_literal(vector: Iterable[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vector) + "]"


class PgVectorStore:
    """pgvector 裡的段落向量。每次操作開一條連線（MCP 與批次指令都是短命行程，不必連線池）。"""

    def __init__(self, *, embedder: Optional[Embedder] = None, table: Optional[str] = None,
                 dim: Optional[int] = None, connect=None):
        from sys_settings.pgvector_settings import HYBRID_RETRIEVAL_SETTINGS

        self.embedder = embedder or Embedder()
        self.table = HYBRID_RETRIEVAL_SETTINGS.physical_table(table or SEARCH_SETTINGS.vector_table)
        self.dim = dim or HYBRID_RETRIEVAL_SETTINGS.pgvector_embed_dim
        self._connect = connect
        self._schema_ready = False

    def _conn(self):
        if self._connect is not None:
            return self._connect()
        from sys_settings.llm_settings import LLMServiceSettings

        return LLMServiceSettings().pgvector_connect()

    def ensure_schema(self, con) -> None:
        if self._schema_ready:
            return
        with con.cursor() as cur:
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.table} (
                    chunk_id TEXT PRIMARY KEY,
                    doc_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    published_at TEXT NOT NULL,
                    text_hash TEXT NOT NULL,
                    embedding vector({self.dim}) NOT NULL
                )""")
            cur.execute(f"CREATE INDEX IF NOT EXISTS {self.table}_doc ON {self.table} (doc_id)")
            # HNSW：近似最近鄰的圖索引，查詢不必跟每一段都比一次（現有的聊天記憶表沒有向量索引，是全表掃描）
            cur.execute(f"CREATE INDEX IF NOT EXISTS {self.table}_hnsw ON {self.table}"
                        f" USING hnsw (embedding vector_cosine_ops)")
        con.commit()
        self._schema_ready = True

    # ---------- 批次寫入（services.search.embed 用）----------

    def existing_chunks(self, doc_ids: Sequence[str]) -> dict[str, dict[str, str]]:
        """文件 id → {段落 id: 內容 hash}。以文件查、不以這次切出的段落查：文件改短時，
        多出來的舊段（例如 #2）也要看得到，才刪得掉。"""
        if not doc_ids:
            return {}
        con = self._conn()
        try:
            self.ensure_schema(con)
            with con.cursor() as cur:
                cur.execute(f"SELECT doc_id, chunk_id, text_hash FROM {self.table} WHERE doc_id = ANY(%s)",
                            (list(doc_ids),))
                found: dict[str, dict[str, str]] = {}
                for doc_id, chunk_id, text_hash in cur.fetchall():
                    found.setdefault(doc_id, {})[chunk_id] = text_hash
                return found
        finally:
            con.close()

    def upsert(self, rows: Sequence[tuple[str, str, str, str, str, Sequence[float]]]) -> None:
        """rows：(chunk_id, doc_id, source, published_at, text_hash, 向量)。"""
        if not rows:
            return
        con = self._conn()
        try:
            self.ensure_schema(con)
            with con.cursor() as cur:
                for chunk_id, doc_id, source, published_at, text_hash, vector in rows:
                    cur.execute(
                        f"INSERT INTO {self.table} (chunk_id, doc_id, source, published_at, text_hash, embedding)"
                        f" VALUES (%s, %s, %s, %s, %s, %s::vector)"
                        f" ON CONFLICT (chunk_id) DO UPDATE SET doc_id = EXCLUDED.doc_id, source = EXCLUDED.source,"
                        f" published_at = EXCLUDED.published_at, text_hash = EXCLUDED.text_hash,"
                        f" embedding = EXCLUDED.embedding",
                        (chunk_id, doc_id, source, published_at, text_hash, _vector_literal(vector)))
            con.commit()
        finally:
            con.close()

    def delete_stale(self, doc_id: str, keep_chunk_ids: Sequence[str]) -> None:
        """文件改短、段數變少時，刪掉多出來的舊段落。"""
        con = self._conn()
        try:
            self.ensure_schema(con)
            with con.cursor() as cur:
                cur.execute(f"DELETE FROM {self.table} WHERE doc_id = %s AND NOT (chunk_id = ANY(%s))",
                            (doc_id, list(keep_chunk_ids)))
            con.commit()
        finally:
            con.close()

    def embedded_doc_ids(self) -> set[str]:
        con = self._conn()
        try:
            self.ensure_schema(con)
            with con.cursor() as cur:
                cur.execute(f"SELECT DISTINCT doc_id FROM {self.table}")
                return {row[0] for row in cur.fetchall()}
        finally:
            con.close()

    # ---------- 查詢 ----------

    def search_with_distances(self, query: str, *, sources: Sequence[str], start: str, end: str,
                              k: int, max_wait_seconds: Optional[float] = None) -> list[tuple[str, float]]:
        """問句 → [(文件 id, 餘弦距離)]，距離小的在前；同一篇多段只留最近的那段。"""
        vector = _vector_literal(self.embedder.embed_query(query, max_wait_seconds=max_wait_seconds))
        con = self._conn()
        try:
            self.ensure_schema(con)
            with con.cursor() as cur:
                # HNSW 每次最多回 ef_search 筆；有來源、日期篩選時開 iterative_scan，篩掉的不足額會再往下找
                cur.execute("SET LOCAL hnsw.ef_search = %s", (max(100, k * 2),))
                cur.execute("SET LOCAL hnsw.iterative_scan = relaxed_order")
                cur.execute(
                    f"SELECT doc_id, embedding <=> %s::vector AS distance FROM {self.table}"
                    f" WHERE source = ANY(%s) AND published_at >= %s AND published_at < %s"
                    f" ORDER BY distance LIMIT %s",
                    (vector, list(sources), start, end, k))
                rows = cur.fetchall()
            con.rollback()   # 只讀；SET LOCAL 隨交易結束
        finally:
            con.close()
        # iterative_scan=relaxed_order 不保證結果照距離排序：先排好再去重，每篇才會留到最近的那段
        best: dict[str, float] = {}
        for doc_id, distance in sorted(rows, key=lambda row: float(row[1])):
            best.setdefault(doc_id, float(distance))
        return list(best.items())

    def search(self, query: str, *, sources: Sequence[str], start: str, end: str, k: int,
               max_distance: Optional[float] = None, max_wait_seconds: Optional[float] = None) -> list[str]:
        return [doc_id for doc_id, distance in
                self.search_with_distances(query, sources=sources, start=start, end=end, k=k,
                                           max_wait_seconds=max_wait_seconds)
                if max_distance is None or distance <= max_distance]
