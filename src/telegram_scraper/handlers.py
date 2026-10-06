import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from db import TelegramDatabase
from filters import (
    extract_forward_source_chat_id,
    is_forward_source_a_primary,
    is_forward_source_in_whitelist,
    should_skip_forward,
)
from media_download import MEDIA_HOLD_NOTIFY, MEDIA_RETRY_WINDOW, download_with_stall_guard
from tg_config import TelegramConfig, TelegramRuntimeConfigWatcher, add_identifier_to_forward_whitelist

logger = logging.getLogger(__name__)


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
        # spoiler 旗標在 media 物件上（MessageMediaPhoto/MessageMediaDocument.spoiler），
        # 不在 message 上。原本讀的 message.media_unread 是「媒體尚未被檢視」（語音/圓形
        # 影片用），與防雷完全無關，導致所有媒體都被記成非 spoiler。
        "is_spoiler": bool(getattr(media, "spoiler", False)),
    }


def _serialize_entities(message: Any) -> list[dict] | None:
    """把 Telethon 的 message.entities 序列化成 JSON 友善的 list。

    保留所有 entity（不只 spoiler），讓 relay 端日後可擴充支援 bold/italic 等格式。
    offset/length 沿用 Telegram 原語意（UTF-16 code units）。
    """
    entities = getattr(message, "entities", None) or []
    if not entities:
        return None
    serialized: list[dict] = []
    for ent in entities:
        offset = getattr(ent, "offset", None)
        length = getattr(ent, "length", None)
        if offset is None or length is None:
            continue
        item: dict = {
            "type": type(ent).__name__,
            "offset": int(offset),
            "length": int(length),
        }
        # 內嵌自訂表情（premium custom emoji）額外保留 document_id，
        # relay 端才有辦法把它換成對應的 Discord App Emoji。
        doc_id = getattr(ent, "document_id", None)
        if doc_id is not None:
            try:
                item["document_id"] = int(doc_id)
            except (TypeError, ValueError):
                pass
        serialized.append(item)
    return serialized or None


async def _download_custom_emojis(
    *,
    message_pk: int,
    entities: list[dict] | None,
    client: Any,
    media_dir: str,
    db: TelegramDatabase,
    log_prefix: str,
) -> None:
    """下載訊息內嵌的自訂表情檔（webp/tgs/webm）到共用 media 目錄。

    以 document_id 去重（已下載過就跳過），並在下載後把帶 document_id 的
    entities 覆寫回該訊息，確保 relay 讀得到 document_id。
    """
    if not entities:
        return

    doc_ids: list[int] = []
    for ent in entities:
        if isinstance(ent, dict) and ent.get("type") == "MessageEntityCustomEmoji":
            did = ent.get("document_id")
            if did is not None and int(did) not in doc_ids:
                doc_ids.append(int(did))
    if not doc_ids:
        return

    # 先把 entities（含 document_id）回填，即使表情已下載過也要確保 DB 有 document_id
    try:
        await db.update_message_entities(message_pk, entities)
    except Exception as exc:
        logger.warning(f"[{log_prefix}] 回填 entities 失敗 message_pk={message_pk}: {exc}")

    known = await db.get_known_emoji_ids(doc_ids)
    todo = [d for d in doc_ids if d not in known]
    if not todo:
        return

    try:
        from telethon.tl.functions.messages import GetCustomEmojiDocumentsRequest
        documents = await client(GetCustomEmojiDocumentsRequest(document_id=todo))
    except Exception as exc:
        logger.warning(f"[{log_prefix}] 取自訂表情 document 失敗 ids={todo}: {exc}")
        return

    for doc in documents or []:
        doc_id = int(getattr(doc, "id", 0) or 0)
        if not doc_id:
            continue
        mime = getattr(doc, "mime_type", "") or ""
        is_animated = mime == "application/x-tgsticker" or mime.startswith("video/")
        target_path = os.path.join(media_dir, f"emoji_{doc_id}{_ext_from_mime(mime)}")
        try:
            file_path = await download_with_stall_guard(client, doc, file=target_path)
        except Exception as exc:
            logger.warning(f"[{log_prefix}] 下載自訂表情失敗 doc_id={doc_id}: {exc}")
            continue
        rel_path = _to_shared_media_rel_path(str(file_path), media_dir) if file_path else None
        try:
            await db.upsert_custom_emoji(
                document_id=doc_id,
                file_rel_path=rel_path,
                mime_type=mime,
                is_animated=is_animated,
            )
        except Exception as exc:
            logger.warning(f"[{log_prefix}] 寫入自訂表情記錄失敗 doc_id={doc_id}: {exc}")
        else:
            logger.info(f"[{log_prefix}] 自訂表情已下載 doc_id={doc_id} animated={is_animated} path={rel_path}")


#: Telethon 挑照片尺寸時會先去掉這兩種：空殼，和只有輪廓向量的 PhotoPathSize（只剩它時下載會出錯）
_UNDOWNLOADABLE_PHOTO_SIZES = frozenset({"PhotoSizeEmpty", "PhotoPathSize"})


def _usable_photo(photo: Any) -> bool:
    """照片要有至少一個真的能下載的尺寸（PhotoEmpty 沒有尺寸）。"""
    sizes = getattr(photo, "sizes", None) or []
    return any(type(size).__name__ not in _UNDOWNLOADABLE_PHOTO_SIZES for size in sizes)


def _usable_document(document: Any) -> bool:
    """文件要有大小（DocumentEmpty 這類空殼沒有）。"""
    return getattr(document, "size", None) is not None


def _downloadable_media(message: Any) -> Any | None:
    """這則訊息裡「download_media 真的會下載到檔案」的媒體物件；沒有就回 None。

    照 Telethon download_media 依外層型別分派：照片、文件、網頁預覽（取 `document or photo`）；
    其他型別（帳單、投票、地點……）一律不算。聯絡人 Telethon 會產生 vCard 檔，這裡刻意不算：
    轉發到 Discord 沒有意義。只有 video_sizes、沒有一般尺寸的照片也不算（極少見）。以前用 `bool(message.media)` 判斷有沒有圖，
    沒附圖的網頁預覽、過期照片、投票等也被標成有圖，卻永遠下載不到；資料庫的「有圖」只會由否變是，
    轉發端的相簿就一直等這張圖（2026-10-05 查到 24 筆）。
    """
    media = getattr(message, "media", None)
    if media is None:
        return None
    kind = type(media).__name__
    if kind == "MessageMediaPhoto":
        photo = getattr(media, "photo", None)
        return photo if _usable_photo(photo) else None
    if kind == "MessageMediaDocument":
        document = getattr(media, "document", None)
        return document if _usable_document(document) else None
    if kind == "MessageMediaWebPage":
        page = getattr(media, "webpage", None)
        # Telethon 取 `document or photo`：文件是空殼（DocumentEmpty 也算真值）時不會改抓照片
        target = getattr(page, "document", None) or getattr(page, "photo", None)
        if target is not None and (_usable_document(target) or _usable_photo(target)):
            return target
    return None


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


def _message_age(message: Any) -> timedelta:
    """發文到現在多久。沒有時間的當作剛發。"""
    date = getattr(message, "date", None)
    if date is None:
        return timedelta(0)
    if date.tzinfo is None:
        date = date.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - date


def _within_retry_window(message: Any) -> bool:
    """發文時間在補圖時限內（見 media_download.MEDIA_RETRY_WINDOW）。"""
    return _message_age(message) <= MEDIA_RETRY_WINDOW


#: 「先壓著」的訊息已經在滿 30 分鐘時通知過的 pk（每則只放行一次；有上限，爬蟲重啟就清空，
#: 重啟後最多多通知一次，轉發端有去重）
_hold_released: dict[int, None] = {}
_HOLD_RELEASED_MAX = 5000


def _mark_hold_released(message_pk: int) -> bool:
    """記下這則已放行；回傳是不是第一次。"""
    if message_pk in _hold_released:
        return False
    _hold_released[message_pk] = None
    if len(_hold_released) > _HOLD_RELEASED_MAX:
        _hold_released.pop(next(iter(_hold_released)))
    return True


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
    source_label: str | None = None,
) -> bool:
    """處理共用訊息流程（forward 過濾、白名單補齊、媒體處理）。"""
    runtime_snapshot = runtime_watcher.get_snapshot()

    is_forward_message = bool(message.fwd_from)

    # 跨來源去重（優先於白名單）：若這是一則轉發、且原始來源本身也是我們直接監聽的
    # 主頻，就丟掉——那則內容會從它自己的主頻直接進來，避免同性質頻道互轉造成重複。
    # 不排除「當前抓取頻道」本身，保持雙向去重（A 轉 B、B 轉 A 都濾）；副作用是頻道
    # 轉發自家舊文也會被視為重複略過，屬可接受。被此判濾掉者不進白名單、不 auto-add。
    if is_forward_message:
        primary_sources = {name.lower() for name in config.source_channels if name}
        if primary_sources and await is_forward_source_a_primary(
            client=client,
            message=message,
            primary_sources=primary_sources,
        ):
            logger.info(f"[{log_prefix}] 略過主頻轉發（去重）message_id={message.id}")
            return False

    allow_forward_here = await is_forward_source_in_whitelist(
        client=client,
        message=message,
        forward_whitelist=runtime_snapshot.forward_whitelist,
    )

    if should_skip_forward(is_forward_message, runtime_snapshot.skip_forwards, allow_forward_here):
        logger.info(f"[{log_prefix}] 略過轉發訊息 message_id={message.id}")
        return False

    # 先經過略過判斷後，剩下的是允許通過的轉發訊息，再補來源 chat_id 到白名單
    if is_forward_message and allow_forward_here:
        source_chat_id = extract_forward_source_chat_id(message)
        added = add_identifier_to_forward_whitelist(config.runtime_config_path, source_chat_id or "")
        if added:
            runtime_watcher.refresh(force=True)
            logger.info(f"[{log_prefix}] 已自動加入 forward 白名單來源 chat_id={source_chat_id}")

    text = raw_text or ""
    has_media = _downloadable_media(message) is not None
    if message.media is not None and not has_media:
        media_type = type(message.media).__name__
        # 沒附圖的網頁預覽很常見，記 INFO；其他看不懂的型別記 WARNING，下次再出現時才知道是什麼
        level = logging.INFO if media_type == "MessageMediaWebPage" else logging.WARNING
        logger.log(level, f"[{log_prefix}] 媒體沒有可下載的檔案，當成純文字 message_id={message.id} type={media_type}")

    # 解析頻道顯示名稱（title 或 username），供 relay 端作為 embed title
    resolved_chat_title = await _resolve_chat_title(client, chat_id)

    if source_label:
        # 逐頻道掃描（History / CatchUp）用實際來源頻道標示，不能用 config.source_channel——
        # 那是多來源設定的第一個頻道，會把其他頻道的訊息全標成它，除錯時嚴重誤導。
        logger.info(f"[{log_prefix}] source_channel={source_label} message_id={message.id} has_media={has_media} text={text}")
    else:
        logger.info(f"[{log_prefix}] chat_id={chat_id} message_id={message.id} has_media={has_media} text={text}")

    # 取得 Telegram media group ID（同一相簿的訊息共享此值）
    raw_grouped_id = getattr(message, "grouped_id", None)
    grouped_id = int(raw_grouped_id) if raw_grouped_id else None

    # 解析 message entities（spoiler、bold 等）以便 relay 端還原 Discord markdown
    entities = _serialize_entities(message)

    # 1. 先 upsert 訊息（取得 pk 與是否新增）
    message_pk, inserted_new = await db.upsert_message_only(
        telegram_chat_id=int(chat_id or 0),
        telegram_message_id=int(message.id),
        text=text,
        message_date=message.date,
        has_media=has_media,
        chat_title=resolved_chat_title,
        grouped_id=grouped_id,
        entities=entities,
    )

    # 2. 媒體下載（僅在需要時：新訊息 或 尚無媒體記錄）
    # media_landed：這次真的補進了媒體列。訊息早就存在、這次才補到圖時，要再通知轉發端（見步驟 3）
    # download_failed：這次有試著下載、卻沒拿到圖（步驟 3 決定要不要先壓著不通知）
    media_landed = False
    download_failed = False
    if has_media and runtime_snapshot.download_media:
        need_download = inserted_new or not await db.has_media_records(message_pk)
        if need_download:
            # 使用穩定檔名（依 photo/document ID），避免重啟產生 (N) 後綴
            target_path = _build_stable_media_path(message, runtime_snapshot.media_dir)
            file_path = None
            try:
                file_path = await download_with_stall_guard(
                    client, message, file=target_path or runtime_snapshot.media_dir)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # 攔下來、不往外拋：訊息照樣入庫（要不要通知轉發端見步驟 3：新訊息先壓著）；補掃會在發文後 12 小時內重試。
                # 以前沒攔，即時事件只留下沒圖的訊息列，啟動的歷史掃描則會讓整個爬蟲當掉、陷入重啟迴圈。
                # dc_id：同一個資料中心連續卡住時，多半是那條連線壞了（Telethon 不會自己換），要重啟爬蟲
                logger.warning(
                    f"[{log_prefix}] 媒體下載失敗（補掃會在 12 小時內重試）"
                    f"message_id={message.id} type={type(message.media).__name__} "
                    f"dc_id={getattr(_downloadable_media(message), 'dc_id', None)}: {exc!r}"
                )
            else:
                if file_path:
                    logger.info(f"[{log_prefix}] 媒體已下載: {file_path}")
                else:
                    logger.warning(
                        f"[{log_prefix}] 媒體下載沒有拿到檔案 message_id={message.id} type={type(message.media).__name__}"
                    )
            media_items: list[dict] = []
            if file_path:
                file_rel_path = _to_shared_media_rel_path(str(file_path), runtime_snapshot.media_dir)
                media_items.append(_build_media_item(message, file_rel_path))
            await db.upsert_media_items(message_pk, media_items)
            media_landed = bool(media_items)
            download_failed = not media_landed
        else:
            logger.info(f"[{log_prefix}] 媒體已存在，略過下載 message_pk={message_pk}")
            # 檔案在就不重抓，但 spoiler 旗標仍要校正——早期版本讀錯欄位（media_unread），
            # 舊資料全被記成非 spoiler，不在這裡回填就永遠錯下去。
            if await db.update_media_spoiler(message_pk, bool(getattr(message.media, "spoiler", False))):
                logger.info(f"[{log_prefix}] 已校正 spoiler 旗標 message_pk={message_pk}")

    # 2.5 下載內嵌自訂表情（premium custom emoji），供 relay 轉成 Discord App Emoji。
    # 只在「即時新訊息」與「on-demand 重抓」時做；啟動歷史掃描（History）刻意跳過，
    # 避免第一次重啟把全頻道歷史表情都抓一遍拖慢啟動 / 撞 Telegram rate limit。
    if entities and log_prefix != "History":
        try:
            await _download_custom_emojis(
                message_pk=message_pk,
                entities=entities,
                client=client,
                media_dir=runtime_snapshot.media_dir,
                db=db,
                log_prefix=log_prefix,
            )
        except Exception as exc:
            logger.exception(f"[{log_prefix}] 處理自訂表情時發生例外 message_pk={message_pk}: {exc}")

    # 3. 通知轉發端
    # /resend_article 的重抓（Refetch）只照舊「新訊息才通知」：它自己會送，這裡多通知會重複貼文
    age = _message_age(message)
    hold = (
        download_failed and log_prefix != "Refetch"
        and runtime_snapshot.catchup_interval_min > 0 and age < MEDIA_HOLD_NOTIFY
    )
    if inserted_new and hold:
        # 新訊息的圖第一次沒下載到：先不通知，等補掃（每輪重試）補到圖再通知，文字和圖一起送成一則。
        # 轉發端的單則不等圖，這裡就通知的話文字會先送出、之後補到的圖再也送不出去。
        # 補掃關掉時不壓（沒有人會再試）；發文已超過 30 分鐘的（漏收後才補進來的）也不壓，等待時間已經過了。
        logger.info(
            f"[{log_prefix}] 圖還沒下載到，先不通知轉發端（補到圖才通知；有文字的單則發文滿 30 分鐘先送文字）"
            f"message_pk={message_pk}"
        )
    elif inserted_new:
        await db.notify_new_message(message_pk)
        logger.info(f"[{log_prefix}] DB 新增訊息成功 message_pk={message_pk}")
        if download_failed:
            # 沒圖就已經通知過（沒壓）：之後重試又失敗時不必再「放行」通知一次
            _mark_hold_released(message_pk)
    elif log_prefix != "Refetch" and _within_retry_window(message) and media_landed:
        # 訊息早就在、這次才補到圖：以前不通知，轉發端只有重啟時才知道（圖因此沒送出）。
        # 只在發文後 12 小時內通知（超過轉發端本來就不補送）；重掃本來就完整的訊息不會走到這裡。
        await db.notify_new_message(message_pk)
        logger.info(f"[{log_prefix}] 補到媒體，通知轉發端 message_pk={message_pk}")
    elif (
        log_prefix != "Refetch" and _within_retry_window(message) and download_failed
        and age >= MEDIA_HOLD_NOTIFY and text.strip() and grouped_id is None
        and _mark_hold_released(message_pk)
    ):
        # 壓著的「有文字的單則」發文滿 30 分鐘還是沒補到圖：通知一次，讓文字先送；之後補到圖仍會再通知。
        # 沒文字的單則和相簿組員不放行：轉發端會把沒文字的當空訊息略過並記成處理過（之後補到的圖要等
        # bot 重啟才送），相簿只送已經有圖的組員（放行只會讓它白等）——它們繼續壓著，等補到圖再通知。
        await db.notify_new_message(message_pk)
        logger.info(f"[{log_prefix}] 圖等滿 30 分鐘還沒下載到，先通知轉發端送文字 message_pk={message_pk}")
    else:
        logger.info(f"[{log_prefix}] DB 已存在訊息（略過重複）message_pk={message_pk}")

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
    source_label: str | None = None,
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
        source_label=source_label,
    )


async def handle_catchup_message(
    msg: Any,
    client: Any,
    config: TelegramConfig,
    runtime_watcher: TelegramRuntimeConfigWatcher,
    db: TelegramDatabase,
    source_label: str | None = None,
) -> bool:
    """處理週期性補掃撈到的訊息。

    與 History 的差別：補掃到的是「本該即時收到卻漏掉」的訊息，等同新訊息，
    因此不跳過內嵌自訂表情下載（log_prefix 非 History 即會下載），確保 relay
    轉出去時表情能正常對應到 Discord App Emoji。
    """
    return await _process_message(
        message=msg,
        chat_id=msg.chat_id,
        raw_text=msg.message or "",
        client=client,
        config=config,
        runtime_watcher=runtime_watcher,
        db=db,
        log_prefix="CatchUp",
        source_label=source_label,
    )


async def handle_refetch_message(
    msg: Any,
    chat_id: int | None,
    client: Any,
    config: TelegramConfig,
    runtime_watcher: TelegramRuntimeConfigWatcher,
    db: TelegramDatabase,
) -> bool:
    """處理 on-demand 重抓（relay 透過 pg NOTIFY 觸發）。

    走與一般訊息相同的 _process_message，重點在補齊/回填內嵌自訂表情。
    """
    resolved_chat_id = getattr(msg, "chat_id", None) or chat_id
    return await _process_message(
        message=msg,
        chat_id=resolved_chat_id,
        raw_text=getattr(msg, "message", "") or "",
        client=client,
        config=config,
        runtime_watcher=runtime_watcher,
        db=db,
        log_prefix="Refetch",
    )
