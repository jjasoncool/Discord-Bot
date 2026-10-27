"""情報搜尋（官網公告、官方 FB、PTT、巴哈）的設定。

搜尋本體在 `services/search/`，MCP 殼在 `llm/mcp_server.py`；兩邊都讀這一份。
"""
from __future__ import annotations

from datetime import time
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

from sys_settings.paths import ARTICLES_DB


class SearchSettings(BaseSettings):
    #: scraper 的資料庫；只用唯讀方式開（`sys_settings.paths.sqlite_readonly_uri`）
    articles_db_path: Path = ARTICLES_DB
    #: 搜尋索引：從 articles.db 建出來的衍生資料，刪掉會自動重建，不算使用者資料。
    #: 容器內固定在 `/search_data`（主機端是 repo 的 `cache/search-mcp/`，docker-compose 只掛給 search-mcp），不放 src/：
    #: 幾百 MB 的衍生資料不該跟程式碼混在一起。路徑放在根目錄那一層，沒掛這個資料夾的容器用到時會直接失敗，不會悄悄另建一份
    index_path: Path = Path("/search_data/search_index.db")

    #: 每種來源最多回幾筆，避免論壇的量把官方公告淹掉
    per_source_limit: int = 5
    #: 一次搜尋最多回幾筆（各來源加總）
    max_limit: int = 20
    #: 每段候選（全詞、模糊、短詞）最多撈幾筆再排序
    candidate_pool: int = 300
    #: 搜尋結果附的摘要長度（字）
    snippet_chars: int = 160
    #: 讀全文時每頁的字數。不能超過 bot 給模型的全文上限（AskAIIntelSettings.fetch_max_chars）：否則 bot 截掉的
    #: 每頁後段，翻頁也讀不到（2026-10-09 最後審查：原本 4000 對 2500，維護預告、版本說明的後段都漏掉）
    fetch_page_chars: int = 2500
    #: 兩次增量同步的最短間隔（秒）；連續搜尋時不必每次都掃一遍 scraper 的資料庫
    sync_min_interval_seconds: float = 60.0

    # ---------- 向量（語意）搜尋：P3 ----------
    # 開關在 settings/switches.json 的 search_vector_mode（改了就生效）；這裡只放細項參數
    #: pgvector 的邏輯表名（實體表名由 HYBRID_RETRIEVAL_SETTINGS.physical_table 加前綴並消毒）
    vector_table: str = "search_chunks"
    #: 只把這天之後的文章算向量。先做最近的（最常被問到），舊資料之後再補
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
    #: A／B 兩半選出來的（沒門檻時，不相關的新文章會把關鍵字找對的結果擠下去）
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

    #: 搜尋時算問句向量、重新排序要排 GPU 的隊。這是**一次搜尋共用**的等待額度（秒）：向量那步等不到，重排就不再等；
    #: 向量那步花掉的時間也從額度扣（bot 正在產生長回答時，不讓搜尋跟著乾等一兩分鐘；2026-10-08 實測兩步各等 10 秒白等 20 秒）
    query_gpu_wait_seconds: float = 10.0
    #: 一次搜尋超過這麼多秒，就把每一步（同步、向量、關鍵字、重排）花的時間寫進 log，找出慢在哪裡
    slow_search_log_seconds: float = 3.0

    # ---------- 重新排序（reranker）：P4 ----------
    # 開關在 settings/switches.json 的 search_rerank_mode；模型名稱在 llm_runtime_config.json 的 rerank_model
    #: 重排前幾篇（關鍵字＋向量合併後的名次）；越多越慢，每篇要讀一次
    rerank_candidates: int = 30
    #: 每篇送給 reranker 的長度（字）：標題＋文件裡和問題最相關的那一段
    rerank_passage_chars: int = 500

    # ---------- 常駐服務（docker-compose 的 search-mcp）----------
    #: MCP 走 HTTP 時聽的位址與 port。容器裡要聽 0.0.0.0，主機那端由 compose 只綁 127.0.0.1
    mcp_host: str = "0.0.0.0"
    mcp_port: int = 8765
    #: 允許的 Host 標頭（MCP 套件防 DNS rebinding）：本機連進來、或同一個 docker 網路用服務名稱連
    mcp_allowed_hosts: tuple[str, ...] = ("127.0.0.1:*", "localhost:*", "search-mcp:*")
    #: 收到停止訊號後，還開著的連線最多等幾秒就關掉。Claude Code 的 MCP 客戶端會一直連著，
    #: 不設上限的話 uvicorn 會等到 Docker 的 10 秒 SIGKILL，收尾都沒跑
    mcp_shutdown_grace_seconds: float = 2.0
    #: 背景每幾秒同步一次（`services.search.background`）。比搜尋時的同步間隔（`sync_min_interval_seconds`）短，
    #: 搜尋時就幾乎輪不到自己同步；巴哈爬蟲每小時重存約 2 萬列，趁剛寫完還在記憶體快取時先消化
    background_sync_seconds: float = 50.0
    #: 每日維護（同步索引、補算新文章的向量）的時刻；過了 `nightly_deadline` 還沒做就等明天，
    #: 不在 04:00～07:30 維護時段（人格萃取、persona agent 用模型）裡搶 GPU
    nightly_at: time = time(3, 0)
    nightly_deadline: time = time(4, 0)

    model_config = SettingsConfigDict(env_prefix="SEARCH_", extra="ignore", frozen=True)


SEARCH_SETTINGS = SearchSettings()
