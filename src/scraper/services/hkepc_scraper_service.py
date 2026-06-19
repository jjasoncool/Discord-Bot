"""HKEPC 系統設備 / 硬體新知爬蟲（IT快訊等 tag）。

繼承 BaseScraperClient → 自動使用 curl_cffi impersonate（TLS 指紋 + UA 輪換），不寫死 UA。

流程：
  列表頁 /tag/{tag}/page/{n} → 解析 .item 卡（標題/id/作者/日期/摘要/留言數）
  → 三層去重（L1 跑批內、L2 DB 已有 content、L3 upsert hkepc_id）
  → 內頁 /{id}/ → 全文 + 圖片來源 URL + 參考連結
  → save_hardware_news

圖片只存來源 URL（不下載），發送時由 bot 暫存下載交給 Discord CDN。
"""
import json
import re
from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup

from config import HKEPC_CONFIG
from services.base_scraper_client import BaseScraperClient
from utils.logger import get_logger
from utils.request_utils import human_sleep

# 首次種子最多翻幾頁的保險上限（避免 first_run_limit 設過大時無限翻頁）
_MAX_FIRST_RUN_PAGES = 20


class HkepcScraperService(BaseScraperClient):
    """HKEPC IT快訊 / 硬體新知爬蟲。"""

    def __init__(self, db_manager):
        super().__init__()
        self.logger = get_logger("hkepc_scraper")
        self.db_manager = db_manager
        self.base_url = HKEPC_CONFIG["base_url"].rstrip("/")
        self.tags = list(HKEPC_CONFIG.get("tags") or ["IT快訊"])
        self.pages_per_tag = max(1, int(HKEPC_CONFIG.get("pages_per_tag", 1) or 1))
        self.first_run_limit = max(1, int(HKEPC_CONFIG.get("first_run_limit", 50) or 50))
        self.timeout = HKEPC_CONFIG.get("timeout", 20)
        self.human_delay_range = HKEPC_CONFIG.get("human_delay_min", (0.35, 0.9))

    # ── URL ──
    def _listing_url(self, tag: str, page: int) -> str:
        return f"{self.base_url}/tag/{quote(tag)}/page/{page}"

    def _detail_url(self, hkepc_id: int) -> str:
        return f"{self.base_url}/{hkepc_id}/"

    # ── HTTP ──
    def _fetch_html(self, url: str) -> str:
        with self._build_session() as session:
            resp = self._fetch_with_retry(
                session,
                url,
                headers=self._build_page_headers(),
                timeout=self.timeout,
                source_name="HKEPC",
            )
            resp.raise_for_status()
            return resp.text

    # ── 解析：列表頁 ──
    @staticmethod
    def _extract_id_from_href(href: str) -> Optional[int]:
        m = re.search(r"/(\d+)/", href or "")
        return int(m.group(1)) if m else None

    @staticmethod
    def _digits(text: str) -> int:
        m = re.search(r"\d+", text or "")
        return int(m.group(0)) if m else 0

    @staticmethod
    def _parse_date(text: str) -> Optional[datetime]:
        text = (text or "").strip()
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
        if not m:
            return None
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None

    def _parse_listing(self, html: str) -> List[Dict]:
        """解析一個列表頁，回傳卡片清單。"""
        soup = BeautifulSoup(html, "html.parser")
        cards: List[Dict] = []
        for item in soup.select(".item"):
            link = item.select_one("a.heading") or item.select_one("a.left.heading") or item.select_one("a[href]")
            if not link:
                continue
            hkepc_id = self._extract_id_from_href(link.get("href", ""))
            if not hkepc_id:
                continue
            card_tags = [a.get_text(strip=True) for a in item.select(".tags a")] or \
                ([item.select_one(".tags").get_text(" ", strip=True)] if item.select_one(".tags") else [])
            cards.append({
                "hkepc_id": hkepc_id,
                "title": self._clean_space(link.get_text(" ", strip=True)),
                "url": urljoin(self.base_url + "/", link.get("href", "")),
                "author": self._clean_author(item.select_one(".author").get_text(" ", strip=True) if item.select_one(".author") else None),
                "introduction": self._clean_intro(item.select_one(".introduction")),
                "published_at": self._parse_date(item.select_one(".date").get_text() if item.select_one(".date") else ""),
                "comment_count": self._digits(item.select_one(".graph-fbCommentsCnt").get_text() if item.select_one(".graph-fbCommentsCnt") else ""),
                "card_tags": [t for t in card_tags if t],
            })
        return cards

    @staticmethod
    def _clean_space(text: Optional[str]) -> Optional[str]:
        if not text:
            return text
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _clean_author(text: Optional[str]) -> Optional[str]:
        if not text:
            return None
        text = re.sub(r"\s+", " ", text).strip()
        return re.sub(r"^文[:：]\s*", "", text) or None

    def _clean_intro(self, intro_el) -> Optional[str]:
        """摘要去掉內嵌的「文章索引： {tag}」麵包屑。"""
        if not intro_el:
            return None
        # 在副本上移除 .tags 子節點，避免動到主樹
        sub = BeautifulSoup(str(intro_el), "html.parser")
        for t in sub.select(".tags"):
            t.extract()
        text = self._clean_space(sub.get_text(" ", strip=True))
        text = re.sub(r"^文章索引[:：]\s*", "", text or "").strip()
        return text or None

    # ── 解析：內頁（全文 + 圖 + 參考連結）──
    def _parse_detail(self, html: str) -> Dict:
        soup = BeautifulSoup(html, "html.parser")
        cont = soup.select_one(".content .text") or soup.select_one(".text") or soup.select_one(".content")
        if not cont:
            return {"content": None, "images_json": None, "reference_url": None}

        # 圖片：只存來源 URL（絕對化）
        images: List[str] = []
        for im in cont.find_all("img"):
            src = im.get("src") or im.get("data-src") or im.get("data-original")
            if not src:
                continue
            src = urljoin(self.base_url + "/", src.strip())
            if src not in images:
                images.append(src)

        # 參考連結：內文第一個外部 http 連結
        reference_url = None
        for a in cont.find_all("a", href=True):
            href = a["href"].strip()
            if href.startswith("http") and "hkepc.com" not in href and "hkepc.net" not in href:
                reference_url = href
                break

        content = cont.get_text("\n", strip=True)
        content = re.sub(r"\n{3,}", "\n\n", content)
        return {
            "content": content or None,
            "images_json": json.dumps(images, ensure_ascii=False) if images else None,
            "reference_url": reference_url,
        }

    # ── 主流程 ──
    def fetch_hkepc_articles(self, first_run: bool = False) -> List[Dict]:
        """抓列表 → 三層去重 → 抓內頁 → 回傳要寫入 DB 的 item 清單。"""
        limit = self.first_run_limit if first_run else None
        seen: Dict[int, Dict] = {}  # L1：跑批內依 hkepc_id 去重，並聯集 tag

        for tag in self.tags:
            page = 1
            while True:
                url = self._listing_url(tag, page)
                try:
                    html = self._fetch_html(url)
                except Exception as e:
                    self.logger.error("HKEPC 列表頁抓取失敗 tag=%s page=%s err=%s", tag, page, e)
                    break
                cards = self._parse_listing(html)
                self.logger.info("HKEPC 列表頁 tag=%s page=%s 解析到 %s 篇", tag, page, len(cards))
                if not cards:
                    break
                for c in cards:
                    hid = c["hkepc_id"]
                    if hid in seen:
                        seen[hid]["tags_set"].update([tag, *c["card_tags"]])
                    else:
                        c["tags_set"] = set([tag, *c["card_tags"]])
                        seen[hid] = c

                # 翻頁條件
                if first_run:
                    if len(seen) >= limit or page >= _MAX_FIRST_RUN_PAGES:
                        break
                else:
                    if page >= self.pages_per_tag:
                        break
                page += 1
                human_sleep(self.human_delay_range)

        candidates = list(seen.values())
        if first_run:
            # 依 id 由大到小（越新越前），取前 limit 篇當種子
            candidates = sorted(candidates, key=lambda c: c["hkepc_id"], reverse=True)[:limit]

        # L2：DB 已有 content 的跳過內頁
        existing_with_content = self.db_manager.get_hardware_news_ids_with_content(
            [c["hkepc_id"] for c in candidates]
        )

        items: List[Dict] = []
        for c in candidates:
            if c["hkepc_id"] in existing_with_content:
                continue
            try:
                detail_html = self._fetch_html(self._detail_url(c["hkepc_id"]))
                detail = self._parse_detail(detail_html)
            except Exception as e:
                self.logger.error("HKEPC 內頁抓取失敗 id=%s err=%s", c["hkepc_id"], e)
                detail = {"content": None, "images_json": None, "reference_url": None}

            items.append({
                "hkepc_id": c["hkepc_id"],
                "title": c["title"],
                "url": c["url"],
                "author": c.get("author"),
                "introduction": c.get("introduction"),
                "published_at": c.get("published_at"),
                "comment_count": c.get("comment_count", 0),
                "tags": ",".join(sorted(c["tags_set"])) if c.get("tags_set") else None,
                **detail,
            })
            human_sleep(self.human_delay_range)

        self.logger.info("HKEPC 本輪候選 %s 篇，需抓內頁 %s 篇", len(candidates), len(items))
        return items

    def save_articles_to_db(self, items: List[Dict]) -> int:
        saved = 0
        for item in items:
            if self.db_manager.save_hardware_news(item):
                saved += 1
        return saved

    def scrape(self, first_run: bool = False) -> Dict:
        """完整一輪：抓 + 存（不負責 commit，由呼叫端 commit）。"""
        items = self.fetch_hkepc_articles(first_run=first_run)
        saved = self.save_articles_to_db(items)
        return {"ok": True, "fetched": len(items), "saved": saved}
