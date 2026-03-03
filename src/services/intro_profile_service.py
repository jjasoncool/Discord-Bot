"""自我介紹/他人印象的業務服務層。

說明：
- 這裡放「流程邏輯」（何時呼叫、如何整理資料）。
- 不放向量庫細節；向量串接由 llm.intro_rag_port 負責。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from llm.intro_rag_port import IntroRAGPort, NullIntroRAGPort


@dataclass(frozen=True)
class IntroProfilePayload:
    guild_id: int
    channel_id: int
    author_id: int
    alias: str
    wuwa_uid: str
    bio: str
    message_to_all: str


@dataclass(frozen=True)
class ImpressionPayload:
    guild_id: int
    channel_id: int
    author_id: int
    target_user_id: int
    target_alias: str
    target_habit: str
    impression: str


@runtime_checkable
class IntroProfileServiceProtocol(Protocol):
    async def on_intro_submitted(self, payload: IntroProfilePayload) -> None:
        """處理自我介紹提交後流程。"""

    async def on_impression_submitted(self, payload: ImpressionPayload) -> None:
        """處理他人印象提交後流程。"""


class IntroProfileService:
    """業務層：接住命令層事件，再委派給 RAG 串接層。"""

    def __init__(self, rag_port: IntroRAGPort | None = None):
        self.rag_port: IntroRAGPort = rag_port or NullIntroRAGPort()

    async def on_intro_submitted(self, payload: IntroProfilePayload) -> None:
        await self.rag_port.index_intro_profile(
            guild_id=payload.guild_id,
            channel_id=payload.channel_id,
            author_id=payload.author_id,
            alias=payload.alias,
            wuwa_uid=payload.wuwa_uid,
            bio=payload.bio,
            message_to_all=payload.message_to_all,
        )

    async def on_impression_submitted(self, payload: ImpressionPayload) -> None:
        await self.rag_port.index_impression(
            guild_id=payload.guild_id,
            channel_id=payload.channel_id,
            author_id=payload.author_id,
            target_user_id=payload.target_user_id,
            target_alias=payload.target_alias,
            target_habit=payload.target_habit,
            impression=payload.impression,
        )
