"""爬蟲存媒體檔的唯一入口：已有完整的檔就不重抓、先寫暫存檔再換名、太久沒進度就取消，並定義補掃重試與補發通知的時限。

架構定位：telegram-scraper 容器裡最底層的工具，只依賴標準庫與 `shared.telegram`。
  - 上層：`handlers`（訊息媒體、自訂表情）、`runner`（啟動時清暫存檔、補掃時限）。
  - 下層：呼叫端交進來的 Telethon client。不 import telethon：bot 容器的測試沒有 Telethon，也要能測這個模組。

介面：
- `fetch_media_file(client, target, path, expected_size=)`：讓 `path` 上有完整的檔，回傳（路徑, 是不是沿用現有的檔）。
- `download_with_stall_guard(client, target, file=)`：只管卡住偵測的下載，給 `fetch_media_file` 用。
- `remove_stale_parts(media_dir)`：清掉行程被強制結束時留下的暫存檔；只在還沒開始下載時呼叫。
- `MEDIA_RETRY_WINDOW`、`MEDIA_HOLD_NOTIFY`：補掃重試與補發通知的時限（定義在 `shared.telegram`）。

規則：
- 爬蟲存媒體一律走 `fetch_media_file`，不直接呼叫 `client.download_media`。
- `path` 要是穩定檔名（同一個 Telegram 檔案永遠同一個路徑）；沒有穩定檔名時傳資料夾，由 Telethon 命名，
  它保證不蓋到現有的檔，所以這條路不經過暫存檔，也不判斷檔案在不在。

例外與決策：
- 先寫暫存檔：Telethon 對已存在的路徑是當場清空再寫。同一個檔被另一則訊息再下載時（別的頻道複製貼上會帶同一個 id），
  一中斷，之前完整的檔就毀了。
- 判斷檔案完整：有大小就比大小，對不上的重新下載，舊版留下的殘檔能因此修好。照片沒有單一大小（Telethon 自己挑尺寸），
  非空就算；正式檔名上的檔都是下載完成才換上去的。
- 暫存檔名每次不同：不同訊息可能同時下載同一個檔，共用暫存檔會互相寫壞。各自下載、各自換名，內容相同，只是多花一次流量。
- 卡住偵測：Telethon 的 download_media 沒有逾時，照片曾經卡 1～1.6 小時；補掃一次處理一則，卡住時整輪補掃跟著停下。
  這裡看「多久沒有新的進度」而不是設總時限：3.5GB 的文件正常要下載 30 分鐘、183MB 的影片 11 分鐘，
  總時限會誤殺大檔；照片 p99 只有 9.3 秒。
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import uuid
from typing import Any

logger = logging.getLogger(__name__)

#: 下載中的暫存檔副檔名
PART_SUFFIX = ".part"
#: 暫存檔的完整格式（正式檔名加 8 碼加副檔名）。原檔名本來就是 .part 的文件存好後也以 .part 結尾，只看結尾會被當暫存檔刪掉
_PART_NAME = re.compile(r"\.[0-9a-f]{8}" + re.escape(PART_SUFFIX) + "$")

#: 多久沒有下載進度就當作卡住。必須大於 Telethon 原地等 FloodWait 的上限（flood_sleep_threshold 預設
#: 60 秒），否則單次限流等待就會被誤判成卡住；連續限流（每次重試都可能再等 ≤60 秒）超過時會被取消，
#: 只是延到下一輪補掃再試。
MEDIA_STALL_TIMEOUT_SEC = 180

# 補圖時限和 bot 共用一份（src/shared 由 compose 唯讀掛進 /opt/pylib）；這裡 import 進來給 handlers、runner 沿用
from shared.telegram import MEDIA_HOLD_NOTIFY, MEDIA_RETRY_WINDOW  # noqa: F401



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


def _is_complete(path: str, expected_size: int | None) -> bool:
    """`path` 上已經有完整的檔案。"""
    try:
        size = os.path.getsize(path)
    except OSError:
        return False
    if not expected_size:
        return size > 0
    if size != expected_size:
        logger.warning(f"現有的檔案大小不符（應為 {expected_size}、實際 {size}），重新下載: {path}")
        return False
    return True


def _remove_part(part: str) -> None:
    """清暫存檔。清不掉只是多佔空間、下次啟動再清，不能蓋掉下載本身的結果。"""
    try:
        os.remove(part)
    except FileNotFoundError:
        pass
    except OSError as exc:
        logger.warning(f"清不掉下載暫存檔 {part}: {exc}")


async def fetch_media_file(
    client: Any, target: Any, path: str, *, expected_size: int | None = None, stall_sec: float | None = None
) -> tuple[Any, bool]:
    """讓 `path` 上有完整的檔案，回傳（路徑, 是不是沿用現有的檔）；Telethon 沒有拿到檔案時路徑是 None。

    下載失敗、卡住、關機時例外照常往外拋，已存在的檔不受影響、暫存檔會清掉。
    """
    if os.path.isdir(path):
        return await download_with_stall_guard(client, target, file=path, stall_sec=stall_sec), False
    if _is_complete(path, expected_size):
        return path, True
    part = f"{path}.{uuid.uuid4().hex[:8]}{PART_SUFFIX}"
    try:
        downloaded = await download_with_stall_guard(client, target, file=part, stall_sec=stall_sec)
        if not downloaded:
            return None, False
        os.replace(downloaded, path)
        return path, False
    finally:
        _remove_part(part)


def remove_stale_parts(media_dir: str) -> int:
    """清掉資料夾裡的暫存檔，回傳清了幾個。下載途中呼叫會砍到正在寫的檔，所以只在啟動時用。"""
    removed = 0
    try:
        with os.scandir(media_dir) as entries:
            for entry in entries:
                if _PART_NAME.search(entry.name) and entry.is_file(follow_symlinks=False):
                    _remove_part(entry.path)
                    removed += 1
    except OSError as exc:
        logger.warning(f"清下載暫存檔失敗 {media_dir}: {exc}")
    return removed
