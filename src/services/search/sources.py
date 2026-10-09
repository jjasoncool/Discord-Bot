"""搜尋的來源登記表：每種來源怎麼從 scraper 的資料庫讀出「文件」。

**加來源＝寫一個 `Source` 子類別並放進 `SOURCES`**；搜尋工具的名稱與參數都不用動
（MCP 的 `sources` 參數、結果的來源標籤都由這張表產生）。

文件的定義（見 `AI_HANDOFF_AND_TODO.md` 的 `mcp-search-tools` 區塊「用語」）：可以直接給人一個連結的那一篇。巴哈以「樓層」為單位，
編號用 `sn`（樓層唯一編號）；`post_id#position` 在資料庫裡有重複，不能當 id。
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from typing import Callable, Iterator, Optional

from services.search.text import html_to_text
from services.source_urls import bahamut_floor_url, official_article_url


@dataclass(frozen=True)
class Doc:
    doc_id: str
    source: str
    title: str
    body: str                 # 正文（原文，未正規化），讀全文時給人看
    url: Optional[str]
    published_at: str         # 'YYYY-MM-DD HH:MM:SS'（UTC+8，照 scraper 存的時間）


@dataclass(frozen=True)
class Change:
    """掃描 scraper 資料庫時看到的一列。內容沒變就不呼叫 `build`（HTML 解析、正規化都省掉）。"""
    doc_id: str
    cursor: tuple[str, int]   # (updated_at, 列 id)，下次從這之後掃
    raw_hash: str
    deleted: bool
    build: Callable[[], Doc] = field(compare=False)


def _hash(*parts) -> str:
    return hashlib.sha1("\x00".join("" if p is None else str(p) for p in parts).encode("utf-8")).hexdigest()


def _ts(value) -> str:
    return str(value or "")[:19]


class Source:
    key: str
    label: str
    official: bool
    table: str

    def doc_id(self, row) -> str:
        """文件編號只在這裡算：掃描比對與寫入索引用的是同一個，才不會重複收錄。"""
        raise NotImplementedError

    def scan(self, con: sqlite3.Connection, cursor: tuple[str, int]) -> Iterator[Change]:
        raise NotImplementedError

    def load(self, con: sqlite3.Connection, native_key: str) -> Optional[tuple[Doc, str]]:
        """讀一份完整文件與附加內容（推文、留言）；找不到回 None。"""
        raise NotImplementedError

    def _changed_rows(self, con, cursor, columns: str):
        updated, row_id = cursor
        # updated_at 可能相同（同一輪寫入），所以游標帶列 id 才不會漏也不會重複。
        # 寫成 (updated_at, id) 成組比較、欄位不包函式，才用得上 scraper 的 (updated_at, id) 索引
        # （2026-10-09 直接在 articles.db 建立，scraper 的 db/models.py 有宣告），直接跳到游標之後：原本每次同步都整張表掃過，
        # 巴哈就算沒有變動也讀 120 MB，快取被擠掉後一次同步要 20 秒以上。
        # updated_at 是空的列撈不到：scraper 建立時就給值（ORM default），目前也沒有空值
        return con.execute(
            f"SELECT {columns}, id AS _row_id, updated_at AS _updated FROM {self.table}"
            " WHERE (updated_at, id) > (?, ?) ORDER BY updated_at, id",
            (updated, row_id),
        )


class ArticleSource(Source):
    key, label, official, table = "article", "官網公告", True, "article_details"

    def doc_id(self, row) -> str:
        return f"article:{row['article_id']}"

    def _doc(self, row) -> Doc:
        return Doc(
            doc_id=self.doc_id(row), source=self.key, title=row["article_title"] or "",
            body=html_to_text(row["article_content"]), url=official_article_url(row["article_id"]),
            published_at=_ts(row["start_time"]),
        )

    def scan(self, con, cursor):
        for row in self._changed_rows(con, cursor, "article_id, article_title, article_content, start_time"):
            yield Change(self.doc_id(row), (row["_updated"], row["_row_id"]),
                         _hash(row["article_title"], row["article_content"], row["start_time"]), False,
                         lambda row=row: self._doc(row))

    def load(self, con, native_key):
        if not native_key.isdigit():
            return None
        row = con.execute("SELECT article_id, article_title, article_content, start_time FROM article_details"
                          " WHERE article_id = ?", (int(native_key),)).fetchone()
        return (self._doc(row), "") if row else None


class FacebookSource(Source):
    key, label, official, table = "fb", "官方 FB", True, "fb_posts"

    def doc_id(self, row) -> str:
        return f"fb:{row['_row_id']}"

    def _doc(self, row) -> Doc:
        text = row["text"] or ""
        first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
        return Doc(
            doc_id=self.doc_id(row), source=self.key, title=first_line[:60], body=text,
            url=row["url"] or row["pfbid_url"], published_at=_ts(row["timestamp"]),
        )

    def scan(self, con, cursor):
        for row in self._changed_rows(con, cursor, "text, url, pfbid_url, timestamp"):
            yield Change(self.doc_id(row), (row["_updated"], row["_row_id"]),
                         _hash(row["text"], row["url"], row["pfbid_url"], row["timestamp"]), False,
                         lambda row=row: self._doc(row))

    def load(self, con, native_key):
        if not native_key.isdigit():
            return None
        row = con.execute("SELECT id AS _row_id, text, url, pfbid_url, timestamp FROM fb_posts WHERE id = ?",
                          (int(native_key),)).fetchone()
        return (self._doc(row), "") if row else None


class PttSource(Source):
    key, label, official, table = "ptt", "PTT", False, "ptt_posts"

    def doc_id(self, row) -> str:
        return f"ptt:{row['article_id']}"

    def _doc(self, row) -> Doc:
        return Doc(
            doc_id=self.doc_id(row), source=self.key, title=row["title"] or "",
            body=row["content"] or "", url=row["url"], published_at=_ts(row["published_at"]),
        )

    def scan(self, con, cursor):
        # 推文第一版不進索引（短、雜、量大），讀全文時才附上；所以推文變了不必重建
        for row in self._changed_rows(con, cursor, "article_id, title, content, url, published_at"):
            yield Change(self.doc_id(row), (row["_updated"], row["_row_id"]),
                         _hash(row["title"], row["content"], row["url"], row["published_at"]), False,
                         lambda row=row: self._doc(row))

    def load(self, con, native_key):
        row = con.execute("SELECT article_id, title, content, url, published_at, comments_json FROM ptt_posts"
                          " WHERE article_id = ?", (native_key,)).fetchone()
        if not row:
            return None
        return self._doc(row), _format_ptt_pushes(row["comments_json"])


def _format_ptt_pushes(raw: Optional[str]) -> str:
    try:
        pushes = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return ""
    lines = [f"{p.get('tag', '')} {p.get('user', '')}: {p.get('content', '')} ({p.get('time', '')})".strip()
             for p in pushes if isinstance(p, dict)]
    return ("【推文】\n" + "\n".join(lines)) if lines else ""


class BahamutSource(Source):
    key, label, official, table = "bahamut", "巴哈姆特", False, "bahamut_posts"

    def doc_id(self, row) -> str:
        # 樓層唯一編號；post_id#position 在資料庫裡有重複
        return f"bahamut:{row['sn']}"

    _COLUMNS = "board_id, post_id, sn, position, title, content, url, published_at, is_deleted"

    def _thread_titles(self, con, post_ids) -> dict[str, str]:
        titles: dict[str, str] = {}
        ids = sorted(set(post_ids))
        for start in range(0, len(ids), 500):
            chunk = ids[start:start + 500]
            marks = ",".join("?" * len(chunk))
            for post_id, title in con.execute(
                    f"SELECT post_id, title FROM bahamut_posts WHERE position = 1 AND post_id IN ({marks})", chunk):
                if title and not titles.get(post_id):
                    titles[post_id] = title
        return titles

    def _doc(self, row, thread_title: str) -> Doc:
        position = row["position"] or 1
        own_title = row["title"] or ""
        # 回覆樓層沒有自己的標題：標題用討論串標題（也會進索引），只靠討論串標題才提到的詞也搜得到
        title = f"{thread_title or own_title}（{position} 樓）" if position > 1 else (own_title or thread_title)
        return Doc(
            doc_id=self.doc_id(row), source=self.key, title=title, body=row["content"] or "",
            url=bahamut_floor_url(row["board_id"], row["sn"]) or row["url"],
            published_at=_ts(row["published_at"]),
        )

    def scan(self, con, cursor):
        # scraper 每輪都會更新「最後看到時間」，updated_at 一天變動上萬列；內容 hash 沒變的就跳過。
        # 分批讀：第一次建索引要掃十萬列，一次全讀進記憶體太大
        result = self._changed_rows(con, cursor, self._COLUMNS)
        while rows := result.fetchmany(2000):
            titles = self._thread_titles(con, [r["post_id"] for r in rows if (r["position"] or 1) > 1])
            for row in rows:
                thread_title = titles.get(row["post_id"], "")
                yield Change(self.doc_id(row), (row["_updated"], row["_row_id"]),
                             _hash(row["title"], row["content"], row["position"], thread_title),
                             bool(row["is_deleted"]),
                             lambda row=row, thread_title=thread_title: self._doc(row, thread_title))

    def load(self, con, native_key):
        row = con.execute(f"SELECT id AS _row_id, {self._COLUMNS} FROM bahamut_posts WHERE sn = ?"
                          " AND COALESCE(is_deleted, 0) = 0", (native_key,)).fetchone()
        if not row:
            return None
        thread_title = self._thread_titles(con, [row["post_id"]]).get(row["post_id"], "")
        comments = con.execute("SELECT user_name, content FROM bahamut_post_comments WHERE parent_sn = ?"
                               " ORDER BY published_at, id", (native_key,)).fetchall()
        lines = [f"{c['user_name'] or ''}: {c['content'] or ''}" for c in comments]
        extras = ("【留言】\n" + "\n".join(lines)) if lines else ""
        return self._doc(row, thread_title), extras


#: 來源登記表。順序就是搜尋結果裡同分時的來源順序（官方在前）。
SOURCES: dict[str, Source] = {s.key: s for s in (ArticleSource(), FacebookSource(), PttSource(), BahamutSource())}
