"""Prompt 檔載入：mtime 快取，改檔即生效免重啟。

**存在理由是收斂**：`signature_tag_extractor` 與 `preference_extractor` 各有一份
一字不差的載入器（只差 log 訊息與設定路徑），persona agent 又要第三份。這種
複製貼上的問題不在行數，而在於**修一個 bug 要記得改好幾處**。

不收斂的例外（形狀不同，各自保留）：
  - `emoji_text_utils._load_descriptions`：永久快取 + 明確 `reload_descriptions()`，
    因為 emoji 字典是被 04:00 排程改寫後主動重載，不是靠 mtime 輪詢
  - `llm_service._load_runtime_config_cached`：讀的是 pydantic 設定物件，錯誤處理不同
  - `ambient_reply._load_ambient_prompt`：多檔疊層，有自己的組裝邏輯
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger("discord_bot")

# path -> (mtime_ns, 內容)。多 thread 讀同一份 prompt 時避免重複讀檔。
_cache: dict[str, tuple[int, Any]] = {}
_lock = threading.Lock()


def _load(path: str | Path, *, label: str, parse) -> Any | None:
    p = Path(path)
    key = str(p)
    try:
        if not p.exists():
            logger.warning("找不到 %s: %s", label, p)
            return None
        mtime_ns = p.stat().st_mtime_ns
        with _lock:
            cached = _cache.get(key)
            if cached is not None and cached[0] == mtime_ns:
                return cached[1]
        value = parse(p.read_text(encoding="utf-8"))
        with _lock:
            _cache[key] = (mtime_ns, value)
        return value
    except Exception as exc:
        logger.warning("載入 %s 失敗（%s）：%s", label, p, exc)
        return None


def read_text(path: str | Path, *, label: str = "prompt") -> str:
    """讀純文字 prompt；缺檔或失敗回空字串（呼叫端自行決定要不要略過）。"""
    value = _load(path, label=label, parse=lambda raw: raw.strip())
    return value or ""


def read_json(path: str | Path, *, label: str = "prompt") -> dict[str, Any] | None:
    """讀 JSON prompt；缺檔或解析失敗回 None（呼叫端自行決定是否致命）。"""
    value = _load(path, label=label, parse=json.loads)
    return value if isinstance(value, dict) else None
