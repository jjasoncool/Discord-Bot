#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Facebook Scraper Service
Facebook 貼文抓取服務類別，支持模組調用和獨立執行

- 文字擷取：先展開「查看更多」，抓取 message 區塊的 innerHTML，
  用 BS4 將 <a> 的顯示文字改寫為完整 href（解碼 &amp;，解開 l.php link shim），
  再輸出純文字，避免「……」截斷網址。
- 圖片擷取：濾掉 data:image 與 svg 佔位圖，避免混入 UI/placeholder。
- 保留：你新增的資料目錄、持續寫入 JSON（去重並排序）、config 讀取等功能。

- 新增：
  1) hashtag 多個支援，並在 JSON 另輸出 text_md（Discord 可直接點的 Markdown 超連結）。
  2) 由貼文小圖追到「照片頁」，從 og:image 擷取大圖 URL（images 只回大圖）。
  3) **分頁管理精簡版**：每次開始抓「新的一篇」貼文前，先關閉主分頁以外的所有分頁。

  4) content_hash（唯一）：以 clean_text(text) + 規範化後 images 路徑（去 query/fragment）做 SHA256，
     作為內容唯一特徵。
  5) 去重決策集中在 _save_fb_posts_to_json：**只看 content_hash**，合併時僅「補空白欄位」、文字取較長、圖片取較多。
  6) URL 欄位策略固定：`url` 儲存「傳統數字型」連結；`pfbid_url` 儲存 `/posts/pfbid...`。
  7) collect_first_n_links 階段即正規化（www + 去 tracking）；同時 logs/fb_url_list.txt 持續累積、不重複。
  8) JSON 做出 insert/update/noop 決策的同時，同步生成 DB ops 並一次性套用到 DB。
  9) debug_mode=True 時才落地 page_source_*.html 與 test_fb_results_*.json。

  10) **時間戳修正（本版）**：
      使用 `python-dateutil` 解析，支援：
        - <meta property="article:published_time">
        - <abbr data-utime>（epoch 秒）
        - <time datetime>
        - 新 Comet 介面：時間連結上的 aria-label / title / data-tooltip-content / data-store（hover 後 tooltip）
      中文（上午/下午/中午/晚上、年/月/日、星期）會先正規化再交給 dateutil。
      若沒有時區資訊，採用 config["timezone"]（預設 Asia/Taipei）視為本地時間再轉 UTC ISO。

  11) **本版新增（強化 timestamp 擷取）**：
      A. 在 extract_timestamp 最前面，直接從 `page_source` 以 regex 抓取嵌入 JSON 的
         `"creation_time":<epoch>` 或 `"publish_time":<epoch>`（Comet SSR 會提供）；
         例如你提供的頁面有：
         - `"post_context":{"object_fbtype":266,"publish_time":1761908406,...}`（tracking JSON） :contentReference[oaicite:3]{index=3}
         - `"timestamp":{"...","story":{"creation_time":1761908406,...}}`（同頁） :contentReference[oaicite:4]{index=4}
      B. 若全數失敗，再嘗試解析「相對時間」（如 `2天`、`3小時`、`剛剛` 等）轉為絕對時間。
      C. 同步在寫入資料庫前，把 JSON 中的 `timestamp`（ISO/UTC）轉為 SQLite DATETIME（`YYYY-MM-DD HH:MM:SS`，以本地時區表示）。
"""

import os
import unicodedata, re
import time
import json
import random
import html as ihtml
import hashlib
import copy  # 本版新增：為了不改動寫回 JSON 的內容，DB 同步時複製 ops
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Tuple
from urllib.parse import urlparse, parse_qs, urlunparse, urlencode, urljoin, unquote

# === 依賴 ===
try:
    from selenium import webdriver
    from selenium.webdriver.firefox.options import Options as FirefoxOptions
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import (
        TimeoutException, NoSuchElementException, StaleElementReferenceException,
        ElementClickInterceptedException, ElementNotInteractableException, NoSuchWindowException
    )
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    print("警告: Selenium 未安裝，將無法執行抓取功能")

import sys

# 確保可以匯入 scraper 模組
scraper_path = os.path.dirname(os.path.dirname(__file__))
if scraper_path not in sys.path:
    sys.path.insert(0, scraper_path)

from config import FACEBOOK_CONFIG, FEATURES  # 依你的環境提供

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False
    print("警告: BeautifulSoup4 未安裝，將無法解析 HTML")

try:
    from utils.logger import get_logger
    logger_available = True
except ImportError:
    logger_available = False
    print("警告: 無法載入 logger，將使用標準輸出")

# DB
try:
    from db.database import DatabaseManager
    from db.models import get_db_session
    db_available = True
except ImportError:
    db_available = False
    print("警告: 無法載入資料庫模組，將只儲存到 JSON")

# === python-dateutil ===
try:
    from dateutil import parser as duparser
    from dateutil.tz import gettz
except Exception as _e:
    raise ImportError("本版需要 python-dateutil，請先安裝：pip install python-dateutil") from _e

# ==================== 全域可調整常數 ====================
IMAGE_LIMIT = 20          # ← 這裡改數字即可！建議 20~30
# =========================================================

class FBScraperService:
    """
    Facebook 貼文抓取服務

    使用方式:
        # 作為模組調用
        service = FBScraperService()
        posts = service.scrape_facebook_posts()

        # 獨立執行進行測試
        python fb_scraper_service.py
    """

    def __init__(self):
        """初始化 FB 抓取服務"""
        self.config = FACEBOOK_CONFIG.copy()
        self.logger = self._get_logger()

        # 確保依賴可用
        if not SELENIUM_AVAILABLE:
            raise ImportError("Selenium 未安裝，無法使用 FB 抓取服務")

        # 環境與資料夾
        is_docker = self._is_in_docker()
        self.config["html_log_dir"] = "/logs" if is_docker else "./logs"
        self.config["data_dir"]     = "/app/data" if is_docker else "./data"

        # 計算最大 HTML 檔案數量 (max_scraping_sessions × max_links)
        max_scraping_sessions = self.config.get("max_scraping_sessions", 3)
        max_links = self.config.get("max_links", 3)
        self.config["max_html_files"] = max_scraping_sessions * max_links

        # 建立必要目錄
        os.makedirs(self.config["html_log_dir"], exist_ok=True)
        os.makedirs(self.config["data_dir"], exist_ok=True)

        # 常數定義
        self.SEE_MORE_KEYWORDS = ["see more", "查看更多", "顯示更多", "更多內容", "顯示更多內容", "更多", "看更多"]
        self.COMMENT_WORDS     = ["comment", "comments", "留言", "回應", "回覆", "replies"]
        self.MESSAGE_SELECTORS = "[data-ad-comet-preview='message'], [data-ad-preview='message']"

        # 應排除的 UI/互動/翻譯等文字（整行出現時）
        self.UI_EXCLUDE_RE = re.compile(
            r"^(所有心情|讚|留言|回覆|分享|最相關|追蹤|傳送|See translation|查看翻譯|收合翻譯|See less|顯示較少|全部留言|新增留言|\d+\s*(則)?(留言|回覆|分享))$"
        )
        self.TEXT_MAX_LEN = 8000
        self.config["image_limit"] = IMAGE_LIMIT

        # 由外部 scheduler 讀取的本輪狀態
        self.last_empty_link_failure = False

        # 主分頁 handle（啟動後會記錄）
        self.main_handle: Optional[str] = None

        # 時區設定（供 dateutil 解析無時區字串時使用）
        self.timezone_str = self.config.get("timezone", "Asia/Taipei")
        self.tzinfo = gettz(self.timezone_str) or gettz("UTC")

    # ---------------- 基本工具 ----------------
    def _is_in_docker(self) -> bool:
        """檢查是否在 Docker 環境中"""
        if os.path.exists('/.dockerenv'):
            return True
        try:
            with open('/proc/1/cgroup', 'r') as f:
                if 'docker' in f.read():
                    return True
        except Exception:
            pass
        return False

    def _get_logger(self):
        """獲取 logger 實例"""
        if logger_available:
            return get_logger('fb_scraper')
        else:
            class SimpleLogger:
                def info(self, msg): print(f"[INFO] {msg}")
                def error(self, msg): print(f"[ERROR] {msg}")
                def warning(self, msg): print(f"[WARNING] {msg}")
            return SimpleLogger()

    # ---------- 人類式行為 & Driver ----------
    def human_sleep(self, a=None, b=None):
        """模擬人類隨機延遲"""
        if a is None or b is None:
            a, b = self.config.get("human_delay_min", (0.35, 0.9))
        time.sleep(random.uniform(a, b))

    def human_move_and_scroll(self, driver):
        """模擬人類移動和捲動行為"""
        self.human_sleep()
        try:
            ActionChains(driver).move_by_offset(
                random.randint(-40, 40),
                random.randint(-40, 40)
            ).perform()
        except Exception:
            pass
        driver.execute_script(f"window.scrollBy(0, {random.randint(60, 220)});")
        self.human_sleep(0.25, 0.6)

    def wait_page_loaded(self, driver, timeout=10):
        """等待頁面載入完成（以 img src 穩定度為 proxy）"""
        end_time = time.time() + timeout
        last_srcs = set()
        while time.time() < end_time:
            try:
                imgs = driver.find_elements(By.CSS_SELECTOR, "img[src]")
                current_srcs = set(
                    im.get_attribute("src") or ""
                    for im in imgs
                    if im.get_attribute("src") and not im.get_attribute("src").startswith("data:")
                )
                if current_srcs == last_srcs:
                    return True
                last_srcs = current_srcs
                time.sleep(0.5)
            except Exception:
                pass
        return True

    def setup_driver(self):
        """設定瀏覽器驅動"""
        opts = FirefoxOptions()
        env_firefox = os.path.join(sys.prefix, 'bin', 'firefox')
        if os.path.exists(env_firefox):
            opts.binary_location = env_firefox
        if self.config.get("headless"):
            opts.add_argument("--headless")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--window-size=1920,1080")
        opts.add_argument("--private")
        opts.add_argument("--lang=zh-TW")
        opts.set_preference("intl.accept_languages", "zh-TW,zh,en-US,en")
        ua = "Mozilla/5.0 (X11; Linux x86_64) Gecko/20100101 Firefox/120.0"
        opts.set_preference("general.useragent.override", ua)
        opts.set_preference("dom.webdriver.enabled", False)
        driver = webdriver.Firefox(options=opts)
        return driver

    def safe_click(self, driver, elem, retries=2):
        """安全點擊元素"""
        for _ in range(retries):
            try:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", elem)
                self.human_sleep(0.15, 0.35)
                try:
                    ActionChains(driver).move_to_element(elem).pause(0.2).click().perform()
                except (ElementClickInterceptedException, ElementNotInteractableException):
                    driver.execute_script("arguments[0].click();", elem)
                return True
            except StaleElementReferenceException:
                self.human_sleep(0.2, 0.4)
            except Exception:
                self.human_sleep(0.2, 0.4)
        try:
            driver.execute_script(
                "arguments[0].dispatchEvent(new MouseEvent('click', {bubbles:true,cancelable:true}));",
                elem
            )
            return True
        except Exception:
            return False

    def close_login_wall(self, driver):
        """關閉登入牆/彈窗（能關則關，不阻塞）"""
        selectors = [
            'div[role="dialog"] [aria-label="關閉"]',
            'div[role="dialog"] [aria-label="Close"]',
            'div[role="dialog"] button[aria-label*="close" i]',
            'div[role="dialog"] button[aria-label*="Close" i]',
            'div[aria-label*="登入"] [aria-label="關閉"]',
            '[aria-label="Close this dialog"]',
            'div[aria-label*="Log in to see more"] button[aria-label="Close"]',
            'div[role="button"][aria-label="Close"]',
            'button[data-testid*="close"]',
        ]
        closed = False
        for sel in selectors:
            try:
                buttons = driver.find_elements(By.CSS_SELECTOR, sel)
                for btn in buttons:
                    if btn.is_displayed() and btn.is_enabled():
                        if self.safe_click(driver, btn):
                            self.logger.info("關閉登入牆/對話框")
                            closed = True
                            self.human_sleep(0.4, 0.8)
                            break
                if closed:
                    break
            except Exception:
                continue
        return closed

    # ---------- 分頁管理（極簡清理） ----------
    def ensure_only_main_tab(self, driver):
        """
        僅保留主分頁：
        - 主分頁以「初次進入粉專首頁時的 handle」為準。
        - 每次抓下一篇前呼叫，直接關閉其餘所有分頁，避免累積造成錯誤或記憶體爆量。
        """
        try:
            handles = driver.window_handles
        except NoSuchWindowException:
            return
        if not handles:
            return
        # 主分頁若尚未記錄或不存在，就以第一個 handle 當主分頁
        if not self.main_handle or self.main_handle not in handles:
            self.main_handle = handles[0]
        # 切回主分頁
        try:
            driver.switch_to.window(self.main_handle)
        except Exception:
            self.main_handle = handles[0]
            try:
                driver.switch_to.window(self.main_handle)
            except Exception:
                pass
        # 關閉其他分頁
        for h in list(handles):
            if h == self.main_handle:
                continue
            try:
                driver.switch_to.window(h)
                driver.close()
            except Exception:
                pass
        # 切回主分頁
        try:
            driver.switch_to.window(self.main_handle)
        except Exception:
            pass

    def open_in_new_tab(self, driver, url) -> Optional[str]:
        """
        **極簡開新分頁**：不做額外判斷；回傳新分頁 handle；失敗回 None。
        """
        try:
            try:
                driver.switch_to.new_window('tab')
            except Exception:
                before = set(driver.window_handles)
                driver.execute_script("window.open('about:blank','_blank');")
                WebDriverWait(driver, 5).until(lambda d: len(d.window_handles) > len(before))
                after = set(driver.window_handles)
                new_h = (after - before).pop()
                driver.switch_to.window(new_h)
            driver.get(url)
            self.wait_page_loaded(driver)
            return driver.current_window_handle
        except Exception as e:
            self.logger.error(f"開新分頁失敗：{e}")
            return None

    # ---------- 連結蒐集（主頁面） ----------
    def extract_links_via_dom(self, driver):
        """通過 DOM 提取貼文詳情連結"""
        script = """
        const anchorsInArticles = Array.from(document.querySelectorAll(
          "article a[href], [role='article'] a[href], div.story_body_container a[href]"
        ));
        const anchorsAll = Array.from(document.querySelectorAll("a[href]"));
        const cand = [...anchorsInArticles, ...anchorsAll];
        const hrefs = [];
        for (const a of cand) {
          const h = a.getAttribute('href') || '';
          if (!h) continue;
          let url = h;
          try { url = new URL(h, location.href).toString(); } catch(e){}
          if (url.includes("/story.php") || url.includes("/posts/") || url.includes("/permalink/")) {
            if (url.includes("comment_id=") || url.includes("reply_comment_id=") || url.includes("comment_tracking")) continue;
            if (url.includes("notif_id=") || url.includes("refid=")) continue;
            hrefs.push(url);
          }
        }
        const seen = new Set();
        const uniq = [];
        for (const u of hrefs) { if (!seen.has(u)) { seen.add(u); uniq.push(u); } }
        return uniq.slice(0, 20);
        """
        try:
            return driver.execute_script(script) or []
        except Exception:
            return []

    def extract_links_via_pagesource(self, driver):
        """通過頁面原始碼提取貼文詳情連結（備援）"""
        html = driver.page_source or ""
        pats = [
            r'https://m\\.facebook\\.com/story\\.php\\?[^"\\\']+',
            r'https://m\\.facebook\\.com/[^"\\\']+/posts/[^"\\\']+',
            r'https://m\\.facebook\\.com/[^"\\\']+/permalink/[^"\\\']+',
        ]
        hrefs = []
        for pat in pats:
            for m in re.findall(pat, html):
                if any(bad in m for bad in ["comment_id=", "reply_comment_id=", "comment_tracking", "notif_id="]):
                    continue
                hrefs.append(m)
        seen, uniq = set(), []
        for u in hrefs:
            if u not in seen:
                seen.add(u)
                uniq.append(u)
        return uniq[:20]

    def collect_first_n_links(self, driver, n=None, scroll_rounds=None):
        """
        收集前 n 個貼文詳情連結（**收集完成後立即做 URL 正規化與落地 fb_url_list**）
        """
        if n is None:
            n = self.config.get("max_links", 3)
        if scroll_rounds is None:
            scroll_rounds = self.config.get("scroll_rounds", 6)

        links, seen = [], set()
        for round_idx in range(1, scroll_rounds + 1):
            if len(links) >= n:
                break
            self.logger.info(f"收集連結（第 {round_idx}/{scroll_rounds} 輪）...")
            self.close_login_wall(driver)
            hrefs = self.extract_links_via_dom(driver) or self.extract_links_via_pagesource(driver)
            for h in hrefs:
                if h in seen:
                    continue
                seen.add(h)
                links.append(h)
                if len(links) >= n:
                    break
            if len(links) >= n:
                break
            self.human_sleep(1.5, 3.0)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            self.human_move_and_scroll(driver)

        canon_links = [self.normalize_fb_url_for_storage(u) for u in links[:n]]
        self._append_fb_url_list(canon_links)

        self.logger.info(f"取得貼文連結數量：{len(canon_links)}")
        for i, u in enumerate(canon_links, 1):
            self.logger.info(f"  #{i}: {u}")
        return canon_links

    # ---------- 詳情頁擷取 ----------
    def node_in_comments(self, driver, node) -> bool:
        """判斷節點是否在留言區"""
        try:
            return driver.execute_script("""
                function inComments(el){
                    const SELS = [
                      "*[id*='comments' i]", "*[class*='comments' i]",
                      "*[class*='comment' i]", "*[id*='ufi' i]",
                      "*[aria-label*='comment' i]", "*[aria-label*='comments' i]",
                      "*[aria-label*='留言']", "*[aria-label*='回覆']"
                    ];
                    while (el && el !== document.body){
                        for (const s of SELS){
                            try { if (el.matches && el.matches(s)) return true; } catch(e){}
                        }
                        el = el.parentElement;
                    }
                    return false;
                }
                return inComments(arguments[0]);
            """, node)
        except Exception:
            return False

    def expand_see_more_in_scope(self, driver, scope):
        """展開查看更多連結（僅限貼文本體區域）"""
        clicked = 0
        try:
            btns = scope.find_elements(By.CSS_SELECTOR, "[role='button'][aria-label]")
            for b in btns:
                if not b.is_displayed():
                    continue
                label = (b.get_attribute("aria-label") or "").strip().lower()
                if any(k in label for k in self.SEE_MORE_KEYWORDS):
                    if self.node_in_comments(driver, b):
                        continue
                    if self.safe_click(driver, b):
                        clicked += 1
                        self.human_sleep(0.35, 0.7)
        except Exception:
            pass
        try:
            text_btns = scope.find_elements(By.XPATH,
                ".//*[contains(translate(normalize-space(.), 'SEE MORE查看更多顯示更多更多內容看更多', 'see more查看更多顯示更多更多內容看更多'),'see more') "
                "or contains(normalize-space(.), '查看更多') or contains(normalize-space(.), '顯示更多') "
                "or contains(normalize-space(.), '更多內容') or normalize-space(.)='更多' or normalize-space(.)='看更多']"
            )
            for b in text_btns:
                if not b.is_displayed():
                    continue
                if self.node_in_comments(driver, b):
                    continue
                if self.safe_click(driver, b):
                    clicked += 1
                    self.human_sleep(0.35, 0.7)
        except Exception:
            pass
        if clicked:
            self.logger.info(f"展開查看更多：{clicked} 次")
        return clicked

    def get_post_root(self, driver):
        """取得貼文主體元素（保守：可退回 body 以涵蓋附件區）"""
        roots = driver.find_elements(By.CSS_SELECTOR, "article, [role='article']")
        for r in roots:
            if r.is_displayed():
                return r
        for sel in ["div#MPhotoContent", "div.story_body_container", "div[data-ft]"]:
            try:
                r = driver.find_element(By.CSS_SELECTOR, sel)
                if r.is_displayed():
                    return r
            except Exception:
                continue
        try:
            return driver.find_element(By.TAG_NAME, "body")
        except Exception:
            return None

    # ---------- URL 正規化 ----------
    def normalize_fb_url_for_storage(self, url: str) -> str:
        """
        存檔用 canonical FB 連結（www）：
        - 網域一律 www.facebook.com
        - 移除追蹤參數，但保留辨識所需（story.php 需 story_fbid/id；photo 需 fbid/set）
        - /posts/NNN、/posts/pfbid...、/permalink/NNN 直接去掉 query/fragment
        """
        s = (url or "").strip()
        if not s:
            return s
        try:
            p = urlparse(ihtml.unescape(s))
        except Exception:
            return s

        if "facebook.com" not in p.netloc:
            return urlunparse((p.scheme or "https", p.netloc, p.path.rstrip("/"), "", p.query, ""))

        netloc = "www.facebook.com"
        path = p.path
        q = parse_qs(p.query)
        new_q = {}

        if path.startswith("/story.php"):
            for k in ("story_fbid", "id"):
                if k in q and q[k]:
                    new_q[k] = q[k]
        elif path.startswith("/photo") or path.startswith("/photo.php"):
            for k in ("fbid", "set", "type"):
                if k in q and q[k]:
                    new_q[k] = q[k]
        else:
            new_q = {}

        return urlunparse((p.scheme or "https", netloc, path.rstrip("/"), "", urlencode(new_q, doseq=True), ""))

    def normalize_fb_url_for_nav(self, url: str) -> str:
        """
        瀏覽器導航用：為了降低登入牆，偏好 m.facebook.com（仅轉 FB 網域）
        """
        try:
            p = urlparse(ihtml.unescape(url.strip()))
        except Exception:
            return url.strip()
        if "facebook.com" not in p.netloc:
            return url.strip()
        netloc = "m.facebook.com"
        return urlunparse((p.scheme or "https", netloc, p.path, "", p.query, ""))

    def _resolve_href(self, href: str, base_url: str) -> str:
        """將錨點 href 轉為完整可點網址：解碼 &amp;、解開 l.php、補全相對位址。"""
        if not href:
            return ""
        href = ihtml.unescape(href.strip())
        try:
            abs_url = urljoin(base_url, href)
        except Exception:
            abs_url = href
        try:
            p = urlparse(abs_url)
            if p.netloc.endswith("facebook.com") and p.path == "/l.php":
                q = parse_qs(p.query)
                if "u" in q and q["u"]:
                    abs_url = ihtml.unescape(unquote(q["u"][0]))
        except Exception:
            pass
        return abs_url

    # ---------- 內容雜湊與圖片正規化 ----------
    def _canonical_image(self, u: str) -> str:
        """移除 query/fragment，僅保留 scheme://host/path；但 Facebook CDN 圖片保留 query 以確保可訪問"""
        try:
            p = urlparse(u)
            if not p.scheme or not p.netloc:
                return u
            # 對於 Facebook CDN 圖片，保留 query parameters 以確保可訪問
            if 'fbcdn.net' in p.netloc and p.query:
                return urlunparse((p.scheme, p.netloc, p.path.rstrip("/"), "", p.query, ""))
            else:
                return urlunparse((p.scheme, p.netloc, p.path.rstrip("/"), "", "", ""))
        except Exception:
            return u

    def _get_image_dedup_key(self, u: str) -> str:
        """專門用於去重比較的 Key（強力移除 tracking）"""
        try:
            # 先用 canonical_image 做基礎正規化
            base = self._canonical_image(u)
            p = urlparse(base)
            if 'fbcdn.net' in p.netloc or 'scontent' in p.netloc:
                q = parse_qs(p.query)
                # 只保留真正重要的參數
                keep = {k: v for k, v in q.items() if k in ("fbid", "set", "type", "id", "eid", "pid")}
                query = urlencode(keep, doseq=True)
                return urlunparse((p.scheme, p.netloc, p.path.rstrip("/"), "", query, "")).lower()
            return base.lower()
        except Exception:
            return u.lower()

    def _get_photo_overlay_count(self, root) -> int:
        """從畫面上抓取 +XX 的實際數字（例如 +13 → 回傳 13）"""
        try:
            elems = root.find_elements(By.CSS_SELECTOR, "span, div")
            for e in elems:
                t = (e.text or "").strip()
                if match := re.fullmatch(r"\+(\d+)", t):
                    return int(match.group(1))
        except Exception:
            pass
        return 0   # 沒有找到就回 0

    def _dedup_image_list(self, images: List[str]) -> List[str]:
        """最簡單統一的圖片去重方法 - 保證最終輸出的 images 絕對無重複"""
        if not images:
            return []
        deduped = []
        seen = set()
        for img in images:
            if not img:
                continue
            key = self._get_image_dedup_key(img)
            if key not in seen:
                seen.add(key)
                deduped.append(self._canonical_image(img))  # 存完整可顯示 URL
        return deduped

    def _normalize_for_hash(self, s: str) -> str:
        if not s:
            return ""
        # 1) Unicode 正規化
        s = unicodedata.normalize("NFKC", s)
        # 2) 各式空白 → 普通空白；移除不可見字元
        trans = {
            0x00A0: 0x20, 0x202F: 0x20, 0x2009: 0x20, 0x2002: 0x20, 0x2003: 0x20,
            0x2004: 0x20, 0x2005: 0x20, 0x2006: 0x20, 0x2007: 0x20, 0x2008: 0x20,
        }
        s = s.translate(trans)
        s = s.translate({ord(c): None for c in "\u200b\u200d\u2060\ufeff"})
        # 3) 統一換行
        s = s.replace("\r\n", "\n").replace("\r", "\n")
        # 4) 壓縮空白（含行首空白）
        s = re.sub(r"[ \t]+", " ", s)
        s = re.sub(r"\n[ \t]+", "\n", s)
        s = re.sub(r"\n{3,}", "\n\n", s)
        # 5) 去頭尾、轉小寫
        return s.strip().lower()

    def _normalize_urls_in_text(self, text: str) -> str:
        """將文字中的 URL 替換成 canonical（去 query/fragment），並移除 hashtag，降低同文不同參數造成的差異"""
        if not text:
            return ""
        def repl(m):
            u = m.group(0)
            try:
                p = urlparse(u)
                return urlunparse((p.scheme or "https", p.netloc, p.path.rstrip("/"), "", "", ""))
            except Exception:
                return u
        out = re.sub(r'https?://[^\s)]+', repl, text, flags=re.IGNORECASE)
        # 移除 hashtag（因為不同抓取時 hashtag 連結可能不同）
        out = re.sub(r'#\w+', '', out)
        out = re.sub(r"[ \t]+", " ", out)
        out = re.sub(r"\n{3,}", "\n\n", out)
        return self._normalize_for_hash(out)

    def _build_content_hash(self, text: str, images: List[str]) -> str:
        """SHA256( normalize(text) ) - content_hash 只基於文章內容，不包含圖片"""
        t = self._normalize_urls_in_text(self.clean_text(text or ""))
        payload = t.encode("utf-8", errors="ignore")
        return hashlib.sha256(payload).hexdigest()

    # ---------- 文字抽取 ----------
    def _apply_hashtag_markdown(self, plain_text: str, hashtag_map: Dict[str, str]) -> str:
        if not hashtag_map:
            return plain_text
        out = plain_text
        for tag in sorted(hashtag_map.keys(), key=len, reverse=True):
            url = hashtag_map[tag]
            out = out.replace(tag, f"[{tag}]({url})")
        return out

    def _html_to_text_and_hashtags(self, html_fragment: str, base_url: str) -> Tuple[str, Dict[str, str]]:
        if not html_fragment:
            return "", {}
        if not BS4_AVAILABLE:
            txt = re.sub(r"<[^>]+>", "", html_fragment)
            return self.clean_text(ihtml.unescape(txt)), {}
        soup = BeautifulSoup(html_fragment, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        hashtag_map: Dict[str, str] = {}
        for a in soup.find_all("a"):
            href = a.get("href") or ""
            resolved = self._resolve_href(href, base_url)
            display = a.get_text() or ""
            is_hashtag = ("/hashtag/" in resolved) or display.strip().startswith("#")
            if is_hashtag:
                tag_text = display.strip() if display.strip().startswith("#") else f"#{display.strip()}"
                hashtag_map[tag_text] = resolved
                a.replace_with(tag_text)
            else:
                replacement = resolved.strip() if resolved else display
                a.replace_with(replacement)
        for br in soup.find_all("br"):
            br.replace_with("\n")
        text = soup.get_text(separator="\n")
        text = ihtml.unescape(text)
        text = self.clean_text(text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text, hashtag_map

    def _extract_from_message_scopes(self, driver, container) -> Tuple[str, Dict[str, str]]:
        scopes = []
        try:
            scopes = container.find_elements(By.CSS_SELECTOR, self.MESSAGE_SELECTORS)
        except Exception:
            scopes = []
        if not scopes:
            try:
                scopes = driver.find_elements(By.CSS_SELECTOR, self.MESSAGE_SELECTORS)
            except Exception:
                scopes = []

        out_candidates: List[Tuple[str, Dict[str, str]]] = []
        base_url = driver.current_url

        for sc in scopes:
            try:
                self.expand_see_more_in_scope(driver, sc)
            except Exception:
                pass
            try:
                html_fragment = sc.get_attribute("innerHTML") or ""
                plain, hmap = self._html_to_text_and_hashtags(html_fragment, base_url)
                plain = self.clean_text(plain)
                if plain and not self.UI_EXCLUDE_RE.match(plain):
                    out_candidates.append((plain, hmap))
            except Exception:
                continue

        if not out_candidates:
            try:
                js = """
                const sel = arguments[0];
                const kws = arguments[1];
                const el = document.querySelector(sel);
                if (!el) return "";
                el.querySelectorAll('[role="button"],a,span,div').forEach(b=>{
                    const t=(b.innerText||"").trim().toLowerCase();
                    if (kws.some(k=>t.includes(k))) { try{b.click();}catch(e){} }
                });
                return el.innerHTML || "";
                """
                html_fragment = driver.execute_script(
                    js, self.MESSAGE_SELECTORS, [k.lower() for k in self.SEE_MORE_KEYWORDS]
                ) or ""
                plain, hmap = self._html_to_text_and_hashtags(html_fragment, base_url)
                plain = self.clean_text(plain)
                if plain and not self.UI_EXCLUDE_RE.match(plain):
                    out_candidates.append((plain, hmap))
            except Exception:
                pass

        if not out_candidates:
            return "", {}

        # 保留你原本邏輯：取最長者
        best_plain, best_map = max(out_candidates, key=lambda x: len(x[0]))
        if len(best_plain) > self.TEXT_MAX_LEN:
            best_plain = best_plain[:self.TEXT_MAX_LEN]
        return best_plain, best_map

    def _extract_from_paragraphs(self, driver, scope) -> Tuple[str, Dict[str, str]]:
        try:
            self.expand_see_more_in_scope(driver, scope)
        except Exception:
            pass

        try:
            blocks = scope.find_elements(By.CSS_SELECTOR, "p, div[dir='auto'], span[dir='auto']")
        except Exception:
            blocks = []

        out, seen = [], set()
        base_url = driver.current_url
        hashtag_union: Dict[str, str] = {}

        for b in blocks:
            try:
                if not b.is_displayed() or self.node_in_comments(driver, b):
                    continue
                html_fragment = b.get_attribute("innerHTML") or ""
                t, hmap = self._html_to_text_and_hashtags(html_fragment, base_url)
                t = self.clean_text(t)
                if not t or self.UI_EXCLUDE_RE.match(t):
                    continue
                if t in seen:
                    continue
                seen.add(t)
                out.append(t)
                hashtag_union.update(hmap)
            except Exception:
                continue

        return ("\n\n".join(out).strip(), hashtag_union)

    def _extract_from_og(self, page_source: str) -> str:
        if not BS4_AVAILABLE:
            return ""
        try:
            soup = BeautifulSoup(page_source, "html.parser")
            og = soup.find("meta", attrs={"property": "og:description"})
            if og and og.get("content"):
                return self.clean_text(ihtml.unescape(og.get("content", "")))
        except Exception:
            pass
        return ""

    def extract_text_from_root(self, driver, root) -> Tuple[str, str]:
        """從根元素提取文字（含保存 page_source 以便除錯）；回傳：(text, text_md)"""
        self.logger.info("摘取文字中...")

        # 在 debug_mode 才落地 HTML
        if self.config.get("debug_mode", False):
            page_source = driver.page_source or ""
            filename = f"page_source_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            filepath = os.path.join(self.config["html_log_dir"], filename)
            self._cleanup_old_html_files()
            try:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(page_source)
                self.logger.info(f"頁面原始碼保存至：{filepath}")
            except Exception:
                pass

        # A. message 容器
        plain, hmap = self._extract_from_message_scopes(driver, root)
        if plain:
            text_md = self._apply_hashtag_markdown(plain, hmap)
            self.logger.info(f"直接自 message 容器取得文字（長度 {len(plain)}）")
            return plain[:self.TEXT_MAX_LEN], text_md[:self.TEXT_MAX_LEN]

        # B. 段落聚合
        candidates: List[Tuple[str, Dict[str, str]]] = []
        try:
            scopes = [root]
            try:
                extra = root.find_elements(By.CSS_SELECTOR, "[role='main'] article, [role='article']")
                scopes.extend([s for s in extra if s.is_displayed()])
            except Exception:
                pass
            for sc in scopes:
                t, hmap2 = self._extract_from_paragraphs(driver, sc)
                if t and len(t) >= 8:
                    candidates.append((t, hmap2))
        except Exception:
            pass

        if candidates:
            best_plain, best_map = max(candidates, key=lambda x: len(x[0]))
            text_md = self._apply_hashtag_markdown(best_plain, best_map)
            self.logger.info(f"段落聚合取得文字（長度 {len(best_plain)}）")
            return best_plain[:self.TEXT_MAX_LEN], text_md[:self.TEXT_MAX_LEN]

        # C. OG 備援
        page_source = driver.page_source or ""
        og = self._extract_from_og(page_source)
        if og:
            self.logger.info(f"從 og:description 備援取得文字（長度 {len(og)}）")
            return og[:self.TEXT_MAX_LEN], og[:self.TEXT_MAX_LEN]

        self.logger.warning("未取得文字（message/scopes/OG 都失敗）")
        return "", ""

    # ---------- 圖片擷取（含大圖） ----------
    def _nearest_anchor_href(self, driver, node) -> str:
        try:
            return driver.execute_script("""
                let el = arguments[0];
                while (el && el !== document.body) {
                    if (el.tagName === 'A' && el.getAttribute('href')) {
                        return el.getAttribute('href');
                    }
                    el = el.parentElement;
                }
                return "";
            """, node) or ""
        except Exception:
            return ""

    def _is_photo_link(self, url: str) -> bool:
        if not url:
            return False
        u = url.lower()
        return ("/photo/?" in u) or ("/photo.php" in u) or ("/photos/" in u)

    def _get_og_image_from_page(self, driver, url: str) -> Optional[str]:
        """在「新分頁」開啟照片頁，取 og:image；完畢立即關閉該分頁。"""
        parent_handle = None
        try:
            parent_handle = driver.current_window_handle
        except Exception:
            parent_handle = None

        photo_handle = self.open_in_new_tab(driver, url)
        if not photo_handle:
            return None
        try:
            # 圖片頁也可能跳出登入牆/彈窗，沿用同一套關閉機制
            self.close_login_wall(driver)
            html = driver.page_source or ""
            if BS4_AVAILABLE and html:
                soup = BeautifulSoup(html, "html.parser")
                og = soup.find("meta", attrs={"property": "og:image"})
                if og and og.get("content"):
                    return ihtml.unescape(og.get("content", "").strip())
            # 備援：取第一張顯示中的 img
            try:
                img = driver.find_element(By.CSS_SELECTOR, "img[src]")
                src = img.get_attribute("src") or ""
                if src:
                    return src
            except Exception:
                pass
            return None
        finally:
            try:
                driver.close()
            except Exception:
                pass
            try:
                # 回到原分頁（不要猜 main_handle / window_handles[0]，避免 session 被玩壞）
                if parent_handle and parent_handle in driver.window_handles:
                    driver.switch_to.window(parent_handle)
                elif self.main_handle and self.main_handle in driver.window_handles:
                    driver.switch_to.window(self.main_handle)
                else:
                    driver.switch_to.window(driver.window_handles[0])
            except Exception:
                pass

    def _has_more_photo_overlay(self, root) -> bool:
        """偵測多圖貼文的「+13 / +5」覆蓋文字（僅限貼文本體區塊）。"""
        try:
            elems = root.find_elements(By.CSS_SELECTOR, "span, div")
        except Exception:
            return False
        for e in elems:
            try:
                t = (e.text or "").strip()
                if re.fullmatch(r"\+\d+", t):
                    return True
            except Exception:
                continue
        return False

    def _collect_images_from_photo_viewer(self, driver, start_url: str, overlay_num: int = 0, hard_cap: int = 35) -> List[str]:
        """副流程：viewer 翻頁抓圖（完全按照你最終確認的流程）
        - 把副流程第一張圖記錄為 start_key
        - 之後連續回到這張第一張圖 N 次才結束（處理 FB 亂序）
        - overlay_num > 0 時同時檢查去重後數量 >= (XX + 4)
        """
        if not start_url:
            return []

        self.logger.info(f"🔄 啟動副流程 viewer 翻頁 - {start_url} (overlay_num={overlay_num})")

        parent_handle = driver.current_window_handle
        photo_handle = self.open_in_new_tab(driver, start_url)
        if not photo_handle:
            return []

        try:
            self.close_login_wall(driver)
            self.wait_page_loaded(driver, timeout=12)
            self.human_sleep(1.2, 2.5)

            start_key = None          # 副流程自己抓到的第一張圖作為起點基準
            seen_keys = set()
            images: List[str] = []
            consecutive_start_repeat = 0
            max_start_repeat = 3      # 連續回到起點幾次才結束（可調整）

            for flip in range(1, hard_cap + 1):
                self.logger.info(f"  └─ 第 {flip} 次翻頁")

                # ==================== 登入牆恢復 ====================
                if self._is_login_wall_blocking(driver):
                    self.logger.warning(f"     ⚠️  偵測到關不掉的登入牆！開始恢復流程 (第 {flip} 輪)")
                    resume_url = driver.current_url or start_url
                    recovered = False
                    for attempt in range(2):
                        try:
                            driver.close()
                            if parent_handle in driver.window_handles:
                                driver.switch_to.window(parent_handle)
                            else:
                                driver.switch_to.window(driver.window_handles[0])

                            new_handle = self.open_in_new_tab(driver, resume_url)
                            if new_handle:
                                self.close_login_wall(driver)
                                self.wait_page_loaded(driver, timeout=12)
                                self.human_sleep(1.0, 2.5)
                                if not self._is_login_wall_blocking(driver):
                                    recovered = True
                                    self.logger.info(f"     ✅ 登入牆恢復成功 (第 {attempt+1} 次)")
                                    break
                        except Exception as e:
                            self.logger.error(f"     重開分頁失敗: {e}")
                    if not recovered:
                        self.logger.error("     ❌ 登入牆恢復失敗，結束 viewer 循環")
                        break

                # ==================== 抓圖 ====================
                full_url = self._get_current_viewer_large_image(driver)
                if full_url:
                    dedup_key = self._get_image_dedup_key(full_url)

                    # 第一張圖：記錄為起點基準
                    if start_key is None:
                        start_key = dedup_key
                        seen_keys.add(dedup_key)
                        images.append(full_url)
                        self.logger.info(f"     → 已記錄副流程第一張圖作為起點基準")
                        self.logger.info(f"     ★ 新增第 {len(images)} 張（起點）")
                        consecutive_start_repeat = 0

                    # 回到起點（亂序處理）
                    elif dedup_key == start_key:
                        consecutive_start_repeat += 1
                        self.logger.info(f"     → 回到起點圖片（連續 {consecutive_start_repeat} 次）")
                        if consecutive_start_repeat >= max_start_repeat:
                            self.logger.info(f"     → 連續 {max_start_repeat} 次回到起點，結束副流程")
                            break

                    # 一般新圖
                    else:
                        if dedup_key not in seen_keys:
                            seen_keys.add(dedup_key)
                            images.append(full_url)
                            self.logger.info(f"     ★ 新增第 {len(images)} 張 viewer 圖片")
                            consecutive_start_repeat = 0   # 重置計數器

                    # overlay_num > 0 的結束條件（去重後數量）
                    if overlay_num > 0 and len(seen_keys) >= (overlay_num + 4):
                        self.logger.info(f"     → 已達到 +{overlay_num} 的預期獨特張數 ({overlay_num + 4} 張)，結束副流程")
                        break

                # 翻下一張 + 加強延遲
                clicked = False
                for sel in [
                    'div[role="button"][aria-label*="下一張" i]',
                    'div[role="button"][aria-label*="Next" i]',
                    'a[role="link"][aria-label*="next" i]'
                ]:
                    try:
                        btns = driver.find_elements(By.CSS_SELECTOR, sel)
                        for btn in btns:
                            if btn.is_displayed() and self.safe_click(driver, btn):
                                clicked = True
                                break
                        if clicked: break
                    except Exception:
                        continue

                if not clicked:
                    try:
                        ActionChains(driver).send_keys(Keys.ARROW_RIGHT).perform()
                    except Exception:
                        pass

                self.human_sleep(1.5, 3.5)
                self.wait_page_loaded(driver, timeout=5)

                if flip >= 35:
                    self.logger.warning("     ⚠️ 已達 35 次安全上限，強制結束副流程")
                    break

            self.logger.info(f"✅ viewer 循環結束，共收集 {len(images)} 張新圖（去重後 {len(seen_keys)} 張）")
            return images

        finally:
            try:
                driver.close()
            except Exception:
                pass
            try:
                driver.switch_to.window(parent_handle)
            except Exception:
                pass

    def _get_current_viewer_large_image(self, driver) -> Optional[str]:
        """專門給 viewer 用的抓大圖函式 - 比 og:image 更穩定"""
        # 方法1：JS 直接抓 og:image（最快）
        try:
            url = driver.execute_script('''
                return document.querySelector('meta[property="og:image"]')?.getAttribute("content") ||
                    document.querySelector('img[role="presentation"]')?.getAttribute("src");
            ''')
            if url and ("fbcdn.net" in url or "scontent" in url):
                return ihtml.unescape(url.strip())
        except Exception:
            pass

        # 方法2：找最大的顯示中圖片
        try:
            imgs = driver.find_elements(By.CSS_SELECTOR, "img[src*='scontent'], img[role='presentation']")
            for img in imgs:
                src = img.get_attribute("src") or ""
                if src and not src.startswith("data:"):
                    return src
        except Exception:
            pass

        return None

    def _is_login_wall_blocking(self, driver) -> bool:
        """判斷是否真的被登入牆擋住（比原本更精準）"""
        try:
            cu = driver.current_url or ""
            if "/login" in cu or "checkpoint" in cu:
                return True

            dialogs = driver.find_elements(By.CSS_SELECTOR, 'div[role="dialog"]')
            for d in dialogs:
                if not d.is_displayed(): continue
                txt = (d.text or "").lower()
                if any(k in txt for k in ["登入", "log in", "password", "密碼"]):
                    return True
        except Exception:
            pass
        return False

    def extract_images_from_root(self, driver, root) -> List[str]:
        """從根元素提取圖片 - 一進來就先判斷是否有 +XX 多圖覆蓋
        有 +XX → 直接走副流程（viewer 翻頁），完全不跑主流程
        沒有 +XX → 才走主流程
        """
        self.logger.info("摘取圖片中...")

        # Step 1: 先判斷是否有 +XX 多圖覆蓋（你的核心需求）
        if self._has_more_photo_overlay(root):
            self.logger.info("偵測到 +XX 多圖覆蓋 → 直接啟動副流程（不跑主流程）")

            # 找第一個可點的照片連結來開 viewer
            photo_links = []
            try:
                nodes = root.find_elements(By.CSS_SELECTOR, "img[src]")
                for im in nodes:
                    href = self._nearest_anchor_href(driver, im)
                    if href and self._is_photo_link(href):
                        photo_nav = self.normalize_fb_url_for_nav(href)
                        photo_links.append(photo_nav)
                        break
            except Exception:
                pass

            if photo_links:
                # 新增：抓 +XX 數字並記錄 log
                overlay_num = self._get_photo_overlay_count(root)
                self.logger.info(f"偵測到 +{overlay_num} 多圖覆蓋，預期至少抓 {overlay_num + 4} 張")

                viewer_imgs = self._collect_images_from_photo_viewer(
                    driver, photo_links[0], overlay_num=overlay_num
                )
                self.logger.info(f"副流程結束 → 最終圖片數: {len(viewer_imgs)}")
                self.logger.info("最終返回的 images 連結：\n" + "\n".join(viewer_imgs))
                return viewer_imgs[:self.config.get("image_limit", 20)]

        # Step 2: 沒有 +XX → 走原本的主流程
        self.logger.info("無多圖覆蓋 → 執行主流程")

        thumbs: List[Tuple[int, str, Optional[str]]] = []
        try:
            nodes = root.find_elements(By.CSS_SELECTOR, "img[src]")
            for im in nodes:
                src = im.get_attribute("src") or ""
                if src.startswith("data:image") or "svg" in src or any(k in src for k in ["emoji", "static.xx.fbcdn.net", "assets"]):
                    continue
                if self.node_in_comments(driver, im):
                    continue
                href = self._nearest_anchor_href(driver, im)
                href_resolved = self._resolve_href(href, driver.current_url) if href else ""
                score = 1 + (2 if "scontent" in src else 0)
                thumbs.append((score, src, href_resolved))
        except Exception:
            pass

        if not thumbs:
            return []

        image_limit = self.config.get("image_limit", 20)
        unique_thumbs = []
        seen = set()
        for _, src, href in sorted(thumbs, key=lambda x: x[0], reverse=True):
            if src in seen: continue
            seen.add(src)
            unique_thumbs.append((src, href))
            if len(unique_thumbs) >= image_limit: break

        fulls: List[str] = []
        for thumb_src, href in unique_thumbs:
            full_url = thumb_src
            if href and self._is_photo_link(href):
                photo_nav = self.normalize_fb_url_for_nav(href)
                full_url = self._get_og_image_from_page(driver, photo_nav) or thumb_src

            canon = self._canonical_image(full_url)
            if canon and canon not in fulls:
                fulls.append(canon)
                self.logger.info(f"抓取圖片 URL: {canon}")

            self.human_sleep(1.2, 2.0)

        # ★★★ 最簡單去重 ★★★
        final_images = self._dedup_image_list(fulls)
        self.logger.info(f"主流程結束 → 最終圖片數: {len(final_images)}")
        self.logger.info("最終返回的 images 連結：\n" + "\n".join(final_images))
        return final_images[:image_limit]

    # ---------- URL 取得：數字型 vs pfbid ----------
    def _extract_canonical_www_url(self, driver) -> str:
        """優先取 og:url 或 rel=canonical，否則用 current_url；最後正規化為 www 存檔"""
        html = driver.page_source or ""
        cand = None
        if BS4_AVAILABLE and html:
            try:
                soup = BeautifulSoup(html, "html.parser")
                link_can = soup.find("link", attrs={"rel": "canonical"})
                if link_can and link_can.get("href"):
                    cand = link_can.get("href").strip()
                if not cand:
                    og = soup.find("meta", attrs={"property": "og:url"})
                    if og and og.get("content"):
                        cand = og.get("content").strip()
            except Exception:
                pass
        if not cand:
            cand = driver.current_url
        return self.normalize_fb_url_for_storage(cand)

    def _extract_pfbid_url(self, driver) -> Optional[str]:
        """嘗試從 current_url 或頁面上的 <a> 找到 /posts/pfbid... 連結"""
        cur = driver.current_url or ""
        if "/posts/pfbid" in cur:
            return self.normalize_fb_url_for_storage(cur)
        try:
            anchors = driver.find_elements(By.CSS_SELECTOR, "a[href*='/posts/pfbid']")
            for a in anchors:
                href = a.get_attribute("href") or ""
                if "/posts/pfbid" in href:
                    return self.normalize_fb_url_for_storage(href)
        except Exception:
            pass
        return None

    def _extract_numeric_url(self, driver) -> Optional[str]:
        """
        取出「傳統數字型」連結：
        - /permalink/<page>/<post>
        - /posts/<digits>
        - /story.php?story_fbid=...&id=...
        """
        def is_numeric_path(u: str) -> bool:
            p = urlparse(u)
            if "/posts/pfbid" in p.path.lower():
                return False
            if re.search(r"/posts/\d+", p.path):
                return True
            if re.search(r"/permalink/\d+/\d+", p.path):
                return True
            if p.path.startswith("/story.php"):
                qs = parse_qs(p.query)
                return ("story_fbid" in qs and "id" in qs)
            return False

        # 1) 看 canonical / og:url
        cand = self._extract_canonical_www_url(driver)
        if cand and is_numeric_path(cand):
            return self.normalize_fb_url_for_storage(cand)

        # 2) 掃描 anchors
        try:
            anchors = driver.find_elements(By.CSS_SELECTOR, "a[href]")
            for a in anchors:
                href = a.get_attribute("href") or ""
                if not href:
                    continue
                absu = self._resolve_href(href, driver.current_url)
                if absu and is_numeric_path(absu):
                    return self.normalize_fb_url_for_storage(absu)
        except Exception:
            pass

        return None

    # ---------- 時間工具（dateutil） ----------
    def _iso_utc_from_epoch(self, sec: int) -> str:
        dt = datetime.fromtimestamp(int(sec), tz=timezone.utc)
        return dt.isoformat().replace("+00:00", "Z")

    def _to_utc_iso(self, dt) -> str:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=self.tzinfo or gettz("UTC"))
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    # 本版新增：把 ISO / epoch 轉成 SQLite DATETIME（本地時區，無時區字尾）
    def _to_sqlite_datetime_local(self, iso_or_epoch: str) -> Optional[str]:
        if not iso_or_epoch:
            return None
        s = str(iso_or_epoch).strip()
        try:
            if re.fullmatch(r"\d{10,13}", s):
                sec = int(s[:10])
                dt = datetime.fromtimestamp(sec, tz=timezone.utc).astimezone(self.tzinfo)
            else:
                dt = duparser.parse(s)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)  # 若是像 "2025-01-01 12:00:00" 當作 UTC
                dt = dt.astimezone(self.tzinfo)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return None

    def _normalize_datetime_text(self, s: str) -> str:
        """
        將中文日期時間轉為 dateutil 可解析的字串（不做繁瑣 parsing，只做最小正規化）
        範例：2025年1月1日 星期六下午7:00 -> 2025-1-1 7:00 PM
        """
        if not s:
            return s
        t = s.strip()
        t = t.replace("：", ":")
        # 去除星期
        t = re.sub(r"星期[一二三四五六日天]", " ", t)
        t = re.sub(r"週[一二三四五六日天]", " ", t)
        # 年月日替換
        t = t.replace("年", "-").replace("月", "-").replace("日", " ")
        # 中文 AM/PM
        t = t.replace("上午", " AM ").replace("早上", " AM ").replace("清晨", " AM ")
        t = t.replace("下午", " PM ").replace("中午", " PM ").replace("晚上", " PM ").replace("傍晚", " PM ")
        # 7點 / 7時 → 7:00
        t = re.sub(r"(\d{1,2})\s*[點时時]", r"\1:00", t)
        # 把「PM 7:00」換成「7:00 PM」
        t = re.sub(r"\b(AM|PM)\s*(\d{1,2}:\d{2})", r"\2 \1", t, flags=re.IGNORECASE)
        # 壓空白
        t = re.sub(r"\s+", " ", t).strip()
        return t

    def _parse_datetime_any(self, s: str) -> Optional[str]:
        """
        使用 python-dateutil 解析任何字串：
        - 純數字（10/13位）→ epoch
        - 中文正規化 → parse(fuzzy=True)
        - 其他格式交給 parse（含 ISO8601）
        回傳 ISO8601 UTC（Z）
        """
        if not s:
            return None
        st = s.strip()

        # epoch 秒/毫秒
        if re.fullmatch(r"\d{10,13}", st):
            sec = int(st[:10])
            return self._iso_utc_from_epoch(sec)

        # 中文正規化再 parse
        norm = self._normalize_datetime_text(st)
        try:
            dt = duparser.parse(norm, fuzzy=True)
            return self._to_utc_iso(dt)
        except Exception:
            pass

        # 最後再嘗試原字串
        try:
            dt = duparser.parse(st, fuzzy=True)
            return self._to_utc_iso(dt)
        except Exception:
            return None

    def _hover(self, driver, elem, pause=0.25):
        try:
            ActionChains(driver).move_to_element(elem).pause(pause).perform()
        except Exception:
            pass

    # 本版新增：從 page_source 直接抓 Comet 內嵌 JSON 的 epoch（creation_time / publish_time）
    def _epoch_from_pagesource(self, html: str) -> Optional[int]:
        if not html:
            return None
        # 先針對典型結構做較嚴謹的兩個樣式
        pats = [
            r'"timestamp"\s*:\s*{[^{}]*"story"\s*:\s*{[^{}]*"creation_time"\s*:\s*(\d{10,})',
            r'"post_context"\s*:\s*{[^{}]*"publish_time"\s*:\s*(\d{10,})',
        ]
        for pat in pats:
            m = re.search(pat, html)
            if m:
                try:
                    return int(m.group(1))
                except Exception:
                    pass
        # 最後寬鬆掃描
        m2 = re.search(r'"(?:creation_time|publish_time)"\s*:\s*(\d{10,})', html)
        if m2:
            try:
                return int(m2.group(1))
            except Exception:
                return None
        return None

    # 本版新增：相對時間（2天、3小時、剛剛）→ 轉 epoch
    def _epoch_from_relative_text(self, s: str) -> Optional[int]:
        if not s:
            return None
        t = s.strip()
        now = datetime.now(tz=self.tzinfo)
        # 剛剛
        if t in ("剛剛", "刚刚"):
            return int(now.timestamp())
        # X 分鐘 / 小時 / 天 / 週 / 月 / 年
        m = re.match(r"(\d+)\s*(分鐘|分|小時|小时|天|週|周|週數|星期|月|年)", t)
        if not m:
            # 英文相對：min/hours/days/weeks/months/years ago
            m2 = re.match(r"(\d+)\s*(min|mins|minutes|hour|hours|day|days|week|weeks|month|months|year|years)", t, flags=re.I)
            if m2:
                num = int(m2.group(1))
                unit = m2.group(2).lower()
                delta = {
                    "min": timedelta(minutes=num), "mins": timedelta(minutes=num), "minutes": timedelta(minutes=num),
                    "hour": timedelta(hours=num),  "hours": timedelta(hours=num),
                    "day": timedelta(days=num),    "days": timedelta(days=num),
                    "week": timedelta(weeks=num),  "weeks": timedelta(weeks=num),
                    "month": timedelta(days=30*num),"months": timedelta(days=30*num),
                    "year": timedelta(days=365*num),"years": timedelta(days=365*num),
                }[unit]
                return int((now - delta).timestamp())
            return None
        num = int(m.group(1))
        unit = m.group(2)
        if unit in ("分鐘", "分"):
            delta = timedelta(minutes=num)
        elif unit in ("小時", "小时"):
            delta = timedelta(hours=num)
        elif unit in ("天",):
            delta = timedelta(days=num)
        elif unit in ("週", "周", "週數", "星期"):
            delta = timedelta(weeks=num)
        elif unit in ("月",):
            delta = timedelta(days=30*num)
        elif unit in ("年",):
            delta = timedelta(days=365*num)
        else:
            return None
        return int((now - delta).timestamp())

    def extract_timestamp(self, driver, root) -> Optional[str]:
        """
        盡可能從貼文本體取出「絕對時間」並轉成 ISO8601 UTC（Z）：
          0) **本版新增**：先從 page_source 讀取 creation_time/publish_time（epoch）
          1) <meta property="article:published_time">
          2) <abbr data-utime> / <time datetime>
          3) aria-label / title / data-tooltip-content / data-store（hover 後 tooltip）
          4) 全頁備援掃描（含 data-store JSON）
          5) **本版新增**：相對時間字樣（2天/3小時/剛剛）
        """
        html = driver.page_source or ""

        # 0) 先用 page_source 的嵌入 JSON 拿 epoch（最可靠）
        try:
            epoch0 = self._epoch_from_pagesource(html)
            if epoch0:
                return self._iso_utc_from_epoch(epoch0)
        except Exception:
            pass

        # 1) meta: article:published_time
        try:
            if BS4_AVAILABLE and html:
                soup = BeautifulSoup(html, "html.parser")
                meta_ts = soup.find("meta", attrs={"property": "article:published_time"})
                if meta_ts and meta_ts.get("content"):
                    iso = self._parse_datetime_any(meta_ts.get("content").strip())
                    if iso:
                        return iso
        except Exception:
            pass

        # 2) data-utime / datetime（root 範圍）
        for sel, attr in [("abbr[data-utime]", "data-utime"), ("time[datetime]", "datetime")]:
            try:
                elems = root.find_elements(By.CSS_SELECTOR, sel)
            except Exception:
                elems = []
            for e in elems:
                try:
                    if self.node_in_comments(driver, e):
                        continue
                    val = (e.get_attribute(attr) or "").strip()
                    if not val:
                        continue
                    # data-utime 通常就是 epoch
                    if attr == "data-utime" and val.isdigit():
                        return self._iso_utc_from_epoch(int(val[:10]))
                    iso = self._parse_datetime_any(val)
                    if iso:
                        return iso
                except Exception:
                    continue

        # 3) aria-label / title / data-tooltip-content / data-store（含 hover / tooltip）
        selectors = [
            "a[aria-label]", "span[aria-label]", "abbr[title]", "[data-tooltip-content]",
            "[title]", "[data-store]"
        ]
        for sel in selectors:
            try:
                elems = root.find_elements(By.CSS_SELECTOR, sel)
            except Exception:
                elems = []
            for e in elems:
                try:
                    if not e.is_displayed():
                        continue
                except Exception:
                    pass
                if self.node_in_comments(driver, e):
                    continue

                # 先 hover 以觸發 tooltip（若有）
                self._hover(driver, e)

                # data-store 可能是 JSON（含 epoch）
                ds = e.get_attribute("data-store") or ""
                if ds:
                    try:
                        obj = json.loads(ds)
                        for k in ("time", "publish_time", "creation_time", "timestamp"):
                            vv = obj.get(k)
                            if vv is not None and str(vv).isdigit():
                                return self._iso_utc_from_epoch(int(str(vv)[:10]))
                    except Exception:
                        pass

                for attr in ("data-utime", "datetime", "data-tooltip-content", "aria-label", "title"):
                    val = e.get_attribute(attr) or ""
                    if not val:
                        continue
                    # 可能是相對字樣
                    ep = self._epoch_from_relative_text(val)
                    if ep:
                        return self._iso_utc_from_epoch(ep)
                    iso = self._parse_datetime_any(val)
                    if iso:
                        return iso

                # tooltip DOM
                try:
                    tooltips = driver.find_elements(By.CSS_SELECTOR, "div[role='tooltip']")
                    for t in tooltips:
                        txt = (t.text or "").strip()
                        ep = self._epoch_from_relative_text(txt)
                        if ep:
                            return self._iso_utc_from_epoch(ep)
                        iso = self._parse_datetime_any(txt)
                        if iso:
                            return iso
                except Exception:
                    pass

        # 4) 全頁備援掃描（含 data-store）
        try:
            all_candidates = driver.find_elements(By.CSS_SELECTOR,
                "abbr[data-utime], time[datetime], a[aria-label], span[aria-label], [data-tooltip-content], [title], [data-store]"
            )
        except Exception:
            all_candidates = []
        for e in all_candidates:
            try:
                if self.node_in_comments(driver, e):
                    continue
                ds = e.get_attribute("data-store") or ""
                if ds:
                    try:
                        obj = json.loads(ds)
                        for k in ("time", "publish_time", "creation_time", "timestamp"):
                            vv = obj.get(k)
                            if vv is not None and str(vv).isdigit():
                                return self._iso_utc_from_epoch(int(str(vv)[:10]))
                    except Exception:
                        pass
                v = (e.get_attribute("data-utime") or "").strip()
                if v.isdigit():
                    return self._iso_utc_from_epoch(int(v[:10]))
                for attr in ("datetime", "aria-label", "title", "data-tooltip-content"):
                    val = (e.get_attribute(attr) or "").strip()
                    if val:
                        ep = self._epoch_from_relative_text(val)
                        if ep:
                            return self._iso_utc_from_epoch(ep)
                        iso = self._parse_datetime_any(val)
                        if iso:
                            return iso
            except Exception:
                continue

        # 5) 最後一招：直接從 page_source 裡抓「相對時間」字樣
        try:
            rel = re.search(r">(剛剛|刚刚|\d+\s*(?:分鐘|分|小時|小时|天|週|周|星期|月|年))<", html)
            if rel:
                ep = self._epoch_from_relative_text(rel.group(1))
                if ep:
                    return self._iso_utc_from_epoch(ep)
        except Exception:
            pass

        return None

    def extract_post_by_url(self, driver, url, idx=1):
        """根據 URL 提取單篇貼文（文字 + 圖片）"""
        self.ensure_only_main_tab(driver)

        open_url = self.normalize_fb_url_for_nav(url)
        new_handle = self.open_in_new_tab(driver, open_url)
        if not new_handle:
            # 導航失敗也回傳基礎結構
            return {"url": "", "pfbid_url": "", "text": "", "text_md": "", "images": [], "timestamp": None, "content_hash": None}

        try:
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, f"{self.MESSAGE_SELECTORS}, article, div.story_body_container"))
                )
            except Exception:
                pass

            self.human_sleep(1.2, 2.0)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            self.human_sleep(0.6, 1.0)
            self.wait_page_loaded(driver)
            self.logger.info(f"貼文載入完成：{driver.current_url}")

            # 取兩種 URL
            pfbid_url = self._extract_pfbid_url(driver) or ""
            numeric_url = self._extract_numeric_url(driver) or ""

            root = self.get_post_root(driver)
            if not root:
                return {
                    "url": numeric_url, "pfbid_url": pfbid_url,
                    "text": "", "text_md": "", "images": [], "timestamp": None, "content_hash": None
                }

            try:
                for sc in root.find_elements(By.CSS_SELECTOR, self.MESSAGE_SELECTORS):
                    self.expand_see_more_in_scope(driver, sc)
            except Exception:
                pass

            text, text_md = self.extract_text_from_root(driver, root)
            images = self.extract_images_from_root(driver, root)
            ts     = self.extract_timestamp(driver, root)

            # ★ 修正：若在 m 站抓不到時間，改嘗試 www 站 canonical 重新抓一次（正確處理分頁返回）
            if not ts:
                try:
                    current_post_handle = driver.current_window_handle  # ★ 記錄目前這篇貼文的分頁
                    www_url = self.normalize_fb_url_for_storage(driver.current_url)
                    if www_url:
                        backup_handle = self.open_in_new_tab(driver, www_url)
                        if backup_handle:
                            try:
                                WebDriverWait(driver, 8).until(
                                    EC.presence_of_element_located((By.CSS_SELECTOR, "article, [role='article']"))
                                )
                            except Exception:
                                pass
                            self.human_sleep(0.6, 1.0)
                            root2 = self.get_post_root(driver)
                            ts2 = self.extract_timestamp(driver, root2 or root)
                            if ts2:
                                ts = ts2
                            # 關掉備援分頁並回到原貼文分頁
                            try:
                                driver.close()
                            except Exception:
                                pass
                            try:
                                driver.switch_to.window(current_post_handle)  # ★ 切回原來貼文分頁
                            except Exception:
                                pass
                except Exception:
                    pass

            content_hash = self._build_content_hash(text, images)

            data = {
                "url": numeric_url,
                "pfbid_url": pfbid_url,
                "text": text,
                "text_md": text_md,
                "images": images,
                "timestamp": ts,   # JSON 仍存 ISO/UTC（Z）
                "content_hash": content_hash,
            }

            if text:
                preview = (text[:160] + "...") if len(text) > 160 else text
                self.logger.info(f"擷取到的文字（預覽）: {preview}")
            else:
                self.logger.warning("未擷取到文字內容")
            self.logger.info(f"圖片數量: {len(images)} | 時間戳: {ts}")

            return data

        finally:
            try:
                driver.close()
            except Exception:
                pass
            try:
                driver.switch_to.window(self.main_handle or driver.window_handles[0])
            except Exception:
                pass

    # ---------- 主流程 ----------
    def scrape_facebook_posts(self) -> List[Dict]:
        """
        主要的 FB 抓取方法
        Returns:
            List[Dict]: 抓取到的貼文列表
        """
        results, empty_link_failure = self._scrape_facebook_posts_once()
        self.last_empty_link_failure = empty_link_failure
        return results

    def _scrape_facebook_posts_once(self) -> Tuple[List[Dict], bool]:
        """單輪抓取；回傳 (results, empty_link_failure)。"""
        driver = None
        try:
            driver = self.setup_driver()
            self.logger.info(f"目標：{self.config['target_url']}")
            self.human_sleep(1.0, 2.0)
            driver.get(self.config["target_url"])
            self.human_sleep(1.2, 2.0)
            self.close_login_wall(driver)

            # 初始化主分頁 handle
            try:
                self.main_handle = driver.current_window_handle
            except Exception:
                self.main_handle = driver.window_handles[0]

            links = self.collect_first_n_links(driver)
            if not links:
                self.logger.error("未能取得任何貼文連結")
                return [], True

            results = []
            for i, url in enumerate(links, 1):
                self.logger.info(f"\n--- 解析第 {i} 篇 ---")
                self.ensure_only_main_tab(driver)

                data = self.extract_post_by_url(driver, url, idx=i)
                data["post_id"] = f"fb_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{i}"
                results.append(data)

                self.ensure_only_main_tab(driver)

            # 集中決策：去重 + 合併 + 產生 DB ops + 寫 JSON + 套 DB
            self._save_fb_posts_to_json(results)
            return results, False

        except Exception as e:
            self.logger.error(f"抓取過程發生錯誤: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return [], False
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass

    # ---------- 儲存 JSON（以 content_hash 為唯一；同時產生 DB ops） ----------
    def _load_existing_json(self) -> Dict:
        """讀取 data/fb_posts.json；不存在則回基本結構"""
        filepath = os.path.join(self.config["data_dir"], "fb_posts.json")
        if not os.path.exists(filepath):
            return {"source": "facebook", "last_updated": None, "total_posts": 0, "posts": []}
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            posts = data.get("posts", []) if isinstance(data, dict) else data
            # 舊資料相容：把 _content_hash 轉為 content_hash
            for p in posts:
                if p.get("_content_hash") and not p.get("content_hash"):
                    p["content_hash"] = p["_content_hash"]
                # 規範 URL
                if p.get("url"):
                    p["url"] = self.normalize_fb_url_for_storage(p["url"])
                if p.get("pfbid_url"):
                    p["pfbid_url"] = self.normalize_fb_url_for_storage(p["pfbid_url"])
            return {"source": "facebook", "last_updated": data.get("last_updated"), "total_posts": len(posts), "posts": posts}
        except Exception:
            return {"source": "facebook", "last_updated": None, "total_posts": 0, "posts": []}

    def _merge_fields_for_duplicate(self, base: Dict, incoming: Dict) -> bool:
        """
        合併同一 content_hash 的資料：
        - 只補「空白」的 url/pfbid_url（不覆蓋非空值）
        - text/text_md 取較長
        - images 取數量較多（同時去重）
        - timestamp 若 base 無而 incoming 有，則補上
        回傳：是否有變動
        """
        changed = False

        # URL 欄位策略：只補空白
        if (not base.get("url")) and incoming.get("url"):
            base["url"] = self.normalize_fb_url_for_storage(incoming["url"])
            changed = True
        if (not base.get("pfbid_url")) and incoming.get("pfbid_url"):
            base["pfbid_url"] = self.normalize_fb_url_for_storage(incoming["pfbid_url"])
            changed = True

        # 文本取較長
        def longer(a: Optional[str], b: Optional[str]) -> str:
            a = a or ""
            b = b or ""
            return b if len(b) > len(a) else a

        new_text = longer(base.get("text"), incoming.get("text"))
        if new_text != (base.get("text") or ""):
            base["text"] = new_text
            changed = True

        new_text_md = longer(base.get("text_md"), incoming.get("text_md"))
        if new_text_md != (base.get("text_md") or ""):
            base["text_md"] = new_text_md
            changed = True

        # 圖片合併去重（新 URL 優先，確保 CDN token 是最新的）
        imgs_old = [x for x in (base.get("images") or []) if x]
        imgs_new = [x for x in (incoming.get("images") or []) if x]

        combined = []
        seen = set()
        for img in imgs_new + imgs_old:   # 新圖優先（CDN token 較新鮮）
            if not img: continue
            key = self._get_image_dedup_key(img)
            if key not in seen:
                seen.add(key)
                combined.append(img)      # ← 存原始完整 URL！

        # 最終輸出前再輕度正規化一次（確保圖片可顯示）
        combined = [self._canonical_image(x) for x in combined]
        old_canonical = [self._canonical_image(x) for x in imgs_old]

        if len(combined) >= len(imgs_old) and combined != old_canonical:
            # 數量不縮水才更新（防止抓取不完整時丟失圖片），同時刷新 CDN token
            base["images"] = combined
            changed = True

        # 時間戳：若 base 無而 incoming 有
        if (not base.get("timestamp")) and incoming.get("timestamp"):
            base["timestamp"] = incoming["timestamp"]
            changed = True

        # 重新計算 content_hash（照理應相同，但保險）
        base["content_hash"] = self._build_content_hash(base.get("text", ""), base.get("images", []))

        # 更新 last_seen
        base["last_seen"] = datetime.now().isoformat()

        return changed

    def _save_fb_posts_to_json(self, new_posts: List[Dict]) -> None:
        """
        儲存 Facebook 貼文到 JSON 並以同決策同步資料庫。
        * 兩道去重關卡：
          1. 第一道：url 或 pfbid_url（如果找到相同 URL，檢查 content_hash）
          2. 第二道：content_hash（如果 content_hash 相同，合併；不同，新增新的）
        * 決策：insert / update / noop
        """
        try:
            bundle = self._load_existing_json()
            existing_posts: List[Dict] = bundle.get("posts", [])

            # 建 url 和 pfbid_url 索引（第一道關卡）
            by_url: Dict[str, Dict] = {}
            by_pfbid_url: Dict[str, Dict] = {}

            for p in existing_posts:
                url = p.get("url") or ""
                pfbid_url = p.get("pfbid_url") or ""
                if url:
                    by_url[url] = p
                if pfbid_url:
                    by_pfbid_url[pfbid_url] = p

            # DB 操作清單
            ops: List[Dict] = []
            added_count = 0
            updated_count = 0
            noop_count = 0

            for np in new_posts:
                # 規範 URL 欄位
                if np.get("url"):
                    np["url"] = self.normalize_fb_url_for_storage(np["url"])
                if np.get("pfbid_url"):
                    np["pfbid_url"] = self.normalize_fb_url_for_storage(np["pfbid_url"])

                # 建立 content_hash（用於第二道關卡）
                ch = np.get("content_hash") or self._build_content_hash(np.get("text", ""), np.get("images", []))
                np["content_hash"] = ch
                np["last_seen"] = datetime.now().isoformat()

                new_url = np.get("url") or ""
                new_pfbid_url = np.get("pfbid_url") or ""

                # 第一道關卡：檢查相同種類的 URL
                existing_post = None
                url_type = None

                if new_url and new_url in by_url:
                    existing_post = by_url[new_url]
                    url_type = "url"
                elif new_pfbid_url and new_pfbid_url in by_pfbid_url:
                    existing_post = by_pfbid_url[new_pfbid_url]
                    url_type = "pfbid_url"

                if existing_post:
                    # 第二道關卡：檢查 content_hash
                    existing_hash = existing_post.get("content_hash")
                    if existing_hash == ch:
                        # content_hash 相同 → 合併欄位
                        before = json.dumps({
                            "url": existing_post.get("url") or "",
                            "pfbid_url": existing_post.get("pfbid_url") or "",
                            "text_len": len(existing_post.get("text") or ""),
                            "text_md_len": len(existing_post.get("text_md") or ""),
                            "img_n": len(existing_post.get("images") or []),
                            "timestamp": existing_post.get("timestamp") or "",
                            "content_hash": existing_post.get("content_hash") or ""
                        }, ensure_ascii=False, sort_keys=True)

                        changed = self._merge_fields_for_duplicate(existing_post, np)

                        after = json.dumps({
                            "url": existing_post.get("url") or "",
                            "pfbid_url": existing_post.get("pfbid_url") or "",
                            "text_len": len(existing_post.get("text") or ""),
                            "text_md_len": len(existing_post.get("text_md") or ""),
                            "img_n": len(existing_post.get("images") or []),
                            "timestamp": existing_post.get("timestamp") or "",
                            "content_hash": existing_post.get("content_hash") or ""
                        }, ensure_ascii=False, sort_keys=True)

                        if changed and before != after:
                            updated_count += 1
                            ops.append({"action": "update", "post": dict(existing_post)})
                        else:
                            noop_count += 1  # JSON 不需異動 → DB 也不動
                    else:
                        # content_hash 不同 → 更新現有貼文（相同 URL 的不同內容版本）
                        # 保留 URL，更新內容
                        existing_post.update({
                            "text": np.get("text", ""),
                            "text_md": np.get("text_md", ""),
                            "images": np.get("images", []),
                            "timestamp": np.get("timestamp"),
                            "content_hash": ch,
                            "last_seen": np["last_seen"]
                        })

                        # 如果新貼文有缺少的 URL 欄位，補上
                        if url_type == "url" and not existing_post.get("pfbid_url") and np.get("pfbid_url"):
                            existing_post["pfbid_url"] = np["pfbid_url"]
                        elif url_type == "pfbid_url" and not existing_post.get("url") and np.get("url"):
                            existing_post["url"] = np["url"]

                        updated_count += 1
                        ops.append({"action": "update", "post": dict(existing_post)})
                else:
                    # 第一道關卡沒有找到 → 檢查是否有相同 content_hash 的貼文（跨種類 URL）
                    existing_by_hash = None
                    for p in existing_posts:
                        if p.get("content_hash") == ch:
                            existing_by_hash = p
                            break

                    if existing_by_hash:
                        # 找到相同 content_hash → 合併 URL 欄位
                        changed = False
                        if not existing_by_hash.get("url") and new_url:
                            existing_by_hash["url"] = new_url
                            changed = True
                        if not existing_by_hash.get("pfbid_url") and new_pfbid_url:
                            existing_by_hash["pfbid_url"] = new_pfbid_url
                            changed = True

                        # 更新 last_seen
                        existing_by_hash["last_seen"] = np["last_seen"]

                        if changed:
                            updated_count += 1
                            ops.append({"action": "update", "post": dict(existing_by_hash)})
                        else:
                            noop_count += 1
                    else:
                        # 都沒有找到 → 新增
                        existing_posts.append(np)

                        # 更新索引
                        if new_url:
                            by_url[new_url] = np
                        if new_pfbid_url:
                            by_pfbid_url[new_pfbid_url] = np

                        added_count += 1
                        ops.append({"action": "insert", "post": dict(np)})

            # 排序（有 timestamp 的放前面）
            existing_posts.sort(key=lambda p: p.get("timestamp") or "", reverse=True)
            bundle["posts"] = existing_posts
            bundle["last_updated"] = datetime.now().isoformat()
            bundle["total_posts"] = len(existing_posts)

            # 寫檔
            filepath = os.path.join(self.config["data_dir"], "fb_posts.json")
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(bundle, f, ensure_ascii=False, indent=2)

            self.logger.info(f"✅ FB 貼文 JSON 已更新：新增 {added_count}、更新 {updated_count}、無變動 {noop_count}；總計 {len(existing_posts)} 篇")

            # 以相同決策同步 DB（DB 不做自行去重判斷）
            if db_available and ops:
                self._sync_db_from_ops(ops)
            elif db_available:
                self.logger.info("資料庫：無需異動（全部為 noop）")

        except Exception as e:
            self.logger.error(f"儲存 FB 貼文 JSON 失敗: {e}")
            import traceback
            self.logger.error(traceback.format_exc())

    # ---------- 以 JSON 決策同步到資料庫 ----------
    def _sync_db_from_ops(self, ops: List[Dict]) -> None:
        """
        僅依據 JSON 決策執行資料庫操作：
        - action == insert → 以 content_hash 新增
        - action == update → 以 content_hash 定位並「補空白欄位 / 合併較長文本 / 合併新圖片」
        - 不處理 noop

        本版修正：
        - 寫入 SQLite 前，把 post['timestamp'] 從 ISO/UTC 或 epoch 統一轉為 SQLite DATETIME（YYYY-MM-DD HH:MM:SS，本地時區）
        - 為避免影響 JSON 寫入內容，這裡對 ops 做淺複製並轉換後再丟給 DB 層
        """
        if not db_available:
            self.logger.warning("資料庫模組不可用，跳過資料庫儲存")
            return

        # 準備送往 DB 的 ops 副本（只轉 timestamp 格式）
        ops_for_db: List[Dict] = []
        for op in ops:
            op_copy = {"action": op.get("action"), "post": dict(op.get("post") or {})}
            ts_iso = op_copy["post"].get("timestamp")
            if ts_iso:
                ts_db = self._to_sqlite_datetime_local(ts_iso)
                if ts_db:
                    op_copy["post"]["timestamp"] = ts_db  # DB 端收到的是 SQLite DATETIME 字串
            ops_for_db.append(op_copy)

        session = None
        try:
            session = get_db_session()
            db_manager = DatabaseManager(session)

            inserted = 0
            updated = 0

            db_manager.sync_fb_posts_ops(ops_for_db)  # 用轉好時間格式的 ops
            inserted = sum(1 for op in ops_for_db if op.get("action") == "insert")
            updated = sum(1 for op in ops_for_db if op.get("action") == "update")

            db_manager.commit()
            self.logger.info(f"✅ FB 貼文資料庫已同步：新增 {inserted}、更新 {updated}")

        except Exception as e:
            self.logger.error(f"同步 FB 貼文到資料庫失敗: {e}")
            if session:
                session.rollback()
            import traceback
            self.logger.error(traceback.format_exc())
        finally:
            if session:
                session.close()

    # ---------- fb_url_list（累積、不重複；存 logs） ----------
    def _append_fb_url_list(self, urls: List[str]):
        """
        將「貼文詳情連結（canonical www）」累積到 logs/fb_url_list.txt
        - 不覆蓋；不重複（讀舊 → 合併 → 回寫）
        """
        if not urls:
            return
        log_file = os.path.join(self.config["html_log_dir"], "fb_url_list.txt")
        old = set()
        if os.path.exists(log_file):
            try:
                with open(log_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        s = line.strip()
                        if s:
                            old.add(s)
            except Exception:
                pass
        for u in urls:
            cu = self.normalize_fb_url_for_storage(u)
            if cu:
                old.add(cu)
        try:
            with open(log_file, 'w', encoding='utf-8') as f:
                for u in sorted(old):
                    f.write(u + "\n")
            self.logger.info(f"📝 已更新 fb_url_list.txt（共 {len(old)} 條）")
        except Exception as e:
            self.logger.error(f"寫入 fb_url_list.txt 失敗: {e}")

    # ---------- 工具 ----------
    def _cleanup_old_html_files(self):
        """清理舊的 HTML 日誌檔案，只保留最近 max_scraping_sessions × max_links 個結果（僅在 debug_mode 寫檔前呼叫）"""
        try:
            html_dir = self.config["html_log_dir"]
            max_files = self.config["max_html_files"]

            if not os.path.exists(html_dir):
                return

            html_files = []
            for filename in os.listdir(html_dir):
                if filename.startswith("page_source_") and filename.endswith(".html"):
                    filepath = os.path.join(html_dir, filename)
                    if os.path.isfile(filepath):
                        ts = filename.replace("page_source_", "").replace(".html", "")
                        try:
                            dt = datetime.strptime(ts, "%Y%m%d_%H%M%S")
                            html_files.append((filepath, dt))
                        except ValueError:
                            try:
                                os.remove(filepath)
                                self.logger.info(f"刪除無效檔案: {filename}")
                            except Exception:
                                pass

            if len(html_files) > max_files:
                html_files.sort(key=lambda x: x[1], reverse=True)
                for filepath, _ in html_files[max_files:]:
                    try:
                        os.remove(filepath)
                        self.logger.info(f"🗑️ 刪除舊 HTML 檔案: {os.path.basename(filepath)}")
                    except Exception as e:
                        self.logger.error(f"刪除舊檔案失敗: {filepath}, {e}")
        except Exception as e:
            self.logger.error(f"清理 HTML 檔案時發生錯誤: {e}")

    # ---------- 其他工具 ----------
    def clean_text(self, s: str) -> str:
        """清理文字內容"""
        if not s:
            return ""
        s = s.replace("\u200b", "").replace("\ufeff", "")
        s = ihtml.unescape(s)
        s = re.sub(r"[ \t]+", " ", s)
        s = re.sub(r"\n[ \t]+", "\n", s)
        s = re.sub(r"\n{3,}", "\n\n", s)
        return s.strip()


def main():
    """獨立執行測試"""
    print("=== Facebook Scraper Service 測試執行 ===")
    try:
        service = FBScraperService()
        print("✅ 服務實例建立成功")
        print("開始測試抓取...")
        results = service.scrape_facebook_posts()

        print(f"\n=== 抓取結果 ({len(results)} 篇) ===")
        for i, post in enumerate(results, 1):
            print(f"\n--- 貼文 {i} ---")
            print(f"ID: {post.get('post_id')}")
            print(f"URL: {post.get('url')}")
            if post.get('pfbid_url'):
                print(f"pfbid_url: {post.get('pfbid_url')}")
            text = post.get('text', '')
            text_md = post.get('text_md', '')
            if text:
                preview = text[:100] + "..." if len(text) > 100 else text
                print(f"文字: {preview}")
            else:
                print("文字: (無)")
            if text_md:
                preview_md = text_md[:100] + "..." if len(text_md) > 100 else text_md
                print(f"文字(Discord Markdown): {preview_md}")
            print(f"圖片數量(大圖): {len(post.get('images', []))}")
            print(f"時間戳(JSON/ISO UTC): {post.get('timestamp')}")
            print(f"content_hash: {post.get('content_hash')}")

        if results and service.config.get("debug_mode", False):
            filename = f"test_fb_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            filepath = os.path.join(service.config["html_log_dir"], filename)
            try:
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(results, f, ensure_ascii=False, indent=2)
                print(f"\n測試結果已儲存至: {filepath}")
            except Exception as e:
                print(f"儲存測試結果失敗: {e}")

    except Exception as e:
        print(f"測試執行失敗: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
