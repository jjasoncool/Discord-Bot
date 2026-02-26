"""LLM 對話上下文檢索。"""

from __future__ import annotations

import logging
from datetime import timezone

import discord

from llm import context_relevance_score


def _build_discord_context_item(msg: discord.Message, tz: timezone) -> dict[str, str]:
    """
    回傳包含元資料的 dict，確保可觀測性與後續 Debug 能力。
    同時將給 LLM 看的文字組合在 'content' 欄位中。
    """
    display_name = getattr(msg.author, "display_name", msg.author.name)
    time_str = msg.created_at.astimezone(tz).strftime("%Y-%m-%d %H:%M")
    compact_content = " ".join(msg.content.split())

    # 產出格式範例：[2026-02-26 14:30] 老哥(98765432): 昨天抽卡又保底了
    formatted_text = f"[{time_str}] {display_name}({msg.author.id}): {compact_content}"

    return {
        "role": "user",
        "content": formatted_text,
        "message_id": str(msg.id),
        "author_id": str(msg.author.id),
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
            "/askai discord context stats: fetched=%s recent=%s relevant=%s selected=%s trimmed=%s sent=%s",
            meta["fetched_count"], meta["recent_selected_count"],
            meta["relevant_selected_count"], meta["selected_count_before_trim"],
            meta["trimmed_count"], meta["sent_count"]
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
