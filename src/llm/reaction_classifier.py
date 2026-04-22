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
import threading
from pathlib import Path
from typing import Literal

logger = logging.getLogger("discord_bot")

Category = Literal["agree", "laugh", "think", "negative", "neutral"]

_VALID_CATEGORIES: set[str] = {"agree", "laugh", "think", "negative", "neutral"}

_EMOJI_DICT_PATH = "/app/settings/emoji_dictionary.txt"

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


# 快取：{emoji_name: category}，從 emoji_dictionary.txt 載入
_custom_emoji_categories: dict[str, Category] | None = None
_cache_lock = threading.Lock()


def _parse_dict_line(line: str) -> tuple[str, str, str | None] | None:
    """解析一行 dict entry。

    支援格式：
      name = description
      name = description | category
      name =                     ← 空值，回 None
    """
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        return None
    name, _, rest = line.partition("=")
    name = name.strip()
    rest = rest.strip()
    if not name or not rest:
        return None

    # 檢查是否有顯式 category
    if "|" in rest:
        desc_part, _, cat_part = rest.rpartition("|")
        desc = desc_part.strip()
        cat = cat_part.strip().lower()
        if cat not in _VALID_CATEGORIES:
            # 類別不合法：當作沒寫，只用描述
            return (name, rest, None)
        return (name, desc, cat)
    return (name, rest, None)


def _infer_category_from_description(description: str) -> Category:
    """從中文描述關鍵字推斷類別，命中優先順序依 rules 列表。"""
    for keywords, category in _DESCRIPTION_KEYWORD_RULES:
        if any(kw in description for kw in keywords):
            return category
    return "neutral"


def _load_custom_emoji_categories() -> dict[str, Category]:
    """從 emoji_dictionary.txt 載入並快取 custom emoji 分類。

    載入流程：
    1. 逐行解析
    2. 有顯式 | category → 用那個
    3. 沒顯式 → 從描述關鍵字推斷
    4. 都推不出 → neutral
    """
    global _custom_emoji_categories
    if _custom_emoji_categories is not None:
        return _custom_emoji_categories

    with _cache_lock:
        if _custom_emoji_categories is not None:
            return _custom_emoji_categories

        result: dict[str, Category] = {}
        path = Path(_EMOJI_DICT_PATH)
        if not path.exists():
            logger.warning("reaction_classifier: 找不到 emoji dict: %s", path)
            _custom_emoji_categories = result
            return result

        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                parsed = _parse_dict_line(line)
                if not parsed:
                    continue
                name, desc, explicit_cat = parsed
                if explicit_cat is not None:
                    result[name] = explicit_cat  # type: ignore[assignment]
                else:
                    result[name] = _infer_category_from_description(desc)
        except Exception as exc:
            logger.warning("reaction_classifier: 載入 emoji dict 失敗: %s", exc)

        _custom_emoji_categories = result
        logger.info(
            "reaction_classifier: 已載入 %d 個 custom emoji 分類",
            len(result),
        )
        return result


def reload_custom_emoji_categories() -> int:
    """強制清快取並重載（emoji dict 更新後呼叫）。回傳載入項目數。"""
    global _custom_emoji_categories
    with _cache_lock:
        _custom_emoji_categories = None
    mapping = _load_custom_emoji_categories()
    return len(mapping)


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
