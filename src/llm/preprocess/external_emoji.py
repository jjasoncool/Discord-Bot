"""別的伺服器的表情與貼圖：字典查不到描述，就下載圖片給模型看。

**為什麼**：本伺服器的表情由管理員在 `settings/emoji_dictionary.txt` 維護描述、貼圖描述在 Discord 上維護；
別的伺服器的不可控——字典沒有、Discord 上的貼圖描述也幾乎都是空的（2026-10-02 查 4 張都是空字串）。
不給圖的話，模型只看得到一個名稱，不知道對方回了什麼。

- 判斷「別的伺服器」：表情名稱不在字典檔（字典連待填的佔位都有記）；貼圖不在本伺服器的快取。
- 只處理最新那則與被回覆的那則（呼叫端決定），每則最多 `MAX_IMAGES` 張，跟其他圖共用呼叫端的總額度。
- Lottie 動態貼圖沒有圖檔，只留名稱。
"""
from __future__ import annotations

import logging
import re
from typing import Any, Iterable, Optional

from llm.preprocess import emoji_dictionary, sticker_cache
from llm.preprocess.vision_image import download_images

logger = logging.getLogger(__name__)

MAX_IMAGES = 2
_EMOJI_RE = re.compile(r"<(a?):(\w+):(\d+)>")


def custom_emojis(text: str) -> list[tuple[str, str, str]]:
    """文字裡的自訂表情 `(名稱, ID, 圖片網址)`，照出現順序。"""
    return [(name, emoji_id, f"https://cdn.discordapp.com/emojis/{emoji_id}.{'gif' if animated else 'png'}")
            for animated, name, emoji_id in _EMOJI_RE.findall(text or "")]


def sticker_image_url(st: Any) -> Optional[str]:
    """貼圖的圖片網址；Lottie 動態貼圖沒有圖檔，回 None。"""
    if getattr(getattr(st, "format", None), "name", "") == "lottie":
        return None
    return str(getattr(st, "url", None) or f"https://media.discordapp.net/stickers/{st.id}.png")


def _targets(text: str, stickers: Iterable[Any]) -> list[tuple[str, str]]:
    """要給模型看的 `(說明, 圖片網址)`，照出現順序、去重。"""
    known = emoji_dictionary.entries()
    out: dict[str, str] = {}
    for name, _emoji_id, url in custom_emojis(text):
        if name not in known:
            out.setdefault(url, f"表情 :{name}:")
    for st in stickers or ():
        sticker_id = getattr(st, "id", 0)
        if sticker_cache.is_known(sticker_id):
            continue
        url = sticker_image_url(st)
        if url:
            out.setdefault(url, f"貼圖「{getattr(st, 'name', '')}」")
    return [(label, url) for url, label in out.items()]


async def external_emoji_context(text: str, stickers: Iterable[Any] = (), *, session=None
                                 ) -> tuple[list[str], list[str]]:
    """`(給模型看的說明行, 圖 base64)`。沒有別的伺服器的表情或貼圖時完全不連網；下載失敗就不加。"""
    targets = _targets(text, stickers)[:MAX_IMAGES]
    if not targets:
        return [], []
    own_session = session is None
    if own_session:
        import aiohttp
        session = aiohttp.ClientSession()
    labels: list[str] = []
    images: list[str] = []
    try:
        for label, url in targets:
            got = await download_images(session, [url], limit=1)
            if got:
                labels.append(label)
                images.extend(got)
    except Exception as exc:
        logger.warning("下載別的伺服器的表情／貼圖失敗：%s", exc)
    finally:
        if own_session:
            await session.close()
    if not images:
        return [], []
    return [f"（附圖：別的伺服器的{'、'.join(labels)}）"], images
