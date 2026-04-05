"""
基礎內容監控類別
提供共用的內容監控、發送、圖片下載和記錄功能
底層使用 SQLite（state_db.py）取代原本的 sent_articles.json
"""
import asyncio
import aiohttp
import io
import json
import logging
import os
import random
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
from urllib.parse import urlparse

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

    # ── 共用圖片下載與檔名工具 ──

    # 常見圖片副檔名（供子類別使用）
    IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp")
    DISALLOWED_IMAGE_EXTENSIONS = (".ico",)

    def _build_request_headers(self) -> Dict[str, str]:
        """建立下載圖片用的請求標頭（優先使用 fake-useragent，否則使用內建隨機 UA 池）"""
        user_agent = None
        try:
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

    async def _download_image_as_file(
        self,
        image_url: str,
        session: aiohttp.ClientSession,
        max_retries: int = 2,
        retry_delay: float = 1.0,
    ) -> Optional[tuple]:
        """
        下載圖片並返回 BytesIO 物件和檔案副檔名。

        Returns:
            (BytesIO 物件, 副檔名) 或 None（如果下載失敗）
        """
        request_headers = self._build_request_headers()

        for attempt in range(max_retries + 1):
            try:
                logger.info("🔄 開始下載圖片 (attempt=%s/%s): %s", attempt + 1, max_retries + 1, image_url)
                async with session.get(image_url, timeout=10, headers=request_headers) as response:
                    logger.info("📡 HTTP 回應狀態: %s for %s", response.status, image_url)

                    # 可重試的狀態碼
                    if response.status in {429, 500, 502, 503, 504}:
                        if attempt < max_retries:
                            wait_seconds = retry_delay * (attempt + 1)
                            logger.warning(
                                "⚠️ 圖片下載暫時失敗 (status=%s)，%.1fs 後重試: %s",
                                response.status, wait_seconds, image_url,
                            )
                            await asyncio.sleep(wait_seconds)
                            continue
                        logger.warning("❌ 圖片下載重試耗盡 (status=%s): %s", response.status, image_url)
                        return None

                    if response.status != 200:
                        logger.warning("❌ 下載圖片失敗，狀態碼 %s: %s", response.status, image_url)
                        return None

                    content = await response.read()

                    # 檢查內容大小（Discord 限制 25MB）
                    if len(content) > 25 * 1024 * 1024:
                        logger.warning("⚠️ 圖片過大，超過 Discord 上限，跳過: %s (%s bytes)", image_url, len(content))
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
                        "✅ 成功下載圖片: %s (%s bytes), Content-Type: %s, 推斷副檔名: %s",
                        image_url, len(content), content_type, ext,
                    )
                    return (image_data, ext)

            except asyncio.TimeoutError:
                if attempt < max_retries:
                    wait_seconds = retry_delay * (attempt + 1)
                    logger.warning("下載圖片逾時，%.1fs 後重試: %s", wait_seconds, image_url)
                    await asyncio.sleep(wait_seconds)
                    continue
                logger.warning("下載圖片逾時（重試耗盡）: %s", image_url)
                return None
            except Exception as e:
                if attempt < max_retries:
                    wait_seconds = retry_delay * (attempt + 1)
                    logger.warning("下載圖片發生錯誤，%.1fs 後重試: %s, err=%s", wait_seconds, image_url, e)
                    await asyncio.sleep(wait_seconds)
                    continue
                logger.error("下載圖片時發生錯誤（重試耗盡） %s: %s", image_url, e)
                return None

        return None

    def _get_image_filename_with_ext(self, image_url: str, index: int, detected_ext: str) -> str:
        """從 URL 獲取圖片檔名，優先使用檢測到的副檔名。"""
        try:
            parsed = urlparse(image_url)
            filename = os.path.basename(parsed.path)
            name, url_ext = os.path.splitext(filename)

            final_ext = detected_ext
            if not final_ext and url_ext and url_ext.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']:
                final_ext = url_ext
            if not final_ext:
                final_ext = '.jpg'

            if name and len(name) > 0:
                filename = name + final_ext
            else:
                filename = f"image_{index}{final_ext}"

            filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
            return filename

        except Exception as e:
            logger.warning("生成圖片檔名時發生錯誤: %s, URL: %s", e, image_url)
            return f"image_{index}{detected_ext or '.jpg'}"

    def _get_image_filename(self, image_url: str, index: int) -> str:
        """從 URL 獲取圖片檔名（無 Content-Type 資訊時使用）。"""
        try:
            parsed = urlparse(image_url)
            filename = os.path.basename(parsed.path)
            name, ext = os.path.splitext(filename)

            if not ext or ext.lower() not in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']:
                if '.png' in image_url.lower():
                    ext = '.png'
                elif '.gif' in image_url.lower():
                    ext = '.gif'
                elif '.webp' in image_url.lower():
                    ext = '.webp'
                elif '.bmp' in image_url.lower():
                    ext = '.bmp'
                else:
                    ext = '.jpg'

                if name:
                    filename = name + ext
                else:
                    filename = f"image_{index}{ext}"

            if not filename or filename.startswith('.'):
                filename = f"image_{index}.jpg"

            filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
            return filename

        except Exception as e:
            logger.warning("生成圖片檔名時發生錯誤: %s, URL: %s", e, image_url)
            return f"image_{index}.jpg"
