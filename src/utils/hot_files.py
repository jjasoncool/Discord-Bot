"""讀「會被手改、改了就要生效」的檔案：看修改時間決定要不要重讀，壞檔沿用上次讀到的好內容。

架構定位
  層級：基礎層（utils）。只依賴標準庫；不 import llm、services、sys_settings、commands（分層守衛擋）。
  上層（誰呼叫）：
    - prompt 與規則檔：各功能自己讀（llm.retrievers.*、llm.persona.*、llm.preprocess.*、services.relay.telegram_filter）
    - config.json：utils.utils.ChannelConfig（驗證最外層是物件、寫入走安全寫入＋備份）
    - settings/switches.json：sys_settings.switches（每個值 pydantic 驗證）
    - LLM runtime 設定：services.llm_service（pydantic 模型、模型名稱空白＝沒設定）
    - 表情、貼圖字典：llm.preprocess.emoji_dictionary／sticker_dictionary（各自的格式與寫入）
  下層（呼叫誰）：只有檔案系統（pathlib）與 logging。

介面
  read_text(path)             純文字；缺檔或從未讀成功回 ""
  read_json(path)             JSON 物件；不是物件或讀不到回 None
  read_parsed(path, parse=…)  自訂解析；回 parse 的結果
  forget(path)                丟掉快取，下次一定重讀（寫檔之後呼叫）

規則
  1. 修改時間沒變 → 回快取。呼叫端不要改回傳值，要改先複製。
  2. 解析失敗 → 沿用上次的好內容並記 WARNING（給了 on_error 就由呼叫端記）；從未成功過 → None。
  3. 缺檔 → None；missing_ok=True 時不記警告（檔案本來就可能還不存在，例如還沒寫過的貼圖字典）。
  4. 這裡只有機制。解析、驗證、寫入、壞了怎麼辦的政策都在呼叫端；不加認得特定檔案的函式。

不收斂的例外：llm.ambient.ambient_reply._load_ambient_prompt（多檔疊層、自己組裝）。
決策與歷史：AI_HANDOFF_AND_TODO.md 的 `architecture-review-2026-10`（M2a）。
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


def _load(path: str | Path, *, label: str, parse, missing_ok: bool = False,
          on_error: Callable[[Exception], None] | None = None) -> Any | None:
    p = Path(path)
    key = str(p)
    if not p.exists():
        if not missing_ok:
            logger.warning("找不到 %s: %s", label, p)
        return None
    try:
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
        with _lock:
            cached = _cache.get(key)
        if on_error is not None:
            on_error(exc)
        else:
            logger.warning("載入 %s 失敗（%s）：%s%s", label, p, exc, "；沿用上次讀到的內容" if cached else "")
        return cached[1] if cached is not None else None


def read_text(path: str | Path, *, label: str = "prompt") -> str:
    """讀純文字 prompt；缺檔或失敗回空字串（呼叫端自行決定要不要略過）。"""
    value = _load(path, label=label, parse=lambda raw: raw.strip())
    return value or ""


def read_json(path: str | Path, *, label: str = "prompt") -> dict[str, Any] | None:
    """讀 JSON prompt；缺檔或解析失敗回 None（呼叫端自行決定是否致命）。"""
    value = _load(path, label=label, parse=json.loads)
    return value if isinstance(value, dict) else None


def read_parsed(path: str | Path, *, parse: Callable[[str], Any], label: str, missing_ok: bool = False,
                on_error: Callable[[Exception], None] | None = None) -> Any | None:
    """讀檔並用 `parse` 解析；檔案修改時間沒變就回上次解析的結果（呼叫端不要改它）。

    缺檔回 None；解析失敗沿用上次的好內容（沒有就 None）。`missing_ok`：檔案本來就可能還不存在（例如還沒寫過的
    貼圖字典），不記警告。`on_error`：解析失敗時改由呼叫端記 log（例如要附上呼叫者）。
    """
    return _load(path, label=label, parse=parse, missing_ok=missing_ok, on_error=on_error)


def forget(path: str | Path) -> None:
    """丟掉快取，下次一定重讀。修改時間的解析度不夠（同一瞬間改兩次）時的保險。"""
    with _lock:
        _cache.pop(str(Path(path)), None)
