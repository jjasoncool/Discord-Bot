"""重新排序（reranker）：把「問題＋一篇候選」一起讀，給一個「這篇有多能回答這個問題」的分數，重排前幾十篇。

第一關（關鍵字＋向量）裡，問題和文件是**分開**算的：快，但粗。reranker **同時**看兩者，看得出「這段剛好在回答
這件事」；也因為每篇都要當場讀一次，只重排前幾十篇。評估顯示正確答案常常已經撈到、只是沒排第一
（原句模式 Hit@1 36%、Hit@10 67%），這一步就是在補這段差距。

  - 模型：`llm_runtime_config.json` 的 `rerank_model`（Lemonade 載入；和主模型、embedding 各佔一個位置）
  - 送什麼：標題＋文件裡和問題最相關的那一段（切段規則同向量；挑和問題重疊的兩字組最多的那段）
  - 問題用哪個：呼叫端給了使用者的原句就用原句（reranker 是拿自然語言問句訓練的），沒給才用查詢字
  - 排 GPU 的隊（`lemonade_gate.gpu_exclusive_sync`），最多等這次搜尋剩下的等待額度（`max_wait_seconds`，
    沒給就用 `query_gpu_wait_seconds`）；等不到或出錯就丟例外，搜尋照原本的名次（見 `index.SearchIndex._rerank`）
"""
from __future__ import annotations

import logging
from contextlib import AbstractContextManager
from typing import Callable, Optional, Protocol, Sequence

from services.search.chunking import split_text
from services.search.text import bigram_tokens, normalize
from sys_settings.search_settings import SEARCH_SETTINGS

logger = logging.getLogger(__name__)


class Reranker(Protocol):
    """問題＋每篇的段落 → 每篇的分數（順序對齊 passages，分數越高越相關）。
    `max_wait_seconds`：最多等 GPU 幾秒，None＝用預設；等不到丟 `GpuBusy`。"""

    def rerank(self, query: str, passages: Sequence[str], *,
               max_wait_seconds: Optional[float] = None) -> list[float]:
        ...


def best_passage(query: str, search_text: str, max_chars: int) -> str:
    """一篇文件裡挑一段給 reranker 讀：照向量的切段規則切（每段帶標題），取和問題重疊最多的那段。

    為什麼不送全文：長公告幾千字，reranker 有長度上限也比較慢；為什麼不只送摘要：太短，看不出有沒有回答到。"""
    title, _, body = (search_text or "").partition("\n")
    pieces = split_text(title, body, max_chars=max_chars, overlap=0)
    if len(pieces) == 1:
        return pieces[0]
    wanted = set(bigram_tokens(normalize(query)))
    # 平手時 max 取第一個：靠前的段落通常是主旨
    return max(pieces, key=lambda piece: len(wanted & set(bigram_tokens(piece))))


class LemonadeReranker:
    """透過 Lemonade 的 /v1/rerank 打 reranker 模型。模型名稱每次用到時重讀設定（bot 長時間不重啟）。"""

    def __init__(self, *, client=None, gate: Optional[Callable[..., AbstractContextManager]] = None,
                 max_wait_seconds: Optional[float] = None, model: Optional[str] = None):
        self._client = client
        if gate is None:
            from llm.client.lemonade_gate import gpu_exclusive_sync

            gate = gpu_exclusive_sync
        self._gate = gate
        self.max_wait_seconds = (SEARCH_SETTINGS.query_gpu_wait_seconds if max_wait_seconds is None
                                 else max_wait_seconds)
        self._fixed_model = model

    def _settings(self):
        from sys_settings.llm_settings import LLMServiceSettings, load_llm_runtime_config

        settings = LLMServiceSettings()
        return settings, load_llm_runtime_config(settings.llm_runtime_model_path)

    def rerank(self, query: str, passages: Sequence[str], *,
               max_wait_seconds: Optional[float] = None) -> list[float]:
        model, options = self._fixed_model, None
        if model is None or self._client is None:
            settings, runtime = self._settings()
            model = model or runtime.rerank_model
            profile = runtime.backends.get(runtime.backend)
            options = profile.model_load_options.get(model) if profile is not None and model else None
            if self._client is None:
                from llm.client.http_client import LlmHttpClient

                self._client = LlmHttpClient(base_url=settings.llm_base_url, timeout=60.0)
        if not model:
            raise RuntimeError("沒有設定 rerank_model（llm_runtime_config.json）")
        with self._gate(max_wait_seconds=self.max_wait_seconds if max_wait_seconds is None else max_wait_seconds):
            if options:
                # 跟 embedding 一樣：Lemonade 要用對的載入參數（例如固定在哪一張卡）
                self._client.ensure_lemonade_model(model=model, options=options)
            return self._client.rerank(model=model, query=query, documents=list(passages))
