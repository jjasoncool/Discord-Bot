"""Lemonade 後端的串流互斥閘。

問題背景：
  Lemonade 收到 chat / embedding 請求時，透過內部 CURL 轉發到對應的
  llama.cpp backend port。實測發現：當 chat（port 8002）的回應正在 stream，
  另一個 embedding 請求（port 8001）打進來，會讓 lemonade 把進行中的 LLM
  連線 reset 掉，並對 client 回 `200 OK + {"error": {"type": "network_error"}}`，
  bot 端會被誤判成 `no_choices`。

解法：
  process 內加一把 asyncio.Lock。/askai 的 chat_completion 進入時持有；
  背景 chat_persistence flush 在跑 batch embedding 前也 await 同一把鎖。
  兩端對稱 → embedding burst 一定要等 stream 結束，反之亦然。

  RAG 用的 embedding（/askai 內 retriever）不掛這個 gate；因為它在 chat
  前就完成，本來就是序列的，不會跟同一個 /askai 的 chat 撞。
"""
from __future__ import annotations

import asyncio
import contextlib


_LEMONADE_STREAM_LOCK = asyncio.Lock()


@contextlib.asynccontextmanager
async def stream_exclusive():
    """進入區段期間持有全域鎖；對手方（chat / bg flush）必須等。

    用法：
        async with stream_exclusive():
            ... # chat_completion 或 batch embedding
    """
    async with _LEMONADE_STREAM_LOCK:
        yield
