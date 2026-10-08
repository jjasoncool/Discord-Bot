"""情報搜尋（官網公告、官方 FB、PTT、巴哈）的設定。

搜尋本體在 `services/search/`，MCP 殼在 `llm/mcp_server.py`；兩邊都讀這一份。
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

_SRC_DIR = Path(__file__).resolve().parent.parent


class SearchSettings(BaseSettings):
    #: scraper 的資料庫；只用唯讀方式開（`mode=ro`，見 `services.search.index`）
    articles_db_path: Path = Path("/app/scraper/articles.db")
    #: 搜尋索引：從 articles.db 建出來的衍生資料，刪掉會自動重建，不算使用者資料
    index_path: Path = _SRC_DIR / "services" / "search" / "data" / "search_index.db"

    #: 每種來源最多回幾筆，避免論壇的量把官方公告淹掉
    per_source_limit: int = 5
    #: 一次搜尋最多回幾筆（各來源加總）
    max_limit: int = 20
    #: 每段候選（全詞、模糊、短詞）最多撈幾筆再排序
    candidate_pool: int = 300
    #: 搜尋結果附的摘要長度（字）
    snippet_chars: int = 160
    #: 讀全文時每頁的字數
    fetch_page_chars: int = 4000
    #: 兩次增量同步的最短間隔（秒）；連續搜尋時不必每次都掃一遍 scraper 的資料庫
    sync_min_interval_seconds: float = 60.0

    # ---------- 向量（語意）搜尋：P3 ----------
    # 開關在 settings/switches.json 的 search_vector_mode（改了就生效）；這裡只放細項參數
    #: pgvector 的邏輯表名（實體表名由 HYBRID_RETRIEVAL_SETTINGS.physical_table 加前綴並消毒）
    vector_table: str = "search_chunks"
    #: 只把這天之後的文章算向量。先做最近的（比例原則，使用者 2026-10-08），舊資料之後再補
    vector_since: str = "2026-01-01"
    #: 巴哈只算這幾類討論串（標題開頭的【】）；閒聊串量大、答案少
    vector_bahamut_categories: tuple[str, ...] = ("攻略", "心得", "情報", "問題")
    #: 切段：每段最多幾個字、相鄰兩段重疊幾個字（答案剛好跨在切點上時，至少有一段是完整的）
    chunk_max_chars: int = 500
    chunk_overlap_chars: int = 80
    #: 一次送幾段去算向量
    embed_batch_size: int = 16
    #: 向量那一路撈幾段（同一篇多段只算一次，所以實際文件數會更少）
    vector_candidates: int = 60
    #: 向量那一路的門檻：餘弦距離（1－相似度）超過就不算，None＝不設。0.35 是 2026-10-08 依距離分布與考卷
    #: A／B 兩半選出來的（沒門檻時，不相關的新文章會把關鍵字找對的結果擠下去），見 AI_HANDOFF_AND_TODO.md 的 mcp-search-tools 區塊
    vector_max_distance: Optional[float] = 0.35
    #: 名次融合（RRF）的 k 與兩路權重
    rrf_k: int = 60
    lexical_weight: float = 1.0
    vector_weight: float = 1.0
    #: 查詢要加的任務說明：這類 embedding 模型要求「查詢」前面寫明任務（文件本身不加），
    #: 少了這段，問句和答案段落的相似度會明顯變差。依模型建議用英文寫
    query_instruction: str = (
        "Given a question from a game community member, retrieve forum posts or official announcements "
        "that answer it"
    )

    #: 搜尋時算問句向量、重新排序要排 GPU 的隊；最多等幾秒，等不到這次就跳過那一步（bot 正在產生長回答時，
    #: 不讓搜尋跟著乾等一兩分鐘）
    query_gpu_wait_seconds: float = 10.0

    # ---------- 重新排序（reranker）：P4 ----------
    # 開關在 settings/switches.json 的 search_rerank_mode；模型名稱在 llm_runtime_config.json 的 rerank_model
    #: 重排前幾篇（關鍵字＋向量合併後的名次）；越多越慢，每篇要讀一次
    rerank_candidates: int = 30
    #: 每篇送給 reranker 的長度（字）：標題＋文件裡和問題最相關的那一段
    rerank_passage_chars: int = 500

    model_config = SettingsConfigDict(env_prefix="SEARCH_", extra="ignore", frozen=True)


SEARCH_SETTINGS = SearchSettings()
