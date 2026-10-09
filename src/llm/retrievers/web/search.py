"""一次網路搜尋：依路由挑引擎 → 查 SearXNG → 窄路由結果太少就換通用引擎補。

/askai 的兩種用法共用這一份（開關 `askai_web_search_mode`）：關鍵字模式由 `intent.should_search` 決定要不要查、
路由，查完塞進 prompt；工具模式由模型決定要不要查（`tools.WebSearchTools`）。哪類引擎對哪類題目有效、
什麼時候要換引擎補查，都是實測出來的（見 `intent._ROUTE_RULES` 的說明），兩種用法不能各寫一份。
"""

from __future__ import annotations

import logging
from typing import Any

from .searxng import WebRetrievalOutcome, fetch_web_results

logger = logging.getLogger(__name__)


async def search_web(
    query: str,
    *,
    settings: Any,  # AskAIWebSettings（以 Any 標記避免 circular import）
    categories: str | None = None,
    time_range: str | None = None,
    language: str | None = None,
    logger_override: logging.Logger | None = None,
) -> WebRetrievalOutcome:
    """照路由（`intent.classify_route` 的 categories／time_range／language）查一次；失敗不 raise，原因在 meta.error。

    窄路由（限類別、限時間）結果少於 `settings.fallback_min_results` 時，改用通用引擎、不限類別與時間再查一次，
    合併去重（窄路由的結果通常比較貼題，排前面）；補查的經過記在 meta.fallback。
    """
    log = logger_override or logger
    engines: str | None = None
    query_categories = categories
    if categories == "news":
        # engines 與 categories 二選一：同送時 SearXNG 取聯集，會把停用的引擎一起叫來陪跑
        engines = settings.news_engines
        query_categories = None
    outcome = await fetch_web_results(
        query,
        settings=settings,
        engines=engines,
        categories=query_categories,
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
        return WebRetrievalOutcome(results=outcome.results, meta={**outcome.meta, "fallback": fallback_meta})
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
        },
    )
