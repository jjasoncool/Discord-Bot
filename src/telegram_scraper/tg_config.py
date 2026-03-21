import json
import os
from dataclasses import dataclass, field
from typing import Any


def normalize_channel_identifier(value: str) -> str:
    """把頻道識別值正規化為 Telethon 可用格式。"""
    value = value.strip()
    value = value.replace("https://t.me/s/", "")
    value = value.replace("https://t.me/", "")
    return value.strip("/")


def _load_required_env(name: str) -> str:
    """讀取必要環境變數，若缺少就直接拋錯。"""
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"缺少必要環境變數: {name}")
    return value


def _to_bool(value: str) -> bool:
    """將字串環境變數轉為布林值。"""
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _parse_csv_set(value: str) -> set[str]:
    """將逗號分隔字串轉為集合，並做基本正規化。"""
    result: set[str] = set()
    for part in value.split(","):
        item = part.strip()
        if not item:
            continue
        result.add(normalize_channel_identifier(item).lower())
    return result


def _parse_whitelist(value: Any) -> set[str]:
    """解析白名單設定，支援字串或陣列。"""
    if isinstance(value, list):
        result: set[str] = set()
        for item in value:
            text = str(item).strip()
            if not text:
                continue
            result.add(normalize_channel_identifier(text).lower())
        return result

    return _parse_csv_set(str(value))


def _load_runtime_json_config(path: str) -> dict[str, Any]:
    """讀取 Telegram runtime JSON 設定檔。"""
    if not os.path.exists(path):
        return {}

    with open(path, "r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise RuntimeError("Telegram runtime 設定檔格式錯誤：根節點必須是 JSON 物件")

    return data


def add_identifier_to_forward_whitelist(runtime_config_path: str, identifier: str) -> bool:
    """將識別值寫入 runtime_config.json 的 forward 白名單。

    回傳值：
    - True: 本次有新增
    - False: 原本就存在
    """
    data = _load_runtime_json_config(runtime_config_path)

    current = data.get("forward_whitelist", [])
    current_set = _parse_whitelist(current)

    identifier_text = normalize_channel_identifier(str(identifier)).lower()
    if not identifier_text:
        return False

    if identifier_text in current_set:
        return False

    # 寫入 JSON 時保留陣列格式，方便人工維護
    if isinstance(current, list):
        new_list = [str(item) for item in current if str(item).strip()]
    else:
        new_list = [item for item in sorted(current_set) if item]

    new_list.append(identifier_text)
    data["forward_whitelist"] = new_list

    with open(runtime_config_path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)
        file.write("\n")

    return True


@dataclass(slots=True)
class TelegramConfig:
    api_id: int
    api_hash: str
    session_dir: str = "session"
    session_name: str = "telegram_scraper"
    test_channel: str = "Seele_WW_leak"
    history_limit: int = 5
    history_hours: int | None = None
    download_media: bool = False
    media_dir: str = "media"
    skip_forwards: bool = True
    forward_whitelist: set[str] = field(default_factory=set)
    runtime_config_path: str = "runtime_config.json"


def load_config_from_env() -> TelegramConfig:
    """從環境變數讀取設定並回傳型別化物件。"""
    api_id_str = _load_required_env("TELEGRAM_API_ID")
    api_hash = _load_required_env("TELEGRAM_API_HASH")

    try:
        api_id = int(api_id_str)
    except ValueError as exc:
        raise RuntimeError("TELEGRAM_API_ID 必須是整數") from exc

    runtime_config_path = "runtime_config.json"
    runtime_json = _load_runtime_json_config(runtime_config_path)

    test_channel_raw = os.getenv("TELEGRAM_TEST_CHANNEL", "Seele_WW_leak").strip()
    history_limit = int(os.getenv("TELEGRAM_TEST_LIMIT", "5"))
    history_hours_raw = runtime_json.get("history_hours", None)
    history_hours: int | None
    if history_hours_raw is None or str(history_hours_raw).strip() == "":
        history_hours = None
    else:
        history_hours = int(history_hours_raw)
        if history_hours <= 0:
            history_hours = None

    download_media = _to_bool(os.getenv("TELEGRAM_DOWNLOAD_MEDIA", "false"))
    media_dir = os.getenv("TELEGRAM_MEDIA_DIR", "media").strip() or "media"
    skip_forwards_raw = runtime_json.get("skip_forwards", True)
    skip_forwards = _to_bool(str(skip_forwards_raw))

    whitelist_raw = runtime_json.get("forward_whitelist", [])
    forward_whitelist = _parse_whitelist(whitelist_raw)

    session_dir = os.getenv("TELEGRAM_SESSION_DIR", "session").strip() or "session"
    session_name = os.getenv("TELEGRAM_SESSION_NAME", "telegram_scraper").strip() or "telegram_scraper"

    return TelegramConfig(
        api_id=api_id,
        api_hash=api_hash,
        session_dir=session_dir,
        session_name=session_name,
        test_channel=normalize_channel_identifier(test_channel_raw),
        history_limit=history_limit,
        history_hours=history_hours,
        download_media=download_media,
        media_dir=media_dir,
        skip_forwards=skip_forwards,
        forward_whitelist=forward_whitelist,
        runtime_config_path=runtime_config_path,
    )
