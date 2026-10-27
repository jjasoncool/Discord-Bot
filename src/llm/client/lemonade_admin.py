"""Lemonade 後端的管理 API（載入、卸載）與後端壞掉時的自癒：OpenAI 相容流程以外、只有 Lemonade 才有的事都在這裡。

架構定位：技術層（llm/client），只依賴 httpx、標準庫與同層的 http_client（例外型別、錯誤分類）；http_client 不認得這裡。
  上層：`backend_admin.admin_for`（建 `LlmHttpClient` 的地方依後端決定要不要掛）；
  介面層的 discord_bot 用 `set_heal_listener` 接自癒事件去私訊群主。
  下層：Lemonade 的 /api/v1/load、/api/v1/unload。

介面：
- `LemonadeAdmin.ensure_loaded(model=, options=, load_timeout=)`：確認已用指定選項載入；行程內快取，同一組合只推一次。
- `LemonadeAdmin.load(...)`／`unload(model=)`：直接打管理 API（同步 HTTP，async 呼叫端包 to_thread）。
- `LemonadeAdmin.heal(model, reason)`：後端卡死或壞了時重載那顆模型；冷卻 60 秒、一小時最多 3 次，超過放棄、記 ERROR、通知一次。
- `LemonadeAdmin.unwrap(data)`：拆「200 OK 但內容是錯誤」的信封；downstream 卡死丟 `UpstreamWedge`，其他當 `LlmAPIError`。
- `set_heal_listener(fn)`／`reset_cache()`：接自癒事件（healed／failed／gave_up）；清載入快取與自癒紀錄（測試、Lemonade 被外部改動時）。

規則：
- 載入選項（recipe_options）只准放非 reserved 的選項（ctx_size、llamacpp_args）；絕不可放 Lemonade 自己管的旗標
  （--embeddings、--ctx-size、--device …）：手動帶上再加 save_options 會把模型載掛，而且永久存住。
- 自癒只重生、不持久化（save_options=False），沿用該模型最後一次載入的選項。

例外與決策：
- 載入快取與自癒紀錄放模組層級、跨 instance 共用：「已載入」是 Lemonade server 端的全域狀態，bot 內幾個 client 打的是同一台。
- 「重啟 Lemonade」做不到也不需要：重載模型＝重開那顆後端行程，顯示卡裝置掉了就是這樣救回來的。
- 冷卻與每小時上限：真的整台掛掉時狂發 load 沒用；一小時內重載三次還壞代表那張卡或驅動有問題，再重載只是蓋過去。
"""
from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Callable

import httpx

from llm.client.http_client import (
    LlmAPIError,
    LlmConnectionError,
    LlmTimeoutError,
    UpstreamWedge,
    judge_failure,
    raise_verdict,
)

logger = logging.getLogger(__name__)

#: 跨 instance 共用：(host, model, options_json) → True，代表本行程已對這個組合推過 /api/v1/load
_LOADED: dict[tuple[str, str, str], bool] = {}
_LOCK = threading.Lock()
_HEAL_COOLDOWN_S = 60.0
_HEAL_MAX_PER_HOUR = 3
_HEAL_WINDOW_S = 3600.0
_LAST_HEAL: dict[tuple[str, str], float] = {}
_HEAL_HISTORY: dict[tuple[str, str], list[float]] = {}
_GAVE_UP_AT: dict[tuple[str, str], float] = {}
#: 自癒事件的回呼（healed／failed／gave_up），介面層接去私訊管理員；可能從任何執行緒被叫，接的人自己排回 event loop
_HEAL_LISTENER: Callable[[dict[str, Any]], None] | None = None


def reset_cache() -> None:
    """清掉載入快取與自癒紀錄（測試、Lemonade 端被外部改動時手動觸發 re-ensure 用）。"""
    with _LOCK:
        _LOADED.clear()
        _LAST_HEAL.clear()
        _HEAL_HISTORY.clear()
        _GAVE_UP_AT.clear()


def set_heal_listener(listener: Callable[[dict[str, Any]], None] | None) -> None:
    """接自癒事件：`{"outcome": "healed"|"failed"|"gave_up", "model", "reason", "heals"}`。"""
    global _HEAL_LISTENER
    _HEAL_LISTENER = listener


def _emit_heal_event(event: dict[str, Any]) -> None:
    if _HEAL_LISTENER is None:
        return
    try:
        _HEAL_LISTENER(event)
    except Exception as exc:  # 邊界：通知只是附帶的，失敗不能影響原本的請求
        logger.warning("Lemonade 自癒事件通知失敗：%s", exc)


class LemonadeAdmin:
    """Lemonade 的管理 API 與自癒；給 `LlmHttpClient(admin=…)`。"""

    def __init__(self, host: str, *, api_key: str = "no-auth", heal_load_timeout: float = 120.0) -> None:
        self._host = host.rstrip("/")
        # 自癒重載模型最多等幾秒：拿著 GPU 閘門的呼叫端給短一點，後端卡住時早點放鎖
        self._heal_load_timeout = heal_load_timeout
        self._http = httpx.Client(headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})

    # ---------- 給 LlmHttpClient 的兩件事 ----------

    def unwrap(self, data: Any) -> Any:
        """拆 Lemonade 風格的「200 OK + {"error": {...}}」信封：downstream 卡死（network_error）丟 `UpstreamWedge`
        讓薄迴圈重載再送；其他錯誤型別當 `LlmAPIError(status=None)`；不是信封就原樣回。"""
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

    def heal(self, model: str, reason: str = "") -> bool:
        """後端卡死或壞了：重發 /api/v1/load 把那顆後端行程重開。沿用該 model 最後一次載入的 recipe_options（從快取取），
        save_options=False 只重生、不覆寫 recipe_options.json。回 True＝已重載；False＝冷卻中、一小時內已太多次、沒 model、重載失敗。"""
        if not model:
            return False
        key = (self._host, model)
        now = time.monotonic()
        allowed = False
        gave_up = False
        recipe: dict[str, Any] = {}
        with _LOCK:
            last = _LAST_HEAL.get(key)
            if last is not None and now - last < _HEAL_COOLDOWN_S:
                return False
            history = [t for t in _HEAL_HISTORY.get(key, []) if now - t < _HEAL_WINDOW_S]
            _HEAL_HISTORY[key] = history
            if len(history) >= _HEAL_MAX_PER_HOUR:
                # 放棄只講一次（一小時內）：之後的請求照一般錯誤收尾，不再每次都吵
                if now - _GAVE_UP_AT.get(key, -_HEAL_WINDOW_S) >= _HEAL_WINDOW_S:
                    _GAVE_UP_AT[key] = now
                    gave_up = True
            else:
                _LAST_HEAL[key] = now
                history.append(now)
                allowed = True
                for (cached_host, cached_model, opts_json) in _LOADED:
                    if cached_host == self._host and cached_model == model:
                        try:
                            parsed = json.loads(opts_json)
                        except ValueError:
                            continue
                        if isinstance(parsed, dict):
                            recipe = parsed
        if gave_up:
            logger.error("Lemonade backend 自癒放棄：model=%s 一小時內已重載 %d 次還是壞（%s），不再自動重載，請檢查那張卡或驅動",
                         model, _HEAL_MAX_PER_HOUR, reason or "沒有錯誤內容")
            _emit_heal_event({"outcome": "gave_up", "model": model, "reason": reason, "heals": _HEAL_MAX_PER_HOUR})
            return False
        if not allowed:
            return False
        try:
            self.load(model_name=model, recipe_options=recipe, timeout=self._heal_load_timeout, save_options=False)
        except (LlmAPIError, LlmConnectionError, LlmTimeoutError) as exc:
            logger.warning("Lemonade backend 自癒重載失敗 model=%s：%s", model, exc)
            _emit_heal_event({"outcome": "failed", "model": model, "reason": f"{reason} / 重載失敗：{exc}"[:300],
                              "heals": len(_HEAL_HISTORY.get(key, []))})
            return False
        logger.warning("Lemonade backend 自癒：後端卡死或壞了（%s），已重發 /api/v1/load 重載 model=%s",
                       reason or "upstream wedge", model)
        _emit_heal_event({"outcome": "healed", "model": model, "reason": reason or "upstream wedge",
                          "heals": len(_HEAL_HISTORY.get(key, []))})
        return True

    # ---------- 管理 API ----------

    def ensure_loaded(self, *, model: str, options: dict[str, Any] | None, load_timeout: float = 180.0) -> None:
        """確認 Lemonade 已用指定 `options` 載入 `model`，沒有就觸發載入；同一組合本行程只推一次（Lemonade 對沒變的選項
        通常會略過，但每次 chat／embed 都打一次管理 API 還是浪費）。"""
        if not options:
            return
        opts_json = json.dumps(options, sort_keys=True)
        cache_key = (self._host, model, opts_json)
        with _LOCK:
            if cache_key in _LOADED:
                return
            self.load(model_name=model, recipe_options=options, timeout=load_timeout)
            _LOADED[cache_key] = True
            logger.info("Lemonade model loaded: model=%s recipe_options=%s", model, options)

    def load(self, *, model_name: str, recipe_options: dict[str, Any], timeout: float, save_options: bool = True) -> None:
        """POST /api/v1/load：平鋪參數（ctx_size 等直接在 top-level，翻成 llama-server 旗標）。載入大模型可能 30～60 秒，
        逾時由呼叫端給。save_options=True 會把選項持久化進 Lemonade 的 recipe_options.json，之後每次載入都吃對的 ctx。"""
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

    def _post(self, path: str, body: dict[str, Any], *, timeout: float, label: str) -> None:
        """管理 API 的 POST：不重試（失敗多半是設定問題），例外分類和一般請求同一份。"""
        url = self._host + path
        try:
            resp = self._http.post(url, json=body, timeout=timeout)
        except httpx.RequestError as exc:
            raise_verdict(judge_failure(exc, label=f"Lemonade {label}", path=path, attempt=0, max_retries=0), exc)
        if not resp.is_success:
            raise LlmAPIError(f"HTTP {resp.status_code}", status=resp.status_code, detail=resp.text)
