"""
Discord 相關共用工具函式

供 article_monitor / bahamut_monitor 等多個來源共用。
"""
import hashlib
import re
from typing import List

import discord

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
