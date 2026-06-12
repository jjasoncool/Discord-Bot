"""SearXNG async HTTP client：查詢、正規化、失敗安靜降級。

與 llm_service 保持一致使用 aiohttp。失敗（timeout / HTTP error / 網路異常）不 raise，
回傳空結果並在 meta 裡記錄 error，讓 /askai 主流程不受影響。
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

import aiohttp

logger = logging.getLogger("discord_bot")


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
    effective_engines = engines if engines is not None else settings.default_engines
    effective_language = language if language is not None else settings.language

    params: dict[str, str] = {
        "q": question,
        "format": "json",
        "language": effective_language,
        "engines": effective_engines,
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
        "SearXNG ok: %d results in %dms (engines=%s query=%s)",
        len(normalized),
        meta["elapsed_ms"],
        effective_engines,
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
