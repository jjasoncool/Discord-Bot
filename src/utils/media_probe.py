"""跑 ffmpeg／ffprobe 這類媒體子行程：等到做完或逾時，逾時就砍掉行程；讀影片長度也在這裡。

架構定位：基礎層（utils），只依賴標準庫。上層：Telegram 轉發的影片壓縮、給 vision 模型看的影片抽幀、
點歌的音量量測。下層：asyncio 的子行程。

介面：
- `run_media_tool(cmd, *, timeout)`：跑一個子行程，回 `ToolResult`（returncode、stdout、stderr、timed_out、ok）；
  逾時砍掉行程、記 warning、不丟例外；執行檔不存在這類啟動失敗丟 OSError。
- `probe_duration(path, *, timeout=30)`：影片長度（秒）；讀不到、逾時、不是影片回 0。

規則：
- 專案裡跑子行程只走 `run_media_tool`（守衛擋自己 `create_subprocess_exec`）：每一處都有逾時、逾時都會收掉行程。
  Telegram 轉發一次只處理一則，一支卡住的 ffmpeg 會讓整條轉發停住。
- 時限由呼叫端依工作給（抽幀一分鐘、壓縮一道十幾分鐘）；stdin 一律關掉，工具不會停下來等輸入。

例外與決策：
- 逾時回結果而不丟例外：呼叫端本來就要看 returncode 決定成敗，多看一個 timed_out 比多接一種例外好。
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Sequence

logger = logging.getLogger(__name__)

# 測試換成假的：不真的開行程、不真的等
_create_subprocess = asyncio.create_subprocess_exec
_wait_for = asyncio.wait_for


@dataclass(frozen=True)
class ToolResult:
    returncode: int | None
    stdout: bytes
    stderr: bytes
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return not self.timed_out and self.returncode == 0


async def run_media_tool(cmd: Sequence[str], *, timeout: float) -> ToolResult:
    """跑 `cmd`，最多等 `timeout` 秒；逾時砍掉行程並回 `timed_out=True`。stdout、stderr 都收起來給呼叫端看。"""
    args = [str(part) for part in cmd]
    proc = await _create_subprocess(
        *args, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await _wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        logger.warning("%s 逾時（%s 秒），已砍掉：%s", args[0], timeout, " ".join(args[1:8]))
        return ToolResult(None, b"", b"", timed_out=True)
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
    return ToolResult(proc.returncode, stdout, stderr)


async def probe_duration(path: str, *, timeout: float = 30) -> float:
    """影片長度（秒）；讀不到、逾時或不是影片回 0。不拋例外，要不要繼續由呼叫端決定。"""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        result = await run_media_tool(cmd, timeout=timeout)
        if result.timed_out:
            return 0.0
        return max(float(result.stdout.decode().strip() or 0), 0.0)
    except (OSError, ValueError) as exc:
        logger.warning("ffprobe 執行失敗：%s err=%s", path, exc)
    return 0.0
