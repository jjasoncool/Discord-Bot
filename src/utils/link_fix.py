"""把貼到 Discord 播不了的影片連結換成能播的網址（X、bilibili），並先確認替代網址真的做得出預覽。

架構定位：基礎層（`utils`），只用標準庫與 aiohttp，不碰 Discord。
  - 上層（誰呼叫）：轉貼流程 `services.relay.link_repost`（挑網址、組轉貼內文）；給模型看 X 貼文的
    `llm.preprocess.tweet_context`（`fetch_tweet`、`tweet_ids`）；組聊天行的 `llm.preprocess.chat_line`
    （`is_repost_text` 認出自動轉貼、`TWEET_LINK_RE` 認出 X 的預覽）。
  - 下層（呼叫誰）：X 的 syndication CDN（查貼文類型）、替代網址本身（預檢）。

介面：
- `find_fixable_links(content)`：訊息裡可以轉的連結與它們的替代網址（純字串，不連網）。
- `select_fixed_links(content, session=None)`：真的要轉貼的替代網址（X 只留影片；每個都預檢過）。
- `repost_text(fixed)`：轉貼訊息的內文（原連結在暴雷裡就照包 `||`）。
- `is_repost_text(text)`：這段文字是不是只有替代網址（認出 bot 的自動轉貼）。
- `probe_preview(session, url)`：用 Discord 爬蟲的身分抓一次，做不做得出影片或圖片預覽（頁面標籤或 Mastodon 相容 API）。
- `fetch_tweet(session, tweet_id)`、`tweet_ids(text)`、`get_token(tweet_id)`：查 X 貼文。

規則：
- X 只轉 `/status/<id>` 的貼文，而且確定是影片（含 GIF）或查詢服務問不到時才轉；圖片貼文 Discord 原生預覽就正常，
  轉了還會把原生預覽一起壓掉。確定不存在（404、tombstone）不轉。
- bilibili 只轉 `bilibili.com/video/BV…`（www.、m.、/en/ 這類語言路徑都認）；短網址 b23.tv 不轉。保留分 P（`p`）與
  時間點（`t`），其他追蹤參數拿掉；不加語言前綴（vxbilibili 已經把標題轉成繁體）。
- 已經是替代網域的連結不轉（比對時要求 `https://` 後面直接接原網域）。
- 替代網址依序預檢，第一個過的才用；全部不過就不轉，群友保留 Discord 原生的預覽。

例外與決策：
- 查類型走 X 自家的 syndication CDN（免金鑰，x.com 本身沒倒就不會消失）；顯示走 fixupx，預檢不過才換 vxtwitter。
  查詢逾時、5xx、怪回應照轉（fail-open），反正還有預檢把關。
- fixupx 的頁面標籤只有標題，影片放在 Mastodon 相容的 API：頁面上的 `application/activity+json` 連結指出貼文 id，
  Discord 讀的是 `/api/v1/statuses/<id>` 的 `media_attachments`。預檢照 Discord 的讀法，標籤沒有就讀那份。
- bilibili 自家 API 對伺服器回 412（風控），不能先查；`/video/BV…` 一定是影片，只靠預檢。
- 預檢帶 Discordbot 的 UA：這些服務看 UA 決定回預覽頁還是轉址到原站。逾時、非 200 當成做不出預覽——
  轉了卻沒預覽、原預覽又被壓掉，群友就什麼都看不到。
- token 演算法移植自 vercel/react-tweet；實測只要非空就放行，照算是防之後收緊。
"""

import asyncio
import logging
import math
import re
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit

logger = logging.getLogger(__name__)

# 只比對貼文連結（含 /status/<id>），個人首頁、搜尋這類轉了也沒意義。涵蓋 x.com 與 twitter.com（含 www./mobile.）。
TWITTER_STATUS_RE = re.compile(
    r"https?://(?:www\.|mobile\.)?(?:x|twitter)\.com/"
    r"(?P<path>(?P<user>[A-Za-z0-9_]+)/status/(?P<id>\d+)(?:/(?:photo|video)/\d+)?)"
    r"(?P<query>\?[^\s|]*)?",
    re.IGNORECASE,
)

# bilibili 影片頁：www.／m.、語言路徑（/en/、/ja/、/zh-tw/）都認；`https://` 後面要直接接 bilibili.com，vxbilibili 不會中。
BILIBILI_VIDEO_RE = re.compile(
    r"https?://(?:(?:www|m)\.)?bilibili\.com/(?:[a-z]{2}(?:-[a-z]{2,4})?/)?video/(?P<bv>BV[0-9A-Za-z]{10})/?"
    r"(?P<query>\?[^\s|]*)?",
    re.IGNORECASE,
)

#: X 的替代網域，依序預檢
X_FIX_DOMAINS = ("fixupx.com", "vxtwitter.com")
#: bilibili 的替代網址前綴
BILIBILI_FIX_BASE = "https://www.vxbilibili.com/video/"
#: bilibili 網址裡要留下來的參數：分 P、時間點
_BILIBILI_KEEP_PARAMS = ("p", "t")

# 認得的貼文連結（給展開內容用）：x.com／twitter.com 本身，加上 fixupx 這類嵌入服務改寫後的網址——
# bot 自己轉貼的就是替代網域，群友回覆它時要從這裡認出是哪一篇。
TWEET_LINK_RE = re.compile(
    r"https?://(?:www\.|mobile\.)?(?:x|twitter|fixupx|fxtwitter|vxtwitter|fixvx)\.com/"
    r"[A-Za-z0-9_]+/status/(?P<id>\d+)",
    re.IGNORECASE,
)

# bot 轉貼用到的替代網址（認自動轉貼用）
_REPOST_URL_RE = re.compile(r"https?://(?:www\.)?(?:fixupx|vxtwitter|vxbilibili)\.com/\S+", re.IGNORECASE)

_SPOILER_RE = re.compile(r"\|\|(.+?)\|\|", re.DOTALL)

# Twitter 自家 syndication CDN（查類型用，免金鑰）。
_SYNDICATION_URL = "https://cdn.syndication.twimg.com/tweet-result"
_SYNDICATION_TIMEOUT = 8  # 秒；查不到就走 fail-open，不要卡太久

#: 預檢用的 UA：跟 Discord 抓預覽時一樣，替代服務才會回預覽頁
DISCORDBOT_UA = "Mozilla/5.0 (compatible; Discordbot/2.0; +https://discordapp.com)"
_PROBE_TIMEOUT = 8  # 秒；Discord 自己抓預覽也不會等太久，太慢的服務當成做不出來
#: 預覽標籤都在 <head>，只讀開頭這麼多
_PROBE_MAX_BYTES = 256 * 1024
#: 有這些標籤之一（內容不是空的）才算做得出影片或圖片預覽；只有標題的不算
_MEDIA_META_KEYS = frozenset({
    "og:video", "og:video:url", "og:video:secure_url", "twitter:player:stream",
    "og:image", "og:image:url", "og:image:secure_url", "twitter:image",
})
_META_TAG_RE = re.compile(r"<meta\b[^>]*>", re.IGNORECASE)
_LINK_TAG_RE = re.compile(r"<link\b[^>]*>", re.IGNORECASE)
_STATUS_ID_RE = re.compile(r"/statuses/([A-Za-z0-9]+)")
_ATTR_RE = re.compile(r"""([a-zA-Z:_-]+)\s*=\s*(?:"([^"]*)"|'([^']*)')""")

_BASE36 = "0123456789abcdefghijklmnopqrstuvwxyz"


@dataclass(frozen=True)
class FixableLink:
    """訊息裡一個可以轉的連結。"""

    kind: str                     # "x" 或 "bilibili"
    candidates: tuple[str, ...]   # 依序預檢的替代網址
    spoiler: bool                 # 原連結在 `||…||` 裡
    tweet_id: str = ""            # X 才有：查貼文類型用


@dataclass(frozen=True)
class FixedLink:
    """預檢過、要轉貼出去的替代網址。"""

    url: str
    spoiler: bool


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


def _spoiler_spans(content: str) -> list[tuple[int, int]]:
    return [(m.start(1), m.end(1)) for m in _SPOILER_RE.finditer(content)]


def _bilibili_query(query: str | None) -> str:
    """只留分 P 與時間點，其他（spm_id_from、vd_source、trackid、share_*）都是追蹤用的。"""
    if not query:
        return ""
    kept = [(k, v) for k, v in parse_qsl(query.lstrip("?"), keep_blank_values=False) if k in _BILIBILI_KEEP_PARAMS]
    return f"?{urlencode(kept)}" if kept else ""


def find_fixable_links(content: str) -> list[FixableLink]:
    """訊息裡可以轉的連結，照出現順序、同一個替代網址只算一次。純字串處理，不連網。"""
    if not content:
        return []
    spans = _spoiler_spans(content)

    def in_spoiler(pos: int) -> bool:
        return any(start <= pos < end for start, end in spans)

    found: list[tuple[int, FixableLink]] = []
    for m in TWITTER_STATUS_RE.finditer(content):
        # 去掉追蹤用的 query string：連結比較乾淨，也不影響預覽
        candidates = tuple(f"https://{domain}/{m.group('path')}" for domain in X_FIX_DOMAINS)
        found.append((m.start(), FixableLink("x", candidates, in_spoiler(m.start()), m.group("id"))))
    for m in BILIBILI_VIDEO_RE.finditer(content):
        url = f"{BILIBILI_FIX_BASE}{m.group('bv')}{_bilibili_query(m.group('query'))}"
        found.append((m.start(), FixableLink("bilibili", (url,), in_spoiler(m.start()))))

    out: list[FixableLink] = []
    seen: set[str] = set()
    for _pos, link in sorted(found, key=lambda item: item[0]):
        if link.candidates[0] in seen:
            continue
        seen.add(link.candidates[0])
        out.append(link)
    return out


def repost_text(fixed: list[FixedLink]) -> str:
    """轉貼訊息的內文：一行一個網址；原連結在暴雷裡就照包 `||`，不然會把群友遮起來的東西直接秀出來。"""
    return "\n".join(f"||{f.url}||" if f.spoiler else f.url for f in fixed)


def is_repost_text(text: str) -> bool:
    """這段文字是不是只有替代網址（暴雷的 `||` 不算內容）——bot 的自動轉貼就長這樣。"""
    tokens = (text or "").replace("||", " ").split()
    return bool(tokens) and all(_REPOST_URL_RE.fullmatch(t) for t in tokens)


def has_media_meta(html: str) -> bool:
    """頁面上有沒有影片或圖片的預覽標籤（`property=` 與 `name=` 兩種寫法都認，vxtwitter 用 `name=`）。"""
    for tag in _META_TAG_RE.findall(html or ""):
        attrs = {name.lower(): (dq or sq) for name, dq, sq in _ATTR_RE.findall(tag)}
        key = (attrs.get("property") or attrs.get("name") or "").lower()
        if key in _MEDIA_META_KEYS and (attrs.get("content") or "").strip():
            return True
    return False


def status_api_url(html: str) -> str | None:
    """頁面上的 `application/activity+json` 連結 → 同一站的 Mastodon 相容 API（`/api/v1/statuses/<id>`）；沒有回 None。"""
    for tag in _LINK_TAG_RE.findall(html or ""):
        attrs = {name.lower(): (dq or sq) for name, dq, sq in _ATTR_RE.findall(tag)}
        if (attrs.get("rel") or "").lower() != "alternate" or (attrs.get("type") or "").lower() != "application/activity+json":
            continue
        href = attrs.get("href") or ""
        parts = urlsplit(href)
        found = _STATUS_ID_RE.search(parts.path)
        if parts.scheme in ("http", "https") and parts.netloc and found:
            return f"{parts.scheme}://{parts.netloc}/api/v1/statuses/{found.group(1)}"
    return None


async def _status_has_media(session, api_url: str, timeout) -> bool:
    async with session.get(api_url, headers={"User-Agent": DISCORDBOT_UA}, timeout=timeout) as resp:
        if resp.status != 200:
            return False
        try:
            data = await resp.json(content_type=None)
        except ValueError:
            return False
    attachments = data.get("media_attachments") if isinstance(data, dict) else None
    return any(isinstance(a, dict) and a.get("url") for a in attachments or ())


async def probe_preview(session, url: str) -> bool:
    """用 Discord 爬蟲的身分抓一次替代網址，看做不做得出影片或圖片預覽。逾時、非 200、連不上都算做不出來。

    先看頁面標籤（vxtwitter、vxbilibili）；沒有就照頁面上的 activity+json 連結讀 Mastodon 相容 API（fixupx）。
    """
    import aiohttp

    timeout = aiohttp.ClientTimeout(total=_PROBE_TIMEOUT)
    try:
        async with session.get(url, headers={"User-Agent": DISCORDBOT_UA}, timeout=timeout) as resp:
            if resp.status != 200:
                logger.info("預檢 %s 回 %s，當成做不出預覽", url, resp.status)
                return False
            body = await resp.content.read(_PROBE_MAX_BYTES)
        html = body.decode("utf-8", errors="replace")
        if has_media_meta(html):
            return True
        api_url = status_api_url(html)
        if api_url and await _status_has_media(session, api_url, timeout):
            return True
    except (asyncio.TimeoutError, aiohttp.ClientError) as exc:
        logger.info("預檢 %s 失敗，當成做不出預覽：%s", url, exc)
        return False
    logger.info("預檢 %s 沒有影片或圖片，當成做不出預覽", url)
    return False


def tweet_ids(text: str) -> list[str]:
    """文字裡出現的貼文 id（含 fixupx 等改寫網址），去重、照出現順序。"""
    return list(dict.fromkeys(m.group("id") for m in TWEET_LINK_RE.finditer(text or "")))


async def fetch_tweet(session, tweet_id: str) -> tuple[str, dict | None]:
    """查 syndication CDN 取單則貼文。回傳 `(狀態, 資料)`，狀態是：

        "ok"        → 有貼文主體，資料是 CDN 回的 dict（內文、作者、mediaDetails…）
        "not_found" → 服務明確回 404 / tombstone（確定不存在）
        "unknown"   → 逾時 / 5xx / 內容無法解析 / 沒有貼文主體（服務問題，無法判斷）

    判斷要不要轉（`_classify_tweet`）與給 AI 看的貼文內容（`llm.preprocess.tweet_context`）共用這支。
    """
    import aiohttp

    url = (
        f"{_SYNDICATION_URL}?id={tweet_id}&lang=en&token={get_token(tweet_id)}"
    )
    try:
        timeout = aiohttp.ClientTimeout(total=_SYNDICATION_TIMEOUT)
        async with session.get(url, timeout=timeout) as resp:
            if resp.status == 404:
                return "not_found", None
            if resp.status >= 500:
                return "unknown", None

            try:
                data = await resp.json(content_type=None)
            except Exception:
                # 空 body / 非 JSON（常見於被限流）→ 當服務問題，fail-open。
                return "unknown", None

            if not isinstance(data, dict) or not data:
                return "unknown", None

            # tombstone / 已刪 → 確定不存在。
            if data.get("__typename") == "TweetTombstone" or "tombstone" in data:
                return "not_found", None

            # 沒有任何貼文主體欄位（例如限流回 {}）→ 視為服務問題，fail-open。
            if not any(k in data for k in ("mediaDetails", "text", "id_str")):
                return "unknown", None

            return "ok", data
    except asyncio.TimeoutError:
        logger.warning("查詢 tweet %s 逾時，視為服務問題（fail-open）", tweet_id)
        return "unknown", None
    except Exception as exc:
        logger.warning("查詢 tweet %s 失敗，視為服務問題（fail-open）：%s", tweet_id, exc)
        return "unknown", None


async def _classify_tweet(session, tweet_id: str) -> str:
    """查 syndication CDN 判斷單則貼文類型。

    回傳：
        "video"     → 推文存在且含影片（含 Twitter GIF，本質也是影片，Discord 同樣播不了）
        "non_video" → 推文存在但無影片（純圖片 / 純文字）
        "not_found" → 服務明確回 404 / tombstone / 沒有貼文主體（確定不存在）
        "unknown"   → 逾時 / 5xx / 內容無法解析（服務問題，無法判斷）
    """
    status, data = await fetch_tweet(session, tweet_id)
    if status != "ok":
        return status
    media = data.get("mediaDetails") or []
    has_video = any(m.get("type") in ("video", "animated_gif") for m in media)
    # 保險：頂層 video 欄位也算。
    if not has_video and data.get("video"):
        has_video = True
    return "video" if has_video else "non_video"


async def select_fixed_links(content: str, session=None) -> list[FixedLink]:
    """挑出真的要轉貼的替代網址。

    先用 regex 擋格式（本地、免網路），沒有可轉的連結就直接回空、不開 session（多數訊息走這條）；
    X 再查類型，只留影片或問不到的；最後每個連結的替代網址依序預檢，第一個做得出預覽的才用。

    session 可由呼叫端注入（方便測試、共用連線池）；不給就自開自關。
    """
    links = find_fixable_links(content)
    if not links:
        return []

    own_session = session is None
    if own_session:
        import aiohttp

        session = aiohttp.ClientSession()
    try:
        fixed: list[FixedLink] = []
        for link in links:
            if link.kind == "x":
                decision = await _classify_tweet(session, link.tweet_id)
                # 只在「確定有影片」或「服務掛掉問不到」時才轉；非影片／不存在一律放生
                if decision not in ("video", "unknown"):
                    continue
            for url in link.candidates:
                if await probe_preview(session, url):
                    fixed.append(FixedLink(url, link.spoiler))
                    break
            else:
                logger.warning("替代網址都做不出預覽，不轉：%s", ", ".join(link.candidates))
    finally:
        if own_session:
            await session.close()
    return fixed
