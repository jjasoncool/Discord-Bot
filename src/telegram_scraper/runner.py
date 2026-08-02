import asyncio
import json
import os
from datetime import datetime, timedelta, timezone

from telethon import TelegramClient, events
from telethon.utils import get_peer_id

from db import TelegramDatabase
from handlers import (
    handle_catchup_message,
    handle_history_message,
    handle_new_message,
    handle_refetch_message,
)
from tg_config import TelegramConfig, TelegramRuntimeConfigWatcher


# relay（discord-bot 容器）透過此 pg NOTIFY channel 要求重抓某則訊息，
# 由本容器「既有常駐 client」執行（不可另開 session）。須與 relay 端常數一致。
EMOJI_REFETCH_CHANNEL = "telegram_emoji_refetch"

# 週期性補掃單輪、單頻道的訊息上限。由舊往新掃，超出的部分下一輪接著補，
# 不會留下永久空洞；純粹避免異常大缺口時一次打爆 Telegram rate limit。
CATCHUP_MAX_PER_CYCLE = 200

# 補掃停用時的迴圈輪詢間隔（秒）——讓使用者改完 runtime_config 不必重啟即可恢復
CATCHUP_DISABLED_RECHECK_SEC = 60


async def _handle_refetch_request(payload, client, config, runtime_watcher, db, process_lock) -> None:
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
        async with process_lock:
            await handle_refetch_message(msg, chat_id, client, config, runtime_watcher, db)
        print(f"[Refetch] 完成 chat_id={chat_id} msg_id={message_id}")
    except Exception as exc:
        print(f"[Refetch] 處理訊息失敗 chat_id={chat_id} msg_id={message_id}: {exc}")


_catchup_chat_id_cache: dict[str, int] = {}


async def _resolve_catchup_chat_id(client, source_channel: str) -> int | None:
    """把頻道識別值解析成 Telegram chat_id（marked id，與 DB 存的一致），結果快取。"""
    cached = _catchup_chat_id_cache.get(source_channel)
    if cached is not None:
        return cached

    try:
        entity = await client.get_entity(source_channel)
        chat_id = int(get_peer_id(entity))
    except Exception as exc:
        print(f"[CatchUp] 解析頻道 chat_id 失敗 channel={source_channel}: {exc}")
        return None

    _catchup_chat_id_cache[source_channel] = chat_id
    return chat_id


async def _catch_up_channel(
    source_channel: str,
    client,
    config: TelegramConfig,
    runtime_watcher: TelegramRuntimeConfigWatcher,
    db: TelegramDatabase,
    process_lock: asyncio.Lock,
) -> None:
    """對單一頻道補掃「DB 內最大 message_id 之後」的訊息。"""
    chat_id = await _resolve_catchup_chat_id(client, source_channel)
    if chat_id is None:
        return

    last_id = await db.get_max_message_id(chat_id)
    if not last_id:
        # 該頻道還沒有任何資料 → 沒有安全的增量基準，交給啟動歷史掃描處理
        return

    fetched = 0
    accepted = 0
    # reverse=True 時 Telethon 會把 offset_id 當「從此 id 之後開始」（內部 +1，不含基準本身），
    # 且回傳順序為舊 → 新，正好讓 BIGSERIAL 與訊息時序一致，relay 才能照時序發。
    async for msg in client.iter_messages(
        source_channel,
        reverse=True,
        offset_id=last_id,
        limit=CATCHUP_MAX_PER_CYCLE,
    ):
        fetched += 1
        # 與即時事件、refetch 共用同一把鎖，避免同一則訊息被並行處理（重複下載媒體）
        async with process_lock:
            if await handle_catchup_message(
                msg, client, config, runtime_watcher, db, source_label=source_channel
            ):
                accepted += 1

    if fetched:
        print(
            f"[CatchUp] {source_channel} 補回漏收訊息："
            f"基準 message_id={last_id} 之後撈到 {fetched} 筆、收下 {accepted} 筆"
        )
    if fetched >= CATCHUP_MAX_PER_CYCLE:
        print(f"[CatchUp] {source_channel} 已達單輪上限（{CATCHUP_MAX_PER_CYCLE} 筆），剩餘部分下一輪繼續")


async def _catch_up_loop(
    client,
    config: TelegramConfig,
    runtime_watcher: TelegramRuntimeConfigWatcher,
    db: TelegramDatabase,
    listen_channels: list[str],
    process_lock: asyncio.Lock,
) -> None:
    """週期性補掃：修補 Telethon 漏掉的即時 NewMessage 事件。

    原本只靠即時事件 + 啟動時掃一次歷史，一旦事件遺失就得等下次重啟才會補上
    （實測每天都有漏，曾出現整整半天沒有任何新訊息進 DB）。這裡以各頻道在 DB
    的最大 message_id 為基準做增量重掃，漏掉的訊息最多延遲一個週期就會自動
    補進 DB 並 NOTIFY relay，不需人工重啟容器。
    """
    while True:
        interval_min = runtime_watcher.get_snapshot().catchup_interval_min
        if interval_min <= 0:
            await asyncio.sleep(CATCHUP_DISABLED_RECHECK_SEC)
            continue

        await asyncio.sleep(interval_min * 60)

        for source_channel in listen_channels:
            try:
                await _catch_up_channel(
                    source_channel, client, config, runtime_watcher, db, process_lock
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # 單一頻道失敗（FloodWait、暫時性網路問題等）不能拖垮整個補掃迴圈
                print(f"[CatchUp] {source_channel} 補掃失敗（下一輪重試）: {exc}")


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

    # 即時事件 / 補掃 / refetch 三條路徑都會處理訊息，共用一把鎖序列化，
    # 避免同一則訊息被並行處理造成重複下載媒體或搶寫同一筆記錄。
    process_lock = asyncio.Lock()

    @client.on(events.NewMessage(chats=listen_channels))
    async def on_new_message(event: events.NewMessage.Event) -> None:
        """即時新訊息事件入口 — 監聽所有 source_channels。"""
        async with process_lock:
            await handle_new_message(event, client, config, runtime_watcher, db)

    catchup_task: asyncio.Task | None = None
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
                    _handle_refetch_request(
                        payload, client, config, runtime_watcher, db, process_lock
                    )
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
                accepted = await handle_history_message(
                    msg, client, config, runtime_watcher, db, source_label=source_channel
                )
                if accepted:
                    accepted_history_count += 1
            print(f"[Telegram] {source_channel} 歷史訊息抓取完成（收下 {accepted_history_count} 筆）")

        print("[Telegram] 全部來源歷史抓取完成，開始監聽新訊息")

        catchup_interval_min = runtime_watcher.get_snapshot().catchup_interval_min
        catchup_task = asyncio.create_task(
            _catch_up_loop(client, config, runtime_watcher, db, listen_channels, process_lock),
            name="telegram_catch_up",
        )
        if catchup_interval_min > 0:
            print(f"[Telegram] 週期性補掃已啟動（每 {catchup_interval_min} 分鐘增量重掃）")
        else:
            print("[Telegram] 週期性補掃目前為停用狀態（catchup_interval_min <= 0）")

        await client.run_until_disconnected()
    finally:
        if catchup_task is not None:
            catchup_task.cancel()
            try:
                await catchup_task
            except (asyncio.CancelledError, Exception):
                pass
        await db.close()
