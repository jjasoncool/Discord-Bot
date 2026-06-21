"""AI 每日日記回顧（v1）。

每天在專屬頻道用琇紫口吻寫一段當天感想——**純表達、不改行為**：只反映它對今天的
感受，不影響它對任何人的插話態度。與 ambient 共用人格/守則 prompt（只換最後一層為
日記行為）；社交來源預設＝插話頻道（ambient_chat_channel_id）。

流程（每天 00:00 台北時區，或 /ai_diary 手動觸發）：
    讀社交頻道過去 24h 互動 → 組日記 prompt → LLMService.generate_reply（持單流鎖）
    → po 到日記頻道。
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import discord

from llm.ambient_reply import _get_llm, _name_with_anchor
from llm.logger_factory import get_or_create_file_logger
from sys_settings.llm_settings import DiaryReflectionSettings
from utils.utils import ChannelConfig

logger = logging.getLogger("discord_bot")

_SETTINGS = DiaryReflectionSettings()

_DEFAULT_DIARY_PROMPT = (
    "你是 Discord 群裡的琇紫。夜深了，獨自在自己的頻道，寫一段今天的日記——"
    "第一人稱、以你自己的感受為主，自然帶到今天群裡發生的事與大家的反應。"
    "一到三小段，口語、不條列、不 markdown，只用繁體中文。"
)


def _read_text_file(path: Path) -> str:
    try:
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
    except Exception as exc:
        logger.warning("載入日記 prompt 檔失敗（%s）：%s", path, exc)
    return ""


def _load_diary_prompt() -> str:
    """組日記 system prompt：共用人格 + 共用守則 + 日記行為。每天一次，直接讀檔不快取。"""
    paths: list[Path] = []
    if _SETTINGS.use_shared_identity and _SETTINGS.identity_path:
        paths.append(Path(_SETTINGS.identity_path))
    if _SETTINGS.guardrails_path:
        paths.append(Path(_SETTINGS.guardrails_path))
    paths.append(Path(_SETTINGS.prompt_path))
    chunks = [t for t in (_read_text_file(p) for p in paths) if t]
    return "\n\n".join(chunks).strip() or _DEFAULT_DIARY_PROMPT


def _resolve_channel_id(config: dict, key: str) -> Optional[int]:
    """從 channel config 取一個有效的頻道 id（無效/未設定回 None）。"""
    raw = config.get(key)
    try:
        cid = int(raw)
    except (TypeError, ValueError):
        return None
    if cid <= 0 or cid == ChannelConfig.DEFAULT_ID:
        return None
    return cid


async def _gather_day_transcript(channel: discord.abc.Messageable) -> list[str]:
    """抓社交頻道過去 lookback_hours 的訊息（最近 max_messages 則）→ 時序 chat_history 行。"""
    after = datetime.now(timezone.utc) - timedelta(hours=_SETTINGS.lookback_hours)
    lines: list[str] = []
    try:
        async for msg in channel.history(
            limit=_SETTINGS.max_messages, after=after, oldest_first=False
        ):
            text = (msg.content or "").strip()
            if not text:
                continue
            name = _name_with_anchor(msg.author)
            if len(text) > _SETTINGS.max_chars_per_msg:
                text = text[: _SETTINGS.max_chars_per_msg] + "…"
            lines.append(f"{name}: {text}")
    except Exception as exc:
        logger.warning("日記抓取頻道歷史失敗：%s", exc)
    lines.reverse()  # newest-first → 時序（舊→新）
    return lines


def _write_diary_debug(*, trace_id: str, prompt_record_log: str, diary: str) -> None:
    if not _SETTINGS.debug_log:
        return
    try:
        dbg = get_or_create_file_logger(
            name="diary_prompt_trace",
            log_path=Path(_SETTINGS.debug_prompt_log_path),
            mode="size",
            max_bytes=_SETTINGS.debug_log_max_bytes,
            backup_count=_SETTINGS.debug_log_backup_count,
        )
        line = "=" * 24
        dbg.info(
            f"\n{line} DIARY trace={trace_id} {line}\n{prompt_record_log}\n"
            f"---- diary ----\n{diary or '(無)'}\n{line} END {line}\n"
        )
    except Exception as exc:
        logger.warning("寫入日記 debug 失敗 trace=%s：%s", trace_id, exc)


async def run_daily_reflection(bot) -> Optional[str]:
    """跑一次每日日記：抓社交頻道 24h 互動 → 生成 → po 到日記頻道。回傳發出的日記文字（或 None）。"""
    if not _SETTINGS.enabled:
        return None

    config = ChannelConfig.load_config(caller="diary_reflection")
    diary_cid = _resolve_channel_id(config, _SETTINGS.diary_channel_config_key)
    if diary_cid is None:
        logger.info("日記略過：未設定日記頻道（%s）", _SETTINGS.diary_channel_config_key)
        return None
    diary_channel = bot.get_channel(diary_cid)
    if diary_channel is None:
        logger.warning("日記略過：找不到日記頻道 id=%s（bot 不在該頻道？）", diary_cid)
        return None

    source_cid = _resolve_channel_id(config, _SETTINGS.source_channel_config_key)
    source_channel = bot.get_channel(source_cid) if source_cid else None
    transcript = await _gather_day_transcript(source_channel) if source_channel else []

    bot_display_name = None
    guild = getattr(diary_channel, "guild", None)
    if guild is not None and guild.me is not None:
        bot_display_name = guild.me.display_name
    elif bot.user is not None:
        bot_display_name = bot.user.name

    llm = _get_llm()
    model = _SETTINGS.model or llm.resolve_ambient_model()
    trace_id = f"diary-{diary_cid}-{int(time.time())}"
    prompt_text = "（現在是深夜，群裡安靜下來了。回顧今天，寫一段你自己的日記。）"

    logger.info(
        "日記生成 trace=%s model=%s 來源訊息=%d", trace_id, model, len(transcript)
    )
    result = await llm.generate_reply(
        prompt=prompt_text,
        system=_load_diary_prompt(),
        chat_context=transcript or None,
        model=model,
        think=_SETTINGS.think,
        bot_display_name=bot_display_name,
        trace_id=trace_id,
    )

    diary = (result.reply or "").strip()
    _write_diary_debug(
        trace_id=trace_id, prompt_record_log=result.prompt_record_log, diary=diary
    )

    if result.error_kind:
        logger.warning("日記生成失敗 kind=%s trace=%s", result.error_kind, trace_id)
        return None
    if not diary:
        logger.info("日記生成為空 trace=%s，不發布", trace_id)
        return None

    diary = diary[: _SETTINGS.max_diary_chars]
    try:
        await diary_channel.send(diary)
    except discord.HTTPException as exc:
        logger.warning("日記發布失敗 trace=%s：%s", trace_id, exc)
        return None

    logger.info(
        "日記已發布 channel=%s 長度=%d 來源訊息=%d trace=%s",
        diary_cid, len(diary), len(transcript), trace_id,
    )
    return diary
