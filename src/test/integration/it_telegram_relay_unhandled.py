"""Telegram 轉發：列出「沒有任何紀錄」的訊息，用來觀察還有沒有新的漏送（只讀，不改任何資料）。

背景：2026-10-05 把當時 373 則沒有發送紀錄的訊息標成頻道 0（停止主動追蹤，見
`src/scripts/telegram_mark_unsent_channel0_2026-10-05.sql`）。之後正常情況下，進來超過幾分鐘的訊息
都應該有紀錄（送到主頻道，或頻道 0；之後若加 LLM 隔離區，送進隔離 thread 也算）；這裡列出來的就是新的類似情況。
頻道 0 的 delivered_at 是標記時間、不是送出時間，所以判斷「同組已送」時排除它。

執行（容器內）：
    docker exec -w /app discord-bot python -m test.integration.it_telegram_relay_unhandled [分鐘，預設 60]
只看進來超過 N 分鐘的訊息，避開正在處理中的：爬蟲在圖還沒下載到時會先壓著不通知（最久約 45 分鐘），
門檻太短會把這些當成漏送。
"""
import asyncio
import sys

import asyncpg

from services.relay.telegram_relay_service import build_telegram_pg_dsn_from_env

_CATEGORY = """
    case
      when m.grouped_id is not null and exists (
           select 1 from telegram_messages s join telegram_relay_delivery_state d on d.message_pk = s.id
           where s.grouped_id = m.grouped_id and s.telegram_chat_id = m.telegram_chat_id
             and d.discord_channel_id <> 0) then '相簿：同組其他張已送、這張沒有紀錄'
      when m.grouped_id is not null then '相簿：整組都沒有紀錄'
      when not m.has_media and coalesce(trim(m.text), '') = '' then '單則：沒文字也沒圖（系統通知）'
      when m.has_media and not exists (select 1 from telegram_message_media mm where mm.message_id = m.id)
           then '單則：標示有圖但圖沒下載到'
      else '單則：其他（可能是送失敗、頻道找不到）'
    end
"""


async def main(min_age_minutes: int) -> None:
    conn = await asyncpg.connect(build_telegram_pg_dsn_from_env())
    try:
        channel0 = await conn.fetchval(
            "select count(*) from telegram_relay_delivery_state where discord_channel_id = 0")
        rows = await conn.fetch(f"""
            select {_CATEGORY} as category, count(*) as n,
                   min(m.created_at) as first_at, max(m.created_at) as last_at, array_agg(m.id order by m.id) as ids
            from telegram_messages m
            where not exists (select 1 from telegram_relay_delivery_state d where d.message_pk = m.id)
              and m.created_at < now() - make_interval(mins => $1)
            group by 1 order by 2 desc""", min_age_minutes)
    finally:
        await conn.close()
    print(f"頻道 0（停止主動追蹤）共 {channel0} 筆")
    if not rows:
        print(f"進來超過 {min_age_minutes} 分鐘、卻沒有任何紀錄的訊息：0 則（沒有新的漏送）")
        return
    total = sum(r["n"] for r in rows)
    print(f"進來超過 {min_age_minutes} 分鐘、卻沒有任何紀錄的訊息：{total} 則")
    for r in rows:
        ids = list(r["ids"])
        sample = ", ".join(str(i) for i in ids[:10]) + (" …" if len(ids) > 10 else "")
        print(f"  {r['n']:>4}  {r['category']}  "
              f"（{r['first_at']:%m-%d %H:%M}～{r['last_at']:%m-%d %H:%M} UTC）  編號：{sample}")


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 60))
