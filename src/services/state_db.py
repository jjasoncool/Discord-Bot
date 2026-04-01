"""
統一狀態追蹤資料庫（SQLite）

取代原本的 sent_articles.json，涵蓋所有來源：
- sent_content：所有來源的已發送去重
- forum_thread_state：PTT / Bahamut 等 forum 來源的 thread 追蹤
- bahamut_post_state / bahamut_comment_slot / bahamut_synced_comment：巴哈明細
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
"""

# 漸進式 migration（對既有 DB 安全，column 已存在會跳過）
_MIGRATIONS_SQL = [
    "ALTER TABLE bahamut_post_state ADD COLUMN content_hash TEXT",
    "ALTER TABLE bahamut_comment_slot ADD COLUMN content_hash TEXT",
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
            "SELECT sn, msg_id, content_hash FROM bahamut_post_state WHERE board_id=? AND post_id=?",
            (board_id, post_id),
        ) as cursor:
            post_rows = await cursor.fetchall()

        for post_row in post_rows:
            sn = post_row[0]
            post_state = {"msg_id": post_row[1], "content_hash": post_row[2], "comment_slots": [], "overflow_slots": []}

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
            await self.db.execute(
                """INSERT INTO bahamut_post_state (board_id, post_id, sn, msg_id, content_hash, updated_at)
                   VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(board_id, post_id, sn)
                   DO UPDATE SET msg_id=excluded.msg_id, content_hash=excluded.content_hash, updated_at=CURRENT_TIMESTAMP""",
                (board_id, post_id, sn, msg_id, post_hash),
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
