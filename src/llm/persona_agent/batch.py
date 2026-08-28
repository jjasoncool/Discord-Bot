"""每晚一次的批次執行：挑人 → 逐一跑 → 到點收手。

排在 production 萃取**之後**（04:00 排程的第 ④ 步），兩者寫不同的表、序列執行，
彼此不知道對方存在。

三個設計決定，每個都來自實測：

**輪替而不是每晚全跑**：實測活躍使用者約 4.4 分／人，56 人要 3.4 小時，04:15 開始
會跑到 07:40——那時群裡開始有人聊天，agent 每步禮讓十分鐘再硬上反而最擾民。
先跑最久沒跑到的人，配合 `deadline_hour` 硬停，沒輪到的明晚自然排前面。

**納入門檻比 production 寬**：production 是 14 天 10 則，門檻外的人它直接跳過；
而那正是 agent 唯一明確贏的族群（7 天 1 則、90 天 91 則那個案例）。

**單人失敗不影響其他人**：每個人獨立 try/except，失敗照樣記進 runs 表——
失敗率與幻覺率是調參的唯一依據，漏記等於瞎調。
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Optional

from llm.persona_agent import agent as persona_agent
from llm.persona_agent import store
from llm.persona_agent import tools as persona_tools
from sys_settings.llm_settings import LLMServiceSettings, PersonaAgentSettings
from sys_settings.pgvector_settings import HYBRID_RETRIEVAL_SETTINGS
from sys_settings.time_settings import APP_TZ

logger = logging.getLogger("discord_bot")


def select_targets(
    guild_id: int, settings: Optional[PersonaAgentSettings] = None
) -> list[str]:
    """挑出本次要跑的 user_id，最久沒跑到的排前面。

    「最久沒跑」包含**從來沒跑過**的人（LEFT JOIN 後 NULL 排最前），所以新成員
    與剛納入門檻的人會自動優先，不必手動維護清單。
    """
    s = settings or PersonaAgentSettings()
    chat = HYBRID_RETRIEVAL_SETTINGS.chat_table()
    sql = f"""
        WITH eligible AS (
            SELECT metadata_->>'author_id' AS author_id, count(*) AS n
            FROM {chat}
            WHERE metadata_->>'doc_type' = 'discord_chat'
              AND metadata_->>'timestamp' >= %s
            GROUP BY 1
            HAVING count(*) >= %s
        ),
        last_run AS (
            SELECT author_id, max(created_at) AS ran_at
            FROM {store.RUNS_TABLE}
            WHERE guild_id = %s
            GROUP BY 1
        )
        SELECT e.author_id
        FROM eligible e
        LEFT JOIN last_run r ON r.author_id = e.author_id
        ORDER BY r.ran_at ASC NULLS FIRST, e.n DESC
    """
    # 時間界線用 tools 那支：字串比較才吃得到表達式索引，理由與注意事項都寫在那裡
    since = persona_tools._cutoff_iso(s.min_messages_days)
    try:
        with LLMServiceSettings().pgvector_cursor() as cur:
            cur.execute(sql, (since, s.min_messages, str(guild_id)))
            rows = cur.fetchall()
    except Exception as exc:
        logger.error("persona agent 選人失敗：%s", exc, exc_info=True)
        return []

    targets = [r[0] for r in rows if r and r[0]]
    if s.mode == "sample":
        targets = targets[: s.sample_size]
    logger.info(
        "persona agent 本次對象 %d 人（mode=%s，符合門檻 %d 人）",
        len(targets), s.mode, len(rows),
    )
    return targets


def _past_deadline(deadline_hour: int) -> bool:
    return datetime.now(APP_TZ).hour >= deadline_hour


async def run_batch(
    *,
    guild_id: int,
    model: str,
    settings: Optional[PersonaAgentSettings] = None,
    llm_service: Any = None,
) -> dict[str, int]:
    """跑一輪批次，回傳統計。任何單人失敗都不會中斷整批。"""
    s = settings or PersonaAgentSettings()
    if not s.enabled:
        logger.info("persona agent 影子模式未啟用，跳過")
        return {"skipped": 1}

    targets = await persona_agent.run_db(select_targets, guild_id, s)
    if not targets:
        return {"targets": 0}

    run_id = f"batch-{int(time.time())}"
    stats = {"targets": len(targets), "ok": 0, "failed": 0, "written": 0, "unrun": 0}
    started = time.perf_counter()

    for i, user_id in enumerate(targets, 1):
        if _past_deadline(s.deadline_hour):
            stats["unrun"] = len(targets) - i + 1
            logger.info(
                "persona agent 已過 %d:00，剩 %d 人留到明晚（最久沒跑的會排前面）",
                s.deadline_hour, stats["unrun"],
            )
            break
        try:
            ctx = persona_tools.ToolContext.build(
                guild_id=guild_id,
                allowed_ids=[user_id],  # 白名單只放這一人，工具層擋掉其他查詢
            )
            run, validated = await persona_agent.run_and_persist(
                user_id=user_id, guild_id=guild_id, ctx=ctx, model=model,
                run_id=run_id, llm_service=llm_service, save=True,
            )
            if run.status == "ok":
                stats["ok"] += 1
            else:
                stats["failed"] += 1
            if validated is not None and validated.skip_reason is None:
                stats["written"] += 1
            logger.info(
                "persona agent 批次進度 %d/%d user=%s status=%s",
                i, len(targets), user_id, run.status,
            )
        except Exception as exc:
            # 單人失敗不影響其他人；記 log 後繼續下一位
            stats["failed"] += 1
            logger.error(
                "persona agent 批次：user=%s 執行失敗 %s", user_id, exc, exc_info=True
            )

    stats["elapsed_s"] = int(time.perf_counter() - started)
    logger.info("persona agent 批次結束：%s", stats)
    return stats
