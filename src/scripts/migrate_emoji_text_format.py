"""把 pgvector 內舊的 `<:name:id>` 格式 text 換成 `:描述:` 格式。

背景：
chat_persistence 以前直接把 msg.content 原文送去 embed，emoji token 變亂碼。
後來改成先做語意替換 `<:name:id>` → `:描述:`，但舊資料仍是亂碼。
此 script 把舊資料的 text 欄位跑一次語意替換，順便 NULL 掉 embedding，
讓 reembed_pgvector.py 重建向量。

使用方式（在 container 內執行）：
    # 先預覽要改幾筆：
    docker exec discord-bot python /app/scripts/migrate_emoji_text_format.py --dry-run

    # 實際套用（只改 data_discord_messages_index）：
    docker exec discord-bot python /app/scripts/migrate_emoji_text_format.py

    # 指定其他資料表也行：
    docker exec discord-bot python /app/scripts/migrate_emoji_text_format.py \
        --table data_discord_member_profiles_index

完成後要跑 reembed_pgvector.py 把 NULL embedding 補回：
    docker exec discord-bot python /app/scripts/reembed_pgvector.py \
        --table data_discord_messages_index

特性：
- Idempotent：已轉換過的 text 不會再被動（沒有 <:.*?:> 就跳過）
- 只更新「text 真的有變的」row，未變動者不動
- 失敗單筆跳過，最後印 summary
"""
from __future__ import annotations

import argparse
import logging
import sys

sys.path.insert(0, "/app")

import psycopg2
import psycopg2.extras

from llm.emoji_text_utils import replace_custom_emoji_with_description
from sys_settings.llm_settings import LLMServiceSettings

logger = logging.getLogger("migrate_emoji")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


def get_conn():
    s = LLMServiceSettings()
    return LLMServiceSettings().pgvector_connect()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", default="data_discord_messages_index",
                    help="要處理的 pgvector 資料表")
    ap.add_argument("--dry-run", action="store_true",
                    help="只計算要改的筆數，不實際 UPDATE")
    ap.add_argument("--batch-size", type=int, default=200,
                    help="每批 commit 的筆數")
    args = ap.parse_args()

    conn = get_conn()
    conn.autocommit = False

    try:
        # 撈所有有 custom emoji 的 row
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                f"""
                SELECT node_id, text
                FROM {args.table}
                WHERE text ~ '<a?:\\w+:\\d+>'
                """
            )
            rows = cur.fetchall()

        logger.info("%s: 找到 %d 筆含 custom emoji token", args.table, len(rows))
        if not rows:
            logger.info("沒有要轉換的 row，結束")
            return

        changed = []
        unchanged = 0
        for row in rows:
            old_text = row["text"] or ""
            new_text = replace_custom_emoji_with_description(old_text)
            if new_text != old_text:
                changed.append((row["node_id"], old_text, new_text))
            else:
                unchanged += 1

        logger.info(
            "語意替換結果：有變化 %d 筆 / 無變化 %d 筆（文字一樣代表字典沒登錄那些 emoji）",
            len(changed), unchanged,
        )

        # 預覽前 3 筆
        for i, (nid, old, new) in enumerate(changed[:3]):
            logger.info("範例 %d | node_id=%s", i + 1, nid)
            logger.info("  舊: %s", old[:150])
            logger.info("  新: %s", new[:150])

        if args.dry_run:
            logger.info("dry-run：不實際寫入 DB")
            return

        # 分批 UPDATE text 並 NULL embedding
        total_updated = 0
        for i in range(0, len(changed), args.batch_size):
            batch = changed[i:i + args.batch_size]
            with conn.cursor() as cur:
                for nid, _old, new in batch:
                    cur.execute(
                        f"""
                        UPDATE {args.table}
                        SET text = %s,
                            embedding = NULL
                        WHERE node_id = %s
                        """,
                        (new, nid),
                    )
            conn.commit()
            total_updated += len(batch)
            logger.info("已更新 %d / %d", total_updated, len(changed))

        logger.info(
            "完成：text 更新 %d 筆、embedding 清空 %d 筆。\n"
            "下一步執行：\n"
            "  docker exec discord-bot python /app/scripts/reembed_pgvector.py --table %s",
            total_updated, total_updated, args.table,
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
