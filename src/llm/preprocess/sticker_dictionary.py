"""別的伺服器的貼圖描述 `settings/sticker_dictionary.txt` 的唯一讀寫點。

**為什麼另開一個檔**：本伺服器的貼圖描述存在 Discord 上（伺服器設定裡每張貼圖的描述欄），
由 `sticker_cache` 抓進記憶體；別的伺服器的貼圖我們改不了它的描述，Discord 上多半也是空的，
只能由 AI 看圖補、記在這裡。用**貼圖 ID** 當鍵——貼圖名稱是自由文字，不同伺服器容易撞名。

格式：`貼圖ID = 名稱｜描述`（跟 `sticker_cache` 的「名稱｜描述」一樣，讀出來直接拼進「[貼圖：…]」）。
使用者可以直接改描述；檔案改了就重讀。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from llm.prompt import prompt_files
from utils.safe_write import replace_text

logger = logging.getLogger(__name__)

STICKER_DICT_PATH = "/app/settings/sticker_dictionary.txt"
_HEADER = """# 別的伺服器的貼圖描述（AI 看圖補的，可直接改）
# 格式：貼圖ID = 名稱｜描述
# 本伺服器的貼圖描述請在 Discord 伺服器設定裡改，不寫在這裡。
"""


def parse_text(raw: str) -> dict[int, str]:
    result: dict[int, str] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if key.isdigit() and value:
            result[int(key)] = value
    return result


def entries() -> dict[int, str]:
    """貼圖 ID → 「名稱｜描述」。還沒寫過（檔案不存在）時是空的。"""
    return prompt_files.read_parsed(STICKER_DICT_PATH, parse=parse_text, label="貼圖字典", missing_ok=True) or {}


def lookup(sticker_id: int) -> Optional[str]:
    return entries().get(int(sticker_id))


def add(sticker_id: int, name: str, description: str, *, backup_dir: str, backup_keep: int = 14) -> bool:
    """記一張貼圖的描述。已經有了就不動（使用者可能改過）。回傳有沒有改檔。"""
    path = Path(STICKER_DICT_PATH)
    raw = path.read_text(encoding="utf-8") if path.exists() else _HEADER
    if int(sticker_id) in parse_text(raw):
        return False
    name = " ".join(str(name).split())
    if not raw.endswith("\n"):
        raw += "\n"
    replace_text(path, f"{raw}{int(sticker_id)} = {name}｜{description}\n", backup_dir=backup_dir, keep=backup_keep)
    prompt_files.forget(path)
    return True
