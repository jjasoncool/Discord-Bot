-- Raw 訊息備份表：on_message / edit / delete / reaction 全量寫入
--
-- 執行方式（必須在 container 內，pgvector 只在 docker network 可達）：
--   docker exec -i pgvector psql -U llm_vector -d discord_data \
--     < /app/scripts/create_raw_messages_table.sql
--
-- 設計原則：
-- 1. 全量原始訊息備份，不做任何過濾（bot 訊息除外）
-- 2. 貼圖/Tenor GIF 結構化儲存（非合併到 content）
-- 3. Reaction 以 JSONB 結構化儲存，reactors 為 source of truth
-- 4. 軟刪除（is_deleted flag），保留歷史分析能力
--
-- 與 data_discord_messages_index（pgvector 索引）的關係：
-- - 此表是「原始備份 + 互動狀態真相來源」
-- - pgvector 那張是「篩選後的語意索引」（未來 Phase 4 才會改成依賴此表）
-- - 目前兩者並列（雙寫），互不影響

CREATE TABLE IF NOT EXISTS discord_messages_raw (
    -- 主鍵與關聯
    message_id       TEXT PRIMARY KEY,
    guild_id         TEXT NOT NULL,
    channel_id       TEXT NOT NULL,                 -- 若在 thread 內，此為 thread 的父頻道
    thread_id        TEXT,                          -- 若在 thread 內才有值
    author_id        TEXT NOT NULL,

    -- 內容（原始，不做 emoji/mention 替換）
    content          TEXT NOT NULL DEFAULT '',

    -- 圖像/嵌入（結構化）
    -- stickers: [{"id": "...", "name": "...", "format_type": int, "description": "..."}]
    stickers         JSONB,
    -- tenor_gifs: [{"url": "...", "title": "...", "description": "..."}]
    tenor_gifs       JSONB,
    has_attachment   BOOLEAN NOT NULL DEFAULT FALSE,
    has_embed        BOOLEAN NOT NULL DEFAULT FALSE,  -- 扣除 tenor 之外的 embed

    -- 時間
    created_at       TIMESTAMPTZ NOT NULL,
    edited_at        TIMESTAMPTZ,
    ingested_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- 對話關係
    reply_to_id      TEXT,
    mention_count    INTEGER NOT NULL DEFAULT 0,
    mentioned_users  JSONB,                           -- ["user_id_a", "user_id_b"]

    -- Reaction 結構化資料
    -- reaction_breakdown schema:
    -- {
    --   "reactors": {"user_id": ["emoji_key_1", ...]},   <- source of truth
    --   "by_emoji": {"emoji_key": count},                 <- derived
    --   "by_category": {"agree": N, "laugh": N, ...}      <- derived
    -- }
    -- emoji_key 格式：
    --   Unicode emoji：直接用字元（例如 "👍"）
    --   Custom emoji：name:id 格式（例如 "LULW:12345"）
    reaction_total         INTEGER NOT NULL DEFAULT 0,
    reaction_unique_users  INTEGER NOT NULL DEFAULT 0,
    reaction_diversity     INTEGER NOT NULL DEFAULT 0,
    reaction_breakdown     JSONB,
    reactions_updated_at   TIMESTAMPTZ,

    -- Reply 統計（被別人 reply 次數；由定期任務回填）
    reply_count            INTEGER NOT NULL DEFAULT 0,

    -- Pipeline 狀態（Phase 4 才會真正用到，先預留）
    indexed_to_pgvector    BOOLEAN NOT NULL DEFAULT FALSE,
    indexed_at             TIMESTAMPTZ,
    quality_score          REAL,

    -- 軟刪除
    is_deleted             BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at             TIMESTAMPTZ,

    -- 相容標記：TRUE 代表從 pgvector backfill 而來，content 可能含貼圖描述合併文字
    legacy_backfilled      BOOLEAN NOT NULL DEFAULT FALSE
);

-- 常用查詢索引
CREATE INDEX IF NOT EXISTS idx_raw_channel_ts
    ON discord_messages_raw (channel_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_raw_author_ts
    ON discord_messages_raw (author_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_raw_pending_index
    ON discord_messages_raw (ingested_at)
    WHERE indexed_to_pgvector = FALSE AND is_deleted = FALSE;

CREATE INDEX IF NOT EXISTS idx_raw_reply_to
    ON discord_messages_raw (reply_to_id)
    WHERE reply_to_id IS NOT NULL;

-- JSONB 內部查詢（例如找所有有 LULW reaction 的訊息）
CREATE INDEX IF NOT EXISTS idx_raw_reaction_emoji
    ON discord_messages_raw
    USING GIN ((reaction_breakdown -> 'by_emoji'));

-- 熱門訊息查詢（高 reaction 的快速排序）
CREATE INDEX IF NOT EXISTS idx_raw_hot_messages
    ON discord_messages_raw (reaction_unique_users DESC, created_at DESC)
    WHERE reaction_unique_users >= 2 AND is_deleted = FALSE;
