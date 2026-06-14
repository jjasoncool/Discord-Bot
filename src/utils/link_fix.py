"""Twitter / X 連結修復工具。

x.com / twitter.com 的貼文（尤其影片）貼到 Discord 不會自動載入預覽，
社群慣用做法是把網域換成第三方 embed 服務（此處用 fixupx.com），
Discord 就能正常顯示預覽。

但圖片貼文 Discord 原生預覽就正常，轉 fixupx 沒有差別，反而多此一舉，
所以本模組會先用 Twitter 自家的 syndication CDN 查詢貼文類型，
只在「確定是影片」或「服務查不到（fail-open）」時才轉，圖片貼文一律放生。

決策表（見 select_video_links）：
  - 確定是影片            → 轉 fixupx（+ 呼叫端砍預覽）
  - 確定非影片（圖片/文字）→ 不轉
  - 明確 404 / 已刪 / 不存在 → 不轉（防呆，尊重服務的確定答案）
  - 逾時 / 5xx / 怪回應     → 轉 fixupx（fail-open，避免查詢服務掛掉就整個停擺）

查類型走 cdn.syndication.twimg.com（Twitter 自家、免金鑰），
顯示走 fixupx.com，查與顯示分離。token 演算法移植自 vercel/react-tweet。
"""

import asyncio
import logging
import math
import re

logger = logging.getLogger(__name__)

# 只比對貼文連結（含 /status/<id>），避免把個人首頁、搜尋等無意義連結也轉掉。
# 涵蓋 x.com 與 twitter.com（含 www. / mobile. 子網域）。
# 另外抓出 user 與 status id，供查詢類型使用。
TWITTER_STATUS_RE = re.compile(
    r"https?://(?:www\.|mobile\.)?(?:x|twitter)\.com/"
    r"(?P<path>(?P<user>[A-Za-z0-9_]+)/status/(?P<id>\d+)(?:/(?:photo|video)/\d+)?)"
    r"(?P<query>\?[^\s]*)?",
    re.IGNORECASE,
)

# 替代用的可預覽網域（顯示用）。
FIXUP_DOMAIN = "fixupx.com"

# Twitter 自家 syndication CDN（查類型用，免金鑰）。
_SYNDICATION_URL = "https://cdn.syndication.twimg.com/tweet-result"
_SYNDICATION_TIMEOUT = 8  # 秒；查不到就走 fail-open，不要卡太久

_BASE36 = "0123456789abcdefghijklmnopqrstuvwxyz"


def get_token(tweet_id: str) -> str:
    """產生 syndication CDN 需要的 token。

    移植自 vercel/react-tweet 的 getToken：
        ((id / 1e15) * π) 轉成 36 進位字串，再去掉所有 0 與小數點。
    純計算、免金鑰、同一個 id 永遠算出同一個 token。
    """
    value = (int(tweet_id) / 1e15) * math.pi
    integer = int(value)
    frac = value - integer

    if integer == 0:
        int_str = "0"
    else:
        int_str = ""
        n = integer
        while n > 0:
            int_str = _BASE36[n % 36] + int_str
            n //= 36

    # 小數部分轉 36 進位（模仿 JS Number.toString(36)，取足夠位數）。
    frac_str = ""
    for _ in range(20):
        if frac == 0:
            break
        frac *= 36
        digit = int(frac)
        frac_str += _BASE36[digit]
        frac -= digit

    return re.sub(r"(0+|\.)", "", f"{int_str}.{frac_str}")


def rewrite_twitter_links(content: str) -> str | None:
    """將內容中的 x.com / twitter.com 貼文連結「全部」轉成 fixupx.com 版本。

    純字串處理、不查詢類型，保留給測試與不需要類型判斷的場合使用。

    回傳：
        - 有可轉連結：所有轉好的網址，多個以換行串接。
        - 沒有可轉連結：None。
    """
    if not content:
        return None

    fixed_links: list[str] = []
    seen: set[str] = set()
    for match in TWITTER_STATUS_RE.finditer(content):
        # 去掉追蹤用 query string，連結較乾淨且不影響預覽。
        new_url = f"https://{FIXUP_DOMAIN}/{match.group('path')}"
        if new_url not in seen:
            seen.add(new_url)
            fixed_links.append(new_url)

    if not fixed_links:
        return None

    return "\n".join(fixed_links)


async def _classify_tweet(session, tweet_id: str) -> str:
    """查 syndication CDN 判斷單則貼文類型。

    回傳：
        "video"     → 推文存在且含影片（含 Twitter GIF，本質也是影片，Discord 同樣播不了）
        "non_video" → 推文存在但無影片（純圖片 / 純文字）
        "not_found" → 服務明確回 404 / tombstone / 沒有貼文主體（確定不存在）
        "unknown"   → 逾時 / 5xx / 內容無法解析（服務問題，無法判斷）
    """
    import aiohttp

    url = (
        f"{_SYNDICATION_URL}?id={tweet_id}&lang=en&token={get_token(tweet_id)}"
    )
    try:
        timeout = aiohttp.ClientTimeout(total=_SYNDICATION_TIMEOUT)
        async with session.get(url, timeout=timeout) as resp:
            if resp.status == 404:
                return "not_found"
            if resp.status >= 500:
                return "unknown"

            try:
                data = await resp.json(content_type=None)
            except Exception:
                # 空 body / 非 JSON（常見於被限流）→ 當服務問題，fail-open。
                return "unknown"

            if not isinstance(data, dict) or not data:
                return "unknown"

            # tombstone / 已刪 → 確定不存在。
            if data.get("__typename") == "TweetTombstone" or "tombstone" in data:
                return "not_found"

            # 沒有任何貼文主體欄位（例如限流回 {}）→ 視為服務問題，fail-open。
            if not any(k in data for k in ("mediaDetails", "text", "id_str")):
                return "unknown"

            media = data.get("mediaDetails") or []
            has_video = any(
                m.get("type") in ("video", "animated_gif") for m in media
            )
            # 保險：頂層 video 欄位也算。
            if not has_video and data.get("video"):
                has_video = True

            return "video" if has_video else "non_video"
    except asyncio.TimeoutError:
        logger.warning("查詢 tweet %s 類型逾時，視為服務問題（fail-open）", tweet_id)
        return "unknown"
    except Exception as exc:
        logger.warning(
            "查詢 tweet %s 類型失敗，視為服務問題（fail-open）：%s", tweet_id, exc
        )
        return "unknown"


async def select_video_links(content: str, session=None) -> str | None:
    """挑出「該轉成 fixupx 的」連結（換行串接）。

    先用 regex 擋格式（本地、免網路），沒有合格式連結就直接早退、
    完全不碰網路、不開 session；命中才查 syndication CDN：
      - 影片 / 服務查不到（unknown）→ 轉
      - 非影片 / 確定不存在（404）   → 不轉

    session 可由呼叫端注入（方便測試 / 共用連線池）；不給就自開自關。

    回傳：
        - 有要轉的連結：換行串接的 fixupx 網址。
        - 沒有：None。
    """
    if not content:
        return None

    # 第 1 層格式防呆：沒有合格式連結就早退，連 session 都不開（多數訊息走這條）。
    matches = list(TWITTER_STATUS_RE.finditer(content))
    if not matches:
        return None

    own_session = session is None
    if own_session:
        import aiohttp

        session = aiohttp.ClientSession()
    try:
        fixed_links: list[str] = []
        seen: set[str] = set()
        for match in matches:
            new_url = f"https://{FIXUP_DOMAIN}/{match.group('path')}"
            if new_url in seen:
                continue

            decision = await _classify_tweet(session, match.group("id"))
            # 只在「確定有影片」或「服務掛掉問不到」時才轉；非影片 / 404 一律放生。
            if decision in ("video", "unknown"):
                seen.add(new_url)
                fixed_links.append(new_url)
    finally:
        if own_session:
            await session.close()

    if not fixed_links:
        return None

    return "\n".join(fixed_links)
