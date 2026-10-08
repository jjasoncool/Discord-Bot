"""GPU 單一資源的互斥閘。

原本只做一件事：擋 Lemonade 的串流衝突（見下）。2026-09-03 起擴成「同一時間只准
一種工作佔 GPU」的閘——排程產圖（ComfyUI）會卸載 LLM 並獨佔顯卡數十分鐘，
它跟 chat / embedding 是同一個資源的競爭者，不該各自開一把鎖。

**檔名還叫 `lemonade_gate` 是暫時的**：等 ComfyUI 那條線接完會一起正名
（見 AI_HANDOFF「ComfyUI 產圖 + GPU 資源仲裁」區塊的檔名正名表）。

── 原始問題（仍然成立）───────────────────────────────────────────
  Lemonade 收到 chat / embedding 請求時，透過內部 CURL 轉發到對應的
  llama.cpp backend port。實測發現：當 chat（port 8002）的回應正在 stream，
  另一個 embedding 請求（port 8001）打進來，會讓 lemonade 把進行中的 LLM
  連線 reset 掉，並對 client 回 `200 OK + {"error": {"type": "network_error"}}`，
  bot 端會被誤判成 `no_choices`。

  解法：process 內一把 asyncio.Lock。/askai 的 chat_completion 進入時持有；
  背景 store_chat flush 在跑 batch embedding 前也 await 同一把鎖。
  兩端對稱 → embedding burst 一定要等 stream 結束，反之亦然。

  RAG 用的 embedding（/askai 內 retriever）不掛這個 gate；因為它在 chat
  前就完成，本來就是序列的，不會跟同一個 /askai 的 chat 撞。

── 跨行程排隊（2026-10-06）────────────────────────────────────────
  asyncio.Lock 只管同一個行程。在 discord-bot 容器裡另開的行程（`docker exec` 跑的手動抽查腳本、
  之後的 MCP server）打模型時不會排隊，會跟插話、/askai 直接搶：10-06 跑 Telegram 過濾的歷史樣本時，
  插話一次花了 106 秒。使用者：「我希望跑判斷還是要排隊的」。
  所以拿到行程內的鎖之後，再拿一把**鎖檔**（`fcntl.flock`，同一個容器的行程共用 /tmp）。
  - 用非阻塞嘗試＋短暫 sleep 輪詢，不丟到執行緒裡等：等的途中被取消（逾時放行、租約到期）時，
    不會留下一個之後才拿到鎖、卻沒人放的執行緒。
  - 關檔就放鎖；行程當掉時作業系統也會放，不會有死鎖殘留。
  - 開不了鎖檔就只在本行程排隊（記 warning），不擋 LLM。
  - **輪流**：剛放掉鎖的行程，下一次先讓一拍（比別人的輪詢間隔長）再搶。不然同一行程連續的工作交棒是立刻的，
    另一個行程每 0.1 秒才試一次，幾乎永遠插不進去，只做到「不同時打模型」，沒做到排隊輪流。
  - **等太久**：等別的行程超過 `_CROSS_PROCESS_WARN_S` 記 warning（之後每 5 分鐘再記），超過
    `_CROSS_PROCESS_MAX_WAIT_S` 就不等鎖檔、記 error 照常打模型——別的行程卡住時，bot 的 AI 不能整個靜默停擺。

── 租約：為什麼不用固定 timeout、也不用 checker task ──────────────
  短工作（chat / embedding）持鎖幾秒到幾分鐘，不需要保護。長工作不同：
  ComfyUI 卡死的話裸 Lock 永遠不放，**bot 的 LLM 功能會全部靜默死掉**
  （/askai、插話、日記、人格萃取），而且不會有任何錯誤訊息。

  **固定 timeout 解不了，因為它分不出「跑很久」和「卡死」**——設短會誤殺正常的
  長工作，設長等於 bot 可以死著那麼久。所以改用租約：持有者拿一個**短期**租約，
  每完成一次可觀測的進展就 `renew()`。產圖的續租點不必另外造：ComfyUI 本來就要
  輪詢 `/history/{prompt_id}` 才知道圖好了沒，**輪詢成功本身就是心跳**。

  另開一個 checker task 去問「還在跑嗎」則是多一個會自己掛掉的元件，而且它最後
  還是得問 ComfyUI——那就是輪詢本身。把檢查點放在本來就會發生的動作上，零件更少。

  到期的處理**不是「別人來搶鎖」**（跨 task 搶鎖很髒），而是**持有者自我了斷**：
  watchdog 直接 cancel 持有它的 task，`async with` 的 finally 自然把鎖釋放。
  借用 asyncio 自己的取消機制，就不必自己管鎖的所有權。

  `lease_seconds=None`（預設）＝不開 watchdog，行為與擴充前一字不差——現有的
  `stream_exclusive()` caller 因此完全不用改。
"""
from __future__ import annotations

import asyncio
import contextlib
import fcntl
import logging
import os
import time


logger = logging.getLogger(__name__)

_GPU_LOCK = asyncio.Lock()

#: 目前持有者標籤（"llm" / "imagegen"）。None ＝ 沒人持有。
_holder: str | None = None

#: watchdog 的檢查間隔上限；租約剩餘時間比這短時會提早醒來。
_WATCHDOG_TICK_S = 5.0

#: 跨行程的鎖檔（同一個容器的行程共用 /tmp）。單元測試由 test/__init__.py 用環境變數換成暫存檔，不跟執行中的 bot 搶
CROSS_PROCESS_LOCK_PATH = os.getenv("LEMONADE_GPU_LOCK_PATH", "/tmp/lemonade_gpu.lock")
#: 別的行程拿著鎖時，多久再試一次
_CROSS_PROCESS_POLL_S = 0.1
#: 剛放掉鎖後讓一拍的長度（要比別人的輪詢間隔長，別的行程才碰得到空檔）
_CROSS_PROCESS_YIELD_S = 2 * _CROSS_PROCESS_POLL_S
_CROSS_PROCESS_WARN_S = 30.0
_CROSS_PROCESS_MAX_WAIT_S = 15 * 60.0
#: 本行程上次放掉鎖檔的時刻（monotonic）
_last_release = 0.0
#: 等滿上限放行後，這個時刻（monotonic）之前不再等鎖檔：不然每個呼叫都從頭等 15 分鐘，排在後面的要等 N 倍
_skip_until = 0.0


class GpuLease:
    """租約把手：長工作每完成一次可觀測的進展就呼叫 `renew()`。

    `lease_seconds=None` 時所有方法都是 no-op（永不到期），讓短工作沿用同一個介面
    而不必分兩套程式碼。
    """

    def __init__(self, owner: str, lease_seconds: float | None) -> None:
        self.owner = owner
        self.lease_seconds = lease_seconds
        self._deadline = (
            time.monotonic() + lease_seconds
            if lease_seconds is not None
            else float("inf")
        )

    def renew(self) -> None:
        """證明還活著，把到期時間往後推。"""
        if self.lease_seconds is not None:
            self._deadline = time.monotonic() + self.lease_seconds

    @property
    def remaining(self) -> float:
        """距離到期還有幾秒（無租約模式回 inf）。"""
        return max(0.0, self._deadline - time.monotonic())

    @property
    def expired(self) -> bool:
        return self.remaining <= 0.0


async def _watch_lease(lease: GpuLease, holder: asyncio.Task | None) -> None:
    """租約到期就取消持有者的 task，讓它自己的 finally 把閘門放掉。"""
    while True:
        remaining = lease.remaining
        if remaining <= 0.0:
            logger.error(
                "GPU 租約到期未續租（owner=%s，%gs 內無進展）→ 取消持有者、釋放閘門",
                lease.owner, lease.lease_seconds or 0.0,
            )
            if holder is not None and not holder.done():
                holder.cancel()
            return
        await asyncio.sleep(min(remaining, _WATCHDOG_TICK_S))


def _open_lock_file() -> int | None:
    try:
        return os.open(CROSS_PROCESS_LOCK_PATH, os.O_RDWR | os.O_CREAT, 0o666)
    except OSError as exc:
        logger.warning("開不了跨行程 GPU 鎖檔，只在本行程排隊：%s", exc)
        return None


class GpuBusy(TimeoutError):
    """等 GPU 鎖檔超過呼叫端給的上限（`gpu_exclusive_sync(max_wait_seconds=…)`）。

    給「等不起」的呼叫用：互動式搜尋算一個問句向量只要零點幾秒，卻可能要等 bot 整段長回答（一兩分鐘）；
    等不到就放棄這一步、退回不用 GPU 的做法，比讓使用者乾等好。"""


def _acquire_steps(fd: int, max_wait: float | None = None):
    """拿鎖檔的等待流程（讓一拍、輪詢、等太久記 warning、超過上限就放行）。

    寫成產生器：每次 yield 要睡幾秒，結束代表拿到鎖或放棄等待。async 版用 `asyncio.sleep`、同步版用
    `time.sleep` 走同一套流程，規則只有這一份。`max_wait` 給了就是「等這麼久還拿不到就丟 GpuBusy」，
    不走預設的「等滿上限照常打模型」。
    """
    global _skip_until
    since_release = time.monotonic() - _last_release
    if since_release < _CROSS_PROCESS_YIELD_S:
        yield _CROSS_PROCESS_YIELD_S - since_release
    started = time.monotonic()
    next_warn = _CROSS_PROCESS_WARN_S
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            _skip_until = 0.0
            return
        except BlockingIOError:
            if time.monotonic() < _skip_until:
                return      # 剛等滿上限放行過：別的行程還卡著，這段時間不再等
            waited = time.monotonic() - started
            if max_wait is not None and waited >= max_wait:
                raise GpuBusy(f"GPU 被別的工作佔著，等了 {waited:.0f} 秒還沒輪到")
            if waited >= _CROSS_PROCESS_MAX_WAIT_S:
                logger.error("等別的行程放 GPU 鎖檔超過 %d 秒，不等了、照常打模型（接下來 %d 秒都不等）（%s）",
                             _CROSS_PROCESS_MAX_WAIT_S, _CROSS_PROCESS_MAX_WAIT_S, CROSS_PROCESS_LOCK_PATH)
                _skip_until = time.monotonic() + _CROSS_PROCESS_MAX_WAIT_S
                return
            if waited >= next_warn:
                logger.warning("別的行程佔著 GPU（鎖檔 %s），已等 %d 秒", CROSS_PROCESS_LOCK_PATH, waited)
                next_warn += 300
            yield _CROSS_PROCESS_POLL_S


def _release(fd: int) -> None:
    global _last_release
    os.close(fd)
    _last_release = time.monotonic()


@contextlib.asynccontextmanager
async def _cross_process_lock():
    """拿鎖檔（別的行程拿著就輪詢等）；離開時關檔放鎖。開不了鎖檔就只在本行程排隊。"""
    fd = _open_lock_file()
    if fd is None:
        yield
        return
    try:
        for delay in _acquire_steps(fd):
            await asyncio.sleep(delay)
        yield
    finally:
        _release(fd)


@contextlib.contextmanager
def gpu_exclusive_sync(max_wait_seconds: float | None = None):
    """同步程式用的 GPU 閘門：只拿跨行程鎖檔，和 bot 的 `stream_exclusive` 排同一個隊。

    `max_wait_seconds`：最多等幾秒，等不到丟 `GpuBusy`（互動式查詢用）；None＝照預設規則一直等（批次工作用）。

    給同一個容器另開、沒有 event loop 的行程用（情報搜尋的批次算向量、MCP 搜尋算問句向量）：
    那些行程裡沒有別的 GPU 使用者，行程內的 asyncio 鎖用不到，跨行程鎖檔才是重點——
    10-08 曾在批次 embedding 與 bot 的長回答同時跑時發生顯示卡斷線。

    ⚠️ 不要在 bot 行程裡、`stream_exclusive` 區段內呼叫：同一個行程開兩個檔案描述子搶同一把鎖檔
    也會互相擋，要等到放行上限才過得去。
    """
    fd = _open_lock_file()
    if fd is None:
        yield
        return
    try:
        for delay in _acquire_steps(fd, max_wait_seconds):
            time.sleep(delay)
        yield
    finally:
        _release(fd)


@contextlib.asynccontextmanager
async def gpu_exclusive(owner: str = "llm", lease_seconds: float | None = None):
    """獨佔 GPU 的區段；其他競爭者（chat / embedding / 產圖）必須等。

    用法（長工作，要續租）：

        async with gpu_exclusive("imagegen", lease_seconds=120) as lease:
            ...
            lease.renew()   # 每次輪詢成功就續，證明還活著

    用法（短工作，不需租約）：`stream_exclusive()` 就是 `gpu_exclusive("llm")`。

    ⚠️ **不可重入**：區段內不要再呼叫任何會取用本閘門的東西（例如 `chat_raw`），
    會死鎖。要在區段內打後端就直接用 `LlmHttpClient`。
    """
    global _holder
    async with _GPU_LOCK, _cross_process_lock():
        _holder = owner
        lease = GpuLease(owner, lease_seconds)
        watchdog = (
            asyncio.create_task(_watch_lease(lease, asyncio.current_task()))
            if lease_seconds is not None
            else None
        )
        try:
            yield lease
        finally:
            if watchdog is not None:
                # 只 cancel 不 await：這裡本身可能正在被取消，await 會立刻再拋
                # CancelledError，反而跳過後面的 _holder 清理。
                watchdog.cancel()
            _holder = None


@contextlib.asynccontextmanager
async def stream_exclusive():
    """短工作（chat / batch embedding）的獨佔區段——不設租約，行為同擴充前。

    用法：
        async with stream_exclusive():
            ... # chat_completion 或 batch embedding
    """
    async with gpu_exclusive("llm"):
        yield


def stream_busy() -> bool:
    """目前是否有人佔著 GPU（chat / embedding / 產圖都算）。

    供背景插話（功能二）判斷「現在有人在用」→ 讓位、不硬擠。
    """
    return _GPU_LOCK.locked()


def current_owner() -> str | None:
    """目前是誰佔著 GPU（"llm" / "imagegen"）；沒人持有回 None。"""
    return _holder


def imagegen_busy() -> bool:
    """目前是不是「產圖」佔著 GPU。

    跟 `stream_busy()` 的差別：後者只回答「有沒有人在用」，本函式回答「是不是那個
    會持有數十分鐘的工作」。前景路徑（/askai）用它決定要照常排隊、還是直接回一句
    「正在產圖」——差別是使用者看到「機器人壞了」還是「機器人在忙」。
    """
    return _holder == "imagegen"


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
