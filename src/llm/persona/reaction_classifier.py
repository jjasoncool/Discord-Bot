"""Reaction emoji 情緒分類器。

把 reaction 的 emoji（Unicode 或 custom）映射到 5 個情緒類別：
  - agree     認同、支持（👍 ❤️ 🔥）
  - laugh     歡樂、爆笑（😂 LULW）
  - think     思考、驚訝（🤔 👀）
  - negative  反對、難過（👎 😡）
  - neutral   其他

分類優先順序：
  1. Custom emoji：查 emoji_dictionary.txt 的顯式 category 欄
  2. Custom emoji：從描述關鍵字推斷（例如描述含「笑」→ laugh）
  3. Unicode emoji：查內建 UNICODE_EMOJI_CATEGORIES
  4. 都查不到 → neutral

Dictionary 格式（擴充過的 emoji_dictionary.txt）：
    emoji_name = 語意描述
    emoji_name = 語意描述 | category
"""
from __future__ import annotations

import logging
from typing import Literal

from llm.preprocess import emoji_dictionary

logger = logging.getLogger(__name__)

Category = Literal["agree", "laugh", "think", "negative", "neutral"]

_VALID_CATEGORIES: set[str] = {"agree", "laugh", "think", "negative", "neutral"}


# 從描述關鍵字推斷類別（供未顯式標註的 custom emoji 使用）
_DESCRIPTION_KEYWORD_RULES: list[tuple[tuple[str, ...], Category]] = [
    (("笑", "爆笑", "樂", "壞笑", "偷笑", "嘿嘿"), "laugh"),
    (("愛", "喜歡", "讚", "棒", "很好", "OK", "認同", "沒錯", "支持", "心"), "agree"),
    (("難過", "哭", "生氣", "不爽", "絕望", "心碎", "慘", "憤怒", "怨", "震驚", "雷"), "negative"),
    (("思考", "動腦", "驚訝", "疑", "問號", "看戲", "吃瓜", "覺得怪", "害怕", "偷看"), "think"),
]

# 內建 Unicode emoji 分類表（常見的先涵蓋，之後可擴充）
UNICODE_EMOJI_CATEGORIES: dict[str, Category] = {
    # ---- agree（認同、支持）----
    "👍": "agree", "👌": "agree", "✅": "agree",
    "❤️": "agree", "🧡": "agree", "💛": "agree", "💚": "agree",
    "💙": "agree", "💜": "agree", "🖤": "agree", "🤍": "agree",
    "🤎": "agree", "💖": "agree", "💗": "agree", "💓": "agree",
    "💞": "agree", "💕": "agree", "💝": "agree", "🫶": "agree",
    "🔥": "agree", "💯": "agree", "💪": "agree", "🙌": "agree",
    "👏": "agree", "🫡": "agree", "⭐": "agree", "🌟": "agree",

    # ---- laugh（歡樂、爆笑）----
    "😂": "laugh", "🤣": "laugh", "😆": "laugh", "😹": "laugh",
    "😁": "laugh", "😄": "laugh", "😃": "laugh", "😅": "laugh",
    "😸": "laugh", "🤭": "laugh", "😜": "laugh", "🤪": "laugh",
    "😝": "laugh", "🥳": "laugh", "🎉": "laugh", "🎊": "laugh",

    # ---- think（思考、驚訝、有感）----
    "🤔": "think", "🧐": "think", "🤨": "think",
    "😮": "think", "😯": "think", "😲": "think", "😦": "think",
    "😧": "think", "👀": "think", "❓": "think", "❔": "think",
    "💭": "think", "💡": "think", "🙂": "think",

    # ---- negative（反對、不爽、難過）----
    "👎": "negative", "❌": "negative", "🚫": "negative",
    "😡": "negative", "🤬": "negative", "😠": "negative",
    "😤": "negative", "🙄": "negative", "😒": "negative",
    "💀": "negative", "☠️": "negative", "😢": "negative",
    "😭": "negative", "😿": "negative", "😞": "negative",
    "😔": "negative", "😩": "negative", "😫": "negative",
    "🤡": "negative", "🤮": "negative", "🤢": "negative",

    # ---- neutral（中性、禮貌、工具）----
    "👋": "neutral", "🙏": "neutral", "✨": "neutral",
    "👉": "neutral", "👈": "neutral", "👆": "neutral",
    "👇": "neutral", "📌": "neutral", "📝": "neutral",
    "🔔": "neutral", "📢": "neutral",
}




def _infer_category_from_description(description: str) -> Category:
    """從中文描述關鍵字推斷類別，命中優先順序依 rules 列表。"""
    for keywords, category in _DESCRIPTION_KEYWORD_RULES:
        if any(kw in description for kw in keywords):
            return category
    return "neutral"


def _load_custom_emoji_categories() -> dict[str, Category]:
    """custom emoji 名稱 → 分類：有顯式 `| category` 用那個，沒有就從描述關鍵字推斷，都推不出是 neutral。
    字典讀取與重讀見 `llm.preprocess.emoji_dictionary`；待填（沒描述）的不列。"""
    return {
        name: e.category or _infer_category_from_description(e.description)  # type: ignore[misc]
        for name, e in emoji_dictionary.entries().items() if e.description
    }


def reload_custom_emoji_categories() -> int:
    """強制重讀字典（emoji dict 更新後呼叫）。回傳項目數。"""
    emoji_dictionary.reload()
    return len(_load_custom_emoji_categories())


def classify_reaction(emoji_name: str, emoji_id: str | None = None) -> Category:
    """把一個 reaction emoji 歸類。

    參數：
        emoji_name: Unicode emoji 字元 或 custom emoji 名稱（不含 <: :>）
        emoji_id:   custom emoji 才有值；Unicode emoji 傳 None

    回傳：5 類 Category 之一。
    """
    # 1. Custom emoji → 查字典
    if emoji_id is not None:
        mapping = _load_custom_emoji_categories()
        if emoji_name in mapping:
            return mapping[emoji_name]
        # 字典裡沒有 → 代表管理員還沒填；logger debug 一下，先 neutral
        logger.debug(
            "reaction_classifier: custom emoji '%s' (id=%s) 不在字典",
            emoji_name, emoji_id,
        )
        return "neutral"

    # 2. Unicode emoji → 查內建表
    if emoji_name in UNICODE_EMOJI_CATEGORIES:
        return UNICODE_EMOJI_CATEGORIES[emoji_name]

    # 3. 查不到 → neutral（常見的 emoji 變體，例如 skin tone 修飾後的）
    return "neutral"
