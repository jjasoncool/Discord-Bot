"""功能二：AI 偶爾插話 / 閒聊（Phase A 骨架）。

掛在 `discord_bot.on_message`，以背景 task 執行，不阻塞訊息處理。

觸發哲學（由便宜到貴，任一關卡不過就 return，多數訊息連模型都不勞動）：
    硬性過濾（零成本）→ **靜默期**（等對話停一下再擷取脈絡）→ 內容閘（看整段 burst）
    → 冷卻 / 每小時上限 → foreground 讓位 → **鉤子閘**（零成本，決定值不值得花那 ~120s）
    → 12B 判斷（回 / [PASS] 沉默）

靜默期依對話節奏切換：慢節奏等到「夠久沒新訊息且沒人在打字」，熱聊只等一小段就開跑
（熱聊等不到靜默，而且插話本來就不需要空檔）。一段 burst 合併成一次評估。

節奏由「對話內容」決定，不由計時器決定：鉤子閘（`ambient_hooks`）算這一刻有沒有值得開口的
訊號，`hook_threshold` 是話多話少的主旋鈕；冷卻退居防洗版的安全網。插不插最終仍由 12B 的
`[PASS]` 說了算，鉤子只管「要不要喚醒它」。
（歷史：曾有 `judge_sampling_rate` 純機率減壓閥，隨機丟棄評估——會丟掉好時機、留下爛時機，
被有判斷依據的鉤子閘完全取代，已移除。）

特例：被 @ 或 reply 機器人 → must-reply，覆蓋冷卻（但仍走同一條 Lemonade 單流）。

模型協調（對齊「只有 P0 才換大模型」共識）：
    - 生成走 `LLMService.generate_reply(model=ambient_model)`，內部經 `chat_raw` 持 `stream_exclusive()`，
      與 /askai 自動序列化、不並流。
    - `/askai`（前景）活躍窗口內，背景插話暫停（`foreground_recently_active`），避免把大模型
      換成 12B、下次 /askai 又換回去的 swap ping-pong。

Phase A 記憶＝近期 `channel.history` 短期對話脈絡（不碰 RAG / persona card；那是 Phase B）。
"""
from __future__ import annotations

import asyncio
import base64
import functools
import logging
import math
import random
import re
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import discord

from llm.ai_interactions_store import fetch_similar_positive, record_interaction
from llm.ambient_hooks import evaluate as evaluate_hook
from llm.ambient_memory import enqueue_for_memory, recall_lines, recall_signature_tags
from llm.chat_line import (
    fetch_recent_lines,
    format_chat_line,
    name_with_anchor,
    semantic_message_text,
)
from llm.emoji_text_utils import is_emoji_or_symbol_only
from llm.lemonade_gate import foreground_recently_active, stream_busy
from llm.logger_factory import get_or_create_file_logger
from services.llm_service import LLMService
from sys_settings.llm_settings import AmbientChatSettings
from utils.utils import ChannelConfig

logger = logging.getLogger("discord_bot")

_SETTINGS = AmbientChatSettings()

# chat_history 每行標 [HH:MM] 發話時刻（台北時區）→ 讓模型判斷新舊/順序，鎖定最新、別翻舊帳
_TAIPEI_TZ = timezone(timedelta(hours=8))

_DEFAULT_AMBIENT_PROMPT = (
    "你是 Discord 群裡的一位群友，個性溫和、偶爾俏皮。"
    "你不是被點名回答問題，而是『剛好想插一句嘴』。"
    "請用一兩句簡短口語的繁體中文回應當下對話。"
    f"如果這則訊息沒什麼好接的、或不適合插話，就只輸出 {_SETTINGS.silence_sentinel}（不要多寫任何字）。"
)

# system prompt 以「組成檔的 mtime 組合」快取：改任一檔即時生效、不必每則訊息重讀
_PROMPT_CACHE: dict = {"text": None, "key": None}

# 共用一個無狀態 LLMService（與 /askai cog 各自持有亦可，因模型協調走的是 module-level 鎖/時間戳）
_LLM_SERVICE: Optional[LLMService] = None

# Phase B：per-channel persona card 召回的短 TTL 快取 {channel_id: (mono_ts, persona_context)}
_PERSONA_CACHE: dict = {}


def _get_llm() -> LLMService:
    global _LLM_SERVICE
    if _LLM_SERVICE is None:
        _LLM_SERVICE = LLMService()
    return _LLM_SERVICE


def _read_text_file(path: Path) -> str:
    """讀單一文字檔；不存在或讀失敗回空字串。"""
    try:
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
    except Exception as exc:
        logger.warning("載入 prompt 檔失敗（%s）：%s", path, exc)
    return ""


def _load_ambient_prompt() -> str:
    """組 ambient system prompt：共用人設身份（琇紫）+ 插話行為規則 + 風格對照範例。

    身份來自 `persona_identity.txt`（與 /askai 同一份），確保插話與問答是同一個角色；
    行為來自 `ambient_reply_prompt.txt`（簡短、允許沉默）；最後疊上與 /askai 共用的
    `persona_examples.txt`（風格對照範例，教它別跟著頻道互嗆下場補刀）。
    以各檔 mtime 組合快取。
    """
    paths: list[Path] = []
    if _SETTINGS.use_shared_identity and _SETTINGS.identity_path:
        paths.append(Path(_SETTINGS.identity_path))      # 共用人格
    if _SETTINGS.guardrails_path:
        paths.append(Path(_SETTINGS.guardrails_path))    # 共用守則/限制
    paths.append(Path(_SETTINGS.prompt_path))            # 插話行為
    if _SETTINGS.use_examples and _SETTINGS.examples_path:
        paths.append(Path(_SETTINGS.examples_path))      # 風格對照範例（克制 roast）

    key = tuple(
        (str(p), p.stat().st_mtime_ns if p.exists() else None) for p in paths
    )
    if _PROMPT_CACHE["key"] == key and _PROMPT_CACHE["text"]:
        return _PROMPT_CACHE["text"]

    chunks = [t for t in (_read_text_file(p) for p in paths) if t]
    text = "\n\n".join(chunks).strip() or _DEFAULT_AMBIENT_PROMPT
    _PROMPT_CACHE["text"] = text
    _PROMPT_CACHE["key"] = key
    return text


def _is_command_like(stripped: str) -> bool:
    """像指令的訊息（! 前綴或誤打的 / 斜線）不插。"""
    return stripped.startswith("!") or stripped.startswith("/")


def _is_link_only(stripped: str) -> bool:
    """整則只有連結（無可聊的文字）不插。"""
    tokens = stripped.split()
    return bool(tokens) and all(
        t.startswith("http://") or t.startswith("https://") for t in tokens
    )


def _is_directed(bot, message: discord.Message) -> bool:
    """是否被點名：@ 機器人，或 reply 機器人的訊息。"""
    if bot.user is not None and bot.user in message.mentions:
        return True
    ref = message.reference
    if ref is not None:
        resolved = getattr(ref, "resolved", None)
        if (
            isinstance(resolved, discord.Message)
            and bot.user is not None
            and resolved.author.id == bot.user.id
        ):
            return True
    return False


def _get_tracker(bot, channel_id: int) -> dict:
    """取得（或建立）某頻道的插話冷卻/計數狀態（仿 echo_tracker）。"""
    tracker = bot.ambient_tracker.get(channel_id)
    if tracker is None:
        tracker = {"last_ts": 0.0, "hour_start": time.monotonic(), "hour_count": 0}
        bot.ambient_tracker[channel_id] = tracker
    return tracker


def _write_ambient_debug(
    *, trace_id: str, prompt_record_log: str, outcome: str, reply: str
) -> None:
    """把實際送進 12B 的完整 prompt（含三層 context）寫進 ambient_prompt.txt，供 debug。

    outcome: reply | pass | error:<kind>。看這個檔就能確認「上下文有沒有被組進去」。
    """
    if not _SETTINGS.debug_log:
        return
    try:
        dbg = get_or_create_file_logger(
            name="ambient_prompt_trace",
            log_path=Path(_SETTINGS.debug_prompt_log_path),
            mode="size",
            max_bytes=_SETTINGS.debug_log_max_bytes,
            backup_count=_SETTINGS.debug_log_backup_count,
        )
        line = "=" * 24
        dbg.info(
            f"\n{line} AMBIENT trace={trace_id} outcome={outcome} {line}\n"
            f"{prompt_record_log}\n"
            f"---- reply ----\n{reply or '(無)'}\n"
            f"{line} END {line}\n"
        )
    except Exception as exc:
        logger.warning("寫入 ambient debug prompt 失敗 trace=%s：%s", trace_id, exc)


def _note_sent(tracker: dict) -> None:
    """送出插話後更新冷卻時刻與每小時計數（滾動 1 小時窗口）。"""
    now = time.monotonic()
    tracker["last_ts"] = now
    if now - tracker["hour_start"] >= 3600:
        tracker["hour_start"] = now
        tracker["hour_count"] = 0
    tracker["hour_count"] += 1


async def _fetch_recent(
    message: discord.Message, thread_map: Optional[dict] = None
) -> tuple[Optional[list[str]], list[int]]:
    """抓近期頻道訊息：回 (對話脈絡行[舊→新], 近期發言者 user_id)。

    thread_map：傳 dict 進來會被填成 `{行編號: discord.Message}`——鉤子閘靠它拿到 Message
    物件算結構特徵。

    對話脈絡含機器人自己的話以維持連續性；participant_ids 只收非 bot，給 persona 召回用。
    bot 自己的行會被標「(你自己)」（self_id），讓模型在混合脈絡裡認得哪幾行是自己講的，
    不致把自己的話當別人（gate #4「我剛插過沒」也靠這個認）。
    """
    self_id = message.guild.me.id if message.guild and message.guild.me else None
    collected, participant_ids = await fetch_recent_lines(
        message.channel,
        tz=_TAIPEI_TZ,
        limit=_SETTINGS.history_limit,
        before=message,
        max_len=200,
        collect_participant_ids=True,
        self_id=self_id,
        thread_replies=True,  # 每行加編號（#N / ↩#M）：指代有錨，也讓鉤子拿得到訊息物件
        thread_map=thread_map,
        on_error=lambda exc: logger.debug("ambient 抓取頻道歷史失敗：%s", exc),
    )
    if message.author.id not in participant_ids:
        participant_ids.append(message.author.id)
    return (collected or None, participant_ids)


def _rag_to_persona_lines(rag_context: Optional[list]) -> Optional[list[str]]:
    """把 retrieve_rag_context_sync 的結果轉成 persona_context 文字行（認得人）。

    截斷每行、限制行數——12B 實測常駐 ctx 4096，persona card 偏長會吃爆 context。
    """
    if not rag_context:
        return None
    max_chars = _SETTINGS.persona_line_max_chars
    lines: list[str] = []
    for item in rag_context:
        content = item.get("content")
        if not content or item.get("metadata") == "persona_card_header":
            continue
        text = " ".join(str(content).split())
        if len(text) > max_chars:
            text = text[:max_chars] + "…"
        lines.append(text)
        if len(lines) >= _SETTINGS.persona_max_lines:
            break
    return lines or None


async def _build_persona_context(
    message: discord.Message, query: str, participant_ids: list[int]
) -> Optional[list[str]]:
    """Phase B：召回在場成員 persona card（intro/impression/auto_personality）。

    走既有 `retrieve_rag_context_sync`（吃純 id、不需 interaction）；sync LlamaIndex 放 executor。
    embedding 走 Lemonade 獨立 port（不卸載 12B）。per-channel 短 TTL 快取避免每則打 pgvector。
    best-effort：任何失敗回退到舊快取或 None，不影響插話本體。
    """
    now = time.monotonic()
    cached = _PERSONA_CACHE.get(message.channel.id)
    if cached and (now - cached[0]) < _SETTINGS.persona_cache_seconds:
        return cached[1]

    persona_context: Optional[list[str]] = None
    try:
        from llm.context_retriever import retrieve_rag_context_sync

        loop = asyncio.get_running_loop()
        rag_context, _meta = await loop.run_in_executor(
            None,
            functools.partial(
                retrieve_rag_context_sync,
                query,
                message.guild.id if message.guild else None,
                message.author.id,
                participant_ids,
                logger,
                _SETTINGS.persona_top_k,
            ),
        )
        persona_context = _rag_to_persona_lines(rag_context)
    except Exception as exc:
        logger.debug("ambient persona 召回失敗：%s", exc)
        return cached[1] if cached else None

    _PERSONA_CACHE[message.channel.id] = (now, persona_context)
    return persona_context


# ─────────────────────────────────────────────────────────────────────────────
# Phase D（實驗，預設關）：chat 歷史 callback
# 撈「這個頻道」過去語意相關的舊訊息，relevance×importance×recency 三因子 gate 後，
# 當「模糊印象」折進 persona_context。研究依據：Generative Agents 的 recency/importance/
# relevance 檢索 + episodic/semantic 之分（避免精確複述瑣事＝避免 uncanny）。
# importance 不另算，接 raw_message_store 已收集、沒人讀的 reaction salience。
# ─────────────────────────────────────────────────────────────────────────────
def _minmax(values: list[float]) -> list[float]:
    """min-max 正規化到 [0,1]；全相同回 0.5（中性，不讓單因子主導）。"""
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi - lo < 1e-9:
        return [0.5 for _ in values]
    return [(v - lo) / (hi - lo) for v in values]


def _callback_heuristic_salience(text: str) -> float:
    """便宜的 salience 先驗（給沒 reaction 的訊息兜底）→ [0,1]。長度 + 問號 + 連結/實體感。"""
    t = (text or "").strip()
    if not t:
        return 0.0
    score = min(len(t) / 80.0, 1.0) * 0.5
    if "?" in t or "？" in t:
        score += 0.25
    if re.search(r"https?://|@\w|[A-Za-z0-9]{4,}", t):
        score += 0.25
    return min(score, 1.0)


def _callback_age_hours(ts_str: Optional[str], now: datetime) -> Optional[float]:
    """ISO 時間字串 → 距今小時數；解析失敗回 None。"""
    if not ts_str:
        return None
    try:
        return max(0.0, (now - datetime.fromisoformat(ts_str)).total_seconds() / 3600.0)
    except Exception:
        return None


def _format_recalled_ts(ts_str: Optional[str]) -> str:
    """ISO 時間字串 → 台北時區「YYYY-MM-DD HH:MM」（舊發言帶完整日期，讓模型知道多久以前）。"""
    if not ts_str:
        return "?"
    try:
        return datetime.fromisoformat(ts_str).astimezone(_TAIPEI_TZ).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "?"


def _log_callback_debug(
    *, query, candidates, survivors, reactions, rel, imp, rec, scored, chosen_n, target=None, max_dist=None
) -> None:
    """候選級 debug（gated by callback_debug）：每筆候選的作者/距離/反應/三因子分/最終排序分/過哪關。

    純 log、不影響回傳。調參就看這裡的真實距離 d=：相關的米拉舊話落哪、無關的落哪 → 把地板設中間。
    tag：drop:DIST/SHORT/QUAL（被距離地板/品質閘刷掉）｜CHOSEN（採用）｜RANKOUT（過閘但排序輸、超過 top_k）；
    後綴 ·BF＝backfill 補滿進來的（距離其實超地板，因地板內不足 callback_min_results 才補）。
    a=作者 id 後四碼。mode：target:名字＝B（撈本人原話，地板較寬）｜topic（全作者，地板較嚴）。
    合併分只用來排序、不當門檻；相關性閘＝d ≤ 地板（max_dist），但數量不足 min 時會放寬地板 backfill。
    """
    md = max_dist if max_dist is not None else _SETTINGS.callback_max_distance
    survivor_mids = {c["message_id"] for c in survivors}
    backfill_mids = {c["message_id"] for c in survivors if c.get("_backfill")}  # 補滿進來的（距離超地板）
    detail = {survivors[i]["message_id"]: (rel[i], imp[i], rec[i]) for i in range(len(survivors))}
    score_by_mid = {c["message_id"]: s for s, c in scored}
    chosen = {c["message_id"] for _s, c in scored[: _SETTINGS.callback_top_k]}  # 與主流程一致：排序前 top_k

    rows = []
    for c in candidates:
        mid, d = c.get("message_id"), c.get("distance")
        a = (c.get("author_id") or "")[-4:] or "----"
        snippet = " ".join((c.get("text") or "").split())[:30]
        ds = f"{d:.3f}" if isinstance(d, (int, float)) else "None"
        if mid not in survivor_mids:
            text = (c.get("text") or "").strip()
            tag = "DIST" if (d is None or d > md) else ("SHORT" if len(text) < _SETTINGS.callback_min_chars else "QUAL")
            rows.append(f"  [drop:{tag}] a={a} d={ds} \"{snippet}\"")
        else:
            relv, impv, recv = detail.get(mid, (0.0, 0.0, 0.0))
            sc = score_by_mid.get(mid, 0.0)
            tag = ("CHOSEN" if mid in chosen else "RANKOUT") + ("·BF" if mid in backfill_mids else "")
            rows.append(
                f"  [{tag}] a={a} d={ds} react={reactions.get(mid, 0)} "
                f"rel={relv:.2f} imp={impv:.2f} rec={recv:.2f} sort={sc:.2f} \"{snippet}\""
            )
    logger.info(
        "ambient callback debug query=%r mode=%s | pool=%d survivors=%d (bf=%d) chosen=%d (floor d<=%.2f, min=%d)\n%s",
        query[:60], (f"target:{target}" if target else "topic"),
        len(candidates), len(survivors), len(backfill_mids), chosen_n, md,
        _SETTINGS.callback_min_results, "\n".join(rows) or "  (無候選)",
    )


async def _resolve_callback_target(message: discord.Message, query: str) -> Optional[str]:
    """從 query 解析「在講誰」→ 唯一 target user_id；保守，模糊就回 None（退回 topic 模式）。

    1) 明確 @mention（去掉 bot 自己）剛好一個 → 用它（最可靠）。
    2) 否則別名解析（expand_alias_candidates → member_profile_store.find_user_ids_by_alias）
       剛好命中一個 → 用它。
    3) 0 / 多個 / 解析失敗 → None：寧缺勿濫，不硬猜、不撈錯人的話安到別人頭上。
    """
    if message.guild is None:
        return None
    from llm.persona_card_builder import expand_alias_candidates, extract_mentioned_user_ids

    bot_id = str(message.guild.me.id) if message.guild.me else None
    uniq_mentions = list(dict.fromkeys(m for m in extract_mentioned_user_ids(query) if m != bot_id))
    if len(uniq_mentions) == 1:
        return uniq_mentions[0]
    if uniq_mentions:  # 多個 mention → 模糊，不猜
        return None

    aliases = expand_alias_candidates(query)
    if not aliases:
        return None
    from llm.member_profile_store import get_member_profile_store
    try:
        loop = asyncio.get_running_loop()
        uids = await loop.run_in_executor(
            None,
            functools.partial(
                get_member_profile_store().find_user_ids_by_alias,
                guild_id=message.guild.id, aliases=aliases,
            ),
        )
    except Exception as exc:
        logger.debug("callback target 別名解析失敗：%s", exc)
        return None
    uids = list(dict.fromkeys(uids))
    return uids[0] if len(uids) == 1 else None


async def _build_chat_callback_context(
    message: discord.Message, query: str
) -> Optional[list[str]]:
    """Phase D：撈本頻道語意相關舊訊息，回「模糊印象」行（或 None）。

    閘：① 絕對距離地板（mode-specific：target 寬、topic 嚴）+ ② 品質閘。撈不到就 None。
    relevance×importance×recency 合併分「只拿來排序」決定撈哪 top_k，不當門檻——這修掉了
    舊版「只撈到一條 → min-max 給 0.5 → 被 min_score 拒」的 bug（常常 callback=0 的元兇）。
    有 target → 撈本人原話（author 過濾）；無 → 全作者話題。預設開（callback_enabled）。
    重模組（search_chat / raw_message_store）在此 lazy import——flag 關時零載入。
    """
    if not _SETTINGS.callback_enabled or not query or message.guild is None:
        return None

    from llm.context_retriever import search_chat
    from llm.raw_message_store import get_reaction_salience

    # target 解析：在講某人 → B 模式（撈「目標本人」原話，author_id 過濾）；
    # 解析不出唯一目標 → topic 模式（不分作者，現狀）。impression 層另在 Phase B 提供「集體印象」。
    target_id = await _resolve_callback_target(message, query)
    target_name = None
    if target_id and target_id.isdigit():
        m = message.guild.get_member(int(target_id))
        target_name = m.display_name if m else None
    dbg_target = target_name or (f"…{target_id[-4:]}" if target_id else None)  # debug 顯示用

    now = datetime.now(timezone.utc)
    # ⑤ 排除近窗：只取比 (now - gap) 更舊的（chat metadata timestamp 為 isoformat，+00:00）
    before_ts = (now - timedelta(hours=_SETTINGS.callback_recency_gap_hours)).isoformat()

    try:
        loop = asyncio.get_running_loop()
        candidates = await loop.run_in_executor(
            None,
            functools.partial(
                search_chat,
                question=query,
                limit=_SETTINGS.callback_candidate_pool,
                logger=logger,
                candidate_ids=None,                   # 全庫
                channel_id=str(message.channel.id),   # 收斂本頻道（chat 無 guild_id）
                before_timestamp=before_ts,
                author_id=target_id,                  # 有 target → 只撈本人原話；None → 全作者
                return_meta=True,
            ),
        )
    except Exception as exc:
        logger.debug("ambient chat callback 檢索失敗：%s", exc)
        return None
    if not candidates:
        if _SETTINGS.callback_debug:
            _log_callback_debug(query=query, candidates=[], survivors=[], reactions={},
                                rel=[], imp=[], rec=[], scored=[], chosen_n=0, target=dbg_target)
        return None

    # ① 絕對相關性地板（mode-specific：target 撈本人原話、低風險 → 放寬）+ ② 品質閘。
    # 這個「絕對距離」是相關性閘；importance/recency 只拿來排序（見下），不用 min-max 合併分當
    # 硬門檻——那會讓「只撈到一條」必被 0.5<門檻 坑掉。
    # 補滿（backfill）：地板內過閘的不足 callback_min_results 時，用「過品質閘但距離超地板」的
    # 最近候選兜底湊數，刻意放寬距離換數量；是否真的引用仍由模型端「不貼切就忽略」把關。
    max_dist = (
        _SETTINGS.callback_target_max_distance if target_id
        else _SETTINGS.callback_max_distance
    )
    survivors: list[dict] = []
    backfill: list[dict] = []   # 過品質閘但距離 > 地板：補滿用（之後按距離近→遠取）
    for c in candidates:
        dist = c.get("distance")
        text = (c.get("text") or "").strip()
        if dist is None:
            continue
        if len(text) < _SETTINGS.callback_min_chars:
            continue
        if is_emoji_or_symbol_only(text) or _is_link_only(text):
            continue
        (survivors if dist <= max_dist else backfill).append({**c, "text": text})
    if len(survivors) < _SETTINGS.callback_min_results and backfill:
        backfill.sort(key=lambda c: c["distance"])  # 最近的先補
        need = _SETTINGS.callback_min_results - len(survivors)
        for c in backfill[:need]:
            survivors.append({**c, "_backfill": True})
    if not survivors:
        if _SETTINGS.callback_debug:
            _log_callback_debug(query=query, candidates=candidates, survivors=[], reactions={},
                                rel=[], imp=[], rec=[], scored=[], chosen_n=0,
                                target=dbg_target, max_dist=max_dist)
        return None

    # salience：reactions（主，接 raw_message_store）+ heuristic（兜底）
    try:
        reactions = await loop.run_in_executor(
            None,
            functools.partial(get_reaction_salience, [c["message_id"] for c in survivors]),
        )
    except Exception as exc:
        logger.debug("ambient callback salience 讀取失敗：%s", exc)
        reactions = {}

    half_life = max(1.0, _SETTINGS.callback_recency_half_life_hours)
    rel_raw, imp_raw, rec_raw = [], [], []
    for c in survivors:
        rel_raw.append(max(0.0, 1.0 - (c["distance"] / 2.0)))          # cosine 距離→相似度
        react_score = 1.0 - math.exp(-reactions.get(c["message_id"], 0) / 2.0)
        imp_raw.append(0.7 * react_score + 0.3 * _callback_heuristic_salience(c["text"]))
        age_h = _callback_age_hours(c.get("timestamp"), now)
        rec_raw.append(0.5 ** (age_h / half_life) if age_h is not None else 0.0)

    rel, imp, rec = _minmax(rel_raw), _minmax(imp_raw), _minmax(rec_raw)
    wr, wi, wc = (
        _SETTINGS.callback_w_relevance,
        _SETTINGS.callback_w_importance,
        _SETTINGS.callback_w_recency,
    )
    # 合併分只拿來「排序」決定撈哪幾條，不再當 pass/fail 門檻（門檻＝上面的絕對距離）。
    scored = sorted(
        ((wr * rel[i] + wi * imp[i] + wc * rec[i], c) for i, c in enumerate(survivors)),
        key=lambda x: x[0],
        reverse=True,
    )

    # 撈回的舊發言用標準 chat 行格式 `[時間] 作者#XXXX: 內容`——讓模型清楚「誰、何時」說的。
    # 框架說明（依稀印象、別精確複述）改放 <recalled_context> 區塊的固定 header（見 llm_service）。
    lines: list[str] = []
    for _score, c in scored[: _SETTINGS.callback_top_k]:
        gist = " ".join(c["text"].split())[: _SETTINGS.callback_line_max_chars]
        aid = c.get("author_id") or ""
        member = message.guild.get_member(int(aid)) if aid.isdigit() else None
        author = name_with_anchor(member) if member else (f"某人#{aid[-4:]}" if len(aid) >= 4 else "某人")
        lines.append(f"[{_format_recalled_ts(c.get('timestamp'))}] {author}: {gist}")

    if _SETTINGS.callback_debug:
        _log_callback_debug(query=query, candidates=candidates, survivors=survivors,
                            reactions=reactions, rel=rel, imp=imp, rec=rec, scored=scored,
                            chosen_n=len(lines), target=dbg_target, max_dist=max_dist)
    return lines or None


def _resolve_target_channel_id() -> Optional[int]:
    """讀白名單頻道 id（ChannelConfig 內含 5 分鐘快取，逐則呼叫成本低）。"""
    config = ChannelConfig.load_config(caller="ambient_reply")
    raw = config.get(_SETTINGS.channel_config_key)
    try:
        cid = int(raw)
    except (TypeError, ValueError):
        return None
    if cid <= 0 or cid == ChannelConfig.DEFAULT_ID:
        return None
    return cid


_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")


def _has_image(message: discord.Message) -> bool:
    """訊息是否含支援的圖片附件（用副檔名快判，不下載）。"""
    return any(
        (att.filename or "").lower().endswith(_IMAGE_EXTS)
        for att in message.attachments
    )


async def _prepare_images(message: discord.Message) -> Optional[list[str]]:
    """下載圖片附件 → base64（給 vision 模型）；silent best-effort，超限/失敗就跳過。"""
    out: list[str] = []
    for att in message.attachments:
        if len(out) >= _SETTINGS.image_max_count:
            break
        if not (att.filename or "").lower().endswith(_IMAGE_EXTS):
            continue
        if att.size and att.size > _SETTINGS.image_max_bytes:
            continue
        try:
            data = await att.read()
        except Exception as exc:
            logger.debug("ambient 讀取圖片失敗：%s", exc)
            continue
        if data:
            out.append(base64.b64encode(data).decode("utf-8"))
    return out or None


async def _resolve_replied_to(
    message: discord.Message,
) -> Optional[discord.Message]:
    """取「被回覆」的那則訊息（Discord 原生 reply 指向的訊息），給 prompt 標出指涉對象。

    reference.resolved 三態：discord.Message（已快取）/ DeletedReferencedMessage（已刪）/
    None（未在快取）。None 時用 message_id 補抓一次；已刪或抓不到一律回 None（best-effort，
    只在訊息確實帶 reference 時才會打 API）。
    """
    ref = message.reference
    if ref is None:
        return None
    resolved = getattr(ref, "resolved", None)
    if isinstance(resolved, discord.Message):
        return resolved
    if ref.message_id is not None:
        try:
            return await message.channel.fetch_message(ref.message_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException) as exc:
            logger.debug("ambient 補抓被回覆訊息失敗：%s", exc)
    return None


# per-channel 序列處理狀態：同頻道同時只有一個 ambient 在跑。生成期間進來的訊息不平行觸發，
# 只更新 latest / 標 pending；等這次跑完，再用「最新」對話狀態重新評估要不要插（@ 走 directed 優先答）。
#   debouncing   靜默期等待中（等的人只有一個，其餘訊息只更新狀態）
#   last_msg_mono 最後一則訊息的時刻（靜默期判準）
#   typing_at    {user_id: 最後一次 typing 事件時刻}
#   msg_times    近期訊息時刻（判斷對話節奏快/慢）
#   burst        靜默期累積的訊息（內容閘改看整段，不是只看最後一則）
_PROC_STATE: dict = {}


def _get_proc_state(channel_id: int) -> dict:
    st = _PROC_STATE.get(channel_id)
    if st is None:
        st = {
            "running": False, "pending": False, "latest": None, "directed": None,
            "debouncing": False, "last_msg_mono": 0.0, "typing_at": {},
            "msg_times": deque(maxlen=12), "burst": deque(maxlen=40),
        }
        _PROC_STATE[channel_id] = st
    return st


def note_typing(channel_id: int, user_id: int) -> None:
    """記下「某人正在這個頻道打字」（discord_bot.on_typing 呼叫）。零 I/O，只寫 dict。

    只追白名單頻道，避免全伺服器每個頻道都佔記憶體。Discord 沒有「停止打字」事件，
    靠 typing_grace_seconds 自然過期。
    """
    if not _SETTINGS.enabled:
        return
    target = _resolve_target_channel_id()
    if target is None or channel_id != target:
        return
    state = _get_proc_state(channel_id)
    now = time.monotonic()
    typing_at = state["typing_at"]
    typing_at[user_id] = now
    if len(typing_at) > 8:  # 順手清過期（人數少，成本可忽略）
        cutoff = now - _SETTINGS.typing_grace_seconds
        for uid in [u for u, t in typing_at.items() if t < cutoff]:
            typing_at.pop(uid, None)


def _someone_typing(state: dict, now: float) -> bool:
    """頻道裡還有人在打字嗎（最後一次 typing 事件在 grace 秒內）。"""
    return any(
        now - t < _SETTINGS.typing_grace_seconds
        for t in (state.get("typing_at") or {}).values()
    )


def _is_hot_conversation(state: dict) -> bool:
    """對話是不是正熱：最近幾則擠在 `hot_window_seconds` 內。"""
    times = state.get("msg_times") or ()
    n = _SETTINGS.hot_min_messages
    if len(times) < n:
        return False
    recent = list(times)[-n:]
    return (recent[-1] - recent[0]) < _SETTINGS.hot_window_seconds


async def _wait_for_quiet(state: dict) -> None:
    """靜默期：依對話節奏切換等法（不搶話）。

    **慢節奏**：等到「距最後一則夠久（`quiet_seconds`）」**且**「沒人在打字」才返回——
    打字不是講話，有人正在打一段長的可能要 20~30 秒，純時間 debounce 會切在半途。
    typing 是加分訊號，收不到（手機/貼圖/第三方 client）就退化成純時間靜默期。

    **熱聊**：只等 `hot_quiet_seconds`，而且**忽略 typing**。熱聊時永遠等不到靜默（一直有人
    在講、在打字），用慢節奏那套只會被 `max_wait` 硬拖、而那時對話又前進了一段；何況熱聊
    插話本來就不需要空檔，真人也是直接接話。留一個很短的間隔只是避免切在某人連發的中間。

    directed（被 @/reply）不等；等待期間被 @ 也立刻打斷。
    """
    if state.get("directed") is not None:
        if _SETTINGS.quiet_directed_seconds > 0:
            await asyncio.sleep(_SETTINGS.quiet_directed_seconds)
        return
    started = time.monotonic()
    while True:
        now = time.monotonic()
        if state.get("directed") is not None:
            return  # 等待中被 @ → 立刻處理
        if now - started >= _SETTINGS.quiet_max_wait_seconds:
            return  # 總上限：一直有人打字也不能無限等
        idle = now - state.get("last_msg_mono", 0.0)
        if _is_hot_conversation(state):
            if idle >= _SETTINGS.hot_quiet_seconds:
                return
        elif idle >= _SETTINGS.quiet_seconds and not _someone_typing(state, now):
            return
        await asyncio.sleep(0.5)


async def maybe_ambient_reply(bot, message: discord.Message) -> None:
    """on_message 背景進入點：硬過濾 + 記憶沉澱 + per-channel 序列協調。整段包 try 防炸 event loop。"""
    try:
        # ── 零成本硬性過濾（連協調都不用進）──
        if not _SETTINGS.enabled:
            return
        if message.author.bot or message.guild is None:
            return  # 不回 bot/自己、不處理 DM
        ambient_model = _get_llm().resolve_ambient_model()
        if not ambient_model:
            return  # 未設定 ambient_model → 整個功能靜默
        target_channel_id = _resolve_target_channel_id()
        if target_channel_id is None or message.channel.id != target_channel_id:
            return  # 非白名單頻道

        # 記憶沉澱：每則（非指令、有內容）都收進緩衝（不受序列協調影響）
        stripped = (message.content or "").strip()
        if stripped and not _is_command_like(stripped):
            enqueue_for_memory(message)

        # ── per-channel 序列協調（以下到設旗標之間無 await → 原子）──
        state = _get_proc_state(message.channel.id)
        state["latest"] = message
        _now_mono = time.monotonic()
        state["last_msg_mono"] = _now_mono
        state["msg_times"].append(_now_mono)    # 對話節奏（快/慢）→ 決定靜默期怎麼等
        state["burst"].append(message)          # 內容閘改看整段 burst
        state["typing_at"].pop(message.author.id, None)  # 送出了 → 清掉他的打字戳記
        if _is_directed(bot, message):
            state["directed"] = message
        if state["running"] or state["debouncing"]:
            state["pending"] = True   # 已有處理器在跑/在等 → 只記新動靜，由它回來重評估
            if _SETTINGS.debug_log:
                logger.info("ambient 吸收 channel=%s：處理器忙，待這輪跑完用最新狀態重評估", message.channel.id)
            return
        state["debouncing"] = True
    except Exception as exc:
        logger.warning("ambient 入口例外：%s", exc, exc_info=True)
        return

    # 靜默期 + 處理迴圈包在同一個 try/finally：兩個旗標**一定**要被清乾淨。
    # 分成兩段 try 會埋地雷——靜默期若收到 CancelledError（BaseException，不被
    # `except Exception` 攔），內層 finally 會把 running 設成 True，然後例外繼續往外拋、
    # 迴圈那段的 finally 永遠不執行 → running 永久卡住，該頻道插話從此靜音且無聲無息。
    try:
        # ── 靜默期：等對話停一下再開跑（不搶話 + 讓擷取到的脈絡完整）──
        # 例外也要往下走：寧可用當下狀態評估一次，也不要白白放掉這一輪。
        try:
            await _wait_for_quiet(state)
        except Exception as exc:
            logger.warning("ambient 靜默期例外 channel=%s：%s", message.channel.id, exc)
        finally:
            # 兩個旗標之間無 await → 不留空隙給其他 task 插進來搶
            state["debouncing"] = False
            state["running"] = True

        # ── 序列處理迴圈（同頻道唯一）：跑完一輪後若有新動靜/待答的 @ 就用最新狀態再跑一輪 ──
        passes = 0
        while True:
            state["pending"] = False
            directed_msg = state["directed"]
            if directed_msg is not None:
                state["directed"] = None
                current, current_directed = directed_msg, True   # @ 優先答
            else:
                current, current_directed = state["latest"], False
            if current is None:
                break
            burst = list(state["burst"])
            state["burst"].clear()
            try:
                # 不外包 watchdog：生成逾時改由 generate_reply 的 timeout 控（只算「鎖內生成」、
                # 不含「等鎖排隊」）→ 排在 /askai 後面時不會被誤砍。其餘 await（抓歷史 / 召回 /
                # 送出）各自有 http/API 逾時，不會無限卡。
                await _run_one_ambient_pass(bot, current, ambient_model, current_directed, burst)
            except Exception as exc:
                logger.warning("ambient pass 例外 channel=%s：%s", message.channel.id, exc, exc_info=True)
            # passes 只計「自發」輪次——max_passes_per_burst 是節制自發重評估用的額度，
            # 被 @ 是必答的，不該被它吃掉。（`max_passes_per_burst` 降成 1 之後這件事會變
            # 致命：生成那 ~120 秒內進來的 @ 會在跑完當下直接被 break 掉，要等下一則訊息
            # 才處理；沒有下一則就永遠不回。）
            if not current_directed:
                passes += 1
            # 還有待答的 @ → 一定要處理完再走。directed 每取用一次就清空，只有新的 @ 才會
            # 再設 → 不會空轉。
            if state["directed"] is not None:
                continue
            # 沒有新動靜 → 收手；自發輪次達上限也收手（避免超活躍頻道空燒 12B）
            if not state["pending"] or passes >= _SETTINGS.max_passes_per_burst:
                break
    finally:
        state["running"] = False
        state["debouncing"] = False


def _log_skip(channel_id: int, reason: str) -> None:
    """記一則被跳過的原因（gated by debug_log）；幫忙 debug『為什麼沒插話』。"""
    if _SETTINGS.debug_log:
        logger.info("ambient 跳過 channel=%s：%s", channel_id, reason)


# 對「插話本身」的不滿訊號——抓到就收手（自發插話）。只收高把握、明顯針對插話的字眼，
# 寧可偶爾誤收（多安靜一下沒差），也別漏掉群友已經喊停的情況。
_CHIME_BACKOFF_WORDS = (
    "尬聊", "閉嘴", "別吵", "話太多", "沒人問你", "你很煩", "吵死", "又是你", "別一直",
)


def _has_chime_backoff_signal(message: discord.Message, chat_context: Optional[list]) -> bool:
    """近期對話是否出現對『插話本身』的不滿 → 自發插話該收手。掃觸發訊息 + 近期 chat_history。"""
    blob = message.content or ""
    if chat_context:
        blob += " " + " ".join(chat_context)
    return any(w in blob for w in _CHIME_BACKOFF_WORDS)


# style_refs（v2）：避免同一句「好回答」連續幾則都被當靈感 → 跳針。記最近注入過的 reply，下次優先避開。
_RECENT_STYLE_REFS: "deque[str]" = deque(maxlen=40)
_RECENT_STYLE_SET: set[str] = set()


def _remember_style_ref(reply_text: str) -> None:
    if not reply_text or reply_text in _RECENT_STYLE_SET:
        return
    if len(_RECENT_STYLE_REFS) == _RECENT_STYLE_REFS.maxlen:
        _RECENT_STYLE_SET.discard(_RECENT_STYLE_REFS[0])  # 即將被擠出的最舊一筆
    _RECENT_STYLE_REFS.append(reply_text)
    _RECENT_STYLE_SET.add(reply_text)


async def _build_style_refs(situation: str) -> Optional[list]:
    """召回「與當下情境語意相近、且被群裡按過讚」的舊插話，抽樣成 <style_refs> 靈感行。

    純風格參考（學味道、別照抄）；shadow 模式（style_refs_enabled=False）只記 log、不注入。
    best-effort：任何失敗都回 None，不影響插話主流程。
    """
    if not situation or not situation.strip():
        return None
    try:
        rows = await asyncio.to_thread(
            fetch_similar_positive,
            situation,
            k=_SETTINGS.style_refs_top_k,
            max_distance=_SETTINGS.style_refs_max_distance,
            min_positive=_SETTINGS.style_refs_min_positive,
        )
    except Exception as exc:
        logger.debug("style_refs 召回失敗：%s", exc)
        return None
    if not rows:
        if _SETTINGS.style_refs_debug:
            logger.info("ambient style_refs：無相近的高讚舊回覆（情境=%r）", situation[:40])
        return None

    # 先避開最近注入過的（壓跳針）；都用過了就退回全部，再抽樣 → 每次選到的不同、有變化
    fresh = [r for r in rows if r["reply_text"] not in _RECENT_STYLE_SET]
    pool = fresh or rows
    n = min(_SETTINGS.style_refs_inject_count, len(pool))
    picked = random.sample(pool, n) if n > 0 else []

    if _SETTINGS.style_refs_debug:
        logger.info(
            "ambient style_refs 召回=%d 抽樣=%d enabled=%s | %s",
            len(rows), len(picked), _SETTINGS.style_refs_enabled,
            " ‖ ".join(
                f"d={p['distance']:.2f}讚{p['positive_reactions']}「{p['reply_text'][:30]}」"
                for p in picked
            ),
        )
    if not _SETTINGS.style_refs_enabled or not picked:
        return None  # shadow：只看 log、不真的注入

    lines: list = []
    for p in picked:
        sit = " ".join((p.get("trigger_text") or p.get("context_snippet") or "").split())[:60]
        rep = " ".join((p.get("reply_text") or "").split())
        lines.append(f"・當時情境「{sit}」→ 你回了:「{rep}」")
        _remember_style_ref(p["reply_text"])
    return lines


async def _record_ambient_interaction(
    *, message: discord.Message, directed: bool, stripped: str, has_image: bool,
    chat_context: Optional[list], reply: str, sent_msg, trace_id: str,
) -> None:
    """把這次插話寫進 ai_interactions（best-effort；sync DB → to_thread 不阻塞 loop）。"""
    try:
        if stripped:
            trigger_kind = "text"
        elif has_image:
            trigger_kind = "image"
        else:
            trigger_kind = "mention"
        # 它實際在回的那段對話：取 chat_history 末幾行（自發時末行已含觸發那句）
        snippet = "\n".join(chat_context[-8:]) if chat_context else None
        await asyncio.to_thread(
            record_interaction,
            guild_id=str(message.guild.id) if message.guild else "",
            channel_id=str(message.channel.id),
            directed=directed,
            trigger_kind=trigger_kind,
            trigger_author_id=str(message.author.id),
            trigger_message_id=str(message.id),
            trigger_text=stripped or None,
            context_snippet=snippet,
            reply_text=reply,
            reply_message_id=str(sent_msg.id) if sent_msg is not None else None,
            trace_id=trace_id,
        )
    except Exception as exc:
        logger.debug("ambient 互動紀錄寫入略過 trace=%s：%s", trace_id, exc)


def _passes_content_gate(msg: discord.Message) -> bool:
    """單則有沒有「可聊的內容」：非指令、非空、非純連結、非純表情、長度在區間內。有圖直接放行。"""
    stripped = (msg.content or "").strip()
    if _is_command_like(stripped):
        return False
    if _has_image(msg):
        return True  # 有圖，圖就是內容
    if not stripped or _is_link_only(stripped):
        return False
    if is_emoji_or_symbol_only(stripped):
        return False
    return _SETTINGS.min_chars <= len(stripped) <= _SETTINGS.max_chars


async def _run_one_ambient_pass(
    bot, message: discord.Message, ambient_model: str, directed: bool,
    burst: Optional[list] = None,
) -> None:
    """單一插話評估：閘門（內容/冷卻/讓位）→ 生成 → 送出。

    message 已通過入口硬過濾（功能開、非 bot、白名單頻道、ambient_model 有設）；
    directed 由入口判好傳入。記憶沉澱也已在入口做過。
    burst＝靜默期累積的整段訊息（內容閘看它，不是只看最後一則）。
    """
    stripped = (message.content or "").strip()
    has_image = _has_image(message)

    cid = message.channel.id
    # ── 非被點名：再過內容/冷卻/讓位（跳過原因都記 log，方便 debug）────
    if not directed:
        # 內容閘看「整段 burst」：靜默期會把一串訊息合併成一次評估，若只看最後一則，
        # 剛好收尾是貼圖或「笑死」就會把整段有料的對話一起刷掉。任一則有料就放行。
        candidates = burst or [message]
        if not any(_passes_content_gate(m) for m in candidates):
            _log_skip(cid, f"整段 burst（{len(candidates)} 則）都沒有可聊的內容")
            return

        tracker = _get_tracker(bot, cid)
        now = time.monotonic()
        if now - tracker["last_ts"] < _SETTINGS.cooldown_seconds:
            remain = _SETTINGS.cooldown_seconds - (now - tracker["last_ts"])
            _log_skip(cid, f"冷卻中（剩 {remain:.0f}s）")
            return
        if now - tracker["hour_start"] >= 3600:
            tracker["hour_start"] = now
            tracker["hour_count"] = 0
        if tracker["hour_count"] >= _SETTINGS.hourly_cap:
            _log_skip(cid, f"已達每小時上限（{_SETTINGS.hourly_cap}）")
            return

        # foreground（/askai、功能一）正在用模型或剛用過 → 讓位，避免換模型 ping-pong
        if stream_busy() or foreground_recently_active(_SETTINGS.askai_grace_seconds):
            _log_skip(cid, "前景活躍/串流忙，讓位")
            return

    else:
        tracker = _get_tracker(bot, cid)

    # ── 生成（12B；走 generate_reply → chat_raw 持 stream_exclusive）──
    # 帶 #XXXX 錨點（與 chat_history 裡 bot 自己的行 name_with_anchor 一致）→ 讓模型能精準
    # 認出 chat_history 裡哪幾行是自己講的。guild.me 是 discord.py 即時提供的 bot Member（動態暱稱）。
    bot_display_name = None
    if message.guild.me is not None:
        bot_display_name = name_with_anchor(message.guild.me)
    elif bot.user is not None:
        bot_display_name = name_with_anchor(bot.user)

    # 讓琇紫知道「當下是誰在跟它講話」——帶發話者顯示名稱 + #XXXX 錨點（跟 chat_history、
    # persona card 對齊，多人也分得清）。guardrails 已說明 #XXXX 是內部碼、不可對外講出。
    asker_display_name = name_with_anchor(message.author)

    thread_map: dict = {}
    chat_context, participant_ids = await _fetch_recent(message, thread_map)

    # 降溫硬閘：自發插話時，若近期對話出現對「插話本身」的不滿（尬聊/閉嘴/話太多…），直接收手，
    # 不勞動模型。沿用 chat_history 滑動視窗——抱怨滾出視窗後自然恢復，不需額外狀態。
    # （被 @/reply 的 directed 不受影響：對方主動找它仍照常回。）
    if not directed and _has_chime_backoff_signal(message, chat_context):
        _log_skip(message.channel.id, "偵測到降溫訊號（尬聊/叫停）→ 收手")
        return

    # ── 鉤子閘：值不值得花那 ~120s 去想。零成本結構演算法 + 少量 regex + k-NN，不動 LLM。
    # 位置在這裡＝已有完整脈絡可算特徵，但還沒付出生成代價。開不開口最終仍由模型 [PASS] 決定，
    # 所以門檻可以寬鬆；ε-greedy 探索比例會無視分數放行，避免鉤子偏好自我強化。
    hook = None
    if not directed:
        recent_msgs = [m for _no, m in sorted(thread_map.items()) if not m.author.bot]
        recent_msgs.append(message)  # thread_map 是 before=message，觸發訊息本身要補上
        hook = await evaluate_hook(recent_msgs, situation=stripped)
        if not hook.passed:
            reason = hook.veto or f"p={hook.prob:.2f}<{_SETTINGS.hook_threshold}"
            _log_skip(cid, f"鉤子閘未過（{reason}）")
            return

    system_prompt = _load_ambient_prompt()
    trace_id = f"amb-{message.channel.id}-{int(time.time() * 1000)}"

    # 看圖：有圖就準備 vision payload（QAT 12B 自帶 vision，不必換模型）
    image_payload = await _prepare_images(message) if has_image else None
    if not stripped and not image_payload and not directed:
        return  # 圖沒抓成功又沒文字 → 沒東西可接

    # ── 被回覆訊息（Discord 原生 reply）：把指涉對象明確帶進 prompt，避免「他/這個」無錨點亂答 ──
    # directed（@/reply 機器人）與自發插話都適用；best-effort，抓不到就略過。
    replied_to_from: Optional[str] = None
    replied_to_text: Optional[str] = None
    replied_msg = await _resolve_replied_to(message)
    if replied_msg is not None:
        rtext = semantic_message_text(replied_msg)
        if not rtext and _has_image(replied_msg):
            rtext = "(一張圖)"
        if rtext:
            if len(rtext) > 200:
                rtext = rtext[:200] + "…"
            replied_to_from = name_with_anchor(replied_msg.author)
            replied_to_text = rtext
        # 帶圖：被回覆訊息的圖也補進 vision payload（trigger 自己的圖優先，整體受 image_max_count 上限）
        if _has_image(replied_msg):
            ref_imgs = await _prepare_images(replied_msg)
            if ref_imgs:
                image_payload = ((image_payload or []) + ref_imgs)[:_SETTINGS.image_max_count]

    # ── 「最新訊息」框架（P1-5）：自發 vs 被點名分開包 ──
    # 被 @/reply（directed）：對方真的在跟你說話 → 維持 <latest_user_message from=發話者>。
    # 自發插話：把觸發訊息併進「你旁觀到的對話」，latest 換成中性自我提示、且不帶 from——
    # 否則結構上會把「別人對別人說的話」（尤其含「你」）誤讀成在問機器人本人（→ 答非所問/尬聊）。
    retrieval_query = stripped or "(圖片或無文字)"
    if directed:
        asker_for_bundle = asker_display_name
        if stripped:
            prompt_text = stripped
        elif image_payload:
            prompt_text = "(對方貼了一張圖)"
        else:
            prompt_text = "(對方只 @ 了我，沒有文字)"
    else:
        asker_for_bundle = None
        _ts = message.created_at.astimezone(_TAIPEI_TZ).strftime("%H:%M")
        if stripped:
            # 觸發訊息本體不截斷（time_only 不帶日期，與近期視窗一致）；compact=False 保留原貌
            chat_context = (chat_context or []) + [
                format_chat_line(message, _TAIPEI_TZ, time_only=True, compact=False)
            ]
        elif image_payload:
            chat_context = (chat_context or []) + [f"[{_ts}] {asker_display_name}: (貼了一張圖)"]
        prompt_text = (
            "（以上是你在群裡旁觀到的最新對話。最新一則是群友彼此在講話、不一定是對你說的——"
            "先判斷適不適合插話；要插就接整段對話裡的具體一點，否則只輸出 [PASS]。）"
        )

    # Phase B：認得人——召回在場成員 persona card（best-effort；用真正的觸發文字當檢索 query）
    persona_cards = await _build_persona_context(message, retrieval_query, participant_ids)
    # Phase C：召回發話者的 trusted 偏好事實（best-effort）
    memory_lines = await recall_lines(message.guild.id, message.author.id)
    # 招牌梗：召回在場成員的 trusted 標籤（衰減+三道閘；spicy 在 dark-launch 期間不召回）
    tag_lines = await recall_signature_tags(message.guild.id, participant_ids, message.guild)
    # Phase D（實驗，預設關）：本頻道歷史 callback（三因子 gate 後的模糊印象）；用真正文字當 query
    callback_lines = await _build_chat_callback_context(message, stripped)  # → 獨立 <recalled_context>
    # Phase v2：風格召回——撈「被群裡按過讚、語意相近」的舊插話當靈感（學味道別照抄；shadow 可關）
    style_ref_lines = await _build_style_refs(stripped)
    persona_context = (
        (persona_cards or []) + (memory_lines or []) + (tag_lines or [])
    ) or None

    # debug 摘要（discord_bot.log）：一眼看出各層 context 各抓到幾筆 + 有沒有圖 + 有沒有接到被回覆訊息
    logger.info(
        "ambient 生成 trace=%s directed=%s model=%s | chat=%d persona=%d memory=%d callback=%d style=%d img=%d reply_to=%d",
        trace_id, directed, ambient_model,
        len(chat_context or []), len(persona_cards or []), len(memory_lines or []),
        len(callback_lines or []), len(style_ref_lines or []),
        len(image_payload or []), 1 if replied_to_text else 0,
    )

    result = await _get_llm().generate_reply(
        prompt=prompt_text,
        system=system_prompt,
        chat_context=chat_context,
        persona_context=persona_context,
        recalled_context=callback_lines,
        style_refs=style_ref_lines,
        images=image_payload,
        model=ambient_model,
        bot_display_name=bot_display_name,
        asker_display_name=asker_for_bundle,
        replied_to_from=replied_to_from,
        replied_to_text=replied_to_text,
        # 生成 timeout＝鎖內生成的上限（chat_raw 的 timeout 在 stream_exclusive 取得後才開始算，
        # 天生不含「等鎖排隊」時間）→ 取代外層 watchdog，避免排在 /askai 後面被誤砍。
        timeout=int(_SETTINGS.pass_timeout_seconds),
        trace_id=trace_id,
    )

    reply = (result.reply or "").strip()
    sentinel = _SETTINGS.silence_sentinel
    if result.error_kind:
        outcome = f"error:{result.error_kind}"
    elif not reply or sentinel in reply:
        outcome = "pass"
    else:
        outcome = "reply"

    # 把完整 prompt（含三層 context）寫進 ambient_prompt.txt，reply/pass/error 都記，方便 debug
    _write_ambient_debug(
        trace_id=trace_id, prompt_record_log=result.prompt_record_log,
        outcome=outcome, reply=reply,
    )

    if result.error_kind:
        logger.info("ambient 生成失敗 kind=%s trace=%s，略過", result.error_kind, trace_id)
        return
    if outcome == "pass":
        # 模型自判「沒梗」→ 不發送（Phase C 之後在此轉傾聽/抽記憶）
        return

    sent_msg = None
    try:
        if directed:
            try:
                sent_msg = await message.reply(reply, mention_author=False)
            except discord.HTTPException as reply_exc:
                # 原訊息可能已被刪除（reply reference 失效，50035 Unknown message）→
                # 退而求其次直接發到頻道，照樣回得到、只是沒有 reply 串接
                logger.info(
                    "ambient reply 失敗（原訊息可能已刪？）trace=%s：%s → 改直接發頻道",
                    trace_id, reply_exc,
                )
                sent_msg = await message.channel.send(
                    reply, allowed_mentions=discord.AllowedMentions.none()
                )
        else:
            sent_msg = await message.channel.send(
                reply, allowed_mentions=discord.AllowedMentions.none()
            )
    except discord.HTTPException as exc:
        logger.warning("ambient 送出回覆失敗 trace=%s：%s", trace_id, exc)
        return

    # 只有「自發插話」才計入冷卻/每小時額度；被 @ 是 user 主動要的，不該吃掉自發的額度（否則
    # 一直 @ 它測試就會把自發插話餓死、整個小時靜默）。
    if not directed:
        _note_sent(tracker)
    logger.info(
        "ambient 已插話 trace=%s 頻道=%s directed=%s",
        trace_id, message.channel.id, directed,
    )

    # 互動紀錄（best-effort、不阻塞）：記下「自己這次說了什麼、對誰、在聊什麼」→ 日記/好感度的素材
    await _record_ambient_interaction(
        message=message, directed=directed, stripped=stripped, has_image=has_image,
        chat_context=chat_context, reply=reply, sent_msg=sent_msg, trace_id=trace_id,
    )
