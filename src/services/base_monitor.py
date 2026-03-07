"""
基礎內容監控類別
提供共用的內容監控、發送和記錄功能
"""
import asyncio
import aiohttp
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
# from abc import ABC, abstractmethod  # 不使用抽象方法

from utils.logger_config import get_article_monitor_logger

logger = get_article_monitor_logger()

class BaseContentMonitor:
    """基礎內容監控類別"""

    def __init__(self, bot, scraper_api_url: str = "http://scraper:8000"):
        self.bot = bot
        self.scraper_api_url = scraper_api_url
        self.sent_content_file = Path("/app/services/sent_articles.json")
        self._load_sent_content()

    def _load_sent_content(self):
        """載入已發送的內容記錄"""
        try:
            if self.sent_content_file.exists():
                with open(self.sent_content_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.sent_article_ids = set(data.get('sent_article_ids', []))
                self.sent_fbpost_ids = set(data.get('sent_fbpost_ids', []))
                self.sent_article_keys = set(data.get('sent_article_keys', []))
            else:
                self.sent_article_ids = set()
                self.sent_fbpost_ids = set()
                self.sent_article_keys = set()
        except Exception as e:
            logger.error(f"載入已發送內容記錄失敗: {e}")
            self.sent_article_ids = set()
            self.sent_fbpost_ids = set()
            self.sent_article_keys = set()

    def _save_sent_content(self):
        """儲存已發送的內容記錄"""
        try:
            # 只保留最近 7 天的記錄
            data = {
                'sent_article_ids': list(self.sent_article_ids),
                'sent_fbpost_ids': list(self.sent_fbpost_ids),
                'sent_article_keys': list(self.sent_article_keys),
                'last_updated': datetime.now().isoformat()
            }

            with open(self.sent_content_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

        except Exception as e:
            logger.error(f"儲存已發送內容記錄失敗: {e}")

    async def fetch_content_from_api(self, endpoint: str, params: Dict = None) -> List[Dict]:
        """從 API 獲取內容的通用方法"""
        try:
            url = f"{self.scraper_api_url}{endpoint}"
            request_params = params or {}

            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=request_params, timeout=30) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get('success'):
                            logger.debug(f"成功從 {endpoint} 取得 {len(data.get('articles', data.get('posts', [])))} 筆內容")
                            # 統一返回內容列表
                            return data.get('articles', data.get('posts', []))
                        else:
                            logger.error(f"API 回應失敗: {data.get('message')}")
                    else:
                        logger.error(f"API 請求失敗，狀態碼: {response.status}")

        except asyncio.TimeoutError:
            logger.error("API 請求逾時")
        except Exception as e:
            logger.error(f"取得內容時發生錯誤: {e}")

        return []

    async def send_embed_to_channels(self, embed, channel_ids: List[int], files: List = None) -> bool:
        """將 Embed 發送到指定頻道的通用方法"""
        success_count = 0

        for channel_id in channel_ids:
            try:
                channel = self.bot.get_channel(channel_id)
                if not channel:
                    logger.error(f"找不到頻道 ID: {channel_id}")
                    continue

                # 發送主要 embed
                await channel.send(embed=embed)

                # 如果有附件，一起發送
                if files:
                    await channel.send(files=files)

                success_count += 1
                logger.info(f"成功發送到頻道 {channel_id}")

            except Exception as e:
                logger.error(f"發送到頻道 {channel_id} 失敗: {e}")

        return success_count > 0

    def mark_content_as_sent(self, content_type: str, content_id):
        """標記內容為已發送"""
        if content_type == 'article':
            self.sent_article_ids.add(content_id)
        elif content_type == 'fbpost':
            self.sent_fbpost_ids.add(content_id)
        elif content_type == 'ptt':
            self.sent_article_keys.add(str(content_id))

        self._save_sent_content()

    def is_content_sent(self, content_type: str, content_id) -> bool:
        """檢查內容是否已發送"""
        if content_type == 'article':
            return content_id in self.sent_article_ids
        elif content_type == 'fbpost':
            return content_id in self.sent_fbpost_ids
        elif content_type == 'ptt':
            return str(content_id) in self.sent_article_keys
        return False
