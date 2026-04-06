from pathlib import Path
from typing import Any

from db import TelegramDatabase
from filters import extract_forward_source_chat_id, is_forward_source_in_whitelist, should_skip_forward
from tg_config import TelegramConfig, TelegramRuntimeConfigWatcher, add_identifier_to_forward_whitelist


_MIME_TO_EXT: dict[str, str] = {
    # 圖片
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/tiff": ".tiff",
    "image/svg+xml": ".svg",
    # 影片
    "video/mp4": ".mp4",
    "video/mpeg": ".mpeg",
    "video/quicktime": ".mov",
    "video/webm": ".webm",
    "video/x-matroska": ".mkv",
    "video/x-msvideo": ".avi",
    "video/3gpp": ".3gp",
    # 音訊
    "audio/ogg": ".ogg",
    "audio/x-ogg": ".ogg",
    "audio/opus": ".ogg",        # Telegram 語音訊息（OPUS in OGG）
    "audio/x-opus+ogg": ".ogg",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/mp4": ".m4a",
    "audio/x-m4a": ".m4a",
    "audio/aac": ".aac",
    "audio/x-aac": ".aac",
    "audio/flac": ".flac",
    "audio/x-flac": ".flac",
    # 文件
    "application/pdf": ".pdf",
    "application/zip": ".zip",
    "application/x-zip-compressed": ".zip",
    "application/x-rar-compressed": ".rar",
    "application/x-7z-compressed": ".7z",
    "application/x-tar": ".tar",
    "application/gzip": ".gz",
    "application/vnd.android.package-archive": ".apk",
    "application/x-tgsticker": ".tgs",   # Telegram 動態貼圖
    "text/plain": ".txt",
    "text/html": ".html",
    "text/csv": ".csv",
}


def _ext_from_mime(mime: str) -> str:
    """從 mime type 決定副檔名，找不到時依大類兜底。"""
    mime = (mime or "").strip().lower()
    if mime in _MIME_TO_EXT:
        return _MIME_TO_EXT[mime]
    # 大類兜底
    if mime.startswith("image/"):
        return ".jpg"
    if mime.startswith("video/"):
        return ".mp4"
    if mime.startswith("audio/"):
        return ".ogg"
    if mime.startswith("text/"):
        return ".txt"
    return ".bin"


def _build_stable_media_path(message: Any, media_dir: str) -> str | None:
    """依 photo/document ID 建立穩定檔名路徑，避免重複下載產生 (N) 後綴。

    副檔名優先順序：
    1. document attributes 裡的原始檔名（最準確）
    2. mime type 對應表
    3. 大類兜底
    """
    media = getattr(message, "media", None)
    if media is None:
        return None

    photo = getattr(media, "photo", None)
    document = getattr(media, "document", None)

    if photo is not None:
        photo_id = getattr(photo, "id", None)
        if photo_id is not None:
            return str(Path(media_dir) / f"{photo_id}.jpg")

    if document is not None:
        doc_id = getattr(document, "id", None)
        if doc_id is None:
            return None

        # 優先從 DocumentAttributeFilename 取原始副檔名
        try:
            from telethon.tl.types import DocumentAttributeFilename
            for attr in getattr(document, "attributes", []):
                if isinstance(attr, DocumentAttributeFilename):
                    orig_ext = Path(attr.file_name).suffix
                    if orig_ext:
                        return str(Path(media_dir) / f"{doc_id}{orig_ext}")
        except Exception:
            pass

        # 從 mime type 推導
        mime = getattr(document, "mime_type", "") or ""
        ext = _ext_from_mime(mime)
        return str(Path(media_dir) / f"{doc_id}{ext}")

    return None


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
        elif mime_type and mime_type.startswith("audio/"):
            media_type = "audio"
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


_chat_title_cache: dict[int, str | None] = {}


async def _resolve_chat_title(client: Any, chat_id: int | None) -> str | None:
    """解析頻道顯示名稱，結果快取避免重複 API 呼叫。"""
    if not chat_id:
        return None
    if chat_id in _chat_title_cache:
        return _chat_title_cache[chat_id]
    title: str | None = None
    try:
        entity = await client.get_entity(chat_id)
        title = getattr(entity, "title", None) or getattr(entity, "username", None)
    except Exception:
        pass
    _chat_title_cache[chat_id] = title
    return title


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
) -> bool:
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
        return False

    # 先經過略過判斷後，剩下的是允許通過的轉發訊息，再補來源 chat_id 到白名單
    if is_forward_message and allow_forward_here:
        source_chat_id = extract_forward_source_chat_id(message)
        added = add_identifier_to_forward_whitelist(config.runtime_config_path, source_chat_id or "")
        if added:
            runtime_watcher.refresh(force=True)
            print(f"[{log_prefix}] 已自動加入 forward 白名單來源 chat_id={source_chat_id}")

    text = raw_text or ""
    has_media = bool(message.media)

    # 解析頻道顯示名稱（title 或 username），供 relay 端作為 embed title
    resolved_chat_title = await _resolve_chat_title(client, chat_id)

    if log_prefix == "History":
        print(f"[History] source_channel={config.source_channel} message_id={message.id} has_media={has_media} text={text}")
    else:
        print(f"[{log_prefix}] chat_id={chat_id} message_id={message.id} has_media={has_media} text={text}")

    # 取得 Telegram media group ID（同一相簿的訊息共享此值）
    raw_grouped_id = getattr(message, "grouped_id", None)
    grouped_id = int(raw_grouped_id) if raw_grouped_id else None

    # 1. 先 upsert 訊息（取得 pk 與是否新增）
    message_pk, inserted_new = await db.upsert_message_only(
        telegram_chat_id=int(chat_id or 0),
        telegram_message_id=int(message.id),
        text=text,
        message_date=message.date,
        has_media=has_media,
        chat_title=resolved_chat_title,
        grouped_id=grouped_id,
    )

    # 2. 媒體下載（僅在需要時：新訊息 或 尚無媒體記錄）
    if has_media and runtime_snapshot.download_media:
        need_download = inserted_new or not await db.has_media_records(message_pk)
        if need_download:
            # 使用穩定檔名（依 photo/document ID），避免重啟產生 (N) 後綴
            target_path = _build_stable_media_path(message, runtime_snapshot.media_dir)
            file_path = await client.download_media(message, file=target_path or runtime_snapshot.media_dir)
            print(f"[{log_prefix}] 媒體已下載: {file_path}")
            media_items: list[dict] = []
            if file_path:
                file_rel_path = _to_shared_media_rel_path(str(file_path), runtime_snapshot.media_dir)
                media_items.append(_build_media_item(message, file_rel_path))
            await db.upsert_media_items(message_pk, media_items)
        else:
            print(f"[{log_prefix}] 媒體已存在，略過下載 message_pk={message_pk}")

    # 3. 通知（僅新訊息才 NOTIFY）
    if inserted_new:
        await db.notify_new_message(message_pk)
        print(f"[{log_prefix}] DB 新增訊息成功 message_pk={message_pk}")
    else:
        print(f"[{log_prefix}] DB 已存在訊息（略過重複）message_pk={message_pk}")

    return True


async def handle_new_message(
    event: Any,
    client: Any,
    config: TelegramConfig,
    runtime_watcher: TelegramRuntimeConfigWatcher,
    db: TelegramDatabase,
) -> bool:
    """處理即時新訊息事件。"""
    if not event.message:
        return False
    return await _process_message(
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
) -> bool:
    """處理歷史訊息。"""
    return await _process_message(
        message=msg,
        chat_id=msg.chat_id,
        raw_text=msg.message or "",
        client=client,
        config=config,
        runtime_watcher=runtime_watcher,
        db=db,
        log_prefix="History",
    )
