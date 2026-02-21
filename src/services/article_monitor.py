"""
官方文章更新服務
定期檢查 scraper API 取得新文章並發送到 Discord 頻道
"""
import asyncio
import aiohttp
import json
import logging
import re
import io
import os
import random
import tempfile
import discord
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
from utils.logger_config import get_discord_bot_logger, get_article_monitor_logger

from .base_monitor import BaseContentMonitor

# 設置日誌器（使用統一配置）
logger = get_discord_bot_logger()
article_logger = get_article_monitor_logger()

class ArticleMonitor(BaseContentMonitor):
    """官方文章更新類別"""

    # 網站配置
    BASE_URL = "https://hw-media-cdn-mingchao.kurogame.com"
    WEBSITE_NAME = "鳴潮官方網站"

    def __init__(self, bot, scraper_api_url: str = "http://scraper:8000"):
        super().__init__(bot, scraper_api_url)
        logger.info(f"初始化官方文章更新器，目標網站: {self.WEBSITE_NAME}")

    def _build_request_headers(self) -> Dict[str, str]:
        """建立下載圖片用的請求標頭（優先使用 fake-useragent，否則使用內建隨機 UA 池）"""
        # 注意：discord_bot 容器目前 requirements 未包含 fake-useragent，需容錯 fallback
        user_agent = None

        try:
            # 若未安裝 fake-useragent 會觸發 ImportError，交由 fallback 處理
            from fake_useragent import UserAgent  # type: ignore
            user_agent = UserAgent().random
        except Exception:
            fallback_user_agents = [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
            ]
            user_agent = random.choice(fallback_user_agents)

        return {
            "User-Agent": user_agent,
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }

    # 已發送文章追蹤現在由 BaseContentMonitor 處理

    async def fetch_recent_articles(self, days: int = 3) -> List[Dict]:
        """從 scraper API 取得最近的文章"""
        try:
            # 使用專為 Discord 設計的 API 端點，指定按時間升序排序（舊到新）
            url = f"{self.scraper_api_url}/api/articles/discord"
            params = {"days": days, "limit": 50, "order": "asc"}

            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=30) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get('success'):
                            logger.debug(f"成功取得 {len(data['articles'])} 篇文章（已按時間排序：舊→新）")
                            return data['articles']
                        else:
                            logger.error(f"API 回應失敗: {data.get('message')}")
                    else:
                        logger.error(f"API 請求失敗，狀態碼: {response.status}")

        except asyncio.TimeoutError:
            logger.error("API 請求逾時")
        except Exception as e:
            logger.error(f"取得文章時發生錯誤: {e}")

        return []

    async def fetch_article_by_id(self, article_id: int) -> Optional[Dict]:
        """從 scraper API 根據 ID 取得單篇文章"""
        try:
            url = f"{self.scraper_api_url}/api/articles/{article_id}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=15) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get('success') and data.get('article'):
                            logger.info(f"成功根據 ID {article_id} 取得文章")
                            return data['article']
                        else:
                            logger.error(f"API 回應錯誤（ID: {article_id}）: {data.get('message', '未知錯誤')}")
                    else:
                        # 嘗試解析錯誤回應
                        try:
                            error_data = await response.json()
                            logger.error(f"API 請求失敗（ID: {article_id}），狀態碼: {response.status}, 細節: {error_data.get('detail')}")
                        except Exception:
                             logger.error(f"API 請求失敗（ID: {article_id}），狀態碼: {response.status}")
        except Exception as e:
            logger.error(f"根據 ID {article_id} 取得文章時發生錯誤: {e}")
        return None

    def _parse_html_content(self, html_content: str) -> tuple[str, List[str]]:
        """
        解析 HTML 內容，轉換為 Discord 支援的 Markdown 格式（使用 html2text）

        Returns:
            tuple: (純文字內容, 圖片URL列表)
        """
        import html2text
        if not html_content:
            logger.debug("HTML 內容為空，跳過解析")
            return "", []

        logger.debug(f"開始解析 HTML 內容，長度: {len(html_content)} 字符")

        # 使用 BeautifulSoup 提取圖片
        images = []
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            img_tags = soup.find_all('img')
            logger.debug(f"找到 {len(img_tags)} 個 img 標籤")
            for i, img in enumerate(img_tags):
                src = img.get('src')
                if src:
                    if src.startswith('//'):
                        src = 'https:' + src
                    elif src.startswith('/'):
                        src = self.BASE_URL + src
                    elif not src.startswith('http'):
                        src = f"{self.BASE_URL}/" + src.lstrip('/')
                    images.append(src)
            logger.debug(f"最終提取到 {len(images)} 張圖片: {images}")
        except Exception as e:
            logger.error(f"BeautifulSoup 解析失敗: {e}")

        # 使用 html2text 轉換 HTML 到 Markdown
        try:
            h = html2text.HTML2Text()
            h.body_width = 0  # 不自動換行
            h.ignore_images = True  # 圖片已經另外處理
            h.ignore_emphasis = False  # 保留粗體斜體
            h.ignore_links = False  # 保留連結
            h.ignore_tables = False
            h.ignore_anchors = False
            h.single_line_break = False  # 保持原本的換行
            markdown_text = h.handle(html_content)
            logger.info(f"html2text 轉換成功，輸出長度: {len(markdown_text)} 字符")
            return markdown_text.strip(), images
        except Exception as e:
            logger.error(f"html2text 轉換失敗，僅回傳純文字: {e}")
            # 最後備用方案：只取純文字
            try:
                soup = BeautifulSoup(html_content, 'html.parser')
                text = soup.get_text(separator='\n', strip=False)
                return text.strip(), images
            except:
                return html_content, images

    def format_article_embed(self, article: Dict) -> dict:
        """格式化文章為 Discord Embed"""
        import discord

        article_id = article.get('article_id', 'unknown')
        article_title = article.get('article_title', '無標題')

        logger.info(f"開始格式化文章 Embed: ID={article_id}, 標題='{article_title}'")

        # 獲取並解析文章內容
        content = article.get('article_content_full') or article.get('article_content', '')
        description = article.get('article_desc', '')

        logger.debug(f"文章內容長度: {len(content)} 字符")
        logger.debug(f"文章描述長度: {len(description)} 字符")

        # 解析 HTML 內容
        logger.debug("開始解析文章內容...")
        parsed_content, content_images = self._parse_html_content(content)
        logger.debug("開始解析文章描述...")
        parsed_description, desc_images = self._parse_html_content(description)

        # 合併所有圖片
        all_images = content_images + desc_images

        # 選擇要顯示的描述
        display_description = ""
        if parsed_description:
            display_description = parsed_description
        elif parsed_content:
            # 如果沒有專門的描述，使用內容的前300字
            display_description = parsed_content[:300] + "..." if len(parsed_content) > 300 else parsed_content

        # 限制描述長度（Discord Embed 描述限制 4096 字符）
        if len(display_description) > 4000:
            display_description = display_description[:3997] + "..."

        # 創建 Embed
        # 優先使用 start_time 作為時間戳，如果沒有則使用 create_time
        timestamp = None
        time_str = article.get('start_time') or article.get('create_time')
        if time_str:
            try:
                # 處理各種時間格式
                if 'T' in time_str:
                    # ISO 格式：2025-06-25T17:04:19 或 2025-06-25T17:04:19Z
                    timestamp = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
                else:
                    # 簡單格式：2025-06-25 17:04:19
                    timestamp = datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S')
            except ValueError as e:
                logger.warning(f"無法解析時間格式 '{time_str}': {e}")
                timestamp = None

        embed = discord.Embed(
            title=article['article_title'][:256] if article.get('article_title') else "無標題",  # 標題限制 256 字符
            description=display_description,
            color=0x00ff00,
            timestamp=timestamp
        )

        # 暫時隱藏文章 ID
        # embed.add_field(name="📄 文章 ID", value=article['article_id'], inline=True)

        # 添加文章類型
        if article.get('article_type_name'):
            embed.add_field(name="📂 類型", value=article['article_type_name'], inline=True)
        elif article.get('article_type'):
            embed.add_field(name="📂 類型 ID", value=article['article_type'], inline=True)

        # 暫時隱藏遊戲 ID
        # if article.get('game_id'):
        #     embed.add_field(name="🎮 遊戲 ID", value=article['game_id'], inline=True)

        # 如果有解析出的完整內容且不太長，添加內容預覽
        if parsed_content and len(parsed_content) <= 1000 and parsed_content != display_description:
            embed.add_field(
                name="📝 內容預覽",
                value=parsed_content[:1000] + ("..." if len(parsed_content) > 1000 else ""),
                inline=False
            )

        # 處理圖片顯示
        logger.info(f"文章 {article.get('article_id', 'unknown')} 圖片處理開始")
        logger.info(f"  內容圖片數量: {len(content_images)}")
        logger.info(f"  描述圖片數量: {len(desc_images)}")
        logger.info(f"  總圖片數量: {len(all_images)}")

        if content_images:
            logger.debug(f"  內容圖片列表: {content_images}")
        if desc_images:
            logger.debug(f"  描述圖片列表: {desc_images}")

        # 優先使用指定的封面圖片
        main_image_url = article.get('article_cover') or article.get('content_cover') or article.get('suggest_cover')

        if main_image_url:
            logger.info(f"  使用指定封面圖片: {main_image_url}")
            embed.set_image(url=main_image_url)
        elif all_images:
            # 如果沒有指定封面但內容中有圖片，使用第一張圖片
            logger.info(f"  使用第一張內容圖片作為主圖: {all_images[0]}")
            embed.set_image(url=all_images[0])
        else:
            logger.info("  沒有可用的圖片")

        # 如果有超過一張圖片，記錄但不在 embed 中顯示連結（將作為附件發送）
        if len(all_images) > 1:
            logger.info(f"  圖片數量 {len(all_images)} > 1，其他圖片將作為附件發送")
            logger.info(f"  其他圖片列表 (第2-{len(all_images)}張): {all_images[1:]}")
        else:
            logger.info(f"  圖片數量 {len(all_images)} ≤ 1，無需附件")

        # 添加時間戳和來源
        footer_text = ""
        # 優先使用 start_time（發佈時間），如果沒有則使用 create_time（建立時間）
        display_time = article.get('start_time') or article.get('create_time')
        if display_time:
            time_label = "發佈時間" if article.get('start_time') else "建立時間"
            footer_text = f"{time_label}: {display_time}"

        if footer_text:
            footer_text += f" • {self.WEBSITE_NAME}"
        else:
            footer_text = self.WEBSITE_NAME

        embed.set_footer(text=footer_text)

        return embed

    async def send_article_to_channel(self, channel_id: int, article: Dict):
        """發送文章到指定頻道（支援多圖片附件，並在超過限制時分批發送）"""
        import discord

        try:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                logger.error(f"找不到頻道 ID: {channel_id}")
                return False

            logger.info(f"[RESEND_ROUTE] 進入 send_article_to_channel: article_id={article.get('article_id')}, channel_id={channel_id}")

            embed = self.format_article_embed(article)

            # 獲取文章中的所有圖片
            content = article.get('article_content_full') or article.get('article_content', '')
            description = article.get('article_desc', '')
            _, content_images = self._parse_html_content(content)
            _, desc_images = self._parse_html_content(description)
            all_images = content_images + desc_images

            # 主圖來源判定
            main_image_url = article.get('article_cover') or article.get('content_cover') or article.get('suggest_cover')
            if not main_image_url and all_images:
                main_image_url = all_images[0]

            # 組裝附件順序：第 1 張為主圖，其餘維持正序
            attachment_images: List[str] = []
            if main_image_url:
                attachment_images.append(main_image_url)

            removed_main_once = False
            for image_url in all_images:
                if main_image_url and not removed_main_once and image_url == main_image_url:
                    removed_main_once = True
                    continue
                attachment_images.append(image_url)

            # 發送主文 + 第 1 張圖片（附件）
            embed.set_image(url=None)  # 禁止以 URL 連結方式顯示圖片
            if attachment_images:
                first_image_url = attachment_images[0]
                async with aiohttp.ClientSession() as session:
                    logger.info(f"開始下載第 1 張圖片（主圖）: {first_image_url}")
                    first_result = await self._download_image_as_file(first_image_url, session, max_retries=2)
                    if first_result:
                        image_data, detected_ext = first_result
                        first_filename = self._get_image_filename_with_ext(first_image_url, 1, detected_ext)
                        first_file = discord.File(image_data, filename=first_filename)
                        embed.set_image(url=f"attachment://{first_filename}")
                        await channel.send(embed=embed, files=[first_file])
                        logger.info(f"📤 發送文章主文+第1張圖片完成: {first_filename}")
                    else:
                        await channel.send(embed=embed)
                        logger.warning(f"❌ 第 1 張主圖下載失敗，僅發送主文: {first_image_url}")
            else:
                await channel.send(embed=embed)
                logger.info("📤 發送文章主文完成（無圖片）")

            logger.info("🧭 進入其餘圖片發送流程（正序）")

            if attachment_images:
                logger.info(f"總共有 {len(attachment_images)} 張附件圖片需要發送（正序）。")
                logger.debug(f"附件發送順序預覽: {attachment_images[:5]}")

                # 將其餘附件圖片分塊，每塊最多 10 張
                chunk_size = 10
                rest_images = attachment_images[1:]
                image_chunks = [rest_images[i:i + chunk_size] for i in range(0, len(rest_images), chunk_size)]

                for i, chunk in enumerate(image_chunks):
                    logger.info(f"準備發送第 {i+1} 批附件，共 {len(chunk)} 張圖片。")
                    files = []
                    async with aiohttp.ClientSession() as session:
                        for j, image_url in enumerate(chunk):
                            # 原始索引：第 2 張起
                            original_index = sum(len(c) for c in image_chunks[:i]) + j + 2
                            logger.info(f"開始下載第 {original_index} 張圖片（批次 {i+1}，圖片 {j+1}）: {image_url}")
                            download_result = await self._download_image_as_file(image_url, session)
                            if download_result:
                                image_data, detected_ext = download_result
                                filename = self._get_image_filename_with_ext(image_url, original_index, detected_ext)
                                discord_file = discord.File(image_data, filename=filename)
                                files.append(discord_file)
                                logger.info(f"✅ 已準備附件: {filename}")
                            else:
                                logger.warning(f"❌ 跳過無法下載的圖片: {image_url}")

                    if files:
                        logger.info(f"📎 準備發送 {len(files)} 個圖片附件...")
                        await asyncio.sleep(0.5)  # 短暫延遲確保順序

                        # 直接發送附件，不顯示提示訊息
                        await channel.send(files=files)
                        logger.info(f"✅ 發送 {len(files)} 個圖片附件完成")
                    else:
                        logger.warning(f"批次 {i+1} 中沒有成功準備的附件。")
            else:
                logger.info("📎 無附件需要發送")

            # 記錄已發送的文章
            self.mark_content_as_sent('article', article['article_id'])

            logger.info(f"成功發送文章 {article['article_id']} 到頻道 {channel_id}")
            return True

        except Exception as e:
            logger.error(f"發送文章到頻道失敗: {e}")
            return False

    async def check_and_send_new_articles(self, channel_ids: List[int]):
        """檢查並發送新文章到指定頻道"""
        try:
            # 取得最近的文章
            articles = await self.fetch_recent_articles(days=3)

            if not articles:
                article_logger.info("[排程]沒有找到新文章")
                return

            # 篩選出未發送的文章
            new_articles = []
            for article in articles:
                if not self.is_content_sent('article', article['article_id']):
                    new_articles.append(article)

            if not new_articles:
                # 使用專門的文章監控日誌器記錄，避免汙染主日誌
                article_logger.info("[排程]沒有新的未發送文章")
                return

            article_logger.info(f"[排程]找到 {len(new_articles)} 篇新文章（已在資料庫層面按時間排序：舊→新）")

            # 記錄文章時間順序（用於除錯）
            for i, article in enumerate(new_articles):
                time_str = article.get('start_time') or article.get('create_time') or '無時間'
                logger.debug(f"[排程]  第 {i+1} 篇: {article.get('article_id')} - {time_str}")

            # 發送新文章到所有指定頻道
            for article in new_articles:
                for channel_id in channel_ids:
                    success = await self.send_article_to_channel(channel_id, article)
                    if success:
                        logger.info(f"[排程]成功發送文章 {article['article_id']} 到頻道 {channel_id}")
                        # 每篇文章之間稍微延遲，避免頻率限制
                        await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"[排程]檢查新文章時發生錯誤: {e}")

    async def start_monitoring(self, channel_ids: List[int], check_interval: int = 180):
        """開始監控文章（每3分鐘檢查一次）"""
        article_logger.info(f"[排程]開始監控文章，檢查間隔: {check_interval} 秒")

        while True:
            try:
                await self.check_and_send_new_articles(channel_ids)
                await asyncio.sleep(check_interval)

            except Exception as e:
                article_logger.error(f"[排程]監控循環發生錯誤: {e}")
                await asyncio.sleep(60)  # 發生錯誤時短暫延遲後重試

    async def start_fb_monitoring(self, channel_ids: List[int], check_interval: int = 600):
        """開始監控 FB 貼文（每10分鐘檢查一次）"""
        logger.info(f"[FB]開始監控 FB 貼文，檢查間隔: {check_interval} 秒")

        while True:
            try:
                await self.check_and_send_fb_posts(channel_ids)
                await asyncio.sleep(check_interval)

            except Exception as e:
                logger.error(f"[FB]監控循環發生錯誤: {e}")
                await asyncio.sleep(300)  # 發生錯誤時5分鐘後重試

    async def _download_image_as_file(
        self,
        image_url: str,
        session: aiohttp.ClientSession,
        max_retries: int = 2,
        retry_delay: float = 1.0
    ) -> Optional[tuple]:
        """
        下載圖片並返回 BytesIO 物件和檔案副檔名

        Args:
            image_url: 圖片 URL
            session: aiohttp 會話

        Returns:
            (BytesIO 物件, 副檔名) 或 None（如果下載失敗）
        """
        request_headers = self._build_request_headers()

        for attempt in range(max_retries + 1):
            try:
                logger.info(f"🔄 開始下載圖片 (attempt={attempt + 1}/{max_retries + 1}): {image_url}")
                async with session.get(image_url, timeout=10, headers=request_headers) as response:
                    logger.info(f"📡 HTTP 回應狀態: {response.status} for {image_url}")

                    # 可重試的狀態碼
                    if response.status in {429, 500, 502, 503, 504}:
                        if attempt < max_retries:
                            wait_seconds = retry_delay * (attempt + 1)
                            logger.warning(
                                f"⚠️ 圖片下載暫時失敗 (status={response.status})，"
                                f"{wait_seconds:.1f}s 後重試: {image_url}"
                            )
                            await asyncio.sleep(wait_seconds)
                            continue

                        logger.warning(f"❌ 圖片下載重試耗盡 (status={response.status}): {image_url}")
                        return None

                    if response.status != 200:
                        logger.warning(f"❌ 下載圖片失敗，狀態碼 {response.status}: {image_url}")
                        return None

                    content = await response.read()

                    # 檢查內容大小（Discord 限制 25MB）
                    if len(content) > 25 * 1024 * 1024:  # 25MB 限制
                        logger.warning(f"⚠️ 圖片過大，超過 Discord 上限，跳過: {image_url} ({len(content)} bytes)")
                        return None

                    # 從 Content-Type 推斷副檔名
                    content_type = response.headers.get('content-type', '').lower()
                    ext = '.jpg'  # 預設
                    if 'png' in content_type:
                        ext = '.png'
                    elif 'gif' in content_type:
                        ext = '.gif'
                    elif 'webp' in content_type:
                        ext = '.webp'
                    elif 'bmp' in content_type:
                        ext = '.bmp'
                    elif 'jpeg' in content_type or 'jpg' in content_type:
                        ext = '.jpg'

                    image_data = io.BytesIO(content)
                    image_data.seek(0)
                    logger.info(
                        f"✅ 成功下載圖片: {image_url} ({len(content)} bytes), "
                        f"Content-Type: {content_type}, 推斷副檔名: {ext}"
                    )
                    return (image_data, ext)

            except asyncio.TimeoutError:
                if attempt < max_retries:
                    wait_seconds = retry_delay * (attempt + 1)
                    logger.warning(f"下載圖片逾時，{wait_seconds:.1f}s 後重試: {image_url}")
                    await asyncio.sleep(wait_seconds)
                    continue

                logger.warning(f"下載圖片逾時（重試耗盡）: {image_url}")
                return None
            except Exception as e:
                if attempt < max_retries:
                    wait_seconds = retry_delay * (attempt + 1)
                    logger.warning(f"下載圖片發生錯誤，{wait_seconds:.1f}s 後重試: {image_url}, err={e}")
                    await asyncio.sleep(wait_seconds)
                    continue

                logger.error(f"下載圖片時發生錯誤（重試耗盡） {image_url}: {e}")
                return None

        return None

    def _get_image_filename_with_ext(self, image_url: str, index: int, detected_ext: str) -> str:
        """
        從 URL 獲取圖片檔名，優先使用檢測到的副檔名

        Args:
            image_url: 圖片 URL
            index: 圖片索引
            detected_ext: 從 Content-Type 檢測到的副檔名

        Returns:
            檔名字串
        """
        try:
            # 嘗試從 URL 解析檔名
            from urllib.parse import urlparse
            parsed = urlparse(image_url)
            filename = os.path.basename(parsed.path)

            # 檢查是否有檔名（不包含副檔名）
            name, url_ext = os.path.splitext(filename)

            # 優先使用檢測到的副檔名，其次使用 URL 中的副檔名
            final_ext = detected_ext
            if not final_ext and url_ext and url_ext.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']:
                final_ext = url_ext

            # 如果還是沒有副檔名，使用預設
            if not final_ext:
                final_ext = '.jpg'

            # 如果有合適的檔名，就使用它
            if name and len(name) > 0:
                filename = name + final_ext
            else:
                filename = f"image_{index}{final_ext}"

            # 確保檔名是安全的（移除特殊字符）
            import re
            filename = re.sub(r'[<>:"/\\|?*]', '_', filename)

            return filename

        except Exception as e:
            logger.warning(f"生成圖片檔名時發生錯誤: {e}, URL: {image_url}")
            # 發生錯誤時使用預設檔名
            return f"image_{index}{detected_ext or '.jpg'}"

    def _get_image_filename(self, image_url: str, index: int) -> str:
        """
        從 URL 獲取圖片檔名

        Args:
            image_url: 圖片 URL
            index: 圖片索引

        Returns:
            檔名字串
        """
        try:
            # 嘗試從 URL 解析檔名
            from urllib.parse import urlparse
            parsed = urlparse(image_url)
            filename = os.path.basename(parsed.path)

            # 檢查是否有副檔名
            name, ext = os.path.splitext(filename)

            # 如果沒有副檔名，或者副檔名不是常見的圖片格式，就根據 URL 判斷或使用預設
            if not ext or ext.lower() not in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']:
                # 嘗試從 URL 中判斷圖片格式
                if '.png' in image_url.lower():
                    ext = '.png'
                elif '.gif' in image_url.lower():
                    ext = '.gif'
                elif '.webp' in image_url.lower():
                    ext = '.webp'
                elif '.bmp' in image_url.lower():
                    ext = '.bmp'
                else:
                    ext = '.jpg'  # 預設為 jpg

                # 如果原本有檔名但沒有正確副檔名，就保留檔名
                if name:
                    filename = name + ext
                else:
                    filename = f"image_{index}{ext}"

            # 如果檔名為空或只有副檔名，使用索引
            if not filename or filename.startswith('.'):
                filename = f"image_{index}.jpg"

            # 確保檔名是安全的（移除特殊字符）
            import re
            filename = re.sub(r'[<>:"/\\|?*]', '_', filename)

            return filename

        except Exception as e:
            logger.warning(f"生成圖片檔名時發生錯誤: {e}, URL: {image_url}")
            # 發生錯誤時使用預設檔名
            return f"image_{index}.jpg"

    async def test_html_parsing(self, html_content: str) -> dict:
        """
        測試 HTML 解析功能

        Args:
            html_content: 要測試的 HTML 內容

        Returns:
            測試結果字典
        """
        try:
            logger.info("開始測試 HTML 解析功能")

            # 使用現有的解析方法
            parsed_text, images = self._parse_html_content(html_content)

            # 分析 Markdown 特徵
            markdown_features = {
                'headers': parsed_text.count('#'),
                'bold_text': parsed_text.count('**'),
                'italic_text': parsed_text.count('*') - parsed_text.count('**') * 2,
                'links': parsed_text.count('['),
                'bullet_lists': parsed_text.count('* '),
                'numbered_lists': len([line for line in parsed_text.split('\n') if line.strip() and line.strip()[0].isdigit() and '.' in line[:5]])
            }

            result = {
                'success': True,
                'parsed_text': parsed_text,
                'text_length': len(parsed_text),
                'images_found': len(images),
                'image_urls': images[:5],  # 只顯示前5張圖片
                'pypandoc_used': False,  # 現在固定為 False，因為已移除 pypandoc
                'markdown_features': markdown_features
            }

            logger.info(f"HTML 解析測試成功 - 文字長度: {len(parsed_text)}, 圖片數量: {len(images)}")
            return result

        except Exception as e:
            logger.error(f"HTML 解析測試失敗: {e}")
            return {
                'success': False,
                'error': str(e),
                'parsed_text': '',
                'text_length': 0,
                'images_found': 0,
                'image_urls': [],
                'pypandoc_used': False,
                'markdown_features': {}
            }

    # FB 貼文監控功能
    async def fetch_recent_fb_posts(self, days: int = 7) -> List[Dict]:
        """從 scraper API 取得最近的 FB 貼文"""
        return await self.fetch_content_from_api("/api/fb_posts/recent", {"days": days, "limit": 20})

    async def send_fb_post_to_channel(self, channel_id: int, fb_post: Dict) -> bool:
        """發送 FB 貼文到指定頻道"""
        try:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                logger.error(f"找不到頻道 ID: {channel_id}")
                return False

            logger.info(f"[RESEND_ROUTE] 進入 send_fb_post_to_channel: fb_id={fb_post.get('id')}, channel_id={channel_id}")

            embed = self.format_fb_embed(fb_post)

            # FB 分支改為：主文 + 第1張圖片（附件）同次發送，再發其餘圖片（正序）
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

            success = True

            if success:
                self.mark_content_as_sent('fbpost', fb_post['id'])
                logger.info(f"成功發送 FB 貼文 {fb_post['id']} 到頻道 {channel_id}")

            return success

        except Exception as e:
            logger.error(f"發送 FB 貼文到頻道失敗: {e}")
            return False

    def format_fb_embed(self, fb_post: Dict):
        """格式化 FB 貼文為 Discord Embed"""

        # 優先使用 text_md（Discord Markdown 格式），如果沒有則使用 text
        description_text = fb_post.get('text_md') or fb_post.get('text', '')
        description = description_text[:2000] if description_text else ''

        # 優先使用 url 欄位，如果 url 是空的則使用 pfbid_url
        embed_url = fb_post.get('url') or fb_post.get('pfbid_url')

        # 優先使用 timestamp（貼文發佈時間），如果沒有則使用 created_at（資料庫記錄時間）
        timestamp_str = fb_post.get('timestamp') or fb_post.get('created_at')
        timestamp = None
        if timestamp_str:
            try:
                # 處理 ISO 格式時間戳
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

        # 添加來源資訊
        embed.add_field(name="📘 來源", value="Facebook", inline=True)

        # 處理圖片
        images = fb_post.get('images', [])
        if images:
            logger.info(f"FB 貼文 {fb_post.get('id', 'unknown')} 設定圖片: {images[0]}")
            embed.set_image(url=images[0])
        else:
            logger.info(f"FB 貼文 {fb_post.get('id', 'unknown')} 沒有圖片")

        # 添加 footer
        embed.set_footer(text="鳴潮官方 Facebook")

        return embed

    async def check_and_send_fb_posts(self, channel_ids: List[int]):
        """檢查並發送新的 FB 貼文"""
        try:
            fb_posts = await self.fetch_recent_fb_posts(days=7)

            if not fb_posts:
                logger.info("[FB] 沒有找到新 FB 貼文")
                return

            # 篩選未發送的貼文
            new_posts = []
            for post in fb_posts:
                if not self.is_content_sent('fbpost', post['id']):
                    new_posts.append(post)

            if not new_posts:
                logger.info("[FB] 沒有新的未發送 FB 貼文")
                return

            logger.info(f"[FB] 找到 {len(new_posts)} 篇新 FB 貼文")

            # 發送到所有指定頻道
            for post in new_posts:
                for channel_id in channel_ids:
                    success = await self.send_fb_post_to_channel(channel_id, post)
                    if success:
                        logger.info(f"[FB] 成功發送 FB 貼文 {post['id']} 到頻道 {channel_id}")
                        await asyncio.sleep(2)  # 延遲避免頻率限制

        except Exception as e:
            logger.error(f"[FB] 檢查 FB 貼文時發生錯誤: {e}")
