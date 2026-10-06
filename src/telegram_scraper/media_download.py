"""爬蟲下載媒體的唯一入口：有「卡住偵測」，並定義補掃重試與補發通知的時限。

**為什麼要卡住偵測**：Telethon 的 download_media 沒有逾時，照片曾經卡 1～1.6 小時；補掃一次處理一則，
卡住時整輪補掃跟著停下。這裡看「多久沒有新的進度」而不是設總時限：3.5GB 的文件正常要下載 30 分鐘、
183MB 的影片 11 分鐘，總時限會誤殺大檔；照片 p99 只有 9.3 秒。

不 import telethon：bot 容器的測試沒有 Telethon，也要能測這個模組。
"""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

logger = logging.getLogger(__name__)

#: 多久沒有下載進度就當作卡住。必須大於 Telethon 原地等 FloodWait 的上限（flood_sleep_threshold 預設
#: 60 秒），否則單次限流等待就會被誤判成卡住；連續限流（每次重試都可能再等 ≤60 秒）超過時會被取消，
#: 只是延到下一輪補掃再試。
MEDIA_STALL_TIMEOUT_SEC = 180

#: 下載失敗後，補掃重試到「發文時間＋這段時間」為止；圖在這段時間內補到才通知轉發端。
#: 跟轉發端的相簿補圖時限（discord-bot `telegram_relay_service._GROUP_FOLLOWUP_MAX_AGE`）一致：
#: 超過之後轉發端本來就不補送，再試也不會出現在 Discord。兩個容器不能互相 import，改一邊要記得改另一邊。
MEDIA_RETRY_WINDOW = timedelta(hours=12)

#: 新訊息的圖第一次下載失敗時，先不通知轉發端，等補掃補到圖再通知（文字和圖一起送成一則）；
#: 發文超過這段時間還沒補到，才通知一次讓文字先送。使用者 2026-10-05 定「等 30 分鐘」：
#: 轉發端的單則不等圖，下載失敗就通知會變成文字先送、之後補到的圖再也送不出去。
MEDIA_HOLD_NOTIFY = timedelta(minutes=30)


class MediaDownloadStalled(TimeoutError):
    """下載太久沒有進度，已經取消。"""


async def download_with_stall_guard(client: Any, target: Any, *, file: Any, stall_sec: float | None = None) -> Any:
    """`client.download_media(target, file=file)`，但超過 `stall_sec` 秒沒有進度就取消並拋 `MediaDownloadStalled`。

    Telethon 每收到一個區塊（最多 512KB）就回呼一次 progress_callback，用它記最後一次有進度的時間。
    外層被取消（關機）時一併取消下載，CancelledError 照常往外拋。
    """
    limit = MEDIA_STALL_TIMEOUT_SEC if stall_sec is None else stall_sec
    loop = asyncio.get_running_loop()
    last_progress = loop.time()

    def on_progress(_received: int, _total: int) -> None:
        nonlocal last_progress
        last_progress = loop.time()

    task = asyncio.ensure_future(client.download_media(target, file=file, progress_callback=on_progress))
    try:
        while True:
            remaining = limit - (loop.time() - last_progress)
            if remaining <= 0:
                raise MediaDownloadStalled(f"下載超過 {limit} 秒沒有進度，已取消")
            done, _ = await asyncio.wait({task}, timeout=remaining)
            if task in done:
                if task.cancelled() and not _being_cancelled():
                    # 外層沒被取消、下載卻被取消：Telethon 斷線時會取消進行中的請求。當成下載失敗，
                    # 不能當成關機往外拋——否則補掃迴圈會跟著結束、直到重啟都不再補掃
                    raise ConnectionError("下載被中斷（連線中斷）")
                return task.result()
    finally:
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                # 收尾等待期間剛好被關機取消：照常往外拋，不能吞掉
                if _being_cancelled():
                    raise
            except Exception:   # 被取消的下載本身的結果不重要；外層原本的例外照常往外拋
                pass


def _being_cancelled() -> bool:
    """目前這個 task 有沒有被要求取消（關機）。"""
    current = asyncio.current_task()
    return bool(current is not None and current.cancelling())
