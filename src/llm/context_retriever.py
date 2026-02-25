"""LLM 對話上下文檢索。"""

from __future__ import annotations

import logging
from datetime import timezone

import discord

from llm import context_relevance_score


def _build_discord_context_item(msg: discord.Message, tz: timezone) -> dict[str, str]:
    display_name = getattr(msg.author, "display_name", msg.author.name)
    timestamp = msg.created_at.astimezone(tz)
    compact_content = " ".join(msg.content.split())
    return {
        "role": "user",
        "content": (
            f"[source=discord]"
            f"[user_id={msg.author.id}]"
            f"[username={display_name}]"
            f"[message_id={msg.id}]"
            f"[channel_id={msg.channel.id}]"
            f"[time={timestamp:%Y-%m-%d %H:%M:%S %z}]"
            f" {compact_content}"
        ),
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
) -> tuple[list[dict[str, str]], dict[str, int]]:
    """從 Discord 歷史訊息檢索上下文：近期保底 + 問題關聯。"""
    context: list[dict[str, str]] = []
    meta = {
        "fetched_count": 0,
        "recent_selected_count": 0,
        "relevant_selected_count": 0,
        "selected_count_before_trim": 0,
        "trimmed_count": 0,
        "sent_count": 0,
    }

    try:
        if not isinstance(interaction.channel, (discord.TextChannel, discord.Thread)):
            return context, meta

        history_messages = [
            msg
            async for msg in interaction.channel.history(limit=max_context_messages)
            if not msg.author.bot
        ]
        meta["fetched_count"] = len(history_messages)
        ordered_messages = list(reversed(history_messages))  # 舊 -> 新

        recent_start_index = max(0, len(ordered_messages) - min_recent_context)
        selected_indices = {
            idx
            for idx, msg in enumerate(ordered_messages)
            if idx >= recent_start_index and msg.content and msg.content.strip()
        }
        meta["recent_selected_count"] = len(selected_indices)

        relevant_candidates: list[tuple[int, int]] = []
        for idx, msg in enumerate(ordered_messages):
            if not msg.content or not msg.content.strip():
                continue

            score = context_relevance_score(question, msg.content)
            if score > 0:
                # 先比關聯分數，再偏好較新的訊息
                relevant_candidates.append((score, idx))

        relevant_candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
        top_relevant_indices = {
            idx for _, idx in relevant_candidates[:max_relevant_context]
        }
        meta["relevant_selected_count"] = len(top_relevant_indices)
        selected_indices.update(top_relevant_indices)

        selected_messages = [ordered_messages[idx] for idx in sorted(selected_indices)]
        context.extend(
            _build_discord_context_item(msg, taipei_tz) for msg in selected_messages
        )

        meta["selected_count_before_trim"] = len(context)
        if len(context) > max_context_to_send:
            meta["trimmed_count"] = len(context) - max_context_to_send
            context = context[-max_context_to_send:]

        meta["sent_count"] = len(context)
        logger.info(
            "/askai discord context stats: fetched=%s recent=%s relevant=%s selected=%s trimmed=%s sent=%s (fetch_limit=%s send_limit=%s)",
            meta["fetched_count"],
            meta["recent_selected_count"],
            meta["relevant_selected_count"],
            meta["selected_count_before_trim"],
            meta["trimmed_count"],
            meta["sent_count"],
            max_context_messages,
            max_context_to_send,
        )
    except Exception as exc:
        logger.warning("讀取聊天上下文失敗: %s", exc)

    return context, meta


async def retrieve_rag_context(
    question: str,
) -> tuple[list[dict[str, str]], dict[str, int | bool]]:
    """RAG 檢索擴充點：目前先保留介面，尚未啟用資料來源。"""
    _ = question
    return [], {
        "enabled": False,
        "sent_count": 0,
    }
