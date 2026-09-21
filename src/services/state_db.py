"""
統一狀態追蹤資料庫（SQLite）

取代原本的 sent_articles.json，涵蓋所有來源：
- sent_content：所有來源的已發送去重
- forum_thread_state：PTT / Bahamut 等 forum 來源的 thread 追蹤
- bahamut_post_state / bahamut_comment_slot / bahamut_synced_comment：巴哈明細
- community_lookup_threads：社群 ID 查詢（PTT / 巴哈）的 thread 追蹤（日期 hybrid section）
"""
import asyncio
import aiosqlite
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set

from utils.logger_config import get_article_monitor_logger

logger = get_article_monitor_logger()

# 預設 DB 路徑
DEFAULT_DB_PATH = Path(__file__).parent / "sent_articles.db"

_CREATE_TABLES_SQL = """
-- 通用：已發送內容去重（所有來源共用）
CREATE TABLE IF NOT EXISTS sent_content (
    source TEXT NOT NULL,
    content_key TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (source, content_key)
);

-- Forum 來源：thread 追蹤（PTT / Bahamut 共用）
CREATE TABLE IF NOT EXISTS forum_thread_state (
    source TEXT NOT NULL,
    content_key TEXT NOT NULL,
    thread_id INTEGER NOT NULL,
    synced_comments_count INTEGER DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (source, content_key)
);

-- 巴哈：文章訊息（主文/回覆的 Discord msg_id）
CREATE TABLE IF NOT EXISTS bahamut_post_state (
    board_id TEXT NOT NULL,
    post_id TEXT NOT NULL,
    sn TEXT NOT NULL,
    msg_id INTEGER NOT NULL,
    content_hash TEXT,
    continuation_msg_ids TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (board_id, post_id, sn)
);

-- 巴哈：留言格（預建 + 溢出）
CREATE TABLE IF NOT EXISTS bahamut_comment_slot (
    board_id TEXT NOT NULL,
    post_id TEXT NOT NULL,
    sn TEXT NOT NULL,
    slot_index INTEGER NOT NULL,
    msg_id INTEGER NOT NULL,
    used_chars INTEGER DEFAULT 0,
    is_overflow INTEGER DEFAULT 0,
    content_hash TEXT,
    PRIMARY KEY (board_id, post_id, sn, slot_index)
);

-- 巴哈：已同步留言（去重）
CREATE TABLE IF NOT EXISTS bahamut_synced_comment (
    sn TEXT NOT NULL,
    comment_id TEXT NOT NULL,
    PRIMARY KEY (sn, comment_id)
);

-- 活動公告 → Discord 伺服器活動：跨來源活動指紋對照（去重 + 冪等 + 可撤銷）
CREATE TABLE IF NOT EXISTS created_events (
    event_fingerprint TEXT PRIMARY KEY,       -- normalize(title)|start|end
    discord_event_id  INTEGER,                -- 建立的 Discord scheduled event id（dry-run 時為 NULL）
    guild_id          INTEGER,
    source            TEXT,                    -- 'article' | 'fb'
    source_id         TEXT,                    -- article_id / fb post_id（來源追溯）
    title             TEXT,
    start_utc8        TEXT,
    end_utc8          TEXT,
    core_name         TEXT,                    -- 指紋核心名（同名改期比對）
    has_image         INTEGER DEFAULT 0,       -- 目前活動有沒有封面（沒有才補，不換圖）
    body              TEXT,                    -- 目前描述採用的活動段落片段（比長度決定要不要換）
    superseded_by     TEXT,                    -- 分身列 → 指向正本指紋（排序永遠排在正本後面）
    user_deleted      INTEGER DEFAULT 0,       -- 墓碑：使用者從 Discord 刪掉，任何來源都不得復活
    deleted_at        TIMESTAMP,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP
);

-- 社群 ID 查詢：每 (guild, source, lookup_id) 唯一 thread，採「日期 hybrid」
CREATE TABLE IF NOT EXISTS community_lookup_threads (
    guild_id              INTEGER NOT NULL,
    source                TEXT NOT NULL,              -- 'ptt' | 'bahamut'
    lookup_id             TEXT NOT NULL,              -- PTT 帳號 或 巴哈 user_id
    thread_id             INTEGER NOT NULL,
    control_msg_id        INTEGER,                    -- 底部控制訊息（[🔄 更新]）的 msg_id
    last_section_date     TEXT,                       -- 'YYYY-MM-DD'：判斷同日 edit / 跨日 append
    last_section_slots    TEXT,                       -- JSON: {header_msg_id, nickname_msg_id, post_slot_msg_ids, comment_slot_msg_ids}
    last_start_date       TEXT,                       -- 上次查詢區間起 'YYYY-MM-DD'（顯示於重查警告 embed）
    last_end_date         TEXT,                       -- 上次查詢區間迄 'YYYY-MM-DD'
    last_updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (guild_id, source, lookup_id)
);
"""

# 漸進式 migration（對既有 DB 安全，column 已存在會跳過）
_MIGRATIONS_SQL = [
    "ALTER TABLE bahamut_post_state ADD COLUMN content_hash TEXT",
    "ALTER TABLE bahamut_comment_slot ADD COLUMN content_hash TEXT",
    "ALTER TABLE bahamut_post_state ADD COLUMN continuation_msg_ids TEXT",
    "ALTER TABLE community_lookup_threads ADD COLUMN last_start_date TEXT",
    "ALTER TABLE community_lookup_threads ADD COLUMN last_end_date TEXT",
    # created_events：支援「升級既有活動」而非只擋重複（封面/描述後補、官方改期、墓碑）
    # 這批欄位在上面的 CREATE TABLE 也有一份 —— 新 DB 走建表、既有 DB 走這裡，兩邊要一起改。
    # 只留「有人讀」的欄位＋兩個稽核時間戳；存了沒人讀的欄位會變成下一個人拿來當判準的誘餌。
    "ALTER TABLE created_events ADD COLUMN core_name TEXT",       # 指紋核心名（同名改期比對）
    "ALTER TABLE created_events ADD COLUMN has_image INTEGER DEFAULT 0",  # 沒有才補封面，不換圖
    "ALTER TABLE created_events ADD COLUMN body TEXT",            # 目前描述採用的片段（比長度）
    "ALTER TABLE created_events ADD COLUMN superseded_by TEXT",   # 分身列 → 指向正本指紋
    "ALTER TABLE created_events ADD COLUMN user_deleted INTEGER DEFAULT 0",  # 墓碑：不得復活
    "ALTER TABLE created_events ADD COLUMN deleted_at TIMESTAMP",
    "ALTER TABLE created_events ADD COLUMN updated_at TIMESTAMP",
    "CREATE INDEX IF NOT EXISTS idx_created_events_core ON created_events(core_name)",
]


class StateDB:
    """統一狀態追蹤 — async SQLite 封裝。"""

    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        """建立連線並初始化表結構。"""
        if self._db is not None:
            return
        self._db = await aiosqlite.connect(str(self.db_path))
        self._db.row_factory = aiosqlite.Row
        # WAL：允許並發讀寫、跨連線讀到已 commit 的資料（避免長連線視圖不一致）；
        # busy_timeout：撞鎖時等待而非立即失敗。
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA busy_timeout=5000")
        await self._db.executescript(_CREATE_TABLES_SQL)
        # 漸進式 migration（column 已存在會跳過）
        for sql in _MIGRATIONS_SQL:
            try:
                await self._db.execute(sql)
            except Exception:
                pass  # column 已存在，忽略
        await self._db.commit()
        logger.info("StateDB 已連線: %s", self.db_path)

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    @property
    def db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("StateDB 尚未連線，請先呼叫 connect()")
        return self._db

    # ── 通用：sent_content（純去重） ──

    async def is_content_sent(self, source: str, content_key: str) -> bool:
        async with self.db.execute(
            "SELECT 1 FROM sent_content WHERE source=? AND content_key=?",
            (source, str(content_key)),
        ) as cursor:
            return await cursor.fetchone() is not None

    async def mark_content_as_sent(self, source: str, content_key: str) -> None:
        await self.db.execute(
            "INSERT OR IGNORE INTO sent_content (source, content_key) VALUES (?, ?)",
            (source, str(content_key)),
        )
        await self.db.commit()

    async def get_all_sent_keys(self, source: str) -> Set[str]:
        async with self.db.execute(
            "SELECT content_key FROM sent_content WHERE source=?",
            (source,),
        ) as cursor:
            rows = await cursor.fetchall()
        return {row[0] for row in rows}

    # ── 活動公告 → Discord 活動：created_events（跨來源指紋去重） ──

    async def record_created_event(
        self,
        fingerprint: str,
        *,
        discord_event_id: Optional[int],
        guild_id: Optional[int],
        source: str,
        source_id: str,
        title: str,
        start_utc8: str,
        end_utc8: str,
        core_name: str = "",
        has_image: bool = False,
        body: str = "",
    ) -> None:
        """記錄已建立（或 dry-run 預定）的活動指紋。重複指紋保留首筆（INSERT OR IGNORE）。"""
        await self.db.execute(
            """INSERT OR IGNORE INTO created_events
               (event_fingerprint, discord_event_id, guild_id, source, source_id,
                title, start_utc8, end_utc8, core_name, has_image, body, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
            (fingerprint, discord_event_id, guild_id, source, str(source_id),
             title, start_utc8, end_utc8, core_name, 1 if has_image else 0, body),
        )
        await self.db.commit()

    async def mark_created_event_deleted(self, discord_event_id: int) -> int:
        """Discord 端刪除/取消活動 → 在 created_events 立**墓碑**，不是刪掉那一列。

        原本是實體 DELETE，理由寫「重送同來源貼文可重新建立」。但同一個活動 article 與 FB
        相隔 7~28 天才會各報一次（實測），實體刪掉之後那篇晚到的公告就會把使用者剛刪掉的
        活動原地復活 —— 那條重建路徑擋不住的，正是使用者真正會踩到的情況，故捨棄。
        墓碑留著，兩條比對路徑都還查得到，只是查到就什麼都不做。

        解除墓碑的唯一入口是 `/resend_article`（人明確要求重抓才會走 clear_event_tombstone
        或 delete_created_event）。自動來源——排程輪詢與 push 通知——一律不得解除。
        回傳標記筆數。
        """
        cur = await self.db.execute(
            "UPDATE created_events SET user_deleted=1, deleted_at=CURRENT_TIMESTAMP "
            "WHERE discord_event_id=? AND user_deleted=0",
            (discord_event_id,),
        )
        await self.db.commit()
        return cur.rowcount

    async def clear_event_tombstone(self, fingerprint: str) -> bool:
        """解除墓碑。**只有 /resend_article 這種人為明確動作能呼叫** ——
        自動來源（排程/推送）一律不得解除，否則墓碑就白立了。"""
        cur = await self.db.execute(
            "UPDATE created_events SET user_deleted=0, deleted_at=NULL "
            "WHERE event_fingerprint=?",
            (fingerprint,),
        )
        await self.db.commit()
        return cur.rowcount > 0

    async def delete_created_event(self, fingerprint: str) -> bool:
        """整列刪除。用在「/resend_article 要求重建，而那個 Discord 活動已經不在了」——
        列裡的 discord_event_id 指向一個死掉的活動，留著只會擋住重建。"""
        cur = await self.db.execute(
            "DELETE FROM created_events WHERE event_fingerprint=?", (fingerprint,)
        )
        await self.db.commit()
        return cur.rowcount > 0

    # created_events 的 SELECT 欄位順序（get / list / find 共用同一個 row → dict 轉換）
    _EVENT_COLS = ("event_fingerprint, discord_event_id, guild_id, source, source_id, "
                   "title, start_utc8, end_utc8, core_name, has_image, "
                   "body, superseded_by, user_deleted")

    @staticmethod
    def _event_row_to_dict(row) -> Dict:
        return {
            "event_fingerprint": row[0], "discord_event_id": row[1], "guild_id": row[2],
            "source": row[3], "source_id": row[4], "title": row[5],
            "start_utc8": row[6], "end_utc8": row[7], "core_name": row[8] or "",
            "has_image": bool(row[9]), "body": row[10] or "",
            "superseded_by": row[11], "user_deleted": bool(row[12]),
        }

    async def get_created_event(self, fingerprint: str) -> Optional[Dict]:
        """取回指紋對應的已建活動（撤銷/升級用）。"""
        async with self.db.execute(
            f"SELECT {self._EVENT_COLS} FROM created_events WHERE event_fingerprint=?",
            (fingerprint,),
        ) as cursor:
            row = await cursor.fetchone()
        return self._event_row_to_dict(row) if row else None

    async def find_overlapping_event(
        self,
        core_name: str,
        start_utc8: str,
        end_utc8: str,
        *,
        exclude_fingerprints: Optional[Set[str]] = None,
    ) -> Optional[Dict]:
        """同活動名、且時間區間**重疊**的既有活動（官方改期/延長 → 升級而非新建）。

        不重疊＝不同檔期（例：[聲弦滌蕩] 每隔幾週開一次），必須各自建活動，
        所以這裡刻意只認重疊，不認「同名就是同一個」。
        時間字串格式固定為 'YYYY-MM-DD HH:MM'，字典序比較等同時間序。

        exclude_fingerprints：**本輪已經配對掉的列**。匯總帖裡若有幾個活動的標題抽不出來、
        一起退用貼文標題，就會同名而區間不同（實測全庫 1 則：article 995「往歲乘霄醒驚蟄」
        1.1版本內容說明，3 個活動同名），彼此不可互相吃掉。
        這裡刻意**不是**排除「整個 (source, source_id)」—— 那樣連 /resend_article 重送同一篇
        改期公告都會對不到自己先前那一列，結果建出第二個活動。

        排序：正本（superseded_by IS NULL）優先；created_at 只有秒精度，同批建立的列
        會同秒，故再用 rowid 當決勝，避免回傳結果不定。
        """
        if not core_name:
            return None
        sql = (f"SELECT {self._EVENT_COLS} FROM created_events "
               "WHERE core_name = ? AND start_utc8 < ? AND ? < end_utc8")
        params: List = [core_name, end_utc8, start_utc8]
        for fingerprint in sorted(exclude_fingerprints or ()):
            sql += " AND event_fingerprint <> ?"
            params.append(fingerprint)
        sql += " ORDER BY (superseded_by IS NULL) DESC, created_at DESC, rowid DESC LIMIT 1"
        async with self.db.execute(sql, params) as cursor:
            row = await cursor.fetchone()
        return self._event_row_to_dict(row) if row else None

    async def find_same_name_events(self, core_name: str) -> List[Dict]:
        """同核心名的所有列（用來偵測「改期到完全不重疊的新區間」並示警）。"""
        if not core_name:
            return []
        async with self.db.execute(
            f"SELECT {self._EVENT_COLS} FROM created_events WHERE core_name = ?", (core_name,)
        ) as cursor:
            return [self._event_row_to_dict(r) for r in await cursor.fetchall()]

    async def list_created_events(self) -> List[Dict]:
        """全表列出（指紋遷移與對帳用；筆數是「活動數」量級，不會大）。"""
        async with self.db.execute(
            f"SELECT {self._EVENT_COLS} FROM created_events ORDER BY created_at"
        ) as cursor:
            return [self._event_row_to_dict(r) for r in await cursor.fetchall()]

    async def update_created_event(
        self,
        fingerprint: str,
        *,
        new_fingerprint: Optional[str] = None,
        source: Optional[str] = None,
        source_id: Optional[str] = None,
        title: Optional[str] = None,
        start_utc8: Optional[str] = None,
        end_utc8: Optional[str] = None,
        core_name: Optional[str] = None,
        has_image: Optional[bool] = None,
        body: Optional[str] = None,
        superseded_by: Optional[str] = None,
    ) -> bool:
        """就地更新既有活動列（升級描述/封面、官方改期換時間、指紋遷移）。

        只有傳進來的欄位會被寫入（None＝不動）。回傳是否真的更新到一列。
        新指紋若已被別列佔用（＝兩列其實是同一個活動）會 UNIQUE 失敗，
        由呼叫端決定怎麼處理，不在這裡吞掉。
        """
        sets, params = ["updated_at = CURRENT_TIMESTAMP"], []
        for col, val in (
            ("event_fingerprint", new_fingerprint), ("source", source),
            ("source_id", None if source_id is None else str(source_id)),
            ("title", title), ("start_utc8", start_utc8), ("end_utc8", end_utc8),
            ("core_name", core_name),
            ("has_image", None if has_image is None else (1 if has_image else 0)),
            ("body", body), ("superseded_by", superseded_by),
        ):
            if val is not None:
                sets.append(f"{col} = ?")
                params.append(val)
        params.append(fingerprint)
        cur = await self.db.execute(
            f"UPDATE created_events SET {', '.join(sets)} WHERE event_fingerprint = ?",
            params,
        )
        await self.db.commit()
        return cur.rowcount > 0

    # ── Forum：forum_thread_state（PTT / Bahamut 共用） ──

    async def get_forum_thread(self, source: str, content_key: str) -> Optional[Dict]:
        """取得 forum thread 追蹤狀態。"""
        async with self.db.execute(
            "SELECT thread_id, synced_comments_count FROM forum_thread_state WHERE source=? AND content_key=?",
            (source, str(content_key)),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return {"thread_id": row[0], "synced_comments_count": row[1]}

    async def upsert_forum_thread(self, source: str, content_key: str, thread_id: int, synced_comments_count: int = 0) -> None:
        """新增或更新 forum thread 狀態。"""
        await self.db.execute(
            """INSERT INTO forum_thread_state (source, content_key, thread_id, synced_comments_count)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(source, content_key)
               DO UPDATE SET thread_id=excluded.thread_id,
                             synced_comments_count=excluded.synced_comments_count,
                             updated_at=CURRENT_TIMESTAMP""",
            (source, str(content_key), thread_id, synced_comments_count),
        )
        await self.db.commit()

    # ── PTT（透過 forum_thread_state）──

    async def get_ptt_state(self, content_key: str) -> Dict:
        result = await self.get_forum_thread("ptt", content_key)
        return result or {}

    async def update_ptt_state(self, content_key: str, state: Dict) -> None:
        content_key = str(content_key)
        # 同時寫入 sent_content（去重）
        await self.mark_content_as_sent("ptt", content_key)
        await self.upsert_forum_thread(
            "ptt", content_key,
            thread_id=state.get("thread_id", 0),
            synced_comments_count=state.get("synced_comments_count", 0),
        )

    # ── Bahamut ──

    async def get_bahamut_thread(self, board_id: str, post_id: str) -> Optional[Dict]:
        """取得巴哈討論串追蹤狀態（含 posts + slots + synced_comments）。"""
        content_key = f"bahamut:{board_id}:{post_id}"
        forum_state = await self.get_forum_thread("bahamut", content_key)
        if forum_state is None:
            return None

        state = {"thread_id": forum_state["thread_id"], "posts": {}}

        # 取所有 post
        async with self.db.execute(
            "SELECT sn, msg_id, content_hash, continuation_msg_ids FROM bahamut_post_state WHERE board_id=? AND post_id=?",
            (board_id, post_id),
        ) as cursor:
            post_rows = await cursor.fetchall()

        for post_row in post_rows:
            sn = post_row[0]
            cont_ids = json.loads(post_row[3]) if post_row[3] else []
            post_state = {"msg_id": post_row[1], "content_hash": post_row[2], "continuation_msg_ids": cont_ids, "comment_slots": [], "overflow_slots": []}

            # 取留言格
            async with self.db.execute(
                """SELECT slot_index, msg_id, used_chars, is_overflow, content_hash
                   FROM bahamut_comment_slot
                   WHERE board_id=? AND post_id=? AND sn=?
                   ORDER BY slot_index""",
                (board_id, post_id, sn),
            ) as cursor:
                slot_rows = await cursor.fetchall()

            for slot_row in slot_rows:
                slot_data = {"msg_id": slot_row[1], "used_chars": slot_row[2], "content_hash": slot_row[4]}
                if slot_row[3]:  # is_overflow
                    post_state["overflow_slots"].append(slot_data)
                else:
                    post_state["comment_slots"].append(slot_data)

            # 取已同步留言 ID
            async with self.db.execute(
                "SELECT comment_id FROM bahamut_synced_comment WHERE sn=?",
                (sn,),
            ) as cursor:
                comment_rows = await cursor.fetchall()
            post_state["synced_comment_ids"] = [r[0] for r in comment_rows]

            state["posts"][sn] = post_state

        return state

    async def save_bahamut_thread(self, board_id: str, post_id: str, state: Dict) -> None:
        """儲存巴哈討論串完整追蹤狀態。"""
        thread_id = state.get("thread_id", 0)
        content_key = f"bahamut:{board_id}:{post_id}"

        # 寫入 sent_content + forum_thread_state
        await self.mark_content_as_sent("bahamut", content_key)
        await self.upsert_forum_thread("bahamut", content_key, thread_id)

        posts = state.get("posts", {})
        for sn, post_state in posts.items():
            msg_id = post_state.get("msg_id", 0)
            post_hash = post_state.get("content_hash")
            cont_ids = json.dumps(post_state.get("continuation_msg_ids", []))
            await self.db.execute(
                """INSERT INTO bahamut_post_state (board_id, post_id, sn, msg_id, content_hash, continuation_msg_ids, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(board_id, post_id, sn)
                   DO UPDATE SET msg_id=excluded.msg_id, content_hash=excluded.content_hash,
                                 continuation_msg_ids=excluded.continuation_msg_ids, updated_at=CURRENT_TIMESTAMP""",
                (board_id, post_id, sn, msg_id, post_hash, cont_ids),
            )

            # 留言格（預建 + 溢出）
            for idx, slot in enumerate(post_state.get("comment_slots", [])):
                await self.db.execute(
                    """INSERT INTO bahamut_comment_slot
                       (board_id, post_id, sn, slot_index, msg_id, used_chars, is_overflow, content_hash)
                       VALUES (?, ?, ?, ?, ?, ?, 0, ?)
                       ON CONFLICT(board_id, post_id, sn, slot_index)
                       DO UPDATE SET msg_id=excluded.msg_id, used_chars=excluded.used_chars, content_hash=excluded.content_hash""",
                    (board_id, post_id, sn, idx, slot.get("msg_id", 0), slot.get("used_chars", 0), slot.get("content_hash")),
                )

            overflow_start = len(post_state.get("comment_slots", []))
            for idx, slot in enumerate(post_state.get("overflow_slots", [])):
                await self.db.execute(
                    """INSERT INTO bahamut_comment_slot
                       (board_id, post_id, sn, slot_index, msg_id, used_chars, is_overflow, content_hash)
                       VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                       ON CONFLICT(board_id, post_id, sn, slot_index)
                       DO UPDATE SET msg_id=excluded.msg_id, used_chars=excluded.used_chars, is_overflow=1, content_hash=excluded.content_hash""",
                    (board_id, post_id, sn, overflow_start + idx, slot.get("msg_id", 0), slot.get("used_chars", 0), slot.get("content_hash")),
                )

            # 已同步留言
            for comment_id in post_state.get("synced_comment_ids", []):
                await self.db.execute(
                    "INSERT OR IGNORE INTO bahamut_synced_comment (sn, comment_id) VALUES (?, ?)",
                    (sn, str(comment_id)),
                )

        await self.db.commit()

    # ── 社群 ID 查詢：community_lookup_threads ──

    async def get_community_lookup_thread(
        self, guild_id: int, source: str, lookup_id: str
    ) -> Optional[Dict]:
        """取得社群 ID 查詢 thread 狀態。"""
        async with self.db.execute(
            """SELECT thread_id, control_msg_id, last_section_date,
                      last_section_slots, last_updated_at,
                      last_start_date, last_end_date
               FROM community_lookup_threads
               WHERE guild_id=? AND source=? AND lookup_id=?""",
            (guild_id, source, str(lookup_id)),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return {
            "thread_id": row[0],
            "control_msg_id": row[1],
            "last_section_date": row[2],
            "last_section_slots": json.loads(row[3]) if row[3] else {},
            "last_updated_at": row[4],
            "last_start_date": row[5],
            "last_end_date": row[6],
        }

    async def upsert_community_lookup_thread(
        self,
        guild_id: int,
        source: str,
        lookup_id: str,
        *,
        thread_id: int,
        control_msg_id: Optional[int] = None,
        last_section_date: Optional[str] = None,
        last_section_slots: Optional[Dict] = None,
        last_start_date: Optional[str] = None,
        last_end_date: Optional[str] = None,
    ) -> None:
        """新增或更新 community lookup thread 狀態。

        未傳的欄位在 UPDATE 時保留既有值（COALESCE），
        INSERT 時則使用 NULL（首次建立可能尚無 section / control_msg_id）。
        """
        slots_json = json.dumps(last_section_slots) if last_section_slots is not None else None
        await self.db.execute(
            """INSERT INTO community_lookup_threads
               (guild_id, source, lookup_id, thread_id, control_msg_id,
                last_section_date, last_section_slots,
                last_start_date, last_end_date, last_updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(guild_id, source, lookup_id) DO UPDATE SET
                   thread_id=excluded.thread_id,
                   control_msg_id=COALESCE(excluded.control_msg_id, community_lookup_threads.control_msg_id),
                   last_section_date=COALESCE(excluded.last_section_date, community_lookup_threads.last_section_date),
                   last_section_slots=COALESCE(excluded.last_section_slots, community_lookup_threads.last_section_slots),
                   last_start_date=COALESCE(excluded.last_start_date, community_lookup_threads.last_start_date),
                   last_end_date=COALESCE(excluded.last_end_date, community_lookup_threads.last_end_date),
                   last_updated_at=CURRENT_TIMESTAMP""",
            (
                guild_id,
                source,
                str(lookup_id),
                thread_id,
                control_msg_id,
                last_section_date,
                slots_json,
                last_start_date,
                last_end_date,
            ),
        )
        await self.db.commit()

    async def delete_community_lookup_thread(
        self, guild_id: int, source: str, lookup_id: str
    ) -> None:
        """刪除對應紀錄（thread 被手動刪除或失效時呼叫）。"""
        await self.db.execute(
            "DELETE FROM community_lookup_threads WHERE guild_id=? AND source=? AND lookup_id=?",
            (guild_id, source, str(lookup_id)),
        )
        await self.db.commit()

    # ── JSON 匯入 ──

    async def migrate_from_json(self, json_path: Path) -> bool:
        """從 sent_articles.json 匯入舊資料。匯入成功回傳 True。"""
        if not json_path.exists():
            return False

        # 檢查是否已有資料（避免重複匯入）
        async with self.db.execute("SELECT COUNT(*) FROM sent_content") as cursor:
            count = (await cursor.fetchone())[0]
        if count > 0:
            logger.info("StateDB 已有資料，跳過 JSON 匯入")
            return False

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # article IDs
            for aid in data.get("sent_article_ids", []):
                await self.db.execute(
                    "INSERT OR IGNORE INTO sent_content (source, content_key) VALUES ('article', ?)",
                    (str(aid),),
                )

            # FB post IDs
            for fid in data.get("sent_fbpost_ids", []):
                await self.db.execute(
                    "INSERT OR IGNORE INTO sent_content (source, content_key) VALUES ('fbpost', ?)",
                    (str(fid),),
                )

            # PTT article keys（sent_content 去重）
            for key in data.get("sent_article_keys", []):
                await self.db.execute(
                    "INSERT OR IGNORE INTO sent_content (source, content_key) VALUES ('ptt', ?)",
                    (str(key),),
                )

            # PTT state（forum_thread_state，只匯入有 thread_id 的）
            ptt_state = data.get("sent_ptt_state", {}) or {}
            for key, state in ptt_state.items():
                tid = state.get("thread_id")
                if not tid:
                    continue
                await self.db.execute(
                    """INSERT INTO forum_thread_state (source, content_key, thread_id, synced_comments_count)
                       VALUES ('ptt', ?, ?, ?)
                       ON CONFLICT(source, content_key)
                       DO UPDATE SET thread_id=excluded.thread_id,
                                     synced_comments_count=excluded.synced_comments_count""",
                    (str(key), tid, state.get("synced_comments_count", 0)),
                )

            await self.db.commit()

            # 匯入成功，備份原檔
            backup_path = json_path.with_suffix(".json.bak")
            json_path.rename(backup_path)
            logger.info("JSON 匯入完成，原檔已備份為 %s（匯入 %s articles, %s fb, %s ptt）",
                        backup_path,
                        len(data.get("sent_article_ids", [])),
                        len(data.get("sent_fbpost_ids", [])),
                        len(data.get("sent_article_keys", [])))
            return True

        except Exception as e:
            logger.error("JSON 匯入失敗: %s", e, exc_info=True)
            return False
