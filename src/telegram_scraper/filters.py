from typing import Any

from telethon.utils import get_peer_id

from tg_config import normalize_channel_identifier


def extract_forward_source_chat_id(message: Any) -> str | None:
    """從轉發資訊嘗試提取來源 chat_id（字串）。"""
    fwd = getattr(message, "fwd_from", None)
    if not fwd:
        return None

    # 優先使用 from_id（可直接轉成 Telegram 標準 peer id）
    from_id = getattr(fwd, "from_id", None)
    if from_id is not None:
        try:
            return str(get_peer_id(from_id)).lower()
        except Exception:
            pass

    # 後備：某些情況只有 channel_id
    channel_id = getattr(fwd, "channel_id", None)
    if channel_id is not None:
        try:
            # Telethon 慣例：Channel peer id 為 -100 開頭
            return str(-1000000000000 + int(channel_id)).lower()
        except Exception:
            return str(channel_id).lower()

    return None


async def is_forward_source_in_whitelist(
    client: Any,
    message: Any,
    forward_whitelist: set[str],
) -> bool:
    """判斷「轉發來源」是否在 forward 白名單。"""
    fwd = getattr(message, "fwd_from", None)
    if not fwd:
        return False

    if not forward_whitelist:
        return False

    candidates: set[str] = set()

    source_chat_id = extract_forward_source_chat_id(message)
    if source_chat_id:
        candidates.add(source_chat_id)

    # 轉發來源名稱（可能是 from_name）
    from_name = getattr(fwd, "from_name", None)
    if from_name:
        candidates.add(normalize_channel_identifier(str(from_name)).lower())

    # 盡量補齊 username/title 作比對
    try:
        resolve_target = getattr(fwd, "from_id", None) or getattr(fwd, "channel_id", None)
        entity = await client.get_entity(resolve_target) if resolve_target is not None else None
        if entity is not None:
            username = getattr(entity, "username", None)
            title = getattr(entity, "title", None)
            if username:
                candidates.add(str(username).lower())
            if title:
                candidates.add(str(title).lower())

            try:
                candidates.add(str(get_peer_id(entity)).lower())
            except Exception:
                pass
    except Exception:
        # 取 entity 失敗時不影響主流程，沿用既有候選值
        pass

    return bool(candidates & forward_whitelist)


def should_skip_forward(is_forward_message: bool, skip_forwards: bool, allow_forward_here: bool) -> bool:
    """統一判斷是否要略過轉發訊息。"""
    return skip_forwards and is_forward_message and not allow_forward_here
