from typing import Any

from filters import extract_forward_source_chat_id, is_forward_source_in_whitelist, should_skip_forward
from tg_config import TelegramConfig, add_identifier_to_forward_whitelist


async def _process_message(
    *,
    message: Any,
    chat_id: int | None,
    raw_text: str,
    client: Any,
    config: TelegramConfig,
    log_prefix: str,
) -> None:
    """處理共用訊息流程（forward 過濾、白名單補齊、媒體處理）。"""
    is_forward_message = bool(message.fwd_from)
    allow_forward_here = await is_forward_source_in_whitelist(
        client=client,
        message=message,
        forward_whitelist=config.forward_whitelist,
    )

    if should_skip_forward(is_forward_message, config.skip_forwards, allow_forward_here):
        print(f"[{log_prefix}] 略過轉發訊息 message_id={message.id}")
        return

    # 先經過略過判斷後，剩下的是允許通過的轉發訊息，再補來源 chat_id 到白名單
    if is_forward_message and allow_forward_here:
        source_chat_id = extract_forward_source_chat_id(message)
        added = add_identifier_to_forward_whitelist(config.runtime_config_path, source_chat_id or "")
        if added:
            config.forward_whitelist.add(str(source_chat_id).lower())
            print(f"[{log_prefix}] 已自動加入 forward 白名單來源 chat_id={source_chat_id}")

    text = raw_text or ""
    has_media = bool(message.media)

    if log_prefix == "History":
        print(f"[History] chat={config.test_channel} message_id={message.id} has_media={has_media} text={text}")
    else:
        print(f"[{log_prefix}] chat_id={chat_id} message_id={message.id} has_media={has_media} text={text}")

    if has_media and config.download_media:
        file_path = await client.download_media(message, file=config.media_dir)
        print(f"[{log_prefix}] 媒體已下載: {file_path}")


async def handle_new_message(event: Any, client: Any, config: TelegramConfig) -> None:
    """處理即時新訊息事件。"""
    if not event.message:
        return
    await _process_message(
        message=event.message,
        chat_id=event.chat_id,
        raw_text=event.raw_text or "",
        client=client,
        config=config,
        log_prefix="Telegram",
    )


async def handle_history_message(msg: Any, client: Any, config: TelegramConfig) -> None:
    """處理歷史訊息。"""
    await _process_message(
        message=msg,
        chat_id=msg.chat_id,
        raw_text=msg.message or "",
        client=client,
        config=config,
        log_prefix="History",
    )
