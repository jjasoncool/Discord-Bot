"""一次網路搜尋：依路由挑引擎 → 查 SearXNG → 窄路由結果太少就換通用引擎補。

/askai 的兩種用法共用這一份（開關 `askai_web_search_mode`）：關鍵字模式由 `intent.should_search` 決定要不要查、
用 `intent._ROUTE_RULES` 路由，查完塞進 prompt；工具模式由模型決定要不要查、選題目類型，路由寫在 `tools._KINDS`
（兩張表刻意分開：關鍵字模式是保留下來退回用的舊做法）。兩種用法共用的是「怎麼查、結果太少怎麼補查、快取」這一份。
新聞的查法另在 `_search_news`：有日期的引擎不限時間、照日期新到舊排，沒日期的引擎用自己的時間條件、排在後面。
"""

from __future__ import annotations

import logging
import time
from typing import Any

from .searxng import WebResult, WebRetrievalOutcome, fetch_web_results

logger = logging.getLogger(__name__)

#: (查詢, 路由) → (到期時刻, 結果)。同一個查詢短時間內直接用上次的結果：少打引擎、降低被擋的機會
_cache: dict[tuple, tuple[float, WebRetrievalOutcome]] = {}
_CACHE_MAX = 64


def _cached(key: tuple) -> WebRetrievalOutcome | None:
    now = time.monotonic()
    for stale in [k for k, (expires, _) in _cache.items() if expires <= now]:
        del _cache[stale]
    hit = _cache.get(key)
    if hit is None:
        return None
    outcome = hit[1]
    return WebRetrievalOutcome(results=list(outcome.results), meta={**outcome.meta, "cached": True},
                               answers=list(outcome.answers))


def _remember(key: tuple, outcome: WebRetrievalOutcome, settings: Any) -> None:
    """只記有結果或直接答案的（都沒有下次要重查；出錯時本來就沒有）；有引擎這次沒回應的也不記（結果不完整，
    下次可能就齊了）。超過上限丟最早到期的。`cache_seconds` 設 0 等於關掉：記進去就已經過期，下次讀不到。"""
    if not outcome.results and not outcome.answers:
        return
    if outcome.meta.get("unresponsive_engines") or outcome.meta.get("primary_unresponsive_engines"):
        return
    if len(_cache) >= _CACHE_MAX:
        del _cache[min(_cache, key=lambda k: _cache[k][0])]
    _cache[key] = (time.monotonic() + settings.cache_seconds, outcome)


async def search_web(
    query: str,
    *,
    settings: Any,  # AskAIWebSettings（以 Any 標記避免 circular import）
    categories: str | None = None,
    time_range: str | None = None,
    language: str | None = None,
    engines: str | None = None,
    logger_override: logging.Logger | None = None,
) -> WebRetrievalOutcome:
    """照路由（categories／time_range／language，或明確指定的 engines）查一次；失敗不 raise，原因在 meta.error。

    窄路由（限類別、限時間）結果少於 `settings.fallback_min_results` 時，改用通用引擎、不限類別與時間再查一次，
    合併去重（窄路由的結果通常比較貼題，排前面）；補查的經過記在 meta.fallback。
    同一個查詢（同字串、同路由）`settings.cache_seconds` 內直接回上次的結果（meta.cached）；出錯或 0 筆不記。
    `engines`：明確指定引擎（天氣、匯率這類專用引擎），不照類別挑。
    """
    log = logger_override or logger
    key = (query, categories, time_range, language, engines)
    hit = _cached(key)
    if hit is not None:
        return hit
    outcome = await _search(query, settings=settings, categories=categories, time_range=time_range,
                            language=language, engines=engines, log=log)
    _remember(key, outcome, settings)
    return outcome


def _newest_first(results: list[WebResult]) -> list[WebResult]:
    """有日期的照日期新到舊排；沒日期的照原順序接在後面（沒日期的不能當成最新）。"""
    dated = [r for r in results if r.published_date]
    undated = [r for r in results if not r.published_date]
    return sorted(dated, key=lambda r: r.published_date or "", reverse=True) + undated


async def _search_news(query: str, *, settings: Any, time_range: str | None, language: str | None,
                       log: logging.Logger) -> WebRetrievalOutcome:
    """新聞：有日期的引擎不限時間（呼叫端沒指定的話）、結果照日期新到舊排——限一週會把最準的新聞引擎整個擋掉，
    不限又會混進舊文，照日期排兩邊都顧到。不給日期的引擎排不了，另外一次請求、用它自己支援的時間條件，結果接在
    有日期的後面。送 engines 不送 categories：同送時 SearXNG 取聯集，會把停用的引擎一起叫來陪跑。"""
    # 有日期的多抓幾倍再排：SearXNG 回的是相關度順序，只抓 top_k 再排，排在後面的新聞永遠進不來
    dated = await fetch_web_results(query, settings=settings, engines=settings.news_engines, categories=None,
                                    limit=settings.top_k * 4, time_range=time_range, language=language,
                                    logger_override=log)
    if not settings.news_undated_engines:
        return WebRetrievalOutcome(results=_newest_first(dated.results)[: settings.top_k], meta=dated.meta,
                                   answers=dated.answers)
    undated = await fetch_web_results(query, settings=settings, engines=settings.news_undated_engines,
                                      categories=None, time_range=settings.news_undated_time_range,
                                      language=language, logger_override=log)
    seen = {r.url for r in dated.results}
    results = (_newest_first(dated.results) + [r for r in undated.results if r.url not in seen])[: settings.top_k]
    both_failed = bool(dated.meta.get("error") and undated.meta.get("error"))
    meta = {
        **dated.meta,
        "result_count": len(results),
        # 一邊出錯、另一邊有回應就不算整次失敗（補查看 error 決定要不要再查）
        "error": dated.meta.get("error") if both_failed else None,
        "unresponsive_engines": [*(dated.meta.get("unresponsive_engines") or []),
                                 *(undated.meta.get("unresponsive_engines") or [])],
        "dated": {"engines": dated.meta.get("engines"), "result_count": len(dated.results),
                  "error": dated.meta.get("error")},
        "undated": {"engines": undated.meta.get("engines"), "time_range": settings.news_undated_time_range,
                    "result_count": len(undated.results), "error": undated.meta.get("error")},
    }
    return WebRetrievalOutcome(results=results, meta=meta, answers=dated.answers or undated.answers)


async def _search(query: str, *, settings: Any, categories: str | None, time_range: str | None,
                  language: str | None, engines: str | None, log: logging.Logger) -> WebRetrievalOutcome:
    if engines is None and categories == "news":
        outcome = await _search_news(query, settings=settings, time_range=time_range, language=language, log=log)
    else:
        outcome = await fetch_web_results(
            query,
            settings=settings,
            engines=engines,
            categories=categories,
            time_range=time_range,
            language=language,
            logger_override=log,
        )

    # 門檻不是 0：news engines 常「只吐 1 筆」，那種半死不活的結果會擋掉補查 → 安靜降級。
    # 只在「沒出錯」時補查：timeout / http error 代表 SearXNG 本身異常，重試無益；本來就是通用、不限時的也不重查。
    narrow = categories is not None or time_range is not None
    if not narrow or outcome.meta.get("error") is not None or len(outcome.results) >= settings.fallback_min_results:
        return outcome

    log.info(
        "網路搜尋結果太少：主搜只有 %d 筆（< %d），改用通用引擎補查 (query=%s)",
        len(outcome.results),
        settings.fallback_min_results,
        query[:80],
    )
    fallback = await fetch_web_results(
        query,
        settings=settings,
        engines=None,      # → default_engines（通用，覆蓋廣）
        categories=None,
        time_range=None,
        language=language,
        logger_override=log,
    )
    fallback_meta = {
        "attempted": True,
        "result_count": len(fallback.results),
        "error": fallback.meta.get("error"),
    }
    if not fallback.results:
        return WebRetrievalOutcome(results=outcome.results, meta={**outcome.meta, "fallback": fallback_meta},
                                   answers=outcome.answers)
    seen_urls = {r.url for r in outcome.results}
    merged = list(outcome.results) + [r for r in fallback.results if r.url not in seen_urls]
    merged = merged[: settings.top_k]
    return WebRetrievalOutcome(
        results=merged,
        meta={
            **fallback.meta,
            "result_count": len(merged),
            "merged_from_primary": len(seen_urls),
            "fallback": fallback_meta,
            # meta 其他欄位是補查那次的；主搜的引擎狀況另外留著，答案數照實際合併後的算
            "primary_unresponsive_engines": outcome.meta.get("unresponsive_engines") or [],
            "answer_count": len(outcome.answers or fallback.answers),
        },
        answers=outcome.answers or fallback.answers,
    )
