"""Prompt 檔載入：mtime 快取，改檔即生效免重啟。

**存在理由是收斂**：`signature_tag_extractor` 與 `preference_extractor` 各有一份
一字不差的載入器（只差 log 訊息與設定路徑），persona agent 又要第三份。這種
複製貼上的問題不在行數，而在於**修一個 bug 要記得改好幾處**。

不只 prompt：表情字典、貼圖字典也走 `read_parsed`（各自的解析函式，檔案改了才重新解析）。

不收斂的例外（形狀不同，各自保留）：
  - `llm_service._load_runtime_config_cached`：讀的是 pydantic 設定物件，錯誤處理不同
  - `ambient_reply._load_ambient_prompt`：多檔疊層，有自己的組裝邏輯
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

# path -> (mtime_ns, 內容)。多 thread 讀同一份 prompt 時避免重複讀檔。
_cache: dict[str, tuple[int, Any]] = {}
_lock = threading.Lock()


def _load(path: str | Path, *, label: str, parse, missing_ok: bool = False) -> Any | None:
    p = Path(path)
    key = str(p)
    try:
        if not p.exists():
            if not missing_ok:
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


def read_parsed(path: str | Path, *, parse: Callable[[str], Any], label: str, missing_ok: bool = False) -> Any | None:
    """讀檔並用 `parse` 解析；檔案修改時間沒變就回上次解析的結果（呼叫端不要改它）。

    缺檔或失敗回 None。`missing_ok`：檔案本來就可能還不存在（例如還沒寫過的貼圖字典），不記警告。
    """
    return _load(path, label=label, parse=parse, missing_ok=missing_ok)


def forget(path: str | Path) -> None:
    """丟掉快取，下次一定重讀。修改時間的解析度不夠（同一瞬間改兩次）時的保險。"""
    with _lock:
        _cache.pop(str(Path(path)), None)
