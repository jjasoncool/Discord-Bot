"""IT 文章監控（系統設備 / 硬體新知，bot 端發送）。

主題層命名為 it_article（來源可多個，目前來源為 HKEPC）。
打 scraper 的 /api/it_articles/* → 用 post_to_channel 發到 hardware_news_channel_id。
排版：單一 embed（標題 + 內文 + 圖 + 參考連結）；圖片暫存下載當附件，交給 Discord CDN。

防洗版：首次啟動以 ensure_seeded() 把目前 API 裡的文章全部標記已發，只發之後新增的。
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import aiohttp
import discord

from services.base_monitor import BaseContentMonitor
from utils.discord_content import post_to_channel

logger = logging.getLogger(__name__)

# state 的 content_type（主題層）
_CONTENT_TYPE = "it_article"
_SEED_FLAG_TYPE = "it_article_meta"
_SEED_FLAG_ID = "seeded"


class ItArticleMonitor(BaseContentMonitor):
    """IT 文章（系統設備 / 硬體新知）監控器。"""

    EMBED_DESC_MAX = 4000  # Discord embed description 上限 ~4096，留餘裕

    async def fetch_recent_it_articles(self, days: int = 3, limit: int = 50, tag: Optional[str] = None) -> List[Dict]:
        """從 scraper API 取最近的 IT 文章（舊→新，同日再依 hkepc_id 遞增穩定排序）。"""
        try:
            url = f"{self.scraper_api_url}/api/it_articles/recent"
            params = {"days": days, "limit": limit, "order": "asc"}
            if tag:
                params["tag"] = tag  # aiohttp 會自動 URL-encode 中文 tag
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=30) as resp:
                    if resp.status != 200:
                        logger.error("IT 文章 API 請求失敗，狀態碼: %s", resp.status)
                        return []
                    data = await resp.json()
                    if not data.get("success"):
                        logger.error("IT 文章 API 回應失敗: %s", data.get("message"))
                        return []
                    items = data.get("items", [])
                    items.sort(key=lambda x: (x.get("published_at") or "", x.get("hkepc_id", 0)))
                    return items
        except asyncio.TimeoutError:
            logger.error("IT 文章 API 請求逾時")
        except Exception as e:
            logger.error("取得 IT 文章時發生錯誤: %s", e)
        return []

    async def fetch_it_article_by_id(self, hkepc_id: int) -> Optional[Dict]:
        """依文章 id 取單篇（resend 用）。"""
        try:
            url = f"{self.scraper_api_url}/api/it_articles/{hkepc_id}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=15) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
                    return data.get("item") if data.get("success") else None
        except Exception as e:
            logger.error("依 id 取得 IT 文章 %s 失敗: %s", hkepc_id, e)
            return None

    def format_embed(self, item: Dict) -> discord.Embed:
        """單一 embed：標題（可點回原文）+ 內文 + 參考連結；圖片於發送時 set_image。"""
        title = (item.get("title") or "（無標題）")[:256]
        body = (item.get("content") or item.get("introduction") or "").strip()

        ref = item.get("reference_url")
        ref_line = f"\n\n🔗 來源：{ref}" if ref else ""
        # 預留參考連結的長度，內文截斷
        body_budget = self.EMBED_DESC_MAX - len(ref_line)
        if len(body) > body_budget:
            body = body[:body_budget - 1].rstrip() + "…"
        description = (body + ref_line)[:4096]

        embed = discord.Embed(
            title=title,
            description=description,
            url=item.get("url") or None,
            color=discord.Color.blue(),
        )
        footer_parts = ["IT快訊"]
        if item.get("tags"):
            footer_parts.append(item["tags"])
        if item.get("published_at"):
            footer_parts.append(item["published_at"][:10])
        embed.set_footer(text=" · ".join(footer_parts))
        return embed

    async def send_to_channel(self, channel_id: int, item: Dict, mark_sent: bool = True) -> bool:
        """發一篇 IT 文章到指定頻道（走 post_to_channel：文字→訊息、論壇→thread）。

        mark_sent=False 用於測試發送（不影響正式去重狀態、可重複發）。
        """
        try:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                logger.error("找不到頻道 ID: %s", channel_id)
                return False

            embed = self.format_embed(item)

            # 下載圖片成暫存附件（不存伺服器），交給 Discord CDN
            files: List[discord.File] = []
            images = item.get("images") or []
            if images:
                async with aiohttp.ClientSession() as session:
                    for idx, img_url in enumerate(images, start=1):
                        result = await self._download_image_as_file(img_url, session, max_retries=2)
                        if not result:
                            logger.warning("IT 文章圖片下載失敗，略過: %s", img_url)
                            continue
                        image_data, detected_ext = result
                        filename = self._get_image_filename_with_ext(img_url, idx, detected_ext)
                        files.append(discord.File(image_data, filename=filename))
                if files:
                    # 第一張內嵌進 embed（單一 embed 內呈現），其餘由 post_to_channel 後送
                    embed.set_image(url=f"attachment://{files[0].filename}")

            await post_to_channel(
                channel,
                embed=embed,
                files=files or None,
                thread_title=item.get("title"),
                follow_up_label="**附圖（後續補送）**",
            )
            if mark_sent:
                await self.mark_content_as_sent(_CONTENT_TYPE, item["hkepc_id"])
            logger.info("成功發送 IT 文章 %s 到頻道 %s (mark_sent=%s)", item.get("hkepc_id"), channel_id, mark_sent)
            return True
        except Exception as e:
            logger.error("發送 IT 文章到頻道失敗: %s", e, exc_info=True)
            return False

    @staticmethod
    def _parse_published(value) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return None

    async def ensure_seeded(self) -> int:
        """首次啟動（只跑一次）：3 天內的文章保留（之後由 check_and_send 實際發出），
        超過 3 天的舊文標記為已發（不發），避免一次倒整個 backlog。

        以 state 旗標保證一輩子只 seed 一次（重啟不會重 seed）。
        回傳這次「標記為已發」的舊文篇數（已 seed 過則回 -1）。
        """
        if await self.is_content_sent(_SEED_FLAG_TYPE, _SEED_FLAG_ID):
            return -1
        items = await self.fetch_recent_it_articles(days=60, limit=500)
        cutoff = datetime.now() - timedelta(days=3)
        seeded = 0
        for it in items:
            pub = self._parse_published(it.get("published_at"))
            # 只把「超過 3 天」的舊文標記已發；3 天內的留著未發 → check_and_send 會發
            if pub is not None and pub < cutoff:
                await self.mark_content_as_sent(_CONTENT_TYPE, it["hkepc_id"])
                seeded += 1
        await self.mark_content_as_sent(_SEED_FLAG_TYPE, _SEED_FLAG_ID)
        logger.info("IT 文章首次 seed 完成：%s 篇舊文(>3天)標記已發，3 天內的將實際發送", seeded)
        return seeded

    async def check_and_send_new(self, channel_ids: List[int]):
        """檢查並發送新文章（舊→新依序）。"""
        try:
            items = await self.fetch_recent_it_articles(days=3, limit=50)
            if not items:
                return
            new_items = [it for it in items if not await self.is_content_sent(_CONTENT_TYPE, it["hkepc_id"])]
            if not new_items:
                return
            logger.info("[IT 文章排程] 找到 %s 篇新文章", len(new_items))
            for it in new_items:
                for channel_id in channel_ids:
                    if await self.send_to_channel(channel_id, it):
                        await asyncio.sleep(1)  # 避免頻率限制
        except Exception as e:
            logger.error("[IT 文章排程] 檢查新文章時發生錯誤: %s", e, exc_info=True)

    async def start_monitoring(self, channel_ids: List[int], check_interval: int = 600):
        """開始監控（首次先 seed 防洗版，再進迴圈）。"""
        seeded = await self.ensure_seeded()
        if seeded >= 0:
            logger.info("[IT 文章排程] 首次啟動，已 seed %s 篇為已發（不洗版）", seeded)
        logger.info("[IT 文章排程] 開始監控，間隔 %s 秒", check_interval)
        while True:
            try:
                await self.check_and_send_new(channel_ids)
                await asyncio.sleep(check_interval)
            except asyncio.CancelledError:
                logger.info("[IT 文章排程] 監控已停止")
                raise
            except Exception as e:
                logger.error("[IT 文章排程] 監控循環發生錯誤: %s", e)
                await asyncio.sleep(60)
