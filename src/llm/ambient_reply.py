"""功能二：AI 偶爾插話 / 閒聊（Phase A 骨架）。

掛在 `discord_bot.on_message`，以背景 task 執行，不阻塞訊息處理。

觸發哲學（由便宜到貴，任一關卡不過就 return，多數訊息連模型都不勞動）：
    硬性過濾（零成本） → 冷卻 / 每小時上限 → foreground 讓位 → 12B 判斷（回 / [PASS] 沉默）

「偶爾」感由冷卻 + 每小時上限保證；插不插由 12B 自己判斷，不擲骰。冷卻期內連判斷都不跑（省 12B）。
`judge_sampling_rate`（預設 1.0）是純減壓閥：頻道太吵時才抽樣降載，預設不作用。

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
import random
import time
from pathlib import Path
from typing import Optional

import discord

from llm.ambient_memory import enqueue_for_memory, recall_lines
from llm.lemonade_gate import foreground_recently_active, stream_busy
from llm.logger_factory import get_or_create_file_logger
from services.llm_service import LLMService
from sys_settings.llm_settings import AmbientChatSettings
from utils.utils import ChannelConfig

logger = logging.getLogger("discord_bot")

_SETTINGS = AmbientChatSettings()

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
    """組 ambient system prompt：共用人設身份（琇紫）+ 插話行為規則。

    身份來自 `persona_identity.txt`（與 /askai 同一份），確保插話與問答是同一個角色；
    行為來自 `ambient_reply_prompt.txt`（簡短、允許沉默）。以兩檔 mtime 組合快取。
    """
    paths: list[Path] = []
    if _SETTINGS.use_shared_identity and _SETTINGS.identity_path:
        paths.append(Path(_SETTINGS.identity_path))      # 共用人格
    if _SETTINGS.guardrails_path:
        paths.append(Path(_SETTINGS.guardrails_path))    # 共用守則/限制
    paths.append(Path(_SETTINGS.prompt_path))            # 插話行為

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


def _name_with_anchor(author) -> str:
    """顯示名稱 + #XXXX（user_id 後四碼），跟 persona card 標題對齊，穩定分辨同名/相似的人。"""
    name = getattr(author, "display_name", None) or author.name
    uid = str(getattr(author, "id", "") or "")
    short = uid[-4:] if len(uid) >= 4 else ""
    return f"{name}#{short}" if short else name


async def _fetch_recent(
    message: discord.Message,
) -> tuple[Optional[list[str]], list[int]]:
    """抓近期頻道訊息：回 (對話脈絡行[舊→新], 近期發言者 user_id)。

    對話脈絡含機器人自己的話以維持連續性；participant_ids 只收非 bot，給 persona 召回用。
    """
    collected: list[str] = []
    participant_ids: list[int] = []
    try:
        async for msg in message.channel.history(
            limit=_SETTINGS.history_limit, before=message
        ):
            if not msg.author.bot and msg.author.id not in participant_ids:
                participant_ids.append(msg.author.id)
            text = (msg.content or "").strip()
            if not text:
                continue
            name = _name_with_anchor(msg.author)
            if len(text) > 200:
                text = text[:200] + "…"
            collected.append(f"{name}: {text}")
    except Exception as exc:
        logger.debug("ambient 抓取頻道歷史失敗：%s", exc)
    collected.reverse()
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


# per-channel 序列處理狀態：同頻道同時只有一個 ambient 在跑。生成期間進來的訊息不平行觸發，
# 只更新 latest / 標 pending；等這次跑完，再用「最新」對話狀態重新評估要不要插（@ 走 directed 優先答）。
_PROC_STATE: dict = {}  # channel_id -> {running, pending, latest, directed}


def _get_proc_state(channel_id: int) -> dict:
    st = _PROC_STATE.get(channel_id)
    if st is None:
        st = {"running": False, "pending": False, "latest": None, "directed": None}
        _PROC_STATE[channel_id] = st
    return st


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
        if _is_directed(bot, message):
            state["directed"] = message
        if state["running"]:
            state["pending"] = True   # 已有處理器在跑 → 只記新動靜，等它回來重評估
            if _SETTINGS.debug_log:
                logger.info("ambient 吸收 channel=%s：處理器忙，待這輪跑完用最新狀態重評估", message.channel.id)
            return
        state["running"] = True
    except Exception as exc:
        logger.warning("ambient 入口例外：%s", exc, exc_info=True)
        return

    # ── 序列處理迴圈（同頻道唯一）：跑完一輪後若有新動靜/待答的 @ 就用最新狀態再跑一輪 ──
    try:
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
            try:
                await asyncio.wait_for(
                    _run_one_ambient_pass(bot, current, ambient_model, current_directed),
                    timeout=_SETTINGS.pass_timeout_seconds,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "ambient pass 逾時取消 channel=%s（>%.0fs）—— 釋放頻道、不鎖死",
                    message.channel.id, _SETTINGS.pass_timeout_seconds,
                )
            except Exception as exc:
                logger.warning("ambient pass 例外 channel=%s：%s", message.channel.id, exc, exc_info=True)
            passes += 1
            # 沒有新動靜也沒有待答 @ → 收手；達上限也收手（避免超活躍頻道空燒 12B）
            if (not state["pending"] and state["directed"] is None) or passes >= _SETTINGS.max_passes_per_burst:
                break
    finally:
        state["running"] = False


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


async def _run_one_ambient_pass(
    bot, message: discord.Message, ambient_model: str, directed: bool
) -> None:
    """單一插話評估：閘門（內容/冷卻/讓位/機率）→ 生成 → 送出。

    message 已通過入口硬過濾（功能開、非 bot、白名單頻道、ambient_model 有設）；
    directed 由入口判好傳入。記憶沉澱也已在入口做過。
    """
    stripped = (message.content or "").strip()
    has_image = _has_image(message)

    cid = message.channel.id
    # ── 非被點名：再過內容/冷卻/讓位/機率（跳過原因都記 log，方便 debug）────
    if not directed:
        if _is_command_like(stripped):
            _log_skip(cid, "指令訊息")
            return
        if not has_image:
            # 純文字才要求：非空、非純連結、長度在區間內（有圖則圖就是內容，放行）
            if not stripped or _is_link_only(stripped):
                _log_skip(cid, "空訊息或純連結")
                return
            n = len(stripped)
            if n < _SETTINGS.min_chars or n > _SETTINGS.max_chars:
                _log_skip(cid, f"長度 {n} 不在 {_SETTINGS.min_chars}~{_SETTINGS.max_chars}")
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

        # 減壓閥（預設 1.0 不作用）：太吵時抽樣降載，避免每則都勞動 12B；插不插仍由 12B 決定
        if _SETTINGS.judge_sampling_rate < 1.0 and random.random() > _SETTINGS.judge_sampling_rate:
            _log_skip(cid, "減壓閥抽樣跳過")
            return
    else:
        tracker = _get_tracker(bot, cid)

    # ── 生成（12B；走 generate_reply → chat_raw 持 stream_exclusive）──
    bot_display_name = None
    if message.guild.me is not None:
        bot_display_name = message.guild.me.display_name
    elif bot.user is not None:
        bot_display_name = bot.user.name

    # 讓琇紫知道「當下是誰在跟它講話」——帶發話者顯示名稱 + #XXXX 錨點（跟 chat_history、
    # persona card 對齊，多人也分得清）。guardrails 已說明 #XXXX 是內部碼、不可對外講出。
    asker_display_name = _name_with_anchor(message.author)

    chat_context, participant_ids = await _fetch_recent(message)

    # 降溫硬閘：自發插話時，若近期對話出現對「插話本身」的不滿（尬聊/閉嘴/話太多…），直接收手，
    # 不勞動模型。沿用 chat_history 滑動視窗——抱怨滾出視窗後自然恢復，不需額外狀態。
    # （被 @/reply 的 directed 不受影響：對方主動找它仍照常回。）
    if not directed and _has_chime_backoff_signal(message, chat_context):
        _log_skip(message.channel.id, "偵測到降溫訊號（尬聊/叫停）→ 收手")
        return

    system_prompt = _load_ambient_prompt()
    trace_id = f"amb-{message.channel.id}-{int(time.time() * 1000)}"

    # 看圖：有圖就準備 vision payload（QAT 12B 自帶 vision，不必換模型）
    image_payload = await _prepare_images(message) if has_image else None
    if not stripped and not image_payload and not directed:
        return  # 圖沒抓成功又沒文字 → 沒東西可接

    if stripped:
        prompt_text = stripped
    elif image_payload:
        prompt_text = "(對方貼了一張圖)"
    else:
        prompt_text = "(對方只 @ 了我，沒有文字)"

    # Phase B：認得人——召回在場成員 persona card（best-effort）
    persona_cards = await _build_persona_context(message, prompt_text, participant_ids)
    # Phase C：召回發話者的 trusted 偏好事實（best-effort）
    memory_lines = await recall_lines(message.guild.id, message.author.id)
    persona_context = ((persona_cards or []) + (memory_lines or [])) or None

    # debug 摘要（discord_bot.log）：一眼看出三層 context 各抓到幾筆 + 有沒有圖
    logger.info(
        "ambient 生成 trace=%s directed=%s model=%s | chat=%d persona=%d memory=%d img=%d",
        trace_id, directed, ambient_model,
        len(chat_context or []), len(persona_cards or []), len(memory_lines or []),
        len(image_payload or []),
    )

    result = await _get_llm().generate_reply(
        prompt=prompt_text,
        system=system_prompt,
        chat_context=chat_context,
        persona_context=persona_context,
        images=image_payload,
        model=ambient_model,
        bot_display_name=bot_display_name,
        asker_display_name=asker_display_name,
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

    try:
        if directed:
            try:
                await message.reply(reply, mention_author=False)
            except discord.HTTPException as reply_exc:
                # 原訊息可能已被刪除（reply reference 失效，50035 Unknown message）→
                # 退而求其次直接發到頻道，照樣回得到、只是沒有 reply 串接
                logger.info(
                    "ambient reply 失敗（原訊息可能已刪？）trace=%s：%s → 改直接發頻道",
                    trace_id, reply_exc,
                )
                await message.channel.send(
                    reply, allowed_mentions=discord.AllowedMentions.none()
                )
        else:
            await message.channel.send(
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
