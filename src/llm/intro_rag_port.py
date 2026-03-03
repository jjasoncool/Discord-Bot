"""Intro RAG 串接層（技術介接層）。

職責：定義「如何把資料送進 RAG/向量庫」的介面。
不放業務流程判斷。
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class IntroRAGPort(Protocol):
    async def index_intro_profile(
        self,
        *,
        guild_id: int,
        channel_id: int,
        author_id: int,
        alias: str,
        wuwa_uid: str,
        bio: str,
        message_to_all: str,
    ) -> None:
        """將自我介紹資料寫入 RAG/向量資料庫。"""

    async def index_impression(
        self,
        *,
        guild_id: int,
        channel_id: int,
        author_id: int,
        target_user_id: int,
        target_alias: str,
        target_habit: str,
        impression: str,
    ) -> None:
        """將他人印象資料寫入 RAG/向量資料庫。"""


class NullIntroRAGPort:
    """預設 no-op 串接，尚未接真正向量庫前使用。"""

    async def index_intro_profile(
        self,
        *,
        guild_id: int,
        channel_id: int,
        author_id: int,
        alias: str,
        wuwa_uid: str,
        bio: str,
        message_to_all: str,
    ) -> None:
        _ = (guild_id, channel_id, author_id, alias, wuwa_uid, bio, message_to_all)

    async def index_impression(
        self,
        *,
        guild_id: int,
        channel_id: int,
        author_id: int,
        target_user_id: int,
        target_alias: str,
        target_habit: str,
        impression: str,
    ) -> None:
        _ = (
            guild_id,
            channel_id,
            author_id,
            target_user_id,
            target_alias,
            target_habit,
            impression,
        )
