"""自訂表情的語意化（`<:name:id>` → `:描述:`），以及「一則訊息有沒有可聊的文字」的判斷。

架構定位：技術層（`llm/preprocess`），只依賴 `llm.preprocess.emoji_dictionary`。上層：聊天記憶寫入（`llm.storage.store_chat`、
`chat_index_backfill`）、插話的內容閘與回憶（`llm.ambient.ambient_reply`）、/askai 的相關名額（`llm.retrievers.context_retriever`）。
下層：表情字典（檔案改了就重讀）。

介面：
- `replace_custom_emoji_with_description(text)`：`<:name:id>`／`<a:name:id>` 換成 `:描述:`（規則見函式說明）。
- `is_emoji_or_symbol_only(text)`：整則只有表情、貼圖或符號（沒有任何字詞）。
- `is_link_only(text)`：整則只有網址。
- `reload_descriptions()`：字典重寫後強制重讀，回有描述的筆數。

規則：
- 兩種格式都認：Discord 原文（`<:name:id>`）與寫進向量庫後的文字（`:描述:`、`[貼圖：…]`），三個呼叫端才會用同一套標準。
- 只做表情替換，不動 URL、mention、空白；人格萃取的深度清理在 `personality_extractor._clean_text_for_extraction`。
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


# 寫進聊天向量庫前，自訂表情已換成 `:描述:`、貼圖換成 `[貼圖：…]`（store_chat.compose_persist_text）。
# 判斷「整則只有表情」時這兩種格式也要認：不然 14,612 則滿 8 字的純貼圖、1,732 則純表情描述會被當成有內容的回憶
_DESCRIBED_EMOJI_PATTERN = re.compile(r":[^:\n]+:")
_STICKER_TEXT_PATTERN = re.compile(r"\[貼圖：[^\]]*\]")
# 字母、數字、中日韓文字；Python 的 \w 在 Unicode 模式下含中日韓
_WORD_CHAR = re.compile(r"\w")


def is_emoji_or_symbol_only(text: str) -> bool:
    """整則是不是只有表情、貼圖或符號：去掉自訂 emoji `<:name:id>`、語意化後的 `:描述:`、貼圖 `[貼圖：…]`、unicode emoji
    後，剩下的沒有任何字詞字元（「????????」「……」這種純標點也算）。

    Discord 原文（插話的內容閘）與聊天向量庫存的文字（插話回憶、/askai 的候選）兩種格式都認得。
    """
    leftover = _CUSTOM_EMOJI_PATTERN.sub("", text or "")
    leftover = _DESCRIBED_EMOJI_PATTERN.sub("", leftover)
    leftover = _STICKER_TEXT_PATTERN.sub("", leftover)
    leftover = _UNICODE_EMOJI_PATTERN.sub("", leftover)
    return _WORD_CHAR.search(leftover) is None


_PREVIEW_TEXT_PATTERN = re.compile(r"\[預覽：[^\]]*\]")


def is_link_only(text: str) -> bool:
    """整則只有連結（每個空白分開的片段都是 http(s) 網址），沒有可聊、可當回憶的文字。

    寫進向量庫的純連結訊息後面接著 Discord 抓到的 `[預覽：標題 - 描述]`（store_chat.compose_persist_text），判斷前先去掉：
    「某人貼過一篇文章」不是值得當回憶注入的內容，預覽標題也不是他說的話。
    """
    tokens = _PREVIEW_TEXT_PATTERN.sub(" ", text or "").split()
    return bool(tokens) and all(t.startswith("http://") or t.startswith("https://") for t in tokens)
