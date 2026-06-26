"""功能二記憶串接（Phase C-3）：把插話頻道訊息收進緩衝 → 閒置批次抽取沉澱 → 召回。

走 `MemoryService` 門面，本檔只負責「訊息來源緩衝 + 排程 flush + 召回格式」這層膠水：
  - enqueue_for_memory：on_message 流裡，插話頻道每則（非 bot、有內容）收進緩衝。
  - maybe_flush：背景排程週期呼叫；緩衝夠量且**前景(/askai)閒置**時才真的跑 12B 抽取（避免換模型）。
  - recall_lines：插話生成前，召回該發話者的 trusted 偏好，注入 persona_context。
"""
from __future__ import annotations

import asyncio
import functools
import logging
import re
from datetime import datetime, timezone
from typing import Optional

import discord

from llm.member_profile_store import get_member_profile_store
from llm.lemonade_gate import foreground_recently_active, stream_busy
from services.llm_service import LLMService
from services.memory_service import get_memory_service
from sys_settings.llm_settings import AmbientChatSettings

logger = logging.getLogger("discord_bot")

_SETTINGS = AmbientChatSettings()

# 記憶緩衝：插話頻道訊息 {guild_id, author_id, alias, text}（背景批次抽取偏好用）
_BUFFER: list[dict] = []

_LLM_SERVICE: Optional[LLMService] = None


def _get_llm() -> LLMService:
    global _LLM_SERVICE
    if _LLM_SERVICE is None:
        _LLM_SERVICE = LLMService()
    return _LLM_SERVICE


def enqueue_for_memory(message: discord.Message) -> None:
    """把一則插話頻道訊息收進記憶緩衝（呼叫端已確認在白名單頻道、非 bot）。"""
    text = (message.content or "").strip()
    if not text or message.guild is None:
        return
    alias = getattr(message.author, "display_name", None) or message.author.name
    _BUFFER.append({
        "guild_id": message.guild.id,
        "author_id": message.author.id,
        "alias": alias or "",
        "text": text[:300],
    })
    # 上限保護：超過就丟最舊
    overflow = len(_BUFFER) - _SETTINGS.memory_buffer_max
    if overflow > 0:
        del _BUFFER[:overflow]


def buffer_size() -> int:
    return len(_BUFFER)


async def maybe_flush(*, force: bool = False) -> dict:
    """背景排程呼叫：緩衝夠量且前景閒置時，跑一次偏好抽取沉澱。

    閒置守門：stream 忙或 /askai 近期活躍 → 跳過（避免把 12B 換掉、跟前景搶）。
    """
    if not _BUFFER:
        return {"flushed": 0, "reason": "empty"}
    if not force and len(_BUFFER) < _SETTINGS.memory_flush_threshold:
        return {"flushed": 0, "reason": "below_threshold"}
    if not force and (stream_busy() or foreground_recently_active(_SETTINGS.askai_grace_seconds)):
        return {"flushed": 0, "reason": "foreground_busy"}

    model = _get_llm().resolve_ambient_model()
    if not model:
        return {"flushed": 0, "reason": "no_model"}

    # 快照後清空，讓新訊息能繼續累積（抽取期間不卡 enqueue）
    batch = _BUFFER[:]
    _BUFFER.clear()

    by_guild: dict[int, list[dict]] = {}
    for item in batch:
        by_guild.setdefault(item["guild_id"], []).append(item)

    svc = get_memory_service()
    totals = {"written": 0, "new": 0, "promoted": 0, "skipped_conf": 0}
    for guild_id, messages in by_guild.items():
        try:
            stats = await svc.observe(guild_id=guild_id, messages=messages, model=model)
            for key in totals:
                totals[key] += int(stats.get(key, 0))
        except Exception as exc:
            logger.warning("ambient 記憶 flush 失敗 guild=%s：%s", guild_id, exc, exc_info=True)

    logger.info("ambient 記憶 flush：批次 %d 則 → %s", len(batch), totals)
    return {"flushed": len(batch), **totals}


async def recall_lines(guild_id: int, user_id: int) -> Optional[list[str]]:
    """召回某發話者的 trusted 偏好，壓成 persona_context 風格的行（best-effort）。"""
    try:
        svc = get_memory_service()
        facts = await svc.recall(
            guild_id=guild_id, user_id=user_id,
            only_trusted=True, limit=_SETTINGS.memory_recall_top_k,
        )
        return svc.format_recall(facts)
    except Exception as exc:
        logger.debug("ambient 記憶召回失敗：%s", exc)
        return None


_ALIAS_SANITIZE_RE = re.compile(r"[<>\[\]{}()\n\r\t`|\\〈-〟＀-／：-＠［-｀｛-･]")


def _tag_effective_strength(row: dict, now: datetime) -> float:
    """招牌梗即時衰減：mention_count × 0.5^(沉默天數/半衰期)。spicy 半衰期更短、淡得快。"""
    try:
        count = int(row.get("mention_count", "1") or "1")
    except ValueError:
        count = 1
    days = 0.0
    try:
        last_dt = datetime.fromisoformat(row.get("last_seen", ""))
        days = max(0.0, (now - last_dt).total_seconds() / 86400.0)
    except Exception:
        pass
    halflife = (
        _SETTINGS.tag_halflife_spicy_days if row.get("sensitivity") == "spicy"
        else _SETTINGS.tag_halflife_low_days
    )
    return count * (0.5 ** (days / max(halflife, 1.0)))


async def recall_signature_tags(
    guild_id: int,
    participant_ids: list[int],
    guild: Optional[discord.Guild] = None,
) -> Optional[list[str]]:
    """召回在場成員的 trusted 招牌梗（批撈 + 即時衰減 + 三道閘）→ persona_context 行（best-effort）。

    閘：suppressed 永不召回；spicy 在 dark-launch 期間不召回（寫庫但不 callback）；已離開 guild 不召回。
    """
    if not participant_ids:
        return None
    try:
        port = get_member_profile_store()
        loop = asyncio.get_running_loop()
        rows = await loop.run_in_executor(
            None,
            functools.partial(
                port.list_signature_tags,
                guild_id=guild_id, author_ids=list(participant_ids), only_trusted=True,
            ),
        )
        if not rows:
            return None
        now = datetime.now(timezone.utc)
        scored: list[tuple] = []
        for r in rows:
            if r.get("suppressed") == "1":
                continue
            if r.get("sensitivity") == "spicy" and _SETTINGS.tag_spicy_dark_launch:
                continue  # dark-launch：spicy 寫庫但不召回
            try:
                aid = int(r.get("author_id", "0"))
            except (TypeError, ValueError):
                aid = 0
            member = None
            if guild is not None:
                member = guild.get_member(aid)
                if member is None:
                    continue  # 已離開 guild
            eff = _tag_effective_strength(r, now)
            if eff < _SETTINGS.tag_recall_floor:
                continue
            scored.append((eff, r, member, aid))
        scored.sort(key=lambda x: x[0], reverse=True)
        lines: list[str] = []
        for _eff, r, member, aid in scored[: _SETTINGS.tag_recall_top_k]:
            # 現名優先（成員可能改暱稱）；附 #後四碼錨點，與 chat_history / persona card 的
            # 「顯示名#後四碼」對齊，避免兩個同名成員在場時把 A 的梗安到 B（張冠李戴）。
            raw_name = (getattr(member, "display_name", None) if member else None) \
                or r.get("alias") or "某人"
            name = _ALIAS_SANITIZE_RE.sub("", raw_name)[:20] or "某人"
            anchor = f"#{str(aid)[-4:]}" if aid else ""
            note = (
                "（敏感梗，僅當對方此刻自己又玩到才順勢回扣）"
                if r.get("sensitivity") == "spicy" else ""
            )
            lines.append(f"（{name}{anchor} 的招牌梗）{r.get('tag', '')}{note}")
        return lines or None
    except Exception as exc:
        logger.debug("ambient 招牌梗召回失敗：%s", exc)
        return None
