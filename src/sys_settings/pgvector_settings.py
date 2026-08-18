"""pgvector / Hybrid Retrieval 固定設定。"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field


class RetrievalSourceConfig(BaseModel):
    """單一檢索資料來源設定。"""

    source_key: str = Field(
        description=(
            "資料來源唯一鍵值。"
            "例如：discord_chat / member_profile / knowledge_base。"
        ),
    )
    table_name: str = Field(
        description="對應 pgvector 資料表名稱。",
    )
    doc_type: str = Field(
        description="寫入 metadata 的 doc_type，用於查詢過濾與觀測。",
    )
    enabled: bool = Field(
        default=True,
        description="是否啟用此來源。可用於灰度上線或暫時停用某資料來源。",
    )
    persist_mode: Literal["none", "auto", "manual"] = Field(
        default="manual",
        description=(
            "資料寫入模式：none=不寫入、auto=流程內自動寫入、manual=由獨立 pipeline 寫入。"
        ),
    )


class HybridRetrievalSettings(BaseModel):
    """Hybrid Retrieval 固定參數（不走 env）。

    參數設計原則：
    - 聊天場景以「召回率」優先，再用 RRF 做穩定融合。
    - 預設值已是可上線起步值；若觀測到 relevant_selected 經常偏低，
      先調高 candidate_pool，再調整 BM25/Vector 權重。
    """

    pgvector_embed_dim: int = Field(
        default=1024,
        description=(
            "向量維度，必須與 embed_model 輸出維度一致。"
            "建議值：與模型一致（常見 768 / 1024 / 1536）。"
            "若不一致會造成寫入或查詢失敗。"
        ),
    )
    persist_chat_to_pgvector: bool = Field(
        default=True,
        description=(
            "是否將 Discord 聊天訊息持久化寫入 pgvector。"
            "建議值：true（正式環境），可累積長期記憶與歷史檢索能力；"
            "若只做短期驗證可暫設 false。"
        ),
    )
    hybrid_rrf_k: int = Field(
        default=60,
        description=(
            "RRF (Reciprocal Rank Fusion) 平滑常數。"
            "建議值：60（常用穩定值）。"
            "值越小越強調前幾名，值越大越平均。"
            "聊天室噪音高時建議維持 50~80。"
        ),
    )
    hybrid_bm25_weight: float = Field(
        default=0.45,
        description=(
            "BM25 字面檢索在 RRF 融合中的權重。"
            "建議值：0.40~0.50。"
            "若關鍵詞命中很重要（專有名詞、代號）可提高。"
        ),
    )
    hybrid_vector_weight: float = Field(
        default=0.55,
        description=(
            "Vector 語意檢索在 RRF 融合中的權重。"
            "建議值：0.50~0.65。"
            "若常見口語、同義詞、縮寫，建議維持高於 BM25。"
        ),
    )
    hybrid_candidate_pool: int = Field(
        default=30,
        description=(
            "向量檢索候選池大小（先取多少筆再融合）。"
            "建議值：20~50，預設 30。"
            "relevant_selected 偏低可先調高到 40；"
            "若延遲升高再逐步下修。"
        ),
    )
    hybrid_alpha: float | None = Field(
        default=0.55,
        description=(
            "Hybrid 融合係數（0~1）。"
            "當有值時，會優先用 alpha 產生權重："
            "vector_weight=alpha、bm25_weight=1-alpha。"
            "建議值：0.50~0.65（聊天語境通常偏語意，故預設 0.55）。"
        ),
    )
    hybrid_min_fused_score: float = Field(
        default=0.003,
        description=(
            "RRF 融合後最低分數門檻。"
            "低於此分數的候選會被過濾，避免把雜訊送進 LLM。"
            "建議值：0.002~0.006，若 relevant_selected 常為 0 可先下修。"
        ),
    )

    retrieval_sources: dict[str, RetrievalSourceConfig] = Field(
        default_factory=lambda: {
            "discord_chat": RetrievalSourceConfig(
                source_key="discord_chat",
                table_name="discord_messages_index",
                doc_type="discord_chat",
                enabled=True,
                persist_mode="auto",
            ),
            "member_profile": RetrievalSourceConfig(
                source_key="member_profile",
                table_name="discord_member_profiles_index",
                doc_type="member_profile",
                enabled=True,
                persist_mode="manual",
            ),
            "knowledge_base": RetrievalSourceConfig(
                source_key="knowledge_base",
                table_name="discord_knowledge_base_index",
                doc_type="knowledge_base",
                enabled=True,
                persist_mode="manual",
            ),
        },
        description=(
            "可擴充多資料來源設定。"
            "未來新增知識庫時，只要在此新增 source，不需複製整套架構。"
        ),
    )

    def get_source(self, source_key: str) -> RetrievalSourceConfig | None:
        """取得單一資料來源設定。"""
        source = self.retrieval_sources.get(source_key)
        if source and source.enabled:
            return source
        return None

    @staticmethod
    def physical_table(table_name: str) -> str:
        """邏輯表名 → LlamaIndex PGVectorStore 的實體表名（`data_<table_name>`）。

        **只允許英數與底線**：表名沒辦法用 `%s` 參數化帶進 SQL，只能字串拼接，
        所以消毒必須發生在這裡。原本專案有四處各自拼 `f"data_{...}"`，其中
        `context_retriever` 與 `member_profile_store` 有消毒、`personality_extractor`
        與 persona agent 沒有——那不只是重複，是**安全性不一致**。收斂成單一來源後
        所有呼叫端自動一致。
        """
        return "data_" + re.sub(r"[^a-zA-Z0-9_]", "", table_name)

    def chat_table(self) -> str:
        """聊天記錄的實體表名（已消毒）。"""
        return self.physical_table(self.get_chat_table_name())

    def source_table(self, source_key: str, *, default: str | None = None) -> str:
        """指定來源的實體表名（已消毒）。來源不存在時用 `default`，沒給就 KeyError。"""
        source = self.get_source(source_key)
        name = source.table_name if source is not None else default
        if not name:
            raise KeyError(f"找不到檢索來源設定: {source_key}")
        return self.physical_table(name)

    def get_chat_table_name(self) -> str:
        """取得 Discord 聊天來源資料表（僅使用多來源結構）。"""
        chat_source = self.get_source("discord_chat")
        if not chat_source:
            raise ValueError("retrieval_sources 必須包含啟用中的 discord_chat 設定")
        return chat_source.table_name

    def resolve_fusion_weights(self) -> tuple[float, float]:
        """取得 BM25/Vector 融合權重。"""
        if self.hybrid_alpha is not None:
            alpha = min(max(float(self.hybrid_alpha), 0.0), 1.0)
            return 1.0 - alpha, alpha

        bm25_weight = max(float(self.hybrid_bm25_weight), 0.0)
        vector_weight = max(float(self.hybrid_vector_weight), 0.0)
        total = bm25_weight + vector_weight
        if total <= 0:
            return 0.5, 0.5
        return bm25_weight / total, vector_weight / total


HYBRID_RETRIEVAL_SETTINGS = HybridRetrievalSettings()
