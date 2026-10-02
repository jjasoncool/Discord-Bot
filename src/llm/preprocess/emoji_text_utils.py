"""Custom emoji 文字替換工具：把 `<:name:id>` / `<a:name:id>` 轉成 `:描述:`。

用途：
- store_chat 寫入 pgvector 前做語意化，避免 embed model 把 emoji token 當雜訊
- 未來其他需要語意化訊息文字的地方也可共用

和 personality_extractor 內的 `_clean_text_for_extraction` 的差別：
- 這裡只做 custom emoji 替換；不動 URL、mention、空白
- personality_extractor 是人格萃取專用的「深度清理」，會多做幾步

字典讀取統一走 `llm.preprocess.emoji_dictionary`（檔案改了就重讀）。
"""
from __future__ import annotations

import logging
import re

from llm.preprocess import emoji_dictionary

logger = logging.getLogger(__name__)

# 支援靜態與動畫 emoji：<:name:id> 和 <a:name:id>
_CUSTOM_EMOJI_PATTERN = re.compile(r"<a?:(\w+):\d+>")


def _load_descriptions() -> dict[str, str]:
    """emoji_name → 描述（只列有描述的）。字典讀取與重讀見 `emoji_dictionary`。"""
    return {name: e.description for name, e in emoji_dictionary.entries().items() if e.description}


def reload_descriptions() -> int:
    """強制重讀字典（04:00 排程改寫檔案後呼叫）。回傳有描述的項目數。"""
    emoji_dictionary.reload()
    return len(_load_descriptions())


def replace_custom_emoji_with_description(text: str) -> str:
    """把文字裡的 `<:name:id>` / `<a:name:id>` 替換成 `:描述:`。

    格式選擇理由：
    - `:xxx:` 是 Discord / Slack / GitHub 的 emoji shortcode 慣例，LLM 天然認得
    - 使用者實際在文字中打出 `:word:` 讓其字面保留的情況罕見（Discord 會自動
      補全或攔截），碰撞率遠低於 `[xxx]`

    - 字典有描述 → 替換為 ` :描述: `（前後加空白，避免多個 emoji 黏一起）
    - 字典有登錄但沒描述（本伺服器、待管理員填）→ 整段移除
    - 字典沒登錄（別的伺服器的表情）→ 保留 ` :名稱: `（2026-10-02 起；以前整段移除，模型不知道對方回了什麼）
    - 字串不含 emoji 格式 → 原樣返回（快速 path）
    - 替換完最後會壓掉多餘空白（包含 sub 自己帶出來的）
    """
    if not text:
        return text
    if "<:" not in text and "<a:" not in text:
        return text

    mapping = _load_descriptions()
    known = emoji_dictionary.entries()

    def _substitute(match: re.Match) -> str:
        name = match.group(1)
        desc = mapping.get(name)
        if desc:
            return f" :{desc}: "
        # 字典裡有、只是還沒填描述＝本伺服器的表情，由管理員維護 → 照舊拿掉；
        # 字典裡根本沒有＝別的伺服器的表情，不可控 → 至少留名稱，不然不知道對方回了什麼
        return " " if name in known else f" :{name}: "

    replaced = _CUSTOM_EMOJI_PATTERN.sub(_substitute, text)
    # 把連續空白壓成單一空白；頭尾 strip
    return re.sub(r"\s+", " ", replaced).strip()


# unicode emoji / 符號（常見區段）——配合 _CUSTOM_EMOJI_PATTERN 判斷「整則只有表情符號」
_UNICODE_EMOJI_PATTERN = re.compile(
    "["
    "\U0001F300-\U0001FAFF"   # symbols & pictographs（含 supplemental / extended-A）
    "\U0001F000-\U0001F0FF"   # 麻將/骰子/撲克
    "\U0001F1E6-\U0001F1FF"   # 區域指示（國旗）
    "\U00002600-\U000026FF"   # misc symbols
    "\U00002700-\U000027BF"   # dingbats
    "️‍⃣"      # variation selector / ZWJ / keycap
    "]+"
)


def is_emoji_or_symbol_only(text: str) -> bool:
    """文字去掉自訂 emoji `<:name:id>` 與 unicode emoji 後是不是空的（＝整則只有表情符號）。

    給「不該對純表情訊息觸發回應」這類判斷共用，複用本模組既有的 custom emoji pattern。
    """
    leftover = _CUSTOM_EMOJI_PATTERN.sub("", text or "")
    leftover = _UNICODE_EMOJI_PATTERN.sub("", leftover).strip()
    return leftover == ""
