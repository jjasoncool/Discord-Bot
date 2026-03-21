import os
from datetime import datetime, timedelta, timezone

from telethon import TelegramClient, events

from handlers import handle_history_message, handle_new_message
from tg_config import TelegramConfig


async def run_telegram_scraper(config: TelegramConfig) -> None:
    """根據設定啟動 Telegram client，執行歷史抓取與即時監聽。"""
    os.makedirs(config.session_dir, exist_ok=True)
    os.makedirs(config.media_dir, exist_ok=True)

    session_path = f"{config.session_dir}/{config.session_name}"
    client = TelegramClient(session_path, config.api_id, config.api_hash)

    @client.on(events.NewMessage)
    async def on_new_message(event: events.NewMessage.Event) -> None:
        """即時新訊息事件入口。"""
        await handle_new_message(event, client, config)

    print("[Telegram] 正在啟動 client...")
    await client.start()

    if config.forward_whitelist:
        print(f"[Telegram] Forward 白名單已啟用: {sorted(config.forward_whitelist)}")
    else:
        print("[Telegram] Forward 白名單未設定")

    print(f"[Telegram] 已連線，開始測試抓取頻道: {config.test_channel}")
    cutoff_dt = None
    if config.history_hours is not None:
        cutoff_dt = datetime.now(timezone.utc) - timedelta(hours=config.history_hours)
        print(f"[Telegram] 歷史時間窗已啟用：最近 {config.history_hours} 小時")

    async for msg in client.iter_messages(config.test_channel, limit=config.history_limit):
        if cutoff_dt is not None and msg.date is not None and msg.date < cutoff_dt:
            # iter_messages 由新到舊，超過時間窗後可直接停止
            print(f"[Telegram] 已達歷史時間窗，停止掃描（message_id={msg.id}）")
            break

        await handle_history_message(msg, client, config)

    print("[Telegram] 歷史訊息測試完成，開始監聽新訊息")
    await client.run_until_disconnected()
