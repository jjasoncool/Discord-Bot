from pathlib import Path
from typing import Any

from db import TelegramDatabase
from filters import extract_forward_source_chat_id, is_forward_source_in_whitelist, should_skip_forward
from tg_config import TelegramConfig, TelegramRuntimeConfigWatcher, add_identifier_to_forward_whitelist


def _to_shared_media_rel_path(file_path: str, media_dir: str) -> str:
    """把 telegram 容器中的下載路徑轉為跨容器可用的相對路徑。"""
    media_dir_path = Path(media_dir).resolve()
    downloaded_path = Path(file_path).resolve()

    try:
        rel_under_media = downloaded_path.relative_to(media_dir_path)
    except ValueError:
        # 非預期路徑時退化成檔名，避免流程中斷
        rel_under_media = Path(downloaded_path.name)

    # discord-bot 容器可透過 /app/telegram_scraper/media/... 讀到同一份檔案
    return str(Path("telegram_scraper") / media_dir_path.name / rel_under_media)


def _build_media_item(message: Any, file_rel_path: str) -> dict:
    """組出媒體資料列（盡量從 Telethon message.media 擷取屬性）。"""
    media = getattr(message, "media", None)
    document = getattr(media, "document", None)
    photo = getattr(media, "photo", None)

    if photo is not None:
        media_type = "photo"
        mime_type = "image/jpeg"
        file_size = None
        width = None
        height = None
        duration_sec = None
    elif document is not None:
        mime_type = getattr(document, "mime_type", None)
        if mime_type and mime_type.startswith("video/"):
            media_type = "video"
        elif mime_type and mime_type.startswith("image/"):
            media_type = "image"
        else:
            media_type = "document"

        file_size = getattr(document, "size", None)
        width = None
        height = None
        duration_sec = None
    else:
        media_type = "unknown"
        mime_type = None
        file_size = None
        width = None
        height = None
        duration_sec = None

    return {
        "media_type": media_type,
        "file_rel_path": file_rel_path,
        "mime_type": mime_type,
        "file_size": file_size,
        "width": width,
        "height": height,
        "duration_sec": duration_sec,
        "is_spoiler": bool(getattr(message, "media_unread", False)),
    }


async def _process_message(
    *,
    message: Any,
    chat_id: int | None,
    raw_text: str,
    client: Any,
    config: TelegramConfig,
    runtime_watcher: TelegramRuntimeConfigWatcher,
    db: TelegramDatabase,
    log_prefix: str,
) -> None:
    """處理共用訊息流程（forward 過濾、白名單補齊、媒體處理）。"""
    runtime_snapshot = runtime_watcher.get_snapshot()

    is_forward_message = bool(message.fwd_from)
    allow_forward_here = await is_forward_source_in_whitelist(
        client=client,
        message=message,
        forward_whitelist=runtime_snapshot.forward_whitelist,
    )

    if should_skip_forward(is_forward_message, runtime_snapshot.skip_forwards, allow_forward_here):
        print(f"[{log_prefix}] 略過轉發訊息 message_id={message.id}")
        return

    # 先經過略過判斷後，剩下的是允許通過的轉發訊息，再補來源 chat_id 到白名單
    if is_forward_message and allow_forward_here:
        source_chat_id = extract_forward_source_chat_id(message)
        added = add_identifier_to_forward_whitelist(config.runtime_config_path, source_chat_id or "")
        if added:
            runtime_watcher.refresh(force=True)
            print(f"[{log_prefix}] 已自動加入 forward 白名單來源 chat_id={source_chat_id}")

    text = raw_text or ""
    has_media = bool(message.media)
    media_items: list[dict] = []

    if log_prefix == "History":
        print(f"[History] chat={config.test_channel} message_id={message.id} has_media={has_media} text={text}")
    else:
        print(f"[{log_prefix}] chat_id={chat_id} message_id={message.id} has_media={has_media} text={text}")

    if has_media and runtime_snapshot.download_media:
        file_path = await client.download_media(message, file=runtime_snapshot.media_dir)
        print(f"[{log_prefix}] 媒體已下載: {file_path}")
        if file_path:
            file_rel_path = _to_shared_media_rel_path(str(file_path), runtime_snapshot.media_dir)
            media_items.append(_build_media_item(message, file_rel_path))

    message_pk, inserted_new = await db.upsert_message_with_media(
        telegram_chat_id=int(chat_id or 0),
        telegram_message_id=int(message.id),
        text=text,
        message_date=message.date,
        has_media=has_media,
        media_items=media_items,
    )

    if inserted_new:
        print(f"[{log_prefix}] DB 新增訊息成功 message_pk={message_pk}")
    else:
        print(f"[{log_prefix}] DB 已存在訊息（略過重複）message_pk={message_pk}")


async def handle_new_message(
    event: Any,
    client: Any,
    config: TelegramConfig,
    runtime_watcher: TelegramRuntimeConfigWatcher,
    db: TelegramDatabase,
) -> None:
    """處理即時新訊息事件。"""
    if not event.message:
        return
    await _process_message(
        message=event.message,
        chat_id=event.chat_id,
        raw_text=event.raw_text or "",
        client=client,
        config=config,
        runtime_watcher=runtime_watcher,
        db=db,
        log_prefix="Telegram",
    )


async def handle_history_message(
    msg: Any,
    client: Any,
    config: TelegramConfig,
    runtime_watcher: TelegramRuntimeConfigWatcher,
    db: TelegramDatabase,
) -> None:
    """處理歷史訊息。"""
    await _process_message(
        message=msg,
        chat_id=msg.chat_id,
        raw_text=msg.message or "",
        client=client,
        config=config,
        runtime_watcher=runtime_watcher,
        db=db,
        log_prefix="History",
    )
