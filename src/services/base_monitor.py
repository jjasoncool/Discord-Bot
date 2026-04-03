"""
基礎內容監控類別
提供共用的內容監控、發送和記錄功能
底層使用 SQLite（state_db.py）取代原本的 sent_articles.json
"""
import asyncio
import aiohttp
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional

from utils.logger_config import get_article_monitor_logger
from services.state_db import StateDB

logger = get_article_monitor_logger()

# 全域共用 StateDB 實例（避免多個 monitor 各開各的連線）
_shared_state_db: Optional[StateDB] = None
_shared_state_db_lock = asyncio.Lock()

# article_runtime.json 共用快取（TTL 5 分鐘）
_article_runtime_cache: Dict = {}
_article_runtime_cache_time: float = 0
_ARTICLE_RUNTIME_PATH = Path(__file__).parent.parent / "settings" / "article_runtime.json"
_ARTICLE_RUNTIME_TTL = 300


def get_article_runtime_config() -> Dict:
    """讀取 article_runtime.json（TTL 快取，所有 monitor 共用）。"""
    import time
    global _article_runtime_cache, _article_runtime_cache_time
    now = time.time()
    if _article_runtime_cache and (now - _article_runtime_cache_time) < _ARTICLE_RUNTIME_TTL:
        return _article_runtime_cache
    try:
        _article_runtime_cache = json.loads(_ARTICLE_RUNTIME_PATH.read_text(encoding="utf-8"))
        _article_runtime_cache_time = now
    except Exception:
        pass
    return _article_runtime_cache


async def get_shared_state_db() -> StateDB:
    """取得全域共用的 StateDB 實例（併發安全）。"""
    global _shared_state_db
    async with _shared_state_db_lock:
        if _shared_state_db is None:
            _shared_state_db = StateDB()
            await _shared_state_db.connect()
    return _shared_state_db


class BaseContentMonitor:
    """基礎內容監控類別"""

    def __init__(self, bot, scraper_api_url: str = "http://scraper:8000"):
        self.bot = bot
        self.scraper_api_url = scraper_api_url
        self._state_db: Optional[StateDB] = None

    async def _get_state_db(self) -> StateDB:
        """延遲取得 StateDB（第一次使用時才建立連線）。"""
        if self._state_db is None:
            self._state_db = await get_shared_state_db()
        return self._state_db

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

    async def mark_content_as_sent(self, content_type: str, content_id) -> None:
        """標記內容為已發送"""
        db = await self._get_state_db()
        await db.mark_content_as_sent(content_type, str(content_id))

    async def update_ptt_state(self, article_key: str, state: Dict) -> None:
        """更新 PTT 發送狀態（thread/comment 增量用）"""
        db = await self._get_state_db()
        await db.update_ptt_state(article_key, state)

    async def get_ptt_state(self, article_key: str) -> Dict:
        """取得 PTT 發送狀態"""
        db = await self._get_state_db()
        return await db.get_ptt_state(article_key)

    async def is_content_sent(self, content_type: str, content_id) -> bool:
        """檢查內容是否已發送"""
        db = await self._get_state_db()
        return await db.is_content_sent(content_type, str(content_id))
