#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Facebook 官方貼文抓取（行動版；即使有登入牆仍能收集前三篇連結，再逐一開啟抓正文與圖片）
- 來源：m.facebook.com/WutheringWaves.ZH/（行動版通常較少牆、且 DOM 易讀）
- 主頁面：只做「收集前三篇貼文連結」（不必點擊、不進詳情）
- 登入牆：先嘗試以人類方式關閉；若仍有，依然以 DOM 讀取連結（不被遮罩影響）
- 詳情頁：在新分頁打開每個貼文連結 → 展開「查看更多」→ 擷取正文與圖片（忽略留言）→ 關閉分頁返回
- 截圖：CDP 截圖避免 headless 白圖；輸出到 /logs
- 改良：專取 [data-ad-comet-preview="message"] / [data-ad-preview="message"] 內文；
       收斂留言區判斷；加入 OG 描述備援；關閉互動暫停。
"""

import os
import re
import time
import json
import base64
import random
import inspect
from datetime import datetime
from urllib.parse import urlparse, parse_qs, urljoin
import sys

from selenium import webdriver
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException, StaleElementReferenceException,
    ElementClickInterceptedException, ElementNotInteractableException
)

from bs4 import BeautifulSoup

def is_in_docker():
    if os.path.exists('/.dockerenv'):
        return True
    try:
        with open('/proc/1/cgroup', 'r') as f:
            if 'docker' in f.read():
                return True
    except Exception:
        pass
    return False

# -------------------- 可調參數 --------------------
TARGET_URL = "https://m.facebook.com/WutheringWaves.ZH/"
HEADLESS = True
LOG_DIR = "/logs" if is_in_docker() else "./logs"
MAX_LINKS = 3
SCROLL_ROUNDS = 6
HUMAN_MIN_DELAY = (0.35, 0.9)
DEBUG_PAUSE = False  # 預設關閉互動，避免卡住

os.makedirs(LOG_DIR, exist_ok=True)

SEE_MORE_KEYWORDS = ["see more", "查看更多", "顯示更多", "更多內容", "顯示更多內容", "更多", "看更多"]
COMMENT_WORDS = ["comment", "comments", "留言", "回應", "回覆", "replies"]
MESSAGE_SELECTORS = "[data-ad-comet-preview='message'], [data-ad-preview='message']"

# 應排除的 UI/互動/翻譯等文字（整行出現時）
UI_EXCLUDE_RE = re.compile(
    r"^(所有心情|讚|留言|回覆|分享|最相關|追蹤|傳送|See translation|查看翻譯|收合翻譯|See less|顯示較少|全部留言|新增留言|\d+\s*(則)?(留言|回覆|分享))$"
)
TEXT_MAX_LEN = 8000

# -------------------- 小工具 --------------------
def clean_text(s: str) -> str:
    if not s:
        return ""
    s = s.replace("\u200b", "").replace("\ufeff", "")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n[ \t]+", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()

def take_screenshot(driver, filename):
    path = os.path.join(LOG_DIR, filename)
    try:
        driver.save_screenshot(path)
        print(f"📸 截圖：{path}")
    except Exception as e:
        print(f"❌ 截圖失敗：{e}")

def human_sleep(a=HUMAN_MIN_DELAY[0], b=HUMAN_MIN_DELAY[1]):
    time.sleep(random.uniform(a, b))

def human_move_and_scroll(driver):
    human_sleep()
    try:
        ActionChains(driver).move_by_offset(random.randint(-40, 40), random.randint(-40, 40)).perform()
    except Exception:
        pass
    driver.execute_script(f"window.scrollBy(0, {random.randint(60, 220)});")
    human_sleep(0.25, 0.6)

def wait_page_loaded(driver, timeout=10):
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

# -------------------- Driver --------------------
def setup_driver():
    opts = FirefoxOptions()
    env_firefox = os.path.join(sys.prefix, 'bin', 'firefox')
    if os.path.exists(env_firefox):
        opts.binary_location = env_firefox
    if HEADLESS:
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

# -------------------- 登入牆 / 彈窗 --------------------
def safe_click(driver, elem, retries=2):
    for _ in range(retries):
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", elem)
            human_sleep(0.15, 0.35)
            try:
                ActionChains(driver).move_to_element(elem).pause(0.2).click().perform()
            except (ElementClickInterceptedException, ElementNotInteractableException):
                driver.execute_script("arguments[0].click();", elem)
            return True
        except StaleElementReferenceException:
            human_sleep(0.2, 0.4)
        except Exception:
            human_sleep(0.2, 0.4)
    try:
        driver.execute_script("""arguments[0].dispatchEvent(new MouseEvent('click', {bubbles:true,cancelable:true}));""", elem)
        return True
    except Exception:
        return False

def close_login_wall(driver):
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
                    if safe_click(driver, btn):
                        print("✓ 關閉登入牆/對話框")
                        closed = True
                        human_sleep(0.4, 0.8)
                        break
            if closed:
                break
        except Exception:
            continue
    return closed

def looks_like_login_wall(driver):
    try:
        dialogs = driver.find_elements(By.CSS_SELECTOR, "div[role='dialog']")
        for dlg in dialogs:
            if not dlg.is_displayed():
                continue
            txt = (dlg.text or "").lower()
            if any(k in txt for k in [
                "log in", "log into facebook", "create new account",
                "登入", "建立新帳號", "建立新帳戶"
            ]):
                return True
            if dlg.find_elements(By.CSS_SELECTOR, "a[href*='login.php'], form[action*='login']"):
                return True
        return False
    except Exception:
        return False

# -------------------- 連結蒐集（主頁面） --------------------
def extract_links_via_dom(driver):
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

def extract_links_via_pagesource(driver):
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

def collect_first_n_links(driver, n=3, scroll_rounds=SCROLL_ROUNDS):
    links, seen = [], set()
    for round_idx in range(1, scroll_rounds + 1):
        if len(links) >= n:
            break
        print(f"🔎 收集連結（第 {round_idx}/{scroll_rounds} 輪）...")
        close_login_wall(driver)
        hrefs = extract_links_via_dom(driver) or extract_links_via_pagesource(driver)
        for h in hrefs:
            if h in seen:
                continue
            seen.add(h)
            links.append(h)
            if len(links) >= n:
                break
        if len(links) >= n:
            break
        human_sleep(1.5, 3.0)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        human_move_and_scroll(driver)
    links = links[:n]
    print(f"✓ 取得貼文連結數量：{len(links)}")
    for i, u in enumerate(links, 1):
        print(f"  #{i}: {u}")
    return links

# -------------------- 留言區判斷（收斂版） --------------------
def node_in_comments(driver, node) -> bool:
    """
    僅以祖先的 id/class/aria-label 判斷是否在留言區，避免 innerText 誤傷整個貼文本體。
    """
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

# -------------------- 展開查看更多（限定在 scope） --------------------
def expand_see_more_in_scope(driver, scope):
    clicked = 0
    # aria-label 方案
    try:
        btns = scope.find_elements(By.CSS_SELECTOR, "[role='button'][aria-label]")
        for b in btns:
            if not b.is_displayed():
                continue
            label = (b.get_attribute("aria-label") or "").strip().lower()
            if any(k in label for k in SEE_MORE_KEYWORDS):
                if node_in_comments(driver, b):
                    continue
                if safe_click(driver, b):
                    clicked += 1
                    human_sleep(0.35, 0.7)
    except Exception:
        pass
    # 文字方案（XPath）
    try:
        text_btns = scope.find_elements(By.XPATH,
            ".//*[contains(translate(normalize-space(.), 'SEE MORE查看更多顯示更多更多內容看更多', 'see more查看更多顯示更多更多內容看更多'),'see more') "
            "or contains(normalize-space(.), '查看更多') or contains(normalize-space(.), '顯示更多') "
            "or contains(normalize-space(.), '更多內容') or normalize-space(.)='更多' or normalize-space(.)='看更多']"
        )
        for b in text_btns:
            if not b.is_displayed():
                continue
            if node_in_comments(driver, b):
                continue
            if safe_click(driver, b):
                clicked += 1
                human_sleep(0.35, 0.7)
    except Exception:
        pass
    if clicked:
        print(f"✓ 展開查看更多：{clicked} 次")
    return clicked

# -------------------- 取貼文主體 root --------------------
def get_post_root(driver):
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

# -------------------- 文字擷取（新策略） --------------------
def _extract_from_message_scopes(driver, container):
    """
    優先在 message 容器擷取；這裡不套留言過濾（因為範圍已經是貼文本體）。
    """
    scopes = []
    try:
        scopes = container.find_elements(By.CSS_SELECTOR, MESSAGE_SELECTORS)
    except Exception:
        scopes = []
    if not scopes:
        # 再全頁找一次，避免 root 判斷不準
        try:
            scopes = driver.find_elements(By.CSS_SELECTOR, MESSAGE_SELECTORS)
        except Exception:
            scopes = []

    out_candidates = []
    for sc in scopes:
        try:
            expand_see_more_in_scope(driver, sc)
            # 直接用 innerText，保留換行
            txt = (sc.get_attribute("innerText") or sc.text or "").strip()
            txt = clean_text(txt)
            if txt and not UI_EXCLUDE_RE.match(txt):
                out_candidates.append(txt)
        except Exception:
            continue
    if not out_candidates:
        # JS 直取備援
        try:
            js = """
            const sc = document.querySelector(arguments[0]);
            if (!sc) return "";
            // 嘗試展開
            const kws = %s;
            sc.querySelectorAll('[role="button"],a,span,div').forEach(b=>{
                const t=(b.innerText||"").trim().toLowerCase();
                if (kws.some(k=>t.includes(k))) { try{b.click();}catch(e){} }
            });
            return sc.innerText || sc.textContent || "";
            """ % (json.dumps([k.lower() for k in SEE_MORE_KEYWORDS]))
            txt = driver.execute_script(js, MESSAGE_SELECTORS) or ""
            txt = clean_text(txt)
            if txt and not UI_EXCLUDE_RE.match(txt):
                out_candidates.append(txt)
        except Exception:
            pass

    if not out_candidates:
        return ""

    best = max(out_candidates, key=len).strip()
    if len(best) > TEXT_MAX_LEN:
        best = best[:TEXT_MAX_LEN]
    return best

def _extract_from_paragraphs(driver, scope):
    """
    備援：在 scope 內用 p/div[dir=auto]/span[dir=auto] 聚合段落，並用收斂後的留言判斷。
    """
    try:
        expand_see_more_in_scope(driver, scope)
    except Exception:
        pass

    try:
        blocks = scope.find_elements(By.CSS_SELECTOR, "p, div[dir='auto'], span[dir='auto']")
    except Exception:
        blocks = []

    out, seen = [], set()
    for b in blocks:
        try:
            if not b.is_displayed():
                continue
            if node_in_comments(driver, b):
                continue
            t = (b.text or "").strip()
            if not t:
                continue
            t = clean_text(t)
            if not t or UI_EXCLUDE_RE.match(t):
                continue
            if t in seen:
                continue
            seen.add(t)
            out.append(t)
        except Exception:
            continue
    return "\n\n".join(out).strip()

def _extract_from_og(page_source: str) -> str:
    try:
        soup = BeautifulSoup(page_source, "html.parser")
        og = soup.find("meta", attrs={"property": "og:description"})
        if og and og.get("content"):
            return clean_text(og.get("content", ""))
    except Exception:
        pass
    return ""

def extract_text_from_root(driver, root):
    """
    擷取貼文正文；優先 message 容器 → 再備援段落聚合 → 最後 OG 描述。
    """
    print("摘取文字中...")

    # 保存 page_source 以利除錯
    page_source = driver.page_source or ""
    filename = f"page_source_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    filepath = os.path.join(LOG_DIR, filename)
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(page_source)
        print(f"頁面原始碼保存至：{filepath}")
    except Exception:
        pass

    # A. 直接從 message 容器擷取
    txt = _extract_from_message_scopes(driver, root)
    if txt:
        print(f"✓ 直接自 message 容器取得文字（長度 {len(txt)}）")
        return txt

    # B. 用段落聚合備援
    candidates = []
    try:
        scopes = [root]
        try:
            extra = root.find_elements(By.CSS_SELECTOR, "[role='main'] article, [role='article']")
            scopes.extend([s for s in extra if s.is_displayed()])
        except Exception:
            pass
        for sc in scopes:
            t = _extract_from_paragraphs(driver, sc)
            if t and len(t) >= 8:
                candidates.append(t)
    except Exception:
        pass

    if candidates:
        best = max(candidates, key=len).strip()
        print(f"✓ 段落聚合取得文字（長度 {len(best)}）")
        return best[:TEXT_MAX_LEN]

    # C. OG 描述備援
    og = _extract_from_og(page_source)
    if og:
        print(f"✓ 從 og:description 備援取得文字（長度 {len(og)}）")
        return og[:TEXT_MAX_LEN]

    print("⚠️ 未取得文字（message/scopes/OG 都失敗）")
    return ""

# -------------------- 圖片擷取 --------------------
def extract_images_from_root(driver, root, limit=8):
    print("摘取圖片中...")
    imgs = []
    try:
        nodes = root.find_elements(By.CSS_SELECTOR, "img[src]")
    except Exception:
        nodes = []
    for im in nodes:
        try:
            src = im.get_attribute("src") or ""
            if not src:
                continue
            if any(k in src for k in ["emoji", "static.xx.fbcdn.net", "assets"]):
                continue
            if node_in_comments(driver, im):
                continue
            score = 1 + (2 if "scontent" in src else 0)
            imgs.append((score, src))
        except Exception:
            continue
    if not imgs:
        return []
    uniq, seen = [], set()
    for score, src in sorted(imgs, key=lambda x: x[0], reverse=True):
        if src in seen:
            continue
        seen.add(src)
        uniq.append(src)
        if len(uniq) >= limit:
            break
    return uniq

def extract_timestamp(driver, root):
    for sel in ["time[datetime]", "abbr[data-utime]"]:
        try:
            te = root.find_element(By.CSS_SELECTOR, sel)
            dt = te.get_attribute("datetime") or te.get_attribute("data-utime")
            if dt:
                try:
                    ts = int(dt)
                    return datetime.utcfromtimestamp(ts).isoformat() + "Z"
                except Exception:
                    return dt
        except Exception:
            continue
    return None

# -------------------- 開關分頁 --------------------
def open_in_new_tab(driver, url):
    human_sleep(1.0, 2.0)
    initial_handles = len(driver.window_handles)
    driver.execute_script("window.open('', '_blank');")
    time.sleep(0.4)
    for _ in range(10):
        new_handles = driver.window_handles
        if len(new_handles) > initial_handles:
            driver.switch_to.window(new_handles[-1])
            driver.delete_all_cookies()
            driver.get(url)
            time.sleep(2.0)
            current_url = driver.current_url
            if 'facebook.com' in current_url and ('posts' in current_url or 'permalink' in current_url or 'story.php' in current_url):
                return True
            else:
                print(f"偵測到非貼文頁面，URL: {current_url}，關閉此分頁")
                main_handle = driver.window_handles[0]
                close_current_tab(driver, main_handle)
                return False
        else:
            time.sleep(0.5)
    driver.switch_to.window(driver.window_handles[-1])
    print(f"未找到貼文分頁，當前URL: {driver.current_url}")
    return False

def close_current_tab(driver, main_handle):
    human_sleep(0.6, 1.2)
    try:
        driver.close()
    except Exception:
        pass
    try:
        driver.switch_to.window(main_handle)
    except Exception:
        pass

# -------------------- 詳情擷取 --------------------
def extract_post_by_url(driver, url, idx=1):
    if url.startswith("https://www.facebook.com/"):
        url = url.replace("https://www.facebook.com/", "https://m.facebook.com/")
    main_handle = driver.window_handles[0]
    if not open_in_new_tab(driver, url):
        return {"url": url, "text": "", "images": [], "timestamp": None}

    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, f"{MESSAGE_SELECTORS}, article, div.story_body_container"))
        )
    except Exception:
        pass

    time.sleep(random.uniform(1.2, 2.0))
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(0.8)
    wait_page_loaded(driver)

    current_url = driver.current_url
    print(f"貼文載入完成：{current_url}")

    root = get_post_root(driver)
    if not root:
        close_current_tab(driver, main_handle)
        return {"url": url, "text": "", "images": [], "timestamp": None}

    # 只在 root 範圍展開查看更多
    try:
        for sc in root.find_elements(By.CSS_SELECTOR, MESSAGE_SELECTORS):
            expand_see_more_in_scope(driver, sc)
    except Exception:
        pass

    text = extract_text_from_root(driver, root)
    images = extract_images_from_root(driver, root, limit=8)
    ts = extract_timestamp(driver, root)

    data = {"url": url, "text": text, "images": images, "timestamp": ts}
    preview = (text[:160] + "...") if text and len(text) > 160 else text
    print(f"擷取到的文字（預覽）: {preview}")
    print(f"圖片數量: {len(images)} | 時間戳: {ts}")

    close_current_tab(driver, main_handle)
    return data

# -------------------- 主流程 --------------------
def main():
    driver = None
    try:
        driver = setup_driver()
        print(f"目標：{TARGET_URL}")
        human_sleep(1.0, 2.0)
        driver.get(TARGET_URL)
        time.sleep(random.uniform(1.2, 2.0))
        close_login_wall(driver)

        links = collect_first_n_links(driver, n=MAX_LINKS, scroll_rounds=SCROLL_ROUNDS)
        if not links:
            print("❌ 未能取得任何貼文連結；結束。")
            return

        results = []
        for i, url in enumerate(links, 1):
            print(f"\n--- 解析第 {i} 篇 ---")
            data = extract_post_by_url(driver, url, idx=i)
            results.append(data)

        print("\n=== 結果（前三篇） ===")
        print(json.dumps(results, ensure_ascii=False, indent=2))

    except Exception as e:
        print(f"❌ 錯誤：{e}")
        import traceback; traceback.print_exc()
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

if __name__ == "__main__":
    main()
