"""名次融合（Reciprocal Rank Fusion，RRF）：把好幾份各自排好的名單合成一份。

為什麼用名次、不用分數：關鍵字搜尋的 BM25 分數和向量的相似度刻度完全不同，硬加沒有意義；
RRF 只看「排第幾」，每份名單第 r 名得 weight / (k + r) 分，加總後排序——兩邊都排前面的會浮上來，
只有一邊排前面的也不會被另一邊完全蓋掉。k 越大，前幾名和後面名次的分數差越小（常用 60）。

`/askai` 的聊天檢索（BM25＋向量）與情報搜尋（關鍵字＋向量）共用這一份。
"""
from __future__ import annotations

from collections import defaultdict
from typing import Hashable, Iterable, Mapping, Optional, Sequence


def rrf_score(rank: int, *, weight: float = 1.0, k: int = 60) -> float:
    """名次（從 1 開始）→ 分數。例：k=60 時第 1 名 1/61、第 2 名 1/62。"""
    return weight / (k + rank)


def fuse_rankings(
    rankings: Mapping[str, Sequence[Hashable]],
    *,
    weights: Optional[Mapping[str, float]] = None,
    k: int = 60,
) -> list[Hashable]:
    """多份名單 → 融合後的名單（分數高的在前；同分照第一次出現的順序）。"""
    scores: dict[Hashable, float] = defaultdict(float)
    order: dict[Hashable, int] = {}
    for name, ranked in rankings.items():
        weight = (weights or {}).get(name, 1.0)
        for position, item in enumerate(ranked, 1):
            scores[item] += rrf_score(position, weight=weight, k=k)
            order.setdefault(item, len(order))
    return sorted(scores, key=lambda item: (-scores[item], order[item]))


def fused_scores(rankings: Mapping[str, Iterable[Hashable]], *, weights: Optional[Mapping[str, float]] = None,
                 k: int = 60) -> dict[Hashable, float]:
    """同 `fuse_rankings`，但回傳每個項目的融合分數（要另外加門檻時用）。"""
    scores: dict[Hashable, float] = defaultdict(float)
    for name, ranked in rankings.items():
        weight = (weights or {}).get(name, 1.0)
        for position, item in enumerate(ranked, 1):
            scores[item] += rrf_score(position, weight=weight, k=k)
    return dict(scores)
