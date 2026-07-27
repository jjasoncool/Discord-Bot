import asyncio
import json
import os
from datetime import datetime, timedelta, timezone

from telethon import TelegramClient, events

from db import TelegramDatabase
from handlers import handle_history_message, handle_new_message, handle_refetch_message
from tg_config import TelegramConfig, TelegramRuntimeConfigWatcher


# relay（discord-bot 容器）透過此 pg NOTIFY channel 要求重抓某則訊息，
# 由本容器「既有常駐 client」執行（不可另開 session）。須與 relay 端常數一致。
EMOJI_REFETCH_CHANNEL = "telegram_emoji_refetch"


async def _handle_refetch_request(payload, client, config, runtime_watcher, db) -> None:
    """處理一筆重抓要求：payload = JSON {chat_id, message_id}。"""
    try:
        data = json.loads(payload)
        chat_id = int(data["chat_id"])
        message_id = int(data["message_id"])
    except Exception as exc:
        print(f"[Refetch] payload 解析失敗 payload={payload!r}: {exc}")
        return

    msg = None
    try:
        msg = await client.get_messages(chat_id, ids=message_id)
    except Exception as exc:
        print(f"[Refetch] 以 chat_id={chat_id} 取訊息失敗，改用 source_channel 重試: {exc}")
    if msg is None:
        try:
            msg = await client.get_messages(config.source_channel, ids=message_id)
        except Exception as exc:
            print(f"[Refetch] 取訊息失敗 chat_id={chat_id} msg_id={message_id}: {exc}")
            return
    if msg is None:
        print(f"[Refetch] 找不到訊息 chat_id={chat_id} msg_id={message_id}")
        return

    try:
        await handle_refetch_message(msg, chat_id, client, config, runtime_watcher, db)
        print(f"[Refetch] 完成 chat_id={chat_id} msg_id={message_id}")
    except Exception as exc:
        print(f"[Refetch] 處理訊息失敗 chat_id={chat_id} msg_id={message_id}: {exc}")


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

    listen_channels = config.source_channels or [config.source_channel]

    @client.on(events.NewMessage(chats=listen_channels))
    async def on_new_message(event: events.NewMessage.Event) -> None:
        """即時新訊息事件入口 — 監聽所有 source_channels。"""
        await handle_new_message(event, client, config, runtime_watcher, db)

    try:
        print("[Telegram] 正在啟動 client...")
        await client.start()

        # on-demand 重抓監聽：越早起越好——歷史掃描可能很久，這段期間也要能收 relay 的
        # /resend_article 重抓通知。用常駐 client 抓指定訊息、補齊自訂表情後回填 DB。
        refetch_listen_conn = None
        refetch_tasks: set = set()
        try:
            refetch_listen_conn = await db.pool.acquire()

            def _on_refetch_notify(conn, pid, channel, payload):
                # 持有 task 參照，避免被 GC 掉導致重抓靜默失敗
                task = asyncio.create_task(
                    _handle_refetch_request(payload, client, config, runtime_watcher, db)
                )
                refetch_tasks.add(task)
                task.add_done_callback(refetch_tasks.discard)

            await refetch_listen_conn.add_listener(EMOJI_REFETCH_CHANNEL, _on_refetch_notify)
            print(f"[Telegram] 已監聽自訂表情重抓通知: {EMOJI_REFETCH_CHANNEL}")
        except Exception as exc:
            print(f"[Telegram] 啟動重抓監聽失敗（不影響主流程）: {exc}")

        if runtime_snapshot.forward_whitelist:
            print(f"[Telegram] Forward 白名單已啟用: {sorted(runtime_snapshot.forward_whitelist)}")
        else:
            print("[Telegram] Forward 白名單未設定")

        print(f"[Telegram] 已連線，開始抓取來源頻道: {', '.join(listen_channels)}")
        cutoff_dt = None
        if runtime_snapshot.history_hours is not None:
            cutoff_dt = datetime.now(timezone.utc) - timedelta(hours=runtime_snapshot.history_hours)
            print(f"[Telegram] 歷史時間窗已啟用：最近 {runtime_snapshot.history_hours} 小時")

        # 逐頻道處理歷史：iter_messages 預設由新到舊，先收集後反轉成舊到新再 insert，
        # 確保「同一頻道」DB id（BIGSERIAL）與訊息時間順序一致，relay 發文才能按時序。
        # 各頻道獨立收集/反轉，避免多來源交錯打亂單頻道時序。
        for source_channel in listen_channels:
            pending_msgs = []
            async for msg in client.iter_messages(source_channel, limit=None):
                if cutoff_dt is not None and msg.date is not None and msg.date < cutoff_dt:
                    print(f"[Telegram] {source_channel} 已達歷史時間窗，停止收集（message_id={msg.id}）")
                    break
                pending_msgs.append(msg)
                if config.history_limit > 0 and len(pending_msgs) >= config.history_limit:
                    print(f"[Telegram] {source_channel} 已達歷史訊息上限（{config.history_limit} 筆），停止收集")
                    break

            # 反轉：舊 → 新，依序 insert 讓 PK 與時間序一致
            pending_msgs.reverse()
            print(f"[Telegram] {source_channel} 開始依時序處理歷史訊息（共 {len(pending_msgs)} 筆）")

            accepted_history_count = 0
            for msg in pending_msgs:
                accepted = await handle_history_message(msg, client, config, runtime_watcher, db)
                if accepted:
                    accepted_history_count += 1
            print(f"[Telegram] {source_channel} 歷史訊息抓取完成（收下 {accepted_history_count} 筆）")

        print("[Telegram] 全部來源歷史抓取完成，開始監聽新訊息")
        await client.run_until_disconnected()
    finally:
        await db.close()
