"""
Facebook 貼文 → Discord 頻道 relay 服務

從 Scraper API 取得 FB 貼文，格式化為 Discord embed 並發送。
"""
import asyncio
import aiohttp
import logging
import re
import discord
from datetime import datetime
from typing import List, Dict, Optional
from urllib.parse import urlparse, urlunparse

from utils.logger_config import get_discord_bot_logger
from .base_monitor import BaseContentMonitor

logger = get_discord_bot_logger()


class FBMonitor(BaseContentMonitor):
    """Facebook 貼文監控類別"""

    def __init__(self, bot, scraper_api_url: str = "http://scraper:8000"):
        super().__init__(bot, scraper_api_url)

    # ── FB URL 清洗 ──

    @staticmethod
    def _sanitize_fb_hashtag_url(url: str) -> str:
        """僅在 Discord 顯示前清洗 Facebook hashtag URL，保留原始資料不變。"""
        if not url:
            return ""
        try:
            parsed = urlparse(url.strip())
        except Exception:
            return url

        if "facebook.com" not in parsed.netloc or "/hashtag/" not in parsed.path:
            return url

        clean_path = parsed.path.rstrip("/")
        return urlunparse((parsed.scheme or "https", "www.facebook.com", clean_path, "", "", ""))

    def _sanitize_fb_text_md_for_discord(self, text_md: str) -> str:
        """清洗 Discord 顯示用的 FB hashtag markdown link，不改動資料來源。"""
        if not text_md:
            return ""

        def _replace(match: re.Match) -> str:
            label = match.group(1)
            url = match.group(2)
            sanitized_url = self._sanitize_fb_hashtag_url(url)
            return f"[{label}]({sanitized_url})"

        pattern = re.compile(r"\[(#[^\]]+)\]\((https?://[^)]+)\)")
        return pattern.sub(_replace, text_md)

    # ── API 呼叫 ──

    async def fetch_recent_fb_posts(self, days: int = 7) -> List[Dict]:
        """從 scraper API 取得最近的 FB 貼文"""
        return await self.fetch_content_from_api("/api/fb_posts/recent", {"days": days, "limit": 20})

    async def fetch_fb_post_by_id(self, fb_post_id: int) -> Optional[Dict]:
        """從 scraper API 根據資料庫 ID 取得單篇 FB 貼文。"""
        try:
            url = f"{self.scraper_api_url}/api/fb_posts/{fb_post_id}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=15) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get('success') and data.get('post'):
                            logger.info(f"成功根據資料庫 ID {fb_post_id} 取得 FB 貼文")
                            return data['post']

                        logger.warning(
                            "FB API 回應成功但內容無效（id=%s）: success=%s has_post=%s",
                            fb_post_id,
                            data.get('success'),
                            bool(data.get('post')),
                        )
                        return None

                    try:
                        error_data = await response.json()
                    except Exception:
                        error_data = {}

                    logger.error(
                        "FB API 請求失敗（id=%s），狀態碼: %s, 細節: %s",
                        fb_post_id,
                        response.status,
                        error_data.get('detail') or error_data.get('message')
                    )
                    return None
        except asyncio.TimeoutError:
            logger.error(f"根據資料庫 ID {fb_post_id} 取得 FB 貼文逾時")
            return None
        except Exception as e:
            logger.error(f"根據資料庫 ID {fb_post_id} 取得 FB 貼文時發生錯誤: {e}")
            return None

    # ── 格式化 ──

    def format_fb_embed(self, fb_post: Dict):
        """格式化 FB 貼文為 Discord Embed"""
        # 優先使用 text_md（Discord Markdown 格式），如果沒有則使用 text
        description_text = fb_post.get('text_md') or fb_post.get('text', '')
        if fb_post.get('text_md'):
            description_text = self._sanitize_fb_text_md_for_discord(description_text)
        description = description_text[:2000] if description_text else ''

        # 優先使用 url 欄位，如果 url 是空的則使用 pfbid_url
        embed_url = fb_post.get('url') or fb_post.get('pfbid_url')

        # 優先使用 timestamp（貼文發佈時間），如果沒有則使用 created_at（資料庫記錄時間）
        timestamp_str = fb_post.get('timestamp') or fb_post.get('created_at')
        timestamp = None
        if timestamp_str:
            try:
                if timestamp_str.endswith('Z'):
                    timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                else:
                    timestamp = datetime.fromisoformat(timestamp_str)
            except ValueError as e:
                logger.warning(f"無法解析 FB 貼文時間戳 '{timestamp_str}': {e}")
                timestamp = None

        embed = discord.Embed(
            title="Facebook 貼文",
            description=description,
            color=0x1877F2,  # FB 藍色
            timestamp=timestamp,
            url=embed_url
        )

        embed.add_field(name="📘 來源", value="Facebook", inline=True)

        images = fb_post.get('images', [])
        if images:
            logger.info(f"FB 貼文 {fb_post.get('id', 'unknown')} 設定圖片: {images[0]}")
            embed.set_image(url=images[0])
        else:
            logger.info(f"FB 貼文 {fb_post.get('id', 'unknown')} 沒有圖片")

        fb_id = fb_post.get('id', '?')
        embed.set_footer(text=f"#{fb_id} 鳴潮官方 Facebook")
        return embed

    # ── 發送 ──

    async def send_fb_post_to_channel(self, channel_id: int, fb_post: Dict) -> bool:
        """發送 FB 貼文到指定頻道"""
        try:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                logger.error(f"找不到頻道 ID: {channel_id}")
                return False

            logger.info(f"[RESEND_ROUTE] 進入 send_fb_post_to_channel: fb_id={fb_post.get('id')}, channel_id={channel_id}")

            embed = self.format_fb_embed(fb_post)

            # FB 分支：主文 + 第1張圖片（附件）同次發送，再發其餘圖片（正序）
            images = fb_post.get('images', [])

            # 1) 先送主文 + 第1張圖片（附件）
            embed.set_image(url=None)  # 禁止以 URL 連結方式顯示圖片
            if images:
                first_image_url = images[0]
                async with aiohttp.ClientSession() as session:
                    logger.info(f"[FB_FLOW] 開始下載第 1 張圖片（主圖）: {first_image_url}")
                    main_result = await self._download_image_as_file(first_image_url, session, max_retries=2)
                    if main_result:
                        image_data, detected_ext = main_result
                        main_filename = self._get_image_filename_with_ext(first_image_url, 1, detected_ext)
                        main_file = discord.File(image_data, filename=main_filename)
                        embed.set_image(url=f"attachment://{main_filename}")
                        await channel.send(embed=embed, files=[main_file])
                        logger.info(f"[FB_FLOW] 📤 主文+第1張圖片發送完成: {main_filename}")
                    else:
                        await channel.send(embed=embed)
                        logger.warning(f"[FB_FLOW] ❌ 第 1 張主圖下載失敗，僅發送主文: {first_image_url}")
            else:
                await channel.send(embed=embed)
                logger.info("[FB_FLOW] 📤 發送 FB 主文完成（無圖片）")

            if images:
                logger.info(f"[FB_FLOW] 總共有 {len(images)} 張圖片，將以正序分段發送")

                # 2) 再送其餘圖片（第 2 張起，正序；每批最多 10）
                rest_images = images[1:]
                if rest_images:
                    chunk_size = 10
                    image_chunks = [rest_images[i:i + chunk_size] for i in range(0, len(rest_images), chunk_size)]

                    for i, chunk in enumerate(image_chunks):
                        logger.info(f"[FB_FLOW] 準備發送第 {i+1} 批其餘圖片，共 {len(chunk)} 張")
                        files = []
                        async with aiohttp.ClientSession() as session:
                            for j, image_url in enumerate(chunk):
                                original_index = sum(len(c) for c in image_chunks[:i]) + j + 2
                                logger.info(f"[FB_FLOW] 開始下載第 {original_index} 張圖片: {image_url}")

                                download_result = await self._download_image_as_file(image_url, session, max_retries=2)
                                if not download_result:
                                    logger.warning(f"[FB_FLOW] ❌ 跳過無法下載圖片: {image_url}")
                                    continue

                                image_data, detected_ext = download_result
                                filename = self._get_image_filename_with_ext(image_url, original_index, detected_ext)
                                files.append(discord.File(image_data, filename=filename))

                        if files:
                            await asyncio.sleep(0.5)
                            await channel.send(files=files)
                            logger.info(f"[FB_FLOW] ✅ 第 {i+1} 批已發送 {len(files)} 張")
                        else:
                            logger.warning(f"[FB_FLOW] 第 {i+1} 批沒有可發送圖片")
            else:
                logger.info("[FB_FLOW] 無圖片可發送")

            await self.mark_content_as_sent('fbpost', fb_post['id'])
            logger.info(f"成功發送 FB 貼文 {fb_post['id']} 到頻道 {channel_id}")
            return True

        except Exception as e:
            logger.error(f"發送 FB 貼文到頻道失敗: {e}")
            return False

    # ── 排程 ──

    async def check_and_send_fb_posts(self, channel_ids: List[int]):
        """檢查並發送新的 FB 貼文"""
        try:
            fb_posts = await self.fetch_recent_fb_posts(days=7)

            if not fb_posts:
                logger.debug("[FB] 沒有找到新 FB 貼文")
                return

            new_posts = []
            for post in fb_posts:
                if not await self.is_content_sent('fbpost', post['id']):
                    new_posts.append(post)

            if not new_posts:
                logger.debug("[FB] 沒有新的未發送 FB 貼文")
                return

            logger.info(f"[FB] 找到 {len(new_posts)} 篇新 FB 貼文")

            for post in new_posts:
                for channel_id in channel_ids:
                    success = await self.send_fb_post_to_channel(channel_id, post)
                    if success:
                        logger.info(f"[FB] 成功發送 FB 貼文 {post['id']} 到頻道 {channel_id}")
                        await asyncio.sleep(2)

        except Exception as e:
            logger.error(f"[FB] 檢查 FB 貼文時發生錯誤: {e}")

    async def start_fb_monitoring(self, channel_ids: List[int], check_interval: int = 600):
        """開始監控 FB 貼文（每10分鐘檢查一次）"""
        logger.info(f"[FB]開始監控 FB 貼文，檢查間隔: {check_interval} 秒")

        while True:
            try:
                await self.check_and_send_fb_posts(channel_ids)
                await asyncio.sleep(check_interval)
            except Exception as e:
                logger.error(f"[FB]監控循環發生錯誤: {e}")
                await asyncio.sleep(300)
