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

from bs4 import BeautifulSoup

# 讓此檔案可被單檔直接執行（與 ptt_scraper_service.py 一致）
# python services/bahamut_scraper_service.py 時，將 /app 加入 sys.path
SCRAPER_ROOT = os.path.dirname(os.path.dirname(__file__))
if SCRAPER_ROOT not in sys.path:
    sys.path.insert(0, SCRAPER_ROOT)

from config import BAHAMUT_CONFIG
from utils.logger import get_logger
from utils.request_utils import human_sleep
from services.base_scraper_client import BaseScraperClient

logger = get_logger("bahamut_scraper")


class BahamutScraperService(BaseScraperClient):
    """Bahamut 爬蟲服務（MVP）"""

    def __init__(self, db_manager=None):
        super().__init__()
        self.logger = get_logger("bahamut_scraper")
        self.db_manager = db_manager

        self.target_board_url = BAHAMUT_CONFIG["target_board_url"]
        subbsn = BAHAMUT_CONFIG.get("subbsn", "").strip()
        if subbsn:
            sep = "&" if "?" in self.target_board_url else "?"
            self.target_board_url = f"{self.target_board_url}{sep}subbsn={subbsn}"
        self.timeout = int(BAHAMUT_CONFIG.get("timeout", 20) or 20)
        self.board_start_page = max(1, int(BAHAMUT_CONFIG.get("board_start_page", 1) or 1))
        self.board_end_page = max(1, int(BAHAMUT_CONFIG.get("board_end_page", 1) or 1))
        self.max_articles_per_page = max(1, int(BAHAMUT_CONFIG.get("max_articles_per_page", 30) or 30))
        self.gate_max_hops = max(1, int(BAHAMUT_CONFIG.get("gate_max_hops", 3) or 3))
        self.human_delay_range = BAHAMUT_CONFIG.get("human_delay_min", (0.35, 0.9))
        self.page_delay_range = BAHAMUT_CONFIG.get("page_delay_range", (2, 5))
        self.sample_output_dir = BAHAMUT_CONFIG.get("sample_output_dir", "data/bahamut_samples")

    def _build_headers(self, referer: Optional[str] = None) -> Dict[str, str]:
        """巴哈頁面請求 headers（delegate 給 BaseScraperClient）"""
        return self._build_page_headers(referer=referer)

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

    # _build_session 繼承自 BaseScraperClient（curl_cffi + TLS 指紋模擬）

    def _fetch_html(
        self,
        session,
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
                    self._current_impersonate,
                    self._build_headers(referer=referer).get("Sec-CH-UA", "N/A"),
                    {k: v for k, v in session.cookies.items()},
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

                had_cknomobile = bool(session.cookies.get("ckNOMOBILE"))

                if redirected_to_mobile and not had_cknomobile:
                    session.cookies.set("ckNOMOBILE", "1", domain=".gamer.com.tw")
                    self.logger.info("Bahamut 偵測到 desktop->mobile 302，補寫 cookie: ckNOMOBILE=1")

                desktop_url = self._to_desktop_forum_url(resp.url)
                if desktop_url != resp.url:
                    if had_cknomobile:
                        self.logger.warning(
                            "Bahamut 已有 ckNOMOBILE cookie 仍被導向手機版，強制改抓 desktop 版: %s -> %s",
                            resp.url,
                            desktop_url,
                        )
                    else:
                        self.logger.info(
                            "Bahamut 首次被導向手機版，已補 cookie，並改以 desktop URL 重新請求: %s -> %s",
                            resp.url,
                            desktop_url,
                        )
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

                    if urlparse(resp.url).netloc == "m.gamer.com.tw":
                        self.logger.warning(
                            "Bahamut 補寫 ckNOMOBILE 並重試 desktop 後，仍落在手機版: request_url=%s final_url=%s",
                            desktop_url,
                            resp.url,
                        )

                status = resp.status_code
                if status >= 400:
                    resp.raise_for_status()
                return resp.text, resp.url, status
            except Exception as e:
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

    def _ensure_board_access(self, session, board_url: str) -> Dict[str, Any]:
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

    def _parse_count_from_element(self, node) -> int:
        """從 DOM 元素取得數字（GP/BP 計數），取不到回 0。"""
        if not node:
            return 0
        text = node.get_text(" ", strip=True)
        match = re.search(r"(\d+)", text)
        return int(match.group(1)) if match else 0

    def _extract_gp_bp_from_raw_text(self, raw_text: str) -> Tuple[int, int]:
        """從 raw_text 的 👍 N 👎 模式提取 GP/BP 數字作為 fallback。"""
        gp = 0
        bp = 0
        gp_match = re.search(r"👍\s*(\d+)", raw_text or "")
        bp_match = re.search(r"👎\s*(\d+)", raw_text or "")
        if gp_match:
            gp = int(gp_match.group(1))
        if bp_match:
            bp = int(bp_match.group(1))
        return gp, bp

    def _extract_comment_reaction_meta(self, node: BeautifulSoup, raw_text: str = "") -> Dict[str, Any]:
        """從留言 DOM 提取 GP/BP 數字。

        留言 DOM 結構：
        <a data-gp="105" class="gp-count">105</a>
        <a data-bp="0" class="bp-count"></a>
        """
        gp_count = 0
        bp_count = 0

        # 優先從 data-gp / data-bp 屬性取（最可靠）
        gp_node = node.select_one("a.gp-count[data-gp]")
        bp_node = node.select_one("a.bp-count[data-bp]")

        if gp_node:
            try:
                gp_count = int(gp_node.get("data-gp", "0"))
            except (ValueError, TypeError):
                gp_count = self._parse_count_from_element(gp_node)

        if bp_node:
            try:
                bp_count = int(bp_node.get("data-bp", "0"))
            except (ValueError, TypeError):
                bp_count = self._parse_count_from_element(bp_node)

        # fallback：從 raw_text 的 👍 N 👎 模式取
        if gp_count == 0 and bp_count == 0 and raw_text:
            gp_count, bp_count = self._extract_gp_bp_from_raw_text(raw_text)

        return {
            "gp_count": gp_count,
            "bp_count": bp_count,
        }

    def _extract_block_gp_bp(self, block: BeautifulSoup) -> Tuple[int, int]:
        """從文章 block 提取 GP/BP 數。

        巴哈 DOM 結構：
        <div class="gp">
            <button ...>...</button>
            <a class="count ...">249</a>   ← GP 數字在這
        </div>
        <div class="bp">
            <button ...>...</button>
            <a class="count ...">-</a>     ← BP 數字在這，"-" 表示 0
        </div>
        """
        gp = 0
        bp = 0

        gp_div = block.select_one("div.gp")
        if gp_div:
            count_node = gp_div.select_one("a.count")
            gp = self._parse_count_from_element(count_node)

        bp_div = block.select_one("div.bp")
        if bp_div:
            count_node = bp_div.select_one("a.count")
            bp = self._parse_count_from_element(count_node)

        return gp, bp

    def _clean_published_at(self, raw: str) -> str:
        """清除 published_at 中的非時間前綴（如「留言時間 」），只保留 datetime 字串。"""
        if not raw:
            return ""
        match = re.search(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", raw)
        return match.group(1) if match else raw.strip()

    def _extract_comment_published_at_from_node(self, node: BeautifulSoup, raw_text: str = "") -> str:
        """從 DOM 或 raw_text 抓留言時間，避免誤抓到樓層。"""
        time_node = node.select_one(".edittime[data-tippy-content]") or node.select_one(".edittime") or node.select_one("time")
        if time_node:
            candidate = (time_node.get("data-tippy-content") or time_node.get_text(" ", strip=True)).strip()
            if re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", candidate):
                return self._clean_published_at(candidate)

        parsed = self._parse_comment_text_fallback(raw_text)
        return self._clean_published_at(parsed.get("published_at", ""))

    def _parse_floor_number(self, floor_text: str) -> int:
        """將 B43 之類樓層轉成可排序數字；失敗則回傳極大值。"""
        if not floor_text:
            return 10**9

        match = re.search(r"B(\d+)", floor_text.strip(), re.IGNORECASE)
        if not match:
            return 10**9

        try:
            return int(match.group(1))
        except Exception:
            return 10**9

    def _parse_comment_id_number(self, comment_id: str) -> int:
        """將 comment_id 轉成可排序數字；允許跳號，但可用來判斷 asc。"""
        if not comment_id:
            return 10**9

        match = re.search(r"(\d+)", str(comment_id).strip())
        if not match:
            return 10**9

        try:
            return int(match.group(1))
        except Exception:
            return 10**9

    def _merge_and_normalize_comments(
        self,
        html_comments: List[Dict[str, Any]],
        xhr_comments: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        合併 HTML 與 moreCommend 留言，並重新編排 position。

        原則：
        1. 若 XHR 有資料，優先採用 XHR（通常較完整，避免先吃到未展開前 HTML 造成 position 偏移）
        2. 保留 HTML 中 XHR 沒抓到的留言作補集
        3. 最後依 floor 重新排序並重編 position，避免 HTML / XHR 各自獨立編碼造成重複或錯位
        """
        merged_by_id: Dict[str, Dict[str, Any]] = {}
        fallback_comments: List[Dict[str, Any]] = []

        for item in xhr_comments:
            cid = (item.get("comment_id") or "").strip()
            if cid:
                merged_by_id[cid] = dict(item)
            else:
                fallback_comments.append(dict(item))

        for item in html_comments:
            cid = (item.get("comment_id") or "").strip()
            if cid:
                if cid not in merged_by_id:
                    merged_by_id[cid] = dict(item)
            else:
                fallback_comments.append(dict(item))

        merged_comments = list(merged_by_id.values()) + fallback_comments
        merged_comments.sort(
            key=lambda item: (
                self._parse_floor_number(str(item.get("floor", ""))),
                self._parse_comment_id_number(str(item.get("comment_id", ""))),
                str(item.get("comment_id", "")),
            )
        )

        for idx, item in enumerate(merged_comments, start=1):
            item["position"] = idx

        return merged_comments

    def fetch_board_articles(self, session) -> Dict[str, Any]:
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
        total_pages = self.board_end_page - self.board_start_page + 1

        for page in range(self.board_start_page, self.board_end_page + 1):
            # 頁與頁之間加延遲（第一頁不用等）
            if page > self.board_start_page:
                human_sleep(*self.page_delay_range)
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

            self.logger.info(
                "Bahamut 列表進度: page %s/%s done, 本頁 %s 篇, 累計 %s 篇",
                page - self.board_start_page + 1,
                total_pages,
                added,
                len(merged_articles),
            )

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

        node = None
        for sel in selectors:
            node = soup.select_one(sel)
            if node:
                break

        if not node:
            body = soup.select_one("body")
            if not body:
                return ""
            txt = body.get_text("\n", strip=True)
            return txt[:3000]

        # 將嵌入式 YouTube iframe 轉為可讀連結
        for iframe in node.select("iframe[data-src*='youtube'], iframe[src*='youtube']"):
            embed_url = iframe.get("data-src") or iframe.get("src") or ""
            video_id = re.search(r'/embed/([^?&]+)', embed_url)
            if video_id:
                watch_url = f"https://www.youtube.com/watch?v={video_id.group(1)}"
                iframe.replace_with(f"\n🎬 {watch_url}\n")

        # 收集超連結 mapping（純文字 → markdown 連結）
        link_replacements = []
        for a_tag in node.select("a[href]"):
            href = a_tag.get("href", "")
            text = a_tag.get_text(strip=True)
            if not text or a_tag.select("img"):
                continue
            # 解開巴哈跳轉連結 ref.gamer.com.tw/redir.php?url=...
            if "ref.gamer.com.tw/redir.php" in href:
                from urllib.parse import parse_qs, urlparse
                parsed = parse_qs(urlparse(href).query)
                real_url = parsed.get("url", [href])[0]
            else:
                real_url = href
            # 如果顯示文字就是 URL，直接放裸 URL（Discord 自動變連結，省空間）
            if text.startswith("http://") or text.startswith("https://"):
                link_replacements.append((text, real_url))
            else:
                link_replacements.append((text, f"[{text}]({real_url})"))

        content = node.get_text("\n", strip=True)

        # 後處理：把純文字替換為 markdown 連結（由長到短避免短的先配到）
        for plain_text, md_link in sorted(link_replacements, key=lambda x: -len(x[0])):
            content = content.replace(plain_text, md_link, 1)

        # 清理殘留的裝飾角括號（get_text 後 < 和 > 跟連結在不同行）
        content = re.sub(r'<\s*\n\s*(\[.+?\]\(.+?\))\s*\n\s*>', r'\1', content)

        return content

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

    def _extract_block_ip(self, block: BeautifulSoup) -> str:
        """從 .edittime[data-hideip] 取得發文者 IP（公開資訊，末段已被巴哈遮蔽為 xxx）。"""
        node = block.select_one(".edittime[data-hideip]")
        if node:
            return node.get("data-hideip", "").strip()
        return ""

    def _extract_block_area(self, block: BeautifulSoup) -> str:
        """從 .edittime[data-area] 取得發文區域標記。"""
        node = block.select_one(".edittime[data-area]")
        if node:
            return node.get("data-area", "").strip()
        return ""

    def _extract_block_title(self, block: BeautifulSoup) -> str:
        title_node = block.select_one("h1.c-post__header__title, h1, .c-article__title, .title")
        return title_node.get_text(" ", strip=True) if title_node else ""

    def _extract_article_blocks(
        self,
        session,
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

            comments = self._merge_and_normalize_comments(html_comments, xhr_comments)
            block_gp, block_bp = self._extract_block_gp_bp(block)

            blocks.append(
                {
                    "sn": sn,
                    "position": idx,
                    "title": self._extract_block_title(block),
                    "author": author_name_node.get_text(" ", strip=True) if author_name_node else "",
                    "author_id": author_node.get_text(" ", strip=True) if author_node else "",
                    "published_at": self._extract_block_published_at(block),
                    "ip": self._extract_block_ip(block),
                    "area": self._extract_block_area(block),
                    "gp_count": block_gp,
                    "bp_count": block_bp,
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
            reaction_meta = self._extract_comment_reaction_meta(node, raw_text=raw_text)

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
        session,
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
                    headers=self._build_xhr_headers(referer),
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
                reaction_meta = self._extract_comment_reaction_meta(node, raw_text=raw_text)

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

    def _extract_article_page_count(self, soup: BeautifulSoup) -> int:
        """從文章頁的分頁列取得總頁數。

        DOM 結構：
        <p class="BH-pagebtnA">
            <a class="pagenow">1</a>
            <a href="?page=2&bsn=...">2</a>
            <a href="?page=4&bsn=...">4</a>  ← 最後一個 = 總頁數
        </p>
        """
        pager = soup.select_one("p.BH-pagebtnA")
        if not pager:
            return 1

        page_links = pager.select("a")
        max_page = 1
        for link in page_links:
            text = link.get_text(strip=True)
            if text.isdigit():
                max_page = max(max_page, int(text))
        return max_page

    def _build_article_page_url(self, article_url: str, page: int) -> str:
        """為文章 URL 加上或替換 page 參數。"""
        parsed = urlparse(article_url)
        query = parse_qs(parsed.query)
        query["page"] = [str(page)]
        query_string = urlencode(query, doseq=True)
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, query_string, parsed.fragment))

    def fetch_article_detail(self, session, article_url: str) -> Dict[str, Any]:
        fetch_start = datetime.now()

        # 第一頁
        html, final_url, status = self._fetch_html(session, article_url, referer=self.target_board_url)
        soup = BeautifulSoup(html, "html.parser")

        # 偵測是否被導到手機版
        mobile_redirect = urlparse(final_url).netloc == "m.gamer.com.tw"

        bsn = parse_qs(urlparse(self.target_board_url).query).get("bsn", [""])[0]
        total_pages = self._extract_article_page_count(soup)
        all_blocks = self._extract_article_blocks(session, soup, article_url, final_url, bsn)
        blocks_per_page = [len(all_blocks)]
        failed_pages: List[int] = []

        # 後續頁面（第 2 頁起）
        for page in range(2, total_pages + 1):
            human_sleep(*self.page_delay_range)
            page_url = self._build_article_page_url(final_url or article_url, page)
            try:
                page_html, page_final_url, page_status = self._fetch_html(session, page_url, referer=final_url)
                page_soup = BeautifulSoup(page_html, "html.parser")
                page_blocks = self._extract_article_blocks(session, page_soup, page_url, page_final_url, bsn)
                all_blocks.extend(page_blocks)
                blocks_per_page.append(len(page_blocks))
                self.logger.info(
                    "Bahamut 文章分頁進度: snA=%s page %s/%s, 本頁 %s blocks",
                    parse_qs(urlparse(article_url).query).get("snA", [""])[0],
                    page, total_pages, len(page_blocks),
                )
            except Exception as e:
                blocks_per_page.append(0)
                failed_pages.append(page)
                self.logger.warning(
                    "Bahamut 文章分頁抓取失敗: page=%s/%s url=%s err=%s",
                    page, total_pages, page_url, e,
                )

        root_post = all_blocks[0] if all_blocks else {}
        replies = all_blocks[1:] if len(all_blocks) > 1 else []

        # 重新編排所有 block 的 position（跨頁連續編號）
        for idx, block in enumerate(all_blocks, start=1):
            block["position"] = idx

        post_id = self._parse_post_id_from_url(final_url or article_url)
        sn_a = parse_qs(urlparse(final_url or article_url).query).get("snA", [post_id])[0]

        fetch_duration = (datetime.now() - fetch_start).total_seconds()

        # 抓取 metadata（存入 raw_json）
        fetch_meta = {
            "fetched_at": fetch_start.isoformat(),
            "fetch_duration_sec": round(fetch_duration, 2),
            "total_pages": total_pages,
            "blocks_per_page": blocks_per_page,
            "block_count": len(all_blocks),
            "mobile_redirect": mobile_redirect,
            "status_code": status,
        }
        if failed_pages:
            fetch_meta["failed_pages"] = failed_pages

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
            "ip": root_post.get("ip", ""),
            "area": root_post.get("area", ""),
            "gp_count": root_post.get("gp_count", 0),
            "bp_count": root_post.get("bp_count", 0),
            "published_at": root_post.get("published_at", ""),
            "content": root_post.get("content", ""),
            "content_images": root_post.get("content_images", []),
            "content_length": root_post.get("content_length", 0),
            "comments_count": root_post.get("comments_count", 0),
            "comments": root_post.get("comments", []),
            "replies": replies,
            "replies_count": len(replies),
            "total_pages": total_pages,
            "raw": fetch_meta,
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
                    article["ip"] = detail.get("ip", "")
                    article["area"] = detail.get("area", "")
                    article["gp_count"] = detail.get("gp_count", 0)
                    article["bp_count"] = detail.get("bp_count", 0)
                    article["published_at"] = detail.get("published_at") or article.get("published_at")
                    article["snA"] = detail.get("snA", "")
                    article["sn"] = detail.get("sn", "")
                    article["position"] = detail.get("position", 1)
                    article["content"] = detail.get("content", "")
                    article["content_images"] = detail.get("content_images", [])
                    article["content_length"] = detail.get("content_length", 0)
                    article["comments_count"] = detail.get("comments_count", 0)
                    article["comments"] = detail.get("comments", [])
                    article["replies"] = detail.get("replies", [])
                    article["replies_count"] = detail.get("replies_count", 0)
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
                        "post_id": detail.get("post_id", post_id),
                        "snA": detail.get("snA", post_id),
                        "sn": detail.get("sn", ""),
                        "position": detail.get("position", 1),
                        "title": detail.get("title", ""),
                        "url": detail.get("url", article_url),
                        "final_url": detail.get("final_url", article_url),
                        "author": detail.get("author", ""),
                        "author_id": detail.get("author_id", ""),
                        "ip": detail.get("ip", ""),
                        "area": detail.get("area", ""),
                        "gp_count": detail.get("gp_count", 0),
                        "bp_count": detail.get("bp_count", 0),
                        "published_at": detail.get("published_at", ""),
                        "content": detail.get("content", ""),
                        "content_images": detail.get("content_images", []),
                        "content_length": detail.get("content_length", 0),
                        "comments_count": detail.get("comments_count", 0),
                        "comments": detail.get("comments", []),
                        "replies": detail.get("replies", []),
                        "replies_count": detail.get("replies_count", 0),
                        "raw": detail.get("raw", {}),
                    }
                ],
            }
            return result

    def _get_board_id(self) -> str:
        """從設定的 target_board_url 取出 bsn"""
        return parse_qs(urlparse(self.target_board_url).query).get("bsn", [""])[0]

    def _parse_published_at(self, raw: str) -> Optional[datetime]:
        """將 published_at 字串轉為 datetime，失敗回傳 None"""
        if not raw:
            return None
        try:
            return datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            return None

    def save_articles_to_db(self, articles: List[Dict[str, Any]]) -> int:
        """將抓到的文章（含回文、留言）寫入資料庫"""
        if not self.db_manager:
            self.logger.warning("未提供 db_manager，略過 DB 寫入")
            return 0

        board_id = self._get_board_id()
        saved_count = 0
        processed_sns = set()

        for article in articles:
            try:
                # --- 主文 ---
                root_sn = article.get("sn", "")
                if not root_sn:
                    continue
                if root_sn in processed_sns:
                    continue

                if article.get("content_length", 0) <= 0 and not article.get("content_images"):
                    self.logger.info(
                        "略過無內容的巴哈文章: post_id=%s sn=%s",
                        article.get("post_id"), root_sn,
                    )
                    continue

                processed_sns.add(root_sn)

                post_data = {
                    "board_id": board_id,
                    "post_id": article.get("post_id", ""),
                    "sn": root_sn,
                    "position": 1,
                    "title": article.get("title", ""),
                    "category": article.get("category", ""),
                    "author_name": article.get("author", ""),
                    "author_id": article.get("author_id", ""),
                    "url": article.get("url", ""),
                    "ip": article.get("ip", ""),
                    "area": article.get("area", ""),
                    "gp_count": article.get("gp_count", 0),
                    "bp_count": article.get("bp_count", 0),
                    "published_at": self._parse_published_at(article.get("published_at", "")),
                    "content": article.get("content", ""),
                    "content_images": article.get("content_images", []),
                    "comments_count": article.get("comments_count", 0),
                    "replies_count": article.get("replies_count", 0),
                    "raw": article.get("raw"),
                }

                saved_post = self.db_manager.save_bahamut_post(post_data)
                if not saved_post:
                    continue
                saved_count += 1

                # 主文留言
                root_comments = article.get("comments", [])
                if root_comments:
                    self.db_manager.save_bahamut_comments(
                        saved_post.id, root_sn, root_comments,
                    )

                # --- 回文 ---
                for reply in article.get("replies", []):
                    reply_sn = reply.get("sn", "")
                    if not reply_sn or reply_sn in processed_sns:
                        continue
                    processed_sns.add(reply_sn)

                    reply_data = {
                        "board_id": board_id,
                        "post_id": article.get("post_id", ""),
                        "sn": reply_sn,
                        "position": reply.get("position", 0),
                        "title": reply.get("title", ""),
                        "category": "",
                        "author_name": reply.get("author", ""),
                        "author_id": reply.get("author_id", ""),
                        "url": article.get("url", ""),
                        "ip": reply.get("ip", ""),
                        "area": reply.get("area", ""),
                        "gp_count": reply.get("gp_count", 0),
                        "bp_count": reply.get("bp_count", 0),
                        "published_at": self._parse_published_at(reply.get("published_at", "")),
                        "content": reply.get("content", ""),
                        "content_images": reply.get("content_images", []),
                        "comments_count": reply.get("comments_count", 0),
                        "replies_count": 0,
                        "raw": None,
                    }

                    saved_reply = self.db_manager.save_bahamut_post(reply_data)
                    if not saved_reply:
                        continue
                    saved_count += 1

                    # 回文留言
                    reply_comments = reply.get("comments", [])
                    if reply_comments:
                        self.db_manager.save_bahamut_comments(
                            saved_reply.id, reply_sn, reply_comments,
                        )

            except Exception as e:
                self.logger.warning(
                    "寫入巴哈文章失敗: post_id=%s sn=%s err=%s",
                    article.get("post_id"), article.get("sn"), e,
                )

        return saved_count

    def export_sample_json(self, result: Dict[str, Any]) -> str:
        os.makedirs(self.sample_output_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = os.path.join(self.sample_output_dir, f"bahamut_sample_{ts}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        return out_path


def main():
    parser = argparse.ArgumentParser(description="Bahamut scraper CLI")
    parser.add_argument(
        "--sna",
        dest="sn_a",
        required=False,
        help="指定主文 ID（snA），只抓單篇文章；bsn 預設沿用設定檔中的 74934",
    )
    parser.add_argument(
        "--start-page",
        type=int,
        default=None,
        help="從第幾頁開始抓（覆蓋 config 的 board_start_page）",
    )
    parser.add_argument(
        "--end-page",
        type=int,
        default=None,
        help="抓到第幾頁（覆蓋 config 的 board_end_page）",
    )
    parser.add_argument(
        "--delay-multiplier",
        type=float,
        default=None,
        help="延遲倍率（例如 3 = 所有延遲 ×3，適合大量抓取避免被鎖）",
    )
    parser.add_argument(
        "--subbsn",
        type=str,
        default=None,
        help="子看板 ID（例如 13），會在 target_board_url 加上 &subbsn=N",
    )
    args = parser.parse_args()

    # 透過 container 建立帶 db_manager 的 service
    from container import ServiceContainer
    container = ServiceContainer()
    container.create_database_tables()
    service = container.create_bahamut_scraper_service()

    # CLI 參數覆蓋 config 設定
    if args.start_page is not None:
        service.board_start_page = max(1, args.start_page)
    if args.end_page is not None:
        service.board_end_page = max(service.board_start_page, args.end_page)

    if args.subbsn is not None:
        # CLI 覆蓋 config 的 subbsn：先還原到不帶 subbsn 的基礎 URL
        base_url = BAHAMUT_CONFIG["target_board_url"]
        sep = "&" if "?" in base_url else "?"
        service.target_board_url = f"{base_url}{sep}subbsn={args.subbsn}"
        logger.info("CLI 子看板模式: %s", service.target_board_url)

    if args.delay_multiplier is not None and args.delay_multiplier > 0:
        multiplier = args.delay_multiplier
        old_human = service.human_delay_range
        old_page = service.page_delay_range
        service.human_delay_range = (old_human[0] * multiplier, old_human[1] * multiplier)
        service.page_delay_range = (old_page[0] * multiplier, old_page[1] * multiplier)
        logger.info(
            "延遲倍率 %.1fx: human_delay=%.1f~%.1fs, page_delay=%.1f~%.1fs",
            multiplier,
            service.human_delay_range[0], service.human_delay_range[1],
            service.page_delay_range[0], service.page_delay_range[1],
        )

    target_sn_a = args.sn_a
    if target_sn_a:
        result = service.fetch_single_bahamut_article(target_sn_a)
    else:
        result = service.fetch_bahamut_articles_with_content()

    # 寫入資料庫
    saved_count = service.save_articles_to_db(result.get("articles", []))
    service.db_manager.commit()
    service.db_manager.close()

    # 依設定決定是否輸出 sample JSON
    output_path = None
    if BAHAMUT_CONFIG.get("export_sample_json", False):
        output_path = service.export_sample_json(result)

    print(json.dumps({
        "ok": result.get("ok"),
        "article_count": result.get("article_count", 0),
        "detailed_count": result.get("detailed_count", 0),
        "saved_count": saved_count,
        "output": output_path,
    }, ensure_ascii=False, indent=2))

    # 通知 Discord Bot
    if result.get("ok") and saved_count > 0:
        try:
            from curl_cffi import requests as curl_req
            payload = {"board_id": BAHAMUT_CONFIG.get("target_board_url", "").split("bsn=")[-1].split("&")[0] or "74934"}
            if target_sn_a:
                payload["post_id"] = target_sn_a
            curl_req.post("http://discord-bot:5000/notify/bahamut", json=payload, timeout=10)
            logger.info("已通知 Discord Bot: %s", payload)
        except Exception as e:
            logger.warning("通知 Discord Bot 失敗（不影響結果）: %s", e)


if __name__ == "__main__":
    main()
