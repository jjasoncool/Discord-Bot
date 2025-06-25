"""
API 服務模組
處理所有外部 API 請求
"""
import time
import requests
import random
from datetime import datetime
from typing import Optional, Dict, Any
from fake_useragent import UserAgent
from utils.logger import get_logger


class APIService:
    """API 服務類別"""

    def __init__(self, timeout: int = 30, default_delay: int = 2, max_retries: int = 3):
        self.timeout = timeout
        self.default_delay = default_delay
        self.max_retries = max_retries
        self.logger = get_logger('api_service')

        # 初始化 UserAgent，加入錯誤處理
        try:
            self.ua = UserAgent()
        except Exception as e:
            self.logger.warning(f"無法初始化 UserAgent，使用預設值: {e}")
            self.ua = None

    def _get_headers(self) -> Dict[str, str]:
        """獲取隨機 User-Agent headers"""
        if self.ua:
            try:
                user_agent = self.ua.random
            except Exception as e:
                self.logger.warning(f"無法獲取隨機 User-Agent: {e}")
                user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        else:
            user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'

        return {
            'User-Agent': user_agent,
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
                    self.logger.debug(f"使用 User-Agent: {headers['User-Agent'][:50]}...")

                response = requests.get(url, headers=headers, timeout=self.timeout)
                response.raise_for_status()

                # 檢查回應內容類型
                content_type = response.headers.get('content-type', '').lower()
                if 'application/json' not in content_type and 'text/json' not in content_type:
                    self.logger.warning(f"回應不是 JSON 格式: {content_type}")

                return response.json()

            except requests.exceptions.Timeout as e:
                self.logger.warning(f"請求超時 (嘗試 {attempt + 1}/{retries + 1}): {url}")
                if attempt == retries:
                    self.logger.error(f"請求最終超時: {str(e)}")

            except requests.exceptions.HTTPError as e:
                status_code = e.response.status_code if e.response else None
                if status_code in [429, 503, 502, 504]:  # 可重試的狀態碼
                    self.logger.warning(f"HTTP 錯誤 {status_code} (嘗試 {attempt + 1}/{retries + 1}): {url}")
                    if attempt < retries:
                        # 對於速率限制錯誤，增加更長的延遲
                        extended_delay = delay * (2 ** attempt) + random.uniform(1, 5)
                        time.sleep(extended_delay)
                        continue
                else:
                    self.logger.error(f"HTTP 錯誤 {status_code}: {str(e)}")
                    break

            except requests.exceptions.ConnectionError as e:
                self.logger.warning(f"連線錯誤 (嘗試 {attempt + 1}/{retries + 1}): {str(e)}")
                if attempt < retries:
                    time.sleep(delay * (attempt + 1))

            except requests.exceptions.RequestException as e:
                self.logger.error(f"網路請求錯誤: {str(e)}")
                break

            except ValueError as e:
                self.logger.error(f"JSON 解析錯誤: {str(e)}")
                break

            except Exception as e:
                self.logger.error(f"未知錯誤: {str(e)}", exc_info=True)
                break

        return None
