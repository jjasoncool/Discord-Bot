"""
Bahamut 爬蟲服務（第一版 MVP）

第一版範圍：
- 抓看板文章列表
- 抓單篇主文
- 抓主文留言（以 HTML 可見內容為主）
- 回文/回文留言先做可抓性探測與 raw 保留，不先結構化入庫
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from requests.adapters import HTTPAdapter
from requests.exceptions import ConnectionError, HTTPError, RequestException, SSLError, Timeout
from urllib3.util.retry import Retry

try:
    import cloudscraper  # type: ignore
    CLOUDSCRAPER_AVAILABLE = True
except Exception:
    cloudscraper = None
    CLOUDSCRAPER_AVAILABLE = False

# 讓此檔案可被單檔直接執行（與 ptt_scraper_service.py 一致）
# python services/bahamut_scraper_service.py 時，將 /app 加入 sys.path
SCRAPER_ROOT = os.path.dirname(os.path.dirname(__file__))
if SCRAPER_ROOT not in sys.path:
    sys.path.insert(0, SCRAPER_ROOT)

from config import BAHAMUT_CONFIG
from utils.logger import get_logger
from utils.request_utils import human_sleep


class BahamutScraperService:
    """Bahamut 爬蟲服務（MVP）"""

    def __init__(self, db_manager=None):
        self.logger = get_logger("bahamut_scraper")
        self.db_manager = db_manager

        self.target_board_url = BAHAMUT_CONFIG["target_board_url"]
        self.timeout = int(BAHAMUT_CONFIG.get("timeout", 20) or 20)
        self.board_pages = max(1, int(BAHAMUT_CONFIG.get("board_pages", 1) or 1))
        self.max_articles_per_page = max(1, int(BAHAMUT_CONFIG.get("max_articles_per_page", 30) or 30))
        self.gate_max_hops = max(1, int(BAHAMUT_CONFIG.get("gate_max_hops", 3) or 3))
        self.human_delay_range = BAHAMUT_CONFIG.get("human_delay_min", (0.35, 0.9))
        self.sample_output_dir = BAHAMUT_CONFIG.get("sample_output_dir", "data/bahamut_samples")

        self.ua = self._init_user_agent()

    def _init_user_agent(self):
        try:
            return UserAgent()
        except Exception as e:
            self.logger.warning(f"初始化 fake-useragent 失敗，改用固定 UA: {e}")
            return None

    def _get_user_agent(self) -> str:
        if self.ua:
            try:
                return self.ua.random
            except Exception as e:
                self.logger.warning(f"取得 fake-useragent 失敗，改用固定 UA: {e}")

        return (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
        )

    def _build_headers(self, referer: Optional[str] = None) -> Dict[str, str]:
        headers = {
            "User-Agent": self._get_user_agent(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            # 明確表達要桌面版文件，不要手機版
            "Upgrade-Insecure-Requests": "1",
            "Sec-CH-UA": '"Chromium";v="127", "Not;A=Brand";v="24", "Google Chrome";v="127"',
            "Sec-CH-UA-Mobile": "?0",
            "Sec-CH-UA-Platform": '"Linux"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        }
        if referer:
            headers["Referer"] = referer
        return headers

    def _to_desktop_forum_url(self, url: str) -> str:
        """若被導到 m.gamer.com.tw/forum/*，轉回 desktop forum URL。"""
        if not url:
            return url

        parsed = urlparse(url)
        if parsed.netloc != "m.gamer.com.tw":
            return url
        if not parsed.path.startswith("/forum/"):
            return url

        desktop_path = parsed.path[len("/forum/"):]
        return urlunparse((parsed.scheme, "forum.gamer.com.tw", f"/{desktop_path}", parsed.params, parsed.query, parsed.fragment))

    def _build_session(self) -> requests.Session:
        if CLOUDSCRAPER_AVAILABLE:
            session = cloudscraper.create_scraper()
        else:
            session = requests.Session()

        retry = Retry(
            total=3,
            connect=3,
            read=3,
            backoff_factor=1.0,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=frozenset(["GET"]),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def _fetch_html(
        self,
        session: requests.Session,
        url: str,
        referer: Optional[str] = None,
    ) -> Tuple[str, str, int]:
        """回傳 (html, final_url, status_code)"""
        last_error: Exception | None = None
        for attempt in range(1, 4):
            try:
                self.logger.info(
                    "Bahamut request start: url=%s referer=%s ua=%s mobile_hint=%s cookies=%s",
                    url,
                    referer,
                    self._build_headers(referer=referer).get("User-Agent", "")[:80],
                    self._build_headers(referer=referer).get("Sec-CH-UA-Mobile"),
                    {
                        "ckFORUM_VIEW_forum": session.cookies.get("ckFORUM_VIEW", domain="forum.gamer.com.tw"),
                        "ckFORUM_VIEW_m": session.cookies.get("ckFORUM_VIEW", domain="m.gamer.com.tw"),
                        "ckMOBILE_gamer": session.cookies.get("ckMOBILE", domain="gamer.com.tw"),
                        "ckMOBILE_forum": session.cookies.get("ckMOBILE", domain="forum.gamer.com.tw"),
                        "ckMOBILE_m": session.cookies.get("ckMOBILE", domain="m.gamer.com.tw"),
                    },
                )

                resp = session.get(
                    url,
                    headers=self._build_headers(referer=referer),
                    timeout=self.timeout,
                )

                self.logger.info(
                    "Bahamut first response: request_url=%s final_url=%s status=%s history=%s location=%s set_cookie=%s",
                    url,
                    resp.url,
                    resp.status_code,
                    [
                        {
                            "status": h.status_code,
                            "url": h.url,
                            "location": h.headers.get("Location"),
                        }
                        for h in resp.history
                    ],
                    resp.headers.get("Location"),
                    resp.headers.get("Set-Cookie"),
                )

                # 依使用者決議：先以一般連結進站，若出現 302 到 mobile 再補 ckNOMOBILE
                redirected_to_mobile = (
                    urlparse(url).netloc == "forum.gamer.com.tw"
                    and urlparse(resp.url).netloc == "m.gamer.com.tw"
                    and any(
                        (h.headers.get("Location") or "").startswith("https://m.gamer.com.tw/forum/")
                        for h in resp.history
                    )
                )

                if redirected_to_mobile and not session.cookies.get("ckNOMOBILE", domain=".gamer.com.tw"):
                    session.cookies.set("ckNOMOBILE", "1", domain=".gamer.com.tw", path="/")
                    self.logger.info("Bahamut 偵測到 desktop->mobile 302，補寫 cookie: ckNOMOBILE=1")

                desktop_url = self._to_desktop_forum_url(resp.url)
                if desktop_url != resp.url:
                    self.logger.warning("Bahamut 被導向手機版，強制改抓 desktop 版: %s -> %s", resp.url, desktop_url)
                    resp = session.get(
                        desktop_url,
                        headers=self._build_headers(referer=referer or url),
                        timeout=self.timeout,
                    )
                    self.logger.info(
                        "Bahamut desktop retry response: request_url=%s final_url=%s status=%s history=%s location=%s set_cookie=%s",
                        desktop_url,
                        resp.url,
                        resp.status_code,
                        [
                            {
                                "status": h.status_code,
                                "url": h.url,
                                "location": h.headers.get("Location"),
                            }
                            for h in resp.history
                        ],
                        resp.headers.get("Location"),
                        resp.headers.get("Set-Cookie"),
                    )

                status = resp.status_code
                if status >= 400:
                    resp.raise_for_status()
                return resp.text, resp.url, status
            except (SSLError, ConnectionError, Timeout, HTTPError, RequestException) as e:
                last_error = e
                self.logger.warning(
                    "Bahamut 請求失敗（attempt=%s/3）url=%s err=%s",
                    attempt,
                    url,
                    e,
                )
                if attempt < 3:
                    human_sleep(1.0 * attempt, 1.5 * attempt)

        raise RuntimeError(f"Bahamut 抓取失敗（重試耗盡）: {url} err={last_error}")

    def _is_gate_page(self, final_url: str, html: str) -> bool:
        text = html or ""
        lower_url = (final_url or "").lower()
        if "a.php" in lower_url:
            return True
        gate_keywords = ["進入看板", "進板圖", "forum.gamer.com.tw/a.php"]
        if any(k in text for k in gate_keywords):
            # 若已經有文章列表關鍵節點，則不視為 gate
            if self._has_board_list_selector(html):
                return False
            return True
        return False

    def _has_board_list_selector(self, html: str) -> bool:
        soup = BeautifulSoup(html, "html.parser")
        selectors = [
            "a.b-list__main__title",
            "div.b-list__row",
            "a[href*='C.php?bsn=']",
        ]
        return any(soup.select_one(sel) for sel in selectors)

    def _extract_gate_target(self, final_url: str, html: str) -> Optional[str]:
        soup = BeautifulSoup(html, "html.parser")

        # 優先找含「進入看板」語意按鈕
        for a in soup.select("a[href]"):
            txt = a.get_text(" ", strip=True)
            href = (a.get("href") or "").strip()
            if not href:
                continue
            if "進入" in txt or "看板" in txt or "B.php?bsn=" in href:
                return urljoin(final_url, href)

        # 次選：找任何回到 B.php 的連結
        for a in soup.select("a[href*='B.php?bsn=']"):
            href = (a.get("href") or "").strip()
            if href:
                return urljoin(final_url, href)

        return None

    def _build_board_page_url(self, board_url: str, page: int) -> str:
        parsed = urlparse(board_url)
        query = parse_qs(parsed.query)
        query["page"] = [str(page)]
        query_string = urlencode(query, doseq=True)
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, query_string, parsed.fragment))

    def _parse_post_id_from_url(self, url: str) -> str:
        if not url:
            return ""
        parsed = urlparse(url)
        q = parse_qs(parsed.query)
        for key in ["snA", "sna", "sn"]:
            if q.get(key):
                return q[key][0]

        # fallback：取最後一段數字
        m = re.search(r"(\d{4,})", url)
        return m.group(1) if m else ""

    def _parse_userid_from_home_url(self, url: str) -> str:
        if not url:
            return ""
        parsed = urlparse(url)
        path = parsed.path.strip("/")
        parts = path.split("/")
        if parts and parts[-1]:
            return parts[-1]
        return ""

    def _ensure_board_access(self, session: requests.Session, board_url: str) -> Dict[str, Any]:
        """處理進版圖 gate，成功後回傳可用 board html 與 final_url"""
        html, final_url, status = self._fetch_html(session, board_url)
        debug_steps: List[Dict[str, Any]] = [{"url": final_url, "status": status, "is_gate": self._is_gate_page(final_url, html)}]

        hops = 0
        while self._is_gate_page(final_url, html) and hops < self.gate_max_hops:
            target = self._extract_gate_target(final_url, html)
            if not target:
                return {
                    "ok": False,
                    "final_url": final_url,
                    "status_code": status,
                    "is_gate": True,
                    "gate_steps": debug_steps,
                    "raw_html_preview": (html or "")[:3000],
                }

            hops += 1
            html, final_url, status = self._fetch_html(session, target, referer=final_url)
            debug_steps.append({"url": final_url, "status": status, "is_gate": self._is_gate_page(final_url, html)})

        if self._is_gate_page(final_url, html):
            return {
                "ok": False,
                "final_url": final_url,
                "status_code": status,
                "is_gate": True,
                "gate_steps": debug_steps,
                "raw_html_preview": (html or "")[:3000],
            }

        return {
            "ok": True,
            "final_url": final_url,
            "status_code": status,
            "is_gate": False,
            "gate_steps": debug_steps,
            "html": html,
        }

    def _extract_list_articles(self, html: str) -> List[Dict[str, Any]]:
        soup = BeautifulSoup(html, "html.parser")
        articles: List[Dict[str, Any]] = []

        rows = soup.select("tr.b-list__row.b-list-item")
        for row in rows:
            title_node = row.select_one("td.b-list__main a.b-list__main__title")
            if not title_node:
                title_node = row.select_one("td.b-list__main a[href*='C.php?bsn=']")
            if not title_node:
                continue

            href = (title_node.get("href") or "").strip()
            title = title_node.get_text(" ", strip=True)
            if not href or not title:
                continue

            full_url = urljoin("https://forum.gamer.com.tw/", href)
            row_text = row.get_text(" ", strip=True)

            author_link = row.select_one(".b-list__count__user a[href]")
            last_reply_user_link = row.select_one(".b-list__time__user a[href]")
            time_link = row.select_one(".b-list__time__edittime a")
            sort_link = row.select_one(".b-list__summary__sort a")

            article = {
                "post_id": self._parse_post_id_from_url(full_url),
                "title": title,
                "url": full_url,
                "author": (author_link.get_text(" ", strip=True) if author_link else ""),
                "author_user_id": self._parse_userid_from_home_url(author_link.get("href", "")) if author_link else "",
                "last_reply_user": (last_reply_user_link.get_text(" ", strip=True) if last_reply_user_link else ""),
                "last_reply_user_id": self._parse_userid_from_home_url(last_reply_user_link.get("href", "")) if last_reply_user_link else "",
                "published_at": "",
                "category": (sort_link.get_text(" ", strip=True) if sort_link else ""),
                "raw_list_text": row_text[:500],
                "is_sticky": bool(row.select_one(".b-list__row--sticky, .b-mark--update[title='置頂']")),
            }

            if time_link:
                article["published_at"] = time_link.get_text(" ", strip=True)

            articles.append(article)

        # 去重
        deduped: List[Dict[str, Any]] = []
        seen = set()
        for item in articles:
            key = item.get("post_id") or item.get("url")
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(item)

        return deduped

    def _parse_comment_text_fallback(self, raw_text: str) -> Dict[str, str]:
        text = " ".join((raw_text or "").split())
        floor_match = re.search(r"\b(B\d+)\b", text)
        time_match = re.search(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?: 編輯)?)", text)

        floor = floor_match.group(1) if floor_match else ""
        published_at = time_match.group(1) if time_match else ""

        body = text.lstrip(" ").strip()
        if floor and floor in body:
            body = body.split(floor, 1)[0].strip()

        user_name = ""
        content = body
        if body:
            parts = body.split(" ", 1)
            user_name = parts[0].strip()
            content = parts[1].strip() if len(parts) > 1 else ""

        return {
            "user_name": user_name,
            "published_at": published_at,
            "floor": floor,
            "content": content,
        }

    def _extract_comment_content_from_node(self, node: BeautifulSoup) -> str:
        """盡量從留言 DOM 萃取乾淨內容，避免把 HOT / floor / 時間混進正文。"""
        selectors = [
            ".reply-content__cont",
            ".comment-content",
            ".comment_content",
            ".reply-content__article",
            ".content",
        ]

        for sel in selectors:
            content_node = node.select_one(sel)
            if content_node:
                content_clone = BeautifulSoup(str(content_node), "html.parser")
                for removable in content_clone.select(
                    ".comment_hot-tag, [name='comment_floor'], .edittime, time, .reply_time, .comment_time"
                ):
                    removable.decompose()

                text = content_clone.get_text("\n", strip=True).strip()
                if text:
                    return text

        return ""

    def _normalize_comment_text(self, text: str) -> str:
        """將巴哈 material icon 特殊字元轉成較可讀的 emoji。"""
        if not text:
            return ""
        normalized = text.replace("", "👍").replace("", "👎")
        return normalized.strip()

    def _extract_comment_reaction_meta(self, node: BeautifulSoup) -> Dict[str, Any]:
        """用較安全的 DOM 規則辨識推/噓按鈕，而非只靠 icon 字元。"""
        gp_button = node.select_one(
            "button.gp, button[onclick*='commentGp'], button[title*='推一個']"
        )
        bp_button = node.select_one(
            "button.bp, button[onclick*='commentBp'], button[title*='我要噓']"
        )

        return {
            "has_thumbsup_button": bool(gp_button),
            "has_thumbsdown_button": bool(bp_button),
            "thumbsup_emoji": "👍" if gp_button else "",
            "thumbsdown_emoji": "👎" if bp_button else "",
        }

    def _extract_comment_published_at_from_node(self, node: BeautifulSoup, raw_text: str = "") -> str:
        """從 DOM 或 raw_text 抓留言時間，避免誤抓到樓層。"""
        time_node = node.select_one(".edittime[data-tippy-content]") or node.select_one(".edittime") or node.select_one("time")
        if time_node:
            candidate = (time_node.get("data-tippy-content") or time_node.get_text(" ", strip=True)).strip()
            if re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", candidate):
                return candidate

        parsed = self._parse_comment_text_fallback(raw_text)
        return parsed.get("published_at", "")

    def fetch_board_articles(self, session: requests.Session) -> Dict[str, Any]:
        preheat = self._ensure_board_access(session, self.target_board_url)
        if not preheat.get("ok"):
            return {
                "ok": False,
                "board_url": self.target_board_url,
                "error": "board_gate_not_passed",
                "gate": preheat,
                "articles": [],
            }

        page_results: List[Dict[str, Any]] = []
        merged_articles: List[Dict[str, Any]] = []
        seen = set()

        for page in range(1, self.board_pages + 1):
            page_url = self._build_board_page_url(self.target_board_url, page)
            html, final_url, status = self._fetch_html(session, page_url, referer=preheat.get("final_url"))
            is_gate = self._is_gate_page(final_url, html)
            if is_gate:
                gate_result = self._ensure_board_access(session, page_url)
                if not gate_result.get("ok"):
                    page_results.append({
                        "page": page,
                        "url": page_url,
                        "ok": False,
                        "status_code": status,
                        "is_gate": True,
                        "gate_steps": gate_result.get("gate_steps", []),
                    })
                    continue
                html = gate_result.get("html", "")
                final_url = gate_result.get("final_url", final_url)
                status = gate_result.get("status_code", status)

            page_articles = self._extract_list_articles(html)
            added = 0
            for item in page_articles:
                key = item.get("post_id") or item.get("url")
                if key in seen:
                    continue
                seen.add(key)
                merged_articles.append(item)
                added += 1

            page_results.append({
                "page": page,
                "url": page_url,
                "final_url": final_url,
                "status_code": status,
                "article_count": len(page_articles),
                "added_count": added,
                "ok": True,
            })

        return {
            "ok": True,
            "board_url": self.target_board_url,
            "gate": preheat,
            "page_count": len(page_results),
            "article_count": len(merged_articles),
            "articles": merged_articles,
            "page_results": page_results,
        }

    def _extract_article_content(self, soup: BeautifulSoup) -> str:
        selectors = [
            ".c-article__content",
            ".c-post__body",
            "#article-content",
            ".post-content",
            "article",
        ]

        for sel in selectors:
            node = soup.select_one(sel)
            if node:
                return node.get_text("\n", strip=True)

        # fallback：擷取較可能是主文區的大段內容
        body = soup.select_one("body")
        if not body:
            return ""
        txt = body.get_text("\n", strip=True)
        return txt[:3000]

    def _extract_article_images(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        """保留主文內圖片 URL，供 JSON / 後續 Discord 呈現使用。"""
        root_selectors = [
            ".c-article__content",
            ".c-post__body",
            "#article-content",
            ".post-content",
            "article",
        ]

        article_root = None
        for sel in root_selectors:
            article_root = soup.select_one(sel)
            if article_root:
                break

        if not article_root:
            return []

        # 重要：先移除留言/回覆區，避免把回覆文章圖片誤當主文圖片
        root_clone = BeautifulSoup(str(article_root), "html.parser")
        for removable in root_clone.select(
            ".c-reply__item, .reply-content, .comment-list, .c-post__footer__reply, .webview_commendlist, [id^='Commendlist_']"
        ):
            removable.decompose()

        image_urls: List[str] = []
        seen = set()
        for node in root_clone.select("img"):
            raw_url = (
                node.get("data-src")
                or node.get("data-original")
                or node.get("src")
                or ""
            ).strip()
            if not raw_url:
                continue
            full_url = urljoin(base_url, raw_url)
            if full_url in seen:
                continue
            seen.add(full_url)
            image_urls.append(full_url)

        return image_urls

    def _extract_block_sn(self, block: BeautifulSoup) -> str:
        block_id = (block.get("id") or "").strip()
        match = re.search(r"post_(\d+)$", block_id)
        if match:
            return match.group(1)

        floor_link = block.select_one("a.floor[href*='sn=']")
        if floor_link:
            href = floor_link.get("href", "")
            parsed = parse_qs(urlparse(href).query)
            if parsed.get("sn"):
                return parsed["sn"][0]

        return ""

    def _extract_block_published_at(self, block: BeautifulSoup) -> str:
        time_node = block.select_one(".c-post__header__info .edittime[data-mtime]")
        if time_node and time_node.get("data-mtime"):
            return time_node.get("data-mtime", "").strip()

        time_node = block.select_one(".c-post__header__info .edittime[data-tippy-content]")
        if time_node:
            return time_node.get("data-tippy-content", "").strip()

        time_node = block.select_one("time, .edittime, .publish-time")
        return time_node.get_text(" ", strip=True) if time_node else ""

    def _extract_block_title(self, block: BeautifulSoup) -> str:
        title_node = block.select_one("h1.c-post__header__title, h1, .c-article__title, .title")
        return title_node.get_text(" ", strip=True) if title_node else ""

    def _extract_article_blocks(
        self,
        session: requests.Session,
        soup: BeautifulSoup,
        article_url: str,
        final_url: str,
        bsn: str,
    ) -> List[Dict[str, Any]]:
        blocks: List[Dict[str, Any]] = []

        for idx, block in enumerate(soup.select("section.c-section[id^='post_']"), start=1):
            sn = self._extract_block_sn(block)
            author_node = block.select_one(".c-post__header__author .userid")
            author_name_node = block.select_one(".c-post__header__author .username")
            html_comments = self._extract_comments(block)
            snb = self._extract_comment_snB(str(block)) or sn
            xhr_comments = self._fetch_comments_via_xhr(
                session,
                bsn=bsn,
                snb=snb,
                referer=final_url or article_url,
            )

            comments = []
            seen_comment_ids = set()
            for item in html_comments + xhr_comments:
                cid = item.get("comment_id") or ""
                if cid and cid in seen_comment_ids:
                    continue
                if cid:
                    seen_comment_ids.add(cid)
                comments.append(item)

            blocks.append(
                {
                    "sn": sn,
                    "position": idx,
                    "title": self._extract_block_title(block),
                    "author": author_name_node.get_text(" ", strip=True) if author_name_node else "",
                    "author_id": author_node.get_text(" ", strip=True) if author_node else "",
                    "published_at": self._extract_block_published_at(block),
                    "content": self._extract_article_content(block),
                    "content_images": self._extract_article_images(block, base_url=final_url or article_url),
                    "content_length": len(self._extract_article_content(block)),
                    "comments": comments,
                    "comments_count": len(comments),
                    "comment_fetch_probe": {
                        "snB": snb,
                        "html_comments_count": len(html_comments),
                        "xhr_comments_count": len(xhr_comments),
                    },
                }
            )

        return blocks

    def _extract_comments(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        comments: List[Dict[str, Any]] = []
        selectors = [
            ".c-reply__item",
            ".reply-content",
            ".comment-list .comment",
            ".c-post__footer__reply li",
        ]

        nodes = []
        for sel in selectors:
            nodes = soup.select(sel)
            if nodes:
                break

        for idx, node in enumerate(nodes, start=1):
            comment_dom_id = (node.get("id") or "").strip()
            comment_id_match = re.search(r"(\d+)$", comment_dom_id)
            comment_id = comment_id_match.group(1) if comment_id_match else str(idx)

            user_node = node.select_one(".userid, .username, [data-userid]")
            user_link = node.select_one("a[href*='home.gamer.com.tw']")
            hot_tag_node = node.select_one(".comment_hot-tag")
            raw_text = self._normalize_comment_text(node.get_text(" ", strip=True)[:500])
            parsed = self._parse_comment_text_fallback(raw_text)
            content_text = self._normalize_comment_text(
                self._extract_comment_content_from_node(node) or parsed.get("content", raw_text[:200])
            )
            published_at = self._extract_comment_published_at_from_node(node, raw_text=raw_text)
            reaction_meta = self._extract_comment_reaction_meta(node)

            comments.append(
                {
                    "comment_id": comment_id,
                    "position": idx,
                    "floor": parsed.get("floor", ""),
                    "user_id": (
                        user_node.get("data-userid", "") if user_node and user_node.get("data-userid")
                        else self._parse_userid_from_home_url(user_link.get("href", "")) if user_link
                        else ""
                    ),
                    "user_name": (
                        user_node.get_text(" ", strip=True) if user_node else parsed.get("user_name", "")
                    ),
                    "content": content_text,
                    "is_hot": bool(hot_tag_node and hot_tag_node.get_text(" ", strip=True).upper() == "HOT"),
                    "published_at": published_at,
                    "raw_text": raw_text,
                    **reaction_meta,
                }
            )

        return comments

    def _extract_comment_snB(self, html: str) -> str:
        """從文章頁 HTML 解析留言串 snB（for moreCommend.php）"""
        if not html:
            return ""

        m = re.search(r'id="Commendlist_(\d+)"', html)
        if m:
            return m.group(1)

        m = re.search(r'"snB"\s*:\s*(\d+)', html)
        if m:
            return m.group(1)

        return ""

    def _fetch_comments_via_xhr(
        self,
        session: requests.Session,
        bsn: str,
        snb: str,
        referer: str,
    ) -> List[Dict[str, Any]]:
        """透過 moreCommend.php 取回折疊/延遲載入留言"""
        if not bsn or not snb:
            return []

        endpoint = "https://forum.gamer.com.tw/ajax/moreCommend.php"
        snc: int = 0
        page = 0
        fetched: List[Dict[str, Any]] = []
        seen_ids = set()

        while page < 30:  # 安全上限
            page += 1
            params = {
                "bsn": bsn,
                "snB": snb,
                "returnHtml": "1",
            }
            if snc:
                params["snC"] = str(snc)

            try:
                resp = session.get(
                    endpoint,
                    params=params,
                    headers={
                        "User-Agent": self._get_user_agent(),
                        "Accept": "application/json, text/javascript, */*; q=0.01",
                        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
                        "X-Requested-With": "XMLHttpRequest",
                        "Referer": referer,
                    },
                    timeout=self.timeout,
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                self.logger.warning("Bahamut XHR 留言抓取失敗: bsn=%s snB=%s snC=%s err=%s", bsn, snb, snc, e)
                break

            html_blocks = data.get("html") or []
            if not html_blocks:
                break

            idx_base = len(fetched)
            for i, block in enumerate(html_blocks, start=1):
                block_soup = BeautifulSoup(block, "html.parser")
                node = block_soup.select_one(".c-reply__item")
                if not node:
                    continue

                comment_dom_id = (node.get("id") or "").strip()
                comment_id_match = re.search(r"(\d+)$", comment_dom_id)
                comment_id = comment_id_match.group(1) if comment_id_match else str(idx_base + i)
                if comment_id in seen_ids:
                    continue
                seen_ids.add(comment_id)

                user_link = node.select_one("a.reply-content__user[href]") or node.select_one("a[href*='home.gamer.com.tw']")
                hot_tag_node = node.select_one(".comment_hot-tag")
                floor_node = node.select_one("[name='comment_floor']")
                raw_text = self._normalize_comment_text(node.get_text(" ", strip=True)[:500])
                content_text = self._normalize_comment_text(self._extract_comment_content_from_node(node))
                published_at = self._extract_comment_published_at_from_node(node, raw_text=raw_text)
                reaction_meta = self._extract_comment_reaction_meta(node)

                fetched.append(
                    {
                        "comment_id": comment_id,
                        "position": idx_base + i,
                        "floor": (floor_node.get_text(" ", strip=True) if floor_node else ""),
                        "user_id": self._parse_userid_from_home_url(user_link.get("href", "")) if user_link else "",
                        "user_name": user_link.get_text(" ", strip=True) if user_link else "",
                        "content": content_text,
                        "is_hot": bool(hot_tag_node and hot_tag_node.get_text(" ", strip=True).upper() == "HOT"),
                        "published_at": published_at,
                        "raw_text": raw_text,
                        "source": "xhr_moreCommend",
                        **reaction_meta,
                    }
                )

            next_snc = data.get("next_snC")
            if not next_snc:
                break
            try:
                snc = int(next_snc)
            except Exception:
                break

            human_sleep(0.15, 0.35)

        return fetched

    def fetch_article_detail(self, session: requests.Session, article_url: str) -> Dict[str, Any]:
        html, final_url, status = self._fetch_html(session, article_url, referer=self.target_board_url)
        soup = BeautifulSoup(html, "html.parser")

        bsn = parse_qs(urlparse(self.target_board_url).query).get("bsn", [""])[0]
        blocks = self._extract_article_blocks(session, soup, article_url, final_url, bsn)

        root_post = blocks[0] if blocks else {}
        replies = blocks[1:] if len(blocks) > 1 else []
        post_id = self._parse_post_id_from_url(final_url or article_url)
        sn_a = parse_qs(urlparse(final_url or article_url).query).get("snA", [post_id])[0]

        return {
            "ok": True,
            "url": article_url,
            "final_url": final_url,
            "status_code": status,
            "post_id": post_id,
            "snA": sn_a,
            "sn": root_post.get("sn", ""),
            "position": root_post.get("position", 1),
            "title": root_post.get("title", ""),
            "author": root_post.get("author", ""),
            "author_id": root_post.get("author_id", ""),
            "published_at": root_post.get("published_at", ""),
            "content": root_post.get("content", ""),
            "content_images": root_post.get("content_images", []),
            "content_length": root_post.get("content_length", 0),
            "comments": root_post.get("comments", []),
            "comments_count": root_post.get("comments_count", 0),
            "replies": replies,
            "replies_count": len(replies),
            "raw": {
                "html_preview": html[:3000],
                "reply_probe": {
                    "has_reply_block": len(replies) > 0,
                    "reply_block_count": len(replies),
                    "note": "目前已切出 post + replies 結構，每個 block 各自帶 comments",
                },
                "block_count": len(blocks),
            },
        }

    def fetch_bahamut_articles_with_content(self) -> Dict[str, Any]:
        with self._build_session() as session:
            base = self.fetch_board_articles(session)
            if not base.get("ok"):
                return base

            detailed_count = 0
            for article in base.get("articles", []):
                url = article.get("url", "")
                if not url:
                    continue
                try:
                    human_sleep(*self.human_delay_range)
                    detail = self.fetch_article_detail(session, url)
                    if not detail.get("ok"):
                        continue

                    article["title"] = detail.get("title") or article.get("title")
                    article["author"] = detail.get("author") or article.get("author")
                    article["published_at"] = detail.get("published_at") or article.get("published_at")
                    article["content"] = detail.get("content", "")
                    article["content_images"] = detail.get("content_images", [])
                    article["content_length"] = detail.get("content_length", 0)
                    article["comments"] = detail.get("comments", [])
                    article["comments_count"] = detail.get("comments_count", 0)
                    article["sn"] = detail.get("sn", "")
                    article["position"] = detail.get("position", 1)
                    article["replies"] = detail.get("replies", [])
                    article["replies_count"] = detail.get("replies_count", 0)
                    article["snA"] = detail.get("snA", "")
                    article["raw"] = detail.get("raw", {})
                    detailed_count += 1
                except Exception as e:
                    self.logger.warning("抓取巴哈文章詳情失敗: url=%s err=%s", url, e)

            base["detailed_count"] = detailed_count
            base["fetched_at"] = datetime.now().isoformat()
            return base

    def build_article_url_by_post_id(self, post_id: str) -> str:
        bsn = parse_qs(urlparse(self.target_board_url).query).get("bsn", [""])[0]
        return f"https://forum.gamer.com.tw/C.php?bsn={bsn}&snA={post_id}"

    def fetch_single_bahamut_article(self, post_id: str) -> Dict[str, Any]:
        """只抓指定 snA 單篇文章，方便除錯與驗證 parser。"""
        article_url = self.build_article_url_by_post_id(post_id)
        with self._build_session() as session:
            detail = self.fetch_article_detail(session, article_url)
            if not detail.get("ok"):
                return detail

            result = {
                "ok": True,
                "article_count": 1,
                "detailed_count": 1,
                "fetched_at": datetime.now().isoformat(),
                "articles": [
                    {
                        "source_type": "bahamut",
                        "post_id": detail.get("post_id", post_id),
                        "title": detail.get("title", ""),
                        "snA": detail.get("snA", post_id),
                        "url": detail.get("url", article_url),
                        "final_url": detail.get("final_url", article_url),
                        "author": detail.get("author", ""),
                        "author_id": detail.get("author_id", ""),
                        "published_at": detail.get("published_at", ""),
                        "content": detail.get("content", ""),
                        "content_images": detail.get("content_images", []),
                        "content_length": detail.get("content_length", 0),
                        "comments": detail.get("comments", []),
                        "comments_count": detail.get("comments_count", 0),
                        "sn": detail.get("sn", ""),
                        "position": detail.get("position", 1),
                        "replies": detail.get("replies", []),
                        "replies_count": detail.get("replies_count", 0),
                        "raw": detail.get("raw", {}),
                    }
                ],
            }
            return result

    def export_sample_json(self, result: Dict[str, Any]) -> str:
        os.makedirs(self.sample_output_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = os.path.join(self.sample_output_dir, f"bahamut_sample_{ts}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        return out_path


def main():
    parser = argparse.ArgumentParser(description="Bahamut scraper sample exporter")
    parser.add_argument(
        "--sna",
        dest="sn_a",
        required=False,
        help="指定主文 ID（snA），只抓單篇文章；bsn 預設沿用設定檔中的 74934",
    )
    args = parser.parse_args()

    service = BahamutScraperService()
    target_sn_a = args.sn_a
    if target_sn_a:
        result = service.fetch_single_bahamut_article(target_sn_a)
    else:
        result = service.fetch_bahamut_articles_with_content()
    out = service.export_sample_json(result)
    print(json.dumps({
        "ok": result.get("ok"),
        "article_count": result.get("article_count", 0),
        "detailed_count": result.get("detailed_count", 0),
        "output": out,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
