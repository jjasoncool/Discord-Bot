"""把 X（Twitter）貼文連結展開成模型看得懂的內容：作者、內文、媒體類型，外加縮圖給模型看。

**為什麼**：bot 轉發 x.com 影片時發的是 fixupx 網址，群友回覆它時模型只看得到網址——實例：
群友回「肛塞？」，模型回「你怎麼從我發的那個連結，直接跳到肛塞了？」，其實那是一支花瓶影片。

- 查詢共用 `utils.link_fix.fetch_tweet`（Twitter 自家 syndication CDN、免金鑰，轉 fixupx 時本來就在查）。
- 影片只給縮圖（CDN 回應現成的 `media_url_https`），不下載影片；圖片貼文每篇最多給
  `MAX_IMAGES_PER_TWEET` 張，跟群友自己貼的圖共用呼叫端的總額度。
- 被標為敏感內容的照樣給圖（模型在本機、不外傳，回應尺度由守則管），但文字註明。
- 只在要呼叫模型時才查；同一篇快取 `CACHE_SECONDS`；查不到就什麼都不加（照舊只有網址）。
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Optional

from llm.preprocess.vision_image import download_images
from utils.link_fix import fetch_tweet, tweet_ids

logger = logging.getLogger(__name__)

CACHE_SECONDS = 3600
#: 一則訊息最多展開幾篇貼文
MAX_TWEETS = 2
#: 每篇最多附幾張圖（影片只有一張縮圖）
MAX_IMAGES_PER_TWEET = 2
_CACHE_MAX = 64
_IMAGE_MAX_BYTES = 5 * 1024 * 1024
_IMAGE_TIMEOUT = 8
_TEXT_MAX = 200
#: 內文裡的 t.co 短網址多半是媒體本身，留著只是雜訊
_TCO = re.compile(r"https?://t\.co/\S+")

#: tweet_id → (時間, 貼文, 縮圖 base64 清單)
_cache: dict[str, tuple[float, "TweetInfo", list[str]]] = {}


@dataclass(frozen=True)
class TweetInfo:
    tweet_id: str
    screen_name: str
    name: str
    text: str
    #: video／gif／photo／text
    kind: str
    video_seconds: Optional[int]
    photo_count: int
    image_urls: tuple[str, ...]
    sensitive: bool


def parse_tweet(tweet_id: str, data: dict[str, Any]) -> TweetInfo:
    """CDN 回應 → 需要的欄位。影片與 GIF 的 `media_url_https` 就是縮圖。"""
    user = data.get("user") or {}
    media = [m for m in data.get("mediaDetails") or [] if isinstance(m, dict)]
    videos = [m for m in media if m.get("type") in ("video", "animated_gif")]
    photos = [m for m in media if m.get("type") == "photo"]
    if videos:
        kind = "gif" if videos[0].get("type") == "animated_gif" else "video"
        millis = (videos[0].get("video_info") or {}).get("duration_millis")
        seconds = round(millis / 1000) if isinstance(millis, (int, float)) and millis else None
        urls = [videos[0].get("media_url_https") or (data.get("video") or {}).get("poster")]
    elif photos:
        kind, seconds = "photo", None
        urls = [m.get("media_url_https") for m in photos]
    else:
        kind, seconds, urls = "text", None, []
    text = " ".join(_TCO.sub("", data.get("text") or "").split())
    if len(text) > _TEXT_MAX:
        text = text[:_TEXT_MAX] + "…"
    return TweetInfo(
        tweet_id=str(tweet_id),
        screen_name=str(user.get("screen_name") or ""),
        name=str(user.get("name") or ""),
        text=text,
        kind=kind,
        video_seconds=seconds,
        photo_count=len(photos),
        image_urls=tuple(u for u in urls if u),
        sensitive=bool(data.get("possibly_sensitive")),
    )


def describe(info: TweetInfo, attached: int) -> str:
    """給模型看的一行：「（X 貼文 @作者（名稱）：內文；影片 24 秒，縮圖已附上）」。"""
    who = f"@{info.screen_name}" + (f"（{info.name}）" if info.name and info.name != info.screen_name else "")
    parts = [f"X 貼文 {who}：{info.text or '（沒有文字）'}"]
    if info.kind in ("video", "gif"):
        label = "GIF" if info.kind == "gif" else "影片"
        length = f" {info.video_seconds} 秒" if info.video_seconds else ""
        parts.append(f"{label}{length}" + ("，縮圖已附上" if attached else ""))
    elif info.kind == "photo":
        parts.append(f"{info.photo_count} 張圖" + (f"，附上 {attached} 張" if attached else ""))
    if info.sensitive:
        parts.append("被標為敏感內容")
    return "（" + "；".join(parts) + "）"


async def _download_images(session, urls: tuple[str, ...]) -> list[str]:
    return await download_images(session, urls, limit=MAX_IMAGES_PER_TWEET, max_bytes=_IMAGE_MAX_BYTES,
                                 timeout=_IMAGE_TIMEOUT)


async def _load(session, tweet_id: str) -> Optional[tuple[TweetInfo, list[str]]]:
    now = time.monotonic()
    hit = _cache.get(tweet_id)
    if hit and now - hit[0] < CACHE_SECONDS:
        return hit[1], hit[2]
    status, data = await fetch_tweet(session, tweet_id)
    if status != "ok" or not data:
        return None
    info = parse_tweet(tweet_id, data)
    images = await _download_images(session, info.image_urls)
    if len(_cache) >= _CACHE_MAX:
        _cache.pop(min(_cache, key=lambda k: _cache[k][0]))
    _cache[tweet_id] = (now, info, images)
    return info, images


async def expand_tweets(text: str, *, session=None) -> tuple[list[str], list[str]]:
    """文字裡的 X 貼文連結 → `(給模型看的說明行, 縮圖 base64)`。沒有連結時完全不連網。

    任何失敗都回空的那一份——少了說明頂多回到以前「只看得到網址」，不該擋住回覆。
    """
    ids = tweet_ids(text)[:MAX_TWEETS]
    if not ids:
        return [], []
    own_session = session is None
    if own_session:
        import aiohttp
        session = aiohttp.ClientSession()
    notes: list[str] = []
    images: list[str] = []
    try:
        for tweet_id in ids:
            try:
                loaded = await _load(session, tweet_id)
            except Exception as exc:
                logger.warning("展開貼文 %s 失敗：%s", tweet_id, exc)
                continue
            if loaded is None:
                continue
            info, imgs = loaded
            notes.append(describe(info, len(imgs)))
            images.extend(imgs)
    finally:
        if own_session:
            await session.close()
    return notes, images
