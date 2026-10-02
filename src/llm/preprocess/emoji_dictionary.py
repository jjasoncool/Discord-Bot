"""自訂表情字典 `settings/emoji_dictionary.txt` 的唯一讀寫點。

格式：`emoji_name = 語意描述[ | 情緒類別]`；`#` 開頭與空行略過；`name =`（空值）是待填的佔位。

**檔案改了就重讀**（`prompt_files.read_parsed` 看修改時間）：使用者會手動維護描述，以前只有
04:00 偵測到新表情時才重載，手改要等 bot 重啟才生效。

以前 `emoji_text_utils`（描述）、`reaction_classifier`（情緒類別）、`personality_extractor`（名稱清單）
各自解析一份；類別不合法時兩邊處理不同（一邊照樣剝掉、一邊當成描述的一部分）。統一成：最後一段是
合法類別才拆開，否則整段都是描述。

**AI 補描述（`fill`）只寫兩種行**：空白待填、或描述只有一個類別字（例：`let_me_see_see = think`）；
名稱不在檔裡（別的伺服器的表情）就加到檔尾的 AI 專區。使用者寫過的描述一律不動。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from llm.prompt import prompt_files
from utils.safe_write import replace_text

logger = logging.getLogger(__name__)

EMOJI_DICT_PATH = "/app/settings/emoji_dictionary.txt"
VALID_CATEGORIES = frozenset({"agree", "laugh", "think", "negative", "neutral"})
#: 別的伺服器的表情由 AI 看圖補，集中放在檔尾這一區（使用者可以直接改）
AI_SECTION_HEADER = "# === 別的伺服器的表情（AI 看圖補的，可直接改） ==="


@dataclass(frozen=True)
class EmojiEntry:
    name: str
    #: 空字串＝待填的佔位（`name =`）
    description: str
    #: 有寫合法類別才有值
    category: Optional[str]

    @property
    def needs_description(self) -> bool:
        """空白，或描述只是一個類別字——模型只看得到 `:think:`，等於沒描述。"""
        return not self.description or self.description.strip().lower() in VALID_CATEGORIES


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


def fill(name: str, description: str, category: Optional[str], *, backup_dir: str, backup_keep: int = 14) -> bool:
    """寫入 AI 看圖得到的描述。回傳有沒有改檔。

    - 名稱在檔裡、而且需要描述 → 就地改那一行；使用者原本選的類別保留，沒選才用 AI 的
    - 名稱在檔裡、使用者已經寫了描述 → 不動（回 False）
    - 名稱不在檔裡 → 加到檔尾 AI 專區
    寫入前一刻重讀檔案，只動那一行，其他行原樣保留。
    """
    path = Path(EMOJI_DICT_PATH)
    raw = path.read_text(encoding="utf-8")
    lines = raw.split("\n")
    for i, line in enumerate(lines):
        entry = parse_line(line)
        if entry is None or entry.name != name:
            continue
        if not entry.needs_description:
            return False
        kept = entry.category or (entry.description.strip().lower() or None)
        lines[i] = _format(name, description, kept or category)
        break
    else:
        lines = _append_to_ai_section(lines, _format(name, description, category))
    replace_text(path, "\n".join(lines), backup_dir=backup_dir, keep=backup_keep)
    prompt_files.forget(path)
    return True


def _format(name: str, description: str, category: Optional[str]) -> str:
    return f"{name} = {description}" + (f" | {category}" if category else "")


def _append_to_ai_section(lines: list[str], new_line: str) -> list[str]:
    """加在 AI 專區最後一行之後；還沒有專區就在檔尾開一個。"""
    try:
        start = lines.index(AI_SECTION_HEADER)
    except ValueError:
        while lines and not lines[-1].strip():
            lines = lines[:-1]
        return [*lines, "", AI_SECTION_HEADER, new_line, ""]
    end = start + 1
    while end < len(lines) and not lines[end].startswith("# ==="):
        end += 1
    # 專區最後一個非空行之後
    last = start
    for j in range(start + 1, end):
        if lines[j].strip():
            last = j
    return [*lines[:last + 1], new_line, *lines[last + 1:]]
