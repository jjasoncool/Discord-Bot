import os
from datetime import datetime, timedelta, timezone

from telethon import TelegramClient, events

from db import TelegramDatabase
from handlers import handle_history_message, handle_new_message
from tg_config import TelegramConfig, TelegramRuntimeConfigWatcher


async def run_telegram_scraper(config: TelegramConfig) -> None:
    """根據設定啟動 Telegram client，執行歷史抓取與即時監聽。"""
    os.makedirs(config.session_dir, exist_ok=True)
    os.makedirs(config.media_dir, exist_ok=True)

    db = TelegramDatabase(
        dsn=config.build_asyncpg_dsn(),
        notify_channel=config.pg_notify_channel,
    )
    runtime_watcher = TelegramRuntimeConfigWatcher(
        runtime_config_path=config.runtime_config_path,
        fallback_config=config,
    )
    runtime_snapshot = runtime_watcher.get_snapshot()

    await TelegramDatabase.ensure_database_exists(
        admin_dsn=config.build_admin_dsn(),
        target_db=config.pg_db,
    )
    await db.connect()
    await db.init_db()
    print("[Telegram] DB 初始化完成")

    session_path = f"{config.session_dir}/{config.session_name}"
    client = TelegramClient(session_path, config.api_id, config.api_hash)

    @client.on(events.NewMessage(chats=[config.source_channel]))
    async def on_new_message(event: events.NewMessage.Event) -> None:
        """即時新訊息事件入口 — 僅監聽 source_channel。"""
        await handle_new_message(event, client, config, runtime_watcher, db)

    try:
        print("[Telegram] 正在啟動 client...")
        await client.start()

        if runtime_snapshot.forward_whitelist:
            print(f"[Telegram] Forward 白名單已啟用: {sorted(runtime_snapshot.forward_whitelist)}")
        else:
            print("[Telegram] Forward 白名單未設定")

        print(f"[Telegram] 已連線，開始抓取來源頻道: {config.source_channel}")
        cutoff_dt = None
        if runtime_snapshot.history_hours is not None:
            cutoff_dt = datetime.now(timezone.utc) - timedelta(hours=runtime_snapshot.history_hours)
            print(f"[Telegram] 歷史時間窗已啟用：最近 {runtime_snapshot.history_hours} 小時")

        # iter_messages 預設由新到舊，先收集後反轉成舊到新再 insert
        # 確保 DB id（BIGSERIAL）與訊息時間順序一致，relay 發文才能按時序
        pending_msgs = []
        async for msg in client.iter_messages(config.source_channel, limit=None):
            if cutoff_dt is not None and msg.date is not None and msg.date < cutoff_dt:
                print(f"[Telegram] 已達歷史時間窗，停止收集（message_id={msg.id}）")
                break
            pending_msgs.append(msg)
            if config.history_limit > 0 and len(pending_msgs) >= config.history_limit:
                print(f"[Telegram] 已達歷史訊息上限（{config.history_limit} 筆），停止收集")
                break

        # 反轉：舊 → 新，依序 insert 讓 PK 與時間序一致
        pending_msgs.reverse()
        print(f"[Telegram] 開始依時序處理歷史訊息（共 {len(pending_msgs)} 筆）")

        accepted_history_count = 0
        for msg in pending_msgs:
            accepted = await handle_history_message(msg, client, config, runtime_watcher, db)
            if accepted:
                accepted_history_count += 1

        print("[Telegram] 歷史訊息抓取完成，開始監聽新訊息")
        await client.run_until_disconnected()
    finally:
        await db.close()
