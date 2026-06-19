"""
官方文章更新服務
定期檢查 scraper API 取得新文章並發送到 Discord 頻道
"""
import asyncio
import aiohttp
import logging
import discord
from datetime import datetime
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
from utils.logger_config import get_discord_bot_logger, get_article_monitor_logger
from utils.discord_content import post_to_channel

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

    # ── API 呼叫 ──

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

    # ── HTML 解析 ──

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

    # ── 格式化 ──

    def format_article_embed(self, article: Dict) -> dict:
        """格式化文章為 Discord Embed"""
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

    # ── 發送 ──

    async def send_article_to_channel(self, channel_id: int, article: Dict):
        """發送文章到指定頻道（支援多圖片附件，並在超過限制時分批發送）"""
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
            # 改走共用 post_to_channel：文字頻道→發訊息、論壇頻道→自動開 thread
            # （回傳首則訊息，後續補圖用 sent_message.channel 才能正確送進 thread）
            embed.set_image(url=None)  # 禁止以 URL 連結方式顯示圖片
            sent_message = None
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
                        sent_message = await post_to_channel(channel, embed=embed, files=[first_file], thread_title=embed.title)
                        logger.info(f"📤 發送文章主文+第1張圖片完成: {first_filename}")
                    else:
                        sent_message = await post_to_channel(channel, embed=embed, thread_title=embed.title)
                        logger.warning(f"❌ 第 1 張主圖下載失敗，僅發送主文: {first_image_url}")
            else:
                sent_message = await post_to_channel(channel, embed=embed, thread_title=embed.title)
                logger.info("📤 發送文章主文完成（無圖片）")

            # 後續補圖的目標：論壇→剛建立的 thread、文字→原頻道
            followup_target = sent_message.channel if sent_message else channel

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

                        # 直接發送附件，不顯示提示訊息（送到 followup_target：thread 或原頻道）
                        await followup_target.send(files=files)
                        logger.info(f"✅ 發送 {len(files)} 個圖片附件完成")
                    else:
                        logger.warning(f"批次 {i+1} 中沒有成功準備的附件。")
            else:
                logger.info("📎 無附件需要發送")

            # 記錄已發送的文章
            await self.mark_content_as_sent('article', article['article_id'])

            logger.info(f"成功發送文章 {article['article_id']} 到頻道 {channel_id}")
            return True

        except Exception as e:
            logger.error(f"發送文章到頻道失敗: {e}")
            return False

    # ── 排程 ──

    async def check_and_send_new_articles(self, channel_ids: List[int]):
        """檢查並發送新文章到指定頻道"""
        try:
            # 取得最近的文章
            articles = await self.fetch_recent_articles(days=3)

            if not articles:
                article_logger.debug("[排程]沒有找到新文章")
                return

            # 篩選出未發送的文章
            new_articles = []
            for article in articles:
                if not await self.is_content_sent('article', article['article_id']):
                    new_articles.append(article)

            if not new_articles:
                # 使用專門的文章監控日誌器記錄，避免汙染主日誌
                article_logger.debug("[排程]沒有新的未發送文章")
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
