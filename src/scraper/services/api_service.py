"""
API 服務模組
處理所有外部 API 請求
"""
import time
import random
from typing import Optional, Dict, Any

from curl_cffi import requests
from services.base_scraper_client import BaseScraperClient
from utils.logger import get_logger


class APIService(BaseScraperClient):
    """API 服務類別"""

    def __init__(self, timeout: int = 30, default_delay: int = 2, max_retries: int = 3):
        super().__init__()
        self.timeout = timeout
        self.default_delay = default_delay
        self.max_retries = max_retries
        self.logger = get_logger('api_service')

    def _get_headers(self) -> Dict[str, str]:
        """API 請求 headers（User-Agent 由 curl_cffi impersonate 自動處理）"""
        return {
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-TW,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
        }

    def _random_delay(self, base_delay: int) -> float:
        """產生隨機延遲時間"""
        return base_delay + random.uniform(0, base_delay * 0.5)

    def fetch_data(self, url: str, delay: Optional[int] = None, retries: Optional[int] = None) -> Optional[Dict[Any, Any]]:
        """
        抓取 JSON 資料，支援重試機制

        Args:
            url: API 網址
            delay: 延遲秒數，避免被 ban
            retries: 重試次數

        Returns:
            JSON 資料或 None
        """
        if delay is None:
            delay = self.default_delay
        if retries is None:
            retries = self.max_retries

        for attempt in range(retries + 1):
            try:
                # 隨機延遲時間增加變化
                actual_delay = self._random_delay(delay)
                time.sleep(actual_delay)

                headers = self._get_headers()
                if attempt == 0:  # 只在第一次嘗試時記錄
                    self.logger.info(f"請求 URL: {url}")
                    self.logger.debug(f"使用 impersonate: {self._current_impersonate}")

                with self._build_session() as session:
                    response = session.get(url, headers=headers, timeout=self.timeout)
                response.raise_for_status()

                # 檢查回應內容類型
                content_type = response.headers.get('content-type', '').lower()
                if 'application/json' not in content_type and 'text/json' not in content_type:
                    self.logger.warning(f"回應不是 JSON 格式: {content_type}")

                return response.json()

            except requests.exceptions.HTTPError as e:
                status_code = getattr(getattr(e, 'response', None), 'status_code', None)
                if status_code in [429, 503, 502, 504]:  # 可重試的狀態碼
                    self.logger.warning(f"HTTP 錯誤 {status_code} (嘗試 {attempt + 1}/{retries + 1}): {url}")
                    if attempt < retries:
                        extended_delay = delay * (2 ** attempt) + random.uniform(1, 5)
                        time.sleep(extended_delay)
                        continue
                else:
                    self.logger.error(f"HTTP 錯誤 {status_code}: {str(e)}")
                    break

            except Exception as e:
                err_name = type(e).__name__
                if attempt < retries:
                    self.logger.warning(f"連線錯誤 (嘗試 {attempt + 1}/{retries + 1}): {str(e)}")
                    time.sleep(delay * (attempt + 1))
                else:
                    self.logger.error(f"請求失敗（{err_name}）: {str(e)}")
                    break

        return None
