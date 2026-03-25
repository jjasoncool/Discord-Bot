import asyncio
import asyncpg
import re


class TelegramDatabase:
    """Telegram 訊息資料庫存取層（asyncpg）。"""

    def __init__(self, dsn: str, notify_channel: str = "telegram_new_message") -> None:
        self.dsn = dsn
        self.notify_channel = notify_channel
        self.pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        """建立連線池。"""
        self.pool = await asyncpg.create_pool(dsn=self.dsn, min_size=1, max_size=5)

    @staticmethod
    async def ensure_database_exists(
        admin_dsn: str,
        target_db: str,
        *,
        max_retries: int = 10,
        retry_delay_sec: float = 2.0,
    ) -> None:
        """確保目標 database 存在，不存在則自動建立。

        PostgreSQL 容器剛啟動時，可能尚未開始接受 TCP 連線，
        因此這裡加入簡單 retry 機制，避免因啟動時序而直接失敗。
        """
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$", target_db):
            raise RuntimeError(f"不合法的 database 名稱: {target_db}")

        last_error: Exception | None = None
        conn = None
        for attempt in range(1, max_retries + 1):
            try:
                conn = await asyncpg.connect(dsn=admin_dsn)
                break
            except OSError as exc:
                last_error = exc
                if attempt >= max_retries:
                    raise RuntimeError(
                        f"無法連線 PostgreSQL（已重試 {max_retries} 次）：{exc}"
                    ) from exc

                print(
                    f"[Telegram][DB] PostgreSQL 尚未 ready，"
                    f"{retry_delay_sec:.1f} 秒後重試 "
                    f"({attempt}/{max_retries})"
                )
                await asyncio.sleep(retry_delay_sec)

        if conn is None:
            raise RuntimeError(f"無法建立 PostgreSQL 管理連線: {last_error}")

        try:
            exists = await conn.fetchval(
                "SELECT 1 FROM pg_database WHERE datname = $1",
                target_db,
            )
            if exists:
                return

            # CREATE DATABASE 不能使用 bind parameter 指定識別字，需手動組 SQL。
            quoted_db = target_db.replace('"', '""')
            await conn.execute(f'CREATE DATABASE "{quoted_db}"')
            print(f"[Telegram][DB] 已自動建立 database: {target_db}")
        finally:
            await conn.close()

    async def close(self) -> None:
        """關閉連線池。"""
        if self.pool is not None:
            await self.pool.close()
            self.pool = None

    async def init_db(self) -> None:
        """初始化 schema（可重複執行，適合容器啟動時自動建表）。"""
        if self.pool is None:
            raise RuntimeError("資料庫尚未 connect")

        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS telegram_messages (
                    id BIGSERIAL PRIMARY KEY,
                    telegram_chat_id BIGINT NOT NULL,
                    telegram_message_id BIGINT NOT NULL,
                    text TEXT,
                    message_date TIMESTAMPTZ,
                    has_media BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE (telegram_chat_id, telegram_message_id)
                );
                """
            )

            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS telegram_message_media (
                    id BIGSERIAL PRIMARY KEY,
                    message_id BIGINT NOT NULL REFERENCES telegram_messages(id) ON DELETE CASCADE,
                    media_type TEXT NOT NULL,
                    file_rel_path TEXT NOT NULL,
                    mime_type TEXT,
                    file_size BIGINT,
                    width INT,
                    height INT,
                    duration_sec INT,
                    is_spoiler BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE (message_id, file_rel_path)
                );
                """
            )

            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_telegram_messages_date
                ON telegram_messages (message_date DESC);
                """
            )

            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_telegram_message_media_message_id
                ON telegram_message_media (message_id);
                """
            )

    async def upsert_message_only(
        self,
        *,
        telegram_chat_id: int,
        telegram_message_id: int,
        text: str,
        message_date,
        has_media: bool,
    ) -> tuple[int, bool]:
        """Upsert 訊息（不含媒體），回傳 (message_pk, inserted_new_message)。"""
        if self.pool is None:
            raise RuntimeError("資料庫尚未 connect")

        async with self.pool.acquire() as conn:
            insert_row = await conn.fetchrow(
                """
                INSERT INTO telegram_messages (
                    telegram_chat_id,
                    telegram_message_id,
                    text,
                    message_date,
                    has_media
                )
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (telegram_chat_id, telegram_message_id) DO NOTHING
                RETURNING id;
                """,
                telegram_chat_id,
                telegram_message_id,
                text,
                message_date,
                has_media,
            )

            if insert_row is not None:
                return int(insert_row["id"]), True

            existing_row = await conn.fetchrow(
                """
                SELECT id
                FROM telegram_messages
                WHERE telegram_chat_id = $1 AND telegram_message_id = $2;
                """,
                telegram_chat_id,
                telegram_message_id,
            )
            if existing_row is None:
                raise RuntimeError("訊息 upsert 後找不到既有資料")

            message_pk = int(existing_row["id"])
            await conn.execute(
                """
                UPDATE telegram_messages
                SET
                    text = CASE
                        WHEN COALESCE(text, '') = '' AND COALESCE($2, '') <> '' THEN $2
                        ELSE text
                    END,
                    message_date = COALESCE(message_date, $3),
                    has_media = has_media OR $4,
                    updated_at = NOW()
                WHERE id = $1;
                """,
                message_pk,
                text,
                message_date,
                has_media,
            )
            return message_pk, False

    async def has_media_records(self, message_pk: int) -> bool:
        """確認此訊息是否已有媒體記錄。"""
        if self.pool is None:
            raise RuntimeError("資料庫尚未 connect")

        async with self.pool.acquire() as conn:
            exists = await conn.fetchval(
                "SELECT 1 FROM telegram_message_media WHERE message_id = $1 LIMIT 1;",
                int(message_pk),
            )
        return bool(exists)

    async def upsert_media_items(self, message_pk: int, media_items: list[dict]) -> None:
        """批次寫入/更新媒體記錄。"""
        if self.pool is None:
            raise RuntimeError("資料庫尚未 connect")

        if not media_items:
            return

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                for media in media_items:
                    await conn.execute(
                        """
                        INSERT INTO telegram_message_media (
                            message_id,
                            media_type,
                            file_rel_path,
                            mime_type,
                            file_size,
                            width,
                            height,
                            duration_sec,
                            is_spoiler
                        )
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                        ON CONFLICT (message_id, file_rel_path)
                        DO UPDATE SET
                            mime_type = COALESCE(EXCLUDED.mime_type, telegram_message_media.mime_type),
                            file_size = COALESCE(EXCLUDED.file_size, telegram_message_media.file_size),
                            width = COALESCE(EXCLUDED.width, telegram_message_media.width),
                            height = COALESCE(EXCLUDED.height, telegram_message_media.height),
                            duration_sec = COALESCE(EXCLUDED.duration_sec, telegram_message_media.duration_sec),
                            is_spoiler = EXCLUDED.is_spoiler,
                            updated_at = NOW();
                        """,
                        int(message_pk),
                        media["media_type"],
                        media["file_rel_path"],
                        media.get("mime_type"),
                        media.get("file_size"),
                        media.get("width"),
                        media.get("height"),
                        media.get("duration_sec"),
                        bool(media.get("is_spoiler", False)),
                    )

    async def notify_new_message(self, message_pk: int) -> None:
        """發送 pg_notify 通知新訊息。"""
        if self.pool is None:
            raise RuntimeError("資料庫尚未 connect")

        async with self.pool.acquire() as conn:
            await conn.execute(
                "SELECT pg_notify($1, $2)",
                self.notify_channel,
                str(message_pk),
            )

    async def upsert_message_with_media(
        self,
        *,
        telegram_chat_id: int,
        telegram_message_id: int,
        text: str,
        message_date,
        has_media: bool,
        media_items: list[dict],
    ) -> tuple[int, bool]:
        """Upsert 訊息與媒體，回傳 (message_pk, inserted_new_message)。"""
        if self.pool is None:
            raise RuntimeError("資料庫尚未 connect")

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                insert_row = await conn.fetchrow(
                    """
                    INSERT INTO telegram_messages (
                        telegram_chat_id,
                        telegram_message_id,
                        text,
                        message_date,
                        has_media
                    )
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (telegram_chat_id, telegram_message_id) DO NOTHING
                    RETURNING id;
                    """,
                    telegram_chat_id,
                    telegram_message_id,
                    text,
                    message_date,
                    has_media,
                )

                inserted_new_message = insert_row is not None
                if inserted_new_message:
                    message_pk = int(insert_row["id"])
                else:
                    existing_row = await conn.fetchrow(
                        """
                        SELECT id
                        FROM telegram_messages
                        WHERE telegram_chat_id = $1 AND telegram_message_id = $2;
                        """,
                        telegram_chat_id,
                        telegram_message_id,
                    )
                    if existing_row is None:
                        raise RuntimeError("訊息 upsert 後找不到既有資料")

                    message_pk = int(existing_row["id"])

                    await conn.execute(
                        """
                        UPDATE telegram_messages
                        SET
                            text = CASE
                                WHEN COALESCE(text, '') = '' AND COALESCE($2, '') <> '' THEN $2
                                ELSE text
                            END,
                            message_date = COALESCE(message_date, $3),
                            has_media = has_media OR $4,
                            updated_at = NOW()
                        WHERE id = $1;
                        """,
                        message_pk,
                        text,
                        message_date,
                        has_media,
                    )

                for media in media_items:
                    await conn.execute(
                        """
                        INSERT INTO telegram_message_media (
                            message_id,
                            media_type,
                            file_rel_path,
                            mime_type,
                            file_size,
                            width,
                            height,
                            duration_sec,
                            is_spoiler
                        )
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                        ON CONFLICT (message_id, file_rel_path)
                        DO UPDATE SET
                            mime_type = COALESCE(EXCLUDED.mime_type, telegram_message_media.mime_type),
                            file_size = COALESCE(EXCLUDED.file_size, telegram_message_media.file_size),
                            width = COALESCE(EXCLUDED.width, telegram_message_media.width),
                            height = COALESCE(EXCLUDED.height, telegram_message_media.height),
                            duration_sec = COALESCE(EXCLUDED.duration_sec, telegram_message_media.duration_sec),
                            is_spoiler = EXCLUDED.is_spoiler,
                            updated_at = NOW();
                        """,
                        message_pk,
                        media["media_type"],
                        media["file_rel_path"],
                        media.get("mime_type"),
                        media.get("file_size"),
                        media.get("width"),
                        media.get("height"),
                        media.get("duration_sec"),
                        bool(media.get("is_spoiler", False)),
                    )

                if inserted_new_message:
                    await conn.execute(
                        "SELECT pg_notify($1, $2)",
                        self.notify_channel,
                        str(message_pk),
                    )

                return message_pk, inserted_new_message
