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
import time


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


def stream_busy() -> bool:
    """目前是否有人持有串流鎖（chat / embedding 正在跑）。

    供背景插話（功能二）判斷「現在有人在用模型」→ 讓位、不硬擠。
    """
    return _LEMONADE_STREAM_LOCK.locked()


# ── 前景活動標記：協調「只有 P0 觸發換模型」的依據 ──────────────────────
# 背景插話/傾聽（功能二，跑小模型）在前景（/askai、功能一，跑大模型）活躍窗口內
# 必須暫停，否則會把大模型卸載換成小模型，下次 /askai 又換回去 → swap ping-pong。
# 用 monotonic 時間戳；只有前景路徑呼叫 note_foreground_activity()。
_LAST_FOREGROUND_ACTIVITY_MONO: float = 0.0


def note_foreground_activity() -> None:
    """前景（/askai、功能一）開始/進行時呼叫，記錄活躍時刻。"""
    global _LAST_FOREGROUND_ACTIVITY_MONO
    _LAST_FOREGROUND_ACTIVITY_MONO = time.monotonic()


def foreground_recently_active(grace_seconds: float) -> bool:
    """前景是否在 grace_seconds 內活躍過（背景插話據此讓位）。"""
    if _LAST_FOREGROUND_ACTIVITY_MONO <= 0.0:
        return False
    return (time.monotonic() - _LAST_FOREGROUND_ACTIVITY_MONO) < grace_seconds
