"""LLM 對話上下文檢索。"""

from __future__ import annotations

import logging
import json
import re
import threading
from collections import defaultdict
from datetime import timezone
from typing import Any

import discord

from llm.sticker_cache import get_sticker_text
from llm.tokenization import tokenize_for_retrieval, tokens_for_debug
from llm.persona_card_builder import (
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
from sys_settings.llm_settings import (
    LLMServiceSettings,
    load_ollama_runtime_config,
)

try:
    from rank_bm25 import BM25Okapi
except Exception:  # pragma: no cover - 依賴可能在部份環境尚未安裝
    BM25Okapi = None

try:
    from llama_index.core import Document, VectorStoreIndex
    from llm.safe_ollama_embedding import SafeOllamaEmbedding as OllamaEmbedding
    from llama_index.vector_stores.postgres import PGVectorStore
except Exception:  # pragma: no cover - 依賴可能在部份環境尚未安裝
    Document = None
    VectorStoreIndex = None
    OllamaEmbedding = None
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


def _load_embed_model_name() -> str:
    """從 Ollama runtime 設定讀取 embedding model，失敗則回退預設。"""
    runtime_config = load_ollama_runtime_config(LLM_SETTINGS.ollama_runtime_model_path)
    return runtime_config.embed_model


def _get_embed_model(logger: logging.Logger) -> Any | None:
    """延遲初始化 Embedding 模型，避免啟動時阻塞。"""
    global _EMBED_MODEL, _EMBED_MODEL_NAME
    embed_model_name = _load_embed_model_name()
    if _EMBED_MODEL is not None and _EMBED_MODEL_NAME == embed_model_name:
        return _EMBED_MODEL

    if OllamaEmbedding is None:
        logger.warning("OllamaEmbedding 尚未可用，向量檢索將退化為 BM25。")
        return None

    try:
        _EMBED_MODEL = OllamaEmbedding(
            model_name=embed_model_name,
            base_url=LLM_SETTINGS.ollama_base_url,
            request_timeout=LLM_SETTINGS.ollama_timeout,
        )
        _EMBED_MODEL_NAME = embed_model_name
    except Exception as exc:
        logger.warning("初始化 OllamaEmbedding 失敗，改用 BM25: %s", exc)
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
            vector_store = PGVectorStore.from_params(
                database=LLM_SETTINGS.pgvector_db,
                host=LLM_SETTINGS.pgvector_host,
                password=LLM_SETTINGS.pgvector_password,
                port=LLM_SETTINGS.pgvector_port,
                user=LLM_SETTINGS.pgvector_user,
                table_name=table_name,
                embed_dim=HYBRID_RETRIEVAL_SETTINGS.pgvector_embed_dim,
                hybrid_search=True,
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


def _rrf_score(rank: int, *, weight: float, rrf_k: int) -> float:
    """Reciprocal Rank Fusion 分數。"""
    # 計算原理（RRF）
    # - 公式：weight / (rrf_k + rank)
    # - rank 越前面（數字越小），分數越高
    # - weight 用來控制來源重要性（BM25 vs Vector）
    #
    # 範例：rrf_k=60
    # - rank=1, weight=0.45 -> 0.45/61
    # - rank=2, weight=0.55 -> 0.55/62
    # 兩路分數可直接相加，形成融合後的最終排序依據。
    return weight / (rrf_k + rank)


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


def _build_vector_rank(
    *,
    question: str,
    messages: list[discord.Message],
    candidate_pool: int,
    logger: logging.Logger,
) -> dict[str, int]:
    """建立向量檢索排名（message_id -> rank）。"""
    # 設計意圖：BM25 負責字面，Vector 負責語意；兩路結果交給 RRF 融合。
    # 這裡刻意用 in-memory index 跑「當輪訊息」語意排序，避免依賴外部索引同步延遲。
    if Document is None or VectorStoreIndex is None:
        return {}

    embed_model = _get_embed_model(logger)
    if embed_model is None:
        return {}

    try:
        docs: list[Document] = []
        for msg in messages:
            # 與 BM25 一致：先排除空內容，避免把無訊號樣本送入向量檢索。
            text = (msg.content or "").strip()
            if not text:
                continue
            docs.append(
                Document(
                    text=text,
                    doc_id=str(msg.id),
                    metadata={
                        "message_id": str(msg.id),
                        "author_id": str(msg.author.id),
                        "channel_id": str(msg.channel.id),
                        "timestamp": msg.created_at.isoformat(),
                        "doc_type": "discord_chat",
                    },
                )
            )

        # 沒有可索引文件時直接回空，保持降級可預期。
        if not docs:
            return {}

        # similarity_top_k 上限受 candidate_pool 與 docs 數量共同約束，
        # 避免請求超出資料集大小。
        index = VectorStoreIndex.from_documents(docs, embed_model=embed_model)
        retriever = index.as_retriever(similarity_top_k=max(1, min(candidate_pool, len(docs))))
        nodes = retriever.retrieve(question)

        vector_rank: dict[str, int] = {}
        for rank, node in enumerate(nodes, start=1):
            # 只接受可對映回原訊息的 node（有 message_id 才能進融合）。
            node_message_id = str(node.metadata.get("message_id", "")).strip()
            if not node_message_id:
                continue
            vector_rank[node_message_id] = rank
        return vector_rank
    except Exception as exc:
        logger.warning("In-memory 向量檢索失敗，改用 BM25: %s", exc)
        return {}


def _build_discord_context_item(msg: discord.Message, tz: timezone) -> dict[str, str]:
    """
    回傳包含元資料的 dict，確保可觀測性與後續 Debug 能力。
    同時將給 LLM 看的文字組合在 'content' 欄位中。
    """
    display_name = getattr(msg.author, "display_name", msg.author.name)
    time_str = msg.created_at.astimezone(tz).strftime("%Y-%m-%d %H:%M")
    compact_content = " ".join(msg.content.split())

    # 加入貼圖描述
    if msg.stickers:
        sticker_texts = []
        for sticker in msg.stickers:
            sticker_text = get_sticker_text(sticker)
            if sticker_text:
                sticker_texts.append(sticker_text)
        if sticker_texts:
            sticker_part = " ".join(sticker_texts)
            compact_content = f"{compact_content} {sticker_part}" if compact_content else sticker_part

    # 產出格式範例：[2026-02-26 14:30] 老哥: 昨天抽卡又保底了 [貼圖：哭哭貓｜難過想哭的心情]
    # author_id 保留在 metadata，避免 content 重複佔用 token。
    formatted_text = f"[{time_str}] {display_name}: {compact_content}"

    return {
        "role": "user",
        "content": formatted_text,
        "message_id": str(msg.id),
        "author_id": str(msg.author.id),
        "display_name": display_name,
        "channel_id": str(msg.channel.id)
    }


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
) -> tuple[list[dict[str, str]], list[dict[str, str]], dict[str, int]]:
    """從 Discord 歷史訊息檢索上下文：近期保底 + Hybrid 關聯檢索。

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
    }
    debug = {
        "question_tokens": [],
        "bm25_ranked": [],
        "vector_ranked": [],
        "fused_ranked": [],
    }

    try:
        if not isinstance(interaction.channel, (discord.TextChannel, discord.Thread)):
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

        recent_start_index = max(0, len(ordered_messages) - min_recent_context)
        selected_indices = {
            idx
            for idx, msg in enumerate(ordered_messages)
            if idx >= recent_start_index and msg.content and msg.content.strip()
        }
        meta["recent_selected_count"] = len(selected_indices)

        debug["question_tokens"] = tokens_for_debug(question)

        # 聊天持久化已改由 on_message buffer 機制處理（chat_persistence.py）
        # 不再在 /askai 流程中同步寫入，避免阻塞 event loop

        bm25_rank = _build_bm25_rank(question=question, messages=ordered_messages)
        vector_rank = _build_vector_rank(
            question=question,
            messages=ordered_messages,
            candidate_pool=HYBRID_RETRIEVAL_SETTINGS.hybrid_candidate_pool,
            logger=logger,
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
            fused_scores[message_id] += _rrf_score(
                rank,
                weight=bm25_weight,
                rrf_k=HYBRID_RETRIEVAL_SETTINGS.hybrid_rrf_k,
            )
        for message_id, rank in vector_rank.items():
            fused_scores[message_id] += _rrf_score(
                rank,
                weight=vector_weight,
                rrf_k=HYBRID_RETRIEVAL_SETTINGS.hybrid_rrf_k,
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
        top_relevant_indices: set[int] = set()
        for message_id, fused_score in fused_ranked:
            # 分數門檻用途：
            # - 避免低相關/噪音訊息被送進 prompt
            # - relevant_selected=0 時可考慮調低 hybrid_min_fused_score
            if fused_score < HYBRID_RETRIEVAL_SETTINGS.hybrid_min_fused_score:
                continue
            idx = index_by_message_id.get(message_id)
            if idx is None:
                continue
            top_relevant_indices.add(idx)
            if len(top_relevant_indices) >= max_relevant_context:
                break

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
            "/askai discord context stats: fetched=%s recent=%s relevant=%s selected=%s trimmed=%s sent=%s bm25_hits=%s vector_hits=%s fused_hits=%s",
            meta["fetched_count"], meta["recent_selected_count"],
            meta["relevant_selected_count"], meta["selected_count_before_trim"],
            meta["trimmed_count"], meta["sent_count"],
            len(bm25_rank), len(vector_rank), len(fused_scores)
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
) -> tuple[list[dict[str, str]], dict[str, int | bool | str]]:
    """同步版本，供 run_in_executor 呼叫。"""
    return _retrieve_rag_context_impl(
        question=question,
        guild_id=guild_id,
        requester_user_id=requester_user_id,
        participant_user_ids=participant_user_ids,
        logger=logger,
        top_k=top_k,
    )


async def retrieve_rag_context(
    *,
    question: str,
    guild_id: int | None,
    requester_user_id: int | None,
    participant_user_ids: list[int] | None,
    logger: logging.Logger,
    top_k: int = 5,
) -> tuple[list[dict[str, str]], dict[str, int | bool | str]]:
    """async 版本（向後相容），內部直接呼叫同步實作。"""
    return _retrieve_rag_context_impl(
        question=question,
        guild_id=guild_id,
        requester_user_id=requester_user_id,
        participant_user_ids=participant_user_ids,
        logger=logger,
        top_k=top_k,
    )


def _retrieve_rag_context_impl(
    *,
    question: str,
    guild_id: int | None,
    requester_user_id: int | None,
    participant_user_ids: list[int] | None,
    logger: logging.Logger,
    top_k: int = 5,
) -> tuple[list[dict[str, str]], dict[str, int | bool | str]]:
    """檢索 member_profile RAG（guild scoped + identity aware + persona cards）。"""

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

    intent = classify_persona_intent(question)
    meta["intent"] = intent

    table_name = source.table_name
    physical_table = f"data_{re.sub(r'[^a-zA-Z0-9_]', '', table_name)}"
    alias_hints = expand_alias_candidates(question)
    mentioned_user_ids = extract_mentioned_user_ids(question)
    participant_ids = [str(uid) for uid in (participant_user_ids or []) if uid]
    participant_ids = list(dict.fromkeys(participant_ids))[:PERSONA_MAX_PARTICIPANTS]
    meta["participant_count"] = len(participant_ids)

    collected: list[dict[str, Any]] = []

    # Stage 1: 高精度 identity SQL
    if psycopg2 is not None and requester_user_id is not None:
        try:
            with psycopg2.connect(
                host=LLM_SETTINGS.pgvector_host,
                port=LLM_SETTINGS.pgvector_port,
                dbname=LLM_SETTINGS.pgvector_db,
                user=LLM_SETTINGS.pgvector_user,
                password=LLM_SETTINGS.pgvector_password,
            ) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        f"""
                        SELECT id, text, metadata_
                        FROM {physical_table}
                        WHERE metadata_->>'doc_type' = 'member_profile'
                          AND metadata_->>'guild_id' = %s
                          AND (
                                (metadata_->>'profile_kind' = 'intro_profile' AND metadata_->>'author_id' = %s)
                             OR (metadata_->>'profile_kind' = 'impression' AND metadata_->>'target_user_id' = %s)
                          )
                        ORDER BY id DESC
                        LIMIT %s
                        """,
                        (str(guild_id), str(requester_user_id), str(requester_user_id), max(3, top_k)),
                    )
                    for row_id, row_text, row_meta in cur.fetchall():
                        parsed_meta = row_meta
                        if isinstance(parsed_meta, str):
                            parsed_meta = json.loads(parsed_meta)
                        collected.append(
                            {
                                "db_id": row_id,
                                "text": row_text or "",
                                "metadata": parsed_meta if isinstance(parsed_meta, dict) else {},
                                "source": "sql_identity",
                            }
                        )
            meta["sql_identity_hits"] = len(collected)
        except Exception as exc:
            logger.warning("member-profile SQL identity retrieval 失敗，改走 vector: %s", exc)

    # Stage 0: 聊天參與者關聯（除了 requester 以外的近期主角）
    if psycopg2 is not None and participant_ids:
        try:
            with psycopg2.connect(
                host=LLM_SETTINGS.pgvector_host,
                port=LLM_SETTINGS.pgvector_port,
                dbname=LLM_SETTINGS.pgvector_db,
                user=LLM_SETTINGS.pgvector_user,
                password=LLM_SETTINGS.pgvector_password,
            ) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        f"""
                        SELECT id, text, metadata_
                        FROM {physical_table}
                        WHERE metadata_->>'doc_type' = 'member_profile'
                          AND metadata_->>'guild_id' = %s
                          AND (
                                (metadata_->>'profile_kind' = 'intro_profile' AND metadata_->>'author_id' = ANY(%s))
                             OR (metadata_->>'profile_kind' = 'impression' AND metadata_->>'target_user_id' = ANY(%s))
                          )
                        ORDER BY id DESC
                        LIMIT %s
                        """,
                        (str(guild_id), participant_ids, participant_ids, max(8, top_k + 3)),
                    )
                    part_rows = cur.fetchall()
                    for row_id, row_text, row_meta in part_rows:
                        parsed_meta = row_meta
                        if isinstance(parsed_meta, str):
                            parsed_meta = json.loads(parsed_meta)
                        collected.append(
                            {
                                "db_id": row_id,
                                "text": row_text or "",
                                "metadata": parsed_meta if isinstance(parsed_meta, dict) else {},
                                "source": "sql_participant",
                            }
                        )
            meta["sql_participant_hits"] = len(part_rows)
        except Exception as exc:
            logger.warning("member-profile SQL participant retrieval 失敗: %s", exc)

    # Stage 2: alias SQL 輔助
    if psycopg2 is not None and (alias_hints or mentioned_user_ids):
        try:
            with psycopg2.connect(
                host=LLM_SETTINGS.pgvector_host,
                port=LLM_SETTINGS.pgvector_port,
                dbname=LLM_SETTINGS.pgvector_db,
                user=LLM_SETTINGS.pgvector_user,
                password=LLM_SETTINGS.pgvector_password,
            ) as conn:
                with conn.cursor() as cur:
                    like_values = [f"%{hint}%" for hint in alias_hints] or ["%__never_match__%"]
                    placeholders = ",".join(["%s"] * len(like_values))
                    cur.execute(
                        f"""
                        SELECT id, text, metadata_
                        FROM {physical_table}
                        WHERE metadata_->>'doc_type' = 'member_profile'
                          AND metadata_->>'guild_id' = %s
                          AND (
                                metadata_->>'alias' ILIKE ANY(ARRAY[{placeholders}])
                             OR metadata_->>'target_alias' ILIKE ANY(ARRAY[{placeholders}])
                             OR metadata_->>'author_id' = ANY(%s)
                             OR metadata_->>'target_user_id' = ANY(%s)
                          )
                        ORDER BY id DESC
                        LIMIT %s
                        """,
                        [
                            str(guild_id),
                            *like_values,
                            *like_values,
                            mentioned_user_ids or ["0"],
                            mentioned_user_ids or ["0"],
                            max(6, top_k + 2),
                        ],
                    )
                    alias_rows = cur.fetchall()
                    for row_id, row_text, row_meta in alias_rows:
                        parsed_meta = row_meta
                        if isinstance(parsed_meta, str):
                            parsed_meta = json.loads(parsed_meta)
                        collected.append(
                            {
                                "db_id": row_id,
                                "text": row_text or "",
                                "metadata": parsed_meta if isinstance(parsed_meta, dict) else {},
                                "source": "sql_alias",
                            }
                        )
            meta["sql_alias_hits"] = len(alias_rows)
        except Exception as exc:
            logger.warning("member-profile SQL alias retrieval 失敗: %s", exc)

    # Stage 3: 語意檢索（LlamaIndex PGVectorStore）
    vector_nodes: list[Any] = []
    if VectorStoreIndex is not None and PGVectorStore is not None:
        try:
            index = _get_or_build_vector_index(table_name, logger)
            if index is not None:
                retriever = index.as_retriever(
                    similarity_top_k=max(top_k * 2, HYBRID_RETRIEVAL_SETTINGS.hybrid_candidate_pool // 2)
                )
                vector_nodes = retriever.retrieve(question)
                meta["vector_hits"] = len(vector_nodes)
                for node in vector_nodes:
                    md = node.metadata if isinstance(node.metadata, dict) else {}
                    if str(md.get("guild_id", "")) != str(guild_id):
                        continue
                    collected.append(
                        {
                            "db_id": md.get("ref_doc_id") or md.get("doc_id") or md.get("document_id") or "",
                            "text": node.text or "",
                            "metadata": md,
                            "source": "vector",
                        }
                    )
        except Exception as exc:
            logger.warning("member-profile vector retrieval 失敗（保留 SQL 結果）: %s", exc)

    dedup: dict[str, dict[str, Any]] = {}
    for item in collected:
        md = item.get("metadata") or {}
        dedup_key = str(
            md.get("ref_doc_id")
            or md.get("doc_id")
            or md.get("document_id")
            or item.get("db_id")
            or hash(item.get("text", ""))
        )
        if dedup_key not in dedup:
            dedup[dedup_key] = item
            continue

        # 保留更高精度來源
        priority = {"sql_identity": 3, "sql_alias": 2, "vector": 1}
        if priority.get(item.get("source", ""), 0) > priority.get(dedup[dedup_key].get("source", ""), 0):
            dedup[dedup_key] = item

    dedup_docs = list(dedup.values())
    meta["dedup_hits"] = len(dedup_docs)

    # 按優先度+新舊排序
    source_priority = {"sql_identity": 0, "sql_alias": 1, "vector": 2}
    dedup_docs.sort(key=lambda d: (source_priority.get(d.get("source", "vector"), 9), -int(d.get("db_id") or 0 if str(d.get("db_id") or "").isdigit() else 0)))

    for doc in dedup_docs:
        md = doc.get("metadata") or {}
        author_id = str(md.get("author_id", ""))
        target_user_id = str(md.get("target_user_id", ""))
        alias = str(md.get("alias", "") or md.get("target_alias", "")).strip()

        if requester_user_id is not None and author_id == str(requester_user_id):
            meta["self_match_count"] += 1
        if requester_user_id is not None and target_user_id == str(requester_user_id):
            meta["target_match_count"] += 1
        if alias and any(h in normalize_alias_text(alias) for h in alias_hints):
            meta["alias_match_count"] += 1

    persona_cards = build_persona_cards(
        docs=dedup_docs,
        requester_user_id=requester_user_id,
        participant_user_ids=participant_ids,
        mentioned_user_ids=mentioned_user_ids,
        intent=intent,
        alias_hints=alias_hints,
        max_cards=min(max(1, top_k), PERSONA_MAX_CARDS),
    )
    meta["cards_generated"] = len(persona_cards)

    # 建立 person_id → alias 對照表，供聊天記錄標註使用
    alias_map: dict[str, str] = {}
    for card in persona_cards:
        pid = card.get("person_id", "")
        alias = card.get("alias", "")
        if pid and alias:
            alias_map[pid] = alias

    rag_context = format_persona_cards_for_context(persona_cards)
    meta["cards_sent"] = max(0, len(rag_context) - 1 if rag_context else 0)
    meta["alias_map"] = alias_map

    meta["selected_count_before_trim"] = len(rag_context)
    card_budget = min(max(1, top_k), PERSONA_MAX_CARDS)
    if len(rag_context) > card_budget + 1:
        meta["trimmed_count"] = len(rag_context) - (card_budget + 1)
        rag_context = [rag_context[0], *rag_context[-card_budget:]]

    meta["sent_count"] = len(rag_context)
    logger.info(
        "/askai member-profile RAG stats: guild=%s requester=%s intent=%s participant=%s alias_hints=%s sql_identity=%s sql_participant=%s sql_alias=%s vector=%s dedup=%s cards=%s self=%s target=%s alias=%s sent=%s",
        guild_id,
        requester_user_id,
        intent,
        meta["participant_count"],
        len(alias_hints),
        meta["sql_identity_hits"],
        meta["sql_participant_hits"],
        meta["sql_alias_hits"],
        meta["vector_hits"],
        meta["dedup_hits"],
        meta["cards_sent"],
        meta["self_match_count"],
        meta["target_match_count"],
        meta["alias_match_count"],
        meta["sent_count"],
    )

    if meta["sent_count"] == 0:
        logger.info(
            "/askai member-profile RAG miss: guild=%s requester=%s reason=no_docs_after_filter",
            guild_id,
            requester_user_id,
        )

    return rag_context, meta
