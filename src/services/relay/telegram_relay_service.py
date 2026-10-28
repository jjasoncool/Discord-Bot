"""Telegram -> Discord relay（先行實作版）。

設計原則：
1. 內容/格式在 Adapter。
2. Publisher 只做發送能力。
3. Telegram 來源走 LISTEN/NOTIFY + DB 補償輪詢。
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import os
import re
import shutil
import tempfile
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from sys_settings.paths import APP_ROOT, TELEGRAM_SCRAPER_DIR
from sys_settings.telegram_relay_settings import TelegramRelaySettings
from utils import hot_files
from utils.utils import CONFIG_FILE, ChannelConfig
from typing import Optional
from urllib.parse import quote_plus

import asyncpg
import discord
from services.relay.telegram_filter import MediaFile, Verdict, media_kind
from shared.telegram import MEDIA_HOLD_NOTIFY, MEDIA_RETRY_WINDOW, normalize_channel_identifier
from utils.discord_content import split_message
from utils.discord_threads import fetch_thread, reopen_thread
from utils.media_probe import probe_duration, run_media_tool
from utils.background_tasks import spawn, supervise

logger = logging.getLogger(__name__)

# 觸發 scraper 端 on-demand 重抓的 pg NOTIFY channel（須與 telegram_scraper/runner.py 一致）
EMOJI_REFETCH_CHANNEL = "telegram_emoji_refetch"


def apply_message_entities(
    text: str,
    entities: list[dict] | None,
    resolve_emoji=None,
) -> str:
    """套用 Telegram entities：MessageEntitySpoiler → Discord `||...||`；
    MessageEntityCustomEmoji → 對應的 Discord App Emoji 標記。

    Telegram 的 entity offset/length 以 UTF-16 code units 計，須先轉成 UTF-16-LE
    bytes 再切片，否則 BMP 外字元（部分 emoji / 罕字）會偏移。spoiler 與自訂表情
    合併在同一次「由後往前」的改寫，避免兩種 entity 並存時位移失效。

    resolve_emoji: callable(document_id:int) -> str|None，回傳該表情的 Discord 標記
    （`<:name:id>`）；回 None 表示不替換（保留原本的 fallback emoji）。
    """
    if not text or not entities:
        return text

    edits: list[dict] = []
    for ent in entities:
        if not isinstance(ent, dict):
            continue
        etype = ent.get("type")
        offset = ent.get("offset")
        length = ent.get("length")
        if offset is None or length is None:
            continue
        try:
            offset = int(offset)
            length = int(length)
        except (TypeError, ValueError):
            continue
        if length <= 0 or offset < 0:
            continue

        if etype == "MessageEntitySpoiler":
            edits.append({"kind": "spoiler", "offset": offset, "length": length})
        elif etype == "MessageEntityCustomEmoji" and resolve_emoji is not None:
            doc_id = ent.get("document_id")
            if doc_id is None:
                continue
            try:
                markup = resolve_emoji(int(doc_id))
            except Exception:
                markup = None
            if markup:
                edits.append({
                    "kind": "replace",
                    "offset": offset,
                    "length": length,
                    "markup": markup,
                })

    if not edits:
        return text

    text_bytes = text.encode("utf-16-le")
    marker = "||".encode("utf-16-le")

    # 由後往前套用，避免插入/替換後位移失效
    for edit in sorted(edits, key=lambda e: e["offset"], reverse=True):
        start = edit["offset"] * 2
        end = start + edit["length"] * 2
        if start < 0 or end > len(text_bytes):
            continue
        if edit["kind"] == "spoiler":
            text_bytes = (
                text_bytes[:start]
                + marker
                + text_bytes[start:end]
                + marker
                + text_bytes[end:]
            )
        else:  # replace（自訂表情）
            text_bytes = (
                text_bytes[:start]
                + edit["markup"].encode("utf-16-le")
                + text_bytes[end:]
            )

    return text_bytes.decode("utf-16-le")


@dataclass
class TelegramMediaRecord:
    file_rel_path: str
    media_type: str
    mime_type: Optional[str] = None
    file_size: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    duration_sec: Optional[int] = None
    is_spoiler: bool = False


@dataclass
class TelegramMessageRecord:
    message_pk: int
    telegram_chat_id: int
    telegram_message_id: int
    text: str
    message_date: Optional[object]
    has_media: bool
    chat_title: Optional[str] = None
    grouped_id: Optional[int] = None
    media_items: list[TelegramMediaRecord] = field(default_factory=list)
    entities: list[dict] = field(default_factory=list)


@dataclass
class AttachmentSpec:
    abs_path: str
    is_spoiler: bool = False
    filename: Optional[str] = None


@dataclass
class RenderOperation:
    op_type: str
    content: str = ""
    attachments: list[AttachmentSpec] = field(default_factory=list)
    embed: Optional[discord.Embed] = None


@dataclass
class RenderPlan:
    target_type: str
    operations: list[RenderOperation]
    payload_meta: dict


class TelegramMessageRepository:
    """Discord 端讀取 telegram_messages / telegram_message_media。"""

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self.pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        if self.pool is None:
            self.pool = await asyncpg.create_pool(dsn=self.dsn, min_size=1, max_size=5)

    async def close(self) -> None:
        if self.pool is not None:
            await self.pool.close()
            self.pool = None

    async def ensure_relay_tables(self) -> None:
        """建立 Relay 需要的狀態表（可重複執行）。"""
        if self.pool is None:
            raise RuntimeError("TelegramMessageRepository 尚未 connect")

        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS telegram_relay_delivery_state (
                    id BIGSERIAL PRIMARY KEY,
                    message_pk BIGINT NOT NULL REFERENCES telegram_messages(id) ON DELETE CASCADE,
                    discord_channel_id BIGINT NOT NULL,
                    delivered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE (message_pk, discord_channel_id)
                );
                """
            )
            # 要補判：開著過濾、模型沒判到就送進主頻道的（欄名要讓人看得懂）。預設 FALSE，加欄不改既有資料
            await conn.execute(
                "ALTER TABLE telegram_relay_delivery_state "
                "ADD COLUMN IF NOT EXISTS needs_recheck BOOLEAN NOT NULL DEFAULT FALSE;"
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS telegram_relay_runtime_state (
                    state_key TEXT PRIMARY KEY,
                    state_value TEXT NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
            # 自訂表情對照表（scraper 也會建；此處保險，避免 relay 先跑時查表報錯）
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS telegram_custom_emoji (
                    document_id BIGINT PRIMARY KEY,
                    file_rel_path TEXT,
                    mime_type TEXT,
                    is_animated BOOLEAN NOT NULL DEFAULT FALSE,
                    discord_emoji_id BIGINT,
                    discord_emoji_name TEXT,
                    status TEXT NOT NULL DEFAULT 'downloaded',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )

    async def get_custom_emoji(self, document_id: int) -> Optional[dict]:
        """讀取一筆自訂表情對照（含下載檔路徑與已上傳的 Discord emoji 資訊）。"""
        if self.pool is None:
            raise RuntimeError("TelegramMessageRepository 尚未 connect")
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT document_id, file_rel_path, mime_type, is_animated,
                       discord_emoji_id, discord_emoji_name, status
                FROM telegram_custom_emoji
                WHERE document_id = $1;
                """,
                int(document_id),
            )
        return dict(row) if row else None

    async def mark_custom_emoji_uploaded(
        self, document_id: int, discord_emoji_id: int, discord_emoji_name: str
    ) -> None:
        """回填上傳成功的 Discord App Emoji 資訊。"""
        if self.pool is None:
            raise RuntimeError("TelegramMessageRepository 尚未 connect")
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE telegram_custom_emoji
                SET discord_emoji_id = $2, discord_emoji_name = $3,
                    status = 'ok', updated_at = NOW()
                WHERE document_id = $1;
                """,
                int(document_id),
                int(discord_emoji_id),
                discord_emoji_name,
            )

    async def mark_custom_emoji_status(self, document_id: int, status: str) -> None:
        """標記自訂表情狀態（unsupported / failed 等）。"""
        if self.pool is None:
            raise RuntimeError("TelegramMessageRepository 尚未 connect")
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE telegram_custom_emoji
                SET status = $2, updated_at = NOW()
                WHERE document_id = $1;
                """,
                int(document_id),
                status,
            )

    async def find_messages_by_id(self, id_value: int) -> list[dict]:
        """用 db id 或 telegram_message_id 找訊息（供 /resend_article 解析）。

        多頻道時 telegram_message_id 可能撞號 → 回傳多筆讓上層要求以 db id 消歧義。
        """
        if self.pool is None:
            raise RuntimeError("TelegramMessageRepository 尚未 connect")
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, telegram_chat_id, telegram_message_id, chat_title
                FROM telegram_messages
                WHERE telegram_message_id = $1 OR id = $1
                ORDER BY id;
                """,
                int(id_value),
            )
        return [dict(row) for row in rows]

    async def send_pg_notify(self, channel: str, payload: str) -> None:
        """對 telegram_data 發 pg_notify（用來觸發 scraper 端重抓）。"""
        if self.pool is None:
            raise RuntimeError("TelegramMessageRepository 尚未 connect")
        async with self.pool.acquire() as conn:
            await conn.execute("SELECT pg_notify($1, $2)", channel, payload)

    async def get_present_emoji_ids(self, document_ids) -> set:
        """回傳這批 document_id 中「已在對照表」的集合（scraper 已下載/處理完）。"""
        if self.pool is None:
            raise RuntimeError("TelegramMessageRepository 尚未 connect")
        ids = [int(d) for d in document_ids]
        if not ids:
            return set()
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT document_id FROM telegram_custom_emoji WHERE document_id = ANY($1::bigint[]);",
                ids,
            )
        return {int(row["document_id"]) for row in rows}

    async def get_runtime_cursor_pk(self) -> Optional[int]:
        if self.pool is None:
            raise RuntimeError("TelegramMessageRepository 尚未 connect")
        async with self.pool.acquire() as conn:
            value = await conn.fetchval(
                """
                SELECT state_value
                FROM telegram_relay_runtime_state
                WHERE state_key = 'last_polled_pk';
                """
            )
        if value is None:
            return None
        try:
            return int(str(value))
        except (TypeError, ValueError):
            return None

    async def set_runtime_cursor_pk(self, message_pk: int) -> None:
        if self.pool is None:
            raise RuntimeError("TelegramMessageRepository 尚未 connect")
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO telegram_relay_runtime_state (state_key, state_value, updated_at)
                VALUES ('last_polled_pk', $1, NOW())
                ON CONFLICT (state_key)
                DO UPDATE SET
                    state_value = EXCLUDED.state_value,
                    updated_at = NOW();
                """,
                str(int(message_pk)),
            )

    async def get_pk_by_telegram_message_id(
        self,
        telegram_message_id: int,
        telegram_chat_id: Optional[int] = None,
    ) -> Optional[int]:
        """根據 telegram_message_id 查詢對應的 message_pk。

        若該訊息屬於 media group，自動回傳 group 首則（最小 pk），
        確保重發時能觸發完整的 group 合併流程。

        telegram_message_id 只在「同一來源（chat）內」唯一，跨來源會重號。
        傳入 telegram_chat_id 可把查詢鎖定到單一來源，避免多來源時抓錯訊息；
        不傳則沿用舊行為（不分來源、取最小 pk）。
        """
        if self.pool is None:
            raise RuntimeError("TelegramMessageRepository 尚未 connect")
        async with self.pool.acquire() as conn:
            if telegram_chat_id is None:
                row = await conn.fetchrow(
                    """
                    SELECT id, grouped_id, telegram_chat_id
                    FROM telegram_messages
                    WHERE telegram_message_id = $1
                    ORDER BY id ASC LIMIT 1;
                    """,
                    int(telegram_message_id),
                )
            else:
                row = await conn.fetchrow(
                    """
                    SELECT id, grouped_id, telegram_chat_id
                    FROM telegram_messages
                    WHERE telegram_message_id = $1 AND telegram_chat_id = $2
                    ORDER BY id ASC LIMIT 1;
                    """,
                    int(telegram_message_id),
                    int(telegram_chat_id),
                )
            if row is None:
                return None

            # 非 group 訊息，直接回傳
            if row["grouped_id"] is None:
                return int(row["id"])

            # 屬於 media group → 找同 group 最小 pk（首則）
            first_pk = await conn.fetchval(
                """
                SELECT id FROM telegram_messages
                WHERE grouped_id = $1 AND telegram_chat_id = $2
                ORDER BY id ASC LIMIT 1;
                """,
                int(row["grouped_id"]),
                int(row["telegram_chat_id"]),
            )
            return int(first_pk) if first_pk is not None else int(row["id"])

    async def mark_message_published(self, message_pk: int, discord_channel_id: int, *,
                                     needs_recheck: bool = False) -> None:
        """記成送到這個頻道；`needs_recheck`＝模型沒判到就送出，之後要補判（跟發送紀錄同一句寫，不會送了卻沒記）。"""
        if self.pool is None:
            raise RuntimeError("TelegramMessageRepository 尚未 connect")
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO telegram_relay_delivery_state (message_pk, discord_channel_id, delivered_at, needs_recheck)
                VALUES ($1, $2, NOW(), $3)
                ON CONFLICT (message_pk, discord_channel_id)
                DO UPDATE SET delivered_at = NOW(), needs_recheck = EXCLUDED.needs_recheck;
                """,
                int(message_pk),
                int(discord_channel_id),
                bool(needs_recheck),
            )

    async def mark_not_tracked(self, message_pk: int) -> None:
        """記成頻道 0（停止追蹤、不算送出）：重啟時的補償只撈完全沒有發送紀錄的，有這列就不再撿回來。"""
        if self.pool is None:
            raise RuntimeError("TelegramMessageRepository 尚未 connect")
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO telegram_relay_delivery_state (message_pk, discord_channel_id, delivered_at, needs_recheck)
                VALUES ($1, 0, NOW(), FALSE)
                ON CONFLICT (message_pk, discord_channel_id) DO NOTHING;
                """,
                int(message_pk),
            )

    async def list_needs_recheck(self, limit: int = 20) -> list[tuple[int, int, datetime]]:
        """要補判的（pk, 頻道, 送出時間），舊的先。"""
        if self.pool is None:
            raise RuntimeError("TelegramMessageRepository 尚未 connect")
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT message_pk, discord_channel_id, delivered_at FROM telegram_relay_delivery_state
                WHERE needs_recheck ORDER BY delivered_at, message_pk LIMIT $1;
                """,
                int(limit),
            )
        return [(int(r["message_pk"]), int(r["discord_channel_id"]), r["delivered_at"]) for r in rows]

    async def clear_needs_recheck(self, message_pks: list[int], discord_channel_id: int) -> None:
        """補判完（放行、或判不了也不必再判）：清掉要補判的標記。"""
        if self.pool is None:
            raise RuntimeError("TelegramMessageRepository 尚未 connect")
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE telegram_relay_delivery_state SET needs_recheck = FALSE
                WHERE message_pk = ANY($1::bigint[]) AND discord_channel_id = $2 AND needs_recheck;
                """,
                [int(pk) for pk in message_pks],
                int(discord_channel_id),
            )

    @contextlib.asynccontextmanager
    async def moving_deliveries(self, message_pks: list[int], from_channel_id: int, to_channel_id: int):
        """把這批 pk 的發送紀錄從 from 頻道改記成 to 頻道：只改頻道欄位（並清掉要補判的標記），`delivered_at` 不動（相簿補圖看第一次
        送出多久了，改成現在會讓舊相簿重新收補圖）。區塊內出錯就整批不改——搬移時區塊內刪主頻道原貼文，
        刪不掉就不能改紀錄。產出被改的（列 id, pk），寫進 log 供整批復原。"""
        if self.pool is None:
            raise RuntimeError("TelegramMessageRepository 尚未 connect")
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                rows = await conn.fetch(
                    """
                    UPDATE telegram_relay_delivery_state
                    SET discord_channel_id = $3, needs_recheck = FALSE
                    WHERE message_pk = ANY($1::bigint[]) AND discord_channel_id = $2
                    RETURNING id, message_pk;
                    """,
                    [int(pk) for pk in message_pks],
                    int(from_channel_id),
                    int(to_channel_id),
                )
                yield [(int(r["id"]), int(r["message_pk"])) for r in rows]

    async def get_delivery_state_count(self) -> int:
        if self.pool is None:
            raise RuntimeError("TelegramMessageRepository 尚未 connect")
        async with self.pool.acquire() as conn:
            value = await conn.fetchval("SELECT COUNT(*) FROM telegram_relay_delivery_state;")
        return int(value or 0)

    async def list_new_message_pks(self, after_pk: int, limit: int = 200) -> list[int]:
        if self.pool is None:
            raise RuntimeError("TelegramMessageRepository 尚未 connect")
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id
                FROM telegram_messages
                WHERE id > $1
                ORDER BY id ASC
                LIMIT $2;
                """,
                int(after_pk),
                int(limit),
            )
        return [int(row["id"]) for row in rows]

    async def list_undelivered_message_pks(self, after_pk: int = 0, limit: int = 500) -> list[int]:
        """列出目前尚未有任何 delivery_state 的 message_pk。"""
        if self.pool is None:
            raise RuntimeError("TelegramMessageRepository 尚未 connect")
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT m.id
                FROM telegram_messages m
                WHERE m.id > $1
                  AND NOT EXISTS (
                      SELECT 1
                      FROM telegram_relay_delivery_state d
                      WHERE d.message_pk = m.id
                  )
                ORDER BY m.id ASC
                LIMIT $2;
                """,
                int(after_pk),
                int(limit),
            )
        return [int(row["id"]) for row in rows]

    async def get_message_by_pk(self, message_pk: int) -> Optional[TelegramMessageRecord]:
        if self.pool is None:
            raise RuntimeError("TelegramMessageRepository 尚未 connect")

        async with self.pool.acquire() as conn:
            message_row = await conn.fetchrow(
                """
                SELECT
                    id,
                    telegram_chat_id,
                    telegram_message_id,
                    text,
                    message_date,
                    has_media,
                    chat_title,
                    grouped_id,
                    entities
                FROM telegram_messages
                WHERE id = $1;
                """,
                int(message_pk),
            )
            if message_row is None:
                return None

            media_rows = await conn.fetch(
                """
                SELECT
                    file_rel_path,
                    media_type,
                    mime_type,
                    file_size,
                    width,
                    height,
                    duration_sec,
                    is_spoiler
                FROM telegram_message_media
                WHERE message_id = $1
                ORDER BY id ASC;
                """,
                int(message_pk),
            )

        media_items = [
            TelegramMediaRecord(
                file_rel_path=str(row["file_rel_path"]),
                media_type=str(row["media_type"]),
                mime_type=row["mime_type"],
                file_size=row["file_size"],
                width=row["width"],
                height=row["height"],
                duration_sec=row["duration_sec"],
                is_spoiler=bool(row["is_spoiler"]),
            )
            for row in media_rows
        ]

        raw_gid = message_row["grouped_id"]
        grouped_id = int(raw_gid) if raw_gid is not None else None

        raw_entities = message_row["entities"]
        if raw_entities is None:
            entities: list[dict] = []
        elif isinstance(raw_entities, str):
            try:
                parsed = json.loads(raw_entities)
                entities = parsed if isinstance(parsed, list) else []
            except json.JSONDecodeError:
                entities = []
        elif isinstance(raw_entities, list):
            entities = raw_entities
        else:
            entities = []

        return TelegramMessageRecord(
            message_pk=int(message_row["id"]),
            telegram_chat_id=int(message_row["telegram_chat_id"]),
            telegram_message_id=int(message_row["telegram_message_id"]),
            text=str(message_row["text"] or ""),
            message_date=message_row["message_date"],
            has_media=bool(message_row["has_media"]),
            chat_title=message_row["chat_title"],
            grouped_id=grouped_id,
            media_items=media_items,
            entities=entities,
        )


    async def get_group_member_states(self, grouped_id: int, chat_id: int) -> list[tuple[int, bool]]:
        """取得同一 media group 的組員 (pk, 是否就緒)，按 telegram_message_id 排序。

        scraper 先寫訊息列、下載完才寫媒體列，「列存在」不代表圖已就緒；
        沒有媒體的組員（has_media=false）視為就緒。
        """
        if self.pool is None:
            raise RuntimeError("TelegramMessageRepository 尚未 connect")
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    m.id,
                    (NOT m.has_media OR EXISTS (
                        SELECT 1 FROM telegram_message_media mm WHERE mm.message_id = m.id
                    )) AS ready
                FROM telegram_messages m
                WHERE m.grouped_id = $1 AND m.telegram_chat_id = $2
                ORDER BY m.telegram_message_id ASC;
                """,
                int(grouped_id),
                int(chat_id),
            )
        return [(int(row["id"]), bool(row["ready"])) for row in rows]

    async def list_quarantined(self, thread_ids: list[int], main_channel_id: int) -> list[dict]:
        """送進這些隔離 thread、還沒放回這個主頻道的訊息（含媒體種類），依發文時間排。"""
        if self.pool is None:
            raise RuntimeError("TelegramMessageRepository 尚未 connect")
        ids = [int(t) for t in thread_ids]
        if not ids:
            return []
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT m.id, m.telegram_chat_id, m.telegram_message_id, m.grouped_id, m.message_date, m.text,
                       COALESCE(array_agg(mm.media_type) FILTER (WHERE mm.media_type IS NOT NULL), '{}') AS media
                FROM telegram_relay_delivery_state d
                JOIN telegram_messages m ON m.id = d.message_pk
                LEFT JOIN telegram_message_media mm ON mm.message_id = m.id
                WHERE d.discord_channel_id = ANY($1::bigint[])
                  AND NOT EXISTS (
                      SELECT 1 FROM telegram_relay_delivery_state x
                      WHERE x.message_pk = m.id AND x.discord_channel_id = $2
                  )
                GROUP BY m.id
                ORDER BY m.message_date, m.telegram_message_id;
                """,
                ids,
                int(main_channel_id),
            )
        return [
            {
                "pk": int(r["id"]), "chat_id": int(r["telegram_chat_id"]),
                "telegram_message_id": int(r["telegram_message_id"]),
                "grouped_id": int(r["grouped_id"]) if r["grouped_id"] is not None else None,
                "message_date": r["message_date"], "text": r["text"] or "", "media": list(r["media"]),
            }
            for r in rows
        ]

    async def get_deliveries(self, message_pks: list[int]) -> dict[int, dict[int, datetime]]:
        """這批 pk 送到過哪些頻道：{pk: {頻道 id: delivered_at}}。不含頻道 0（停止追蹤的標記，不是送出）。

        認「同一則或同一本相簿送去哪裡」要看所有頻道：被隔離的送進隔離 thread，只查主頻道會當成沒送過、重判重貼。
        """
        if self.pool is None:
            raise RuntimeError("TelegramMessageRepository 尚未 connect")
        pks = [int(pk) for pk in message_pks]
        if not pks:
            return {}
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT message_pk, discord_channel_id, delivered_at
                FROM telegram_relay_delivery_state
                WHERE message_pk = ANY($1::bigint[]) AND discord_channel_id <> 0;
                """,
                pks,
            )
        out: dict[int, dict[int, datetime]] = {}
        for row in rows:
            out.setdefault(int(row["message_pk"]), {})[int(row["discord_channel_id"])] = row["delivered_at"]
        return out

class MessageRouteResolver:
    """讀取 config.json，解析 telegram_chat_id 對應 Discord channel ids。"""

    def __init__(
        self,
        config_path: str | Path = CONFIG_FILE,
        telegram_runtime_config_path: str | Path = TELEGRAM_SCRAPER_DIR / "runtime_config.json",
    ) -> None:
        self.config_path = Path(config_path)
        self.telegram_runtime_config_path = Path(telegram_runtime_config_path)

    @staticmethod
    def _normalize_source_key(raw: object) -> str:
        return normalize_channel_identifier(str(raw or "")).lower()

    def _load_telegram_runtime_config(self) -> dict:
        """爬蟲那邊人手改的 runtime_config（頻道名稱等）；缺檔回空，改了下一次讀就生效。"""
        return hot_files.read_json(self.telegram_runtime_config_path, label="telegram runtime_config") or {}

    def _load_config(self) -> dict:
        return ChannelConfig.load_config(str(self.config_path), caller="telegram_relay")

    def is_telegram_relay_enabled(self) -> bool:
        config = self._load_config()
        return bool(config.get("telegram_relay_enabled", False))

    def validate_telegram_config(self) -> tuple[bool, str]:
        config = self._load_config()
        enabled = bool(config.get("telegram_relay_enabled", False))
        routes = config.get("telegram_channel_routes")

        if not enabled:
            return False, "telegram_relay_enabled=false"

        if routes is None:
            return False, "缺少 telegram_channel_routes"

        if not isinstance(routes, dict):
            return False, "telegram_channel_routes 必須是 dict"

        return True, "ok"

    @staticmethod
    def _coerce_msg_id(raw: object) -> Optional[int]:
        """把設定值轉成正整數的 telegram_message_id，無效則回 None。"""
        if isinstance(raw, bool):  # JSON 的 true/false 會變 bool，要先擋掉
            return None
        try:
            parsed = int(raw)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    def resolve_replay_msg_id(self, telegram_chat_id: int) -> Optional[int]:
        """解析「這個來源」的重送起始 telegram_message_id。

        支援兩種 config 格式：
          - 新版（per-來源）: {"<來源名稱或 chat_id>": <message_id>}
          - 舊版（全域）    : <message_id> 單一數字 → 套用到所有來源

        新版的來源解析方式與 telegram_channel_routes 一致：
        先用 chat_id 當 key，找不到再退回 telegram runtime 的 source_channel 名稱。
        """
        config = self._load_config()
        raw = config.get("telegram_replay_from_message_id")
        if raw is None:
            return None

        # 舊版：單一數字 = 全域重送
        if not isinstance(raw, dict):
            return self._coerce_msg_id(raw)

        # 新版：per-來源 dict
        val = raw.get(str(telegram_chat_id))
        if val is None:
            runtime_cfg = self._load_telegram_runtime_config()
            source_channel = self._normalize_source_key(runtime_cfg.get("source_channel"))
            if source_channel:
                val = raw.get(source_channel)
        return self._coerce_msg_id(val)

    def get_all_replay_msg_ids(self) -> list[int]:
        """列出所有設定的重送 message_id（不分來源），供開機時計算掃描起點用。"""
        config = self._load_config()
        raw = config.get("telegram_replay_from_message_id")
        if raw is None:
            return []
        candidates = raw.values() if isinstance(raw, dict) else [raw]
        result: list[int] = []
        for value in candidates:
            mid = self._coerce_msg_id(value)
            if mid is not None and mid not in result:
                result.append(mid)
        return result

    def resolve_telegram_routes(self, telegram_chat_id: int) -> list[int]:
        config = self._load_config()
        routes = config.get("telegram_channel_routes") or {}
        if not isinstance(routes, dict):
            return []

        route_values = routes.get(str(telegram_chat_id))

        # 支援以 source_channel 名稱設路由（目前 telegram scraper 常見配置）
        if not route_values:
            runtime_cfg = self._load_telegram_runtime_config()
            source_channel = self._normalize_source_key(runtime_cfg.get("source_channel"))
            if source_channel:
                route_values = routes.get(source_channel)

        if not route_values:
            return []

        if isinstance(route_values, (int, str)):
            route_values = [route_values]
        if not isinstance(route_values, list):
            return []

        normalized: list[int] = []
        for raw in route_values:
            try:
                cid = int(raw)
            except (TypeError, ValueError):
                continue
            if cid > 0:
                normalized.append(cid)
        return normalized


class TelegramRenderAdapter:
    """Telegram 專屬格式邏輯（保留現有格式策略，不在 publisher 改文案）。"""

    # Discord embed description 文件上限為 4096，但實測後端對接近上限的超長 embed
    # 會回 500（error code 0）而非乾淨的 400；本頻道送成功的最長一筆為 3012 字。
    # 保守取 3000 當「每段」上限：超過就切成多則連續發送（不截斷、不丟內容）。
    _DESCRIPTION_MAX_CHARS = 3000

    def __init__(self, app_root: str | Path = APP_ROOT) -> None:
        self.app_root = Path(app_root)
        self._runtime_config_path = self.app_root / "telegram_scraper" / "runtime_config.json"

    def _get_source_channel_name(self) -> str:
        """從 telegram runtime_config.json 讀取頻道名稱；讀不到就叫 Telegram。"""
        data = hot_files.read_json(self._runtime_config_path, label="telegram runtime_config") or {}
        name = str(data.get("source_channel", "")).strip()
        return name if name else "Telegram"

    def check_media_root(self) -> bool:
        media_root = self.app_root / "telegram_scraper" / "media"
        if media_root.exists() and media_root.is_dir():
            return True
        logger.warning("Telegram media 目錄不存在或不可用: %s", media_root)
        return False

    @staticmethod
    def _safe_file_sha1(abs_path: Path) -> Optional[str]:
        try:
            hasher = hashlib.sha1()
            with abs_path.open("rb") as f:
                while True:
                    chunk = f.read(1024 * 1024)
                    if not chunk:
                        break
                    hasher.update(chunk)
            return hasher.hexdigest()
        except Exception:
            return None

    def render(
        self,
        message: TelegramMessageRecord,
        emoji_map: dict | None = None,
        title_suffix: str = "",
    ) -> RenderPlan:
        attachments: list[AttachmentSpec] = []
        seen_media_keys: set[str] = set()

        for media in message.media_items:
            abs_path = self.app_root / media.file_rel_path
            if not abs_path.exists():
                logger.warning("Telegram relay 媒體檔不存在，略過: message_pk=%s path=%s", message.message_pk, abs_path)
                continue

            file_hash = self._safe_file_sha1(abs_path)
            dedupe_key = file_hash or str(abs_path.resolve())
            if dedupe_key in seen_media_keys:
                logger.info(
                    "Telegram relay 偵測重複圖片（已去重）: message_pk=%s path=%s",
                    message.message_pk,
                    abs_path,
                )
                continue
            seen_media_keys.add(dedupe_key)

            ext = abs_path.suffix or ".bin"
            filename = f"tg_{message.message_pk}_{len(attachments) + 1}{ext}"
            attachments.append(
                AttachmentSpec(
                    abs_path=str(abs_path),
                    is_spoiler=bool(media.is_spoiler),
                    filename=filename,
                )
            )

        # 先以 entities 還原 spoiler + 自訂表情，再依長度切成多段（保留全文，不截斷）
        resolve_emoji = (lambda did: (emoji_map or {}).get(did)) if emoji_map else None
        rendered_text = apply_message_entities(message.text or "", message.entities, resolve_emoji=resolve_emoji)
        content = rendered_text.strip()
        source_name = (message.chat_title or self._get_source_channel_name()) + title_suffix

        chunks = split_message(content, self._DESCRIPTION_MAX_CHARS) if content else [""]
        total = len(chunks)

        # 切成多段時，用標題「（續）」＋頁碼 footer「i/n」讓讀者看得出是同一篇連續文章；
        # 附件只掛在第一段，避免每段重送。
        operations: list[RenderOperation] = []
        for idx, chunk in enumerate(chunks):
            if total == 1:
                title = source_name
                footer = f"msg #{message.telegram_message_id} · db#{message.message_pk}"
            elif idx == 0:
                title = source_name
                footer = f"msg #{message.telegram_message_id} · db#{message.message_pk} · 1/{total}"
            else:
                title = f"{source_name}（續）"
                footer = f"msg #{message.telegram_message_id} · db#{message.message_pk} · {idx + 1}/{total}"

            embed = discord.Embed(
                title=title,
                description=chunk or None,
                color=0x2CA5E0,  # Telegram 藍
                timestamp=message.message_date,
            )
            embed.set_footer(text=footer)
            operations.append(
                RenderOperation(
                    op_type="send_message",
                    content="",
                    attachments=attachments if idx == 0 else [],
                    embed=embed,
                )
            )

        return RenderPlan(
            target_type="text_channel",
            operations=operations,
            payload_meta={
                "source": "telegram",
                "message_pk": message.message_pk,
                "telegram_chat_id": message.telegram_chat_id,
                "telegram_message_id": message.telegram_message_id,
                "version": 1,
            },
        )


class DiscordMessagePublisher:
    """共用發送能力：只執行 RenderPlan，不決定內容。"""

    # 備用上限（無法取得 guild 資訊時使用）
    _DISCORD_FILE_LIMIT_FALLBACK = 25 * 1024 * 1024 - 512 * 1024  # ~24.5 MB
    _IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff"}
    _VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv"}

    @staticmethod
    def _get_file_limit(channel: discord.abc.Messageable) -> int:
        """從 channel 所屬 guild 取得實際檔案上限，留 512 KB 餘裕。"""
        guild = getattr(channel, "guild", None)
        if guild is not None:
            return guild.filesize_limit - 512 * 1024
        return DiscordMessagePublisher._DISCORD_FILE_LIMIT_FALLBACK

    @staticmethod
    def _chunk_attachments(attachments: list[AttachmentSpec], chunk_size: int = 10) -> list[list[AttachmentSpec]]:
        return [attachments[i:i + chunk_size] for i in range(0, len(attachments), chunk_size)]

    # ------------------------------------------------------------------
    # 媒體壓縮：影片 (ffmpeg) / 圖片 (Pillow)
    # ------------------------------------------------------------------

    @staticmethod
    async def _compress_video(src: str, dst: str, target_bytes: int) -> bool:
        """用 ffmpeg 將影片壓縮到 target_bytes 以內（CRF 品質優先 + maxrate 兜底）。

        策略：CRF 23 保證畫質穩定，maxrate 限制峰值 bitrate 使檔案不超限，
        bufsize 設為 maxrate 的 2 倍讓動態場景有足夠緩衝，避免卡頓掉幀。
        若第一輪 CRF 23 仍超限，用更高 CRF 重試一次。
        """
        duration = await probe_duration(src)
        if duration <= 0:
            logger.warning("無法取得影片長度，跳過壓縮: %s", src)
            return False

        # 目標平均 bitrate（留 5% 給容器 overhead）
        avg_bitrate = int(target_bytes * 8 / duration * 0.95)
        if avg_bitrate < 100_000:  # 低於 100 kbps 品質太差，放棄
            logger.warning("影片壓縮目標 bitrate 過低 (%d bps)，跳過: %s", avg_bitrate, src)
            return False

        src_size = os.path.getsize(src)
        # 音訊 bitrate 固定 128kbps，從目標扣除音訊佔用
        audio_bitrate = 128_000
        audio_bytes = int(audio_bitrate * duration / 8)
        video_target_bytes = max(target_bytes - audio_bytes, target_bytes // 2)
        # 目標影片 bitrate（留 3% 給容器 overhead）
        video_bitrate = int(video_target_bytes * 8 / duration * 0.97)

        if video_bitrate < 100_000:
            logger.warning("影片壓縮目標 bitrate 過低 (%d bps)，跳過: %s", video_bitrate, src)
            return False

        # two-pass 統計檔放在輸出目錄
        passlog = os.path.splitext(dst)[0] + "_passlog"

        logger.info(
            "影片壓縮開始 (two-pass, video_bitrate=%s): %s (來源 %s bytes, 目標 %s bytes, duration=%.1fs)",
            video_bitrate, src, src_size, target_bytes, duration,
        )

        # Pass 1：分析，不產出影片
        pass1_cmd = [
            "ffmpeg", "-y", "-i", src,
            "-c:v", "libx264", "-preset", "medium",
            "-b:v", str(video_bitrate),
            "-pass", "1", "-passlogfile", passlog,
            "-an",
            "-f", "null", "/dev/null",
        ]
        # 每一道都有時限：轉發一次只處理一則，ffmpeg 卡住整條轉發就停
        timeout = TelegramRelaySettings().video_compress_timeout_seconds
        result = await run_media_tool(pass1_cmd, timeout=timeout)
        if not result.ok:
            logger.warning("ffmpeg pass 1 失敗 (rc=%s): %s\n%s", result.returncode, src, result.stderr.decode()[-500:])
            return False

        logger.info("影片壓縮 pass 1 完成，開始 pass 2: %s", src)

        # Pass 2：根據統計精確編碼
        pass2_cmd = [
            "ffmpeg", "-y", "-i", src,
            "-c:v", "libx264", "-preset", "medium",
            "-b:v", str(video_bitrate),
            "-pass", "2", "-passlogfile", passlog,
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            dst,
        ]
        result = await run_media_tool(pass2_cmd, timeout=timeout)

        # 清理 passlog 暫存檔
        for suffix in ("", "-0.log", "-0.log.mbtree"):
            path = passlog + suffix
            if os.path.exists(path):
                os.remove(path)

        if not result.ok:
            logger.warning("ffmpeg pass 2 失敗 (rc=%s): %s\n%s", result.returncode, src, result.stderr.decode()[-500:])
            return False

        result_size = os.path.getsize(dst)
        logger.info(
            "影片壓縮完成 (two-pass): %s -> %s bytes (limit=%s)",
            src, result_size, target_bytes,
        )
        if result_size > target_bytes:
            logger.warning("ffmpeg two-pass 壓縮後仍超限 (%s bytes > %s): %s", result_size, target_bytes, src)
            return False

        return True

    @staticmethod
    async def _compress_image(src: str, dst: str, target_bytes: int) -> bool:
        """用 Pillow 縮圖到 target_bytes 以內。回傳是否成功。"""
        from PIL import Image

        def _do_compress() -> bool:
            try:
                img = Image.open(src)
            except Exception as exc:
                logger.warning("Pillow 無法開啟圖片: %s err=%s", src, exc)
                return False

            # 先嘗試只降品質（JPEG）
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            for quality in (85, 70, 50, 30):
                img.save(dst, format="JPEG", quality=quality, optimize=True)
                if os.path.getsize(dst) <= target_bytes:
                    logger.info("圖片壓縮完成 (quality=%s): %s -> %s bytes", quality, src, os.path.getsize(dst))
                    return True

            # 品質不夠，逐步縮小解析度
            scale = 0.75
            for _ in range(4):
                new_w = int(img.width * scale)
                new_h = int(img.height * scale)
                if new_w < 100 or new_h < 100:
                    break
                resized = img.resize((new_w, new_h), Image.LANCZOS)
                resized.save(dst, format="JPEG", quality=50, optimize=True)
                if os.path.getsize(dst) <= target_bytes:
                    logger.info("圖片縮小完成 (%sx%s): %s -> %s bytes", new_w, new_h, src, os.path.getsize(dst))
                    return True
                scale *= 0.75

            logger.warning("圖片壓縮後仍超限: %s", src)
            return False

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _do_compress)

    async def _ensure_under_limit(self, attachment: AttachmentSpec, tmp_dir: str, file_limit: int) -> Optional[AttachmentSpec]:
        """檢查附件大小，超過上限時嘗試壓縮。回傳可用的 AttachmentSpec 或 None（放棄）。"""
        file_size = os.path.getsize(attachment.abs_path)
        if file_size <= file_limit:
            return attachment

        ext = os.path.splitext(attachment.abs_path)[1].lower()
        original_name = attachment.filename or os.path.basename(attachment.abs_path)
        logger.warning(
            "附件超過 Discord 上限 (%s bytes, limit=%s): %s — 嘗試壓縮",
            file_size, file_limit, attachment.abs_path,
        )

        if ext in self._VIDEO_EXTS:
            dst = os.path.join(tmp_dir, f"compressed_{original_name}")
            # 輸出一定是 mp4
            if not dst.lower().endswith(".mp4"):
                dst = os.path.splitext(dst)[0] + ".mp4"
                original_name = os.path.splitext(original_name)[0] + ".mp4"
            ok = await self._compress_video(attachment.abs_path, dst, file_limit)
            if ok:
                return AttachmentSpec(
                    abs_path=dst,
                    is_spoiler=attachment.is_spoiler,
                    filename=original_name,
                )
        elif ext in self._IMAGE_EXTS:
            dst = os.path.join(tmp_dir, f"compressed_{os.path.splitext(original_name)[0]}.jpg")
            ok = await self._compress_image(attachment.abs_path, dst, file_limit)
            if ok:
                return AttachmentSpec(
                    abs_path=dst,
                    is_spoiler=attachment.is_spoiler,
                    filename=os.path.splitext(original_name)[0] + ".jpg",
                )
        else:
            logger.warning("不支援壓縮的檔案類型 (%s)，跳過: %s", ext, attachment.abs_path)

        logger.warning("附件壓縮失敗或仍超限，跳過該檔案: %s", attachment.abs_path)
        return None

    # ------------------------------------------------------------------

    async def publish_to_channel(self, channel: discord.abc.Messageable, plan: RenderPlan, *,
                                 sent: Optional[list] = None) -> int:
        """`sent`：給了就把送出的每則 Discord 訊息放進去（搬移失敗時要收回剛貼的那份）。"""
        published_count = 0
        tmp_dir: Optional[str] = None
        file_limit = self._get_file_limit(channel)
        logger.debug("Discord 檔案上限: %s bytes (guild=%s)", file_limit, getattr(getattr(channel, "guild", None), "name", "N/A"))

        async def send(**kwargs) -> None:
            message = await channel.send(**kwargs)
            if sent is not None:
                sent.append(message)

        try:
            for operation in plan.operations:
                if operation.op_type != "send_message":
                    logger.warning("未知 RenderOperation，略過: %s", operation.op_type)
                    continue

                valid_attachments: list[AttachmentSpec] = []
                for attachment in operation.attachments:
                    if not os.path.exists(attachment.abs_path):
                        logger.warning("附件不存在，略過: %s", attachment.abs_path)
                        continue
                    valid_attachments.append(attachment)

                # 檢查大小，必要時壓縮
                sized_attachments: list[AttachmentSpec] = []
                for attachment in valid_attachments:
                    file_size = os.path.getsize(attachment.abs_path)
                    if file_size > file_limit:
                        if tmp_dir is None:
                            tmp_dir = tempfile.mkdtemp(prefix="tg_relay_compress_")
                        result = await self._ensure_under_limit(attachment, tmp_dir, file_limit)
                        if result is not None:
                            sized_attachments.append(result)
                    else:
                        sized_attachments.append(attachment)

                chunks = self._chunk_attachments(sized_attachments, chunk_size=10)

                if not chunks:
                    await send(content=operation.content or None, embed=operation.embed)
                    published_count += 1
                    continue

                # 把所有附件攤平成單一列表，並分離圖片與非圖片（影片等）
                all_items = [item for chunk in chunks for item in chunk]
                _image_exts = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

                def _is_image(item: AttachmentSpec) -> bool:
                    fn = (item.filename or "").lower()
                    return fn.rsplit(".", 1)[-1] in {e.lstrip(".") for e in _image_exts}

                image_items = [item for item in all_items if _is_image(item)]
                non_image_items = [item for item in all_items if not _is_image(item)]

                # 第一則：embed（+ 第一張圖片，若有的話）
                embed = operation.embed.copy() if operation.embed else None
                first_image_file: Optional[discord.File] = None
                if image_items and not image_items[0].is_spoiler:
                    first = image_items[0]
                    first_image_file = discord.File(
                        first.abs_path,
                        filename=first.filename or os.path.basename(first.abs_path),
                        spoiler=first.is_spoiler,
                    )
                    if embed is not None:
                        embed.set_image(url=f"attachment://{first.filename}")
                    image_items = image_items[1:]

                send_files = [first_image_file] if first_image_file else []
                await send(content=operation.content or None, embed=embed, files=send_files or None)
                published_count += 1

                # 剩餘圖片分批發送
                if image_items:
                    for chunk in self._chunk_attachments(image_items, chunk_size=10):
                        files = [
                            discord.File(
                                item.abs_path,
                                filename=item.filename or os.path.basename(item.abs_path),
                                spoiler=item.is_spoiler,
                            )
                            for item in chunk
                        ]
                        await send(files=files)
                        published_count += 1

                # 非圖片附件（影片等）在 embed 之後發送
                if non_image_items:
                    for chunk in self._chunk_attachments(non_image_items, chunk_size=10):
                        files = [
                            discord.File(
                                item.abs_path,
                                filename=item.filename or os.path.basename(item.abs_path),
                                spoiler=item.is_spoiler,
                            )
                            for item in chunk
                        ]
                        await send(files=files)
                        published_count += 1
        finally:
            # 清理暫存壓縮檔
            if tmp_dir is not None:
                shutil.rmtree(tmp_dir, ignore_errors=True)

        return published_count


class CustomEmojiResolver:
    """把 Telegram 內嵌自訂表情（premium custom emoji）轉成 Discord App Emoji。

    以全域 document_id 為 key（表情不屬於任何頻道）查對照表；未上傳過的就把下載好的
    靜態表情（webp）轉成 PNG、上傳成 bot 私有的 Application Emoji、回填對照表。
    Phase 1 只處理靜態；動態（tgs/webm）標記 unsupported、保留 fallback。
    """

    def __init__(self, bot, repository: "TelegramMessageRepository", app_root: Path) -> None:
        self.bot = bot
        self.repository = repository
        self.app_root = Path(app_root)
        self._app_emoji_by_name: Optional[dict] = None  # name -> discord.Emoji，快取

    async def resolve(self, entities: list[dict] | None) -> dict:
        """回傳 {document_id: '<:name:id>'}，只含成功解析的表情。"""
        if not entities:
            return {}
        doc_ids: list[int] = []
        for ent in entities:
            if isinstance(ent, dict) and ent.get("type") == "MessageEntityCustomEmoji":
                did = ent.get("document_id")
                if did is not None and int(did) not in doc_ids:
                    doc_ids.append(int(did))
        result: dict = {}
        for did in doc_ids:
            try:
                markup = await self._resolve_one(did)
            except Exception as exc:
                logger.warning("解析自訂表情失敗 doc=%s: %s", did, exc)
                markup = None
            if markup:
                result[did] = markup
        return result

    async def _ensure_cache(self) -> None:
        if self._app_emoji_by_name is not None:
            return
        try:
            emojis = await self.bot.fetch_application_emojis()
            self._app_emoji_by_name = {e.name: e for e in emojis}
        except Exception as exc:
            logger.warning("讀取 application emojis 失敗: %s", exc)
            self._app_emoji_by_name = {}

    async def _resolve_one(self, document_id: int) -> Optional[str]:
        row = await self.repository.get_custom_emoji(document_id)
        if row is None:
            return None
        # 已上傳過 → 直接用
        if row.get("discord_emoji_id") and row.get("status") == "ok":
            name = row.get("discord_emoji_name") or f"tg_{document_id}"
            return f"<:{name}:{int(row['discord_emoji_id'])}>"
        # 動態表情：Phase 1 不做
        if row.get("is_animated"):
            await self.repository.mark_custom_emoji_status(document_id, "unsupported")
            return None
        rel = row.get("file_rel_path")
        if not rel:
            return None
        abs_path = self.app_root / rel
        if not abs_path.exists():
            logger.warning("自訂表情檔不存在: %s", abs_path)
            return None

        name = f"tg_{document_id}"
        try:
            image_bytes = self._to_png_bytes(abs_path)
        except Exception as exc:
            logger.warning("自訂表情轉檔失敗 doc=%s: %s", document_id, exc)
            await self.repository.mark_custom_emoji_status(document_id, "failed")
            return None

        await self._ensure_cache()
        existing = (self._app_emoji_by_name or {}).get(name)
        if existing is not None:
            await self.repository.mark_custom_emoji_uploaded(document_id, existing.id, name)
            return f"<:{name}:{existing.id}>"

        try:
            emoji = await self.bot.create_application_emoji(name=name, image=image_bytes)
        except Exception as exc:
            logger.warning("建立 application emoji 失敗 doc=%s: %s", document_id, exc)
            # 可能名稱已存在（競態）→ 重讀快取再試一次
            self._app_emoji_by_name = None
            await self._ensure_cache()
            existing = (self._app_emoji_by_name or {}).get(name)
            if existing is not None:
                await self.repository.mark_custom_emoji_uploaded(document_id, existing.id, name)
                return f"<:{name}:{existing.id}>"
            await self.repository.mark_custom_emoji_status(document_id, "failed")
            return None

        if self._app_emoji_by_name is not None:
            self._app_emoji_by_name[name] = emoji
        await self.repository.mark_custom_emoji_uploaded(document_id, emoji.id, name)
        return f"<:{name}:{emoji.id}>"

    @staticmethod
    def _to_png_bytes(abs_path: Path) -> bytes:
        """把靜態表情（webp 等）轉成 <=128px 的 PNG bytes（符合 Discord emoji 限制）。"""
        import io

        from PIL import Image

        with Image.open(abs_path) as im:
            im = im.convert("RGBA")
            im.thumbnail((128, 128))
            buf = io.BytesIO()
            im.save(buf, format="PNG")
            return buf.getvalue()


@dataclass
class _RouteDeliveries:
    """一則或一本相簿在某個主頻道的發送紀錄，依去向分開（pk → delivered_at）。"""
    main: dict[int, datetime] = field(default_factory=dict)
    #: 送進這個主頻道的隔離 thread（含被刪重建前的舊 thread）
    quarantine: dict[int, datetime] = field(default_factory=dict)

    @property
    def sent(self) -> dict[int, datetime]:
        return {**self.quarantine, **self.main}


@dataclass(frozen=True)
class QuarantineItem:
    """隔離區裡還沒放回的一個發送單位（面板的選單用）。"""
    #: 單則本身；相簿是 Telegram 順序第一張（跟發文 footer 的 db# 一致）
    pk: int
    posted: Optional[datetime]
    text: str
    image_count: int = 0
    video_count: int = 0


class SentButNotRecorded(RuntimeError):
    """已經送出，但發送紀錄沒寫上（資料庫暫時失敗）。重送會重複貼文，呼叫端不能當成「沒送出」重試。"""


# 轉發貼文認回 Telegram 那則（`TelegramRenderAdapter.render`）：embed footer「msg #… · db#<pk>」，或附件檔名
# tg_<pk>_<n>。相簿第 2 批起的圖、影片是另外一則、沒有 embed，只認得出檔名；有雷的附件 Discord 會在檔名前加 SPOILER_
_FOOTER_PK = re.compile(r"db#(\d+)")
_ATTACHMENT_PK = re.compile(r"^(?:SPOILER_)?tg_(\d+)_\d+\.")


def _footer_pks(message) -> set[int]:
    footers = [getattr(getattr(e, "footer", None), "text", "") or "" for e in getattr(message, "embeds", None) or []]
    return {int(pk) for text in footers for pk in _FOOTER_PK.findall(text)}


def relay_post_pks(message) -> set[int]:
    """bot 轉發的一則 Discord 訊息屬於哪幾則 Telegram 訊息（pk）；不是轉發的回空集合。"""
    names = [getattr(a, "filename", "") or "" for a in getattr(message, "attachments", None) or []]
    return _footer_pks(message) | {int(m.group(1)) for name in names if (m := _ATTACHMENT_PK.match(name))}


class MessageRelayWorker:
    """Telegram Relay Worker：LISTEN + 補償 polling + 去重。

    開了 LLM 過濾（`content_filter`，見 `services.relay.telegram_filter`）時，每個發送單位（單則或整本相簿）
    送出前判一次，判成垃圾的改送主頻道底下的隔離 thread（`quarantine`），發送紀錄記 thread 的 id。
    晚到的圖跟著同一則或同一本的去向送、不再判；被隔離的再被排進來也不會重判重貼。
    """

    def __init__(
        self,
        *,
        bot: discord.Client,
        repository: TelegramMessageRepository,
        route_resolver: MessageRouteResolver,
        render_adapter: TelegramRenderAdapter,
        publisher: DiscordMessagePublisher,
        dsn: str,
        notify_channel: str = "telegram_new_message",
        poll_interval_sec: int = 3600,
        content_filter=None,
        quarantine=None,
    ) -> None:
        self.bot = bot
        self.repository = repository
        self.route_resolver = route_resolver
        self.render_adapter = render_adapter
        self.publisher = publisher
        self.dsn = dsn
        self.notify_channel = notify_channel
        self.poll_interval_sec = poll_interval_sec
        #: 相簿到齊判斷看時間、睡覺都經過這兩個：正式就是 time.monotonic 與 asyncio.sleep，測試換成假時鐘
        self._clock = time.monotonic
        self._sleep = asyncio.sleep
        #: 發文超過這麼久的不送（`_skip_if_stale`）；測試資料用固定日期時換成更長的
        self._max_message_age = timedelta(days=TelegramRelaySettings().max_message_age_days)
        self._emoji_resolver = CustomEmojiResolver(bot, repository, render_adapter.app_root)
        #: 有 `mode`（off／dry_run／on）與 `judge(text, media, trace_id=)` 的物件；None＝不過濾（測試預設）
        self._filter = content_filter
        #: `QuarantineThreads`；None＝沒有隔離區（判成垃圾也照常送主頻道）
        self._quarantine = quarantine

        self._running = False
        self._queue: asyncio.Queue[int] = asyncio.Queue(maxsize=5000)
        self._tasks: list[asyncio.Task] = []
        self._listen_conn: asyncpg.Connection | None = None

        self._processed_set: set[int] = set()
        self._processed_order: deque[int] = deque(maxlen=5000)
        self._queued_set: set[int] = set()  # 追蹤已在 queue 中的 PK，防止重複入隊
        # 處理中又收到通知的 PK（例如判斷途中爬蟲補到圖）：處理完再排一次，不直接丟掉。
        # 還在佇列裡、沒開始處理的不用：輪到時本來就會讀到最新的資料
        self._requeue: set[int] = set()
        self._processing: set[int] = set()
        # 放回、搬移同時只做一則：兩位管理員同時按同一則時，第二位會看到「已經放回過了」
        self._quarantine_lock = asyncio.Lock()
        # 開了過濾時一次只處理一則（開關每則重讀，切換不用重啟）
        self._filtered_lock = asyncio.Lock()
        # 待補判：模型恢復回應時叫醒補判（`_recheck_loop`）；確定沒有待補判的才不叫（啟動時不知道，先當有）
        self._recheck_wake = asyncio.Event()
        self._recheck_known = True
        self._last_polled_pk: int = 0

        # 正在收集的 media group（key=(chat_id, grouped_id)）。收集期間到的組員只登記到
        # _dirty_groups 就返回，由收集者發完後回頭複查，不各自佔處理槽空等。
        self._active_groups: set[tuple[int, int]] = set()
        self._dirty_groups: set[tuple[int, int]] = set()

    @property
    def running(self) -> bool:
        return self._running

    async def start(self) -> None:
        if self._running:
            return

        valid, reason = self.route_resolver.validate_telegram_config()
        if not valid:
            logger.warning("Telegram Relay Worker 未啟動：%s", reason)
            return

        self.render_adapter.check_media_root()

        await self.repository.connect()
        await self.repository.ensure_relay_tables()

        # 重發模式：把所有來源設定的 telegram_message_id 換算成 message_pk，
        # 取最小者當「掃描起點」（cursor 只是掃描下限，多倒帶只是多掃、靠 delivery_state
        # 去重，安全；真正「哪些訊息要強制重送」由每則訊息依自己的來源各別判斷）。
        replay_from_pk: Optional[int] = None
        replay_msg_ids = self.route_resolver.get_all_replay_msg_ids()
        for replay_msg_id in replay_msg_ids:
            pk = await self.repository.get_pk_by_telegram_message_id(replay_msg_id)
            if pk is None:
                logger.warning(
                    "Telegram Relay 重送模式：找不到 telegram_message_id=%s 對應的訊息，忽略",
                    replay_msg_id,
                )
                continue
            replay_from_pk = pk if replay_from_pk is None else min(replay_from_pk, pk)

        if replay_from_pk is not None:
            self._last_polled_pk = max(0, replay_from_pk - 1)
            await self.repository.set_runtime_cursor_pk(self._last_polled_pk)
            logger.warning(
                "Telegram Relay 啟用重送模式：掃描起點 message_pk=%s（共 %d 個來源設定）",
                replay_from_pk, len(replay_msg_ids),
            )
        else:
            saved_cursor = await self.repository.get_runtime_cursor_pk()
            if saved_cursor is not None:
                self._last_polled_pk = max(0, saved_cursor)
            else:
                # 首次啟動時從最早資料開始掃描，搭配 delivery_state 去重，避免漏補發
                self._last_polled_pk = 0
                await self.repository.set_runtime_cursor_pk(self._last_polled_pk)

        bootstrap_count = await self._enqueue_backfill_once(after_pk=self._last_polled_pk)

        # 安全補償：掃描所有尚未有 delivery_state 的歷史訊息，
        # 避免 cursor 已推進但舊訊息未送出的情況（例如 DB 重建後 delivery_state 遺失）。
        if replay_from_pk is None:
            reconcile_pks = await self.repository.list_undelivered_message_pks(after_pk=0, limit=5000)
            for message_pk in reconcile_pks:
                await self._enqueue_message_pk(message_pk)
            reconcile_count = len(reconcile_pks)
            if reconcile_count > 0:
                logger.warning(
                    "Telegram Relay 啟動補償：偵測到 %s 筆未發送訊息，已排入佇列",
                    reconcile_count,
                )
                bootstrap_count += reconcile_count

        self._running = True

        self._tasks = [
            supervise(self._listen_loop, name="telegram_relay_listen"),
            supervise(self._poll_loop, name="telegram_relay_poll"),
            supervise(self._process_loop, name="telegram_relay_process"),
            supervise(self._recheck_loop, name="telegram_relay_recheck"),
        ]
        logger.info("Telegram Relay Worker 已啟動（notify=%s poll=%ss）", self.notify_channel, self.poll_interval_sec)
        if bootstrap_count > 0:
            logger.info("Telegram Relay 啟動補償已排入 %s 筆歷史訊息", bootstrap_count)

    async def _enqueue_backfill_once(self, after_pk: int) -> int:
        """啟動時立即做一次 DB 補償掃描，把既有訊息排入 queue。"""
        cursor = max(0, int(after_pk))
        total = 0

        while True:
            pks = await self.repository.list_new_message_pks(after_pk=cursor, limit=500)
            if not pks:
                break

            for message_pk in pks:
                await self._enqueue_message_pk(message_pk)

            total += len(pks)
            cursor = max(cursor, max(pks))

            if len(pks) < 500:
                break

        return total

    async def stop(self) -> None:
        if not self._running:
            return

        self._running = False
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()

        if self._listen_conn is not None:
            try:
                await self._listen_conn.close()
            except Exception:
                pass
            self._listen_conn = None

        await self.repository.close()
        logger.info("Telegram Relay Worker 已停止")

    def _mark_processed(self, message_pk: int) -> None:
        if message_pk in self._processed_set:
            return

        if len(self._processed_order) >= self._processed_order.maxlen:
            old = self._processed_order.popleft()
            self._processed_set.discard(old)

        self._processed_set.add(message_pk)
        self._processed_order.append(message_pk)

    def _seen_processed(self, message_pk: int) -> bool:
        return message_pk in self._processed_set

    async def _enqueue_message_pk(self, message_pk: int) -> None:
        if message_pk <= 0:
            return
        if message_pk in self._processed_set:
            return
        if message_pk in self._queued_set:
            if message_pk in self._processing:
                self._requeue.add(message_pk)
            return
        try:
            self._queue.put_nowait(message_pk)
            self._queued_set.add(message_pk)
        except asyncio.QueueFull:
            logger.error("Telegram relay queue 已滿，丟棄 message_pk=%s", message_pk)

    async def _listen_loop(self) -> None:
        while self._running:
            try:
                conn = await asyncpg.connect(dsn=self.dsn)
                self._listen_conn = conn

                def _on_notify(_conn: asyncpg.Connection, _pid: int, _channel: str, payload: str) -> None:
                    try:
                        message_pk = int(str(payload).strip())
                    except (TypeError, ValueError):
                        logger.error("收到無效 NOTIFY payload: channel=%s payload=%s", self.notify_channel, payload)
                        return
                    logger.info("收到 NOTIFY: channel=%s message_pk=%s", _channel, message_pk)
                    spawn(self._enqueue_message_pk(message_pk), name=f"Telegram 通知入列 {message_pk}")

                await conn.add_listener(self.notify_channel, _on_notify)
                logger.info("Telegram relay LISTEN 已連線: channel=%s", self.notify_channel)

                while self._running and not conn.is_closed():
                    await asyncio.sleep(1)

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("Telegram relay LISTEN 失敗，5 秒後重連: %s", exc, exc_info=True)
                await asyncio.sleep(5)
            finally:
                if self._listen_conn is not None:
                    try:
                        await self._listen_conn.close()
                    except Exception:
                        pass
                    self._listen_conn = None

    async def _poll_loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(self.poll_interval_sec)
                new_pks = await self.repository.list_new_message_pks(after_pk=self._last_polled_pk, limit=500)
                if not new_pks:
                    continue

                for message_pk in new_pks:
                    await self._enqueue_message_pk(message_pk)
                self._last_polled_pk = max(self._last_polled_pk, max(new_pks))
                logger.info("Telegram relay 補償輪詢捕捉 %s 筆新訊息", len(new_pks))

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("Telegram relay 補償輪詢失敗: %s", exc, exc_info=True)
                await asyncio.sleep(5)

    async def _resolve_channel(self, channel_id: int) -> Optional[discord.abc.Messageable]:
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except Exception:
                channel = None
        if channel is None or not hasattr(channel, "send"):
            return None
        return channel  # type: ignore[return-value]

    async def _resolve_custom_emojis(self, entities) -> dict:
        """把訊息 entities 裡的自訂表情解析成 {document_id: markup}（best-effort）。"""
        try:
            return await self._emoji_resolver.resolve(entities)
        except Exception as exc:
            logger.warning("解析自訂表情整體失敗（略過）: %s", exc)
            return {}

    async def _wait_emoji_ready(self, message_pk: int, timeout: float = 15.0) -> bool:
        """poll DB 直到該訊息的自訂表情都「entities 有 document_id」且「已下載進對照表」或逾時。

        只檢查 entities 的 document_id 不夠——舊訊息可能先前已回填 document_id 但檔尚未下載，
        會造成過早判定就緒、resolver 抓到空表。故一併確認對照表已有該表情。
        """
        waited = 0.0
        interval = 0.5
        while waited < timeout:
            message = await self.repository.get_message_by_pk(message_pk)
            if message is not None:
                custom = [
                    e for e in (message.entities or [])
                    if isinstance(e, dict) and e.get("type") == "MessageEntityCustomEmoji"
                ]
                if not custom:
                    return True  # 這則沒有自訂表情，無需等待
                doc_ids = {int(e["document_id"]) for e in custom if e.get("document_id")}
                if len(doc_ids) == len(custom):
                    present = await self.repository.get_present_emoji_ids(doc_ids)
                    if doc_ids <= present:
                        return True
            await asyncio.sleep(interval)
            waited += interval
        return False

    async def resend_telegram_by_id(self, id_value: int) -> dict:
        """/resend_article type:telegram 用：以 db id 或 telegram_message_id 重送一則。

        流程：解析訊息 → 通知 scraper 即時重抓（補齊自訂表情）→ 等就緒 →
        解析 App Emoji → 渲染 → 送到該來源路由頻道（略過 delivery_state 去重，強制送）。
        """
        candidates = await self.repository.find_messages_by_id(id_value)
        if not candidates:
            return {"ok": False, "reason": "not_found"}
        if len(candidates) > 1:
            return {"ok": False, "reason": "ambiguous", "candidates": candidates}

        row = candidates[0]
        message_pk = int(row["id"])
        chat_id = int(row["telegram_chat_id"])
        tg_msg_id = int(row["telegram_message_id"])

        # 1. 通知 scraper 即時重抓（帶 chat_id，多頻道也抓對）
        refetch_ok = False
        try:
            await self.repository.send_pg_notify(
                EMOJI_REFETCH_CHANNEL,
                json.dumps({"chat_id": chat_id, "message_id": tg_msg_id}),
            )
            refetch_ok = await self._wait_emoji_ready(message_pk, timeout=15.0)
        except Exception as exc:
            logger.warning("觸發重抓失敗（改用現有 DB 內容）: %s", exc)

        # 2. 讀最新訊息 → 解析表情 → 渲染
        message = await self.repository.get_message_by_pk(message_pk)
        if message is None:
            return {"ok": False, "reason": "not_found"}
        emoji_map = await self._resolve_custom_emojis(message.entities)
        plan = self.render_adapter.render(message, emoji_map=emoji_map)

        # 3. 送到該來源的路由頻道
        route_ids = self._routes(message.telegram_chat_id)
        sent = 0
        channels: list[int] = []
        for channel_id in route_ids:
            channel = await self._resolve_channel(channel_id)
            if channel is None:
                continue
            sent += await self.publisher.publish_to_channel(channel, plan)
            channels.append(channel_id)

        custom_count = len([
            e for e in (message.entities or [])
            if isinstance(e, dict) and e.get("type") == "MessageEntityCustomEmoji"
        ])
        return {
            "ok": True,
            "sent": sent,
            "channels": channels,
            "refetch_ok": refetch_ok,
            "emoji_found": custom_count,
            "emoji_rendered": len(emoji_map),
            "db_id": message_pk,
            "telegram_message_id": tg_msg_id,
        }

    # media group 到齊判斷：scraper 先寫訊息列、下載完才寫媒體列，組員也可能逐則進來，
    # 所以要「每個組員都有媒體」且「這麼久沒有新組員、也沒有新就緒」才算到齊
    _GROUP_QUIET_SEC = 3.0
    # 等待上限：超過就先發已就緒的，其餘晚到的走補圖
    _GROUP_MAX_WAIT_SEC = 60.0
    # 等待期間輪詢 DB 的間隔秒數
    _GROUP_POLL_INTERVAL = 0.5
    # Telegram 相簿最多 10 則；湊滿且都就緒就不必再等安靜期
    _TELEGRAM_ALBUM_MAX = 10
    # 補圖時效：該組首次送出超過這麼久，晚到的組員就不補發。重啟時 reconcile 會把所有
    # 沒有 delivery 記錄的組員重新排入，沒有時效會把舊相簿的缺圖一口氣倒進頻道。
    _GROUP_FOLLOWUP_MAX_AGE = timedelta(hours=12)
    _GROUP_FOLLOWUP_TITLE_SUFFIX = "（補圖）"

    async def _wait_group_settled(self, grouped_id: int, chat_id: int) -> list[tuple[int, bool]]:
        """輪詢到整組到齊（或逾時），回傳組員 (pk, 是否就緒)。"""
        started = self._clock()
        last_change = started
        previous: Optional[list[tuple[int, bool]]] = None
        while True:
            members = await self.repository.get_group_member_states(grouped_id, chat_id)
            now = self._clock()
            if members != previous:
                previous = members
                last_change = now
            all_ready = bool(members) and all(ready for _, ready in members)
            if all_ready and (
                len(members) >= self._TELEGRAM_ALBUM_MAX
                or now - last_change >= self._GROUP_QUIET_SEC
            ):
                return members
            if now - started >= self._GROUP_MAX_WAIT_SEC:
                logger.warning(
                    "Telegram relay media group 等待逾時，先發已就緒者: grouped_id=%s members=%s",
                    grouped_id, members,
                )
                return members
            await self._sleep(self._GROUP_POLL_INTERVAL)

    async def _merge_group_messages(self, pks: list[int]) -> Optional[TelegramMessageRecord]:
        """把多則組員的文字與媒體合併到第一則上，成為單一虛擬訊息。"""
        merged_text_parts: list[str] = []
        merged_media: list[TelegramMediaRecord] = []
        first_msg: Optional[TelegramMessageRecord] = None
        merged_pks: list[int] = []

        for pk in pks:
            member = await self.repository.get_message_by_pk(pk)
            if member is None:
                continue
            merged_pks.append(pk)
            if first_msg is None:
                first_msg = member
            if member.text.strip():
                merged_text_parts.append(member.text.strip())
            merged_media.extend(member.media_items)

        if first_msg is None:
            return None

        first_msg.text = "\n".join(merged_text_parts)
        first_msg.media_items = merged_media
        logger.info(
            "Telegram relay media group 合併: grouped_id=%s pks=%s media_count=%s",
            first_msg.grouped_id, merged_pks, len(merged_media),
        )
        return first_msg

    async def _is_force_replay(self, chat_id: int, message_pk: int) -> bool:
        """依「這則訊息的來源」各別判斷是否強制重送；查 pk 時帶上 chat_id 鎖定來源，
        避免 telegram_message_id 跨來源重號時抓錯訊息。"""
        replay_msg_id = self.route_resolver.resolve_replay_msg_id(chat_id)
        if replay_msg_id is None:
            return False
        replay_pk = await self.repository.get_pk_by_telegram_message_id(replay_msg_id, chat_id)
        return replay_pk is not None and message_pk >= replay_pk

    @staticmethod
    def _message_age(message: TelegramMessageRecord) -> Optional[timedelta]:
        """Telegram 發文到現在多久；沒有發文時間回 None。"""
        posted = message.message_date
        if not isinstance(posted, datetime):
            return None
        if posted.tzinfo is None:
            posted = posted.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - posted

    async def _skip_if_stale(self, message: TelegramMessageRecord) -> bool:
        """發文超過 `_max_message_age` 的不送：記成頻道 0（停止追蹤）、當成處理過，回 True。

        頻道 0 不算送出，之後要送照樣送得出去。重送模式涵蓋的照送：那是人指定要重送的。沒有發文時間的當成新的。
        """
        age = self._message_age(message)
        if age is None or age <= self._max_message_age:
            return False
        if await self._is_force_replay(message.telegram_chat_id, message.message_pk):
            return False
        logger.info(
            "Telegram relay 發文超過 %g 天，不送: message_pk=%s telegram_chat_id=%s telegram_message_id=%s 發文 %s 前",
            self._max_message_age.total_seconds() / 86400, message.message_pk, message.telegram_chat_id,
            message.telegram_message_id, str(age).split(".")[0],
        )
        await self.repository.mark_not_tracked(message.message_pk)
        self._mark_processed(message.message_pk)
        return True

    async def _advance_cursor(self, message_pk: int) -> None:
        self._last_polled_pk = max(self._last_polled_pk, message_pk)
        await self.repository.set_runtime_cursor_pk(self._last_polled_pk)

    async def _route_deliveries(self, pks: list[int], route_ids: list[int]) -> dict[int, _RouteDeliveries]:
        """每個主頻道：這批 pk 送到主頻道的、送進它的隔離 thread 的。"""
        rows = await self.repository.get_deliveries(pks)
        out = {route_id: _RouteDeliveries() for route_id in route_ids}
        for pk, channels in rows.items():
            for channel_id, delivered_at in channels.items():
                if channel_id in out:
                    out[channel_id].main[pk] = delivered_at
                elif self._quarantine is not None:
                    parent = await self._quarantine.parent_of(channel_id)
                    if parent in out:
                        out[parent].quarantine[pk] = delivered_at
        return out

    def _group_pending(
        self,
        grouped_id: int,
        candidate_pks: list[int],
        channel_id: int,
        delivered: Optional[_RouteDeliveries],
        force_replay: bool,
    ) -> tuple[list[int], Optional[str]]:
        """回傳 (這個主頻道該發的組員 pk, 補圖跟著哪裡)。

        組內還沒有組員送過 → 第一次送（第二個值是 None，要過濾判斷）。已有組員送過 → 這次是補晚到的圖，
        跟著同本的去向（"main"／"quarantine"，有主頻道紀錄就是主頻道，含從隔離區放回的）、不再判斷；
        補圖超過時效則回傳空清單。
        """
        if force_replay or delivered is None:
            # 重送模式不看 delivery_state；這一輪已送過的（已標 processed）不再送。
            # 開了過濾時要注意：重播會重新判斷，被隔離的可能這次被放行貼進主頻道（thread 那則還在），
            # 晚到的組員也會被當成新相簿單獨判。重播是持續生效的旗標，用完要改回 null
            return [pk for pk in candidate_pks if not self._seen_processed(pk)], None

        sent = delivered.sent
        pending = [pk for pk in candidate_pks if pk not in sent]
        if not pending or not sent:
            return pending, None

        kind, times = ("main", delivered.main) if delivered.main else ("quarantine", delivered.quarantine)
        first_sent = min(times.values())
        if datetime.now(timezone.utc) - first_sent > self._GROUP_FOLLOWUP_MAX_AGE:
            logger.info(
                "Telegram relay 相簿補圖已過時效，略過: grouped_id=%s channel_id=%s pending=%s first_sent=%s",
                grouped_id, channel_id, pending, first_sent,
            )
            return [], kind
        return pending, kind

    def _filter_media(self, unit: TelegramMessageRecord) -> list[MediaFile]:
        root = Path(self.render_adapter.app_root)
        return [
            MediaFile(root / item.file_rel_path, media_kind(item.media_type, item.mime_type, item.file_rel_path))
            for item in unit.media_items
        ]

    async def _judge_unit(self, unit: TelegramMessageRecord, *, complete: bool) -> tuple[Optional[Verdict], bool]:
        """過濾一個發送單位 →（要隔離的判定, 要不要記成待補判）。

        - 判定：判成垃圾、而且要真的隔離時才有；其他情況（沒開、只記錄、放行）是 None。
        - 待補判：正式模式下模型沒判到（沒回應、出錯、回答看不懂）就照常送主頻道的，之後補判、是垃圾再搬走
          （每則訊息都要被檢查過）。
        - `complete=False`（相簿等待逾時只到齊一部分、單則的圖等太久還沒到）不判、照常送：只看到一部分就判，
          會把「文字只有水、圖是設計稿」那種情報錯關（13649）。
        """
        if not self._filter_active():
            return None, False
        mode = self._filter.mode
        if not complete:
            logger.info("Telegram 過濾：圖還沒到齊，不判、照常送 message_pk=%s", unit.message_pk)
            return None, False
        verdict = await self._filter.judge(unit.text, self._filter_media(unit), trace_id=f"tgfilter-{unit.message_pk}")
        logger.info(
            "Telegram 過濾：message_pk=%s 判定=%s 標籤=%s 理由=%s 看圖=%s 秒=%.1f 由模型判=%s mode=%s",
            unit.message_pk, "隔離" if verdict.quarantine else "放行", verdict.label or "-", verdict.reason or "-",
            verdict.images_seen, verdict.seconds, verdict.by_model, mode,
        )
        if verdict.by_model:
            if self._recheck_known:
                self._recheck_wake.set()   # 模型回應了：之前沒判到的可以補判
        elif verdict.recheck and mode == "on" and self._quarantine is not None:
            self._recheck_known = True
            logger.info("Telegram 過濾：沒判到就送主頻道，記成待補判 message_pk=%s", unit.message_pk)
            return None, True
        if not verdict.quarantine:
            return None, False
        if mode != "on" or self._quarantine is None:
            logger.info("Telegram 過濾（只記錄）：會隔離、照常送主頻道 message_pk=%s", unit.message_pk)
            return None, False
        return verdict, False

    @staticmethod
    def _verdict_header(verdict: Optional[Verdict]) -> str:
        """隔離那則最上面一行。"""
        if verdict is None:
            return ""
        return f"判定：{verdict.label}｜{verdict.reason}" if verdict.reason else f"判定：{verdict.label}"

    async def _destination(self, route_id: int, quarantine: bool) -> Optional[tuple[discord.abc.Messageable, int]]:
        """主頻道或它底下的隔離 thread →（可送的物件, 發送紀錄要記的頻道 id）；找不到回 None（這次不送、之後重試）。"""
        channel = await self._resolve_channel(route_id)
        if channel is None:
            logger.warning("Telegram relay 目標頻道不存在或不可發送: channel_id=%s", route_id)
            return None
        if not quarantine:
            return channel, route_id
        thread = await self._quarantine.thread_for(channel) if self._quarantine is not None else None
        if thread is None:
            logger.warning("Telegram relay 隔離 thread 取不到，這次不送、之後重試: channel_id=%s", route_id)
            return None
        return thread, int(thread.id)

    async def _send_unit(
        self,
        unit: TelegramMessageRecord,
        pks: list[int],
        channel: discord.abc.Messageable,
        channel_id: int,
        *,
        title_suffix: str = "",
        header: str = "",
        record: bool = True,
        sent: Optional[list] = None,
        needs_recheck: bool = False,
    ) -> int:
        """把一個發送單位送到頻道（或 thread），並把這批 pk 記成送到那裡。單則、相簿、隔離共用。

        `record=False`：不寫紀錄，由呼叫端改（搬移：主頻道原貼文刪掉後才改）；`sent`：收集送出的 Discord 訊息；
        `needs_recheck`：模型沒判到就送出，紀錄記成要補判。
        """
        logger.info(
            "Telegram relay 發送目標: channel_id=%s guild=%r channel=%r",
            channel_id,
            getattr(getattr(channel, "guild", None), "name", "N/A"),
            getattr(channel, "name", "N/A"),
        )
        emoji_map = await self._resolve_custom_emojis(unit.entities)
        plan = self.render_adapter.render(unit, emoji_map=emoji_map, title_suffix=title_suffix)
        if header and plan.operations:
            plan.operations[0].content = header
        count = await self.publisher.publish_to_channel(channel, plan, sent=sent)
        if not record:
            return count
        try:
            for pk in pks:
                await self.repository.mark_message_published(pk, channel_id, needs_recheck=needs_recheck)
        except Exception as exc:
            raise SentButNotRecorded(f"已送到 {channel_id}，但發送紀錄沒寫上：{exc}") from exc
        return count

    # ------------------------------------------------------------------
    # 隔離區：清單與放回主頻道
    # ------------------------------------------------------------------

    async def quarantine_items(self, parent_id: int, *, current_thread_id: Optional[int] = None) -> list[QuarantineItem]:
        """這個主頻道的隔離區裡、還沒放回的發送單位，依發文時間排（相簿算一項）。

        `current_thread_id`：面板所在的 thread。runtime 檔遺失時先讓它補記回去（`parent_of` 會問 Discord），
        不然面板會顯示「目前沒有被隔離的訊息」。
        """
        if self._quarantine is None:
            return []
        if current_thread_id is not None:
            await self._quarantine.parent_of(current_thread_id)
        rows = await self.repository.list_quarantined(await self._quarantine.thread_ids_of(parent_id), parent_id)
        units: dict[tuple, list[dict]] = {}
        for row in rows:
            key = (row["chat_id"], row["grouped_id"]) if row["grouped_id"] is not None else ("pk", row["pk"])
            units.setdefault(key, []).append(row)
        items = []
        for members in units.values():
            members.sort(key=lambda r: r["telegram_message_id"])
            media = [m for r in members for m in r["media"]]
            items.append(QuarantineItem(
                pk=members[0]["pk"],
                posted=members[0]["message_date"],
                text="\n".join(r["text"].strip() for r in members if r["text"].strip()),
                image_count=sum(1 for m in media if m in ("photo", "image")),
                video_count=sum(1 for m in media if m == "video"),
            ))
        items.sort(key=lambda i: (i.posted is None, i.posted or datetime.min.replace(tzinfo=timezone.utc), i.pk))
        return items

    async def restore(self, message_pk: int, restored_by: str) -> tuple[bool, str]:
        """把隔離區裡的一則（相簿整本）照正常流程送回主頻道、記主頻道的發送紀錄，隔離那則改成「已由 X 放回」。

        不判斷（使用者看過才放回的）。回傳 (有沒有放回, 給操作者看的說明)。
        相簿放回途中算「處理中」：這段時間晚到的組員先登記，放回後再處理（那時已有主頻道紀錄，會以補圖送主頻道），
        不然它會被當成隔離相簿的補圖送進隔離區，之後這本永遠留在選單裡放不回去。
        """
        async with self._quarantine_lock:
            record = await self.repository.get_message_by_pk(message_pk)
            if record is None:
                return False, "找不到這則訊息。"
            album_key = None
            if record.grouped_id is not None:
                album_key = (record.telegram_chat_id, int(record.grouped_id))
                if album_key in self._active_groups:
                    return False, "這本相簿正在處理中，請稍後再試。"
                self._active_groups.add(album_key)
            try:
                return await self._restore_unit(record, restored_by)
            finally:
                if album_key is not None:
                    self._active_groups.discard(album_key)
                    if album_key in self._dirty_groups:
                        self._dirty_groups.discard(album_key)
                        spawn(self._after_restore_followup(record), name="Telegram 相簿補發")

    async def _after_restore_followup(self, record: TelegramMessageRecord) -> None:
        try:
            await self._process_group_member(record, time.perf_counter())
        except Exception as exc:
            logger.error("Telegram 隔離區：放回後處理晚到的組員失敗 grouped_id=%s：%s", record.grouped_id, exc,
                         exc_info=True)

    async def _restore_unit(self, record: TelegramMessageRecord, restored_by: str) -> tuple[bool, str]:
        message_pk = record.message_pk
        pks = await self.unit_pks(record)
        route_ids = self._routes(record.telegram_chat_id)
        deliveries = await self._route_deliveries(pks, route_ids)
        restored = False
        for route_id in route_ids:
            delivered = deliveries.get(route_id)
            if delivered is None or delivered.main or not delivered.quarantine:
                continue
            q_pks = [pk for pk in pks if pk in delivered.quarantine]
            unit = await self._merge_group_messages(q_pks) if record.grouped_id is not None else record
            dest = await self._destination(route_id, False)
            if unit is None or dest is None:
                return False, "主頻道現在送不出去，請稍後再試。"
            channel, channel_id = dest
            note = ""
            try:
                await self._send_unit(unit, q_pks, channel, channel_id)
            except SentButNotRecorded as exc:
                # 主頻道已經有了：不能回報失敗（再按一次會貼兩則），照樣標成已放回
                logger.error("Telegram 隔離區放回：%s", exc)
                note = "（發送紀錄沒寫上，請不要再按一次）"
            except Exception as exc:
                logger.error("Telegram 隔離區放回失敗: message_pk=%s err=%s", message_pk, exc, exc_info=True)
                return False, "送回主頻道失敗，請稍後再試。"
            logger.info("Telegram 隔離區：%s 把 message_pk=%s 放回主頻道 %s", restored_by, q_pks, channel_id)
            restored = True
            # 主頻道已經送出：之後的標示、通知面板失敗只記 log，不能讓操作者以為沒放回
            try:
                await self._mark_restored(q_pks, restored_by)
                thread = await self._quarantine.current_thread(route_id)
                if thread is not None:
                    self._quarantine.changed(route_id, thread)
            except Exception as exc:
                logger.warning("Telegram 隔離區：已放回，但標示隔離那則或更新面板失敗 message_pk=%s：%s",
                               message_pk, exc)
        if not restored:
            return False, "這則已經放回過了，或不在隔離區。"
        return True, f"已放回主頻道。{note}"

    async def find_quarantine_messages(self, pks: list[int]) -> list[discord.Message]:
        """隔離 thread 裡、footer 的 db# 是這批 pk 的 bot 訊息（相簿第一次送出與補圖各一則）。"""
        if self._quarantine is None:
            return []
        wanted = {int(pk) for pk in pks}
        rows = await self.repository.get_deliveries(list(wanted))
        thread_ids = {ch for channels in rows.values() for ch in channels
                      if await self._quarantine.parent_of(ch) is not None}
        me = getattr(getattr(self.bot, "user", None), "id", None)
        found = []
        for thread_id in thread_ids:
            thread = await fetch_thread(self.bot, thread_id)
            if thread is None:
                continue
            async for message in thread.history(limit=self._QUARANTINE_SCAN_LIMIT):
                if getattr(message.author, "id", None) != me:
                    continue
                if _footer_pks(message) & wanted:
                    found.append(message)
        return found

    async def _mark_restored(self, pks: list[int], restored_by: str) -> None:
        """隔離那則（含補圖）最上面加一行「已由 X 放回主頻道」；改不了只記 log（主頻道已經送出）。"""
        note = f"✅ 已由 {restored_by} 放回主頻道"
        for message in await self.find_quarantine_messages(pks):
            try:
                await reopen_thread(message.channel)
                content = (message.content or "").strip()
                await message.edit(content=f"{content}\n{note}" if content else note)
            except Exception as exc:
                logger.warning("隔離那則改成已放回失敗 message_id=%s：%s", getattr(message, "id", None), exc)

    # 放回時往回翻隔離 thread 找原貼文的則數上限（一天約一則，翻得到幾個月）
    _QUARANTINE_SCAN_LIMIT = 500

    # ------------------------------------------------------------------
    # 隔離區：把已經貼在主頻道的移進來（判成垃圾的搬到 thread、原本頻道的貼文刪除）
    # ------------------------------------------------------------------

    async def unit_pks(self, record: TelegramMessageRecord) -> list[int]:
        """一個發送單位的 pk：單則是自己，相簿是同一本全部（依 Telegram 順序）。"""
        if record.grouped_id is None:
            return [record.message_pk]
        members = await self.repository.get_group_member_states(int(record.grouped_id), record.telegram_chat_id)
        return [pk for pk, _ in members] or [record.message_pk]

    async def judge_existing(self, message_pk: int) -> Optional[Verdict]:
        """直接判一則已經在資料庫的（相簿整本），不看開關、不送；沒接過濾或找不到回 None。一次性搬移用。

        圖還沒到齊的不判、回放行，跟轉發端 `complete=False` 一樣：只看到一部分就判，會把「文字只有水、
        圖是設計稿」那種情報錯關（13649）。
        """
        record = await self.repository.get_message_by_pk(message_pk)
        if self._filter is None or record is None:
            return None
        if record.grouped_id is not None:
            members = await self.repository.get_group_member_states(int(record.grouped_id), record.telegram_chat_id)
            complete = all(ready for _, ready in members)
            unit = await self._merge_group_messages([pk for pk, _ in members] or [message_pk])
        else:
            complete = not (record.has_media and not record.media_items)
            unit = record
        if unit is None:
            return None
        if not complete:
            return Verdict(False, reason="圖還沒到齊，不判", by_model=False)
        return await self._filter.judge(unit.text, self._filter_media(unit), trace_id=f"tgfilter-{message_pk}")

    async def relay_posts(self, channel, *, after: Optional[datetime] = None) -> dict[int, list[discord.Message]]:
        """頻道裡 bot 轉發的貼文，依 Telegram 那則的 pk 分組。一個發送單位可能是好幾則 Discord 訊息
        （長文分段、相簿分批、影片另一則、補圖），要整組刪才不會留半則。整批搬移時掃一次給每則用。"""
        me = getattr(getattr(self.bot, "user", None), "id", None)
        out: dict[int, list[discord.Message]] = {}
        async for message in channel.history(limit=None, after=after):
            if getattr(message.author, "id", None) != me:
                continue
            for pk in relay_post_pks(message):
                out.setdefault(pk, []).append(message)
        return out

    async def move_to_quarantine(self, message_pk: int, verdict: Verdict, posts: dict[int, list[discord.Message]],
                                 *, apply: bool = True) -> tuple[bool, str]:
        """把已經在主頻道的一則（相簿整本，含補圖）移進隔離區，之後跟新判的一樣能從面板放回。

        順序：照正常流程貼進隔離 thread（帶判定那行）→ 刪主頻道原貼文 → 發送紀錄的頻道從主頻道改成 thread。
        原貼文一則都沒刪掉就不改紀錄、收回 thread 那份：不然面板會列出它，放回後主頻道變兩份。
        `posts`：`relay_posts` 掃主頻道的結果。`apply=False`：只做同樣的檢查、回報會刪幾則（腳本的預覽）。
        回傳 (有沒有搬（預覽：會不會搬）, 說明)。
        """
        async with self._quarantine_lock:
            record = await self.repository.get_message_by_pk(message_pk)
            if record is None:
                return False, f"找不到這則訊息（db#{message_pk}）。"
            pks = await self.unit_pks(record)
            route_ids = self._routes(record.telegram_chat_id)
            deliveries = await self._route_deliveries(pks, route_ids)
            # 每個主頻道都檢查過才動手，不會搬了一邊才發現另一邊不能搬
            plans = []
            for route_id in route_ids:
                delivered = deliveries.get(route_id)
                if delivered is None or not delivered.main or delivered.quarantine:
                    continue   # 沒送到這個主頻道，或已經在隔離區（含放回過的）
                main_pks = [pk for pk in pks if pk in delivered.main]
                originals, problem = self._move_originals(record, main_pks, route_id, delivered, posts)
                if problem:
                    return False, f"{problem}，沒搬（db#{message_pk}）。"
                plans.append((route_id, main_pks, originals))
            if not plans:
                return False, f"不在主頻道（沒送過或已經在隔離區），沒搬（db#{message_pk}）。"
            if not apply:
                return True, "；".join(f"會刪主頻道 {len(originals)} 則" for _, _, originals in plans)
            notes = []
            for route_id, main_pks, originals in plans:
                ok, note = await self._move_unit(record, main_pks, route_id, verdict, originals)
                if not ok:
                    return False, note
                notes.append(note)
            return True, "；".join(notes)

    def _move_originals(self, record: TelegramMessageRecord, main_pks: list[int], route_id: int,
                        delivered: _RouteDeliveries, posts: dict[int, list[discord.Message]]) -> tuple[list, str]:
        """這個主頻道要刪的原貼文（照貼出的相反順序）；不能搬時回 ([], 原因)。"""
        if record.grouped_id is not None:
            first_sent = min(delivered.main.values())
            if datetime.now(timezone.utc) - first_sent < self._GROUP_FOLLOWUP_MAX_AGE:
                # 補圖時效內，線上 bot（另一個行程，這裡的鎖管不到）還可能把晚到的圖補進主頻道：搬到一半補進來的
                # 會留在主頻道，這本在面板上也放不回去
                hours = int(self._GROUP_FOLLOWUP_MAX_AGE.total_seconds() // 3600)
                return [], f"相簿第一次送出還不到 {hours} 小時，晚到的圖還可能補進主頻道"
        # 相反順序刪（Discord 的訊息 id 依時間遞增）：本文那則（帶 db#）最後刪，中途失敗時它還在，重跑認得出來、補得完
        originals = sorted({m.id: m for pk in main_pks for m in posts.get(pk, [])
                            if getattr(m.channel, "id", None) == route_id}.values(), key=lambda m: m.id, reverse=True)
        if not originals:
            return [], "主頻道找不到原貼文"
        if not any(_footer_pks(m) & set(main_pks) for m in originals):
            # 2026-07-25 以前 footer 只有「msg #…」沒有 db#：本文那則（垃圾內容本身）認不出來，只刪得到後面的圖、影片
            return [], "認不出主頻道的本文那則（07-25 以前的舊格式沒有 db#）"
        return originals, ""

    async def _move_unit(self, record: TelegramMessageRecord, main_pks: list[int], route_id: int, verdict: Verdict,
                         originals: list[discord.Message]) -> tuple[bool, str]:
        unit = await self._merge_group_messages(main_pks) if record.grouped_id is not None else record
        dest = await self._destination(route_id, True)
        if unit is None or dest is None:
            return False, f"隔離 thread 取不到，沒搬（db#{record.message_pk}）。"
        thread, thread_id = dest
        copies: list[discord.Message] = []
        deleted = 0
        try:
            await self._send_unit(unit, main_pks, thread, thread_id, header=self._verdict_header(verdict),
                                  record=False, sent=copies)
            async with self.repository.moving_deliveries(main_pks, route_id, thread_id) as rows:
                for message in originals:
                    try:
                        await message.delete()
                    except discord.NotFound:
                        pass   # 已經不在了
                    deleted += 1
        except Exception as exc:
            if deleted < len(originals):
                return await self._abandon_move(record, main_pks, originals, copies, deleted, exc)
            rows = await self._record_after_deleted(main_pks, route_id, thread_id, exc)
            if rows is None:
                return False, f"原貼文已全刪、發送紀錄改不上（db#{record.message_pk}，log 有要手動執行的 SQL）。"
        logger.info("Telegram 隔離區：已搬移 db#%s 主頻道 %s → thread %s；刪原貼文 %s 則；發送紀錄（列 id, pk）=%s",
                    record.message_pk, route_id, thread_id, len(originals), rows)
        self._quarantine.changed(route_id, thread)
        return True, f"已搬進隔離區、刪主頻道 {len(originals)} 則（db#{record.message_pk}）。"

    async def _abandon_move(self, record: TelegramMessageRecord, main_pks: list[int], originals: list,
                            copies: list, deleted: int, exc: Exception) -> tuple[bool, str]:
        """原貼文沒刪完就失敗：紀錄沒改（交易回滾）。一則都沒刪就收回 thread 那份，跟沒搬一樣。"""
        if deleted:
            # 刪了一部分：thread 那份不能收回（主頻道只剩本文那則）；重跑這則會刪掉剩下的並改紀錄（thread 會多一份）
            logger.error("Telegram 隔離區搬移：主頻道原貼文刪了 %s/%s 則，發送紀錄沒改 pks=%s：%s",
                         deleted, len(originals), main_pks, exc, exc_info=True)
            return False, f"原貼文刪了 {deleted}/{len(originals)} 則、發送紀錄沒改，重跑這則會補完（db#{record.message_pk}）。"
        logger.error("Telegram 隔離區搬移失敗，沒搬 db#%s：%s", record.message_pk, exc, exc_info=True)
        for copy in copies:
            try:
                await copy.delete()
            except Exception as cleanup_exc:
                logger.warning("收回 thread 那份失敗 message_id=%s：%s", getattr(copy, "id", None), cleanup_exc)
        return False, f"搬移失敗，沒搬（db#{record.message_pk}）：{exc}"

    async def _record_after_deleted(self, main_pks: list[int], route_id: int, thread_id: int,
                                    exc: Exception) -> Optional[list[tuple[int, int]]]:
        """原貼文全刪了才失敗（多半是寫入資料庫時）：這時改紀錄已經安全（主頻道不會變兩份），交易外再試一次。
        不改的話重跑會因為主頻道找不到原貼文而不搬，這則就卡在面板外面。還是失敗就在 log 留要手動執行的 SQL。"""
        try:
            async with self.repository.moving_deliveries(main_pks, route_id, thread_id) as rows:
                pass
        except Exception as retry_exc:
            logger.error(
                "Telegram 隔離區搬移：主頻道原貼文已全刪，發送紀錄改不上（%s；第一次：%s）。要手動執行："
                "UPDATE telegram_relay_delivery_state SET discord_channel_id = %s "
                "WHERE message_pk = ANY('{%s}'::bigint[]) AND discord_channel_id = %s;",
                retry_exc, exc, thread_id, ",".join(str(pk) for pk in main_pks), route_id, exc_info=True,
            )
            return None
        logger.warning("Telegram 隔離區搬移：改紀錄第一次失敗（%s），原貼文已全刪，重試成功", exc)
        return rows

    # ------------------------------------------------------------------
    # 待補判：模型沒判到就送進主頻道的，之後補判（每則訊息都要被檢查過）
    # ------------------------------------------------------------------

    _RECHECK_INTERVAL = timedelta(minutes=10)
    _RECHECK_BATCH = 20

    async def _recheck_loop(self) -> None:
        """模型恢復回應時（`_judge_unit` 叫醒）或每 `_RECHECK_INTERVAL` 補判一次；出錯不中斷。"""
        while self._running:
            try:
                await asyncio.wait_for(self._recheck_wake.wait(), self._RECHECK_INTERVAL.total_seconds())
            except asyncio.TimeoutError:
                pass
            self._recheck_wake.clear()
            try:
                await self.run_recheck()
            except Exception as exc:
                logger.error("Telegram 過濾補判失敗：%s", exc, exc_info=True)

    async def run_recheck(self) -> int:
        """要補判的（`needs_recheck`）判一次：垃圾搬進隔離區、情報（或再判也一樣的）清掉標記；還是判不到的留到下次。
        只在正式模式（on）做：只記錄模式本來就不搬，關掉時不判。回傳判完幾個發送單位。"""
        if not self._filter_active() or self._filter.mode != "on" or self._quarantine is None:
            return 0
        rows = await self.repository.list_needs_recheck(self._RECHECK_BATCH)
        self._recheck_known = bool(rows)
        done: set[int] = set()
        handled = 0
        for pk, channel_id, delivered_at in rows:
            if pk in done:
                continue
            record = await self.repository.get_message_by_pk(pk)
            if record is None:
                await self.repository.clear_needs_recheck([pk], channel_id)
                continue
            unit = await self.unit_pks(record)
            done.update(unit)
            if (record.grouped_id is not None
                    and datetime.now(timezone.utc) - delivered_at < self._GROUP_FOLLOWUP_MAX_AGE):
                continue   # 補圖時效內的相簿搬不動（`_move_originals`），過了再補判
            verdict = await self.judge_existing(unit[0])
            if verdict is None or (not verdict.by_model and verdict.recheck):
                logger.info("Telegram 過濾補判：還是判不到，下次再補 db#%s（%s）", unit[0],
                            getattr(verdict, "reason", "-"))
                break   # 模型還沒好，後面的也判不到
            handled += 1
            if not verdict.quarantine:
                await self.repository.clear_needs_recheck(unit, channel_id)
                logger.info("Telegram 過濾補判：放行 db#%s（%s）", unit[0], verdict.reason or "-")
                continue
            channel = await self._resolve_channel(channel_id)
            posts = await self.relay_posts(channel, after=delivered_at - timedelta(minutes=5)) if channel else {}
            ok, note = await self.move_to_quarantine(unit[0], verdict, posts)
            if ok:
                logger.info("Telegram 過濾補判：判成垃圾，%s", note)
            else:
                # 判成垃圾卻搬不動（原貼文被刪了、找不到）：不再補判，留 log 給人處理
                await self.repository.clear_needs_recheck(unit, channel_id)
                logger.error("Telegram 過濾補判：判成垃圾但搬不動，請手動處理 db#%s：%s", unit[0], note)
        return handled

    async def _process_group_member(self, message: TelegramMessageRecord, started: float) -> None:
        """media group 組員入口：同組同時只有一個收集者，其餘組員登記後返回。"""
        key = (message.telegram_chat_id, int(message.grouped_id))
        if key in self._active_groups:
            self._dirty_groups.add(key)
            logger.info(
                "Telegram relay media group 成員，交由進行中的收集處理: message_pk=%s grouped_id=%s",
                message.message_pk, message.grouped_id,
            )
            return

        self._active_groups.add(key)
        try:
            while True:
                self._dirty_groups.discard(key)
                await self._publish_group_pending(message, started)
                # 收集期間有組員登記 → 回頭複查一次（晚到的會以補圖送出）。
                # 這個檢查到移出 _active_groups 之間沒有 await，組員不會卡在空檔沒人處理。
                if key not in self._dirty_groups:
                    break
        finally:
            self._active_groups.discard(key)
            self._dirty_groups.discard(key)

    async def _publish_group_pending(self, trigger: TelegramMessageRecord, started: float) -> None:
        """把 media group 裡「還沒送到各路由頻道」的組員合併送出。

        不論哪個組員先觸發都一樣：等整組到齊 → 各頻道挑出還沒送的 → 合併成一則送出。
        組內已有組員送過（組員晚到、上次等待逾時）時，改以「（補圖）」送出剩下的。
        """
        chat_id = trigger.telegram_chat_id
        grouped_id = int(trigger.grouped_id)

        route_ids = self._routes(chat_id)
        if not route_ids:
            logger.info(
                "Telegram relay 無路由，略過: message_pk=%s chat_id=%s telegram_message_id=%s",
                trigger.message_pk, chat_id, trigger.telegram_message_id,
            )
            self._mark_processed(trigger.message_pk)
            return

        members = await self.repository.get_group_member_states(grouped_id, chat_id)
        group_pks = [pk for pk, _ in members] or [trigger.message_pk]
        force_replay = await self._is_force_replay(chat_id, min(group_pks))

        # 先確認有沒有該發的：收尾複查、重啟時 reconcile 排入的舊組員多半沒有，
        # 這時不必等整組到齊的安靜期
        deliveries = {} if force_replay else await self._route_deliveries(group_pks, route_ids)
        # 待送的組員一張圖都還沒到就不等：爬蟲補到圖會再通知；在這裡等只會白等 60 秒，
        # 開了過濾（一次只處理一則）時還會讓後面的情報一起卡住
        ready_now = {pk for pk, ready in members if ready}
        pending_now: set[int] = set()
        for channel_id in route_ids:
            pending_now.update(
                self._group_pending(grouped_id, group_pks, channel_id, deliveries.get(channel_id), force_replay)[0]
            )
        if not pending_now & ready_now:
            # 還在等圖的組員**不能**記成處理過：爬蟲補到圖的通知會被當成重複丟掉，那張就永遠送不出去
            for pk in group_pks:
                if pk not in pending_now:
                    self._mark_processed(pk)
            await self._advance_cursor(max(group_pks))
            return

        members = await self._wait_group_settled(grouped_id, chat_id)
        group_pks = [pk for pk, _ in members] or group_pks
        ready_pks = [pk for pk, ready in members if ready]
        # 等待期間可能有別的路徑送出了一部分（例如放回），送之前重查
        deliveries = {} if force_replay else await self._route_deliveries(group_pks, route_ids)
        complete = len(ready_pks) == len(group_pks)

        published_count = 0
        sent_pks: set[int] = set()
        # 送不出去的組員也記成處理過（只在記憶體）：不然同一本的其他組員通知進來時會各自重判、重送一次，
        # 半則訊息最多貼 N 份（開過濾一次只處理一則時一定會發生）。重試交給重啟時的補償，跟單則一致
        failed_pks: set[int] = set()
        followup = False
        judged: dict[str, Optional[Verdict]] = {}
        for channel_id in route_ids:
            pending, follow = self._group_pending(
                grouped_id, ready_pks, channel_id, deliveries.get(channel_id), force_replay,
            )
            if not pending:
                continue

            merged = await self._merge_group_messages(pending)
            if merged is None:
                continue
            if not merged.text.strip() and not merged.media_items:
                logger.info("Telegram relay media group 無可發內容，略過: grouped_id=%s pks=%s", grouped_id, pending)
                continue

            if follow is None:
                # 第一次送：整本判一次（多個路由共用同一個判定）
                if "verdict" not in judged:
                    judged["verdict"], judged["recheck"] = await self._judge_unit(merged, complete=complete)
                verdict, recheck = judged["verdict"], judged["recheck"]
                to_quarantine = verdict is not None
            else:
                # 補圖：跟著同本的去向，不再判（待補判時整本一起判、一起搬，補圖不另記）
                verdict, recheck = None, False
                to_quarantine = follow == "quarantine"
            dest = await self._destination(channel_id, to_quarantine)
            if dest is None:
                failed_pks.update(pending)
                continue
            target, target_id = dest
            try:
                # 只標記這次實際合併送出的組員；還沒就緒的留著，到了再以補圖送出
                published_count += await self._send_unit(
                    merged, pending, target, target_id,
                    title_suffix=self._GROUP_FOLLOWUP_TITLE_SUFFIX if follow is not None else "",
                    header=self._verdict_header(verdict),
                    needs_recheck=recheck and target_id == channel_id,
                )
                sent_pks.update(pending)
                followup = followup or follow is not None
                if target_id != channel_id:
                    self._quarantine.changed(channel_id, target)
            except Exception as exc:
                failed_pks.update(pending)
                logger.error(
                    "Telegram relay 發送失敗: message_pk=%s channel_id=%s err=%s",
                    merged.message_pk,
                    channel_id,
                    exc,
                    exc_info=True,
                )

        for pk in sent_pks | failed_pks:
            self._mark_processed(pk)
        await self._advance_cursor(max(group_pks))

        latency_ms = int((time.perf_counter() - started) * 1000)
        result = "published" if published_count > 0 else "failed_or_skipped"
        logger.info(
            "telegram_relay_result message_pk=%s telegram_chat_id=%s telegram_message_id=%s route_count=%s published_count=%s latency_ms=%s result=%s grouped_id=%s group_size=%s followup=%s",
            trigger.message_pk,
            chat_id,
            trigger.telegram_message_id,
            len(route_ids),
            published_count,
            latency_ms,
            result,
            grouped_id,
            len(sent_pks),
            followup,
        )

    async def _process_one(self, message_pk: int) -> None:
        if self._seen_processed(message_pk):
            return

        started = time.perf_counter()
        message = await self.repository.get_message_by_pk(message_pk)
        if message is None:
            logger.warning("Telegram relay 查無訊息: message_pk=%s", message_pk)
            return

        # 排在相簿之前：相簿組員的發文時間相同，逐則擋掉就不會有整組等圖、補圖的動作
        if await self._skip_if_stale(message):
            return

        # media group 整組處理；要排在「空訊息」判斷之前——組員的圖可能還在下載，
        # 此刻沒有媒體不代表是空訊息
        if message.grouped_id is not None:
            await self._process_group_member(message, started)
            return

        # 有圖標示、但圖還沒下載到（爬蟲先寫訊息列、下載完才寫媒體列，每小時輪詢與重啟補償會撿到中間狀態）：
        # 先不處理、也不記成處理過，等爬蟲補到圖的通知，文字和圖一起送。有文字的最多等 30 分鐘就先送文字、
        # 沒文字的等到補圖時限；時間基準跟爬蟲一樣用 Telegram 發文時間。
        media_pending = message.has_media and not message.media_items
        if media_pending:
            age = self._message_age(message)
            wait_limit = MEDIA_HOLD_NOTIFY if message.text.strip() else MEDIA_RETRY_WINDOW
            if age is not None and age < wait_limit:
                logger.info(
                    "Telegram relay 圖還沒下載到，先不送: message_pk=%s 發文 %s 前",
                    message_pk, str(age).split(".")[0],
                )
                return

        # 跳過無內容訊息（無文字且無媒體，通常是 Telegram 服務通知）
        if not message.text.strip() and not message.media_items:
            logger.info(
                "Telegram relay 略過空訊息: message_pk=%s telegram_message_id=%s",
                message.message_pk,
                message.telegram_message_id,
            )
            self._mark_processed(message_pk)
            return

        route_ids = self._routes(message.telegram_chat_id)
        if not route_ids:
            logger.info(
                "Telegram relay 無路由，略過: message_pk=%s chat_id=%s telegram_message_id=%s",
                message.message_pk,
                message.telegram_chat_id,
                message.telegram_message_id,
            )
            self._mark_processed(message_pk)
            return

        published_count = 0
        force_replay = await self._is_force_replay(message.telegram_chat_id, message_pk)
        # 送過主頻道或隔離 thread 的路由都不再送（隔離過的只查主頻道會被當成沒送過、重判重貼）
        deliveries = {} if force_replay else await self._route_deliveries([message_pk], route_ids)
        pending_routes = []
        for channel_id in route_ids:
            delivered = deliveries.get(channel_id)
            if delivered is not None and delivered.sent:
                logger.info("Telegram relay 略過已發送訊息: message_pk=%s channel_id=%s", message_pk, channel_id)
            else:
                pending_routes.append(channel_id)

        verdict, recheck = (await self._judge_unit(message, complete=not media_pending)
                            if pending_routes else (None, False))
        for channel_id in pending_routes:
            dest = await self._destination(channel_id, verdict is not None)
            if dest is None:
                continue
            target, target_id = dest
            try:
                published_count += await self._send_unit(
                    message, [message_pk], target, target_id, header=self._verdict_header(verdict),
                    needs_recheck=recheck and target_id == channel_id,
                )
                if target_id != channel_id:
                    self._quarantine.changed(channel_id, target)
            except Exception as exc:
                logger.error(
                    "Telegram relay 發送失敗: message_pk=%s channel_id=%s err=%s",
                    message_pk,
                    channel_id,
                    exc,
                    exc_info=True,
                )

        self._mark_processed(message_pk)
        await self._advance_cursor(message_pk)
        latency_ms = int((time.perf_counter() - started) * 1000)
        result = "published" if published_count > 0 else "failed_or_skipped"
        logger.info(
            "telegram_relay_result message_pk=%s telegram_chat_id=%s telegram_message_id=%s route_count=%s published_count=%s latency_ms=%s result=%s grouped_id=%s group_size=%s",
            message.message_pk,
            message.telegram_chat_id,
            message.telegram_message_id,
            len(route_ids),
            published_count,
            latency_ms,
            result,
            message.grouped_id,
            1,
        )

    # 同時處理訊息的並行上限（避免大檔壓縮卡住整條 pipeline）
    _PROCESS_CONCURRENCY = 3

    def _routes(self, chat_id: int) -> list[int]:
        """這個來源要送到哪些頻道；同一個頻道寫兩次只送一次（以前逐頻道查「送過沒」會擋掉第二次，
        現在一次查完所有紀錄，要自己去重）。"""
        return list(dict.fromkeys(self.route_resolver.resolve_telegram_routes(chat_id)))

    def _filter_active(self) -> bool:
        return self._filter is not None and self._filter.mode != "off"

    async def _process_loop(self) -> None:
        sem = asyncio.Semaphore(self._PROCESS_CONCURRENCY)
        bg_tasks: set[asyncio.Task] = set()

        async def _run(pk: int) -> None:
            async with sem:
                self._processing.add(pk)
                try:
                    if self._filter_active():
                        # 開了過濾就一次只處理一則：模型一次只能判一則，並行快不了多少，
                        # 反而讓判得快的插隊、打亂 Discord 上的順序
                        async with self._filtered_lock:
                            await self._process_one(pk)
                    else:
                        await self._process_one(pk)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.error("Telegram relay process loop 發生錯誤: %s", exc, exc_info=True)
                finally:
                    self._processing.discard(pk)
                    self._queued_set.discard(pk)
                    try:
                        self._queue.task_done()
                    except ValueError:
                        pass
                    if pk in self._requeue:
                        self._requeue.discard(pk)
                        await self._enqueue_message_pk(pk)

        while self._running:
            try:
                message_pk = await self._queue.get()
                task = asyncio.create_task(_run(message_pk), name=f"tg_relay_{message_pk}")
                bg_tasks.add(task)
                task.add_done_callback(bg_tasks.discard)
            except asyncio.CancelledError:
                raise


def build_telegram_pg_dsn_from_env() -> str:
    """由環境變數組出 Telegram 使用的 PostgreSQL DSN。"""
    host = os.getenv("PGVECTOR_HOST", "pgvector").strip() or "pgvector"
    port = int(os.getenv("PGVECTOR_PORT", "5432"))
    db = os.getenv("TELEGRAM_PGVECTOR_DB", "").strip() or os.getenv("PGVECTOR_DB", "discord_data").strip() or "discord_data"
    user = os.getenv("PGVECTOR_USER", "")
    password = os.getenv("PGVECTOR_PASSWORD", "")
    if not user or not password:
        raise RuntimeError("缺少 PGVECTOR_USER / PGVECTOR_PASSWORD，無法啟動 Telegram relay")

    encoded_user = quote_plus(user)
    encoded_password = quote_plus(password)
    return f"postgresql://{encoded_user}:{encoded_password}@{host}:{port}/{db}"
