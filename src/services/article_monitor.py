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
import tempfile
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from pathlib import Path
from bs4 import BeautifulSoup

logger = logging.getLogger('article_monitor')

class ArticleMonitor:
    """官方文章更新類別"""

    # 網站配置
    BASE_URL = "https://hw-media-cdn-mingchao.kurogame.com"
    WEBSITE_NAME = "鳴潮官方網站"

    def __init__(self, bot, scraper_api_url: str = "http://scraper:8000"):
        self.bot = bot
        self.scraper_api_url = scraper_api_url
        self.sent_articles_file = Path("/app/services/sent_articles.json")
        self.sent_articles = self._load_sent_articles()
        self.pypandoc_available = self._check_pypandoc()
        logger.info(f"初始化官方文章更新器，目標網站: {self.WEBSITE_NAME}")

    def _check_pypandoc(self) -> bool:
        """檢查 pypandoc 是否可用"""
        try:
            import pypandoc
            # 檢查 pandoc 是否已安裝
            pypandoc.get_pandoc_version()
            logger.info("pypandoc 可用，將使用 pypandoc 進行 HTML 解析")
            return True
        except Exception as e:
            logger.warning(f"pypandoc 不可用，將使用備用解析方法: {e}")
            return False

    def _load_sent_articles(self) -> set:
        """載入已發送的文章 ID 列表"""
        try:
            if self.sent_articles_file.exists():
                with open(self.sent_articles_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return set(data.get('sent_article_ids', []))
        except Exception as e:
            logger.error(f"載入已發送文章列表失敗: {e}")
        return set()

    def _save_sent_articles(self):
        """儲存已發送的文章 ID 列表"""
        try:
            # 只保留最近 7 天的記錄，避免檔案過大
            cutoff_date = datetime.now() - timedelta(days=7)

            data = {
                'sent_article_ids': list(self.sent_articles),
                'last_updated': datetime.now().isoformat(),
                'cutoff_date': cutoff_date.isoformat()
            }

            with open(self.sent_articles_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

        except Exception as e:
            logger.error(f"儲存已發送文章列表失敗: {e}")

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
                            logger.info(f"成功取得 {len(data['articles'])} 篇文章（已按時間排序：舊→新）")
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

    def _parse_html_content(self, html_content: str) -> tuple[str, List[str]]:
        """
        解析 HTML 內容，轉換為 Discord 支援的 Markdown 格式

        Returns:
            tuple: (純文字內容, 圖片URL列表)
        """
        if not html_content:
            logger.debug("HTML 內容為空，跳過解析")
            return "", []

        logger.debug(f"開始解析 HTML 內容，長度: {len(html_content)} 字符")

        # 首先使用 BeautifulSoup 提取圖片和清理內容
        images = []
        try:
            soup = BeautifulSoup(html_content, 'html.parser')

            # 收集所有圖片
            img_tags = soup.find_all('img')
            logger.debug(f"找到 {len(img_tags)} 個 img 標籤")

            for i, img in enumerate(img_tags):
                src = img.get('src')
                alt = img.get('alt', '')
                logger.debug(f"  圖片 {i+1}: src='{src}', alt='{alt}'")

                if src:
                    original_src = src
                    # 處理相對路徑
                    if src.startswith('//'):
                        src = 'https:' + src
                        logger.debug(f"    轉換 // 路徑: {original_src} -> {src}")
                    elif src.startswith('/'):
                        # 使用配置的基礎 URL
                        src = self.BASE_URL + src
                        logger.debug(f"    轉換相對路徑: {original_src} -> {src}")
                    elif not src.startswith('http'):
                        src = f"{self.BASE_URL}/" + src.lstrip('/')
                        logger.debug(f"    補全 URL: {original_src} -> {src}")
                    else:
                        logger.debug(f"    保持完整 URL: {src}")

                    images.append(src)
                else:
                    logger.debug(f"    跳過無 src 的圖片標籤")

            logger.debug(f"最終提取到 {len(images)} 張圖片: {images}")

            # 移除 script 和 style 標籤
            for script in soup(["script", "style", "noscript"]):
                script.decompose()

        except Exception as e:
            logger.error(f"BeautifulSoup 解析失敗: {e}")

        # 使用 pypandoc 進行 HTML 到 Markdown 轉換
        if self.pypandoc_available:
            try:
                import pypandoc

                # 使用 pypandoc 轉換 HTML 到 Markdown
                markdown_text = pypandoc.convert_text(
                    html_content,
                    'markdown',
                    format='html',
                    extra_args=[
                        '--wrap=none',  # 不自動換行
                        '--no-highlight',  # 不使用代碼高亮
                        '--reference-links',  # 使用參考式連結
                    ]
                )

                # 清理 pypandoc 轉換後的內容
                markdown_text = self._clean_pypandoc_output(markdown_text)

                return markdown_text, images

            except Exception as e:
                logger.error(f"pypandoc 轉換失敗，使用備用方法: {e}")

        # 備用方法：使用 BeautifulSoup 手動轉換
        return self._fallback_html_parsing(html_content, images)

    def _clean_pypandoc_output(self, markdown_text: str) -> str:
        """清理 pypandoc 轉換後的 Markdown 內容"""
        # 移除多餘的換行符
        markdown_text = re.sub(r'\n{3,}', '\n\n', markdown_text)

        # 清理多餘的空格
        markdown_text = re.sub(r'[ \t]+', ' ', markdown_text)

        # 修復列表格式
        markdown_text = re.sub(r'^-\s+', '• ', markdown_text, flags=re.MULTILINE)

        # 修復粗體格式（確保 Discord 相容）
        markdown_text = re.sub(r'\*\*([^*]+)\*\*', r'**\1**', markdown_text)

        # 修復斜體格式
        markdown_text = re.sub(r'\*([^*]+)\*', r'*\1*', markdown_text)

        # 清理連結格式
        markdown_text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'[\1](\2)', markdown_text)

        # 移除參考式連結的定義部分（Discord 不支援）
        markdown_text = re.sub(r'\n\s*\[[^\]]+\]:\s*https?://[^\s]+', '', markdown_text)

        return markdown_text.strip()

    def _fallback_html_parsing(self, html_content: str, images: List[str]) -> tuple[str, List[str]]:
        """備用的 HTML 解析方法"""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')

            # 處理各種 HTML 標籤轉換為 Markdown
            # 處理標題
            for tag in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
                level = int(tag.name[1])
                text = tag.get_text().strip()
                if text:
                    tag.string = '#' * level + ' ' + text + '\n\n'

            # 處理粗體和斜體
            for tag in soup.find_all(['b', 'strong']):
                text = tag.get_text().strip()
                if text:
                    tag.string = f"**{text}**"

            for tag in soup.find_all(['i', 'em']):
                text = tag.get_text().strip()
                if text:
                    tag.string = f"*{text}*"

            # 處理連結
            for tag in soup.find_all('a'):
                href = tag.get('href', '')
                text = tag.get_text().strip()
                if href and text:
                    if href.startswith('/'):
                        href = self.BASE_URL + href
                    tag.string = f"[{text}]({href})"

            # 處理列表
            for ul in soup.find_all('ul'):
                items = ul.find_all('li')
                list_text = ""
                for item in items:
                    item_text = item.get_text().strip()
                    if item_text:
                        list_text += f"• {item_text}\n"
                if list_text:
                    ul.string = list_text + "\n"

            for ol in soup.find_all('ol'):
                items = ol.find_all('li')
                list_text = ""
                for i, item in enumerate(items, 1):
                    item_text = item.get_text().strip()
                    if item_text:
                        list_text += f"{i}. {item_text}\n"
                if list_text:
                    ol.string = list_text + "\n"

            # 處理段落
            for p in soup.find_all('p'):
                text = p.get_text().strip()
                if text:
                    p.string = text + '\n\n'

            # 處理換行
            for br in soup.find_all('br'):
                br.replace_with('\n')

            # 處理區塊引用
            for blockquote in soup.find_all('blockquote'):
                text = blockquote.get_text().strip()
                if text:
                    quoted_text = '\n'.join([f"> {line}" for line in text.split('\n') if line.strip()])
                    blockquote.string = quoted_text + '\n\n'

            # 處理代碼區塊
            for code in soup.find_all('code'):
                text = code.get_text()
                if text:
                    code.string = f"`{text}`"

            for pre in soup.find_all('pre'):
                text = pre.get_text()
                if text:
                    pre.string = f"```\n{text}\n```\n"

            # 獲取純文字內容
            text = soup.get_text()

            # 清理多餘的空白和換行
            text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)  # 合併多個換行
            text = re.sub(r'[ \t]+', ' ', text)            # 合併多個空格
            text = re.sub(r'^\s+|\s+$', '', text, flags=re.MULTILINE)  # 移除行首行尾空白
            text = text.strip()

            return text, images

        except Exception as e:
            logger.error(f"備用 HTML 解析失敗: {e}")
            # 最後的備用方案：只移除 HTML 標籤
            try:
                soup = BeautifulSoup(html_content, 'html.parser')
                return soup.get_text().strip(), images
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
        """發送文章到指定頻道（支援多圖片附件）"""
        import discord

        try:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                logger.error(f"找不到頻道 ID: {channel_id}")
                return False

            embed = self.format_article_embed(article)

            # 獲取文章中的所有圖片
            content = article.get('article_content_full') or article.get('article_content', '')
            description = article.get('article_desc', '')
            _, content_images = self._parse_html_content(content)
            _, desc_images = self._parse_html_content(description)
            all_images = content_images + desc_images

            # 準備附件（第二張圖片開始）
            files = []
            if len(all_images) > 1:
                logger.info(f"準備下載 {len(all_images) - 1} 張附件圖片")

                # 限制附件數量（Discord 最多 10 個附件）
                max_attachments = min(9, len(all_images) - 1)  # 保留一個位置給可能的其他附件
                attachment_images = all_images[1:max_attachments + 1]

                async with aiohttp.ClientSession() as session:
                    for i, image_url in enumerate(attachment_images):
                        image_data = await self._download_image_as_file(image_url, session)
                        if image_data:
                            filename = self._get_image_filename(image_url, i + 2)
                            discord_file = discord.File(image_data, filename=filename)
                            files.append(discord_file)
                            logger.debug(f"已準備附件: {filename}")
                        else:
                            logger.warning(f"跳過無法下載的圖片: {image_url}")

                logger.info(f"成功準備 {len(files)} 個圖片附件")

            # 先發送 embed 消息
            await channel.send(embed=embed)
            logger.info("發送文章 embed 完成")

            # 如果有附件，稍後發送附件
            if files:
                await asyncio.sleep(0.5)  # 短暫延遲確保順序
                await channel.send(files=files)
                logger.info(f"發送 {len(files)} 個圖片附件完成")
            else:
                logger.info("無附件需要發送")

            # 記錄已發送的文章
            self.sent_articles.add(article['article_id'])
            self._save_sent_articles()

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
                logger.info("沒有找到新文章")
                return

            # 篩選出未發送的文章
            new_articles = []
            for article in articles:
                if article['article_id'] not in self.sent_articles:
                    new_articles.append(article)

            if not new_articles:
                logger.info("沒有新的未發送文章")
                return

            logger.info(f"找到 {len(new_articles)} 篇新文章（已在資料庫層面按時間排序：舊→新）")
            
            # 記錄文章時間順序（用於除錯）
            for i, article in enumerate(new_articles):
                time_str = article.get('start_time') or article.get('create_time') or '無時間'
                logger.debug(f"  第 {i+1} 篇: {article.get('article_id')} - {time_str}")

            # 發送新文章到所有指定頻道
            for article in new_articles:
                for channel_id in channel_ids:
                    success = await self.send_article_to_channel(channel_id, article)
                    if success:
                        # 每篇文章之間稍微延遲，避免頻率限制
                        await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"檢查新文章時發生錯誤: {e}")

    async def start_monitoring(self, channel_ids: List[int], check_interval: int = 180):
        """開始監控文章（每3分鐘檢查一次）"""
        logger.info(f"開始監控文章，檢查間隔: {check_interval} 秒")

        while True:
            try:
                await self.check_and_send_new_articles(channel_ids)
                await asyncio.sleep(check_interval)

            except Exception as e:
                logger.error(f"監控循環發生錯誤: {e}")
                await asyncio.sleep(60)  # 發生錯誤時短暫延遲後重試

    async def test_html_parsing(self, html_content: str) -> Dict:
        """
        測試 HTML 解析功能

        Args:
            html_content: 要測試的 HTML 內容

        Returns:
            Dict: 包含解析結果的字典
        """
        try:
            parsed_text, images = self._parse_html_content(html_content)

            result = {
                'success': True,
                'pypandoc_used': self.pypandoc_available,
                'original_html': html_content[:500] + "..." if len(html_content) > 500 else html_content,
                'parsed_text': parsed_text[:1500] + "..." if len(parsed_text) > 1500 else parsed_text,
                'images_found': len(images),
                'image_urls': images[:5],  # 最多顯示前5張圖片
                'text_length': len(parsed_text),
                'has_markdown': any(char in parsed_text for char in ['**', '*', '#', '[', ']', '>', '`']),
                'markdown_features': self._analyze_markdown_features(parsed_text)
            }

            return result

        except Exception as e:
            logger.error(f"HTML 解析測試失敗: {e}")
            return {
                'success': False,
                'error': str(e),
                'pypandoc_used': self.pypandoc_available,
                'original_html': html_content[:200] + "..." if len(html_content) > 200 else html_content
            }

    def _analyze_markdown_features(self, text: str) -> Dict[str, int]:
        """分析 Markdown 格式特徵"""
        return {
            'headers': len(re.findall(r'^#+\s', text, re.MULTILINE)),
            'bold_text': len(re.findall(r'\*\*[^*]+\*\*', text)),
            'italic_text': len(re.findall(r'\*[^*]+\*', text)),
            'links': len(re.findall(r'\[([^\]]+)\]\([^)]+\)', text)),
            'bullet_lists': len(re.findall(r'^•\s', text, re.MULTILINE)),
            'numbered_lists': len(re.findall(r'^\d+\.\s', text, re.MULTILINE)),
            'code_blocks': len(re.findall(r'```', text)),
            'inline_code': len(re.findall(r'`[^`]+`', text)),
            'blockquotes': len(re.findall(r'^>\s', text, re.MULTILINE))
        }

    async def _download_image_as_file(self, image_url: str, session: aiohttp.ClientSession) -> Optional[io.BytesIO]:
        """
        下載圖片並返回 BytesIO 物件

        Args:
            image_url: 圖片 URL
            session: aiohttp 會話

        Returns:
            BytesIO 物件或 None（如果下載失敗）
        """
        try:
            logger.debug(f"開始下載圖片: {image_url}")
            async with session.get(image_url, timeout=10) as response:
                if response.status == 200:
                    content = await response.read()
                    # 檢查內容大小（Discord 限制 25MB，但我們設定更小的限制）
                    if len(content) > 8 * 1024 * 1024:  # 8MB 限制
                        logger.warning(f"圖片過大，跳過: {image_url} ({len(content)} bytes)")
                        return None

                    image_data = io.BytesIO(content)
                    logger.debug(f"成功下載圖片: {image_url} ({len(content)} bytes)")
                    return image_data
                else:
                    logger.warning(f"下載圖片失敗，狀態碼 {response.status}: {image_url}")
                    return None

        except asyncio.TimeoutError:
            logger.warning(f"下載圖片逾時: {image_url}")
            return None
        except Exception as e:
            logger.error(f"下載圖片時發生錯誤 {image_url}: {e}")
            return None

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

            # 如果沒有副檔名，根據常見情況添加
            if not os.path.splitext(filename)[1]:
                filename += '.jpg'  # 預設為 jpg

            # 如果檔名為空或只有副檔名，使用索引
            if not filename or filename.startswith('.'):
                filename = f"image_{index}.jpg"

            return filename

        except Exception:
            # 發生錯誤時使用預設檔名
            return f"image_{index}.jpg"
