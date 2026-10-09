"""SearXNG async HTTP client：查詢、正規化、失敗安靜降級。

與 llm_service 保持一致使用 aiohttp。失敗（timeout / HTTP error / 網路異常）不 raise，
回傳空結果並在 meta 裡記錄 error，讓 /askai 主流程不受影響。

被擋的引擎：SearXNG 在回應的 `unresponsive_engines` 寫出哪個引擎沒回應、為什麼。真人驗證、限流、拒絕存取
這類「對方擋了我們」的，記一行 WARNING，接下來一段時間（`blocked_engine_cooldown_seconds`）先不問它。
以前 bot 只記「ok: 0 results」，duckduckgo 被真人驗證擋了幾個小時都看不出來（10-09）。
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)

#: 被擋的引擎 → 暫避到的時刻（`time.monotonic()`），整個行程共用
_blocked_until: dict[str, float] = {}
#: 這些原因代表對方擋了我們，不是一時連不上（逾時、連線錯誤照常重試）。SearXNG 自己暫停的會寫「Suspended: 原因」
#: ——逾時、HTTP 錯誤也會被它暫停幾秒（Suspended: timeout），所以看原因本身，不能看到 Suspended 就算被擋
_BLOCK_MARKERS = ("captcha", "too many requests", "access denied")


def _usable_engines(engines: str) -> tuple[str, list[str]]:
    """拿掉還在暫避的引擎，回傳 (要送的 engines, 這次略過的)。全被擋時照原樣送：總比不查好，也讓 SearXNG 回報最新狀況。"""
    names = [name.strip() for name in engines.split(",") if name.strip()]
    now = time.monotonic()
    skipped = [name for name in names if _blocked_until.get(name, 0.0) > now]
    usable = [name for name in names if name not in skipped]
    if not usable:
        return engines, []
    return ",".join(usable), skipped


def _note_unresponsive(items: Any, settings: Any, log: logging.Logger) -> list[list[str]]:
    """記下這次沒回應的引擎；被擋的開始暫避（第一次才記 WARNING，暫避期間不重複記）。"""
    reported: list[list[str]] = []
    now = time.monotonic()
    for item in items or []:
        if not isinstance(item, (list, tuple)) or not item:
            continue
        name = str(item[0])
        reason = str(item[1]) if len(item) > 1 else ""
        reported.append([name, reason])
        if any(marker in reason.lower() for marker in _BLOCK_MARKERS):
            if _blocked_until.get(name, 0.0) <= now:
                log.warning("SearXNG 引擎 %s 被擋（%s），接下來 %d 分鐘先不問它",
                            name, reason, int(settings.blocked_engine_cooldown_seconds // 60))
            _blocked_until[name] = now + settings.blocked_engine_cooldown_seconds
        else:
            log.info("SearXNG 引擎 %s 這次沒回應：%s", name, reason)
    return reported


@dataclass(frozen=True)
class WebResult:
    """正規化後的單筆搜尋結果。"""

    title: str
    url: str
    snippet: str
    engine: str
    published_date: str | None = None


@dataclass(frozen=True)
class WebRetrievalOutcome:
    """一次搜尋的完整輸出（含結果與觀測用 meta）。"""

    results: list[WebResult]
    meta: dict[str, Any]


async def fetch_web_results(
    question: str,
    *,
    settings: Any,  # AskAIWebSettings（以 Any 標記避免 circular import）
    engines: str | None = None,
    categories: str | None = None,
    limit: int | None = None,
    time_range: str | None = None,
    language: str | None = None,
    logger_override: logging.Logger | None = None,
) -> WebRetrievalOutcome:
    """打 SearXNG 取回搜尋結果。

    engines / categories / limit / time_range / language 未指定時沿用 settings 預設。
    失敗不 raise：回空 results + meta.error 標記原因。
    """
    log = logger_override or logger
    top_k = limit if limit is not None else settings.top_k
    effective_engines, skipped_engines = _usable_engines(
        engines if engines is not None else settings.default_engines
    )
    effective_language = language if language is not None else settings.language

    params: dict[str, str] = {
        "q": question,
        "format": "json",
        "language": effective_language,
        "engines": effective_engines,
        "safesearch": str(settings.safesearch),
    }
    if categories:
        params["categories"] = categories
    if time_range:
        params["time_range"] = time_range

    meta: dict[str, Any] = {
        "enabled": True,
        "query": question,
        "engines": effective_engines,
        "categories": categories,
        "time_range": time_range,
        "language": effective_language,
        "result_count": 0,
        "elapsed_ms": 0,
        "error": None,
        "skipped_engines": skipped_engines,
        "unresponsive_engines": [],
    }

    timeout = aiohttp.ClientTimeout(total=settings.timeout_seconds)
    started = time.monotonic()

    try:
        # SearxNG botdetection 預期請求帶 X-Forwarded-For / X-Real-IP；
        # 內網直連沒有 proxy，補一個值避免每次呼叫都在 searxng log 跳 warning。
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                settings.searxng_url,
                params=params,
                headers={"X-Forwarded-For": "127.0.0.1"},
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    meta["error"] = f"http_{resp.status}"
                    log.warning(
                        "SearXNG HTTP %s: %s (query=%s)",
                        resp.status,
                        body[:200],
                        question[:80],
                    )
                    meta["elapsed_ms"] = int((time.monotonic() - started) * 1000)
                    return WebRetrievalOutcome(results=[], meta=meta)

                data = await resp.json(content_type=None)
    except asyncio.TimeoutError:
        meta["error"] = "timeout"
        meta["elapsed_ms"] = int((time.monotonic() - started) * 1000)
        log.warning(
            "SearXNG timeout after %.1fs (query=%s)",
            settings.timeout_seconds,
            question[:80],
        )
        return WebRetrievalOutcome(results=[], meta=meta)
    except aiohttp.ClientError as exc:
        meta["error"] = f"client_error:{type(exc).__name__}"
        meta["elapsed_ms"] = int((time.monotonic() - started) * 1000)
        log.warning("SearXNG client error: %s (query=%s)", exc, question[:80])
        return WebRetrievalOutcome(results=[], meta=meta)
    except Exception as exc:
        meta["error"] = f"unexpected:{type(exc).__name__}"
        meta["elapsed_ms"] = int((time.monotonic() - started) * 1000)
        log.warning("SearXNG unexpected error: %s (query=%s)", exc, question[:80])
        return WebRetrievalOutcome(results=[], meta=meta)

    meta["elapsed_ms"] = int((time.monotonic() - started) * 1000)
    if isinstance(data, dict):
        meta["unresponsive_engines"] = _note_unresponsive(data.get("unresponsive_engines"), settings, log)

    raw_results = data.get("results", []) if isinstance(data, dict) else []
    normalized: list[WebResult] = []
    seen_urls: set[str] = set()

    for item in raw_results:
        if not isinstance(item, dict):
            continue
        url = (item.get("url") or "").strip()
        if not url or url in seen_urls:
            continue
        title = (item.get("title") or "").strip()
        snippet = (item.get("content") or "").strip()
        engine = (item.get("engine") or "").strip()
        published = item.get("publishedDate")
        if not title and not snippet:
            continue
        seen_urls.add(url)
        normalized.append(
            WebResult(
                title=title[:160],
                url=url,
                snippet=snippet[:400],
                engine=engine,
                published_date=published if isinstance(published, str) else None,
            )
        )
        if len(normalized) >= top_k:
            break

    meta["result_count"] = len(normalized)
    log.info(
        "SearXNG ok: %d results in %dms (engines=%s 略過=%s 沒回應=%s query=%s)",
        len(normalized),
        meta["elapsed_ms"],
        effective_engines,
        skipped_engines or "-",
        [name for name, _ in meta["unresponsive_engines"]] or "-",
        question[:80],
    )
    return WebRetrievalOutcome(results=normalized, meta=meta)


def format_web_context_lines(results: list[WebResult]) -> list[str]:
    """把 WebResult 列表渲染成 <web_context> 區塊內每行。

    格式：`[N] [YYYY-MM-DD] 標題 — snippet <url>`
    URL 以 `<...>` 角括號包覆：這是 Discord 認得的 URL 邊界標記，避免輸出被
    Discord 客戶端誤把右括號 `)` / 句號等吃進 URL。LLM 看到範本就會模仿這個格式。
    日期取自 publishedDate（前 10 碼），無日期時省略該欄；snippet 為空時也省略。
    """
    lines: list[str] = []
    for idx, result in enumerate(results, start=1):
        parts = [f"[{idx}]"]
        if result.published_date:
            parts.append(f" [{result.published_date[:10]}]")
        parts.append(f" {result.title}")
        if result.snippet:
            parts.append(f" — {result.snippet}")
        parts.append(f" <{result.url}>")
        lines.append("".join(parts))
    return lines
