"""每日 04:00 維護的編排：四個步驟照順序跑一次，加上「什麼時候跑、錯過要補跑」的排程。

架構定位：功能層（`llm/persona`）。只決定步驟順序與失敗怎麼隔離，每一步的實作在各自的模組。
  - 上層（誰呼叫）：`discord_bot` 在 on_ready 用 `supervise` 掛 `schedule_loop`；手動測試可直接呼叫 `run_once`。
  - 下層（呼叫誰）：`llm.persona.personality_extractor`（① 補表情字典、上次萃取時間）、`llm.persona.signature_tag_extractor`（②）、
    `llm.persona.agent.batch`（③ persona agent）、`llm.persona.agent.publish`（④ 發布精簡版）、`llm.persona.member_names`（名字表）、
    `sys_settings`（模型名稱、agent 開關）。

介面：
  - `run_once(guild)`：跑一次四步；已經有一輪在跑就記 INFO 跳過。
  - `schedule_loop(bot)`：先等 60 秒 → 啟動補跑檢查 → 每天 04:00 跑一次；給 `supervise`。
  - `catch_up_if_missed(bot, *, now=None)`：上次寫入早於上一個該跑的 04:00 就補跑一次，回傳有沒有補。
  - `last_scheduled_run(now)`／`next_run(now)`：上一個該跑、下一個要跑的 04:00。

規則：
  - 每一步各自接例外、失敗不拖累後面；同一時間只跑一輪（`_running`）。
  - ③ 排在 ① ② 之後：它吃 GPU、跑最久；④ 排最後，把每個人最新的精簡版寫進 auto_personality。
  - 各步驟的模組在第一次跑時才 import：啟動不載入 agent 那一大串，改了程式也會在下一個 04:00 用到新版。
  - 名字表（顯示名稱＋伺服器暱稱＋全域名稱）③④ 用同一份，agent 的歸因與發布的擋名字規則才會一致。

例外與決策：
  - 2026-10-13 拆掉原本的第 ③ 步「production 人格萃取」（整批送 LLM 直接寫 auto_personality）：精簡版連續 12 晚 failed=0，
    備援每晚只剩 1 人、寫入 0；精簡版是空的人從此維持最後一版描述（備援寫出來的品質不如 agent，寧可空著）。
  - 排程還是手寫的 sleep 迴圈（守衛 `test_shared_conventions` 列為例外），待搬到 `utils.due_loop.run_due_loop`。
  - 從 `discord_bot.on_ready` 搬出來：維護的順序、補跑、不重疊是功能邏輯，不該和啟動登記混在一起。
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from sys_settings.llm_settings import LLMServiceSettings, load_llm_runtime_config
from sys_settings.time_settings import APP_TZ

logger = logging.getLogger(__name__)

MAINTENANCE_HOUR = 4
STARTUP_DELAY_SECONDS = 60      # 讓其他服務先就緒
RETRY_AFTER_SECONDS = 3600      # 排程那一輪失敗後隔多久再試

_SETTINGS = LLMServiceSettings()
_running = False                # 同一時間只跑一輪（補跑檢查、排程、手動測試不會疊在一起）


def _scheduled_model() -> Optional[str]:
    runtime_config = load_llm_runtime_config(_SETTINGS.llm_runtime_model_path)
    return runtime_config.personality_model or runtime_config.model


async def run_once(guild) -> None:
    """跑一次四步：① emoji 字典 → ② 招牌梗衰減 → ③ persona agent → ④ 發布精簡版。"""
    global _running
    if guild is None:
        logger.warning("每日維護：無可用 guild")
        return
    if _running:
        logger.info("每日維護略過：已有一輪正在執行中")
        return
    _running = True
    try:
        await _run_steps(guild)
    finally:
        _running = False


async def _run_steps(guild) -> None:
    # ① emoji 字典：讀 guild.emojis、補上還沒登記的表情
    try:
        from llm.persona.personality_extractor import refresh_emoji_dictionary
        refresh_emoji_dictionary(guild)
    except Exception as exc:
        logger.warning("emoji 字典自動更新失敗: %s", exc)

    # ② 招牌梗衰減 sweep：純 SQL、不佔 GPU
    try:
        from llm.persona.signature_tag_extractor import run_signature_tag_sweep
        await run_signature_tag_sweep(guild)
    except Exception as exc:
        logger.warning("招牌梗 sweep 失敗: %s", exc)

    def _member_names() -> dict[str, list[str]]:
        from llm.persona.member_names import member_names_from_guild
        return member_names_from_guild(guild)

    # ③ persona agent：寫獨立資料表，不碰 auto_personality（那是 ④ 的事）；失敗不該影響任何既有功能
    try:
        from llm.persona.agent.batch import run_batch
        from sys_settings.llm_settings import PersonaAgentSettings
        agent_settings = PersonaAgentSettings()
        if agent_settings.enabled:
            await run_batch(guild_id=guild.id, model=_scheduled_model(), settings=agent_settings,
                            member_names=_member_names())
    except Exception as exc:
        logger.error("persona agent 批次失敗: %s", exc, exc_info=True)

    # ④ 發布精簡版：每個人 agent 最新版本挑出來的（當晚 ③ 沒輪到的人也算）；失敗時大家維持原描述，下一晚再寫
    try:
        from llm.persona.agent.publish import effective_publish_mode, run_publish
        await run_publish(guild_id=guild.id, mode=effective_publish_mode(), member_names=_member_names())
    except Exception as exc:
        logger.error("persona 精簡版發布失敗: %s", exc, exc_info=True)


def last_scheduled_run(now: datetime) -> datetime:
    """「上一個應該跑的 04:00」：現在還沒過今天 04:00，上一個就是昨天的。"""
    run = now.replace(hour=MAINTENANCE_HOUR, minute=0, second=0, microsecond=0)
    return run - timedelta(days=1) if now < run else run


def next_run(now: datetime) -> datetime:
    """下一個 04:00（現在剛好是 04:00 整就算已經過了，排明天）。"""
    target = now.replace(hour=MAINTENANCE_HOUR, minute=0, second=0, microsecond=0)
    return target + timedelta(days=1) if now >= target else target


async def catch_up_if_missed(bot, *, now: Optional[datetime] = None) -> bool:
    """啟動補跑檢查：上次寫入早於上一個該跑的 04:00（容器重啟、中斷錯過了）就立刻補跑一次。回傳有沒有補跑。

    看的是 auto_personality 的 `last_extracted_at` 最大值——④ 每晚寫入時記的就是當下時間。
    """
    guild = bot.guilds[0] if bot.guilds else None
    if guild is None:
        return False
    from llm.persona.personality_extractor import get_last_extraction_time
    now = now or datetime.now(APP_TZ)
    due = last_scheduled_run(now)
    last_utc = get_last_extraction_time(guild.id)
    last_local = last_utc.astimezone(APP_TZ) if last_utc else None   # metadata 存的是 UTC，轉本機時區再比
    if last_local is None or last_local < due:
        logger.info("啟動補跑檢查：last_extract=%s, 上個排程=%s → 立即補跑", last_local, due.isoformat())
        await run_once(guild)
        return True
    logger.info("啟動補跑檢查：last_extract=%s ≥ 上個排程=%s，跳過", last_local, due.isoformat())
    return False


async def schedule_loop(bot) -> None:
    """先等 60 秒讓其他服務就緒 → 啟動補跑檢查 → 每天 04:00 跑一次；失敗記 ERROR、1 小時後再試。給 `supervise`。"""
    await asyncio.sleep(STARTUP_DELAY_SECONDS)
    try:
        await catch_up_if_missed(bot)
    except Exception as exc:
        logger.error("啟動補跑檢查失敗: %s", exc, exc_info=True)
    while True:
        try:
            now = datetime.now(APP_TZ)
            target = next_run(now)
            wait_seconds = (target - now).total_seconds()
            logger.info("每日維護排程：下次執行 %s（等待 %.0f 秒）", target.isoformat(), wait_seconds)
            await asyncio.sleep(wait_seconds)
            await run_once(bot.guilds[0] if bot.guilds else None)
        except Exception as exc:
            logger.error("每日維護排程失敗: %s", exc, exc_info=True)
            await asyncio.sleep(RETRY_AFTER_SECONDS)
