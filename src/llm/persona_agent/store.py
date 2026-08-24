"""persona agent 的兩張獨立資料表：成品與過程分開存。

**為什麼不寫進 `data_discord_member_profiles_index`**（也就是 production 的
`auto_personality` 那張）：
  ① 那是向量檢索表，版本歷史塞進去會被語意召回撈出來**當成現況**餵給模型
  ② 版本歷史不需要 embedding，每列算一次 1024 維純浪費
  ③ 需要 `UNIQUE(guild_id, author_id, version)` 這種關聯約束，jsonb metadata 撐不起來

**為什麼成品與過程要分兩張**：`versions` 是要留很久的成品（漂移分析靠它），
`runs` 是量大的過程 log（`trace` 的 JSONB 可能很肥、只在除錯與評測時翻、可定期清）。
混在一起會讓成品表被 log 拖垮，而且兩者的保存政策沒辦法分開設。

建表方式比照 `ai_interactions_store`：同一個 pgvector DB 裡的普通 SQL 表、
軟連結（以 author_id 對應，無硬 FK）、`ensure_table()` idempotent。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from sys_settings.llm_settings import LLMServiceSettings

logger = logging.getLogger("discord_bot")

VERSIONS_TABLE = "persona_agent_versions"
RUNS_TABLE = "persona_agent_runs"

_DDL = f"""
CREATE TABLE IF NOT EXISTS {VERSIONS_TABLE} (
  id           BIGSERIAL PRIMARY KEY,
  guild_id     TEXT NOT NULL,
  author_id    TEXT NOT NULL,
  version      INT  NOT NULL,
  persona_text TEXT NOT NULL,
  changes      JSONB NOT NULL,
  confidence   TEXT NOT NULL,
  notes        TEXT,
  model        TEXT NOT NULL,
  based_on     TEXT,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (guild_id, author_id, version)
);
CREATE INDEX IF NOT EXISTS idx_persona_versions_latest
  ON {VERSIONS_TABLE} (guild_id, author_id, version DESC);

CREATE TABLE IF NOT EXISTS {RUNS_TABLE} (
  id                 BIGSERIAL PRIMARY KEY,
  run_id             TEXT NOT NULL,
  guild_id           TEXT NOT NULL,
  author_id          TEXT NOT NULL,
  status             TEXT NOT NULL,
  steps              INT  NOT NULL DEFAULT 0,
  tool_calls         INT  NOT NULL DEFAULT 0,
  prompt_tokens      INT,
  thinking_exhausted BOOLEAN NOT NULL DEFAULT FALSE,
  evidence_claimed   INT NOT NULL DEFAULT 0,
  evidence_bogus     INT NOT NULL DEFAULT 0,
  accepted_changes   INT NOT NULL DEFAULT 0,
  rejected_changes   INT NOT NULL DEFAULT 0,
  skip_reason        TEXT,
  trace              JSONB,
  duration_ms        INT,
  error              TEXT,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_persona_runs_author_time
  ON {RUNS_TABLE} (guild_id, author_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_persona_runs_run_id ON {RUNS_TABLE} (run_id);
"""


def ensure_table() -> None:
    """建表（idempotent）。失敗只 log 不 raise —— 影子模式不該拖垮排程。"""
    try:
        with LLMServiceSettings().pgvector_cursor(commit=True) as cur:
            cur.execute(_DDL)
        logger.info("persona agent 資料表就緒：%s / %s", VERSIONS_TABLE, RUNS_TABLE)
    except Exception as exc:
        logger.error("建立 persona agent 資料表失敗：%s", exc, exc_info=True)


def latest_version(guild_id: int, author_id: str) -> Optional[dict[str, Any]]:
    """取該使用者最新一版（沒有回 None）。第一次跑時回 None → 改讀 production 當基準。"""
    sql = f"""
        SELECT version, persona_text, created_at
        FROM {VERSIONS_TABLE}
        WHERE guild_id = %s AND author_id = %s
        ORDER BY version DESC LIMIT 1
    """
    try:
        with LLMServiceSettings().pgvector_cursor() as cur:
            cur.execute(sql, (str(guild_id), str(author_id)))
            row = cur.fetchone()
    except Exception as exc:
        logger.warning("讀取最新版本失敗（視為沒有舊版本）：%s", exc)
        return None
    if not row:
        return None
    return {"version": row[0], "persona_text": row[1], "created_at": row[2]}


#: 這些 skip_reason 是**合法結果，不是失敗**。模型自認資料不足而不寫版本，跟它跑掛掉
#: 是兩回事——把前者算成失敗會讓話少的人被越勒越緊（預算降 70% → 50% → 隔離），
#: 而他們正是最需要多撈資料的族群，方向剛好相反。
_NON_FAILURE_SKIPS = ("confidence=low",)


def _is_failure(status: str, skip_reason: Optional[str]) -> bool:
    """這一次執行算不算失敗（用於連續失敗計數）。"""
    if status != "ok":
        return True
    if not skip_reason:
        return False
    return not any(ok in skip_reason for ok in _NON_FAILURE_SKIPS)


def consecutive_failures(guild_id: int, author_id: str, *, look_back: int = 5) -> int:
    """數最近連續幾次沒有成功寫入版本。

    給「漸進降級 + 隔離」用：連續失敗越多次就把預算調得越保守，超過門檻就跳過並
    列進維運報告。**重點不是省 GPU（一人一晚約 3 分鐘），是避免沉默失敗**——
    某個人永遠跑不成而沒人知道，才是真正的損害。
    """
    sql = f"""
        SELECT status, skip_reason FROM {RUNS_TABLE}
        WHERE guild_id = %s AND author_id = %s
        ORDER BY created_at DESC LIMIT %s
    """
    try:
        with LLMServiceSettings().pgvector_cursor() as cur:
            cur.execute(sql, (str(guild_id), str(author_id), look_back))
            rows = cur.fetchall()
    except Exception as exc:
        logger.warning("讀取連續失敗次數失敗（視為 0）：%s", exc)
        return 0
    count = 0
    for status, skip_reason in rows:
        if not _is_failure(status, skip_reason):
            break
        count += 1
    return count


def write_version(
    *,
    guild_id: int,
    author_id: str,
    persona_text: str,
    changes: list[dict[str, Any]],
    confidence: str,
    notes: str,
    model: str,
    based_on: str,
) -> Optional[int]:
    """寫入新版本（版本號自動遞增）。回傳版本號；失敗回 None。

    **永不原地覆蓋**——這正是要修掉的痛點：production 的 `auto_personality` 是
    一人一卡、寫新的就蓋掉舊的，寫壞了沒有退路。
    """
    sql = f"""
        INSERT INTO {VERSIONS_TABLE}
          (guild_id, author_id, version, persona_text, changes,
           confidence, notes, model, based_on)
        SELECT %s, %s, COALESCE(MAX(version), 0) + 1, %s, %s::jsonb, %s, %s, %s, %s
        FROM {VERSIONS_TABLE} WHERE guild_id = %s AND author_id = %s
        RETURNING version
    """
    params = (
        str(guild_id), str(author_id), persona_text,
        json.dumps(changes, ensure_ascii=False),
        confidence, notes, model, based_on,
        str(guild_id), str(author_id),
    )
    try:
        with LLMServiceSettings().pgvector_cursor(commit=True) as cur:
            cur.execute(sql, params)
            version = cur.fetchone()[0]
        logger.info(
            "persona agent 寫入版本 author=%s v%d（%d 項變更，based_on=%s）",
            author_id, version, len(changes), based_on,
        )
        return version
    except Exception as exc:
        logger.error("寫入 persona 版本失敗 author=%s：%s", author_id, exc, exc_info=True)
        return None


def record_run(
    *,
    run_id: str,
    guild_id: int,
    author_id: str,
    status: str,
    steps: int,
    tool_calls: int,
    prompt_tokens: Optional[int],
    thinking_exhausted: bool,
    evidence_claimed: int,
    evidence_bogus: int,
    accepted_changes: int,
    rejected_changes: int,
    skip_reason: Optional[str],
    trace: list[dict[str, Any]],
    duration_ms: int,
    error: Optional[str],
) -> bool:
    """記一次執行。**成功與失敗都要記**——失敗率與幻覺率是調參的唯一依據。"""
    sql = f"""
        INSERT INTO {RUNS_TABLE}
          (run_id, guild_id, author_id, status, steps, tool_calls, prompt_tokens,
           thinking_exhausted, evidence_claimed, evidence_bogus, accepted_changes,
           rejected_changes, skip_reason, trace, duration_ms, error)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s)
    """
    params = (
        run_id, str(guild_id), str(author_id), status, steps, tool_calls,
        prompt_tokens, thinking_exhausted, evidence_claimed, evidence_bogus,
        accepted_changes, rejected_changes, skip_reason,
        json.dumps(trace, ensure_ascii=False), duration_ms, error,
    )
    try:
        with LLMServiceSettings().pgvector_cursor(commit=True) as cur:
            cur.execute(sql, params)
        return True
    except Exception as exc:
        logger.error("記錄 persona agent run 失敗：%s", exc, exc_info=True)
        return False
