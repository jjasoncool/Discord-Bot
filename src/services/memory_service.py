"""MemoryService：跨功能共享的「記憶」單一接口（門面）。

任何功能要用記憶，只 import 這個、呼叫語意清楚的方法，**不碰 pgvector / 12B / corroboration 細節**。
底層委派給 `member_profile_store`（儲存）與 `preference_extractor`（抽取/升等），門面穩定、底層可換。

各功能怎麼用：
  - 功能二 ambient：`observe(...)`（背景沉澱）+ `recall(...)`（插話前帶記憶）
  - /remember（顯式記憶，未來）：`remember(..., 高 confidence/status=trusted)`
  - /askai、功能一（未來）：`recall(...)`（要用時才 opt-in；persona 讀取器目前白名單排除 preference_fact）
  - 管理面板（未來）：`list_facts / forget`

目前涵蓋 `preference_fact`（功能二偏好事實）。未來功能一的 `ai_self_memory` 可在此擴方法，介面自然長大。
"""
from __future__ import annotations

import asyncio
import functools
import logging
import threading
from typing import Optional

from llm.member_profile_store import get_member_profile_store

logger = logging.getLogger("discord_bot")


class MemoryService:
    """共享記憶門面。無狀態（只持有底層 port 單例），可安全共用。"""

    def __init__(self) -> None:
        self._port = get_member_profile_store()

    # ── 讀（召回 / 查詢） ────────────────────────────────────────────
    async def recall(
        self, *, guild_id: int, user_id: int, only_trusted: bool = True,
        limit: Optional[int] = None,
    ) -> list[dict[str, str]]:
        """召回某人的偏好事實（預設只撈 trusted）；依 last_seen 由新到舊，可限筆數。"""
        rows = await self._list(guild_id=guild_id, user_id=user_id, only_trusted=only_trusted)
        rows.sort(key=lambda r: r.get("last_seen", ""), reverse=True)
        if limit is not None:
            rows = rows[:limit]
        return rows

    async def list_facts(
        self, *, guild_id: int, user_id: Optional[int] = None,
    ) -> list[dict[str, str]]:
        """列出偏好事實（管理用，含 tentative）。"""
        return await self._list(guild_id=guild_id, user_id=user_id, only_trusted=False)

    async def _list(
        self, *, guild_id: int, user_id: Optional[int], only_trusted: bool,
    ) -> list[dict[str, str]]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            functools.partial(
                self._port.list_preference_facts,
                guild_id=guild_id, author_id=user_id, only_trusted=only_trusted,
            ),
        )

    # ── 寫（抽取 / 升等 / 一步到位） ──────────────────────────────────
    async def extract(self, *, messages: list[dict], model: str) -> list[dict]:
        """從一批訊息抽出候選偏好（12B 守門）。"""
        from llm.preference_extractor import extract_preferences
        return await extract_preferences(messages=messages, model=model)

    async def remember(self, *, guild_id: int, candidates: list[dict]) -> dict:
        """把候選偏好寫入（含 corroboration 升等）。"""
        from llm.preference_extractor import ingest_preferences
        return await ingest_preferences(guild_id=guild_id, candidates=candidates)

    async def observe(self, *, guild_id: int, messages: list[dict], model: str) -> dict:
        """一步到位：抽取 + 寫入（功能二背景沉澱主入口）。

        並排跑兩條獨立抽取：偏好事實（preference_fact）+ 招牌梗（signature_tag）。
        回傳偏好 stats（維持 maybe_flush 加總相容）；招牌梗自行 log 自己的 stats。
        """
        from llm.preference_extractor import process_message_batch
        pref_stats = await process_message_batch(
            guild_id=guild_id, messages=messages, model=model
        )
        # 招牌梗抽取又是一段 26B 生成：偏好段跑完後再判一次前景閘，若 /askai 此刻已來就讓位
        # （本批 tag 延後，靠後續 flush 補；避免多排一段背景生成擋在前景前面）。
        try:
            from llm.lemonade_gate import foreground_recently_active, stream_busy
            from sys_settings.llm_settings import AmbientChatSettings
            if stream_busy() or foreground_recently_active(AmbientChatSettings().askai_grace_seconds):
                logger.info("signature_tag 抽取讓位前景（stream 忙或 /askai 近期活躍），本批延後")
            else:
                from llm.signature_tag_extractor import process_tag_batch
                await process_tag_batch(guild_id=guild_id, messages=messages, model=model)
        except Exception as exc:
            logger.warning("signature_tag 批次失敗（不影響偏好抽取）：%s", exc, exc_info=True)
        return pref_stats

    # ── 治理 ────────────────────────────────────────────────────────
    async def forget(self, *, doc_id: str) -> None:
        """刪一筆偏好事實（刪錯 / 禁記）。"""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, functools.partial(self._port.delete_preference_fact, doc_id=doc_id)
        )

    # ── 召回格式化（給 prompt 注入） ─────────────────────────────────
    @staticmethod
    def format_recall(facts: list[dict]) -> Optional[list[str]]:
        """把召回的事實壓成 persona_context 風格的自然語言行（一人一行）。"""
        if not facts:
            return None
        by_alias: dict[str, list[str]] = {}
        for f in facts:
            alias = (f.get("alias") or "對方").strip() or "對方"
            fact = (f.get("fact") or "").strip()
            if fact:
                by_alias.setdefault(alias, []).append(fact)
        lines = [
            f"（你記得關於 {alias} 的事）{'；'.join(facts_)}"
            for alias, facts_ in by_alias.items() if facts_
        ]
        return lines or None


_memory_service_singleton: Optional[MemoryService] = None
_singleton_lock = threading.Lock()


def get_memory_service() -> MemoryService:
    """取得 MemoryService 單例。"""
    global _memory_service_singleton
    if _memory_service_singleton is None:
        with _singleton_lock:
            if _memory_service_singleton is None:
                _memory_service_singleton = MemoryService()
    return _memory_service_singleton
