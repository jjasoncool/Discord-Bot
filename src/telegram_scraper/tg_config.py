import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus


def normalize_channel_identifier(value: str) -> str:
    """把頻道識別值正規化為 Telethon 可用格式。"""
    value = value.strip()
    value = value.replace("https://t.me/s/", "")
    value = value.replace("https://t.me/", "")
    value = value.strip("/")
    if value.startswith("@"):
        value = value[1:]
    return value


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
    source_channel: str = "Seele_WW_leak"
    history_limit: int = 5
    history_hours: int | None = None
    download_media: bool = False
    media_dir: str = "media"
    skip_forwards: bool = True
    forward_whitelist: set[str] = field(default_factory=set)
    runtime_config_path: str = "runtime_config.json"
    pg_host: str = "pgvector"
    pg_port: int = 5432
    pg_db: str = "telegram_data"
    pg_user: str = ""
    pg_password: str = ""
    pg_notify_channel: str = "telegram_new_message"

    def build_admin_dsn(self) -> str:
        """組出管理用 DSN（連到 postgres maintenance DB，用於建 DB）。"""
        encoded_user = quote_plus(self.pg_user)
        encoded_password = quote_plus(self.pg_password)
        return (
            f"postgresql://{encoded_user}:{encoded_password}"
            f"@{self.pg_host}:{self.pg_port}/postgres"
        )

    def build_asyncpg_dsn(self) -> str:
        """組出 asyncpg 連線字串。"""
        encoded_user = quote_plus(self.pg_user)
        encoded_password = quote_plus(self.pg_password)
        return (
            f"postgresql://{encoded_user}:{encoded_password}"
            f"@{self.pg_host}:{self.pg_port}/{self.pg_db}"
        )


@dataclass(slots=True, frozen=True)
class TelegramRuntimeConfigSnapshot:
    """Telegram runtime_config.json 的快照。"""

    history_hours: int | None
    skip_forwards: bool
    forward_whitelist: set[str]
    download_media: bool
    media_dir: str


class TelegramRuntimeConfigWatcher:
    """runtime_config.json 變更監聽（polling + 快取）。"""

    def __init__(
        self,
        runtime_config_path: str,
        fallback_config: TelegramConfig,
        refresh_interval_sec: float = 2.0,
    ) -> None:
        self.runtime_config_path = runtime_config_path
        self.fallback_config = fallback_config
        self.refresh_interval_sec = max(refresh_interval_sec, 0.2)

        self._last_mtime: float | None = None
        self._last_checked_at: float = 0.0
        self._snapshot = TelegramRuntimeConfigSnapshot(
            history_hours=fallback_config.history_hours,
            skip_forwards=fallback_config.skip_forwards,
            forward_whitelist=set(fallback_config.forward_whitelist),
            download_media=fallback_config.download_media,
            media_dir=fallback_config.media_dir,
        )

        # 初始化先強制同步一次
        self.refresh(force=True)

    def _build_snapshot_from_runtime_json(self, runtime_json: dict[str, Any]) -> TelegramRuntimeConfigSnapshot:
        """把 runtime JSON 與 fallback 設定合併成快照。"""
        history_hours_raw = runtime_json.get("history_hours", self.fallback_config.history_hours)
        history_hours: int | None
        if history_hours_raw is None or str(history_hours_raw).strip() == "":
            history_hours = None
        else:
            try:
                history_hours = int(history_hours_raw)
                if history_hours <= 0:
                    history_hours = None
            except (TypeError, ValueError):
                history_hours = self.fallback_config.history_hours

        skip_forwards = _to_bool(str(runtime_json.get("skip_forwards", self.fallback_config.skip_forwards)))
        forward_whitelist = _parse_whitelist(runtime_json.get("forward_whitelist", self.fallback_config.forward_whitelist))
        download_media = _to_bool(str(runtime_json.get("download_media", self.fallback_config.download_media)))
        media_dir = str(runtime_json.get("media_dir", self.fallback_config.media_dir)).strip() or self.fallback_config.media_dir

        return TelegramRuntimeConfigSnapshot(
            history_hours=history_hours,
            skip_forwards=skip_forwards,
            forward_whitelist=forward_whitelist,
            download_media=download_media,
            media_dir=media_dir,
        )

    def refresh(self, force: bool = False) -> TelegramRuntimeConfigSnapshot:
        """依檔案 mtime 決定是否重新載入，回傳最新快照。"""
        now = time.monotonic()
        if not force and (now - self._last_checked_at) < self.refresh_interval_sec:
            return self._snapshot

        self._last_checked_at = now
        path = Path(self.runtime_config_path)
        mtime = path.stat().st_mtime if path.exists() else None
        if not force and mtime == self._last_mtime:
            return self._snapshot

        try:
            runtime_json = _load_runtime_json_config(self.runtime_config_path)
            self._snapshot = self._build_snapshot_from_runtime_json(runtime_json)
            self._last_mtime = mtime
            print("[Telegram] runtime_config.json 已重新載入（watcher）")
        except Exception as exc:
            print(f"[Telegram] runtime_config.json 重新載入失敗，沿用舊快照: {exc}")

        return self._snapshot

    def get_snapshot(self) -> TelegramRuntimeConfigSnapshot:
        """取得目前快照（必要時自動 refresh）。"""
        return self.refresh(force=False)


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

    source_channel_raw = str(
        runtime_json.get("source_channel", os.getenv("TELEGRAM_SOURCE_CHANNEL", "Seele_WW_leak"))
    ).strip()
    try:
        history_limit = max(0, int(runtime_json.get("history_limit", 0)))
    except (TypeError, ValueError):
        history_limit = 0
    history_hours_raw = runtime_json.get("history_hours", None)
    history_hours: int | None
    if history_hours_raw is None or str(history_hours_raw).strip() == "":
        history_hours = None
    else:
        history_hours = int(history_hours_raw)
        if history_hours <= 0:
            history_hours = None

    # 媒體下載設定優先讀 runtime_config.json，若未設定才回退到 env（相容舊配置）
    download_media_raw = runtime_json.get("download_media", os.getenv("TELEGRAM_DOWNLOAD_MEDIA", "false"))
    download_media = _to_bool(str(download_media_raw))
    media_dir = str(runtime_json.get("media_dir", os.getenv("TELEGRAM_MEDIA_DIR", "media"))).strip() or "media"
    skip_forwards_raw = runtime_json.get("skip_forwards", True)
    skip_forwards = _to_bool(str(skip_forwards_raw))

    whitelist_raw = runtime_json.get("forward_whitelist", [])
    forward_whitelist = _parse_whitelist(whitelist_raw)

    session_dir = os.getenv("TELEGRAM_SESSION_DIR", "session").strip() or "session"
    session_name = os.getenv("TELEGRAM_SESSION_NAME", "telegram_scraper").strip() or "telegram_scraper"
    pg_host = os.getenv("PGVECTOR_HOST", "pgvector").strip() or "pgvector"
    pg_port = int(os.getenv("PGVECTOR_PORT", "5432"))
    telegram_pg_db = os.getenv("TELEGRAM_PGVECTOR_DB", "").strip()
    if telegram_pg_db:
        pg_db = telegram_pg_db
    else:
        pg_db = os.getenv("PGVECTOR_DB", "discord_data").strip() or "discord_data"
    pg_user = _load_required_env("PGVECTOR_USER")
    pg_password = _load_required_env("PGVECTOR_PASSWORD")
    pg_notify_channel = os.getenv("TELEGRAM_PG_NOTIFY_CHANNEL", "telegram_new_message").strip() or "telegram_new_message"

    return TelegramConfig(
        api_id=api_id,
        api_hash=api_hash,
        session_dir=session_dir,
        session_name=session_name,
        source_channel=normalize_channel_identifier(source_channel_raw),
        history_limit=history_limit,
        history_hours=history_hours,
        download_media=download_media,
        media_dir=media_dir,
        skip_forwards=skip_forwards,
        forward_whitelist=forward_whitelist,
        runtime_config_path=runtime_config_path,
        pg_host=pg_host,
        pg_port=pg_port,
        pg_db=pg_db,
        pg_user=pg_user,
        pg_password=pg_password,
        pg_notify_channel=pg_notify_channel,
    )
