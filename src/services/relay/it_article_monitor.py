"""IT 文章監控（系統設備 / 硬體新知，bot 端發送）。

主題層命名為 it_article（來源可多個，目前來源為 HKEPC）。
打 scraper 的 /api/it_articles/* → 用 post_to_channel 發到 hardware_news_channel_id。
排版：單一 embed（標題 + 內文 + 圖 + 參考連結）；圖片暫存下載當附件，交給 Discord CDN。

防洗版：首次啟動以 ensure_seeded() 把目前 API 裡的文章全部標記已發，只發之後新增的。

內頁晚到：HKEPC 內頁偶爾被擋（403），當下只有列表頁的摘要，照樣先發；
之後 scraper 補到內文，由 refresh_intro_only_messages() 把那則訊息就地更新成完整內文。
"""
import asyncio
import io
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import aiohttp
import discord

from services.relay.base_monitor import BaseContentMonitor
from utils.discord_content import post_to_channel

logger = logging.getLogger(__name__)

# state 的 content_type（主題層）
_CONTENT_TYPE = "it_article"
_SEED_FLAG_TYPE = "it_article_meta"
_SEED_FLAG_ID = "seeded"


class ItArticleMonitor(BaseContentMonitor):
    """IT 文章（系統設備 / 硬體新知）監控器。"""

    EMBED_DESC_MAX = 4000  # Discord embed description 上限 ~4096，留餘裕
    SEND_INTERVAL = 2.0    # 每篇之間的固定間隔（秒），避免 rate limit
    SEND_MAX_ATTEMPTS = 3  # 單篇發送的最大嘗試次數（含首次）
    SEND_RETRY_BACKOFF = 3.0  # 重試退避基數（秒），第 n 次等 backoff*n
    # 回頭補內文時往前看多遠：跟 check_and_send_new 取的 API 範圍（3 天）一致，
    # 再舊的文章 API 也不會回，內文不會再來。
    REFRESH_LOOKBACK_DAYS = 3
    REFRESH_HISTORY_LIMIT = 200  # 3 天約 30 篇＋附圖補送訊息，200 則足夠

    async def fetch_recent_it_articles(self, days: int = 3, limit: int = 50, tag: Optional[str] = None) -> List[Dict]:
        """從 scraper API 取最近的 IT 文章（舊→新，同日再依 hkepc_id 遞增穩定排序）。"""
        try:
            url = f"{self.scraper_api_url}/api/it_articles/recent"
            # order=desc 取「最新」limit 篇（避免文章數 > limit 時，新文被截掉）；
            # 下面再用 Python 排成 asc，讓發送維持舊→新的時序。
            params = {"days": days, "limit": limit, "order": "desc"}
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

        Discord 5xx（暫時性伺服器錯誤）會自動重試 SEND_MAX_ATTEMPTS 次；
        仍失敗則保留「未發」狀態，由下次 notify 自動補發。
        mark_sent=False 用於測試發送（不影響正式去重狀態、可重複發）。
        """
        channel = self.bot.get_channel(channel_id)
        if not channel:
            logger.error("找不到頻道 ID: %s", channel_id)
            return False

        embed = self.format_embed(item)

        # 圖片先下載成「原始 bytes」（不存伺服器）；重試時用同一份 bytes 重建 discord.File，
        # 避免 BytesIO 送過一次就被消耗。
        image_blobs: List[Tuple[bytes, str]] = []
        images = item.get("images") or []
        if images:
            async with aiohttp.ClientSession() as session:
                for idx, img_url in enumerate(images, start=1):
                    result = await self._download_image_as_file(img_url, session, max_retries=2)
                    if not result:
                        logger.warning("IT 文章圖片下載失敗，略過: %s", img_url)
                        continue
                    image_data, detected_ext = result
                    raw = image_data.getvalue() if hasattr(image_data, "getvalue") else image_data
                    image_blobs.append((raw, self._get_image_filename_with_ext(img_url, idx, detected_ext)))
            if image_blobs:
                # 第一張內嵌進 embed（單一 embed 內呈現），其餘由 post_to_channel 後送
                embed.set_image(url=f"attachment://{image_blobs[0][1]}")

        for attempt in range(1, self.SEND_MAX_ATTEMPTS + 1):
            try:
                files = [discord.File(io.BytesIO(raw), filename=fn) for raw, fn in image_blobs]
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
            except discord.DiscordServerError as e:
                # Discord 5xx 暫時性錯誤 → 退避後重試
                if attempt < self.SEND_MAX_ATTEMPTS:
                    wait = self.SEND_RETRY_BACKOFF * attempt
                    logger.warning("發送 IT 文章 %s 撞 Discord 5xx(第 %s 次)，%.0f 秒後重試: %s",
                                   item.get("hkepc_id"), attempt, wait, e)
                    await asyncio.sleep(wait)
                else:
                    logger.error("發送 IT 文章 %s 連 %s 次撞 5xx，保留未發待下次補發: %s",
                                 item.get("hkepc_id"), self.SEND_MAX_ATTEMPTS, e)
                    return False
            except Exception as e:
                logger.error("發送 IT 文章 %s 到頻道失敗（非 5xx，不重試）: %s", item.get("hkepc_id"), e, exc_info=True)
                return False
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

    @staticmethod
    def _article_key(url: Optional[str]) -> str:
        # 用網址裡的文章編號比對：HKEPC 網址帶標題（可能是 %E5... 編碼、也可能是中文），
        # 站方改標題時 scraper 會跟著更新 url，整串網址比就對不上舊訊息。抓不到編號才退回整串網址。
        text = (url or "").strip()
        m = re.search(r"hkepc\.com/(\d+)(?:/|$)", text)
        return m.group(1) if m else text

    async def refresh_intro_only_messages(self, channel_ids: List[int], items: List[Dict]) -> int:
        """把先前「只帶摘要」發出的訊息，就地更新成完整內文。回傳更新了幾則。

        為什麼掃頻道比對、不另存訊息 id：IT 頻道綁定限定文字頻道，讀一次最近 3 天的訊息就夠
        （每次通知 1～2 次 API），不必在 sent_articles.db 加表，已經發出去的舊訊息也能一併補上。
        認定「只帶摘要」：訊息 embed 的描述，等於這篇在「沒有內文」時會排出的描述。
        排版以後若改了，舊訊息就對不上而不動——寧可漏補，也不誤改別的訊息。
        """
        by_key = {
            self._article_key(it.get("url")): it
            for it in items
            if (it.get("content") or "").strip() and it.get("url")
        }
        if not by_key or self.bot.user is None:
            return 0

        updated = 0
        after = datetime.now(timezone.utc) - timedelta(days=self.REFRESH_LOOKBACK_DAYS)
        for channel_id in channel_ids:
            channel = self.bot.get_channel(channel_id)
            if channel is None or not hasattr(channel, "history"):
                continue
            try:
                # 從最新的讀起：給了 after 時 discord.py 預設由舊到新，limit 會先吃掉最舊的，
                # 剛發出、最需要補的那幾則反而讀不到
                async for msg in channel.history(limit=self.REFRESH_HISTORY_LIMIT, after=after, oldest_first=False):
                    if msg.author.id != self.bot.user.id or not msg.embeds:
                        continue
                    old = msg.embeds[0]
                    item = by_key.get(self._article_key(old.url))
                    if item is None:
                        continue
                    old_desc = (old.description or "").strip()
                    intro_desc = (self.format_embed({**item, "content": None, "reference_url": None}).description or "").strip()
                    if old_desc != intro_desc:
                        continue  # 已經是完整內文，或不是這個版本排出來的訊息
                    new_embed = self.format_embed(item)
                    if (new_embed.description or "").strip() == old_desc:
                        continue
                    try:
                        await self._edit_with_full_content(msg, old, new_embed, item)
                        updated += 1
                        logger.info("已把 IT 文章 %s 的摘要訊息就地更新成完整內文（訊息 %s）", item.get("hkepc_id"), msg.id)
                    except Exception as e:
                        logger.warning("更新 IT 文章 %s 的訊息 %s 失敗（下次通知再試）: %s", item.get("hkepc_id"), msg.id, e)
                    await asyncio.sleep(self.SEND_INTERVAL)
            except Exception as e:
                logger.warning("讀取 IT 頻道 %s 的近期訊息失敗，本次不補內文: %s", channel_id, e)
        return updated

    async def _edit_with_full_content(self, msg, old_embed, new_embed: discord.Embed, item: Dict) -> None:
        """換成完整內文；原本有圖就沿用，沒有而內文帶圖時補上第一張（其餘圖片不另發，免得插到後面的訊息之間）。

        帶圖的那次編輯若失敗（多半是新圖太大），退回只換文字：內文比圖重要，
        而且不退的話，之後每次通知都會重新下載、重試、再失敗。
        """
        old_image = getattr(getattr(old_embed, "image", None), "url", None)
        if old_image:
            att = self._matching_attachment(msg, old_image)
            if att is None:
                new_embed.set_image(url=old_image)
                await msg.edit(embed=new_embed)
                return
            # 讀回來的圖片網址帶簽章、會過期；原圖是這則訊息的附件時，改用 attachment:// 引用它
            new_embed.set_image(url=f"attachment://{att.filename}")
            attachments = list(msg.attachments)
        else:
            file = await self._first_image_file(item) if item.get("images") else None
            if file is None:
                await msg.edit(embed=new_embed)
                return
            new_embed.set_image(url=f"attachment://{file.filename}")
            attachments = [*msg.attachments, file]  # 列出的舊附件會保留，沒列的會被刪掉
        try:
            await msg.edit(embed=new_embed, attachments=attachments)
        except discord.HTTPException as e:
            logger.warning("IT 文章 %s 帶圖更新失敗，改成只更新文字: %s", item.get("hkepc_id"), e)
            new_embed.set_image(url=old_image)  # 原本沒圖時是 None＝拿掉圖
            await msg.edit(embed=new_embed)

    @staticmethod
    def _matching_attachment(msg, image_url: str):
        path = image_url.split("?", 1)[0]
        for att in msg.attachments:
            if path.endswith("/" + att.filename):
                return att
        return None

    async def _first_image_file(self, item: Dict) -> Optional[discord.File]:
        img_url = item["images"][0]
        async with aiohttp.ClientSession() as session:
            result = await self._download_image_as_file(img_url, session, max_retries=2)
        if not result:
            logger.warning("IT 文章補內文時圖片下載失敗，只更新文字: %s", img_url)
            return None
        image_data, detected_ext = result
        raw = image_data.getvalue() if hasattr(image_data, "getvalue") else image_data
        filename = self._get_image_filename_with_ext(img_url, 1, detected_ext)
        return discord.File(io.BytesIO(raw), filename=filename)

    async def check_and_send_new(self, channel_ids: List[int]):
        """檢查並發送新文章（舊→新依序），再把先前只帶摘要的訊息補成完整內文。"""
        try:
            items = await self.fetch_recent_it_articles(days=3, limit=50)
            if not items:
                return
            new_items = [it for it in items if not await self.is_content_sent(_CONTENT_TYPE, it["hkepc_id"])]
            if new_items:
                logger.info("[IT 文章排程] 找到 %s 篇待發文章", len(new_items))
                for it in new_items:
                    for channel_id in channel_ids:
                        await self.send_to_channel(channel_id, it)
                    # 每篇之間固定間隔（不論成敗），避免 rate limit
                    await asyncio.sleep(self.SEND_INTERVAL)
            # 新文先發：補內文要讀頻道、下載圖片、逐則編輯，放前面會拖慢新文
            await self.refresh_intro_only_messages(channel_ids, items)
        except Exception as e:
            logger.error("[IT 文章排程] 檢查新文章時發生錯誤: %s", e, exc_info=True)
