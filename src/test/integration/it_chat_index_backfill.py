"""聊天向量庫補寫：在真的資料庫上跑補寫查詢（`llm/storage/chat_index_backfill.py` 的 `_fetch_missing`），只讀不寫。

驗的事：查詢在現在的表結構上跑得動（欄位、型別、跳過清單的寫法）；查回來的每一則真的不在聊天向量庫、也沒被刪除；
組出來的項目欄位齊全、時間是 UTC；帶跳過清單再查，候選數剛好少掉那幾則。不印訊息內容，只印則數與時間範圍。

執行（容器內，pgvector 要在）：
    docker exec -w /app discord-bot python -m test.integration.it_chat_index_backfill
"""
import time
from datetime import datetime, timedelta, timezone

from llm.storage import chat_index_backfill as backfill
from sys_settings.llm_settings import LLMServiceSettings
from sys_settings.pgvector_settings import HYBRID_RETRIEVAL_SETTINGS


def main() -> None:
    now = datetime.now(timezone.utc)
    since, until = now - timedelta(days=backfill.WINDOW_DAYS), now - timedelta(minutes=backfill.SETTLE_MINUTES)

    started = time.monotonic()
    total, rows = backfill._fetch_missing(since, until, backfill.BATCH_LIMIT, [])
    print(f"查詢 {time.monotonic() - started:.2f} 秒；近 {backfill.WINDOW_DAYS} 天候選 {total} 則，這輪拿到 {len(rows)} 則")
    if not rows:
        print("沒有缺的，結束")
        return

    ids = [row["message_id"] for row in rows]
    with LLMServiceSettings().pgvector_cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {HYBRID_RETRIEVAL_SETTINGS.chat_table()} "
                    "WHERE metadata_->>'message_id' = ANY(%s)", (ids,))
        in_index = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM discord_messages_raw WHERE message_id = ANY(%s) AND is_deleted", (ids,))
        deleted = cur.fetchone()[0]
    assert in_index == 0, f"{in_index} 則其實已經在聊天向量庫"
    assert deleted == 0, f"{deleted} 則已被刪除，不該補"
    assert [r["created_at"] for r in rows] == sorted(r["created_at"] for r in rows), "要排成由舊到新"

    items, too_short = backfill.build_items(rows)
    assert all(set(item) == {"message_id", "text", "author_id", "channel_id", "guild_id", "timestamp"} for item in items)
    assert all(item["timestamp"].endswith("+00:00") for item in items), "時間要是 UTC"
    print(f"可排 {len(items)} 則、太短 {len(too_short)} 則；{items[0]['timestamp']} ～ {items[-1]['timestamp']}"
          if items else f"全部太短（{len(too_short)} 則）")

    skip = ids[:3]
    total_after, _ = backfill._fetch_missing(since, until, backfill.BATCH_LIMIT, skip)
    assert total_after == total - len(skip), f"帶跳過清單再查應少 {len(skip)} 則，實際 {total} → {total_after}"
    print("全部通過")


if __name__ == "__main__":
    main()
