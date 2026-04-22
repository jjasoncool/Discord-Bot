"""Custom emoji 文字替換工具：把 `<:name:id>` / `<a:name:id>` 轉成 `:描述:`。

用途：
- chat_persistence 寫入 pgvector 前做語意化，避免 embed model 把 emoji token 當雜訊
- 未來其他需要語意化訊息文字的地方也可共用

和 personality_extractor 內的 `_clean_text_for_extraction` 的差別：
- 這裡只做 custom emoji 替換；不動 URL、mention、空白
- personality_extractor 是人格萃取專用的「深度清理」，會多做幾步

字典來源與 reaction_classifier 一樣是 emoji_dictionary.txt；兩者各自獨立快取，
更新字典後呼叫 `reload_descriptions()` 即可熱重載本模組快取。
"""
from __future__ import annotations

import logging
import re
import threading
from pathlib import Path

logger = logging.getLogger("discord_bot")

_EMOJI_DICT_PATH = "/app/settings/emoji_dictionary.txt"

# 支援靜態與動畫 emoji：<:name:id> 和 <a:name:id>
_CUSTOM_EMOJI_PATTERN = re.compile(r"<a?:(\w+):\d+>")

_description_cache: dict[str, str] | None = None
_cache_lock = threading.Lock()


def _load_descriptions() -> dict[str, str]:
    """載入 emoji_name → 描述。讀取時會剝除可能尾隨的 `| category` 部分。"""
    global _description_cache
    if _description_cache is not None:
        return _description_cache

    with _cache_lock:
        if _description_cache is not None:
            return _description_cache

        result: dict[str, str] = {}
        path = Path(_EMOJI_DICT_PATH)
        if not path.exists():
            logger.warning("emoji_text_utils: 找不到 emoji dict: %s", path)
            _description_cache = result
            return result

        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                name, _, desc = line.partition("=")
                name = name.strip()
                desc = desc.strip()
                # 新格式：desc 可能尾隨 "| category"，剝掉只留描述
                if "|" in desc:
                    desc = desc.rpartition("|")[0].strip()
                if name and desc:
                    result[name] = desc
        except Exception as exc:
            logger.warning("emoji_text_utils: 載入字典失敗: %s", exc)

        _description_cache = result
        logger.info(
            "emoji_text_utils: 已載入 %d 個 custom emoji 描述", len(result),
        )
        return result


def reload_descriptions() -> int:
    """強制清快取並重載。回傳載入項目數。"""
    global _description_cache
    with _cache_lock:
        _description_cache = None
    return len(_load_descriptions())


def replace_custom_emoji_with_description(text: str) -> str:
    """把文字裡的 `<:name:id>` / `<a:name:id>` 替換成 `:描述:`。

    格式選擇理由：
    - `:xxx:` 是 Discord / Slack / GitHub 的 emoji shortcode 慣例，LLM 天然認得
    - 使用者實際在文字中打出 `:word:` 讓其字面保留的情況罕見（Discord 會自動
      補全或攔截），碰撞率遠低於 `[xxx]`

    - 字典有描述 → 替換為 ` :描述: `（前後加空白，避免多個 emoji 黏一起）
    - 字典沒登錄 → 整段 emoji 移除（與 personality_extractor 行為一致）
    - 字串不含 emoji 格式 → 原樣返回（快速 path）
    - 替換完最後會壓掉多餘空白（包含 sub 自己帶出來的）
    """
    if not text:
        return text
    if "<:" not in text and "<a:" not in text:
        return text

    mapping = _load_descriptions()

    def _substitute(match: re.Match) -> str:
        name = match.group(1)
        desc = mapping.get(name)
        return f" :{desc}: " if desc else " "

    replaced = _CUSTOM_EMOJI_PATTERN.sub(_substitute, text)
    # 把連續空白壓成單一空白；頭尾 strip
    return re.sub(r"\s+", " ", replaced).strip()
