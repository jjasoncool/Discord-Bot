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

- 新增（本版）：
  1) hashtag 多個支援，並在 JSON 另輸出 text_md（Discord 可直接點的 Markdown 超連結）。
  2) 由貼文小圖追到「照片頁」，從 og:image 擷取大圖 URL（images 只回大圖）。
  3) **分頁管理精簡版**：每次開始抓「新的一篇」貼文前，先關閉主分頁以外的所有分頁，避免累積造成記憶體暴衝。
     （依你的要求，移除先前的外網判斷與其他額外檢查）

  # 新增（本版再強化）：
  4) content_hash（唯一）：以 clean_text(text) + 規範化後 images 路徑（去 query/fragment）做 SHA256，
     作為內容唯一特徵，寫入 JSON 與 DB，並作為去重的唯一依據。
  5) 去重決策集中在 _save_fb_posts_to_json：**只看 content_hash**，合併時僅「補空白欄位」、文字取較長、圖片取較多。
  6) URL 欄位策略固定：`url` 儲存「傳統數字型」連結；`pfbid_url` 儲存 `/posts/pfbid...`。
     若抓不到其中一種，可留空；重複時只補空白，不覆蓋既有非空。
  7) 連結在 collect_first_n_links 階段即正規化（www + 去 tracking）；同時 logs/fb_url_list.txt 持續累積、不重複。
  8) JSON 做出 insert/update/noop 決策的同時，**同步生成 DB ops** 並一次性套用到 DB（DB 不再重複判斷）。
  9) debug_mode=True 時才落地 page_source_*.html 與 test_fb_results_*.json，控制日誌檔量。
"""

import os
import re
import time
import json
import random
import html as ihtml
import hashlib
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from urllib.parse import urlparse, parse_qs, urlunparse, urlencode, urljoin, unquote

try:
    from selenium import webdriver
    from selenium.webdriver.firefox.options import Options as FirefoxOptions
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.common.action_chains import ActionChains
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

# 注意：依你現有專案做法，get_db_session 從 db.models 匯入；DatabaseManager 從 db.database 匯入
#（這點保持與你現有代碼一致）:contentReference[oaicite:4]{index=4}
try:
    from db.database import DatabaseManager
    from db.models import get_db_session
    db_available = True
except ImportError:
    db_available = False
    print("警告: 無法載入資料庫模組，將只儲存到 JSON")


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
        self.config = FACEBOOK_CONFIG.copy()  # 建立副本，避免修改原始設定
        self.logger = self._get_logger()

        # 確保依賴可用
        if not SELENIUM_AVAILABLE:
            raise ImportError("Selenium 未安裝，無法使用 FB 抓取服務")

        # 路徑設定 (根據環境選擇目錄)
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

        # 主分頁 handle（啟動後會記錄）
        self.main_handle: Optional[str] = None

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
            r'https://m\.facebook\.com/story\.php\?[^"\']+',
            r'https://m\.facebook\.com/[^"\']+/posts/[^"\']+',
            r'https://m\.facebook\.com/[^"\']+/permalink/[^"\']+',
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

    def _normalize_urls_in_text(self, text: str) -> str:
        """將文字中的 URL 替換成 canonical（去 query/fragment），降低同文不同參數造成的差異"""
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
        out = re.sub(r"[ \t]+", " ", out)
        out = re.sub(r"\n{3,}", "\n\n", out)
        return out.strip().lower()

    def _build_content_hash(self, text: str, images: List[str]) -> str:
        """SHA256( normalize(text) + '\n' + join(sorted(canonical_images)) )"""
        t = self._normalize_urls_in_text(self.clean_text(text or ""))
        imgs = [self._canonical_image(x) for x in (images or []) if x]
        imgs = sorted(list(dict.fromkeys(imgs)))
        payload = (t + "\n" + "\n".join(imgs)).encode("utf-8", errors="ignore")
        return hashlib.sha256(payload).hexdigest()

    # ---------- 文字抽取（略；保留你原本流程） ----------
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
        photo_handle = self.open_in_new_tab(driver, url)
        if not photo_handle:
            return None
        try:
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
                driver.switch_to.window(self.main_handle or driver.window_handles[0])
            except Exception:
                pass

    def extract_images_from_root(self, driver, root, limit=8) -> List[str]:
        """從根元素提取圖片（嘗試照片頁 og:image；否則退回縮圖）"""
        self.logger.info("摘取圖片中...")
        thumbs: List[Tuple[int, str, Optional[str]]] = []
        try:
            nodes = root.find_elements(By.CSS_SELECTOR, "img[src]")
        except Exception:
            nodes = []

        for im in nodes:
            try:
                src = im.get_attribute("src") or ""
                if not src:
                    continue
                if src.startswith("data:image") or "svg+xml" in src:
                    continue
                if any(k in src for k in ["emoji", "static.xx.fbcdn.net", "assets"]):
                    continue
                if self.node_in_comments(driver, im):
                    continue
                href = self._nearest_anchor_href(driver, im)
                href_resolved = self._resolve_href(href, driver.current_url) if href else ""
                score = 1 + (2 if "scontent" in src else 0)
                thumbs.append((score, src, href_resolved))
            except Exception:
                continue

        if not thumbs:
            return []

        unique_thumbs, seen = [], set()
        for score, src, href in sorted(thumbs, key=lambda x: x[0], reverse=True):
            if src in seen:
                continue
            seen.add(src)
            unique_thumbs.append((score, src, href))
            if len(unique_thumbs) >= limit:
                break

        fulls: List[str] = []
        seen_full = set()
        for _, thumb_src, href in unique_thumbs:
            full_url = None
            if href and self._is_photo_link(href):
                photo_nav = self.normalize_fb_url_for_nav(href)
                full_url = self._get_og_image_from_page(driver, photo_nav)
            if not full_url:
                full_url = thumb_src
            canon_full = self._canonical_image(full_url)
            if canon_full and canon_full not in seen_full:
                seen_full.add(canon_full)
                fulls.append(canon_full)
                self.logger.info(f"抓取圖片 URL: {canon_full}")
            if len(fulls) >= limit:
                break

        return fulls

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

    def extract_timestamp(self, driver, root):
        """提取時間戳（先抓 article:published_time；再抓 time[datetime]/abbr[data-utime]）"""
        try:
            html = driver.page_source or ""
            if BS4_AVAILABLE and html:
                soup = BeautifulSoup(html, "html.parser")
                meta_ts = soup.find("meta", attrs={"property": "article:published_time"})
                if meta_ts and meta_ts.get("content"):
                    return meta_ts.get("content").strip()
        except Exception:
            pass

        for sel in ["time[datetime]", "abbr[data-utime]"]:
            try:
                te = root.find_element(By.CSS_SELECTOR, sel)
                dt = te.get_attribute("datetime") or te.get_attribute("data-utime")
                if dt:
                    try:
                        ts = int(dt)
                        return datetime.fromtimestamp(ts).isoformat() + "Z"
                    except Exception:
                        return dt
            except Exception:
                continue
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
            images = self.extract_images_from_root(driver, root, limit=8)
            ts     = self.extract_timestamp(driver, root)

            content_hash = self._build_content_hash(text, images)

            data = {
                "url": numeric_url,        # 傳統數字型（可為空字串）
                "pfbid_url": pfbid_url,    # 新制 pfbid（可為空字串）
                "text": text,
                "text_md": text_md,
                "images": images,
                "timestamp": ts,
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
                return []

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
            return results

        except Exception as e:
            self.logger.error(f"抓取過程發生錯誤: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return []
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

        # 圖片取較多（同時做 canonical 去重）
        imgs_old = [self._canonical_image(x) for x in (base.get("images") or []) if x]
        imgs_new = [self._canonical_image(x) for x in (incoming.get("images") or []) if x]
        uniq_old = list(dict.fromkeys(imgs_old))
        uniq_new = list(dict.fromkeys(imgs_new))
        if len(uniq_new) > len(uniq_old):
            base["images"] = uniq_new
            changed = True
        else:
            base["images"] = uniq_old

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
        * 唯一鍵：content_hash
        * 決策：insert / update / noop
        """
        try:
            bundle = self._load_existing_json()
            existing_posts: List[Dict] = bundle.get("posts", [])

            # 建 content_hash 索引
            by_hash: Dict[str, Dict] = {}
            for p in existing_posts:
                h = p.get("content_hash")
                if h and h not in by_hash:
                    by_hash[h] = p

            # DB 操作清單
            ops: List[Dict] = []
            added_count = 0
            updated_count = 0
            noop_count = 0

            for np in new_posts:
                ch = np.get("content_hash") or self._build_content_hash(np.get("text", ""), np.get("images", []))
                if not ch:
                    # 沒有 hash，略過此篇
                    noop_count += 1
                    continue

                # 規範 URL 欄位
                if np.get("url"):
                    np["url"] = self.normalize_fb_url_for_storage(np["url"])
                if np.get("pfbid_url"):
                    np["pfbid_url"] = self.normalize_fb_url_for_storage(np["pfbid_url"])

                np["content_hash"] = ch
                np["last_seen"] = datetime.now().isoformat()

                if ch not in by_hash:
                    # 全新 → insert
                    existing_posts.append(np)
                    by_hash[ch] = np
                    added_count += 1
                    ops.append({"action": "insert", "post": dict(np)})
                else:
                    # 已存在 → 合併
                    target = by_hash[ch]
                    before = json.dumps({
                        "url": target.get("url") or "",
                        "pfbid_url": target.get("pfbid_url") or "",
                        "text_len": len(target.get("text") or ""),
                        "text_md_len": len(target.get("text_md") or ""),
                        "img_n": len(target.get("images") or []),
                        "timestamp": target.get("timestamp") or ""
                    }, ensure_ascii=False, sort_keys=True)

                    changed = self._merge_fields_for_duplicate(target, np)

                    after = json.dumps({
                        "url": target.get("url") or "",
                        "pfbid_url": target.get("pfbid_url") or "",
                        "text_len": len(target.get("text") or ""),
                        "text_md_len": len(target.get("text_md") or ""),
                        "img_n": len(target.get("images") or []),
                        "timestamp": target.get("timestamp") or ""
                    }, ensure_ascii=False, sort_keys=True)

                    if changed and before != after:
                        updated_count += 1
                        ops.append({"action": "update", "post": dict(target)})
                    else:
                        noop_count += 1  # JSON 不需異動 → DB 也不動

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
        """
        if not db_available:
            self.logger.warning("資料庫模組不可用，跳過資料庫儲存")
            return

        session = None
        try:
            session = get_db_session()
            db_manager = DatabaseManager(session)

            inserted = 0
            updated = 0

            db_manager.sync_fb_posts_ops(ops)  # 新增的精準同步方法（見 database.py）
            inserted = sum(1 for op in ops if op.get("action") == "insert")
            updated = sum(1 for op in ops if op.get("action") == "update")

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
            print(f"時間戳: {post.get('timestamp')}")
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
