"""
反爬 HTTP client 基底類別

提供共用的 session 管理、TLS 指紋模擬、headers 建構、retry 邏輯。
子類別（BahamutScraperService、PTTScraperService 等）繼承後可直接使用，
或覆寫個別方法做來源專屬調整。

指紋來源（兩層，自動輪換）：
1. curl_cffi 內建 impersonate 池（Chrome/Firefox/Safari/Edge）— 70% 機率
2. 本地指紋庫 tools/fingerprints.json — 30% 機率
   由 extract_fingerprint.py 手動從容器內 Firefox ESR 抓取，
   用法：docker exec scraper python tools/extract_fingerprint.py

依賴：curl_cffi（TLS 指紋模擬，取代 cloudscraper + requests）
"""
import json
import logging
import random
from pathlib import Path
from typing import Dict, List, Optional

from curl_cffi.requests import Session
from utils.request_utils import human_sleep

logger = logging.getLogger(__name__)

# ── impersonate 輪換池 ──
# 每個 impersonate 目標 = 一致的 TLS 指紋 + User-Agent + HTTP/2 行為
# curl_cffi 會自動設定對應的 User-Agent，不需手動指定
#
# 注意：Sec-CH-UA 只有 Chromium 系瀏覽器會送（Chrome/Edge），
#       Firefox / Safari 不送 Sec-CH-UA headers。
#       _build_page_headers / _build_xhr_headers 會根據當前 impersonate 自動判斷。

CHROMIUM_TARGETS = [
    "chrome124", "chrome131", "chrome136",
    "edge99", "edge101",
]
FIREFOX_TARGETS = [
    "firefox133", "firefox135", "firefox144",
]
SAFARI_TARGETS = [
    "safari17_0", "safari18_0",
]

# 預設池：Chrome 為主（最常見），混入 Firefox 和 Safari 增加多樣性
DEFAULT_IMPERSONATE_POOL: List[str] = CHROMIUM_TARGETS + FIREFOX_TARGETS + SAFARI_TARGETS

# ── 本地指紋庫 ──
# 由 tools/extract_fingerprint.py 從容器內真實瀏覽器抓取
FINGERPRINTS_FILE = Path(__file__).parent.parent / "tools" / "fingerprints.json"


def _load_local_fingerprints() -> List[dict]:
    """載入本地指紋庫（啟動時讀取一次）"""
    if not FINGERPRINTS_FILE.exists():
        return []
    try:
        data = json.loads(FINGERPRINTS_FILE.read_text(encoding="utf-8"))
        valid = [fp for fp in data if fp.get("ja3")]
        if valid:
            logger.info("已載入 %d 筆本地指紋: %s", len(valid), [fp["name"] for fp in valid])
        return valid
    except Exception as e:
        logger.warning("載入本地指紋庫失敗: %s", e)
        return []


LOCAL_FINGERPRINTS: List[dict] = _load_local_fingerprints()

# Sec-CH-UA 對照表（只有 Chromium 系需要）
_SEC_CH_UA_MAP = {
    "chrome124": '"Chromium";v="124", "Not;A=Brand";v="24", "Google Chrome";v="124"',
    "chrome131": '"Chromium";v="131", "Not;A=Brand";v="24", "Google Chrome";v="131"',
    "chrome136": '"Chromium";v="136", "Not;A=Brand";v="24", "Google Chrome";v="136"',
    "edge99":    '"Chromium";v="99", "Not;A=Brand";v="24", "Microsoft Edge";v="99"',
    "edge101":   '"Chromium";v="101", "Not;A=Brand";v="24", "Microsoft Edge";v="101"',
}


def _is_chromium(target: str) -> bool:
    """判斷 impersonate 目標是否為 Chromium 系（Chrome/Edge）"""
    return target.startswith("chrome") or target.startswith("edge")


class BaseScraperClient:
    """
    反爬 HTTP client 基底類別。

    功能：
    - curl_cffi session 建立（含 TLS 指紋模擬 + 自動輪換）
    - 頁面請求 headers（navigate 模式）
    - XHR/AJAX 請求 headers（cors 模式）
    - User-Agent 由 curl_cffi impersonate 自動管理，不手動設定

    子類別用法：
        class MyScraperService(BaseScraperClient):
            IMPERSONATE_POOL = ["chrome136"]  # 可選覆寫，限定特定瀏覽器
            TIMEOUT = 20                      # 可選覆寫

            def __init__(self, ...):
                super().__init__()
                ...
    """

    # ── 子類別可覆寫的類別屬性 ──
    IMPERSONATE_POOL: List[str] = DEFAULT_IMPERSONATE_POOL
    TIMEOUT: int = 20

    def __init__(self):
        # 當前選中的指紋（impersonate 名稱或本地指紋 dict）
        self._current_impersonate: str = ""
        self._current_local_fp: Optional[dict] = None
        self._rotate_impersonate()

    @property
    def IMPERSONATE(self) -> str:
        """當前使用的 impersonate 目標名稱"""
        return self._current_impersonate

    def _rotate_impersonate(self):
        """
        輪換到下一個隨機指紋（建立新 session 時呼叫）。

        指紋來源有兩層：
        1. curl_cffi 內建 impersonate 池
        2. 本地指紋庫（tools/fingerprints.json）
        本地指紋以 1/3 的機率被選中（增加多樣性但不喧賓奪主）。
        """
        use_local = LOCAL_FINGERPRINTS and random.random() < 0.3
        if use_local:
            self._current_local_fp = random.choice(LOCAL_FINGERPRINTS)
            self._current_impersonate = self._current_local_fp["name"]
        else:
            self._current_local_fp = None
            self._current_impersonate = random.choice(self.IMPERSONATE_POOL)

    # ── Session 建立 ──

    def _build_session(self) -> Session:
        """
        建立 curl_cffi Session（含 TLS 指紋模擬）。
        每次建立新 session 時自動輪換 impersonate 目標。

        如果選到本地指紋，使用 ja3 + akamai 自訂指紋；
        否則使用 curl_cffi 內建 impersonate。
        """
        self._rotate_impersonate()

        if self._current_local_fp:
            # 使用本地抓取的真實瀏覽器指紋
            logger.info("建立 session: 本地指紋 %s (ja3_hash=%s)",
                        self._current_impersonate, self._current_local_fp.get("ja3_hash", "?"))
            return Session(
                ja3=self._current_local_fp["ja3"],
                akamai=self._current_local_fp.get("akamai", ""),
                headers={"User-Agent": self._current_local_fp.get("user_agent", "")},
            )
        else:
            logger.info("建立 session: impersonate %s", self._current_impersonate)
            return Session(impersonate=self._current_impersonate)

    # ── Headers 建構 ──

    def _build_page_headers(self, referer: Optional[str] = None) -> Dict[str, str]:
        """
        一般頁面請求 headers（模擬瀏覽器直接導航）。

        Sec-CH-UA headers 只在 Chromium 系瀏覽器加入；
        Firefox / Safari 不送這些 headers（符合真實瀏覽器行為）。
        User-Agent 不手動設定，由 curl_cffi impersonate 自動處理。
        """
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        }

        # Chromium 系加入 Sec-CH-UA headers
        if _is_chromium(self._current_impersonate):
            sec_ch_ua = _SEC_CH_UA_MAP.get(self._current_impersonate)
            if sec_ch_ua:
                headers["Sec-CH-UA"] = sec_ch_ua
            headers["Sec-CH-UA-Mobile"] = "?0"
            headers["Sec-CH-UA-Platform"] = '"Linux"'

        if referer:
            headers["Referer"] = referer
            # 有 referer 代表是從站內連結跳轉，Sec-Fetch-Site 改為 same-origin
            headers["Sec-Fetch-Site"] = "same-origin"
        return headers

    def _build_xhr_headers(self, referer: str, origin: Optional[str] = None) -> Dict[str, str]:
        """
        AJAX/XHR 請求 headers（模擬 JavaScript fetch/XMLHttpRequest）。

        對應瀏覽器行為：頁面上的 JS 發出 AJAX 請求載入更多內容。
        User-Agent 不手動設定，由 curl_cffi impersonate 自動處理。
        """
        # 自動從 referer 推斷 origin
        if origin is None:
            from urllib.parse import urlparse
            parsed = urlparse(referer)
            origin = f"{parsed.scheme}://{parsed.netloc}"

        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": origin,
            "Referer": referer,
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        }

        # Chromium 系加入 Sec-CH-UA headers
        if _is_chromium(self._current_impersonate):
            sec_ch_ua = _SEC_CH_UA_MAP.get(self._current_impersonate)
            if sec_ch_ua:
                headers["Sec-CH-UA"] = sec_ch_ua
            headers["Sec-CH-UA-Mobile"] = "?0"
            headers["Sec-CH-UA-Platform"] = '"Linux"'

        return headers

    # ── 共用 fetch + retry ──

    def _fetch_with_retry(
        self,
        session: Session,
        url: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        cookies: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
        max_retries: int = 3,
        source_name: str = "Scraper",
    ) -> "curl_cffi.requests.Response":
        """
        共用的 GET + retry 邏輯。

        失敗時以指數退避重試，重試耗盡拋出 RuntimeError。
        回傳 curl_cffi Response 物件（API 與 requests.Response 相容）。
        """
        if headers is None:
            headers = self._build_page_headers()
        if timeout is None:
            timeout = self.TIMEOUT

        last_error: Exception | None = None
        for attempt in range(1, max_retries + 1):
            try:
                resp = session.get(
                    url,
                    headers=headers,
                    cookies=cookies,
                    timeout=timeout,
                )
                return resp
            except Exception as e:
                last_error = e
                logger.warning(
                    "%s 請求失敗（attempt=%s/%s）: url=%s err=%s",
                    source_name, attempt, max_retries, url, e,
                )
                if attempt < max_retries:
                    human_sleep(1.0 * attempt, 1.5 * attempt)

        raise RuntimeError(
            f"{source_name} 抓取失敗（重試耗盡）: {url} err={last_error}"
        )
