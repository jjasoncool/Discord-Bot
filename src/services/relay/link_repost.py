"""把群友貼的 X 影片、bilibili 影片換成 Discord 能播的網址轉貼出來；新預覽真的出現了，才壓掉原訊息的預覽。

架構定位：功能層（`services/relay`），吃 Discord 訊息物件。
  - 上層（誰呼叫）：`discord_bot.on_message`（每則訊息丟背景跑 `repost_fixed_links`）。
  - 下層（呼叫誰）：`utils.link_fix`（挑網址、預檢、組內文）；Discord（回覆、等訊息更新、壓預覽、刪訊息）。

介面：
- `repost_fixed_links(bot, message)`：整段流程；沒有要轉的連結就什麼都不做、也不連網。

規則：
- 轉貼用回覆送出、不 @ 原貼者：大家看得出是誰的影片，程式也靠這個回覆關係找回原訊息（`chat_line`、插話），不另存。
- 轉貼長出影片、圖片或縮圖的預覽才壓原訊息的預覽；`PREVIEW_WAIT_SECONDS` 內沒長出來就刪掉轉貼、原預覽留著。
  只有文字的預覽不算；一則訊息有好幾個連結時，轉貼上有任何一個預覽就算。
- 壓別人的預覽要「管理訊息」權限；缺權限只記 warning，轉貼照樣留著。

例外與決策：
- 不加固定延遲：查過的轉貼，原預覽每次都壓成功、log 也沒有限流；出問題的是替代服務做不出那篇影片，那時原預覽
  已經被壓掉，群友什麼都看不到。改成等新的長出來才壓舊的，新的做不出來時至少還留著原預覽。
- 等預覽靠 Discord 抓完預覽後送來的訊息更新事件；時間到還沒等到就向 API 再讀一次那則（事件可能在開始等之前就到了）。
"""

from __future__ import annotations

import asyncio
import logging

import discord

from utils.link_fix import repost_text, select_fixed_links

logger = logging.getLogger(__name__)

#: 轉貼送出後最多等幾秒讓 Discord 長出預覽；Discord 抓替代服務通常一兩秒內就好
PREVIEW_WAIT_SECONDS = 10

_MEDIA_PARTS = ("video", "image", "thumbnail")


def _has_media(embed) -> bool:
    """discord.Embed 有沒有影片、圖片或縮圖。"""
    return any(getattr(getattr(embed, part, None), "url", None) for part in _MEDIA_PARTS)


def _has_media_data(embed: dict) -> bool:
    """訊息更新事件裡的原始 embed（dict）有沒有影片、圖片或縮圖。"""
    return any(isinstance(embed.get(part), dict) and embed[part].get("url") for part in _MEDIA_PARTS)


async def _wait_for_preview(bot, repost: discord.Message) -> bool:
    """等轉貼長出影片或圖片預覽；`PREVIEW_WAIT_SECONDS` 內沒有就回 False。"""
    if any(_has_media(e) for e in repost.embeds):
        return True

    def _updated(payload) -> bool:
        return payload.message_id == repost.id and any(
            _has_media_data(e) for e in (payload.data.get("embeds") or []) if isinstance(e, dict)
        )

    try:
        await bot.wait_for("raw_message_edit", check=_updated, timeout=PREVIEW_WAIT_SECONDS)
        return True
    except asyncio.TimeoutError:
        pass
    try:
        fresh = await repost.channel.fetch_message(repost.id)
    except discord.HTTPException as exc:
        logger.warning("讀不到剛送出的轉貼 %s，當成沒有預覽：%s", repost.id, exc)
        return False
    return any(_has_media(e) for e in fresh.embeds)


async def _suppress_original(message: discord.Message) -> None:
    try:
        await message.edit(suppress=True)
    except discord.Forbidden:
        logger.warning("壓制原訊息預覽失敗：缺少「管理訊息」權限")
    except discord.HTTPException as exc:
        logger.warning("壓制原訊息預覽失敗：%s", exc)


async def repost_fixed_links(bot, message: discord.Message) -> None:
    """訊息裡有 X 影片或 bilibili 影片連結就轉貼能播的版本；新預覽出現才壓原預覽，等不到就收回轉貼。"""
    fixed = await select_fixed_links(message.content or "")
    if not fixed:
        return
    try:
        repost = await message.reply(repost_text(fixed), mention_author=False)
    except discord.HTTPException as exc:
        logger.warning("轉貼替代網址失敗：%s", exc)
        return
    if await _wait_for_preview(bot, repost):
        await _suppress_original(message)
        return
    logger.warning(
        "轉貼 %s 等了 %d 秒沒長出預覽，收回轉貼、保留原訊息的預覽：%s",
        repost.id, PREVIEW_WAIT_SECONDS, ", ".join(f.url for f in fixed),
    )
    try:
        await repost.delete()
    except discord.HTTPException as exc:
        logger.warning("收回沒有預覽的轉貼 %s 失敗：%s", repost.id, exc)
