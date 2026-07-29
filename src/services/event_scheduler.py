"""
活動公告 → 自動建立 Discord 伺服器活動（副作用層）。

流程：閘門(channel==config.article_monitor_channel_id) → parse_events → 相對起點版本日回填
      → 跨來源活動指紋去重(created_events) → clamp start 到未來 → create_scheduled_event → 記指紋。
全程 best-effort：任何失敗只 log、不拋（絕不拖垮轉發主流程）。
掛點：article_monitor.send_article_to_channel / fb_monitor.send_fb_post_to_channel 尾巴。

設計依據：對 articles.db 全 490 篇對抗審查（2026-07-01）。詳見
AI_HANDOFF_AND_TODO.md「活動公告 → 自動建立 Discord 伺服器活動」區塊。
"""
from __future__ import annotations

import asyncio
import logging
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

# 注意：discord / ChannelConfig / StateDB 等相依只在 maybe_schedule_events 內 lazy import，
# 讓本模組的純邏輯（VersionDateResolver / plan_events）可在無 discord 環境被單測。
from services.event_time_parser import (
    ParsedEvent, parse_events, event_fingerprint, SERVER_TZ,
)

logger = logging.getLogger("discord_bot")

# external 活動固定地點（多遊戲後續再抽）
LOCATION = "鳴潮"
# Discord 要求 start 在未來；clamp 緩衝
START_BUFFER = timedelta(minutes=5)
# 單篇最多建幾個（防匯總帖異常爆量）
MAX_EVENTS_PER_POST = 15

# 「總表公告」：【3.5版本】[角色/武器活動喚取・第二期] 這類把當期多個卡池寫成一則的公告。
# 用途＝**收斂成一則**（見 plan_events）：內文各卡池標題行不拆開，一律用貼文標題當活動名與指紋基準。
# 這樣 article 總表與 FB 總表貼文指紋一致，靠既有 is_event_created 就擋得住跨來源重複。
# 註：總表**不是**各卡池獨立公告的重複——查證 3.2~3.5 全部檔期，官方是「一部分卡池發獨立公告、
# 其餘包進總表」，兩者互補；故不可因「同區間已有活動」就跳過總表，否則會漏掉只存在總表裡的卡池。
_UMBRELLA_TITLE = re.compile(r'\d+\.\d+\s*版本.*角色.*武器.*喚取|角色\s*/\s*武器.*喚取')


def is_umbrella_title(name: str) -> bool:
    """是否為當期多卡池的總表公告標題。"""
    return bool(_UMBRELLA_TITLE.search(name or ""))

# articles.db 路徑（discord-bot 容器掛 ./src → /app；版本日回填用，RO）
_ARTICLES_DB = Path(__file__).resolve().parent.parent / "scraper" / "articles.db"


# ── 版本更新日回填（相對起點「X版本更新後」→ 版本真實上線時間） ──

class VersionDateResolver:
    """從 articles.db 的版本內容說明帖擷取各版本『更新維護時間』，供相對起點回填。

    來源：標題含『X.Y版本…』且內文含『更新維護時間：…日期…』的帖。
    取維護時間範圍的**最後一個日期**（維護結束＝版本上線）當該版本起點。
    一次掃描快取；查不到的版本回 None（上層據此 SKIP，寧可漏不可錯）。
    """

    _VER_IN_TITLE = re.compile(r'(\d+\.\d+)\s*版本')
    _MAINT_LINE = re.compile(r'更新維護時間[：:]\s*([^\n]{0,80})')
    _DATE = re.compile(
        r'(\d{4})\s*[/年]\s*(\d{1,2})\s*[/月]\s*(\d{1,2})\s*日?\s*(\d{1,2})\s*[:：]\s*(\d{2})'
    )

    def __init__(self, db_path: Path = _ARTICLES_DB):
        self.db_path = db_path
        self._map: Optional[dict] = None

    def _load(self) -> dict:
        result: dict = {}
        try:
            con = sqlite3.connect(f"file:{self.db_path}?mode=ro&immutable=1", uri=True)
            try:
                rows = con.execute(
                    "SELECT article_title, article_content FROM article_details "
                    "WHERE article_content LIKE '%更新維護時間%'"
                ).fetchall()
            finally:
                con.close()
        except Exception as e:
            logger.warning("[event] 版本日回填載入失敗（articles.db 不可讀？）: %s", e)
            return result

        for title, content in rows:
            vm = self._VER_IN_TITLE.search(title or "")
            if not vm:
                continue
            version = vm.group(1)
            # 去 HTML，抓維護時間行的最後一個日期
            import html as _html
            text = _html.unescape(re.sub(r'<[^>]+>', '', content or ''))
            line = self._MAINT_LINE.search(text)
            if not line:
                continue
            dates = self._DATE.findall(line.group(1))
            if not dates:
                continue
            y, mo, d, h, mi = (int(x) for x in dates[-1])  # 最後一個＝維護結束＝版本上線
            try:
                dt = datetime(y, mo, d, h, mi, tzinfo=SERVER_TZ)
            except ValueError:
                continue
            # 同版本取最早一筆（最初公告）
            if version not in result or dt < result[version]:
                result[version] = dt
        logger.info("[event] 版本日回填載入 %s 個版本：%s", len(result),
                    ", ".join(f"{k}={v:%Y/%m/%d}" for k, v in sorted(result.items())))
        return result

    def ensure_loaded(self) -> None:
        if self._map is None:
            self._map = self._load()

    def update_time(self, version: Optional[str]) -> Optional[datetime]:
        if not version:
            return None
        self.ensure_loaded()
        return (self._map or {}).get(version)


_version_resolver = VersionDateResolver()


def parse_source_time(s) -> Optional[datetime]:
    """把來源的發布時間字串/物件轉成 UTC+8 aware datetime（缺年補年、clamp 用）。"""
    if s is None:
        return None
    if isinstance(s, datetime):
        return s if s.tzinfo else s.replace(tzinfo=SERVER_TZ)
    text = str(s).strip()
    if not text:
        return None
    # ISO（FB timestamp 可能帶 Z / 時區）
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt.astimezone(SERVER_TZ) if dt.tzinfo else dt.replace(tzinfo=SERVER_TZ)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text.split("+")[0].strip(), fmt).replace(tzinfo=SERVER_TZ)
        except ValueError:
            continue
    return None


async def _download_image_bytes(url: Optional[str], *, max_bytes: int = 8 * 1024 * 1024) -> Optional[bytes]:
    """下載封面圖 bytes（best-effort）。失敗 / 非 200 / 過大 → None；只在記憶體用完即丟，不落地不進 DB。"""
    if not url:
        return None
    try:
        import aiohttp
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10, headers=headers) as resp:
                if resp.status != 200:
                    return None
                data = await resp.read()
        if not data or len(data) > max_bytes:
            return None
        return data
    except Exception as e:
        logger.warning("[event] 封面圖下載失敗（略過圖）: %s", e)
        return None


def _first_content_image(html_text: Optional[str]) -> Optional[str]:
    """從 HTML 內文抓第一張 <img> 的 src（封面欄位皆空時的 fallback，對齊 embed 取圖）。"""
    if not html_text:
        return None
    m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', html_text)
    return m.group(1) if m else None


# ── 規劃（純：不碰 discord/db；產出待建清單） ──

@dataclass
class PlannedEvent:
    name: str
    start: datetime          # clamp 後（送 Discord 用）
    logical_start: datetime  # 真實活動起點（寫進描述）
    end: datetime
    description: str
    fingerprint: str
    source: str
    source_id: str


def plan_events(
    parsed: List[ParsedEvent],
    *,
    title: str,
    source: str,
    source_id: str,
    url: Optional[str],
    version_resolver: Optional[VersionDateResolver],
    now: datetime,
    post_time: Optional[datetime] = None,
) -> List[PlannedEvent]:
    """把解析出的事件轉成待建清單（解起點、算指紋、clamp、本地去重）。

    起點三類：
      - 絕對日期 → 直接用。
      - 「X版本更新後」→ 版本日回填；解不到 → SKIP。
      - 「即日起/即時」→ 貼文日壓 00:00（UTC+8）；無貼文日 → SKIP。
      - 其餘無法判定的相對描述 → SKIP（寧可漏不可錯）。
    """
    planned: List[PlannedEvent] = []
    local_seen = set()
    # 總表公告（整期卡池包成一則）：不拆各卡池，一律用貼文標題。
    # 各卡池另有獨立公告會各自建活動，拆了必重複；同期卡池區間相同，收斂後本地去重自然併成一則。
    umbrella = is_umbrella_title(title or "")

    for ev in parsed:
        if ev.start is not None:
            logical_start = ev.start
        elif ev.is_relative_start:
            logical_start = version_resolver.update_time(ev.start_relative_version) if version_resolver else None
        elif ev.is_immediate_start and post_time is not None:
            # 即日起 → 貼文日壓 00:00（伺服器時區）
            logical_start = post_time.astimezone(SERVER_TZ).replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            logical_start = None
        if logical_start is None:
            continue  # 起點無法判定 → SKIP（寧可漏不可錯，且防 None 比較炸）

        end = ev.end
        discord_start = max(now + START_BUFFER, logical_start)
        if discord_start >= end:
            continue  # 已結束 / 區間無效

        # 顯示標題：總表公告與單事件用「貼文自然標題」（article_title / FB 首行；一致、可讀）；
        # 多事件（版本內容說明匯總帖）才用逐活動括號名區分。
        headline = (title or "").strip()
        if headline and (umbrella or len(parsed) == 1):
            display_name = headline
        else:
            display_name = ev.title_hint or headline or "鳴潮活動"

        # 指紋核心：總表用貼文標題（與 FB 總表貼文同基準才對得上），其餘維持原基準
        fp_basis = headline if (umbrella and headline) else (ev.title_hint or headline)
        fp = event_fingerprint(fp_basis, logical_start, end)
        if fp in local_seen:
            continue
        local_seen.add(fp)

        planned.append(PlannedEvent(
            name=(display_name.strip()[:100] or "鳴潮活動"),
            start=discord_start,
            logical_start=logical_start,
            end=end,
            description=_build_description(logical_start, end, url, ev),
            fingerprint=fp,
            source=source,
            source_id=str(source_id),
        ))
        if len(planned) >= MAX_EVENTS_PER_POST:
            break

    return planned


def _build_description(logical_start: datetime, end: datetime, url: Optional[str], ev: ParsedEvent) -> str:
    """url：優先為本站轉發訊息的 Discord jump link（點了直接跳到公告那則，好追來源）；
    拿不到訊息時才退回官方原文連結。"""
    lines = [
        f"活動時間：{logical_start:%Y/%m/%d %H:%M} ~ {end:%Y/%m/%d %H:%M}（伺服器時間 UTC+8）",
    ]
    if ev.is_relative_start:
        lines.append(f"（起點由 {ev.start_relative_version} 版本更新時間回填）")
    if url:
        lines.append("")
        lines.append(f"公告出處：{url}")
    return "\n".join(lines)[:1000]


# ── 副作用入口（掛在 monitor send 尾巴；best-effort 不拋） ──

async def maybe_schedule_events(
    bot,
    *,
    source: str,
    source_id,
    title: str,
    text: str,
    post_time: Optional[datetime],
    url: Optional[str],
    channel_id: int,
    is_html: bool,
    image_url: Optional[str] = None,
    message_url: Optional[str] = None,
) -> None:
    """偵測公告內活動時間並（依設定 dry-run / 實建）建立 Discord 伺服器活動。

    image_url：該篇 article/FB 貼文的封面圖，會下載後掛到活動當封面（best-effort，
    不落地、不寫 DB）；下載失敗或無圖則活動無封面。
    message_url：本次轉發那則 Discord 訊息的 jump link，寫進活動描述當「公告出處」
    （點了直接跳到伺服器內的公告訊息）；拿不到時退回官方原文連結 url。
    """
    try:
        import discord
        from utils.utils import ChannelConfig
        from services.base_monitor import get_shared_state_db

        config = ChannelConfig.load_config(caller="event_scheduler")
        # 閘門：只處理發進「活動公告頻道」(= article_monitor_channel_id) 的內容，即時讀、自動同步
        if str(channel_id) != str(config.get("article_monitor_channel_id")):
            return
        if not config.get("event_schedule_enabled", True):
            return
        dry_run = bool(config.get("event_schedule_dry_run", True))  # 首批保險：預設 dry-run

        events = parse_events(text, post_time=post_time, is_html=is_html, fallback_title=title or "")
        if not events:
            return

        channel = bot.get_channel(int(channel_id))
        guild = getattr(channel, "guild", None)
        if guild is None:
            logger.warning("[event] 找不到 guild（channel_id=%s）", channel_id)
            return

        await asyncio.to_thread(_version_resolver.ensure_loaded)
        now = datetime.now(timezone.utc)
        planned = plan_events(
            events, title=title or "", source=source, source_id=source_id,
            url=(message_url or url), version_resolver=_version_resolver,
            now=now, post_time=post_time,
        )
        if not planned:
            return

        db = await get_shared_state_db()
        cover_bytes = None      # 封面圖 bytes（best-effort、下載一次供本篇所有事件共用、不落地/不進 DB）
        cover_fetched = False
        for p in planned:
            # 跨來源指紋去重總閘（擋 Article↔FB 雙報、重跑、FB 內部重複列）
            if await db.is_event_created(p.fingerprint):
                continue

            s8 = p.logical_start.astimezone(SERVER_TZ).strftime("%Y-%m-%d %H:%M")
            e8 = p.end.astimezone(SERVER_TZ).strftime("%Y-%m-%d %H:%M")

            if dry_run:
                logger.info("[event][dry-run] 待建活動 | %s | %s ~ %s | src=%s:%s | fp=%s",
                            p.name, s8, e8, p.source, p.source_id, p.fingerprint)
                continue

            # 首次真要建時才下載封面圖（附加到活動、不寫 DB）
            if not cover_fetched:
                cover_bytes = await _download_image_bytes(image_url)
                cover_fetched = True

            create_kwargs = dict(
                name=p.name,
                start_time=p.start,
                end_time=p.end,
                entity_type=discord.EntityType.external,
                privacy_level=discord.PrivacyLevel.guild_only,
                location=LOCATION,
                description=p.description,
            )
            if cover_bytes:
                create_kwargs["image"] = cover_bytes

            try:
                created = await guild.create_scheduled_event(**create_kwargs)
                await db.record_created_event(
                    p.fingerprint,
                    discord_event_id=created.id,
                    guild_id=guild.id,
                    source=p.source,
                    source_id=p.source_id,
                    title=p.name,
                    start_utc8=s8,
                    end_utc8=e8,
                )
                logger.info("[event] ✅ 已建立伺服器活動：%s (id=%s) %s ~ %s",
                            p.name, created.id, s8, e8)
            except discord.HTTPException as e:
                logger.warning("[event] 建立活動失敗（Discord 拒絕）：%s | %s", p.name, e)
            except Exception as e:
                logger.warning("[event] 建立活動失敗：%s | %s", p.name, e)

    except Exception as e:
        logger.warning("[event] maybe_schedule_events 例外（已吞，不影響轉發）：%s", e)


# ── 各來源薄 adapter（欄位對應住「活動功能自己家」；monitor 呼叫端變一行、best-effort 不拋） ──

async def schedule_from_article(bot, article: dict, channel_id: int,
                                message_url: Optional[str] = None) -> None:
    """從官方文章 dict 觸發活動偵測。欄位對應集中於此，article_monitor 只需一行呼叫。"""
    try:
        text = (article.get("article_content_full") or article.get("article_content")
                or article.get("article_desc") or "")
        # 封面：優先指定封面欄位，皆空則退用內文第一張圖（對齊 format_article_embed 取圖）
        image_url = (article.get("article_cover") or article.get("content_cover")
                     or article.get("suggest_cover") or _first_content_image(text))
        await maybe_schedule_events(
            bot, source="article", source_id=article.get("article_id"),
            title=article.get("article_title", ""),
            text=text,
            post_time=parse_source_time(article.get("start_time") or article.get("create_time")),
            url=f"https://wutheringwaves.kurogames.com/zh-tw/main/news/detail/{article.get('article_id')}",
            channel_id=channel_id, is_html=True,
            image_url=image_url, message_url=message_url,
        )
    except Exception as e:
        logger.warning("[event] article 活動偵測失敗（已吞）: %s", e)


async def schedule_from_fb(bot, fb_post: dict, channel_id: int,
                           message_url: Optional[str] = None) -> None:
    """從 FB 貼文 dict 觸發活動偵測。標題取內文首行（＝貼文標題，與 article_title 一致風格）。"""
    try:
        text = fb_post.get("text_md") or fb_post.get("text") or ""
        first_line = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
        await maybe_schedule_events(
            bot, source="fb", source_id=fb_post.get("id"),
            title=first_line,
            text=text,
            post_time=parse_source_time(fb_post.get("timestamp") or fb_post.get("created_at")),
            url=(fb_post.get("url") or fb_post.get("pfbid_url")),
            channel_id=channel_id, is_html=False,
            image_url=(fb_post.get("images") or [None])[0],
            message_url=message_url,
        )
    except Exception as e:
        logger.warning("[event] fb 活動偵測失敗（已吞）: %s", e)
