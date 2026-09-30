"""
反爬 HTTP client 基底類別

提供共用的 session 管理、TLS 指紋模擬、headers 建構、retry 邏輯。
子類別（BahamutScraperService、PTTScraperService 等）繼承後可直接使用，
或覆寫個別方法做來源專屬調整。

指紋來源（兩層，每建一個 session 隨機選一次；都是 Firefox 系，理由見下方輪換池）：
1. curl_cffi 內建 impersonate 池（Firefox）— 70% 機率
2. 本地指紋庫 tools/fingerprints.json — 30% 機率
   由 extract_fingerprint.py 手動從容器內 Firefox ESR 抓取，
   用法：docker exec scraper python tools/extract_fingerprint.py

一輪抓取請包在 run_session() 裡：整輪同一個瀏覽器、cookie 延續。

依賴：curl_cffi（TLS 指紋模擬，取代 cloudscraper + requests）
"""
import json
import logging
import random
from contextlib import contextmanager, nullcontext
from pathlib import Path
from typing import Dict, List, Optional

from curl_cffi.requests import Session
from utils.request_utils import human_sleep

logger = logging.getLogger(__name__)

# ── impersonate 輪換池 ──
# 每個 impersonate 目標 = 一致的 TLS 指紋 + User-Agent + HTTP/2 行為 + Sec-CH-UA 系列標頭，
# 全部由 curl_cffi 依目標自動送出。我們刻意不自己寫 Sec-CH-UA／Platform／Mobile：
# 以前手寫的版本平台一律報 "Linux"，但 Chrome 目標的 UA 是 macOS、Edge 是 Windows，
# 送出去就是「UA 說 Mac、平台說 Linux」這種真瀏覽器不會有的矛盾，還蓋掉了 curl_cffi 內建的正確值。
#
# 只用 Firefox 系：2026-10-01 逐站實測，HKEPC 的 Cloudflare 對 curl_cffi 模擬的 Chrome（124～150）
# 與 Safari（18／26）一律給挑戰頁（403「Just a moment...」，跟我們送什麼標頭無關），
# Firefox（133／144／147）與本機抓的 Firefox ESR 指紋全部通過；巴哈、PTT、官網 JSON 則每一種都通過。
# 所有網站都過的只有 Firefox 系；一個 IP 固定用同一種瀏覽器，也比每次換一種更像真人。
# 以前 HKEPC 的 403 時有時無，就是隨機抽到 Chrome／Safari 的那幾頁被擋。
# 要加回其他瀏覽器或換版本，先用同樣方式逐站實測（見 AI_HANDOFF「scraper 抓網頁機制檢查」）。
FIREFOX_TARGETS = ["firefox144", "firefox147"]

try:
    # curl_cffi 原始碼把 BrowserType 標成「1.x 會移除」，而 requirements 沒鎖版本：拿不到清單就不過濾，
    # 不能讓這道防呆本身變成 import 失敗、整個 scraper（含給 bot 用的 API）起不來。
    from curl_cffi.requests import BrowserType
    _SUPPORTED_TARGETS: Optional[set] = {b.value for b in BrowserType}
except Exception:
    _SUPPORTED_TARGETS = None


def _supported_only(targets: List[str], supported: Optional[set] = _SUPPORTED_TARGETS) -> List[str]:
    """剔除目前安裝的 curl_cffi 不認得的目標。

    requirements 沒鎖版本，重建映像可能換成不認得某個目標的版本；照樣拿去建 session，
    每個請求都會失敗。寧可少幾個選擇、記一筆警告；全都不認得時退回 curl_cffi 的 "firefox"
    別名（它永遠指向該版本支援的最新 Firefox）。拿不到支援清單時原樣回傳。
    """
    if supported is None:
        return list(targets)
    kept = [t for t in targets if t in supported]
    dropped = [t for t in targets if t not in supported]
    if dropped:
        logger.warning("目前的 curl_cffi 不支援這些 impersonate 目標，已略過: %s", dropped)
    return kept or ["firefox"]


DEFAULT_IMPERSONATE_POOL: List[str] = _supported_only(FIREFOX_TARGETS)

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
            IMPERSONATE_POOL = ["firefox147"]  # 可選覆寫，限定特定瀏覽器（先逐站實測）
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
        self._run_session: Optional[Session] = None
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

    @contextmanager
    def run_session(self):
        """整輪共用一個 session：同一個瀏覽器指紋、cookie 一路延續，離開區塊才關。

        以前多數爬蟲每個請求都開新 session（每次重選瀏覽器、cookie 從零開始），
        同一個 IP 幾秒內就換一種瀏覽器，真的讀者不會這樣。區塊裡的 _build_session()
        都回傳這一個，而且呼叫端的 `with` 不會把它關掉；巢狀呼叫沿用外層那一個。
        """
        if self._run_session is not None:
            yield self._run_session
            return
        session = self._new_session()
        self._run_session = session
        try:
            yield session
        finally:
            self._run_session = None
            session.close()

    def _build_session(self):
        """給 `with self._build_session() as session:` 用。

        在 run_session() 區塊裡：回傳本輪共用的 session（包成離開 with 也不關閉）；
        區塊外：建一個新的（沿用舊行為，with 結束就關）。
        """
        if self._run_session is not None:
            return nullcontext(self._run_session)
        return self._new_session()

    def _new_session(self) -> Session:
        """
        建立 curl_cffi Session（含 TLS 指紋模擬），每次都重新隨機選一個指紋。

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

        User-Agent 與 Sec-CH-UA 系列不在這裡設定，由 curl_cffi impersonate 依目標送出
        （Firefox / Safari 目標本來就不送 Sec-CH-UA，符合真實瀏覽器行為）。
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

        if referer:
            headers["Referer"] = referer
            # 有 referer 代表是從站內連結跳轉，Sec-Fetch-Site 改為 same-origin
            headers["Sec-Fetch-Site"] = "same-origin"
        return headers

    def _build_xhr_headers(self, referer: str, origin: Optional[str] = None) -> Dict[str, str]:
        """
        AJAX/XHR 請求 headers（模擬 JavaScript fetch/XMLHttpRequest）。

        對應瀏覽器行為：頁面上的 JS 發出 AJAX 請求載入更多內容。
        User-Agent 與 Sec-CH-UA 系列不在這裡設定，由 curl_cffi impersonate 依目標送出。
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
