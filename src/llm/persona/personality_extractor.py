"""人格萃取的共用零件：prompt 與規則檔、資料庫連線、上次寫入時間、每晚補表情字典、聊天文字清理。

架構定位：功能層（`llm/persona`）。
  - 上層（誰呼叫）：`llm.persona.daily_maintenance`（① `refresh_emoji_dictionary`、補跑檢查 `get_last_extraction_time`）、
    `llm.persona.agent`（`agent.py` 讀 `_load_extract_prompts` 的 system prompt；`tools.py` 用 `_get_db_conn`、`_clean_text_for_extraction`）。
  - 下層（呼叫誰）：`llm.preprocess.emoji_dictionary`／`emoji_text_utils`、`sys_settings`（pgvector 連線、表名）、`utils.hot_files`（規則檔）。

介面：`refresh_emoji_dictionary(guild)`、`get_last_extraction_time(guild_id)`、`load_description_rules()`、
  `_load_extract_prompts()`、`_get_db_conn()`、`_clean_text_for_extraction(text)`（共用元件，見 AGENTS）。

規則：描述要寫成什麼樣的規則只有 `persona_description_rules.txt` 一份，persona agent 讀同一個檔；
  `personality_extraction_prompt.json` 的 system_prompt 是人格素描的角色設定，agent 疊在它之上。

例外與決策：2026-10-13 拆掉原本在這裡的「production 人格萃取」pipeline（整批送 LLM、直接寫 auto_personality，
  04:00 維護的第 ③ 步與 /personality_extract 指令），由 persona agent 與發布精簡版取代；檔名沿用。
  經過見交接檔 `persona-extraction-agent`。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime


from llm.preprocess import emoji_dictionary
from llm.preprocess.emoji_text_utils import (
    reload_descriptions as _reload_emoji_descriptions,
    replace_custom_emoji_with_description,
)
from sys_settings.llm_settings import LLMServiceSettings
from sys_settings.pgvector_settings import HYBRID_RETRIEVAL_SETTINGS

logger = logging.getLogger(__name__)


_EXTRACT_PROMPT_PATH = "/app/settings/prompts/personality_extraction_prompt.json"
# 「描述要寫成什麼樣」的規則抽成共用檔：persona agent 需要同一份規則，
# 各自複製一份的話，日後調整其中一邊會靜默分岔。比照 persona_examples.txt
# 被 /askai 與插話共用的做法——共用的是**檔案**，兩邊各自讀。
_DESCRIPTION_RULES_PATH = "/app/settings/prompts/persona_description_rules.txt"
_extract_prompts: dict[str, str] | None = None


def _load_extract_prompts() -> dict[str, str]:
    """載入萃取 prompt（快取）。"""
    global _extract_prompts
    if _extract_prompts is not None:
        return _extract_prompts

    from pathlib import Path
    path = Path(_EXTRACT_PROMPT_PATH)
    if not path.exists():
        raise FileNotFoundError(f"找不到萃取 prompt 檔案: {path}")
    _extract_prompts = json.loads(path.read_text(encoding="utf-8"))
    return _extract_prompts


def load_description_rules() -> str:
    """讀取共用的「描述品質規則」（persona agent 讀同一個檔案）。

    讀檔失敗時回空字串而非拋錯：少了這段規則描述品質會變差，但整個 04:00 排程
    不該因為一個附加檔案不見就停擺。
    """
    from utils import hot_files

    return hot_files.read_text(_DESCRIPTION_RULES_PATH, label="描述品質規則")


def _get_db_conn():
    """建立 pgvector 連線。"""
    return LLMServiceSettings().pgvector_connect()


def get_last_extraction_time(guild_id: int | None = None) -> datetime | None:
    """查詢 auto_personality 最後一次萃取的時間（來自 metadata_.last_extracted_at）。

    回傳 UTC datetime；若資料庫沒有任何 auto_personality 記錄或未帶時間戳，回傳 None。
    給排程啟動時判斷「上次排程是否錯過」用。
    """
    profile_table = HYBRID_RETRIEVAL_SETTINGS.source_table("member_profile")
    sql = f"""
        SELECT MAX((metadata_->>'last_extracted_at')::TIMESTAMPTZ)
        FROM {profile_table}
        WHERE metadata_->>'profile_kind' = 'auto_personality'
          AND metadata_->>'last_extracted_at' IS NOT NULL
    """
    params: list = []
    if guild_id is not None:
        sql += " AND metadata_->>'guild_id' = %s"
        params.append(str(guild_id))

    try:
        with _get_db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                row = cur.fetchone()
                return row[0] if row and row[0] else None
    except Exception as exc:
        logger.warning("查詢 last_extracted_at 失敗: %s", exc)
        return None


def _load_all_emoji_names_from_file() -> set[str]:
    """所有已登記的 emoji name（含空值佔位），用於判斷是否需要新增。"""
    return set(emoji_dictionary.entries())


def refresh_emoji_dictionary(guild) -> int:
    """掃描 guild.emojis，把字典沒有的 emoji name 以空值 append 到檔案尾端。

    只處理本 guild 擁有的 emoji（guild.emojis 自然只列本伺服器自訂 emoji；
    其他伺服器的引用不會出現在這裡）。新項目以空值佔位寫入，萃取邏輯會自動
    忽略無描述的 emoji，等管理員手動填寫語意後才真正生效。

    回傳新增的項目數。
    """
    from datetime import datetime
    from pathlib import Path

    existing_names = _load_all_emoji_names_from_file()
    guild_emoji_names = {e.name for e in guild.emojis}
    new_names = sorted(guild_emoji_names - existing_names)
    if not new_names:
        logger.info(
            "emoji 字典無新項目（本 guild 共 %d 個自訂 emoji，全部已記錄）",
            len(guild_emoji_names),
        )
        return 0

    path = Path(emoji_dictionary.EMOJI_DICT_PATH)
    today = datetime.now().strftime("%Y-%m-%d")
    block = [
        "",
        f"# === 自動偵測 {today}（待填寫） ===",
        *[f"{name} =" for name in new_names],
        "",
    ]
    try:
        with path.open("a", encoding="utf-8") as f:
            f.write("\n".join(block))
    except Exception as exc:
        logger.warning("寫入 emoji 字典失敗: %s", exc)
        return 0

    # 清所有共用 emoji 快取（字典檔剛被改過）
    _reload_emoji_descriptions()
    try:
        from llm.persona.reaction_classifier import reload_custom_emoji_categories
        reload_custom_emoji_categories()
    except Exception as exc:
        logger.warning("重載 reaction_classifier 快取失敗: %s", exc)

    logger.info(
        "emoji 字典新增 %d 個待填項目（前 10：%s）",
        len(new_names),
        new_names[:10],
    )
    return len(new_names)


def _clean_text_for_extraction(text: str) -> str:
    """清理聊天文字，移除對人格分析無用的噪音。"""
    import re
    # Discord 自訂 emoji：<:name:id> → :描述:（與 store_chat 共用同一替換函式）
    text = replace_custom_emoji_with_description(text)
    # 移除所有 URL（對人格分析無用，且模型容易誤判為「分享音樂/資訊」）
    text = re.sub(r"https?://\S+", "", text)
    # 移除 Discord mention <@id> 保留可讀形式
    text = re.sub(r"<@!?(\d+)>", "@某人", text)
    # 壓縮空白
    text = " ".join(text.split()).strip()
    return text


