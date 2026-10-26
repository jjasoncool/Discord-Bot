"""給 /askai 與插話撈「上下文」：這個頻道最近與相關的聊天行，和在場、被問到的人的人物卡。

架構定位：服務層（`llm/retrievers`）。上層：功能層與介面層（/askai 的 `commands.llm_commands`、插話的
`llm.ambient.ambient_reply`）。下層：pgvector（`LLMServiceSettings.pgvector_connect`）、LlamaIndex 向量索引、
`llm.persona.persona_card_builder`（卡片）、`llm.persona.member_names`（名字對照）、`utils.rank_fusion`（混合排名）。
不 import discord：Discord 物件由上層傳進來，這裡只讀屬性（守衛 `test_layering`）。

介面：
- `retrieve_discord_context(channel, question, ...)`：頻道近期訊息 → 最近幾則＋關鍵字與向量混合挑出的相關幾則，
  bot 自己的回覆另一段；回 (context, bot_context, meta)。
- `retrieve_rag_context_sync(question, guild_id, requester, participants, logger, top_k, mentioned_user_ids, member_names)`：
  人物卡。四段：`_parse_profile_question`（誰在問、提到誰、在場誰）→ `_collect_profile_candidates`
  （三路 SQL：本人、在場的人、提到的人與別名；一路語意 `_vector_profile_route`）→ `_dedup_profile_docs`
  → `_profile_cards_context`（每人一張卡、裁到額度）；回 (context, meta)，meta 是各段的計數。
- `search_chat(...)`：聊天向量庫的語意搜尋（/askai 的窗內重排與插話回憶的全庫搜尋都走這支），同一人同一句只回一則。

規則：
- 同步、會碰 DB：呼叫端放到執行緒（`asyncio.to_thread`／executor）。`retrieve_discord_context` 是 async，BM25、向量、
  重排都丟 executor。
- 重複與雜訊在檢索端處理、不在寫入端。/askai：視窗先用 `_collapse_window` 把同一人同一句（`tokenization.dedup_key`）
  折成最新的一則，關鍵字與向量兩路都吃折好的清單（各折各的會留到不同的那則，融合時兩路分數被拆開）；相關名額再擋
  純表情／貼圖／連結的行（`emoji_text_utils`）、不分作者同一句只留一則。插話回憶的全庫搜尋沒有視窗可先折，由
  `search_chat(collapse=True)` 折。保底的最近幾則不經這些閘。
- 重排（reranker）由呼叫端決定要不要給（開關在指令層看）；這層不 import `services.search`，拿到的是 `rerank(query,
  passages)` 介面。重排失敗照融合名次，/askai 不能因此失敗。
- 每一路檢索失敗只記 WARNING、其他路照常；向量索引跨呼叫共用（`_VECTOR_INDEX_CACHE`），不每次重建。
- 呼叫端若已把問句裡的 <@id> 換成名字，`mentioned_user_ids` 要顯式傳入，這裡重抽會抽不到。

例外與決策：去重後的排序只認本人 → 提到的人 → 語意，在場者那一路沒有名次、排最後。拆段時刻意沒改：卡片產生器
自己依來源加分，候選順序不影響卡片順序；要改就連排序表與測試一起改。
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import logging
import json
import math
import re
import threading
from collections import defaultdict
from dataclasses import dataclass
from datetime import timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # 只給型別註解；服務層不認 discord，Discord 物件由指令層傳進來（守衛 test_layering）
    import discord

from llm.client.lemonade_gate import gpu_exclusive
from llm.preprocess.chat_line import format_chat_line
from llm.preprocess.emoji_text_utils import is_emoji_or_symbol_only, is_link_only
from llm.preprocess.tokenization import dedup_key, tokenize_for_retrieval, tokens_for_debug
from llm.persona.member_names import display_names, match_members
from llm.persona.persona_card_builder import (
    PERSONA_MAX_PARTICIPANTS,
    PERSONA_MAX_CARDS,
    classify_persona_intent,
    expand_alias_candidates,
    extract_mentioned_user_ids,
    build_persona_cards,
    format_persona_cards_for_context,
    normalize_alias_text,
)
from sys_settings.pgvector_settings import HYBRID_RETRIEVAL_SETTINGS
from utils.rank_fusion import rrf_score
from sys_settings.llm_settings import (
    LLMServiceSettings,
    load_llm_runtime_config,
)

try:
    from rank_bm25 import BM25Okapi
except Exception:  # pragma: no cover - 依賴可能在部份環境尚未安裝
    BM25Okapi = None

try:
    from llama_index.core import VectorStoreIndex
    from llm.client.embedding_client import SafeLLMEmbedding
    from llama_index.vector_stores.postgres import PGVectorStore
except Exception:  # pragma: no cover - 依賴可能在部份環境尚未安裝
    VectorStoreIndex = None
    SafeLLMEmbedding = None
    PGVectorStore = None

try:
    import psycopg2
except Exception:  # pragma: no cover - 依賴可能在部份環境尚未安裝
    psycopg2 = None


LLM_SETTINGS = LLMServiceSettings()
_EMBED_MODEL: Any | None = None
_EMBED_MODEL_NAME: str | None = None
_PERSISTED_MESSAGE_IDS: set[str] = set()

# 跨呼叫共用的 pgvector index。key=(table_name, embed_model_name)。
# 原本 _retrieve_rag_context_impl 每次呼叫都 new PGVectorStore + VectorStoreIndex，
# 造成 /askai 每次都重開 Ollama HTTP 連線；高頻互動下累積到 Windows ephemeral port 池會塞爆。
_VECTOR_INDEX_CACHE: dict[tuple[str, str], Any] = {}
# retrieve_rag_context_sync 走 run_in_executor，多個 /askai 並發可能競爭 index cache init
_vector_index_lock = threading.Lock()


def _pgvector_connect():
    """開一條 pgvector(Postgres) 連線。

    連線憑證集中一處：chat 向量搜尋（search_chat）與 member_profile 的 persona SQL
    各 stage 都用同一份 creds，避免散落多處 drift。回傳 connection 物件，呼叫端照舊
    `with _pgvector_connect() as conn:` 使用（語意與原本 inline psycopg2.connect 相同）。
    """
    return LLM_SETTINGS.pgvector_connect()


def _load_embed_model_name() -> str:
    """從 runtime 設定讀取 embedding model，失敗則回退預設。"""
    runtime_config = load_llm_runtime_config(LLM_SETTINGS.llm_runtime_model_path)
    return runtime_config.embed_model


def _get_embed_model(logger: logging.Logger) -> Any | None:
    """延遲初始化 Embedding 模型，避免啟動時阻塞。"""
    global _EMBED_MODEL, _EMBED_MODEL_NAME
    runtime_config = load_llm_runtime_config(LLM_SETTINGS.llm_runtime_model_path)
    embed_model_name = runtime_config.embed_model
    if _EMBED_MODEL is not None and _EMBED_MODEL_NAME == embed_model_name:
        return _EMBED_MODEL

    if SafeLLMEmbedding is None:
        logger.warning("SafeLLMEmbedding 尚未可用，向量檢索將退化為 BM25。")
        return None

    try:
        from llm.client.embedding_client import make_safe_llm_embedding
        _EMBED_MODEL = make_safe_llm_embedding(
            settings=LLM_SETTINGS,
            runtime_config=runtime_config,
        )
        _EMBED_MODEL_NAME = embed_model_name
    except Exception as exc:
        logger.warning("初始化 SafeLLMEmbedding 失敗，改用 BM25: %s", exc)
        _EMBED_MODEL = None
        _EMBED_MODEL_NAME = None

    return _EMBED_MODEL


def _get_or_build_vector_index(table_name: str, logger: logging.Logger) -> Any | None:
    """取得跨呼叫共用的 pgvector VectorStoreIndex。

    key = (table_name, embed_model_name)；embed model 換掉時自動重建。
    原本 /askai 每次檢索都 new PGVectorStore + VectorStoreIndex，每次都開新的
    Ollama HTTP 連線；高頻互動會塞爆 Windows ephemeral port 池。
    """
    if VectorStoreIndex is None or PGVectorStore is None:
        return None

    embed_model = _get_embed_model(logger)
    if embed_model is None:
        return None

    cache_key = (table_name, _EMBED_MODEL_NAME or "")
    # Fast path：無鎖 double-check
    cached = _VECTOR_INDEX_CACHE.get(cache_key)
    if cached is not None:
        return cached

    with _vector_index_lock:
        cached = _VECTOR_INDEX_CACHE.get(cache_key)
        if cached is not None:
            return cached

        # embed_model 名稱變了，清掉同 table 的舊 key
        for key in list(_VECTOR_INDEX_CACHE.keys()):
            if key[0] == table_name and key[1] != (_EMBED_MODEL_NAME or ""):
                _VECTOR_INDEX_CACHE.pop(key, None)

        try:
            vector_store = LLM_SETTINGS.pgvector_vector_store(
                table_name=table_name,
                embed_dim=HYBRID_RETRIEVAL_SETTINGS.pgvector_embed_dim,
            )
            index = VectorStoreIndex.from_vector_store(
                vector_store=vector_store,
                embed_model=embed_model,
            )
            _VECTOR_INDEX_CACHE[cache_key] = index
            logger.info(
                "context_retriever: 建立 VectorStoreIndex table=%s embed_model=%s",
                table_name, _EMBED_MODEL_NAME,
            )
            return index
        except Exception as exc:
            logger.warning("建立 VectorStoreIndex 失敗 table=%s: %s", table_name, exc)
            return None


def _collapse_key(author_id: Any, text: str, message_id: Any) -> tuple[str, str]:
    """折疊用的鍵：同一作者＋`dedup_key`。沒有任何字詞字元的（「????」「……」）不折，各自算一句，不然不相干的純標點會被湊成一組。"""
    key_text = dedup_key(text)
    return (str(author_id or ""), key_text if key_text else f"#{message_id}")


def _collapse_window(messages: list[discord.Message]) -> tuple[list[discord.Message], dict[str, str]]:
    """視窗裡同一人同一句只留最新的一則，順序照舊（舊 → 新）；另回「每則 id → 它那一組的代表 id」的對照表。

    折疊只做這一次、放在關鍵字與向量兩路之前：兩路各折各的會留到不同的那則，融合時本該加在一起的兩路分數
    被拆到兩個 id，被人重複講過的句子反而排在一次性發言後面。留最新的，脈絡上離提問最近。
    向量那一路還是要拿全部的 id 去查（最新那則可能還在寫入緩衝裡、沒進向量庫，舊的那則才找得到），查到的再用
    對照表換成代表。
    """
    latest: dict[tuple[str, str], Any] = {}
    members: dict[tuple[str, str], list[str]] = {}
    for msg in messages:
        text = (msg.content or "").strip()
        if not text:
            continue
        key = _collapse_key(getattr(getattr(msg, "author", None), "id", ""), text, msg.id)
        latest[key] = msg
        members.setdefault(key, []).append(str(msg.id))
    representative = {mid: str(latest[key].id) for key, mids in members.items() for mid in mids}
    kept = {str(msg.id) for msg in latest.values()}
    return [msg for msg in messages if str(msg.id) in kept], representative


def _build_bm25_rank(
    *,
    question: str,
    messages: list[discord.Message],
) -> dict[str, int]:
    """建立 BM25 排名（message_id -> rank）。"""
    # 為什麼回傳 rank 而不是原始分數？
    # - 因為後續 RRF 需要的是「排名」，不是各家檢索器的原始 score。
    # - 這樣可以避免 BM25 與 Vector 的分數尺度不同，導致融合失真。
    #
    # 小範例（示意）
    # question:「昨天楓谷活動有加倍掉寶嗎」
    # m2:「昨天活動地圖真的有掉寶加倍」-> BM25 rank 1
    # m4:「Maple 活動加倍時間到 12 點」 -> BM25 rank 2
    # 輸出：{"m2": 1, "m4": 2, ...}
    if BM25Okapi is None:
        return {}

    # `corpus_tokens` 與 `ordered_ids` 必須一一對齊：
    # - corpus_tokens[i] 是第 i 筆文件的 token 清單
    # - ordered_ids[i]   是同一筆文件的 message_id
    # 這樣 BM25 回傳分數陣列後，才能正確 map 回 Discord 訊息。
    corpus_tokens: list[list[str]] = []
    ordered_ids: list[str] = []
    for msg in messages:
        # 1) 先做最小清洗：避免空白/None 進入索引，降低雜訊。
        text = (msg.content or "").strip()
        if not text:
            continue

        # 2) 將文字轉成檢索 token（中英數 + 中文 n-gram）。
        #    BM25 是以 token 為單位算匹配，不是直接比原句字串。
        tokens = list(tokenize_for_retrieval(text))

        # 3) 若 token 為空，表示這筆內容對 BM25 無可用訊號，跳過。
        if not tokens:
            continue

        # 4) 保持「token 與 message_id 同步 append」的對齊關係。
        corpus_tokens.append(tokens)
        ordered_ids.append(str(msg.id))

    # 若語料全被過濾，直接回空，避免建立空 BM25 模型。
    if not corpus_tokens:
        return {}

    # query 也要走同一套 tokenization，才能在同一向量空間匹配。
    query_tokens = list(tokenize_for_retrieval(question))

    # 問題本身若沒有任何可用 token（例如全符號），就無法做 BM25 匹配。
    if not query_tokens:
        return {}

    # 5) 建立 BM25 模型並對 query 算每一筆文件分數。
    #    回傳的 `scores` 與 `corpus_tokens` 是同索引順序。
    bm25 = BM25Okapi(corpus_tokens)
    scores = bm25.get_scores(query_tokens)

    # 6) 依分數由高到低排序。
    #    這裡先轉成 (message_id, score) 方便後續轉 rank map。
    ranked = sorted(
        zip(ordered_ids, scores),
        key=lambda x: float(x[1]),
        reverse=True,
    )

    # 7) 為了給 RRF 融合，最終輸出「排名」而不是 raw score：
    #    - 不同檢索器（BM25/Vector）score 尺度不同
    #    - rank 更容易跨檢索器融合，降低尺度不一致問題
    bm25_rank: dict[str, int] = {}
    current_rank = 1
    for message_id, score in ranked:
        # 分數 <= 0 代表幾乎無匹配訊號，排除噪音文件。
        if float(score) <= 0:
            continue
        bm25_rank[message_id] = current_rank
        current_rank += 1

    # 範例（概念）：
    # ranked = [(m2, 4.2), (m4, 3.8), (m1, 0.0)]
    # -> bm25_rank = {"m2": 1, "m4": 2}
    # m1 因 score<=0 被濾掉，不進入後續 RRF。
    return bm25_rank


#: 折疊前多撈幾倍：同一句的向量幾乎相同、名次連號，只撈 limit 筆再折會剩不到幾則；距離排序的成本在掃描，不在筆數
_COLLAPSE_OVERFETCH = 4
#: 全庫搜尋的 hnsw.ef_search（pgvector 上限）。聊天表裡同一句話重複幾十次、向量一模一樣，HNSW 圖裡這種點只跟彼此相連、
#: 從外面進去的邊很少，搜尋束太窄會整團繞過：實測 ef 200 時「臥槽」那 72 列一列都沒回來、400 回 2 列、1000 回 70 列；
#: 熱快取下 1000 只多花約 20 ms（4～6 ms → 15～29 ms），冷快取的十幾秒是磁碟讀索引頁、和 ef 無關
_FULL_CORPUS_EF_SEARCH = 1000
#: 向量欄名只能長這樣（直接拼進 SQL）
_EMBEDDING_COLUMN = re.compile(r"^[a-z_][a-z0-9_]*$")


def _collapse_repeats(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """距離由近到遠的候選，同一作者同一句（`_collapse_key`）只留一則，裁到 limit。

    名次取該組最近的那筆、距離也記那筆的（查詢對上的是它）；代表取最新的那則（message_id 最大；同一句的向量幾乎相同，
    挑哪則都在同一個距離附近，最新的對插話回憶的新近度最有利，也和 /askai 視窗折疊留最新的一致）；
    `repeat_count` 記它在這批裡出現幾次。不同作者的同一句各自保留：幾個人都講過是訊號，不是重複。
    計數只數撈回來的這批（`_COLLAPSE_OVERFETCH` 倍），不是全庫。
    """
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    order: list[tuple[str, str]] = []
    for row in rows:
        key = _collapse_key(row["author_id"], row["text"], row["message_id"])
        rep = groups.get(key)
        if rep is None:
            groups[key] = dict(row, repeat_count=1)
            order.append(key)
            continue
        count = rep["repeat_count"] + 1
        newest = max(rep, row, key=lambda r: (len(r["message_id"]), r["message_id"]))
        rep = dict(newest, repeat_count=count)
        if "distance" in groups[key]:
            rep["distance"] = groups[key]["distance"]
        groups[key] = rep
    return [groups[key] for key in order][:limit]


def search_chat(
    *,
    question: str,
    limit: int,
    logger: logging.Logger,
    candidate_ids: list[str] | None = None,
    channel_id: str | None = None,
    before_timestamp: str | None = None,
    author_id: str | None = None,
    return_meta: bool = False,
    min_chars: int | None = None,
    collapse: bool = True,
    embedding_column: str = "embedding",
):
    """對 discord_chat 向量庫做語意搜尋。

    這是 chat 語意搜尋的統一入口（facade）。/askai 的窗內重排與全庫歷史搜尋都走這支：

    - candidate_ids 提供（/askai 現況）→ `message_id = ANY(...)` 限定在這批候選內重排
      （窗內重排，行為等價）。
    - candidate_ids=None → 開放全庫語意搜尋（歷史搜尋）。
      ⚠ chat 文件未存 guild_id，全庫搜尋跨群安全需另帶 channel_id 收斂（見下）。
    - channel_id：把結果收斂到單一頻道（chat 文件有 channel_id、無 guild_id）。
    - before_timestamp（ISO 字串）：只取早於此時刻的訊息，用來排除近窗（chat metadata 的
      timestamp 為 msg.created_at.isoformat()，帶 +00:00，字串 `<` 即時序比較）。
    - author_id：只取該作者說的訊息（callback target 模式用——撈「目標本人」原話）。
    - min_chars：只取 `length(text) >= min_chars` 的。插話回憶把太短的擋在 SQL 裡，候選池才不會被反應詞佔掉
      （全表 42.6% 不到 8 字，以前撈 25 筆有 45% 在 Python 端才被丟）。
    - collapse（預設開）：同一作者、`dedup_key` 相同的文字只留距離最近的一則，`repeat_count` 記這批候選裡它出現幾次
      （多撈 `_COLLAPSE_OVERFETCH` 倍再折，不是全庫計數）。同一句的向量幾乎相同、名次連號，不折的話一個人貼過幾千次
      的表情描述能把候選池佔滿。
    - embedding_column：查哪個向量欄（只給評估程式用：重算向量期間拿同一組題對影子欄 embedding_v2 比對）；
      只接受小寫英數與底線，正式流程一律預設的 embedding。

    回傳格式由 return_meta 決定（兩種都先在 Python 端照距離排好：建了 HNSW 之後 iterative_scan 的回傳順序不保證）：
    - return_meta=False（預設，/askai 用）→ list[str]：message_id 由近到遠。
    - return_meta=True（callback 用）→ list[dict]：{message_id, text, distance, timestamp, author_id, repeat_count}，由近到遠。

    回空 list 代表無結果或降級（psycopg2 缺、embedding/連線失敗等），caller 自行決定 fallback。
    """
    if psycopg2 is None:
        return []
    if not _EMBEDDING_COLUMN.match(embedding_column or ""):
        raise ValueError(f"embedding_column 只能是小寫英數與底線：{embedding_column!r}")

    embed_model = _get_embed_model(logger)
    if embed_model is None:
        return []

    # 指定了候選集卻是空的 → 無可搜（與舊行為一致：訊息全空時回空）
    if candidate_ids is not None and not candidate_ids:
        return []

    try:
        query_embedding = embed_model.get_query_embedding(question)
    except Exception as exc:
        logger.warning("pgvector chat 搜尋嵌入失敗（降級）: %s", exc)
        return []

    if not query_embedding:
        return []

    try:
        table_name = HYBRID_RETRIEVAL_SETTINGS.get_chat_table_name()
    except Exception as exc:
        logger.warning("取得 chat table name 失敗: %s", exc)
        return []

    physical_table = HYBRID_RETRIEVAL_SETTINGS.physical_table(table_name)
    # pgvector 的向量 literal 需以 '[v1,v2,...]' 字串形式帶入再 cast 成 vector。
    vector_literal = "[" + ",".join(f"{float(v):.6f}" for v in query_embedding) + "]"

    # 動態組 SELECT/WHERE；params 嚴格按 SQL 內 %s 出現順序（SELECT → WHERE → ORDER BY → LIMIT）。
    # 折疊要看作者與文字、排序要看距離（HNSW 的 iterative_scan 不保證回傳順序），所以一律撈回來；
    # dist 的 %s 出現在 SELECT，必須最先 append（在 WHERE params 之前）
    select_cols = ["metadata_->>'message_id' AS mid", "text", "metadata_->>'author_id' AS author",
                   f"{embedding_column} <=> %s::vector AS dist", "metadata_->>'timestamp' AS ts"]
    params: list[Any] = [vector_literal]
    where = [f"{embedding_column} IS NOT NULL"]
    if HYBRID_RETRIEVAL_SETTINGS.chat_table_is_shared():
        # 只有聊天表和別的來源共用時才篩 doc_type。專用表不篩：metadata_->>'doc_type' 沒有統計資料，規劃器會估成
        # 只有 0.5% 的列符合、算出向量索引要撈兩萬筆才湊得滿，於是改走全表掃描（全庫 top-100 從毫秒變成一百多秒）
        where.append("metadata_->>'doc_type' = %s")
        params.append(HYBRID_RETRIEVAL_SETTINGS.get_source("discord_chat").doc_type)
    if min_chars:
        where.append("length(text) >= %s")
        params.append(int(min_chars))
    if candidate_ids is not None:
        where.append("metadata_->>'message_id' = ANY(%s)")
        params.append(candidate_ids)
    if channel_id is not None:
        where.append("metadata_->>'channel_id' = %s")
        params.append(channel_id)
    if before_timestamp is not None:
        where.append("metadata_->>'timestamp' < %s")
        params.append(before_timestamp)
    if author_id is not None:
        where.append("metadata_->>'author_id' = %s")
        params.append(author_id)
    params.append(vector_literal)      # ORDER BY embedding <=> %s::vector
    fetch_limit = max(1, limit) * (_COLLAPSE_OVERFETCH if collapse else 1)
    params.append(fetch_limit)         # LIMIT %s

    sql = f"""
        SELECT {', '.join(select_cols)}
        FROM {physical_table}
        WHERE {' AND '.join(where)}
        ORDER BY {embedding_column} <=> %s::vector
        LIMIT %s
    """

    try:
        with _pgvector_connect() as conn:
            with conn.cursor() as cur:
                # 聊天表建了 HNSW 索引之後才有作用，沒索引時設了無害：索引一次最多回 ef_search 筆，再套頻道、時間、
                # 作者的篩選會不足額；iterative_scan 讓它不足時繼續往外找（同 services/search/vectors.py）。
                # 全庫搜尋一律開到上限（理由在 _FULL_CORPUS_EF_SEARCH）；窗內重排走 message_id 的索引，這個值用不到。
                # SET LOCAL 只活在這個交易裡
                ef_search = _FULL_CORPUS_EF_SEARCH if candidate_ids is None else min(1000, max(100, 2 * fetch_limit))
                cur.execute("SET LOCAL hnsw.ef_search = %s", (ef_search,))
                cur.execute("SET LOCAL hnsw.iterative_scan = relaxed_order")
                cur.execute(sql, tuple(params))
                rows = cur.fetchall()
    except Exception as exc:
        logger.warning("pgvector chat 搜尋查詢失敗（降級）: %s", exc)
        return []

    found: list[dict[str, Any]] = []
    for mid, text, author, dist, ts in rows:
        if not mid:
            continue
        found.append({
            "message_id": str(mid), "text": text or "", "author_id": str(author) if author else "", "repeat_count": 1,
            "distance": float(dist) if dist is not None else None, "timestamp": ts,
        })
    found.sort(key=lambda item: (item["distance"] is None, item["distance"] or 0.0))   # 近 → 遠；沒距離的排最後
    found = _collapse_repeats(found, max(1, limit)) if collapse else found[: max(1, limit)]
    if return_meta:
        return found
    return [item["message_id"] for item in found]


def _build_vector_rank(
    *,
    question: str,
    messages: list[discord.Message],
    candidate_pool: int,
    logger: logging.Logger,
    representative: dict[str, str] | None = None,
) -> dict[str, int]:
    """建立向量檢索排名（message_id -> rank）— /askai 窗內重排，薄包 search_chat。

    設計意圖：BM25 負責字面，Vector 負責語意；兩路結果交給 RRF 融合。
    讀取 `store_chat` 寫入端累積的既有 embedding，避免每次 /askai 都重跑
    100 則訊息的 in-memory embedding（GIL 佔用 + Ollama HTTP 爆量）。

    Buffer gap：`store_chat` 有 30 筆/5 分鐘 buffer，極新的訊息可能尚未
    flush 到 pgvector，會缺 vector rank。但 `min_recent_context` 會無條件把
    最近 N 則選進 context，BM25 rank 也會補，整體召回影響可接受。

    候選 = 本次抓到的視窗訊息（排除空內容），透過 search_chat 的 candidate_ids 限定，
    故為「窗內重排」；要做全庫歷史搜尋改直接呼叫 search_chat(candidate_ids=None)。
    `representative`（`_collapse_window` 的對照表）給了就把查到的 id 換成那一組的代表、同一組只留最好的名次：
    候選要帶全部的 id（代表那則可能還沒進向量庫），名次卻要落在和 BM25 同一則上。
    """
    message_ids = [
        str(msg.id)
        for msg in messages
        if msg.content and msg.content.strip()
    ]
    if not message_ids:
        return {}

    # 重複的副本會佔掉 SQL LIMIT 的名額：多撈「副本數」筆，換成代表後仍裁到 candidate_pool 組
    groups = len({(representative or {}).get(mid, mid) for mid in message_ids})
    ordered = search_chat(
        question=question,
        limit=max(1, min(len(message_ids), candidate_pool + (len(message_ids) - groups))),
        logger=logger,
        candidate_ids=message_ids,
        collapse=False,            # 同一組的代表由對照表決定，不在這裡折
    )
    ranks: dict[str, int] = {}
    for mid in ordered:
        rep = (representative or {}).get(mid, mid)
        if rep not in ranks and len(ranks) < candidate_pool:
            ranks[rep] = len(ranks) + 1
    return ranks


def _build_discord_context_item(msg: discord.Message, tz: timezone) -> dict[str, str]:
    """
    回傳包含元資料的 dict，確保可觀測性與後續 Debug 能力。
    同時將給 LLM 看的文字組合在 'content' 欄位中。

    組行（名字錨點 / emoji 語意化 / 貼圖 / 時間戳）走共用的 format_chat_line，與 ambient /
    日記同一份邏輯。`date` 欄供組裝層做「換日才印日期 header」，content 內的時間戳保留完整
    YYYY-MM-DD（time_only=False）；若日後改成日期 header 模式，把這裡切 time_only=True 即可。
    產出格式範例：[2026-02-26 14:30] 老哥#1234: 昨天抽卡又保底了 :哭哭貓:
    """
    return {
        "role": "user",
        "content": format_chat_line(msg, tz),
        "message_id": str(msg.id),
        "author_id": str(msg.author.id),
        "display_name": getattr(msg.author, "display_name", msg.author.name),
        "channel_id": str(msg.channel.id),
        "date": msg.created_at.astimezone(tz).strftime("%Y-%m-%d"),
    }


async def _rerank_relevant(
    reranker: Any,
    question: str,
    picked: list[tuple[str, float]],
    passages: list[str],
    *,
    min_score: float | None,
    logger: logging.Logger,
    gpu_wait_seconds: float,
    lease_seconds: float,
    gate: Any = None,
) -> tuple[list[str], list[dict[str, Any]]]:
    """融合名次前幾則交給 reranker（問題＋每則一起讀、打分）重排；回 (保留的 message_id 依分數高到低, debug 列)。

    第一關的 BM25 與向量是問題、訊息分開算的，快但粗；reranker 同時讀兩者，看得出「這句剛好在回答這件事」。
    GPU 閘門在這裡拿（bot 行程的 async 閘門：插話、產圖看得到持有者；reranker 本身不再拿鎖），最多等
    `gpu_wait_seconds`，等不到、reranker 壞掉、回傳筆數不對，都照融合名次、debug 列給空（meta 的 reranked_count 會是 0）；
    `min_score` 有給時低於它的不保留，是相關名額的最後一道品質閘。

    「拿閘門＋跑 reranker」包在自己的 task 裡：閘門的租約到期會取消持有者 task，reranker 是同步 HTTP、在執行緒裡
    沒辦法續租，租約要是在 /askai 的工作者 task 上到期，取消的就是工作者本身——發問的人永遠等不到回答、排隊的
    工作者也整個結束。包成獨立 task 之後，被取消的只是重排，照融合名次繼續。
    """
    loop = asyncio.get_running_loop()
    fallback = [mid for mid, _ in picked]
    gate = gate or gpu_exclusive   # 呼叫時才解析，測試換成假閘門

    async def _gated_rerank() -> list[float]:
        async with contextlib.AsyncExitStack() as stack:
            async with asyncio.timeout(gpu_wait_seconds):
                await stack.enter_async_context(gate("askai-rerank", lease_seconds=lease_seconds))
            return await loop.run_in_executor(None, functools.partial(reranker.rerank, question, passages))

    task = asyncio.create_task(_gated_rerank(), name="askai-rerank")
    try:
        await asyncio.wait({task})
    except asyncio.CancelledError:
        task.cancel()   # 外面的工作者被取消（關機、使用者取消）：連重排一起收掉，取消照常往外走
        raise
    if task.cancelled():
        logger.warning("/askai 重排的 GPU 租約（%.0f 秒）到期被取消，照融合名次", lease_seconds)
        return fallback, []
    exc = task.exception()
    if isinstance(exc, TimeoutError):
        logger.info("/askai 重排等 GPU 超過 %.0f 秒，照融合名次", gpu_wait_seconds)
        return fallback, []
    if exc is not None:
        # 重排是加分項，失敗就照融合名次，/askai 不能因此失敗
        logger.warning("/askai 相關訊息重排失敗，照融合名次：%s", exc)
        return fallback, []
    scores = task.result()
    if len(scores) != len(picked):
        logger.warning("/askai 重排回傳 %d 個分數、送了 %d 則，照融合名次", len(scores), len(picked))
        return fallback, []
    # 後端漏掉的文件客戶端會填 -inf、壞掉的可能回 NaN：非有限分數的一律不保留；一個有限分數都沒有就當失敗
    finite = [i for i in range(len(picked)) if math.isfinite(float(scores[i]))]
    if not finite:
        logger.warning("/askai 重排沒有回任何有效分數（%d 則），照融合名次", len(picked))
        return fallback, []
    order = sorted(finite, key=lambda i: -float(scores[i]))
    debug_rows = [
        {"message_id": picked[i][0], "score": round(float(scores[i]), 4), "content": passages[i]} for i in order
    ] + [{"message_id": picked[i][0], "score": None, "content": passages[i]} for i in range(len(picked)) if i not in finite]
    kept = [picked[i][0] for i in order if min_score is None or float(scores[i]) >= min_score]
    return kept, debug_rows


async def retrieve_discord_context(
    interaction: discord.Interaction,
    question: str,
    *,
    max_context_messages: int,
    min_recent_context: int,
    max_relevant_context: int,
    max_context_to_send: int,
    taipei_tz: timezone,
    logger: logging.Logger,
    reranker: Any | None = None,
    rerank_candidates: int | None = None,
    rerank_min_score: float | None = None,
    rerank_gpu_wait_seconds: float = 10.0,
    rerank_lease_seconds: float = 240.0,
) -> tuple[list[dict[str, str]], list[dict[str, str]], dict[str, int]]:
    """從 Discord 歷史訊息檢索上下文：近期保底 + Hybrid 關聯檢索。

    `reranker`（有 `rerank(query, passages) -> list[float]` 的物件，例如情報搜尋的 `LemonadeReranker`，建立時要讓它自己不拿鎖）
    給了就把融合名次前 `rerank_candidates` 則（None＝和相關名額一樣多）交給它連問題一起讀、重新打分，分數低於
    `rerank_min_score` 的不進 prompt（None＝不設門檻）；GPU 閘門在這裡拿，最多等 `rerank_gpu_wait_seconds`。
    回傳 (chat_context, bot_context, meta)。
    """
    # === 核心流程導讀（學習/除錯用） ===
    # 1) 抓歷史訊息（max_context_messages）
    # 2) 先保底最近 N 則（min_recent_context）避免漏掉剛講完的上下文
    # 3) BM25 rank（字面）+ Vector rank（語意）
    # 4) 用 RRF 融合 + 分數門檻過濾（hybrid_min_fused_score）
    # 5) 合併「recent 保底 + relevant 檢索」成最終 context
    # 6) 輸出 meta 與 retrieval_debug，供 prompt log 完整追蹤
    #
    # 範例（示意）
    # question:「昨天楓谷活動是不是有加倍掉寶？」
    # - BM25 可能把「有加倍掉寶」字面最接近的訊息排前面
    # - Vector 可能把「Maple 活動加倍時間」這類語意接近訊息排前面
    # - RRF 融合後，兩者都高的訊息通常會浮到前面
    context: list[dict[str, str]] = []
    bot_context: list[dict[str, str]] = []
    meta = {
        "fetched_count": 0,
        "recent_selected_count": 0,
        "relevant_selected_count": 0,
        "selected_count_before_trim": 0,
        "trimmed_count": 0,
        "sent_count": 0,
        "bot_history_count": 0,
        "relevant_skipped_noise": 0,
        "relevant_skipped_repeat": 0,
        "reranked_count": 0,
    }
    debug = {
        "question_tokens": [],
        "bm25_ranked": [],
        "vector_ranked": [],
        "fused_ranked": [],
        "reranked": [],
    }

    try:
        # 只在伺服器裡有歷史可讀的頻道（文字頻道、thread）抓脈絡；私訊沒有 guild、分類與論壇頻道沒有 history。
        # 看能力不看型別：這層不 import discord。
        channel = interaction.channel
        if getattr(channel, "guild", None) is None or not callable(getattr(channel, "history", None)):
            return context, bot_context, meta

        bot_user_id = interaction.client.user.id if interaction.client.user else None
        all_messages = [
            msg
            async for msg in interaction.channel.history(limit=max_context_messages)
        ]
        history_messages = [msg for msg in all_messages if not msg.author.bot]
        # 自己的回覆：從最近 10 則中用 BM25 挑最相關的 3 則
        bot_candidates = [
            msg for msg in all_messages
            if msg.author.id == bot_user_id and msg.content and msg.content.strip()
        ][:10] if bot_user_id else []
        if bot_candidates and len(bot_candidates) > 3:
            bot_ordered = list(reversed(bot_candidates))  # 舊 -> 新
            bot_bm25 = _build_bm25_rank(question=question, messages=bot_ordered)
            # 取 BM25 rank 最小（最相關）的 3 個 message_id
            top_bot_ids = set(sorted(bot_bm25, key=bot_bm25.get)[:3])
            # 保持時序輸出
            bot_messages = [msg for msg in bot_ordered if str(msg.id) in top_bot_ids]
        else:
            bot_messages = list(reversed(bot_candidates)) if bot_candidates else []
        meta["fetched_count"] = len(history_messages)
        ordered_messages = list(reversed(history_messages))  # 舊 -> 新
        # 同一人同一句只留最新的一則：BM25 吃折好的清單，向量路拿全部 id 去查、查到的換成代表；
        # 保底的最近 N 則仍看未折的視窗
        collapsed_messages, representative = _collapse_window(ordered_messages)

        recent_start_index = max(0, len(ordered_messages) - min_recent_context)
        selected_indices = {
            idx
            for idx, msg in enumerate(ordered_messages)
            if idx >= recent_start_index and msg.content and msg.content.strip()
        }
        meta["recent_selected_count"] = len(selected_indices)

        debug["question_tokens"] = tokens_for_debug(question)

        # 聊天持久化已改由 on_message buffer 機制處理（store_chat.py）
        # 不再在 /askai 流程中同步寫入，避免阻塞 event loop

        # BM25（純 Python CPU 運算，佔 GIL）與 vector（1 次 Ollama embed + pgvector SQL）
        # 都是同步函式；丟到 executor 避免阻塞 event loop（語音 heartbeat / 其他 /askai
        # 會被連累）。asyncio.gather 讓兩者在 thread pool 並行跑。
        loop = asyncio.get_running_loop()
        bm25_rank, vector_rank = await asyncio.gather(
            loop.run_in_executor(
                None,
                functools.partial(
                    _build_bm25_rank,
                    question=question,
                    messages=collapsed_messages,
                ),
            ),
            loop.run_in_executor(
                None,
                functools.partial(
                    _build_vector_rank,
                    question=question,
                    messages=ordered_messages,
                    candidate_pool=HYBRID_RETRIEVAL_SETTINGS.hybrid_candidate_pool,
                    logger=logger,
                    representative=representative,
                ),
            ),
        )
        bm25_weight, vector_weight = HYBRID_RETRIEVAL_SETTINGS.resolve_fusion_weights()

        # 為什麼先整理 message_text_map？
        # - 後續 debug 區塊需要快速以 message_id 找回原文
        # - 避免每次都重新掃描 ordered_messages（降低重複運算）

        message_text_map = {
            str(msg.id): " ".join((msg.content or "").split())
            for msg in ordered_messages
            if msg.content and msg.content.strip()
        }

        debug["bm25_ranked"] = [
            {
                "message_id": message_id,
                "rank": rank,
                "content": message_text_map.get(message_id, ""),
                "tokens": tokens_for_debug(message_text_map.get(message_id, "")),
            }
            for message_id, rank in sorted(bm25_rank.items(), key=lambda x: x[1])
        ]

        debug["vector_ranked"] = [
            {
                "message_id": message_id,
                "rank": rank,
                "content": message_text_map.get(message_id, ""),
            }
            for message_id, rank in sorted(vector_rank.items(), key=lambda x: x[1])
        ]

        # RRF 融合：message_id -> rrf score
        fused_scores: dict[str, float] = defaultdict(float)
        for message_id, rank in bm25_rank.items():
            fused_scores[message_id] += rrf_score(
                rank,
                weight=bm25_weight,
                k=HYBRID_RETRIEVAL_SETTINGS.hybrid_rrf_k,
            )
        for message_id, rank in vector_rank.items():
            fused_scores[message_id] += rrf_score(
                rank,
                weight=vector_weight,
                k=HYBRID_RETRIEVAL_SETTINGS.hybrid_rrf_k,
            )

        index_by_message_id = {str(msg.id): idx for idx, msg in enumerate(ordered_messages)}
        fused_ranked = sorted(fused_scores.items(), key=lambda x: x[1], reverse=True)
        debug["fused_ranked"] = [
            {
                "message_id": message_id,
                "score": round(float(score), 8),
                "content": message_text_map.get(message_id, ""),
            }
            for message_id, score in fused_ranked
        ]
        # 相關名額的品質閘與跨作者折疊：純表情／貼圖／連結的行不佔名額，不同人說的同一句只留融合分最高的那則
        # （同一人的重複在 _collapse_window 已經折掉，這裡的 repeat 計數就是跨作者的）；保底的最近 N 則不經這裡，
        # 剛講完的反應詞照樣看得到。有 reranker 時先多挑幾則，讓它重排後再取名額
        want = max(max_relevant_context, rerank_candidates or 0) if reranker is not None else max_relevant_context
        picked: list[tuple[str, float]] = []
        seen_keys: set[str] = set()
        for message_id, fused_score in fused_ranked:
            # 分數門檻：避免低相關/噪音訊息被送進 prompt；relevant_selected=0 時可考慮調低 hybrid_min_fused_score
            if fused_score < HYBRID_RETRIEVAL_SETTINGS.hybrid_min_fused_score:
                continue
            if message_id not in index_by_message_id:
                continue
            text = message_text_map.get(message_id, "")
            if is_emoji_or_symbol_only(text) or is_link_only(text):
                meta["relevant_skipped_noise"] += 1
                continue
            key = dedup_key(text) or f"#{message_id}"   # 純標點不折，各自算一句
            if key in seen_keys:
                meta["relevant_skipped_repeat"] += 1
                continue
            seen_keys.add(key)
            picked.append((message_id, fused_score))
            if len(picked) >= want:
                break

        relevant_ids = [mid for mid, _ in picked]
        if reranker is not None and len(picked) > 1:
            # 給 reranker 看「誰說的: 內容」：誰說過什麼這類問題，只有內文判不出來
            passages = [
                f"{getattr(ordered_messages[index_by_message_id[mid]].author, 'display_name', '')}: {message_text_map[mid]}"
                for mid, _ in picked
            ]
            relevant_ids, debug["reranked"] = await _rerank_relevant(
                reranker, question, picked, passages, min_score=rerank_min_score, logger=logger,
                gpu_wait_seconds=rerank_gpu_wait_seconds, lease_seconds=rerank_lease_seconds,
            )
            meta["reranked_count"] = sum(1 for row in debug["reranked"] if row["score"] is not None)
        top_relevant_indices = {index_by_message_id[mid] for mid in relevant_ids[:max_relevant_context]}

        meta["relevant_selected_count"] = len(top_relevant_indices)
        selected_indices.update(top_relevant_indices)

        selected_messages = [ordered_messages[idx] for idx in sorted(selected_indices)]

        # 核心修改：以 dict 形式加入全域宣告，保持結構一致性
        if selected_messages:
            channel_id = interaction.channel.id
            context.append({
                "role": "system",
                "content": f"--- 以下為 Discord (頻道ID: {channel_id}) 的聊天紀錄 ---",
                "metadata": "header"
            })

            context.extend(
                _build_discord_context_item(msg, taipei_tz) for msg in selected_messages
            )

        meta["selected_count_before_trim"] = len(context)

        # 確保截斷時保留第一行的宣告 Header
        if len(context) > max_context_to_send + 1:
            meta["trimmed_count"] = len(context) - (max_context_to_send + 1)
            # 保留第一行的宣告，然後接上後面截斷的訊息
            context = [context[0]] + context[-(max_context_to_send):]

        meta["sent_count"] = len(context)
        logger.info(
            "/askai discord context stats: fetched=%s recent=%s relevant=%s selected=%s trimmed=%s sent=%s "
            "bm25_hits=%s vector_hits=%s fused_hits=%s noise_skipped=%s repeat_skipped=%s reranked=%s",
            meta["fetched_count"], meta["recent_selected_count"],
            meta["relevant_selected_count"], meta["selected_count_before_trim"],
            meta["trimmed_count"], meta["sent_count"],
            len(bm25_rank), len(vector_rank), len(fused_scores),
            meta["relevant_skipped_noise"], meta["relevant_skipped_repeat"], meta["reranked_count"],
        )
        # Bot 自身回覆（獨立於 chat_history 額度外）
        if bot_messages:
            bot_context.extend(
                _build_discord_context_item(msg, taipei_tz)
                for msg in reversed(bot_messages)  # 舊 -> 新
            )
            meta["bot_history_count"] = len(bot_context)

    except Exception as exc:
        logger.warning("讀取聊天上下文失敗: %s", exc)

    meta["retrieval_debug"] = debug
    return context, bot_context, meta


def retrieve_rag_context_sync(
    question: str,
    guild_id: int | None,
    requester_user_id: int | None,
    participant_user_ids: list[int] | None,
    logger: logging.Logger,
    top_k: int = 5,
    mentioned_user_ids: list[str] | None = None,
    member_names: dict[str, list[str]] | None = None,
) -> tuple[list[dict[str, str]], dict[str, int | bool | str]]:
    """同步版本，供 run_in_executor 呼叫。

    mentioned_user_ids: 上游已從原始 question（含 <@id>）抽出的 user_id 列表。
        若為 None，內部會從 question 重抽——但若 caller 已把 question 替換成
        display_name（resolved），重抽會失敗，必須顯式傳入。
    member_names: Discord 成員名字（`llm.persona.member_names.member_names_from_guild`）。
        有給時卡片標籤用顯示名稱，問句裡的詞也會比對 Discord 名字找人（「一野」→ 糯糯）。
    """
    return _retrieve_rag_context_impl(
        question=question,
        guild_id=guild_id,
        requester_user_id=requester_user_id,
        participant_user_ids=participant_user_ids,
        logger=logger,
        top_k=top_k,
        mentioned_user_ids=mentioned_user_ids,
        member_names=member_names,
    )


def _retrieve_rag_context_impl(
    *,
    question: str,
    guild_id: int | None,
    requester_user_id: int | None,
    participant_user_ids: list[int] | None,
    logger: logging.Logger,
    top_k: int = 5,
    mentioned_user_ids: list[str] | None = None,
    member_names: dict[str, list[str]] | None = None,
) -> tuple[list[dict[str, str]], dict[str, int | bool | str]]:
    """檢索 member_profile RAG（guild scoped + identity aware + persona cards）。

    四段：解析問句（誰在問、提到誰、在場誰）→ 四路撈候選（三路 SQL、一路語意）→ 去重排序
    → 組卡片並裁到額度。每段各一個函式，`meta` 一路帶著記計數。
    """
    meta: dict[str, int | bool | str] = {
        "enabled": True,
        "intent": "general",
        "sql_identity_hits": 0,
        "sql_participant_hits": 0,
        "sql_alias_hits": 0,
        "vector_hits": 0,
        "dedup_hits": 0,
        "participant_count": 0,
        "cards_generated": 0,
        "cards_sent": 0,
        "selected_count_before_trim": 0,
        "trimmed_count": 0,
        "sent_count": 0,
        "self_match_count": 0,
        "target_match_count": 0,
        "alias_match_count": 0,
    }

    if not question.strip() or not guild_id:
        logger.info("/askai member-profile RAG skipped: empty question or missing guild")
        return [], meta
    source = HYBRID_RETRIEVAL_SETTINGS.get_source("member_profile")
    if source is None:
        meta["enabled"] = False
        logger.info("/askai member-profile RAG skipped: source disabled")
        return [], meta

    q = _parse_profile_question(question, requester_user_id, participant_user_ids, mentioned_user_ids, member_names)
    meta["intent"] = q.intent
    meta["participant_count"] = len(q.participant_ids)

    physical_table = HYBRID_RETRIEVAL_SETTINGS.physical_table(source.table_name)
    collected = _collect_profile_candidates(q, guild_id, physical_table, source.table_name, top_k, logger, meta)
    dedup_docs = _dedup_profile_docs(collected)
    meta["dedup_hits"] = len(dedup_docs)
    _count_profile_matches(dedup_docs, q, meta)

    rag_context = _profile_cards_context(dedup_docs, q, top_k, member_names, meta)
    logger.info(
        "/askai member-profile RAG stats: guild=%s requester=%s intent=%s participant=%s alias_hints=%s sql_identity=%s sql_participant=%s sql_alias=%s vector=%s dedup=%s cards=%s self=%s target=%s alias=%s sent=%s",
        guild_id, requester_user_id, q.intent, meta["participant_count"], len(q.alias_hints),
        meta["sql_identity_hits"], meta["sql_participant_hits"], meta["sql_alias_hits"], meta["vector_hits"],
        meta["dedup_hits"], meta["cards_sent"], meta["self_match_count"], meta["target_match_count"],
        meta["alias_match_count"], meta["sent_count"],
    )
    if meta["sent_count"] == 0:
        logger.info(
            "/askai member-profile RAG miss: guild=%s requester=%s reason=no_docs_after_filter",
            guild_id, requester_user_id,
        )
    return rag_context, meta


@dataclass(frozen=True)
class _ProfileQuestion:
    """問句解析結果：誰在問、問句裡提到誰（<@id>、Discord 名字、別名片段）、在場誰。"""
    question: str
    intent: str
    requester_user_id: int | None
    alias_hints: list[str]
    mentioned_user_ids: list[str]
    named_ids: list[str]          # 提到的人：<@id> 與 Discord 名字對到的，去重
    participant_ids: list[str]


def _parse_profile_question(
    question: str, requester_user_id: int | None, participant_user_ids: list[int] | None,
    mentioned_user_ids: list[str] | None, member_names: dict[str, list[str]] | None,
) -> _ProfileQuestion:
    alias_hints = expand_alias_candidates(question)
    # mentioned_user_ids 優先採 caller 傳入（從原始 <@id> 抽出）；否則從 question 重抽——
    # caller 若已將 question 替換成 display_name，重抽會失敗，必須顯式傳入
    if mentioned_user_ids is None:
        mentioned_user_ids = extract_mentioned_user_ids(question)
    # 問句裡的詞對到 Discord 名字的人（自介、印象的別名由別名那一路的 SQL 比對）
    alias_user_ids = match_members(member_names or {}, alias_hints)
    participant_ids = [str(uid) for uid in (participant_user_ids or []) if uid]
    participant_ids = list(dict.fromkeys(participant_ids))[:PERSONA_MAX_PARTICIPANTS]
    return _ProfileQuestion(
        question=question, intent=classify_persona_intent(question), requester_user_id=requester_user_id,
        alias_hints=alias_hints, mentioned_user_ids=list(mentioned_user_ids),
        named_ids=list(dict.fromkeys([*mentioned_user_ids, *alias_user_ids])),
        participant_ids=participant_ids,
    )


def _rows_to_docs(rows, source: str) -> list[dict[str, Any]]:
    """SQL 撈回的 (id, text, metadata_) 轉成候選文件；metadata_ 可能是 JSON 字串。"""
    docs = []
    for row_id, row_text, row_meta in rows:
        parsed_meta = row_meta
        if isinstance(parsed_meta, str):
            parsed_meta = json.loads(parsed_meta)
        docs.append({
            "db_id": row_id,
            "text": row_text or "",
            "metadata": parsed_meta if isinstance(parsed_meta, dict) else {},
            "source": source,
        })
    return docs


def _sql_profile_route(sql: str, params, source: str, label: str, logger: logging.Logger) -> list[dict[str, Any]]:
    """跑一路 SQL 候選查詢；失敗只記 WARNING、回空清單，其他路照常。"""
    try:
        with _pgvector_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return _rows_to_docs(cur.fetchall(), source)
    except Exception as exc:
        logger.warning("member-profile SQL %s retrieval 失敗: %s", label, exc)
        return []


_PROFILE_WHERE = """
    WHERE metadata_->>'doc_type' = 'member_profile'
      AND metadata_->>'guild_id' = %s
"""


def _collect_profile_candidates(
    q: _ProfileQuestion, guild_id: int, physical_table: str, table_name: str,
    top_k: int, logger: logging.Logger, meta: dict,
) -> list[dict[str, Any]]:
    """四路撈候選：發問者本人 → 在場的人 → 問句提到的人與別名 → 語意檢索。各路有沒有查看條件；計數記進 meta。"""
    collected: list[dict[str, Any]] = []
    # 本人：自介與 AI 觀察看 author_id，別人寫給他的印象看 target_user_id
    kinds_of = """
          (
                (metadata_->>'profile_kind' = 'intro_profile' AND metadata_->>'author_id' = {p})
             OR (metadata_->>'profile_kind' = 'auto_personality' AND metadata_->>'author_id' = {p})
             OR (metadata_->>'profile_kind' = 'impression' AND metadata_->>'target_user_id' = {p})
          )
    """
    if psycopg2 is not None and q.requester_user_id is not None:
        sql = (f"SELECT id, text, metadata_ FROM {physical_table}" + _PROFILE_WHERE
               + " AND " + kinds_of.format(p="%s") + " ORDER BY id DESC LIMIT %s")
        rid = str(q.requester_user_id)
        docs = _sql_profile_route(sql, (str(guild_id), rid, rid, rid, max(3, top_k)), "sql_identity", "identity", logger)
        meta["sql_identity_hits"] = len(docs)
        collected += docs

    if psycopg2 is not None and q.participant_ids:
        sql = (f"SELECT id, text, metadata_ FROM {physical_table}" + _PROFILE_WHERE
               + " AND " + kinds_of.format(p="ANY(%s)") + " ORDER BY id DESC LIMIT %s")
        ids = q.participant_ids
        docs = _sql_profile_route(sql, (str(guild_id), ids, ids, ids, max(8, top_k + 3)), "sql_participant", "participant", logger)
        meta["sql_participant_hits"] = len(docs)
        collected += docs

    if psycopg2 is not None and (q.alias_hints or q.named_ids):
        like_values = [f"%{hint}%" for hint in q.alias_hints] or ["%__never_match__%"]
        placeholders = ",".join(["%s"] * len(like_values))
        # 按 profile_kind 分流：自介／AI 觀察用 author_id（被提到的人本人），印象用 target_user_id
        # （別人寫給他的）。不用扁平 author_id ANY，避免「被提到的人寫給別人的印象」被歸到別人卡裡。
        sql = (f"SELECT id, text, metadata_ FROM {physical_table}" + _PROFILE_WHERE + f"""
          AND (
                metadata_->>'alias' ILIKE ANY(ARRAY[{placeholders}])
             OR metadata_->>'target_alias' ILIKE ANY(ARRAY[{placeholders}])
             OR (metadata_->>'profile_kind' IN ('intro_profile', 'auto_personality')
                 AND metadata_->>'author_id' = ANY(%s))
             OR (metadata_->>'profile_kind' = 'impression'
                 AND metadata_->>'target_user_id' = ANY(%s))
          )
        ORDER BY id DESC
        LIMIT %s
        """)
        named = q.named_ids or ["0"]
        params = [str(guild_id), *like_values, *like_values, named, named, max(6, top_k + 2)]
        docs = _sql_profile_route(sql, params, "sql_alias", "alias", logger)
        meta["sql_alias_hits"] = len(docs)
        collected += docs

    collected += _vector_profile_route(q.question, guild_id, table_name, top_k, logger, meta)
    return collected


def _vector_profile_route(
    question: str, guild_id: int, table_name: str, top_k: int, logger: logging.Logger, meta: dict,
) -> list[dict[str, Any]]:
    """語意檢索（LlamaIndex PGVectorStore）：撈得比額度寬，只收本伺服器的；失敗保留 SQL 結果。"""
    if VectorStoreIndex is None or PGVectorStore is None:
        return []
    docs: list[dict[str, Any]] = []
    try:
        index = _get_or_build_vector_index(table_name, logger)
        if index is None:
            return []
        retriever = index.as_retriever(
            similarity_top_k=max(top_k * 2, HYBRID_RETRIEVAL_SETTINGS.hybrid_candidate_pool // 2)
        )
        vector_nodes = retriever.retrieve(question)
        meta["vector_hits"] = len(vector_nodes)
        for node in vector_nodes:
            md = node.metadata if isinstance(node.metadata, dict) else {}
            if str(md.get("guild_id", "")) != str(guild_id):
                continue
            # node.metadata 不含 ref_doc_id（LlamaIndex 把它放在 node 本身），要從 node 取，
            # 才會跟 SQL 撈到的同一份文件去重——否則同一則印象會在卡片裡出現兩次
            ref_doc_id = getattr(getattr(node, "node", node), "ref_doc_id", None)
            docs.append({
                "db_id": ref_doc_id or md.get("ref_doc_id") or md.get("doc_id") or md.get("document_id") or "",
                "text": node.text or "",
                "metadata": md,
                "source": "vector",
            })
    except Exception as exc:
        logger.warning("member-profile vector retrieval 失敗（保留 SQL 結果）: %s", exc)
    return docs


# 同一份文件兩路都撈到時留哪一筆：精度高的來源（卡片的來源加分也看它）
_DEDUP_PRIORITY = {"sql_identity": 4, "sql_alias": 3, "sql_participant": 2, "vector": 1}
# 去重後的排序：本人 → 提到的人 → 語意；沒列的（在場者那一路）排最後，同來源新的在前
_SORT_PRIORITY = {"sql_identity": 0, "sql_alias": 1, "vector": 2}


def _dedup_profile_docs(collected: list[dict[str, Any]]) -> list[dict[str, Any]]:
    dedup: dict[str, dict[str, Any]] = {}
    for item in collected:
        md = item.get("metadata") or {}
        dedup_key = str(
            md.get("ref_doc_id") or md.get("doc_id") or md.get("document_id")
            or item.get("db_id") or hash(item.get("text", ""))
        )
        kept = dedup.get(dedup_key)
        if kept is None or _DEDUP_PRIORITY.get(item.get("source", ""), 0) > _DEDUP_PRIORITY.get(kept.get("source", ""), 0):
            dedup[dedup_key] = item

    def _row_no(d) -> int:
        db_id = str(d.get("db_id") or "")
        return int(db_id) if db_id.isdigit() else 0

    docs = list(dedup.values())
    docs.sort(key=lambda d: (_SORT_PRIORITY.get(d.get("source", "vector"), 9), -_row_no(d)))
    return docs


def _count_profile_matches(docs: list[dict[str, Any]], q: _ProfileQuestion, meta: dict) -> None:
    """統計撈到的文件是關於誰的（本人寫的、寫給本人的、對到問句別名的），只進 log 與 meta。"""
    rid = str(q.requester_user_id) if q.requester_user_id is not None else None
    for doc in docs:
        md = doc.get("metadata") or {}
        alias = str(md.get("alias", "") or md.get("target_alias", "")).strip()
        if rid is not None and str(md.get("author_id", "")) == rid:
            meta["self_match_count"] += 1
        if rid is not None and str(md.get("target_user_id", "")) == rid:
            meta["target_match_count"] += 1
        if alias and any(h in normalize_alias_text(alias) for h in q.alias_hints):
            meta["alias_match_count"] += 1


def _profile_cards_context(
    docs: list[dict[str, Any]], q: _ProfileQuestion, top_k: int,
    member_names: dict[str, list[str]] | None, meta: dict,
) -> list[dict[str, str]]:
    """候選文件 → 每人一張卡 → 給模型的 context 行（第一行是表頭）；多於額度只留最後幾張。"""
    card_budget = min(max(1, top_k), PERSONA_MAX_CARDS)
    persona_cards = build_persona_cards(
        docs=docs,
        requester_user_id=q.requester_user_id,
        participant_user_ids=q.participant_ids,
        mentioned_user_ids=q.mentioned_user_ids,
        intent=q.intent,
        alias_hints=q.alias_hints,
        max_cards=card_budget,
        display_names=display_names(member_names),
    )
    meta["cards_generated"] = len(persona_cards)
    rag_context = format_persona_cards_for_context(persona_cards)
    meta["cards_sent"] = max(0, len(rag_context) - 1 if rag_context else 0)
    meta["selected_count_before_trim"] = len(rag_context)
    if len(rag_context) > card_budget + 1:
        meta["trimmed_count"] = len(rag_context) - (card_budget + 1)
        rag_context = [rag_context[0], *rag_context[-card_budget:]]
    meta["sent_count"] = len(rag_context)
    return rag_context
