"""功能二記憶：使用者偏好事實抽取與寫入（Phase C-2/C-3 核心）。

把一批插話頻道訊息餵 12B → 抽出「本人自我揭露的中性偏好」原子事實（守門：自他分流、
敏感丟、紅線丟）→ 經 corroboration（多次提到才升等）寫入共享 pgvector 記憶層。

政策（見 AI_HANDOFF 功能二區塊）：
  只記本人中性偏好；他人/敏感/紅線一律丟；confidence < 門檻不寫；
  首見 tentative（不公開引用），不同批次提到 ≥ trusted_promote_at 升 trusted（才會被召回）。

本檔是「大腦」（給定訊息 → 抽取 + 寫入）；訊息來源緩衝 / 排程 / 召回在 ambient_memory 接。
"""
from __future__ import annotations

import asyncio
import functools
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from llm.intro_rag_port import get_pgvector_intro_rag_port
from services.llm_service import LLMService
from sys_settings.llm_settings import AmbientChatSettings

logger = logging.getLogger("discord_bot")

_SETTINGS = AmbientChatSettings()
_LLM_SERVICE: Optional[LLMService] = None
_PROMPT_CACHE: dict = {"text": None, "mtime_ns": None}


def _get_llm() -> LLMService:
    global _LLM_SERVICE
    if _LLM_SERVICE is None:
        _LLM_SERVICE = LLMService()
    return _LLM_SERVICE


def _load_extractor_prompt() -> str:
    """讀抽取守門 prompt（mtime 快取）；缺檔回空字串（呼叫端會略過抽取）。"""
    path = Path(_SETTINGS.extractor_prompt_path)
    try:
        if path.exists():
            mtime_ns = path.stat().st_mtime_ns
            if _PROMPT_CACHE["mtime_ns"] == mtime_ns and _PROMPT_CACHE["text"]:
                return _PROMPT_CACHE["text"]
            text = path.read_text(encoding="utf-8").strip()
            if text:
                _PROMPT_CACHE["text"] = text
                _PROMPT_CACHE["mtime_ns"] = mtime_ns
                return text
    except Exception as exc:
        logger.warning("載入 preference extractor prompt 失敗（%s）：%s", path, exc)
    return ""


def _parse_facts(raw: str) -> list[dict]:
    """從 12B 輸出穩健地解析 JSON facts 陣列（容忍 markdown 圍欄與前後雜訊）。"""
    if not raw:
        return []
    s = raw.strip()
    start = s.find("[")
    end = s.rfind("]")
    if start == -1 or end == -1 or end < start:
        return []
    try:
        data = json.loads(s[start : end + 1])
    except Exception:
        return []
    if not isinstance(data, list):
        return []

    out: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        author_id = str(item.get("author_id", "")).strip()
        fact = str(item.get("fact", "")).strip()
        fact_key = str(item.get("fact_key", "")).strip()
        if not author_id.isdigit() or not fact or not fact_key:
            continue
        try:
            confidence = float(item.get("confidence", 0))
        except (TypeError, ValueError):
            confidence = 0.0
        out.append({
            "author_id": author_id,
            "fact": fact[:200],
            "fact_key": fact_key[:120],
            "category": str(item.get("category", "")).strip()[:40],
            "confidence": max(0.0, min(1.0, confidence)),
        })
    return out


async def extract_preferences(*, messages: list[dict], model: str) -> list[dict]:
    """messages: [{author_id, alias, text}, …] → 候選 facts（含 alias）。

    用 chat_raw（非 generate_reply，避開人設/安全框架），temperature 低求穩定。
    """
    system_prompt = _load_extractor_prompt()
    if not system_prompt or not messages:
        return []

    alias_map: dict[str, str] = {}
    lines: list[str] = []
    for m in messages:
        author_id = str(m.get("author_id", "")).strip()
        text = (m.get("text", "") or "").strip()
        if not author_id.isdigit() or not text:
            continue
        alias_map.setdefault(author_id, (m.get("alias", "") or ""))
        lines.append(f"author_id={author_id} ({m.get('alias', '') or '-'}): {text[:300]}")
    if not lines:
        return []

    chat_messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "以下是群聊訊息：\n" + "\n".join(lines)},
    ]
    try:
        raw = await _get_llm().chat_raw(
            model=model, messages=chat_messages, temperature=0.2
        )
    except Exception as exc:
        logger.warning("preference 抽取 LLM 失敗：%s", exc)
        return []

    facts = _parse_facts(raw)
    for f in facts:
        f["alias"] = alias_map.get(f["author_id"], "")
    return facts


async def ingest_preferences(*, guild_id: int, candidates: list[dict]) -> dict:
    """corroboration + 寫入。回傳統計 {written, new, promoted, skipped_conf}。

    流程：濾 confidence → 批內同 (author, fact_key) 去重（一批只算一次）→ 依作者讀既有 →
    命中既有則 mention_count+1（達門檻升 trusted），否則新建 tentative。
    """
    stats = {"written": 0, "new": 0, "promoted": 0, "skipped_conf": 0}
    if not candidates:
        return stats

    port = get_pgvector_intro_rag_port()
    loop = asyncio.get_running_loop()
    now_iso = datetime.now(timezone.utc).isoformat()

    # 濾信心 + 批內去重（同一批內同一件事只算一次 corroboration）
    deduped: dict[tuple[str, str], dict] = {}
    for c in candidates:
        if c.get("confidence", 0.0) < _SETTINGS.memory_min_confidence:
            stats["skipped_conf"] += 1
            continue
        deduped.setdefault((c["author_id"], c["fact_key"]), c)

    by_author: dict[str, list[dict]] = {}
    for (author_id, _fk), c in deduped.items():
        by_author.setdefault(author_id, []).append(c)

    for author_id, cands in by_author.items():
        existing_rows = await loop.run_in_executor(
            None,
            functools.partial(
                port.list_preference_facts, guild_id=guild_id, author_id=int(author_id)
            ),
        )
        existing = {r.get("fact_key", ""): r for r in existing_rows}

        for c in cands:
            prev = existing.get(c["fact_key"])
            if prev:
                try:
                    prev_count = int(prev.get("mention_count", "1") or "1")
                except ValueError:
                    prev_count = 1
                count = prev_count + 1
                first_seen = prev.get("first_seen") or now_iso
                was_trusted = prev.get("status") == "trusted"
            else:
                count = 1
                first_seen = now_iso
                was_trusted = False

            status = "trusted" if count >= _SETTINGS.trusted_promote_at else "tentative"
            doc_id = await port.index_preference_fact(
                guild_id=guild_id,
                author_id=int(author_id),
                alias=c.get("alias", ""),
                fact=c["fact"],
                fact_key=c["fact_key"],
                category=c.get("category", ""),
                confidence=float(c.get("confidence", 0.0)),
                status=status,
                mention_count=count,
                first_seen=first_seen,
                last_seen=now_iso,
            )
            if doc_id:
                stats["written"] += 1
                if not prev:
                    stats["new"] += 1
                if status == "trusted" and not was_trusted:
                    stats["promoted"] += 1

    return stats


async def process_message_batch(
    *, guild_id: int, messages: list[dict], model: str
) -> dict:
    """便利接口：給定一批訊息 → 抽取 → corroboration 寫入。供 ambient_memory flush 呼叫。"""
    candidates = await extract_preferences(messages=messages, model=model)
    if not candidates:
        return {"written": 0, "new": 0, "promoted": 0, "skipped_conf": 0}
    stats = await ingest_preferences(guild_id=guild_id, candidates=candidates)
    logger.info("preference 批次寫入：guild=%s %s", guild_id, stats)
    return stats
