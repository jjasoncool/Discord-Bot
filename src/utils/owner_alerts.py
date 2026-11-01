"""要群主介入的狀況：下層發警報，介面層把它變成私訊＋「重新偵測」按鈕；同一張登記表也餵「機器人狀態」。

架構定位：基礎層（utils），只依賴標準庫，不 import discord。
  上層：發警報的技術層與服務層（Lemonade 自癒放棄；之後的資料庫、容器沒消息、Discord 權限）用 `emit`／`inform`；
       介面層的 `commands.owner_alert_commands` 用 `set_listener` 接通知、`register` 登記各種狀況的重測與狀態、
       `retest`／`active`／`kinds` 回應按鈕與面板。
  下層：無。

介面：
- `emit(kind, key, text, *, severity="error") -> bool`：發一則警報，任何執行緒都能叫。同一把 (kind, key) 在
  `RESEND_SECONDS` 內只送一次（文字會更新、不重送），嚴重度升高（warning → error）照送；回 True＝這次有送出去。
- `inform(kind, key, text)`：一行通知、沒有按鈕，順便解除同一把的警報（例：自癒成功）。
- `set_listener(fn)`：介面層接通知；接上時把還沒送的補送。fn 可能在任何執行緒被叫，自己排回 event loop。
- `register(kind, *, title, retest=None, status=None)`：登記一種狀況：面板上的名稱、重測函式（async，吃 key、
  回 `RetestResult`）、狀態函式（回一行字或 `Status(level, text)`，sync 或 async 都可以）。
- `retest(kind, key) -> RetestResult`：跑登記的重測；成功就解除那一把。
- `status_of(kind) -> Status`：那種狀況現在的燈號與一行說明：有 error 警報＝alert（紅）、有 warning 警報＝至少 watch（黃）、
  其餘照狀態函式回的（只回字串就算 ok）；`status_line(kind)` 只拿說明那一行。
- `active()`／`resolve(kind, key)`／`kinds()`／`title(kind)`；`reset()` 清空（測試用）。

規則：
- 通知群主要人介入只走這裡（守衛擋別處再寫一個 `notify_owner_*`）；文案由發出的那層寫，管理員訊息可以帶技術原因。
- `key` 會放進按鈕的 custom_id：只留字母、數字、`.`、`-`、`_`、`*`，其他字元換成 `_`，最長 60 字。

例外與決策：
- 警報只記在記憶體：重啟就忘。重啟本身就是一次重測，還在壞的下一輪會再發。
- 同一把一小時只送一次，沿用 Lemonade「放棄只講一次」；解除之後再壞會馬上再送。嚴重度升高是例外：先送了「還會再試」的警告，
  之後「放棄了、要你處理」不能被去重吃掉。
- 沒接 listener 的行程（search-mcp 這類不跑介面層的）通知送不出去，待送的只留最近 `_PENDING_MAX` 則；發警報的那層自己有寫 log。
"""
from __future__ import annotations

import inspect
import logging
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger(__name__)

#: 同一把警報多久內不重送（秒）
RESEND_SECONDS = 3600.0
#: 看時間經過這個名字，測試換成假時鐘
_clock = time.monotonic

_KEY_BAD = re.compile(r"[^A-Za-z0-9._*\-]")
_KEY_MAX = 60
#: 嚴重度高低：升高時不受一小時去重限制
_SEVERITY_RANK = {"info": 0, "warning": 1, "error": 2}
#: listener 一直沒接上時最多留幾則待送
_PENDING_MAX = 50


@dataclass(frozen=True)
class Alert:
    kind: str
    key: str
    text: str
    severity: str      # "error"／"warning"＝要人介入（掛按鈕）；"info"＝一行通知
    since: float       # `_clock()` 的時刻，算「多久了」
    at: float          # `time.time()`，給訊息上的時間


@dataclass(frozen=True)
class RetestResult:
    ok: bool
    text: str = ""
    #: 這次根本沒測到（例：顯示卡被別的工作佔著）：不是壞了，介面不能寫成「還是壞」
    untested: bool = False


#: 燈號由輕到重；面板排序與整體顏色都照這個順序
LEVELS = ("ok", "watch", "alert")


@dataclass(frozen=True)
class Status:
    """一種狀況現在的燈號：ok（綠、正常）、watch（黃、觀察中：自己會好、或剛好過）、alert（紅、要人處理）。"""
    level: str
    text: str = ""

    @property
    def rank(self) -> int:
        return LEVELS.index(self.level) if self.level in LEVELS else len(LEVELS)


Retest = Callable[[str], Awaitable[RetestResult]]
StatusFn = Callable[[], Any]
Listener = Callable[[Alert], None]


@dataclass
class KindSpec:
    kind: str
    title: str
    retest: Optional[Retest] = None
    status: Optional[StatusFn] = None


_LOCK = threading.Lock()
_KINDS: dict[str, KindSpec] = {}
_ACTIVE: dict[tuple[str, str], Alert] = {}
#: 每一把最後一次真的送出去的時刻與嚴重度（去重、判斷升級都看它，不看被去重吃掉的那幾則）
_LAST_SENT: dict[tuple[str, str], tuple[float, str]] = {}
#: listener 還沒接上時（bot 還在啟動）累積的通知，接上就補送
_PENDING: list[Alert] = []
_LISTENER: Optional[Listener] = None


def clean_key(key: str) -> str:
    """把 key 整理成能放進 custom_id 的樣子。"""
    cleaned = _KEY_BAD.sub("_", str(key or "").strip()) or "_"
    return cleaned[:_KEY_MAX]


def emit(kind: str, key: str, text: str, *, severity: str = "error") -> bool:
    """發一則要人介入的警報。同一把在 `RESEND_SECONDS` 內只送一次（嚴重度升高照送）；回 True＝這次有送。"""
    key = clean_key(key)
    pair = (kind, key)
    now = _clock()
    with _LOCK:
        previous = _ACTIVE.get(pair)
        alert = Alert(kind, key, text, severity, since=previous.since if previous else now, at=time.time())
        _ACTIVE[pair] = alert
        last = _LAST_SENT.get(pair)
        if last is not None and now - last[0] < RESEND_SECONDS \
                and _SEVERITY_RANK.get(severity, 2) <= _SEVERITY_RANK.get(last[1], 2):
            return False
        _LAST_SENT[pair] = (now, severity)
        listener = _LISTENER
        if listener is None:
            _queue(alert)
    if listener is not None:
        _deliver(listener, alert)
    return True


def inform(kind: str, key: str, text: str) -> None:
    """一行通知（沒有按鈕），順便解除同一把的警報。"""
    key = clean_key(key)
    resolve(kind, key)
    alert = Alert(kind, key, text, "info", since=_clock(), at=time.time())
    with _LOCK:
        listener = _LISTENER
        if listener is None:
            _queue(alert)
    if listener is not None:
        _deliver(listener, alert)


def resolve(kind: str, key: str) -> Optional[Alert]:
    """解除一把警報：之後同一把再壞會馬上再送。回被解除的那則，沒有回 None。"""
    pair = (kind, clean_key(key))
    with _LOCK:
        _LAST_SENT.pop(pair, None)
        return _ACTIVE.pop(pair, None)


def active() -> list[Alert]:
    """還沒解除的警報，先發生的在前。"""
    with _LOCK:
        return sorted(_ACTIVE.values(), key=lambda a: a.since)


def set_listener(listener: Optional[Listener]) -> None:
    """介面層接通知；接上時把累積的補送。"""
    global _LISTENER
    with _LOCK:
        _LISTENER = listener
        backlog, _PENDING[:] = list(_PENDING), []
    if listener is None:
        return
    for alert in backlog:
        _deliver(listener, alert)


def register(kind: str, *, title: str, retest: Optional[Retest] = None, status: Optional[StatusFn] = None) -> None:
    """登記一種狀況（重複登記就覆蓋，cog 重載時會這樣）。"""
    with _LOCK:
        _KINDS[kind] = KindSpec(kind, title, retest, status)


def kinds() -> list[KindSpec]:
    with _LOCK:
        return list(_KINDS.values())


def title(kind: str) -> str:
    with _LOCK:
        spec = _KINDS.get(kind)
    return spec.title if spec is not None else kind


async def retest(kind: str, key: str) -> RetestResult:
    """跑那種狀況登記的重測；成功就解除那一把。沒登記重測的回失敗。"""
    with _LOCK:
        spec = _KINDS.get(kind)
    if spec is None or spec.retest is None:
        return RetestResult(False, "這種狀況沒有重測方法")
    result = await spec.retest(clean_key(key))
    if result.ok:
        resolve(kind, key)
    return result


async def status_of(kind: str) -> Status:
    """那種狀況現在的燈號與說明：警報蓋過狀態函式（error → alert、warning → 至少 watch），狀態函式只回字串就當 ok；
    沒登記狀態函式時說明用最新那則警報的文字。狀態函式 sync、async 都可以。"""
    with _LOCK:
        spec = _KINDS.get(kind)
        alerts = sorted((a for (k, _), a in _ACTIVE.items() if k == kind), key=lambda a: a.since)
    reported = Status("ok", "")
    if spec is not None and spec.status is not None:
        try:
            value = spec.status()
            if inspect.isawaitable(value):
                value = await value
        except Exception as exc:  # 邊界：狀態只是顯示，一項查不到不該讓整個面板出不來
            logger.warning("查 %s 的狀態失敗：%s", kind, exc)
            value = Status("watch", f"查不到狀態（{type(exc).__name__}）")
        reported = value if isinstance(value, Status) else Status("ok", str(value or ""))
    level = reported.level
    if any(a.severity == "error" for a in alerts):
        level = "alert"
    elif alerts and reported.rank < Status("watch").rank:
        level = "watch"
    text = reported.text or (alerts[-1].text if alerts else "")
    return Status(level, text)


async def status_line(kind: str) -> str:
    """那種狀況現在的一行說明（`status_of` 的 text）。"""
    return (await status_of(kind)).text


def reset() -> None:
    """清空登記表、警報與 listener（測試用）。"""
    global _LISTENER
    with _LOCK:
        _KINDS.clear()
        _ACTIVE.clear()
        _LAST_SENT.clear()
        _PENDING.clear()
        _LISTENER = None


def _queue(alert: Alert) -> None:
    """listener 還沒接上：留著等接上補送，只留最近 `_PENDING_MAX` 則（呼叫端拿著 `_LOCK`）。"""
    _PENDING.append(alert)
    del _PENDING[:-_PENDING_MAX]


def _deliver(listener: Listener, alert: Alert) -> None:
    try:
        listener(alert)
    except Exception as exc:  # 邊界：通知只是附帶的，失敗不能影響發警報的那條請求
        logger.warning("群主通知送不出去（%s/%s）：%s", alert.kind, alert.key, exc)
