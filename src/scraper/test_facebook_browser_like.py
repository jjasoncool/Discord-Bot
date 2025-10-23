#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Facebook 官方貼文抓取（行動版；即使有登入牆仍能收集前三篇連結，再逐一開啟抓正文與圖片）
- 來源：m.facebook.com/WutheringWaves.ZH/（行動版通常較少牆、且 DOM 易讀）
- 主頁面：只做「收集前三篇貼文連結」（不必點擊、不進詳情）
- 登入牆：先嘗試以人類方式關閉；若仍有，依然以 DOM 讀取連結（不被遮罩影響）
- 詳情頁：在新分頁打開每個貼文連結 → 展開「查看更多」→ 擷取正文與圖片（忽略留言）→ 關閉分頁返回
- 截圖：CDP 截圖避免 headless 白圖；輸出到 /logs
"""

import os
import re
import time
import json
import base64
import random
from datetime import datetime
from urllib.parse import urlparse, parse_qs, urljoin

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException, StaleElementReferenceException,
    ElementClickInterceptedException, ElementNotInteractableException
)

# -------------------- 可調參數 --------------------
TARGET_URL = "https://m.facebook.com/WutheringWaves.ZH/"
HEADLESS = True              # 建議除錯時改 False 觀察
LOG_DIR = "/logs"
MAX_LINKS = 3                # 只收集前三篇
SCROLL_ROUNDS = 6            # 主頁面最多下捲次數以蒐集連結
HUMAN_MIN_DELAY = (0.35, 0.9)

os.makedirs(LOG_DIR, exist_ok=True)

SEE_MORE_KEYWORDS = ["see more", "查看更多", "顯示更多", "更多內容", "顯示更多內容", "更多"]
COMMENT_WORDS = ["comment", "comments", "留言", "回應", "回覆", "replies"]

# -------------------- Driver 相關 --------------------
def setup_driver():
    opts = Options()
    if HEADLESS:
        opts.add_argument("--headless=new")
        # 軟體 GL，避免白圖
        opts.add_argument("--use-gl=swiftshader")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--incognito")
    opts.add_argument("--lang=zh-TW")
    # 某些環境可輕微降低自動化痕跡
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    prefs = {"intl.accept_languages": "zh-TW,zh,en-US,en"}
    opts.add_experimental_option("prefs", prefs)
    # UA（簡單固定即可）
    ua = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    opts.add_argument(f"--user-agent={ua}")

    driver = webdriver.Chrome(options=opts)
    # （可選）調整 navigator.webdriver
    try:
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    except Exception:
        pass
    # CDP 設定
    try:
        driver.execute_cdp_cmd("Network.enable", {})
        driver.execute_cdp_cmd("Network.setExtraHTTPHeaders", {
            "headers": {"Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7"}
        })
        driver.execute_cdp_cmd("Page.enable", {})
    except Exception:
        pass
    return driver

def take_screenshot(driver, filename):
    path = os.path.join(LOG_DIR, filename)
    try:
        metrics = driver.execute_cdp_cmd("Page.getLayoutMetrics", {})
        cs = metrics.get("contentSize", {})
        clip = {
            "x": 0, "y": 0,
            "width": float(cs.get("width", 1920)),
            "height": float(cs.get("height", 1080)),
            "scale": 1
        }
        img = driver.execute_cdp_cmd("Page.captureScreenshot", {"format": "png", "clip": clip})
        with open(path, "wb") as f:
            f.write(base64.b64decode(img["data"]))
        print(f"📸 截圖：{path}")
    except Exception as e:
        print(f"❌ 截圖失敗：{e}")

# -------------------- 人類式行為 --------------------
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
    # 最後嘗試 dispatchEvent
    try:
        driver.execute_script("""arguments[0].dispatchEvent(new MouseEvent('click', {bubbles:true,cancelable:true}));""", elem)
        return True
    except Exception:
        return False

# -------------------- 登入牆 / 彈窗 --------------------
def close_login_wall(driver):
    """
    嘗試以人類方式關閉登入牆；若關不掉也不阻礙 DOM 讀取。
    """
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
    """
    直接在 DOM 取出候選貼文連結（不需點擊；可穿透遮罩）
    目標 href 包含：/story.php、/posts/、/permalink/
    """
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

      // 統一成絕對網址
      let url = h;
      try { url = new URL(h, location.href).toString(); } catch(e){}

      // 只收貼文詳情的 pattern
      if (url.includes("/story.php") || url.includes("/posts/") || url.includes("/permalink/")) {
        // 排除留言/回覆錨點
        if (url.includes("comment_id=") || url.includes("reply_comment_id=") || url.includes("comment_tracking")) continue;
        // 排除通知/廣告追蹤
        if (url.includes("notif_id=") || url.includes("refid=")) continue;
        hrefs.push(url);
      }
    }
    // 去重並保留順序
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
    """
    正則備援：從 page_source 直接撈 m-site 貼文連結。
    """
    html = driver.page_source or ""
    # 常見三類
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
    # 去重保序
    seen, uniq = set(), []
    for u in hrefs:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq[:20]

def collect_first_n_links(driver, n=3, scroll_rounds=SCROLL_ROUNDS):
    """
    主頁面蒐集前 n 個貼文連結；若不夠就捲動多次。
    遇登入牆先嘗試關閉；即便關不掉，也能讀 DOM 抓連結。
    """
    links = []
    seen = set()
    round_idx = 0

    while len(links) < n and round_idx < scroll_rounds:
        round_idx += 1
        print(f"🔎 收集連結（第 {round_idx}/{scroll_rounds} 輪）...")

        # 嘗試關閉彈窗，但不強求
        close_login_wall(driver)

        # DOM 直接撈
        hrefs = extract_links_via_dom(driver)
        if not hrefs:
            # 正則備援
            hrefs = extract_links_via_pagesource(driver)

        # 去重 + 收集
        for h in hrefs:
            if h in seen:
                continue
            seen.add(h)
            links.append(h)
            if len(links) >= n:
                break

        if len(links) >= n:
            break

        # 不足就下捲載入更多
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        human_move_and_scroll(driver)
        # 截圖（除錯用）
        take_screenshot(driver, f"collect_round_{round_idx}.png")

    # 若仍不足，保留已取得的
    links = links[:n]
    print(f"✓ 取得貼文連結數量：{len(links)}")
    for i, u in enumerate(links, 1):
        print(f"  #{i}: {u}")
    return links

# -------------------- 詳情頁擷取 --------------------
def node_in_comments(driver, node) -> bool:
    """
    啟發式判斷：此節點是否位於留言區（避免抓到留言文字/圖片）。
    """
    try:
        return driver.execute_script("""
            const words = arguments[1];
            function inComments(el){
                while (el && el !== document.body){
                    const al = (el.getAttribute && el.getAttribute('aria-label') || '').toLowerCase();
                    const id = (el.id || '').toLowerCase();
                    const cls = (el.className || '').toLowerCase();
                    const txt = (el.innerText || '').toLowerCase();
                    if (id.includes('comments') || id.includes('ufi') || cls.includes('comment')) return true;
                    for (const w of words){
                        if (al.includes(w) || (txt && txt.includes(w))) return true;
                    }
                    el = el.parentElement;
                }
                return false;
            }
            return inComments(arguments[0]);
        """, node, [w.lower() for w in COMMENT_WORDS])
    except Exception:
        return False

def expand_see_more_in_scope(driver, scope):
    """
    在指定區域內展開「查看更多/See more」；避免展開留言區。
    """
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
            ".//*[contains(translate(normalize-space(.), 'SEE MORE查看更多顯示更多更多內容', 'see more查看更多顯示更多更多內容'),'see more') "
            "or contains(normalize-space(.), '查看更多') or contains(normalize-space(.), '顯示更多') "
            "or contains(normalize-space(.), '更多內容') or normalize-space(.)='更多']"
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

def get_post_root(driver):
    """
    嘗試鎖定貼文主體容器（避免掃到留言）。
    """
    # 優先 article
    roots = driver.find_elements(By.CSS_SELECTOR, "article, [role='article']")
    for r in roots:
        if r.is_displayed():
            return r
    # 其次 m 站常見容器
    for sel in ["div#MPhotoContent", "div.story_body_container", "div[data-ft]"]:
        try:
            r = driver.find_element(By.CSS_SELECTOR, sel)
            if r.is_displayed():
                return r
        except Exception:
            continue
    # 最後備援：body
    try:
        return driver.find_element(By.TAG_NAME, "body")
    except Exception:
        return None

def extract_text_from_root(driver, root):
    """
    只擷取正文文字（盡量避開留言）；先看已知 message 容器，再退而求其次。
    """
    texts = []
    # 已知正文容器（桌面/行動混合，盡量涵蓋）
    selectors = [
        "[data-ad-comet-preview='message']",
        "[data-ad-preview='message']",
        "div.story_body_container",
        "div[data-sigil*='m-feed-voice']",
    ]
    for sel in selectors:
        try:
            nodes = root.find_elements(By.CSS_SELECTOR, sel)
        except Exception:
            nodes = []
        for n in nodes:
            if node_in_comments(driver, n):
                continue
            for e in n.find_elements(By.CSS_SELECTOR, "div[dir='auto'], span[dir='auto']"):
                t = (e.text or "").strip()
                if t:
                    texts.append(t)

    if not texts:
        # 備援：取 root 下可見文字塊，但跳過疑似留言的節點
        try:
            cand = root.find_elements(By.CSS_SELECTOR, "div[dir='auto'], span[dir='auto']")
        except Exception:
            cand = []
        for e in cand:
            if node_in_comments(driver, e):
                continue
            t = (e.text or "").strip()
            if len(t) >= 5:
                texts.append(t)

    if not texts:
        # 再不行就拿 root 的整體文字（常會包含 UI/留言，僅作最後備援）
        try:
            t = (root.text or "").strip()
            if t:
                texts.append(t)
        except Exception:
            pass

    if not texts:
        return ""
    texts.sort(key=len, reverse=True)
    return texts[0][:2000]

def extract_images_from_root(driver, root, limit=8):
    """
    只收貼文主體的圖片；排除 emoji/UI 圖與留言中的圖。
    """
    imgs = []
    try:
        nodes = root.find_elements(By.CSS_SELECTOR, "img[src]")
    except Exception:
        nodes = []
    for im in nodes:
        if node_in_comments(driver, im):
            continue
        src = im.get_attribute("src") or ""
        if not src:
            continue
        if any(k in src for k in ["emoji", "static.xx.fbcdn.net", "assets"]):
            continue
        # scontent 優先
        score = 1 + (2 if "scontent" in src else 0)
        imgs.append((score, src))
    if not imgs:
        return []
    # 去重保序（依 score 排序）
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

def open_in_new_tab(driver, url):
    driver.execute_script("window.open(arguments[0], '_blank');", url)
    time.sleep(0.4)
    driver.switch_to.window(driver.window_handles[-1])

def close_current_tab(driver, main_handle):
    try:
        driver.close()
    except Exception:
        pass
    driver.switch_to.window(main_handle)

def extract_post_by_url(driver, url, idx=1):
    """
    在新分頁打開貼文 → 盡量展開查看更多 → 擷取正文 + 圖片（忽略留言）→ 截圖 → 關閉分頁
    """
    main_handle = driver.window_handles[0]
    open_in_new_tab(driver, url)

    # 載入
    time.sleep(random.uniform(1.8, 3.2))
    close_login_wall(driver)  # 能關就關；關不掉也先抽取

    # 取 root
    root = get_post_root(driver)
    if not root:
        take_screenshot(driver, f"post_{idx}_no_root.png")
        close_current_tab(driver, main_handle)
        return {"url": url, "text": "", "images": [], "timestamp": None}

    # 展開查看更多（僅在 root 範圍）
    try:
        expand_see_more_in_scope(driver, root)
    except Exception:
        pass

    text = extract_text_from_root(driver, root)
    images = extract_images_from_root(driver, root, limit=8)
    ts = extract_timestamp(driver, root)

    take_screenshot(driver, f"post_{idx}.png")
    data = {"url": url, "text": text, "images": images, "timestamp": ts}

    close_current_tab(driver, main_handle)
    return data

# -------------------- 主流程 --------------------
def main():
    driver = None
    try:
        driver = setup_driver()
        print(f"目標：{TARGET_URL}")
        driver.get(TARGET_URL)
        time.sleep(random.uniform(1.8, 3.0))
        close_login_wall(driver)  # 能關就關，不能關也不影響 DOM 抽取
        take_screenshot(driver, "landing.png")

        # 1) 主頁面收集前三篇貼文連結（即便有登入牆）
        links = collect_first_n_links(driver, n=MAX_LINKS, scroll_rounds=SCROLL_ROUNDS)
        if not links:
            print("❌ 未能取得任何貼文連結；結束。")
            return

        # 2) 逐一在新分頁開啟連結，擷取正文與圖片（忽略留言）
        results = []
        for i, url in enumerate(links, 1):
            print(f"\n--- 解析第 {i} 篇 ---")
            data = extract_post_by_url(driver, url, idx=i)
            preview = (data["text"][:160] + "...") if data["text"] and len(data["text"]) > 160 else data["text"]
            print(f"時間：{data['timestamp']}")
            print(f"正文：{preview}")
            print(f"圖片：{len(data['images'])} 張")
            results.append(data)

        # 3) 輸出結果（你可改成寫檔）
        print("\n=== 結果（前三篇） ===")
        print(json.dumps(results, ensure_ascii=False, indent=2))
        take_screenshot(driver, "final.png")

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
