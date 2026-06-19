"""
Discord 相關共用工具函式

供 article_monitor / bahamut_monitor 等多個來源共用。
"""
import asyncio
import hashlib
import logging
import re
from typing import List, Optional

import discord

logger = logging.getLogger(__name__)

# 常見圖片副檔名（各 monitor 共用）
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp")


def sanitize_forum_thread_title(title: str, content: str = "", fallback: str = "（無標題）") -> str:
    """清理 forum thread 標題（Discord 上限 100 字元）。
    若 title 為空，嘗試從 content 取前 20 字作為替代。
    """
    sanitized = (title or "").replace("\n", " ").replace("\r", " ").strip()
    sanitized = re.sub(r"\s+", " ", sanitized)
    if not sanitized:
        content_preview = (content or "").replace("\n", " ").replace("\r", " ").strip()
        content_preview = re.sub(r"\s+", " ", content_preview)
        sanitized = content_preview[:20] if content_preview else fallback
    return sanitized[:100]


def linkify_image_urls(text: str) -> str:
    """將文字中的裸圖片 URL 轉為 markdown 連結 [🖼 圖片](url)。"""
    def _replace(match):
        url = match.group(0)
        lower = url.lower().split("?")[0]  # 去掉 query string 再判斷
        if any(lower.endswith(ext) for ext in IMAGE_EXTENSIONS):
            return f"[🖼 圖片]({url})"
        return url
    return re.sub(r'https?://[^\s<>"]+', _replace, text)


def content_hash(text: str) -> str:
    """快速 hash，用來比對 embed 內容是否有變化。"""
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def chunk_discord_files(files: List[discord.File], chunk_size: int = 10) -> List[List[discord.File]]:
    """將 Discord 附件依 Discord 限制切成多批。"""
    if not files:
        return []
    return [files[i:i + chunk_size] for i in range(0, len(files), chunk_size)]


async def get_forum_tags(channel: discord.ForumChannel, tag_name: str) -> List[discord.ForumTag]:
    """從 forum channel 取得指定名稱的 tag。"""
    for tag in channel.available_tags:
        if tag.name == tag_name:
            return [tag]
    return []


async def post_to_channel(
    channel: discord.abc.GuildChannel,
    *,
    content: Optional[str] = None,
    embed: Optional[discord.Embed] = None,
    embeds: Optional[List[discord.Embed]] = None,
    files: Optional[List[discord.File]] = None,
    thread_title: Optional[str] = None,
    tags: Optional[List[discord.ForumTag]] = None,
    follow_up_label: Optional[str] = None,
    files_per_message: int = 10,
) -> Optional[discord.Message]:
    """依「綁定的頻道型別」自動決定發文方式，並穩健處理附件：

      - ForumChannel          → create_thread()，每則開一個新 thread
        （thread_title 當標題，空時自動從 content 取前 20 字；tags 會帶成 applied_tags）。
      - TextChannel / Thread  → send()，直接發一則訊息。

    附件處理（兩種型別一致）：
      - 第一則最多帶 files_per_message 張附件，其餘自動分批以後續訊息補送。
      - 若「帶附件的第一則」因 HTTPException 失敗（多半是檔案太大/上傳失敗），
        自動退成純文字重發，並把所有附件改走後續批次補送。
      - follow_up_label 當第一個補送批次的說明文字（例：「本文附圖（後續補送）」）。

    回傳首則 discord.Message（forum 為 thread 首則）；呼叫端可用 msg.channel
    取得 thread / 文字頻道繼續發後續內容（留言等），forum / text 寫法一致。

    這是給「要同時支援論壇或文字頻道」的功能用的共用入口；
    現有只發單一型別的程式可逐步改用它，但不是必須。
    """
    files = list(files or [])
    initial_files = files[:files_per_message]
    remaining_files = files[files_per_message:]

    async def _post_initial(attachments: List[discord.File]) -> Optional[discord.Message]:
        kwargs = {}
        if content is not None:
            kwargs["content"] = content
        if embed is not None:
            kwargs["embed"] = embed
        if embeds is not None:
            kwargs["embeds"] = embeds
        if attachments:
            kwargs["files"] = attachments
        if isinstance(channel, discord.ForumChannel):
            if tags:
                kwargs["applied_tags"] = tags
            title = sanitize_forum_thread_title(thread_title or "", content or "")
            created = await channel.create_thread(name=title, **kwargs)
            # discord.py 2.x 的 create_thread 回傳 ThreadWithMessage(.thread/.message)
            return getattr(created, "message", None)
        return await channel.send(**kwargs)

    try:
        starter = await _post_initial(initial_files)
    except discord.HTTPException:
        if not initial_files:
            raise  # 不是附件造成的失敗，往上拋給呼叫端處理
        logger.error(
            "post_to_channel 帶附件發文失敗，改用純文字 fallback，附件改走後續批次補送",
            exc_info=True,
        )
        starter = await _post_initial([])
        remaining_files = files  # 全部附件都改後送

    target = getattr(starter, "channel", None)
    if target is not None and remaining_files:
        for idx, chunk in enumerate(chunk_discord_files(remaining_files, files_per_message)):
            if idx == 0 and follow_up_label:
                await target.send(follow_up_label, files=chunk)
            else:
                await target.send(files=chunk)
            await asyncio.sleep(0.5)

    return starter
