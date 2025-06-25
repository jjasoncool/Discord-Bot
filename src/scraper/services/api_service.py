"""
API 服務模組
處理所有外部 API 請求
"""
import time
import requests
from datetime import datetime
from typing import Optional, Dict, Any
from utils.logger import get_logger


class APIService:
    """API 服務類別"""

    def __init__(self, timeout: int = 30, default_delay: int = 2):
        self.timeout = timeout
        self.default_delay = default_delay
        self.logger = get_logger('api_service')

    def fetch_data(self, url: str, delay: Optional[int] = None) -> Optional[Dict[Any, Any]]:
        """
        抓取 JSON 資料

        Args:
            url: API 網址
            delay: 延遲秒數，避免被 ban

        Returns:
            JSON 資料或 None
        """
        try:
            if delay is None:
                delay = self.default_delay

            time.sleep(delay)
            response = requests.get(url, timeout=self.timeout)
            response.raise_for_status()

            return response.json()

        except requests.exceptions.RequestException as e:
            self.logger.error(f"網路請求錯誤 ({url}): {str(e)}")
            return None
        except ValueError as e:
            self.logger.error(f"JSON 解析錯誤 ({url}): {str(e)}")
            return None
        except Exception as e:
            self.logger.error(f"未知錯誤 ({url}): {str(e)}", exc_info=True)
            return None
