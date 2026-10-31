"""Lemonade 後端的管理 API（載入、卸載）與後端壞掉時的自癒：OpenAI 相容流程以外、只有 Lemonade 才有的事都在這裡。

架構定位：技術層（llm/client），只依賴 httpx、標準庫與同層的 http_client（例外型別、錯誤分類）；http_client 不認得這裡。
  上層：`backend_admin.admin_for`（建 `LlmHttpClient` 的地方依後端決定要不要掛）；`LLMService.replaced_backends`／
  `probe_backend`（介面層每分鐘問放棄中的模型行程換了沒、重新偵測時單獨驗一顆）；介面層 `commands.owner_alert_commands`
  用 `allow_heal` 打開自癒、`reset_cache`／`release` 清紀錄。
  下層：Lemonade 的 /api/v1/load、/api/v1/unload、/api/v1/health，重開後驗證打的 OpenAI 相容端點；自癒放棄、重開失敗、
  重開了還是壞經 `utils.owner_alerts.emit` 交給介面層（私訊群主＋「重新偵測」按鈕），救回來 `inform` 一行。

介面：
- `LemonadeAdmin.ensure_loaded(model=, options=, load_timeout=)`：確認已用指定選項載入；行程內快取，同一組合只推一次。
- `LemonadeAdmin.load(...)`／`unload(model=)`：直接打管理 API（同步 HTTP，async 呼叫端包 to_thread）。
- `LemonadeAdmin.heal(model, reason, kind=)`：後端壞了時把那顆模型的行程重開（unload 再 load），確認行程換了、再真的算一次，
  都過了才回 True、通知「已重開、能算」；冷卻 60 秒（從重開結束算）、一小時最多 3 次，用完或第 3 次還是壞就放棄。
  `kind` 是呼叫端那個請求的種類（embedding／llm／reranking），health 查不到類型時用它驗證。
- `LemonadeAdmin.restart(model=, recipe=)`／`verify(model=, kind=)`／`backend(model)`：重開、最小請求驗證、health 裡那顆模型的那一筆。
- `LemonadeAdmin.check(model)`：單獨驗一顆模型（照 health 或上次自癒記下的類型送最小請求），重新偵測測主模型以外的用。
- `LemonadeAdmin.replaced_since_give_up()`：放棄中的模型裡，行程換掉的（群主重啟了 Lemonade 或手動重載）；回報一次就以新行程為準。
- `LemonadeAdmin.unwrap(data)`：拆「200 OK 但內容是錯誤」的信封；downstream 卡死丟 `UpstreamWedge`，其他當 `LlmAPIError`。
- `allow_heal(enabled)`：這個行程要不要自癒（預設不要）。
- `reset_cache()`：清載入快取與全部自癒紀錄（含放棄）：群主按「重新偵測」、測試、Lemonade 被外部改動時。
- `release(models)`：只清這幾顆的自癒紀錄（自動重測確認它們好了）。
- `heal_notice(outcome, model, reason, heals, pids)`：四種結果給群主看的一行（管理員訊息可以帶技術原因）。
- `heal_summary()`：狀態面板用的一行：誰放棄中、這一小時重開了幾次。
- `LemonadeAdmin.close()`：關掉管理 API 的連線池（探測這種用完就丟的呼叫端用）。

規則：
- 載入選項（recipe_options）只准放非 reserved 的選項（ctx_size、llamacpp_args）；絕不可放 Lemonade 自己管的旗標
  （--embeddings、--ctx-size、--device …）：手動帶上再加 save_options 會把模型載掛，而且永久存住。
- 自癒的載入不持久化（save_options=False），沿用該模型最後一次載入的選項。
- unload 一定帶 model_name：body 沒有 model_name 時 Lemonade 會卸載全部模型。
- 重開與驗證都在呼叫端那條請求裡做：拿著 GPU 閘門的呼叫端（聊天記憶寫入）就是拿著閘門重開，每一步等多久照 `heal_load_timeout`。

例外與決策：
- 重開＝unload 再 load：Lemonade 的 load 對還活著、選項相同的模型什麼都不做、直接回 200（2026.43.3 的 `Router::load_model`），
  顯示卡裝置掉了的行程照樣活著、每個請求都 500，只送 load 永遠救不回來；它自己的 watchdog 也不認得這種壞法。
- 「救回來」要看到行程換了、而且真的算得出來：只看管理 API 回 200 會把沒重開說成恢復，還把警報解除。類型（health 的 type，
  沒有就用呼叫端交的 kind）都不知道時不算救回。驗證直接打端點送最小請求，不走 `LlmHttpClient`（那條路失敗會再叫 heal），
  也不能用服務層的探測（技術層不往上 import）。
- 放棄就停：三次真的重開都救不回來，代表那張卡或驅動有問題，再試只是一直吵。之後只有群主按「重新偵測」（`reset_cache`），
  或介面層發現行程換了、重測確認好了（`release`）才會再救。
- 只有一個行程自癒（bot，由介面層 `allow_heal(True)`）：search-mcp、docker exec 的批次各有一份紀錄、又沒有人收通知，
  各自重開會互相換掉對方看到的行程、讓「行程換了＝群主重啟了」失準；它們碰到同樣的錯只照原錯誤收尾，等 bot 這邊救。
- 冷卻從重開結束算、重開中別人進來直接回 False：一次重開（卸載、載入大模型、驗證）可能超過冷卻時間，從開始算會讓同一個
  請求的重試又重開一次。世代號分兩層：`reset_cache` 換全部的、`release` 只換放掉的那幾顆；在那之前開始的自癒做完時
  不把放棄、冷卻寫回去，別顆正在跑的照常寫。
- 載入快取與自癒紀錄放模組層級、跨 instance 共用：「已載入」是 Lemonade server 端的全域狀態，bot 內幾個 client 打的是同一台。
- `_LOCK` 只保護那幾個 dict，載入模型（30～180 秒的 HTTP）在每個組合自己的鎖底下做：查快取、看狀態、清紀錄都在 event loop 上叫，
  不能被別的執行緒正在載入的模型擋住。
"""
from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Callable, Iterable, Optional

import httpx

from llm.client.http_client import (
    LlmAPIError,
    LlmConnectionError,
    LlmTimeoutError,
    UpstreamWedge,
    backend_message,
    judge_failure,
    raise_verdict,
)
from utils import owner_alerts

logger = logging.getLogger(__name__)

#: 看時間經過這個名字，測試換成假時鐘
_clock = time.monotonic

#: 跨 instance 共用：(host, model, options_json) → True，代表本行程已對這個組合推過 /api/v1/load
_LOADED: dict[tuple[str, str, str], bool] = {}
_LOCK = threading.Lock()
_HEAL_COOLDOWN_S = 60.0
_HEAL_MAX_PER_HOUR = 3
_HEAL_WINDOW_S = 3600.0
_LAST_HEAL: dict[tuple[str, str], float] = {}
_HEAL_HISTORY: dict[tuple[str, str], list[float]] = {}
#: 放棄中的模型：(host, model) → (放棄的時刻, 當時的行程 pid；查不到是 None)；只有 reset_cache／release 清
_GAVE_UP: dict[tuple[str, str], tuple[float, Optional[int]]] = {}
#: 正在重開的模型：重開中別的請求進來不再重開一次
_HEALING: set[tuple[str, str]] = set()
#: 上次自癒時那個請求的種類（health 查不到類型時，重新偵測單獨驗這顆用）
_KINDS: dict[tuple[str, str], str] = {}
#: 世代號：reset_cache 換全部的、release 只換那幾顆的；在那之前開始的自癒做完時不寫回放棄與冷卻
_GENERATION = 0
_MODEL_GENERATION: dict[tuple[str, str], int] = {}
#: 這個行程要不要自癒（`allow_heal`）
_HEAL_ENABLED = False
#: 每個 (host, model, options) 自己的載入鎖：同一組合同時只載一次，但不擋別人查快取
_LOAD_LOCKS: dict[tuple[str, str, str], threading.Lock] = {}
#: 群主通知的狀況種類（`utils.owner_alerts`）；key 是模型名稱
ALERT_KIND = "lemonade"
#: 查 /api/v1/health 最多等幾秒（只用來比對行程與類型，查不到就當不知道）
_HEALTH_TIMEOUT_S = 5.0
#: 重開後真的算一次：類型 → (端點, 最小請求, 回應裡要有東西的 key)
_VERIFY: dict[str, tuple[str, Callable[[str], dict[str, Any]], str]] = {
    "embedding": ("/v1/embeddings", lambda m: {"model": m, "input": "ping"}, "data"),
    "llm": ("/v1/chat/completions",
            lambda m: {"model": m, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 1, "stream": False},
            "choices"),
    "reranking": ("/v1/rerank", lambda m: {"model": m, "query": "ping", "documents": ["ping"], "top_n": 1}, "results"),
}
#: 重開、驗證時會丟的例外：都當「這次沒救回來」
_HEAL_ERRORS = (LlmAPIError, LlmConnectionError, LlmTimeoutError, UpstreamWedge)


def allow_heal(enabled: bool) -> None:
    """這個行程要不要自癒：bot 的群主通知 cog 載入時打開、卸載時關掉；別的行程不開（見模組說明）。"""
    global _HEAL_ENABLED
    _HEAL_ENABLED = bool(enabled)


def reset_cache() -> None:
    """清掉載入快取與全部自癒紀錄（含放棄）：群主按「重新偵測」（Lemonade 修好、重啟後 bot 才會再救、再推載入選項）、測試、
    Lemonade 端被外部改動時手動觸發 re-ensure 用。"""
    global _GENERATION
    with _LOCK:
        _GENERATION += 1
        _LOADED.clear()
        _LAST_HEAL.clear()
        _HEAL_HISTORY.clear()
        _GAVE_UP.clear()


def release(models: Iterable[str]) -> None:
    """只清這幾顆模型的自癒紀錄（放棄、次數、冷卻）：自動重測確認它們的新行程能算之後叫；別顆的紀錄與正在跑的自癒照舊。"""
    names = set(models)
    with _LOCK:
        keys = {k for table in (_GAVE_UP, _HEAL_HISTORY, _LAST_HEAL) for k in table if k[1] in names}
        keys |= {k for k in _HEALING if k[1] in names}
        for key in keys:
            _MODEL_GENERATION[key] = _MODEL_GENERATION.get(key, 0) + 1
            for table in (_GAVE_UP, _HEAL_HISTORY, _LAST_HEAL):
                table.pop(key, None)


def _generation(key: tuple[str, str]) -> tuple[int, int]:
    """這顆模型現在的世代號（呼叫端拿著 `_LOCK`）。"""
    return _GENERATION, _MODEL_GENERATION.get(key, 0)


def _pid_text(pids: Optional[tuple[Optional[int], Optional[int]]]) -> str:
    if not pids:
        return ""
    old, new = pids
    return f"（行程 {old if old is not None else '?'}→{new if new is not None else '?'}）"


def heal_notice(outcome: str, model: str, reason: str = "", heals: int | None = None,
                pids: Optional[tuple[Optional[int], Optional[int]]] = None) -> str:
    """自癒結果 → 給群主看的一行。"""
    model = str(model or "?")
    reason = str(reason or "").strip() or "沒有錯誤內容"
    moved = _pid_text(pids)
    if outcome == "healed":
        return (f"🔧 Lemonade 自癒：{model} 回錯（{reason}），已重開那顆模型{moved}並確認能算；這一小時第 {heals} 次。"
                "常發生代表那張卡或驅動有問題。")
    if outcome == "still_broken":
        return (f"⚠️ Lemonade 自癒：{model} 重開了{moved}還是壞（{reason}），這一小時第 {heals}／{_HEAL_MAX_PER_HOUR} 次；"
                "下次再碰到會再重開（至少隔一分鐘），一直這樣代表那張卡或驅動有問題。")
    if outcome == "failed":
        return (f"⚠️ Lemonade 自癒失敗：{model} 重開沒成功（{reason}），這一小時第 {heals}／{_HEAL_MAX_PER_HOUR} 次；"
                "下次再碰到會再試，請看看 Lemonade，修好後按「重新偵測」。")
    if outcome == "gave_up":
        return (f"🛑 Lemonade 自癒放棄：{model} 一小時內重開 {heals} 次還是壞（{reason}），bot 不再自動重開。"
                "請檢查那張顯示卡或驅動（可能要重開機）；修好、重啟 Lemonade 之後 bot 會自己發現並重新偵測，也可以按「重新偵測」。")
    return f"Lemonade 自癒事件：{outcome} {model}（{reason}）"


def heal_summary() -> str:
    """狀態面板用的一行：哪顆模型放棄中（幾分鐘前）、哪顆這一小時重開了幾次；都沒有就是正常。"""
    now = _clock()
    with _LOCK:
        gave_up = {key: at for key, (at, _pid) in _GAVE_UP.items()}
        recent = {key: [t for t in ts if now - t < _HEAL_WINDOW_S] for key, ts in _HEAL_HISTORY.items()}
    parts = [f"{model} 已放棄自動重開（{int((now - at) // 60)} 分鐘前；按重新偵測，或重啟 Lemonade 後 bot 會自己重測）"
             for (_, model), at in gave_up.items()]
    parts += [f"{key[1]} 這一小時重開 {len(ts)} 次" for key, ts in recent.items() if ts and key not in gave_up]
    return "；".join(parts) if parts else "這一小時沒有重開過"


def _pid(entry: Optional[dict[str, Any]]) -> Optional[int]:
    pid = entry.get("pid") if isinstance(entry, dict) else None
    return pid if isinstance(pid, int) else None


class LemonadeAdmin:
    """Lemonade 的管理 API 與自癒；給 `LlmHttpClient(admin=…)`。"""

    def __init__(self, host: str, *, api_key: str = "no-auth", heal_load_timeout: float = 120.0) -> None:
        self._host = host.rstrip("/")
        # 自癒重開、驗證每一步最多等幾秒：拿著 GPU 閘門的呼叫端給短一點，後端卡住時早點放鎖
        self._heal_load_timeout = heal_load_timeout
        self._http = httpx.Client(headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})

    # ---------- 給 LlmHttpClient 的兩件事 ----------

    def unwrap(self, data: Any) -> Any:
        """拆 Lemonade 風格的「200 OK + {"error": {...}}」信封：downstream 卡死（network_error）丟 `UpstreamWedge`
        讓薄迴圈重開再送；其他錯誤型別當 `LlmAPIError(status=None)`；不是信封就原樣回。"""
        if not isinstance(data, dict):
            return data
        err = data.get("error")
        if not isinstance(err, dict):
            return data
        err_type = str(err.get("type", "")).strip()
        err_msg = str(err.get("message", "")).strip()
        if err_type == "network_error":
            raise UpstreamWedge(f"upstream network_error: {err_msg}")
        raise LlmAPIError(
            f"upstream error envelope: type={err_type or '<unknown>'} message={err_msg or '<empty>'}",
            status=None, detail=str(data)[:1000],
        )

    def heal(self, model: str, reason: str = "", kind: Optional[str] = None) -> bool:
        """後端卡死或壞了：把那顆模型的行程重開，確認行程換了、再真的算一次，都過了才回 True（呼叫端可以重送）。
        沒開自癒、冷卻中、重開中、已放棄、沒 model、重開失敗、重開了還是壞都回 False，呼叫端照原錯誤收尾。"""
        if not model or not _HEAL_ENABLED:
            return False
        key = (self._host, model)
        now = _clock()
        recipe: dict[str, Any] = {}
        attempt = 0
        with _LOCK:
            if key in _GAVE_UP or key in _HEALING:
                return False
            last = _LAST_HEAL.get(key)
            if last is not None and now - last < _HEAL_COOLDOWN_S:
                return False
            if kind:
                _KINDS[key] = kind
            generation = _generation(key)
            history = [t for t in _HEAL_HISTORY.get(key, []) if now - t < _HEAL_WINDOW_S]
            _HEAL_HISTORY[key] = history
            exhausted = len(history) >= _HEAL_MAX_PER_HOUR
            if not exhausted:
                _HEALING.add(key)
                _LAST_HEAL[key] = now
                history.append(now)
                attempt = len(history)
                recipe = self._cached_recipe(model)
        if exhausted:
            # 這一小時已經重開滿三次（每次都救回來過，但又壞）：一直掉就是卡或驅動的問題
            self._give_up(model, reason or "upstream wedge", _HEAL_MAX_PER_HOUR, _pid(self.backend(model)), generation)
            return False
        try:
            return self._restart_and_verify(model, reason, kind, recipe, attempt, generation)
        finally:
            with _LOCK:
                _HEALING.discard(key)
                if generation == _generation(key):
                    _LAST_HEAL[key] = _clock()   # 冷卻從重開結束算

    def _restart_and_verify(self, model: str, reason: str, kind: Optional[str], recipe: dict[str, Any],
                            attempt: int, generation: tuple[int, int]) -> bool:
        before = self.backend(model)
        try:
            self.restart(model=model, recipe=recipe)
        except _HEAL_ERRORS as exc:
            detail = f"{reason} / 重開失敗：{backend_message(exc) or exc}"[:300]
            if attempt >= _HEAL_MAX_PER_HOUR:
                # 記現在的行程：unload 成功、load 失敗時舊行程已經被結束，記舊的會被當成「有人重開過」
                self._give_up(model, detail, attempt, _pid(self.backend(model)), generation)
            else:
                logger.warning("Lemonade backend 自癒重開失敗 model=%s（第 %d 次）：%s", model, attempt, detail)
                owner_alerts.emit(ALERT_KIND, model, heal_notice("failed", model, detail, attempt), severity="warning")
            return False
        after = self.backend(model)
        pids = (_pid(before), _pid(after))
        try:
            if pids[0] is not None and pids[0] == pids[1]:
                raise LlmAPIError(f"行程沒換（pid {pids[0]}），Lemonade 沒有真的重開", status=None, kind="not_restarted")
            verify_kind = (after or before or {}).get("type") or kind
            if verify_kind not in _VERIFY:
                raise LlmAPIError(f"不知道 {model} 是哪一類模型（{verify_kind!r}），沒辦法確認能算", status=None,
                                  kind="unverifiable")
            self.verify(model=model, kind=verify_kind)
        except _HEAL_ERRORS as exc:
            detail = f"{reason} / 重開後：{backend_message(exc) or exc}"[:300]
            if attempt >= _HEAL_MAX_PER_HOUR:
                self._give_up(model, detail, attempt, pids[1], generation)
            else:
                logger.warning("Lemonade backend 自癒：model=%s 重開了 pid %s→%s 還是壞（第 %d 次）：%s",
                               model, pids[0], pids[1], attempt, detail)
                owner_alerts.emit(ALERT_KIND, model, heal_notice("still_broken", model, detail, attempt, pids),
                                  severity="warning")
            return False
        logger.warning("Lemonade backend 自癒：後端卡死或壞了（%s），已重開 model=%s（pid %s→%s）並確認能算",
                       reason or "upstream wedge", model, pids[0], pids[1])
        owner_alerts.inform(ALERT_KIND, model, heal_notice("healed", model, reason or "upstream wedge", attempt, pids))
        return True

    def _cached_recipe(self, model: str) -> dict[str, Any]:
        """這顆模型最後一次載入的選項（呼叫端拿著 `_LOCK`）；沒推過就空的，Lemonade 用它存的選項。"""
        recipe: dict[str, Any] = {}
        for (cached_host, cached_model, opts_json) in _LOADED:
            if cached_host == self._host and cached_model == model:
                try:
                    parsed = json.loads(opts_json)
                except ValueError:
                    continue
                if isinstance(parsed, dict):
                    recipe = parsed
        return recipe

    def _give_up(self, model: str, reason: str, heals: int, pid: Optional[int], generation: tuple[int, int]) -> None:
        """記下放棄（連同當時的行程，之後比對換了沒）、記 ERROR、通知一次；別的執行緒已經放棄過、或這段期間群主按了
        重新偵測（世代號換了）就不寫。"""
        with _LOCK:
            key = (self._host, model)
            if key in _GAVE_UP or generation != _generation(key):
                return
            _GAVE_UP[key] = (_clock(), pid)
        logger.error("Lemonade backend 自癒放棄：model=%s 一小時內重開 %d 次還是壞（%s），不再自動重開，請檢查那張卡或驅動",
                     model, heals, reason or "沒有錯誤內容")
        owner_alerts.emit(ALERT_KIND, model, heal_notice("gave_up", model, reason, heals))

    def restart(self, *, model: str, recipe: dict[str, Any]) -> None:
        """把那顆模型的行程重開：先 unload（Lemonade 會結束那個行程）、再照原本的選項 load。模型已經不在（404）就直接載。"""
        try:
            self._post("/api/v1/unload", {"model_name": model}, timeout=self._heal_load_timeout, label=f"unload {model}")
        except LlmAPIError as exc:
            if exc.status != 404:
                raise
        self.load(model_name=model, recipe_options=recipe, timeout=self._heal_load_timeout, save_options=False)

    def verify(self, *, model: str, kind: Optional[str]) -> None:
        """真的算一次：照類型送最小請求；失敗或類型不認得都丟 `LlmAPIError`（或連線例外）。"""
        spec = _VERIFY.get(kind or "")
        if spec is None:
            raise LlmAPIError(f"不知道 {model} 是哪一類模型（{kind!r}），沒辦法驗證", status=None, kind="unverifiable")
        path, body, key = spec
        data = self.unwrap(self._post(path, body(model), timeout=self._heal_load_timeout, label=f"verify {model}"))
        if not (isinstance(data, dict) and data.get(key)):
            raise LlmAPIError(f"{path} 回應沒有 {key}", status=None, detail=str(data)[:500], kind="empty")

    def check(self, model: str) -> None:
        """單獨驗一顆模型能不能算（不重開）：類型照 health，沒載入就照上次自癒記下的；都不知道丟 `LlmAPIError`。
        沒載入的模型 Lemonade 收到請求會自己載入，所以這也是「載不載得起來」的測試。"""
        with _LOCK:
            remembered = _KINDS.get((self._host, model))
        self.verify(model=model, kind=(self.backend(model) or {}).get("type") or remembered)

    def backend(self, model: str) -> Optional[dict[str, Any]]:
        """/api/v1/health 裡這顆模型的那一筆（pid、type…）；沒載入或查不到回 None。"""
        loaded = self._loaded_backends()
        return loaded.get(model) if loaded is not None else None

    def replaced_since_give_up(self) -> list[str]:
        """放棄中的模型裡，行程已經換掉的（群主重啟了 Lemonade、手動重載，或模型被卸載了）。回報一次就以現在的行程為準，
        同一個行程不會每次都報。沒有放棄中的模型就不打 health；查不到 health 回空（下一輪再看）。放棄時沒查到行程的，
        這次查到的就當基準。"""
        with _LOCK:
            watched = {model: pid for (host, model), (_at, pid) in _GAVE_UP.items() if host == self._host}
        if not watched:
            return []
        loaded = self._loaded_backends()
        if loaded is None:
            return []
        replaced = []
        for model, pid in watched.items():
            current = _pid(loaded.get(model))
            if pid is not None and current == pid:
                continue
            with _LOCK:
                key = (self._host, model)
                if key in _GAVE_UP and _GAVE_UP[key][1] == pid:
                    _GAVE_UP[key] = (_GAVE_UP[key][0], current)
            if pid is not None:
                replaced.append(model)
        return replaced

    def _loaded_backends(self) -> Optional[dict[str, dict[str, Any]]]:
        """/api/v1/health 的 all_models_loaded，照模型名稱；查不到回 None。"""
        try:
            resp = self._http.get(self._host + "/api/v1/health", timeout=_HEALTH_TIMEOUT_S)
            data = resp.json() if resp.is_success else None
        except (httpx.RequestError, ValueError) as exc:
            logger.info("Lemonade health 查不到：%s", exc)
            return None
        if not isinstance(data, dict):
            return None
        entries = data.get("all_models_loaded") or []
        return {e["model_name"]: e for e in entries if isinstance(e, dict) and isinstance(e.get("model_name"), str)}

    # ---------- 管理 API ----------

    def ensure_loaded(self, *, model: str, options: dict[str, Any] | None, load_timeout: float = 180.0) -> None:
        """確認 Lemonade 已用指定 `options` 載入 `model`，沒有就觸發載入；同一組合本行程只推一次（Lemonade 對沒變的選項
        會略過，但每次 chat／embed 都打一次管理 API 還是浪費）。"""
        if not options:
            return
        opts_json = json.dumps(options, sort_keys=True)
        cache_key = (self._host, model, opts_json)
        with _LOCK:
            if cache_key in _LOADED:
                return
            load_lock = _LOAD_LOCKS.setdefault(cache_key, threading.Lock())
        # 載入要等 30～180 秒，只鎖這一個組合：查快取、看狀態的人不必跟著等
        with load_lock:
            with _LOCK:
                if cache_key in _LOADED:
                    return
            self.load(model_name=model, recipe_options=options, timeout=load_timeout)
            with _LOCK:
                _LOADED[cache_key] = True
            logger.info("Lemonade model loaded: model=%s recipe_options=%s", model, options)

    def close(self) -> None:
        """關掉管理 API 的連線池（用完就丟的探測用；長期持有的 client 不必關）。"""
        self._http.close()

    def load(self, *, model_name: str, recipe_options: dict[str, Any], timeout: float, save_options: bool = True) -> None:
        """POST /api/v1/load：平鋪參數（ctx_size 等直接在 top-level，翻成 llama-server 旗標）。載入大模型可能 30～60 秒，
        逾時由呼叫端給。save_options=True 會把選項持久化進 Lemonade 的 recipe_options.json，之後每次載入都吃對的 ctx。
        模型已載入、選項相同時 Lemonade 什麼都不做（不會重開行程）。"""
        body: dict[str, Any] = {"model_name": model_name, **dict(recipe_options), "save_options": save_options}
        self._post("/api/v1/load", body, timeout=timeout, label=f"load {model_name}")

    def unload(self, *, model: str, timeout: float = 60.0) -> None:
        """POST /api/v1/unload：把 model 從 VRAM 卸下。卸載後不必載回去：下一個請求 Lemonade 會自動重新載入，持久化的選項不會丟。
        順手清掉這顆 model 的載入快取（「本行程推過 load」的假設不再成立），只清這顆、不殃及別的。"""
        self._post("/api/v1/unload", {"model_name": model}, timeout=timeout, label=f"unload {model}")
        with _LOCK:
            for key in [k for k in _LOADED if k[0] == self._host and k[1] == model]:
                _LOADED.pop(key, None)
            _LAST_HEAL.pop((self._host, model), None)
        logger.info("Lemonade model unloaded: model=%s", model)

    def _post(self, path: str, body: dict[str, Any], *, timeout: float, label: str) -> Any:
        """管理 API 與驗證請求的 POST：不重試（失敗多半是設定問題），例外分類和一般請求同一份；回 JSON（不是 JSON 回 None）。"""
        url = self._host + path
        try:
            resp = self._http.post(url, json=body, timeout=timeout)
        except httpx.RequestError as exc:
            raise_verdict(judge_failure(exc, label=f"Lemonade {label}", path=path, attempt=0, max_retries=0), exc)
        if not resp.is_success:
            raise LlmAPIError(f"HTTP {resp.status_code}", status=resp.status_code, detail=resp.text)
        try:
            return resp.json()
        except ValueError:
            return None
