"""
社群 ID 查詢服務 — 對 scraper articles.db 做 PTT / 巴哈 的使用者紀錄查詢。

查詢策略：
- 區間內優先，不足保底值時補撈區間外
- 受 hard cap 1000 筆/來源保護
- PTT 走 SQLite JSON1（`json_each` + `json_extract`）+ 既有 `ix_ptt_posts_published_at`
- 巴哈走 SQL（`bahamut_posts` / `bahamut_post_comments`），author_id 為穩定 key

回傳 DTO 統一為 CommunityActivity，主文會附帶 Discord 內部 jump URL（若 state_db 有對應），
否則 caller 退而求其次用原站 URL。
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import aiosqlite

from services.state_db import StateDB


# ── 預設常數（由 AI_HANDOFF_AND_TODO.md 定案）──
DEFAULT_SCRAPER_DB_PATH = Path("/app/scraper/articles.db")
PTT_POST_MIN = 20
PTT_COMMENT_MIN = 100
BAHAMUT_POST_MIN = 20
BAHAMUT_COMMENT_MIN = 100
HARD_CAP = 1000
FUZZY_CANDIDATE_LIMIT = 100  # Discord Select 上限 25，view 端做分頁


@dataclass
class CommunityActivity:
    """統一的活動紀錄 DTO（post 或 comment）。"""
    kind: str                               # 'post' | 'comment'
    source: str                             # 'ptt' | 'bahamut'
    board: str                              # PTT 板名 / 巴哈 bsn
    title: Optional[str]                    # post 標題 或 comment 所屬 post 的標題
    content: str
    time: Optional[str]                     # ISO / 原始時間字串
    url: Optional[str]                      # 原站 URL
    discord_jump_url: Optional[str] = None  # Discord 內部 jump URL（僅 post 適用）
    extra: Dict = field(default_factory=dict)
    in_range: bool = True


@dataclass
class LookupResult:
    posts_in_range: List[CommunityActivity]
    posts_fallback: List[CommunityActivity]
    comments_in_range: List[CommunityActivity]
    comments_fallback: List[CommunityActivity]
    hit_hard_cap: bool = False

    @property
    def total_posts(self) -> int:
        return len(self.posts_in_range) + len(self.posts_fallback)

    @property
    def total_comments(self) -> int:
        return len(self.comments_in_range) + len(self.comments_fallback)


@dataclass
class BahamutCandidate:
    """模糊查詢候選清單項目。"""
    author_id: str
    author_name: str
    post_count: int = 0
    comment_count: int = 0


class CommunityLookupService:
    """查 scraper DB 的社群活動紀錄。"""

    def __init__(
        self,
        scraper_db_path: Path = DEFAULT_SCRAPER_DB_PATH,
        state_db: Optional[StateDB] = None,
    ):
        self.scraper_db_path = scraper_db_path
        self.state_db = state_db

    def _connect_scraper_ro(self):
        """scraper DB 用 read-only 連線（避免誤寫 + 避免與 scraper 寫入衝突）。"""
        uri = f"file:{self.scraper_db_path}?mode=ro"
        return aiosqlite.connect(uri, uri=True)

    # ══════════════════════════════════════════════════
    # PTT
    # ══════════════════════════════════════════════════

    async def query_ptt(
        self,
        author: str,
        *,
        start_date: str,
        end_date: str,
        guild_id: Optional[int] = None,
        post_min: int = PTT_POST_MIN,
        comment_min: int = PTT_COMMENT_MIN,
        hard_cap: int = HARD_CAP,
    ) -> LookupResult:
        """查 PTT 某使用者在指定日期區間的發文 + 留言紀錄。

        Args:
            author: PTT 帳號（僅帳號本體，不含 nickname 括號）。
            start_date: 區間起始日 `YYYY-MM-DD`（含）。
            end_date: 區間結束日 `YYYY-MM-DD`（含）。
            guild_id: 若提供且 state_db 存在，會解析主文的 Discord 內部 jump URL。
            post_min/comment_min: 區間內不足時補撈區間外的保底門檻。
            hard_cap: 單類單次硬上限。
        """
        range_start = f"{start_date} 00:00:00"
        range_end = f"{end_date} 23:59:59"
        hit_cap = False

        # PTT author 欄位格式 "JohnDoe (John)" → 兼顧精確與尾部 nickname
        author_like = f"{author} (%"

        async with self._connect_scraper_ro() as conn:
            conn.row_factory = aiosqlite.Row

            # ── 主文 ──
            post_sql_base = """
                SELECT id, board, article_id, title, author, url, content, published_at
                FROM ptt_posts
                WHERE (author = ? OR author LIKE ?)
            """
            post_rows_in = await _fetch_all(
                conn,
                post_sql_base + " AND published_at IS NOT NULL AND published_at >= ? AND published_at <= ?"
                                " ORDER BY published_at DESC LIMIT ?",
                (author, author_like, range_start, range_end, hard_cap),
            )
            if len(post_rows_in) >= hard_cap:
                hit_cap = True

            post_rows_fb: List = []
            if len(post_rows_in) < post_min:
                need = post_min - len(post_rows_in)
                post_rows_fb = await _fetch_all(
                    conn,
                    post_sql_base + " AND (published_at IS NULL OR published_at < ?)"
                                    " ORDER BY published_at DESC LIMIT ?",
                    (author, author_like, range_start, need),
                )

            # ── 留言（JSON1 展開）──
            comment_sql_base = """
                SELECT p.board, p.article_id, p.title, p.url, p.published_at,
                       json_extract(c.value, '$.tag')     AS tag,
                       json_extract(c.value, '$.content') AS content,
                       json_extract(c.value, '$.time')    AS ptime
                FROM ptt_posts p, json_each(p.comments_json) c
                WHERE json_extract(c.value, '$.user') = ?
            """
            comment_rows_in = await _fetch_all(
                conn,
                comment_sql_base + " AND p.published_at IS NOT NULL AND p.published_at >= ? AND p.published_at <= ?"
                                   " ORDER BY p.published_at DESC LIMIT ?",
                (author, range_start, range_end, hard_cap),
            )
            if len(comment_rows_in) >= hard_cap:
                hit_cap = True

            comment_rows_fb: List = []
            if len(comment_rows_in) < comment_min:
                need = comment_min - len(comment_rows_in)
                comment_rows_fb = await _fetch_all(
                    conn,
                    comment_sql_base + " AND (p.published_at IS NULL OR p.published_at < ?)"
                                       " ORDER BY p.published_at DESC LIMIT ?",
                    (author, range_start, need),
                )

        posts_in = [_ptt_post_from_row(r, True) for r in post_rows_in]
        posts_fb = [_ptt_post_from_row(r, False) for r in post_rows_fb]
        comments_in = [_ptt_comment_from_row(r, True) for r in comment_rows_in]
        comments_fb = [_ptt_comment_from_row(r, False) for r in comment_rows_fb]

        if self.state_db and guild_id:
            for p_list in (posts_in, posts_fb):
                for p in p_list:
                    p.discord_jump_url = await self._resolve_ptt_discord_url(
                        guild_id=guild_id,
                        board=p.board,
                        article_id=str(p.extra.get("article_id") or ""),
                    )

        return LookupResult(
            posts_in_range=posts_in,
            posts_fallback=posts_fb,
            comments_in_range=comments_in,
            comments_fallback=comments_fb,
            hit_hard_cap=hit_cap,
        )

    async def _resolve_ptt_discord_url(
        self, *, guild_id: int, board: str, article_id: str
    ) -> Optional[str]:
        """查 state_db 取 PTT 主文的 Discord thread 連結。"""
        if not self.state_db or not board or not article_id:
            return None
        content_key = f"ptt:{board}:{article_id}"
        state = await self.state_db.get_forum_thread("ptt", content_key)
        thread_id = state.get("thread_id") if state else None
        if not thread_id:
            return None
        return f"https://discord.com/channels/{guild_id}/{thread_id}"

    # ══════════════════════════════════════════════════
    # 巴哈
    # ══════════════════════════════════════════════════

    async def query_bahamut(
        self,
        lookup_id: str,
        *,
        start_date: str,
        end_date: str,
        fuzzy: bool = False,
        guild_id: Optional[int] = None,
        post_min: int = BAHAMUT_POST_MIN,
        comment_min: int = BAHAMUT_COMMENT_MIN,
        hard_cap: int = HARD_CAP,
    ) -> LookupResult:
        """查巴哈某使用者在指定日期區間的發文 + 留言紀錄。

        Args:
            lookup_id: 巴哈 user_id（精確模式）或關鍵字（模糊模式）。
            start_date: 區間起始日 `YYYY-MM-DD`（含）。
            end_date: 區間結束日 `YYYY-MM-DD`（含）。
            fuzzy: 模糊模式 — 同時比對 user_id 精確 + author_name/user_name LIKE。
        """
        range_start = f"{start_date} 00:00:00"
        range_end = f"{end_date} 23:59:59"
        hit_cap = False

        if fuzzy:
            # 模糊模式：ID 與 名稱 都用 LIKE %keyword%
            post_cond = "(p.author_id LIKE ? OR p.author_name LIKE ?)"
            comment_cond = "(c.user_id LIKE ? OR c.user_name LIKE ?)"
            like_pat = f"%{lookup_id}%"
            post_params_base: Tuple = (like_pat, like_pat)
            comment_params_base: Tuple = (like_pat, like_pat)
        else:
            post_cond = "p.author_id = ?"
            comment_cond = "c.user_id = ?"
            post_params_base = (lookup_id,)
            comment_params_base = (lookup_id,)

        async with self._connect_scraper_ro() as conn:
            conn.row_factory = aiosqlite.Row

            # ── 主文 ──
            # LEFT JOIN 取父 thread title：position>1（回文）時本身 title 可能為空
            post_select = """
                SELECT p.id, p.board_id, p.post_id, p.sn, p.position, p.title,
                       p.category, p.author_name, p.author_id, p.url,
                       p.content, p.gp_count, p.bp_count, p.published_at,
                       parent.title AS parent_title
                FROM bahamut_posts p
                LEFT JOIN bahamut_posts parent
                    ON parent.board_id = p.board_id
                    AND parent.post_id = p.post_id
                    AND parent.position = 1
                WHERE
            """
            post_rows_in = await _fetch_all(
                conn,
                post_select + post_cond +
                " AND p.published_at IS NOT NULL AND p.published_at >= ? AND p.published_at <= ?"
                " ORDER BY p.published_at DESC LIMIT ?",
                post_params_base + (range_start, range_end, hard_cap),
            )
            if len(post_rows_in) >= hard_cap:
                hit_cap = True

            post_rows_fb: List = []
            if len(post_rows_in) < post_min:
                need = post_min - len(post_rows_in)
                post_rows_fb = await _fetch_all(
                    conn,
                    post_select + post_cond +
                    " AND (p.published_at IS NULL OR p.published_at < ?)"
                    " ORDER BY p.published_at DESC LIMIT ?",
                    post_params_base + (range_start, need),
                )

            # ── 留言 ──
            # 留言直接 parent 可能是回文 (position>1，自身 title 為空)，
            # LEFT JOIN 根 thread (同 post_id + position=1) 取 thread 層級的標題
            comment_select = """
                SELECT c.id, c.floor, c.user_id, c.user_name, c.content,
                       c.gp_count, c.bp_count, c.published_at,
                       p.board_id, p.post_id, p.sn AS parent_sn, p.position AS parent_position,
                       COALESCE(pt.title, NULLIF(p.title, '')) AS parent_title,
                       pt.sn AS thread_sn,
                       p.url AS parent_url
                FROM bahamut_post_comments c
                JOIN bahamut_posts p ON c.bahamut_post_id = p.id
                LEFT JOIN bahamut_posts pt
                    ON pt.board_id = p.board_id
                    AND pt.post_id = p.post_id
                    AND pt.position = 1
                WHERE
            """
            comment_rows_in = await _fetch_all(
                conn,
                comment_select + comment_cond +
                " AND c.published_at IS NOT NULL AND c.published_at >= ? AND c.published_at <= ?"
                " ORDER BY c.published_at DESC LIMIT ?",
                comment_params_base + (range_start, range_end, hard_cap),
            )
            if len(comment_rows_in) >= hard_cap:
                hit_cap = True

            comment_rows_fb: List = []
            if len(comment_rows_in) < comment_min:
                need = comment_min - len(comment_rows_in)
                comment_rows_fb = await _fetch_all(
                    conn,
                    comment_select + comment_cond +
                    " AND (c.published_at IS NULL OR c.published_at < ?)"
                    " ORDER BY c.published_at DESC LIMIT ?",
                    comment_params_base + (range_start, need),
                )

        posts_in = [_bahamut_post_from_row(r, True) for r in post_rows_in]
        posts_fb = [_bahamut_post_from_row(r, False) for r in post_rows_fb]
        comments_in = [_bahamut_comment_from_row(r, True) for r in comment_rows_in]
        comments_fb = [_bahamut_comment_from_row(r, False) for r in comment_rows_fb]

        if self.state_db and guild_id:
            for p_list in (posts_in, posts_fb):
                for p in p_list:
                    p.discord_jump_url = await self._resolve_bahamut_discord_url(
                        guild_id=guild_id,
                        board_id=p.board,
                        post_id=str(p.extra.get("post_id") or ""),
                        sn=str(p.extra.get("sn") or ""),
                    )

        return LookupResult(
            posts_in_range=posts_in,
            posts_fallback=posts_fb,
            comments_in_range=comments_in,
            comments_fallback=comments_fb,
            hit_hard_cap=hit_cap,
        )

    async def _resolve_bahamut_discord_url(
        self, *, guild_id: int, board_id: str, post_id: str, sn: str
    ) -> Optional[str]:
        """查 state_db 取巴哈主文/回文的 Discord 連結（thread/{msg_id}）。"""
        if not self.state_db or not board_id or not post_id:
            return None
        state = await self.state_db.get_bahamut_thread(board_id, post_id)
        if not state:
            return None
        thread_id = state.get("thread_id")
        if not thread_id:
            return None
        # 取該 sn 的 msg_id（主文或指定回文）
        posts = state.get("posts", {}) or {}
        post_state = posts.get(sn) if sn else None
        msg_id = (post_state or {}).get("msg_id")
        if msg_id:
            return f"https://discord.com/channels/{guild_id}/{thread_id}/{msg_id}"
        # 退回 thread 首
        return f"https://discord.com/channels/{guild_id}/{thread_id}"

    async def search_bahamut_candidates(
        self, keyword: str, limit: int = FUZZY_CANDIDATE_LIMIT
    ) -> List[BahamutCandidate]:
        """模糊候選清單（ID 精確 + name LIKE，合併 post/comment 兩邊結果）。"""
        if not keyword:
            return []
        like_pat = f"%{keyword}%"

        async with self._connect_scraper_ro() as conn:
            conn.row_factory = aiosqlite.Row

            # 模糊：ID 與 名稱 都 LIKE %keyword%
            post_rows = await _fetch_all(
                conn,
                """
                SELECT author_id, author_name, COUNT(*) AS n
                FROM bahamut_posts
                WHERE author_id IS NOT NULL
                  AND (author_id LIKE ? OR author_name LIKE ?)
                GROUP BY author_id, author_name
                """,
                (like_pat, like_pat),
            )
            comment_rows = await _fetch_all(
                conn,
                """
                SELECT user_id AS author_id, user_name AS author_name, COUNT(*) AS n
                FROM bahamut_post_comments
                WHERE user_id IS NOT NULL
                  AND (user_id LIKE ? OR user_name LIKE ?)
                GROUP BY user_id, user_name
                """,
                (like_pat, like_pat),
            )

        # 合併：以 author_id 為主要 key；同一 id 可能對應多個 name，取最多出現的
        # 過濾 author_id 不符 Discord SelectOption.value 1~100 長度規定者
        # （巴哈 scraper 早期資料曾出現空 / 全空白 / 異常超長的 author_id）
        merged: Dict[str, BahamutCandidate] = {}
        for row in post_rows:
            aid = (row["author_id"] or "").strip()
            if not (1 <= len(aid) <= 100):
                continue
            if aid not in merged:
                merged[aid] = BahamutCandidate(author_id=aid, author_name=row["author_name"] or "")
            merged[aid].post_count += row["n"]
        for row in comment_rows:
            aid = (row["author_id"] or "").strip()
            if not (1 <= len(aid) <= 100):
                continue
            if aid not in merged:
                merged[aid] = BahamutCandidate(author_id=aid, author_name=row["author_name"] or "")
            elif not merged[aid].author_name and row["author_name"]:
                merged[aid].author_name = row["author_name"]
            merged[aid].comment_count += row["n"]

        # 精確 ID 命中排最前，其次依活躍度（post + comment）遞減
        candidates = sorted(
            merged.values(),
            key=lambda c: (
                0 if c.author_id == keyword else 1,
                -(c.post_count + c.comment_count),
                c.author_name,
            ),
        )
        return candidates[:limit]


# ══════════════════════════════════════════════════
# Helper: row → DTO
# ══════════════════════════════════════════════════

def _ptt_post_from_row(row, in_range: bool) -> CommunityActivity:
    return CommunityActivity(
        kind="post",
        source="ptt",
        board=row["board"],
        title=row["title"],
        content=row["content"] or "",
        time=row["published_at"],
        url=row["url"],
        in_range=in_range,
        extra={
            "author": row["author"],
            "ptt_post_id": row["id"],
            "article_id": row["article_id"],
        },
    )


def _ptt_comment_from_row(row, in_range: bool) -> CommunityActivity:
    return CommunityActivity(
        kind="comment",
        source="ptt",
        board=row["board"],
        title=row["title"],
        content=row["content"] or "",
        time=row["ptime"],
        url=row["url"],
        in_range=in_range,
        extra={
            "tag": row["tag"],
            "parent_article_id": row["article_id"],
            "parent_published_at": row["published_at"],
        },
    )


def _bahamut_post_from_row(row, in_range: bool) -> CommunityActivity:
    # 回文（position > 1）的 title 通常是空字串；若是回文，把 title 顯示為父 thread title
    own_title = row["title"] or ""
    parent_title = _safe_get(row, "parent_title") or ""
    display_title = own_title if own_title else parent_title
    # 組「精確樓層」URL：Co.php?bsn=...&sn=... 可直接跳到該篇主文/回文，
    # 比 scraper 存的 thread URL (C.php?snA=...) 精確
    sn_val = row["sn"]
    precise_url = (
        f"https://forum.gamer.com.tw/Co.php?bsn={row['board_id']}&sn={sn_val}"
        if sn_val else row["url"]
    )
    return CommunityActivity(
        kind="post",
        source="bahamut",
        board=row["board_id"],
        title=display_title,
        content=row["content"] or "",
        time=row["published_at"],
        url=precise_url,
        in_range=in_range,
        extra={
            "author_name": row["author_name"],
            "author_id": row["author_id"],
            "category": row["category"],
            "gp": row["gp_count"] or 0,
            "bp": row["bp_count"] or 0,
            "bahamut_post_id": row["id"],
            "sn": row["sn"],
            "post_id": row["post_id"],
            "position": row["position"],
            "parent_title": parent_title,
        },
    )


def _safe_get(row, key: str):
    """aiosqlite.Row 沒有 .get，手動判定 key 是否存在。"""
    try:
        return row[key]
    except (IndexError, KeyError):
        return None


def _bahamut_comment_from_row(row, in_range: bool) -> CommunityActivity:
    # 留言 header link 指向「根 thread 首樓」（thread_sn），若查不到退 parent_sn，最後退 scraper 存的 url
    thread_sn = _safe_get(row, "thread_sn")
    parent_sn_val = row["parent_sn"]
    target_sn = thread_sn or parent_sn_val
    parent_precise_url = (
        f"https://forum.gamer.com.tw/Co.php?bsn={row['board_id']}&sn={target_sn}"
        if target_sn else row["parent_url"]
    )
    return CommunityActivity(
        kind="comment",
        source="bahamut",
        board=row["board_id"],
        title=row["parent_title"],
        content=row["content"] or "",
        time=row["published_at"],
        url=parent_precise_url,
        in_range=in_range,
        extra={
            "floor": row["floor"],
            "user_name": row["user_name"],
            "user_id": row["user_id"],
            "gp": row["gp_count"] or 0,
            "bp": row["bp_count"] or 0,
            "parent_post_id": row["post_id"],
            "parent_sn": row["parent_sn"],
            "parent_position": _safe_get(row, "parent_position"),
            "parent_is_reply": bool(_safe_get(row, "parent_position") and row["parent_position"] != 1),
        },
    )


async def _fetch_all(conn, sql: str, params: Tuple) -> List:
    async with conn.execute(sql, params) as cursor:
        return await cursor.fetchall()
