"""Telegram -> Discord relay（先行實作版）。

設計原則：
1. 內容/格式在 Adapter。
2. Publisher 只做發送能力。
3. Telegram 來源走 LISTEN/NOTIFY + DB 補償輪詢。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import shutil
import tempfile
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus

import asyncpg
import discord
from telegram_scraper.tg_config import normalize_channel_identifier

logger = logging.getLogger("discord_bot")


def apply_spoiler_entities(text: str, entities: list[dict] | None) -> str:
    """把 Telegram MessageEntitySpoiler 範圍轉成 Discord 的 `||...||` 暴雷標記。

    Telegram 的 entity offset/length 以 UTF-16 code units 計，須先將文字轉為 UTF-16-LE
    bytes 再切片，否則 BMP 外字元（部分 emoji / 罕字）會偏移。
    其他 entity 類型（bold/italic 等）目前不處理。
    """
    if not text or not entities:
        return text

    spoilers = [
        ent for ent in entities
        if isinstance(ent, dict) and ent.get("type") == "MessageEntitySpoiler"
    ]
    if not spoilers:
        return text

    text_bytes = text.encode("utf-16-le")
    open_marker = "||".encode("utf-16-le")
    close_marker = "||".encode("utf-16-le")

    # 從後往前處理，避免插入記號後位移失效
    for ent in sorted(spoilers, key=lambda e: int(e.get("offset", 0)), reverse=True):
        offset_units = int(ent.get("offset", 0))
        length_units = int(ent.get("length", 0))
        if length_units <= 0:
            continue
        start = offset_units * 2
        end = start + length_units * 2
        if start < 0 or end > len(text_bytes):
            continue
        text_bytes = (
            text_bytes[:start]
            + open_marker
            + text_bytes[start:end]
            + close_marker
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
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS telegram_relay_runtime_state (
                    state_key TEXT PRIMARY KEY,
                    state_value TEXT NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )

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

    async def get_pk_by_telegram_message_id(self, telegram_message_id: int) -> Optional[int]:
        """根據 telegram_message_id 查詢對應的 message_pk。

        若該訊息屬於 media group，自動回傳 group 首則（最小 pk），
        確保重發時能觸發完整的 group 合併流程。
        """
        if self.pool is None:
            raise RuntimeError("TelegramMessageRepository 尚未 connect")
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, grouped_id, telegram_chat_id
                FROM telegram_messages
                WHERE telegram_message_id = $1
                ORDER BY id ASC LIMIT 1;
                """,
                int(telegram_message_id),
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

    async def is_message_published(self, message_pk: int, discord_channel_id: int) -> bool:
        if self.pool is None:
            raise RuntimeError("TelegramMessageRepository 尚未 connect")
        async with self.pool.acquire() as conn:
            exists = await conn.fetchval(
                """
                SELECT 1
                FROM telegram_relay_delivery_state
                WHERE message_pk = $1 AND discord_channel_id = $2;
                """,
                int(message_pk),
                int(discord_channel_id),
            )
        return bool(exists)

    async def mark_message_published(self, message_pk: int, discord_channel_id: int) -> None:
        if self.pool is None:
            raise RuntimeError("TelegramMessageRepository 尚未 connect")
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO telegram_relay_delivery_state (message_pk, discord_channel_id, delivered_at)
                VALUES ($1, $2, NOW())
                ON CONFLICT (message_pk, discord_channel_id)
                DO UPDATE SET delivered_at = NOW();
                """,
                int(message_pk),
                int(discord_channel_id),
            )

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


    async def get_grouped_message_pks(self, grouped_id: int, chat_id: int) -> list[int]:
        """取得同一 media group 的所有 message pk（按 telegram_message_id 排序）。"""
        if self.pool is None:
            raise RuntimeError("TelegramMessageRepository 尚未 connect")
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id
                FROM telegram_messages
                WHERE grouped_id = $1 AND telegram_chat_id = $2
                ORDER BY telegram_message_id ASC;
                """,
                int(grouped_id),
                int(chat_id),
            )
        return [int(row["id"]) for row in rows]


class MessageRouteResolver:
    """讀取 config.json，解析 telegram_chat_id 對應 Discord channel ids。"""

    def __init__(
        self,
        config_path: str = "config.json",
        telegram_runtime_config_path: str = "telegram_scraper/runtime_config.json",
    ) -> None:
        self.config_path = Path(config_path)
        self.telegram_runtime_config_path = Path(telegram_runtime_config_path)

    @staticmethod
    def _normalize_source_key(raw: object) -> str:
        return normalize_channel_identifier(str(raw or "")).lower()

    def _load_telegram_runtime_config(self) -> dict:
        if not self.telegram_runtime_config_path.exists():
            return {}
        try:
            return json.loads(self.telegram_runtime_config_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.error("讀取 telegram runtime_config 失敗: %s", exc, exc_info=True)
            return {}

    def _load_config(self) -> dict:
        if not self.config_path.exists():
            return {}
        try:
            return json.loads(self.config_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.error("讀取 config.json 失敗: %s", exc, exc_info=True)
            return {}

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

    def get_replay_from_message_id(self) -> Optional[int]:
        """從 config 讀取重發起始 telegram_message_id。"""
        config = self._load_config()
        raw = config.get("telegram_replay_from_message_id")
        if raw is None:
            return None
        try:
            parsed = int(raw)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

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

    def __init__(self, app_root: str = "/app") -> None:
        self.app_root = Path(app_root)
        self._runtime_config_path = self.app_root / "telegram_scraper" / "runtime_config.json"

    def _get_source_channel_name(self) -> str:
        """從 telegram runtime_config.json 讀取頻道名稱。"""
        try:
            data = json.loads(self._runtime_config_path.read_text(encoding="utf-8"))
            name = str(data.get("source_channel", "")).strip()
            return name if name else "Telegram"
        except Exception:
            return "Telegram"

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

    def render(self, message: TelegramMessageRecord) -> RenderPlan:
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

        # 先以 entities 還原 spoiler 等格式，再做長度截斷，避免切到 markdown 中間
        rendered_text = apply_spoiler_entities(message.text or "", message.entities)
        content = rendered_text.strip()
        description = content[:4000] + ("..." if len(content) > 4000 else "")

        source_name = message.chat_title or self._get_source_channel_name()
        embed = discord.Embed(
            title=source_name,
            description=description or None,
            color=0x2CA5E0,  # Telegram 藍
            timestamp=message.message_date,
        )
        embed.set_footer(text=f"msg #{message.telegram_message_id}")

        op = RenderOperation(op_type="send_message", content="", attachments=attachments, embed=embed)

        return RenderPlan(
            target_type="text_channel",
            operations=[op],
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
        probe_cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            src,
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *probe_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            duration = float(stdout.decode().strip())
        except Exception as exc:
            logger.warning("ffprobe 執行失敗: %s err=%s", src, exc, exc_info=True)
            duration = 0

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
        proc = await asyncio.create_subprocess_exec(
            *pass1_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.warning("ffmpeg pass 1 失敗 (rc=%s): %s\n%s", proc.returncode, src, stderr.decode()[-500:])
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
        proc = await asyncio.create_subprocess_exec(
            *pass2_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

        # 清理 passlog 暫存檔
        for suffix in ("", "-0.log", "-0.log.mbtree"):
            path = passlog + suffix
            if os.path.exists(path):
                os.remove(path)

        if proc.returncode != 0:
            logger.warning("ffmpeg pass 2 失敗 (rc=%s): %s\n%s", proc.returncode, src, stderr.decode()[-500:])
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

    async def publish_to_channel(self, channel: discord.abc.Messageable, plan: RenderPlan) -> int:
        published_count = 0
        tmp_dir: Optional[str] = None
        file_limit = self._get_file_limit(channel)
        logger.debug("Discord 檔案上限: %s bytes (guild=%s)", file_limit, getattr(getattr(channel, "guild", None), "name", "N/A"))

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
                    await channel.send(content=operation.content or None, embed=operation.embed)
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
                await channel.send(content=operation.content or None, embed=embed, files=send_files or None)
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
                        await channel.send(files=files)
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
                        await channel.send(files=files)
                        published_count += 1
        finally:
            # 清理暫存壓縮檔
            if tmp_dir is not None:
                shutil.rmtree(tmp_dir, ignore_errors=True)

        return published_count


class MessageRelayWorker:
    """Telegram Relay Worker：LISTEN + 補償 polling + 去重。"""

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
    ) -> None:
        self.bot = bot
        self.repository = repository
        self.route_resolver = route_resolver
        self.render_adapter = render_adapter
        self.publisher = publisher
        self.dsn = dsn
        self.notify_channel = notify_channel
        self.poll_interval_sec = poll_interval_sec

        self._running = False
        self._queue: asyncio.Queue[int] = asyncio.Queue(maxsize=5000)
        self._tasks: list[asyncio.Task] = []
        self._listen_conn: asyncpg.Connection | None = None

        self._processed_set: set[int] = set()
        self._processed_order: deque[int] = deque(maxlen=5000)
        self._queued_set: set[int] = set()  # 追蹤已在 queue 中的 PK，防止重複入隊
        self._last_polled_pk: int = 0

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

        # 重發模式：從 config 讀取 telegram_message_id，轉換成 message_pk
        replay_from_pk: Optional[int] = None
        replay_msg_id = self.route_resolver.get_replay_from_message_id()
        if replay_msg_id is not None:
            replay_from_pk = await self.repository.get_pk_by_telegram_message_id(replay_msg_id)
            if replay_from_pk is None:
                logger.warning(
                    "Telegram Relay 重送模式：找不到 telegram_message_id=%s 對應的訊息，忽略",
                    replay_msg_id,
                )

        if replay_from_pk is not None:
            self._last_polled_pk = max(0, replay_from_pk - 1)
            await self.repository.set_runtime_cursor_pk(self._last_polled_pk)
            logger.warning(
                "Telegram Relay 啟用重送模式：telegram_message_id=%s → message_pk=%s",
                replay_msg_id, replay_from_pk,
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
            asyncio.create_task(self._listen_loop(), name="telegram_relay_listen"),
            asyncio.create_task(self._poll_loop(), name="telegram_relay_poll"),
            asyncio.create_task(self._process_loop(), name="telegram_relay_process"),
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
        if message_pk in self._queued_set or message_pk in self._processed_set:
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
                    asyncio.get_running_loop().create_task(self._enqueue_message_pk(message_pk))

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

    # media group 等待同組訊息到齊的秒數
    _GROUP_WAIT_SEC = 3.0
    # 等待期間輪詢 DB 的間隔秒數
    _GROUP_POLL_INTERVAL = 0.5

    async def _collect_media_group(self, message: TelegramMessageRecord) -> TelegramMessageRecord:
        """等待同一 media group 的訊息到齊，合併成單一虛擬訊息。

        策略：短暫等待（_GROUP_WAIT_SEC），輪詢 DB 直到組員數穩定，
        然後把所有組員的 media_items 合併到第一則訊息上。
        """
        grouped_id = message.grouped_id
        chat_id = message.telegram_chat_id
        if grouped_id is None:
            return message

        prev_count = 0
        elapsed = 0.0
        while elapsed < self._GROUP_WAIT_SEC:
            await asyncio.sleep(self._GROUP_POLL_INTERVAL)
            elapsed += self._GROUP_POLL_INTERVAL
            sibling_pks = await self.repository.get_grouped_message_pks(grouped_id, chat_id)
            if len(sibling_pks) == prev_count:
                break  # 數量穩定，認為到齊
            prev_count = len(sibling_pks)

        sibling_pks = await self.repository.get_grouped_message_pks(grouped_id, chat_id)

        if len(sibling_pks) <= 1:
            return message

        # 合併所有 sibling 的文字與媒體到第一則訊息
        merged_text_parts: list[str] = []
        merged_media: list[TelegramMediaRecord] = []
        first_msg: Optional[TelegramMessageRecord] = None
        all_pks: list[int] = []

        for pk in sibling_pks:
            sibling = await self.repository.get_message_by_pk(pk)
            if sibling is None:
                continue
            all_pks.append(pk)
            if first_msg is None:
                first_msg = sibling
            if sibling.text.strip():
                merged_text_parts.append(sibling.text.strip())
            merged_media.extend(sibling.media_items)

        if first_msg is None:
            return message

        merged_text = "\n".join(merged_text_parts)
        first_msg.text = merged_text
        first_msg.media_items = merged_media

        logger.info(
            "Telegram relay media group 合併: grouped_id=%s pks=%s media_count=%s",
            grouped_id, all_pks, len(merged_media),
        )
        return first_msg

    async def _process_one(self, message_pk: int) -> None:
        if self._seen_processed(message_pk):
            return

        started = time.perf_counter()
        message = await self.repository.get_message_by_pk(message_pk)
        if message is None:
            logger.warning("Telegram relay 查無訊息: message_pk=%s", message_pk)
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

        # media group 合併：同一 grouped_id 只由最小 pk 負責發送
        sibling_pks: list[int] = []
        if message.grouped_id is not None:
            sibling_pks = await self.repository.get_grouped_message_pks(
                message.grouped_id, message.telegram_chat_id,
            )
            first_pk = sibling_pks[0] if sibling_pks else message_pk
            if message_pk != first_pk:
                # 非組內第一則 → 標記已處理，由第一則統一發送
                logger.info(
                    "Telegram relay media group 成員，交由首則處理: "
                    "message_pk=%s grouped_id=%s first_pk=%s",
                    message_pk, message.grouped_id, first_pk,
                )
                self._mark_processed(message_pk)
                self._last_polled_pk = max(self._last_polled_pk, message_pk)
                await self.repository.set_runtime_cursor_pk(self._last_polled_pk)
                return

            # 是第一則 → 等待同組到齊，合併媒體
            message = await self._collect_media_group(message)

        route_ids = self.route_resolver.resolve_telegram_routes(message.telegram_chat_id)
        if not route_ids:
            logger.info(
                "Telegram relay 無路由，略過: message_pk=%s chat_id=%s telegram_message_id=%s",
                message.message_pk,
                message.telegram_chat_id,
                message.telegram_message_id,
            )
            self._mark_processed(message_pk)
            return

        plan = self.render_adapter.render(message)
        published_count = 0

        replay_msg_id = self.route_resolver.get_replay_from_message_id()
        force_replay = False
        if replay_msg_id is not None:
            replay_pk = await self.repository.get_pk_by_telegram_message_id(replay_msg_id)
            force_replay = replay_pk is not None and message_pk >= replay_pk

        for channel_id in route_ids:
            channel = await self._resolve_channel(channel_id)
            if channel is None:
                logger.warning("Telegram relay 目標頻道不存在或不可發送: channel_id=%s", channel_id)
                continue

            # 確認實際發送目標（guild / channel 名稱）
            guild_name = getattr(getattr(channel, "guild", None), "name", "N/A")
            channel_name = getattr(channel, "name", "N/A")
            logger.info(
                "Telegram relay 發送目標: channel_id=%s guild=%r channel=%r",
                channel_id, guild_name, channel_name,
            )

            if not force_replay:
                already_sent = await self.repository.is_message_published(message_pk, channel_id)
                if already_sent:
                    logger.info(
                        "Telegram relay 略過已發送訊息: message_pk=%s channel_id=%s",
                        message_pk,
                        channel_id,
                    )
                    continue

            try:
                published_count += await self.publisher.publish_to_channel(channel, plan)
                await self.repository.mark_message_published(message_pk, channel_id)
                # 同時標記所有 sibling 為已發送，避免重複送出
                for sib_pk in sibling_pks:
                    if sib_pk != message_pk:
                        await self.repository.mark_message_published(sib_pk, channel_id)
            except Exception as exc:
                logger.error(
                    "Telegram relay 發送失敗: message_pk=%s channel_id=%s err=%s",
                    message_pk,
                    channel_id,
                    exc,
                    exc_info=True,
                )

        # 標記自己與所有 sibling 為已處理
        self._mark_processed(message_pk)
        for sib_pk in sibling_pks:
            self._mark_processed(sib_pk)

        max_pk = max([message_pk] + sibling_pks) if sibling_pks else message_pk
        self._last_polled_pk = max(self._last_polled_pk, max_pk)
        await self.repository.set_runtime_cursor_pk(self._last_polled_pk)
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
            len(sibling_pks) if sibling_pks else 1,
        )

    # 同時處理訊息的並行上限（避免大檔壓縮卡住整條 pipeline）
    _PROCESS_CONCURRENCY = 3

    async def _process_loop(self) -> None:
        sem = asyncio.Semaphore(self._PROCESS_CONCURRENCY)
        bg_tasks: set[asyncio.Task] = set()

        async def _run(pk: int) -> None:
            async with sem:
                try:
                    await self._process_one(pk)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.error("Telegram relay process loop 發生錯誤: %s", exc, exc_info=True)
                finally:
                    self._queued_set.discard(pk)
                    try:
                        self._queue.task_done()
                    except ValueError:
                        pass

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
