"""用 ffprobe 讀影片長度。轉發端壓縮影片、給 vision 模型看的影片抽幀都要先知道長度。"""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


async def probe_duration(path: str, *, timeout: float = 30) -> float:
    """影片長度（秒）；讀不到、逾時或不是影片回 0。不拋例外，要不要繼續由呼叫端決定。"""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout)
        return max(float(stdout.decode().strip() or 0), 0.0)
    except asyncio.TimeoutError:
        logger.warning("ffprobe 逾時（%s 秒）：%s", timeout, path)
    except Exception as exc:
        logger.warning("ffprobe 執行失敗：%s err=%s", path, exc)
    finally:
        if proc is not None and proc.returncode is None:
            proc.kill()
            await proc.wait()
    return 0.0
