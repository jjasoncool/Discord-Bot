"""自訂表情字典 `settings/emoji_dictionary.txt` 的唯一讀取點。

格式：`emoji_name = 語意描述[ | 情緒類別]`；`#` 開頭與空行略過；`name =`（空值）是待填的佔位。

**檔案改了就重讀**（`prompt_files.read_parsed` 看修改時間）：使用者會手動維護描述，以前只有
04:00 偵測到新表情時才重載，手改要等 bot 重啟才生效。

以前 `emoji_text_utils`（描述）、`reaction_classifier`（情緒類別）、`personality_extractor`（名稱清單）
各自解析一份；類別不合法時兩邊處理不同（一邊照樣剝掉、一邊當成描述的一部分）。統一成：最後一段是
合法類別才拆開，否則整段都是描述。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from llm.prompt import prompt_files

logger = logging.getLogger(__name__)

EMOJI_DICT_PATH = "/app/settings/emoji_dictionary.txt"
VALID_CATEGORIES = frozenset({"agree", "laugh", "think", "negative", "neutral"})


@dataclass(frozen=True)
class EmojiEntry:
    name: str
    #: 空字串＝待填的佔位（`name =`）
    description: str
    #: 有寫合法類別才有值
    category: Optional[str]


def parse_line(line: str) -> Optional[EmojiEntry]:
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        return None
    name, _, rest = line.partition("=")
    name, rest = name.strip(), rest.strip()
    if not name:
        return None
    if "|" in rest:
        desc, _, cat = rest.rpartition("|")
        cat = cat.strip().lower()
        if cat in VALID_CATEGORIES:
            return EmojiEntry(name, desc.strip(), cat)
    return EmojiEntry(name, rest, None)


def parse_text(raw: str) -> dict[str, EmojiEntry]:
    result: dict[str, EmojiEntry] = {}
    for line in raw.splitlines():
        entry = parse_line(line)
        if entry is not None:
            result[entry.name] = entry
    return result


def entries() -> dict[str, EmojiEntry]:
    """名稱 → 字典項目（含待填的佔位）。檔案修改時間變了就重讀。"""
    return prompt_files.read_parsed(EMOJI_DICT_PATH, parse=parse_text, label="emoji 字典") or {}


def reload() -> int:
    """強制重讀（修改時間解析度不夠時的保險）。回傳項目數。"""
    prompt_files.forget(EMOJI_DICT_PATH)
    return len(entries())

