"""
官方文章更新服務
定期檢查 scraper API 取得新文章並發送到 Discord 頻道
"""
import asyncio
import aiohttp
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from pathlib import Path

logger = logging.getLogger('article_monitor')

class ArticleMonitor:
    """官方文章更新類別"""

    def __init__(self, bot, scraper_api_url: str = "http://scraper:8000"):
        self.bot = bot
        self.scraper_api_url = scraper_api_url
        self.sent_articles_file = Path("/app/services/sent_articles.json")
        self.sent_articles = self._load_sent_articles()

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
            # 使用專為 Discord 設計的 API 端點
            url = f"{self.scraper_api_url}/api/articles/discord"
            params = {"days": days, "limit": 50}

            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=30) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get('success'):
                            logger.info(f"成功取得 {len(data['articles'])} 篇文章（包含完整內容）")
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

    def format_article_embed(self, article: Dict) -> dict:
        """格式化文章為 Discord Embed"""
        import discord

        # 優先使用完整版本的內容，如果沒有則使用簡短版本
        content = article.get('article_content_full') or article.get('article_content', '')
        description = article.get('article_desc', '')

        # 限制描述長度
        if description and len(description) > 2000:
            description = description[:1997] + "..."
        elif not description and content:
            # 如果沒有描述，使用內容的前200字作為描述
            description = content[:200] + "..." if len(content) > 200 else content

        embed = discord.Embed(
            title=article['article_title'],
            description=description,
            color=0x00ff00,
            timestamp=datetime.fromisoformat(article['start_time'].replace('Z', '+00:00')) if article.get('start_time') else None
        )

        # 添加文章 ID
        embed.add_field(name="文章 ID", value=article['article_id'], inline=True)

        # 添加文章類型
        if article.get('article_type_name'):
            embed.add_field(name="類型", value=article['article_type_name'], inline=True)
        elif article.get('article_type'):
            embed.add_field(name="類型 ID", value=article['article_type'], inline=True)

        # 添加遊戲 ID
        if article.get('game_id'):
            embed.add_field(name="遊戲 ID", value=article['game_id'], inline=True)

        # 優先使用副表的圖片，如果沒有則使用主表的
        image_url = article.get('article_cover') or article.get('content_cover') or article.get('suggest_cover')
        if image_url:
            embed.set_image(url=image_url)

        # 添加時間戳
        if article.get('create_time'):
            embed.set_footer(text=f"建立時間: {article['create_time']}")

        return embed

    async def send_article_to_channel(self, channel_id: int, article: Dict):
        """發送文章到指定頻道"""
        try:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                logger.error(f"找不到頻道 ID: {channel_id}")
                return False

            embed = self.format_article_embed(article)
            await channel.send(embed=embed)

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

            logger.info(f"找到 {len(new_articles)} 篇新文章")

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
