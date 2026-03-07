"""
PTT 爬蟲服務
目前先提供「可抓到搜尋頁」的最小驗證能力
"""
import os
import sys
import json
import argparse
import hashlib
from datetime import datetime
from typing import Dict, Any, List
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse, unquote_plus

import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent

# 讓此檔案可被「單檔直接執行」
# python services/ptt_scraper_service.py 時，將 /app 加入 sys.path
SCRAPER_ROOT = os.path.dirname(os.path.dirname(__file__))
if SCRAPER_ROOT not in sys.path:
    sys.path.insert(0, SCRAPER_ROOT)

from config import PTT_CONFIG
from utils.logger import get_logger
from utils.request_utils import human_sleep


class NoOpDatabaseManager:
    """dry-run 用的空資料庫管理器"""

    def save_ptt_post(self, post_data: dict):
        return post_data

    def commit(self):
        return True

    def close(self):
        return None


class PTTScraperService:
    """PTT 爬蟲服務（MVP）"""

    def __init__(self, db_manager):
        self.logger = get_logger("ptt_scraper")
        self.db_manager = db_manager
        self.target_search_url = PTT_CONFIG["target_search_url"]
        self.timeout = PTT_CONFIG.get("timeout", 20)
        self.over18_cookie = PTT_CONFIG.get("over18_cookie", {"over18": "1"})
        self.human_delay_range = PTT_CONFIG.get("human_delay_min", (0.35, 0.9))
        self.ua = self._init_user_agent()

    def _build_first_page_url(self) -> str:
        """將設定的搜尋 URL 正規化為第一頁（page=1）"""
        parsed = urlparse(self.target_search_url)
        query = parse_qs(parsed.query)
        query["page"] = ["1"]
        first_page_query = urlencode(query, doseq=True)
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, first_page_query, parsed.fragment))

    def _parse_board_from_url(self, article_url: str) -> str:
        """從文章 URL 解析看板名稱"""
        parsed = urlparse(article_url)
        parts = [p for p in parsed.path.split("/") if p]
        # 典型路徑: /bbs/C_Chat/M.xxxxx.html
        if len(parts) >= 3 and parts[0] == "bbs":
            return parts[1]
        return ""

    def _get_target_keywords(self) -> List[str]:
        """從 target_search_url 的 q 參數取得搜尋關鍵字"""
        parsed = urlparse(self.target_search_url)
        query = parse_qs(parsed.query)
        keywords: List[str] = []
        for raw in query.get("q", []):
            kw = unquote_plus(raw).strip()
            if kw:
                keywords.append(kw)
        return keywords

    def _extract_matched_keywords(self, title: str, content: str) -> str:
        """回傳文章實際命中的關鍵字（逗號串接）"""
        text = f"{title}\n{content}".lower()
        matched: List[str] = []
        for kw in self._get_target_keywords():
            if kw.lower() in text and kw not in matched:
                matched.append(kw)
        return ",".join(matched)

    def _parse_published_at(self, published_at_raw: str):
        """解析 PTT 內文頁時間字串為 datetime；失敗回 None"""
        if not published_at_raw:
            return None

        raw = " ".join(published_at_raw.split())
        for fmt in ["%a %b %d %H:%M:%S %Y", "%b %d %H:%M:%S %Y"]:
            try:
                return datetime.strptime(raw, fmt)
            except ValueError:
                continue
        return None

    def _init_user_agent(self):
        """初始化 fake-useragent，失敗時回傳 None 走 fallback"""
        try:
            return UserAgent()
        except Exception as e:
            self.logger.warning(f"初始化 fake-useragent 失敗，將使用固定 UA: {e}")
            return None

    def _get_user_agent(self) -> str:
        """取得 User-Agent（優先 fake-useragent，失敗則 fallback）"""
        if self.ua:
            try:
                return self.ua.random
            except Exception as e:
                self.logger.warning(f"取得 fake-useragent 隨機 UA 失敗，改用固定 UA: {e}")

        return (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
        )

    def _build_headers(self) -> Dict[str, str]:
        return {
            "User-Agent": self._get_user_agent(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }

    def _fetch_html(self, url: str) -> str:
        """共用 HTML 抓取"""
        with requests.Session() as session:
            response = session.get(
                url,
                headers=self._build_headers(),
                cookies=self.over18_cookie,
                timeout=self.timeout,
            )
        response.raise_for_status()
        return response.text

    def _trim_article_tail(self, content: str) -> str:
        """更安全地去除 PTT 文章尾段（簽名/發信站），避免誤切正文中的 --"""
        if not content:
            return ""

        lines = content.splitlines()

        # 優先以「發信站」作為明確尾段起點
        for idx, line in enumerate(lines):
            if "※ 發信站:" in line:
                return "\n".join(lines[:idx]).strip()

        # 次選：只切「獨立一行」的簽名分隔線，且僅在文章後半段才採用
        start_idx = len(lines) // 2
        for idx in range(start_idx, len(lines)):
            if lines[idx].strip() == "--":
                return "\n".join(lines[:idx]).strip()

        return content.strip()

    @staticmethod
    def _build_comments_hash(comments: List[Dict[str, Any]]) -> str:
        serialized = json.dumps(comments, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _parse_article_list(self, html: str) -> List[Dict[str, Any]]:
        """解析第一頁文章列表"""
        soup = BeautifulSoup(html, "html.parser")
        entries = soup.select("div.r-ent")
        articles: List[Dict[str, Any]] = []

        for entry in entries:
            title_node = entry.select_one("div.title a")
            if not title_node:
                # 被刪除的文章通常沒有 a 標籤
                continue

            href = (title_node.get("href") or "").strip()
            full_url = f"https://www.ptt.cc{href}" if href.startswith("/") else href
            article_id = href.split("/")[-1].replace(".html", "") if href else ""

            articles.append({
                "title": title_node.get_text(strip=True),
                "url": full_url,
                "article_id": article_id,
                "author": (entry.select_one("div.author").get_text(strip=True) if entry.select_one("div.author") else ""),
                "date": (entry.select_one("div.date").get_text(strip=True) if entry.select_one("div.date") else ""),
                "push": (entry.select_one("div.nrec").get_text(strip=True) if entry.select_one("div.nrec") else ""),
            })

        return articles

    def fetch_first_page_articles(self) -> Dict[str, Any]:
        """抓取搜尋結果第一頁文章列表"""
        first_page_url = self._build_first_page_url()
        self.logger.info(f"[{datetime.now()}] 開始抓取 PTT 第一頁文章列表: {first_page_url}")

        html = self._fetch_html(first_page_url)
        soup = BeautifulSoup(html, "html.parser")
        page_title = (soup.title.text.strip() if soup.title else "")
        articles = self._parse_article_list(html)

        result = {
            "ok": True,
            "status_code": 200,
            "url": first_page_url,
            "title": page_title,
            "article_count": len(articles),
            "articles": articles,
        }

        self.logger.info(
            f"[{datetime.now()}] PTT 第一頁文章列表抓取成功: "
            f"status={result['status_code']}, article_count={result['article_count']}, title={result['title']}"
        )
        return result

    def fetch_article_detail(self, article_url: str) -> Dict[str, Any]:
        """抓取單篇文章內文"""
        self.logger.info(f"[{datetime.now()}] 開始抓取文章內文: {article_url}")

        html = self._fetch_html(article_url)
        soup = BeautifulSoup(html, "html.parser")

        page_title = (soup.title.text.strip() if soup.title else "")
        main_content = soup.select_one("#main-content")

        if not main_content:
            return {
                "ok": False,
                "url": article_url,
                "title": page_title,
                "author": "",
                "published_at": "",
                "content": "",
                "content_length": 0,
            }

        # 擷取 metadata（作者/時間）
        author = ""
        published_at = ""
        for meta_line in soup.select("div.article-metaline"):
            tag = meta_line.select_one("span.article-meta-tag")
            value = meta_line.select_one("span.article-meta-value")
            if not tag or not value:
                continue
            tag_text = tag.get_text(strip=True)
            value_text = value.get_text(strip=True)
            if tag_text == "作者":
                author = value_text
            elif tag_text == "時間":
                published_at = value_text

        comments: List[Dict[str, Any]] = []
        for push in soup.select("#main-content div.push"):
            tag_node = push.select_one("span.push-tag")
            user_node = push.select_one("span.push-userid")
            content_node = push.select_one("span.push-content")
            time_node = push.select_one("span.push-ipdatetime")

            content_text = content_node.get_text(strip=False) if content_node else ""
            if content_text.startswith(":"):
                content_text = content_text[1:]

            comments.append({
                "tag": (tag_node.get_text(strip=True) if tag_node else ""),
                "user": (user_node.get_text(strip=True) if user_node else ""),
                "content": content_text.strip(),
                "time": (time_node.get_text(" ", strip=True) if time_node else ""),
            })

        # 移除 metadata/push，保留正文
        content_soup = BeautifulSoup(str(main_content), "html.parser")
        for selector in [
            "div.article-metaline",
            "div.article-metaline-right",
            "div.push",
            "span.f2",
        ]:
            for tag in content_soup.select(selector):
                tag.decompose()

        content = content_soup.get_text("\n", strip=True)
        content = self._trim_article_tail(content)

        return {
            "ok": True,
            "url": article_url,
            "title": page_title,
            "author": author,
            "published_at": published_at,
            "content": content,
            "content_length": len(content),
            "comments": comments,
            "comments_count": len(comments),
            "comments_hash": self._build_comments_hash(comments),
        }

    def fetch_ptt_articles_with_content(self) -> Dict[str, Any]:
        """抓第一頁列表，並逐篇抓內文（先不入庫）"""
        base_result = self.fetch_first_page_articles()
        articles = base_result.get("articles", [])

        detailed_count = 0
        for article in articles:
            try:
                human_sleep(*self.human_delay_range)
                detail = self.fetch_article_detail(article.get("url", ""))

                if not detail.get("ok") or detail.get("content_length", 0) <= 0:
                    self.logger.warning(
                        "略過更新已失效/已刪除的 PTT 文章抓取結果: url=%s ok=%s content_length=%s",
                        article.get("url"),
                        detail.get("ok"),
                        detail.get("content_length", 0),
                    )
                    continue

                article["content"] = detail.get("content", "")
                article["content_length"] = detail.get("content_length", 0)
                article["published_at"] = detail.get("published_at", "")
                article["comments"] = detail.get("comments", [])
                article["comments_count"] = detail.get("comments_count", 0)
                article["comments_hash"] = detail.get("comments_hash", "")

                # 內文頁通常可取得較完整作者資訊
                if detail.get("author"):
                    article["author"] = detail.get("author")

                detailed_count += 1
            except Exception as e:
                self.logger.warning(f"抓取單篇文章內文失敗: url={article.get('url')}, error={e}")
                continue

        base_result["detailed_count"] = detailed_count

        self.logger.info(
            f"[{datetime.now()}] PTT 第一頁內文抓取完成: "
            f"article_count={base_result.get('article_count', 0)}, detailed_count={detailed_count}"
        )
        return base_result

    def save_articles_to_db(self, articles: List[Dict[str, Any]], db_manager=None) -> int:
        """將抓到的文章寫入資料庫（upsert）"""
        active_db_manager = db_manager or self.db_manager

        saved_count = 0

        for article in articles:
            try:
                if article.get("content_length", 0) <= 0:
                    self.logger.info(
                        "略過未取得有效內文的 PTT 貼文，不更新 DB: article_id=%s url=%s",
                        article.get("article_id"),
                        article.get("url"),
                    )
                    continue

                post_data = {
                    "board": self._parse_board_from_url(article.get("url", "")),
                    "article_id": article.get("article_id"),
                    "title": article.get("title"),
                    "author": article.get("author"),
                    "url": article.get("url"),
                    "content": article.get("content"),
                    "comments": article.get("comments", []),
                    "comments_count": article.get("comments_count", 0),
                    "comments_hash": article.get("comments_hash", ""),
                    "matched_keywords": self._extract_matched_keywords(
                        article.get("title", ""),
                        article.get("content", ""),
                    ),
                    "published_at": self._parse_published_at(article.get("published_at", "")),
                }

                saved = active_db_manager.save_ptt_post(post_data)
                if saved:
                    saved_count += 1
            except Exception as e:
                self.logger.warning(
                    f"寫入 PTT 貼文失敗: article_id={article.get('article_id')}, error={e}"
                )

        return saved_count


def main():
    """單檔執行入口（debug 用）"""
    parser = argparse.ArgumentParser(description="PTT scraper debug/CLI 入口")
    parser.add_argument(
        "--write-db",
        action="store_true",
        help="將抓取結果寫入資料庫（預設為 dry-run，不寫 DB）",
    )
    args = parser.parse_args()

    print("=== PTT Scraper Service Debug ===")
    try:
        service = PTTScraperService(NoOpDatabaseManager())
        db_manager = service.db_manager

        if args.write_db:
            from container import ServiceContainer
            container = ServiceContainer()
            container.create_database_tables()
            service = container.create_ptt_scraper_service()
            db_manager = service.db_manager

        result = service.fetch_ptt_articles_with_content()

        saved_count = 0
        if args.write_db:
            try:
                saved_count = service.save_articles_to_db(result.get("articles", []))
                db_manager.commit()
            finally:
                if db_manager:
                    db_manager.close()

        print("✅ 抓取完成")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print(f"write_db={args.write_db}, saved_count={saved_count}")
    except Exception as e:
        print(f"❌ 抓取失敗: {e}")
        raise


if __name__ == "__main__":
    main()
