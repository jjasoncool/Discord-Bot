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
    ParsedEvent, parse_events, event_fingerprint, normalize_title, SERVER_TZ,
)

logger = logging.getLogger("discord_bot")

# external 活動固定地點（多遊戲後續再抽）
LOCATION = "鳴潮"
# Discord 要求 start 在未來；clamp 緩衝
START_BUFFER = timedelta(minutes=5)
# 單篇最多建幾個（防匯總帖異常爆量）
MAX_EVENTS_PER_POST = 15
# Discord 伺服器活動描述上限
DESCRIPTION_LIMIT = 1000

# 建立/升級活動的序列化鎖：article 與 fb 兩條 notify 路徑會並行，
# 而「查指紋 → 建活動 → 記指紋」中間有多個 await，沒鎖會讓同一個活動被建兩次。
_SCHEDULE_LOCK = asyncio.Lock()


# 「活動預告 | <X> …即將開啟！」這種預告帖標題。收 <> 進核心名之後，預告帖與正式公告會
# 合併成同一個活動，若名稱停在預告帖，活動都開跑一個月了還寫著「即將開啟」。
_PREVIEW_TITLE = re.compile(r'活動預告|即將開啟|即將上線|即將登場')


def is_preview_title(name: str) -> bool:
    """是否為「預告」型標題（只配當暫時的名字，正式公告到了要換掉）。"""
    return bool(_PREVIEW_TITLE.search(name or ""))


# 「總表公告」：【3.5版本】[角色/武器活動喚取・第二期] 這類把當期多個卡池寫成一則的公告。
# 用途＝**收斂成一則**（見 plan_events）：內文各卡池標題行不拆開，一律用貼文標題當活動名與指紋基準。
# 這樣 article 總表與 FB 總表貼文指紋一致，去重時查得到同一列（見 maybe_schedule_events
# 的 get_created_event / find_overlapping_event），跨來源重複就擋得住。
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
    core_name: str = ""      # 指紋核心名（同名改期比對用）
    body: str = ""           # 活動段落片段
    # 以下三個是為了「升級時重建描述」而帶著走的零件：改期必須重寫描述（時間就寫在第一行），
    # 但那時可能要沿用既有的較長片段，所以不能只留組好的字串。
    note: str = ""           # 「（起點由 X 版本更新時間回填）」之類的附註
    link: Optional[str] = None        # 公告出處（Discord jump link）
    source_url: Optional[str] = None  # 官方原文


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
    source_url: Optional[str] = None,
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
            # 起點無法判定 → SKIP（寧可漏不可錯，且防 None 比較炸）
            logger.info("[event] 略過（起點解不出）｜%s｜來源=%s:%s｜起點原文=%r",
                        ev.title_hint or title, source, source_id, ev.start_raw)
            continue

        end = ev.end
        discord_start = max(now + START_BUFFER, logical_start)
        if discord_start >= end:
            logger.info("[event] 略過（已結束/區間無效）｜%s｜%s ~ %s｜來源=%s:%s",
                        ev.title_hint or title,
                        logical_start.astimezone(SERVER_TZ).strftime("%Y-%m-%d %H:%M"),
                        end.astimezone(SERVER_TZ).strftime("%Y-%m-%d %H:%M"), source, source_id)
            continue

        # 顯示標題：總表公告與單事件用「貼文自然標題」（article_title / FB 首行；一致、可讀）；
        # 多事件（版本內容說明匯總帖）才用逐活動括號名區分。
        headline = (title or "").strip()
        if headline and (umbrella or len(parsed) == 1):
            display_name = headline
        else:
            display_name = ev.title_hint or headline or "鳴潮活動"

        # 指紋核心：總表用貼文標題（與 FB 總表貼文同基準才對得上），其餘維持原基準
        note = (f"（起點由 {ev.start_relative_version} 版本更新時間回填）"
                if ev.is_relative_start else "")
        fp_basis = headline if (umbrella and headline) else (ev.title_hint or headline)
        fp = event_fingerprint(fp_basis, logical_start, end)
        if fp in local_seen:
            continue  # 同帖同活動重複列（總表收斂後必然發生，屬正常）
        local_seen.add(fp)

        planned.append(PlannedEvent(
            name=(display_name.strip()[:100] or "鳴潮活動"),
            start=discord_start,
            logical_start=logical_start,
            end=end,
            description=_build_description(logical_start, end, url, note=note,
                                           body=ev.body, source_url=source_url),
            fingerprint=fp,
            source=source,
            source_id=str(source_id),
            core_name=normalize_title(fp_basis),
            body=ev.body,
            note=note,
            link=url,
            source_url=source_url,
        ))
        if len(planned) >= MAX_EVENTS_PER_POST:
            # 靜默截斷會讓活動永遠漏掉（來源已 mark_content_as_sent，不會重試）
            logger.warning("[event] ⚠️ 單帖活動數達上限 %s，其餘已截斷｜來源=%s:%s｜共解出 %s 個",
                           MAX_EVENTS_PER_POST, source, source_id, len(parsed))
            break

    return planned


def _build_description(
    logical_start: datetime,
    end: datetime,
    url: Optional[str] = None,
    *,
    note: str = "",
    body: str = "",
    source_url: Optional[str] = None,
) -> str:
    """組活動描述：時間 → 該活動的敘述片段 → 公告出處 ＋ 官方原文。

    為什麼要放片段：一則匯總帖會產生 N 個活動，但 jump link 的最小粒度是「一則訊息」，
    點過去無法定位到其中某一個活動；而轉發訊息本身也只帶公告前段。
    把該活動自己的敘述帶進來，使用者在活動頁就看得懂，不必跳轉。

    url：本站轉發訊息的 Discord jump link；source_url：官方原文（全文在那裡）。
    片段是輔助、連結是退路，所以**先保住時間行與連結**，剩下的空間才給片段。
    """
    head = [f"活動時間：{logical_start:%Y/%m/%d %H:%M} ~ {end:%Y/%m/%d %H:%M}（伺服器時間 UTC+8）"]
    if note:
        head.append(note)

    tail = []
    if url:
        tail.append(f"公告出處：{url}")
    if source_url and source_url != url:
        tail.append(f"官方原文：{source_url}")

    head_text, tail_text = "\n".join(head), "\n".join(tail)
    room = DESCRIPTION_LIMIT - len(head_text) - len(tail_text) - 4  # 4＝兩個空行
    parts = [head_text]
    body = (body or "").strip()
    if body and room > 40:
        parts.extend(["", body if len(body) <= room else body[:room - 1].rstrip() + "…"])
    if tail_text:
        parts.extend(["", tail_text])
    return "\n".join(parts)[:DESCRIPTION_LIMIT]


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
    force: bool = False,
) -> None:
    """偵測公告內活動時間並（依設定 dry-run / 實建）建立 Discord 伺服器活動。

    image_url：該篇 article/FB 貼文的封面圖，會下載後掛到活動當封面（best-effort，
    不落地、不寫 DB）；下載失敗或無圖則活動無封面。
    force：只有 `/resend_article` 會傳 True —— 人明確要求重抓，才允許解除「使用者刪掉」
    的墓碑並重建。自動來源（排程／推送）一律 False。
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
            now=now, post_time=post_time, source_url=url,
        )
        if not planned:
            return

        db = await get_shared_state_db()
        link = message_url or url

        # 封面圖：整篇共用、只下載一次（不落地、不進 DB）；建立與升級都會用到
        cover = {"bytes": None, "fetched": False}

        async def ensure_cover():
            if not cover["fetched"]:
                cover["fetched"] = True
                if not image_url:
                    logger.info("[event] 本篇無封面圖來源（活動將無封面）｜來源=%s:%s", source, source_id)
                else:
                    cover["bytes"] = await _download_image_bytes(image_url)
                    if cover["bytes"] is None:
                        logger.info("[event] 封面圖取不到（活動將無封面）：%s", image_url)
            return cover["bytes"]

        # 「查既有 → 建立/升級 → 寫回」中間有多個 await，article 與 fb 兩條 notify 會並行，
        # 沒有鎖會讓同一個活動被建兩次（TOCTOU）。
        async with _SCHEDULE_LOCK:
            try:
                await _migrate_fingerprints_once(db)
            except Exception as e:
                # 遷移沒成功就不能往下走：新指紋比對未遷移的舊列 = 整批重建
                logger.error("[event] 指紋遷移未完成，本次不建立任何活動（下次重試）：%s", e)
                return

            # 本輪已經配對或新建的指紋。用它（而不是「整則公告」）當重疊比對的排除清單：
            # 同一則匯總帖內部同名不同區間的活動不可互相吃掉，但 /resend_article 重送同一篇
            # 改期公告時，仍必須對得到自己先前那一列，否則會建出第二個活動。
            matched: set = set()

            for p in planned:
                s8 = p.logical_start.astimezone(SERVER_TZ).strftime("%Y-%m-%d %H:%M")
                e8 = p.end.astimezone(SERVER_TZ).strftime("%Y-%m-%d %H:%M")
                try:
                    # ① 指紋命中＝同活動同檔期；② 同名且區間重疊＝官方改期/延長（仍是同一個活動）
                    existing = await db.get_created_event(p.fingerprint)
                    if existing is None:
                        existing = await db.find_overlapping_event(
                            p.core_name, s8, e8, exclude_fingerprints=matched)
                    if existing:
                        matched.add(existing["event_fingerprint"])

                    # 墓碑：使用者自己從 Discord 刪掉的活動，**自動來源**一律不准復活。
                    # 只有 /resend_article（force）這種人明確要求重抓才解得開。
                    if existing and existing.get("user_deleted"):
                        if not force:
                            logger.info("[event] 已被使用者從 Discord 刪除，不重建｜%s｜fp=%s｜"
                                        "新來源=%s:%s", p.name, existing["event_fingerprint"],
                                        p.source, p.source_id)
                            continue
                        fp_dead = existing["event_fingerprint"]
                        if await _fetch_event(guild, existing.get("discord_event_id")) is not None:
                            # 活動只是被取消、還在伺服器上 → 解除墓碑後照常走升級
                            await db.clear_event_tombstone(fp_dead)
                            existing = await db.get_created_event(fp_dead)
                            logger.info("[event] /resend 解除墓碑（活動仍在，改走升級）｜%s", p.name)
                        else:
                            # 活動真的被刪了 → 整列丟掉，下面重新建一個
                            await db.delete_created_event(fp_dead)
                            existing = None
                            logger.info("[event] /resend 解除墓碑並重建（原活動已不在 Discord 上）｜%s",
                                        p.name)

                    if existing is None:
                        await _warn_same_name_elsewhere(db, p, s8, e8)

                    if dry_run:
                        logger.info("[event][dry-run] %s | %s | %s ~ %s | src=%s:%s | fp=%s",
                                    "升級既有活動" if existing else "待建活動",
                                    p.name, s8, e8, p.source, p.source_id, p.fingerprint)
                        continue

                    if existing:
                        await _upgrade_existing_event(guild, db, p, existing, s8=s8, e8=e8,
                                                      ensure_cover=ensure_cover,
                                                      image_url=image_url)
                    else:
                        await _create_event(guild, db, p, s8=s8, e8=e8,
                                            cover_bytes=await ensure_cover(), message_url=link)
                        matched.add(p.fingerprint)
                except Exception as e:
                    # 單一活動失敗不可拖垮同帖其餘活動：來源已 mark_content_as_sent，不會再重試
                    logger.warning("[event] 處理活動時例外（已跳過該筆，其餘續跑）：%s | %s", p.name, e)

    except Exception as e:
        logger.warning("[event] maybe_schedule_events 例外（已吞，不影響轉發）：%s", e)


# ── 建立 / 升級 / 指紋遷移（都在 _SCHEDULE_LOCK 內被呼叫） ──


async def _fetch_event(guild, event_id):
    """取 Discord 活動物件（先 cache、再打 API）。**只有真的被刪掉才回 None。**

    原本是 `except Exception: return None`，把 5xx／逾時／連線中斷全部壓成「活動不存在」，
    呼叫端就走「使用者刪掉了 → 不重建」然後什麼都不寫。但來源端早在呼叫本模組之前就
    mark_content_as_sent 了，這篇公告不會再被處理 —— 一次暫時性 API 失敗，等於這個來源
    帶來的封面與完整描述永久遺失，而 log 還宣稱活動被刪，排查會往錯方向找。
    暫時性錯誤一律往外拋，交給每筆各自的 try 記 warning。
    """
    if event_id in (None, ""):
        return None
    import discord

    event = guild.get_scheduled_event(int(event_id))
    if event is not None:
        return event
    try:
        return await guild.fetch_scheduled_event(int(event_id))
    except discord.NotFound:
        return None


async def _warn_same_name_elsewhere(db, p: PlannedEvent, s8: str, e8: str) -> None:
    """同名活動已存在、區間卻不重疊時示警（可能是官方改期到全新區間）。

    刻意**不自動合併**：不重疊也可能只是同一個活動的下一個檔期（[聲弦滌蕩] 每隔幾週開一次），
    自動併會把正常的循環活動吃掉。歷史資料上「改期」一次都沒出現過，寧可漏不可錯 ——
    但要讓人看得到，才不會默默多一個活動。
    """
    if not p.core_name:
        return
    try:
        siblings = await db.find_same_name_events(p.core_name)
    except Exception:
        return
    now8 = datetime.now(SERVER_TZ).strftime("%Y-%m-%d %H:%M")
    live = [r for r in siblings
            if not r.get("user_deleted") and (r.get("end_utc8") or "") > now8]
    if not live:
        return
    logger.warning(
        "[event] ⚠️ 同名活動已存在但區間不重疊，仍會新建（若是官方改期，請人工刪掉舊的）｜"
        "%s｜新=%s ~ %s｜既有=%s", p.name, s8, e8,
        "、".join(f"{r['start_utc8']}~{r['end_utc8']}(event={r['discord_event_id']})"
                  for r in live[:3]))


async def _create_event(guild, db, p: PlannedEvent, *, s8: str, e8: str,
                        cover_bytes: Optional[bytes], message_url: Optional[str]) -> None:
    """建立新活動並記錄指紋。建立成功後若寫 DB 失敗，**必須**分開報，不能謊報建立失敗。"""
    import discord

    kwargs = dict(
        name=p.name,
        start_time=p.start,
        end_time=p.end,
        entity_type=discord.EntityType.external,
        privacy_level=discord.PrivacyLevel.guild_only,
        location=LOCATION,
        description=p.description,
    )
    if cover_bytes:
        kwargs["image"] = cover_bytes

    try:
        created = await guild.create_scheduled_event(**kwargs)
    except discord.Forbidden:
        logger.error("[event] ❌ bot 缺少『管理活動』權限，自動建活動全面停擺（%s）", p.name)
        return
    except discord.HTTPException as e:
        logger.warning("[event] 建立活動失敗（Discord 拒絕）：%s | %s", p.name, e)
        return

    try:
        await db.record_created_event(
            p.fingerprint,
            discord_event_id=created.id, guild_id=guild.id,
            source=p.source, source_id=p.source_id, title=p.name,
            start_utc8=s8, end_utc8=e8,
            core_name=p.core_name, has_image=bool(cover_bytes), body=p.body,
        )
    except Exception as e:
        # 活動已經在 Discord 上了，只是指紋沒記到 → 下次同來源重送會再建一個
        logger.error("[event] ⚠️ 活動已建立但指紋寫入失敗（下次重送會重複建，請留意）"
                     "｜event_id=%s｜fp=%s｜%s", created.id, p.fingerprint, e)
        return

    logger.info("[event] ✅ 已建立伺服器活動：%s (id=%s) %s ~ %s｜封面=%s 片段=%s字｜來源=%s:%s",
                p.name, created.id, s8, e8, "有" if cover_bytes else "無",
                len(p.body), p.source, p.source_id)


async def _upgrade_existing_event(guild, db, p: PlannedEvent, existing: dict, *,
                                  s8: str, e8: str, ensure_cover, image_url) -> None:
    """既有活動已存在 → 把「這次帶來的東西比較好」的部分補上去。

    **四軸各自判斷，刻意不綁在一個總分上。**實作中途真的寫過「內容品質總分變高才換描述與
    封面」的版本，對全庫重放後確認不可行（422 筆規劃事件有 294 筆同分），三個症狀都真實發生：
      ① 官方改期時品質分通常沒變 → 走不進換描述的分支 → Discord 上活動時間改了，
         描述第一行的「活動時間：…」還是舊的，自相矛盾；
      ② 專屬帖（+1 分）必定覆蓋匯總帖，但專屬帖開頭常是劇情導言、匯總帖寫的才是玩法與獎勵
         → 描述反而變短（實測有 370 → 118 字）；
      ③ 分數沒變高就整筆 return，正式公告的內容永遠補不上（全庫 14.6% 的公告一個字都沒更新）。
    """
    import discord

    existing_body = existing.get("body") or ""
    existing_title = existing.get("title") or ""
    rescheduled = (existing.get("start_utc8") != s8 or existing.get("end_utc8") != e8)

    # ① 片段：明顯更豐富才換（門檻 +40 字，避免長度相近時來回抖動）
    better_body = bool(p.body) and (not existing_body or len(p.body) >= len(existing_body) + 40)
    # ② 封面：既有沒圖才補。既有已有圖就不動 —— 換圖對使用者沒有價值，只會反覆重傳
    wants_cover = (not existing.get("has_image")) and bool(image_url)
    # ③ 名稱：既有停在預告帖標題、而新來源是正式公告 → 換掉（否則活動開跑了還叫「即將開啟」）
    wants_rename = is_preview_title(existing_title) and not is_preview_title(p.name)

    if not (rescheduled or better_body or wants_cover or wants_rename):
        logger.info("[event] 已存在且沒有更好的內容，略過｜%s｜片段 %s→%s 字・封面=%s｜來源=%s:%s",
                    p.name, len(existing_body), len(p.body),
                    "有" if existing.get("has_image") else "無", p.source, p.source_id)
        return

    # 先確認活動還在，再決定要不要下載封面（避免白抓；實測單張約 0.8~1.0 MB）
    event = await _fetch_event(guild, existing.get("discord_event_id"))
    if event is None:
        # 活動在 Discord 上已不存在，而 DB 又沒有墓碑 → 多半是 bot 離線期間被刪。
        # 刻意不重建：使用者刪掉就是不想要；指紋留著繼續擋（墓碑機制見 state_db）。
        logger.info("[event] 既有活動在 Discord 上已不存在，略過升級且不重建｜fp=%s｜event_id=%s",
                    existing.get("event_fingerprint"), existing.get("discord_event_id"))
        return

    cover_bytes = await ensure_cover() if wants_cover else None

    # 改期時**必須**重建描述（活動時間就寫在第一行）；若這次的片段沒比較好，沿用既有片段，
    # 才不會為了修時間而把描述換成比較差的版本。
    body_for_desc = p.body if better_body else (existing_body or p.body)

    edits = {}
    if better_body or rescheduled:
        edits["description"] = _build_description(
            p.logical_start, p.end, p.link,
            note=p.note, body=body_for_desc, source_url=p.source_url,
        )
    if cover_bytes:
        edits["image"] = cover_bytes
    if wants_rename:
        edits["name"] = p.name
    if rescheduled:
        edits["end_time"] = p.end
        # 已經開始的活動不可改起點。p.start 是 clamp 過的 max(now+5min, logical_start)，
        # 送出去會把進行中的活動推到「5 分鐘後開始」；而且 discord.py 把 start/end 併進同一個
        # PATCH，Discord 一旦因此回 400，連官方延長的 end_time 也一起失效。
        if p.logical_start > datetime.now(timezone.utc):
            edits["start_time"] = p.logical_start
        else:
            logger.info("[event] 活動已開始，改期只同步結束時間｜%s｜新結束=%s", p.name, e8)
    if not edits:
        return

    try:
        await event.edit(**edits)
    except discord.Forbidden:
        logger.error("[event] ❌ bot 缺少『管理活動』權限，無法升級活動（%s）", p.name)
        return
    except discord.HTTPException as e:
        logger.warning("[event] 升級活動失敗（Discord 拒絕）：%s | %s", p.name, e)
        return

    tags = [name for flag, name in (
        ("description", "描述"), ("image", "封面"), ("name", "名稱"),
        ("end_time", "時間"),
    ) if flag in edits]

    try:
        await db.update_created_event(
            existing["event_fingerprint"],
            new_fingerprint=(p.fingerprint if rescheduled else None),
            source=p.source, source_id=p.source_id,
            title=(p.name if wants_rename else None),
            start_utc8=(s8 if rescheduled else None),
            end_utc8=(e8 if rescheduled else None),
            core_name=p.core_name,
            has_image=(True if cover_bytes else None),
            body=(body_for_desc if "description" in edits else None),
        )
    except Exception as e:
        logger.error("[event] ⚠️ 活動已在 Discord 升級但 DB 寫回失敗｜event_id=%s｜%s",
                     existing.get("discord_event_id"), e)
        return

    logger.info("[event] ♻️ 已升級既有活動：%s (id=%s)｜更新了 %s｜片段 %s→%s 字｜新來源=%s:%s",
                p.name, event.id, "＋".join(tags) or "（無）",
                len(existing_body), len(body_for_desc), p.source, p.source_id)


_fp_migration_done = False


def _compact_stamp(stamp: Optional[str]) -> str:
    """'2026-08-22 10:00' → '202608221000'（對齊 event_fingerprint 的時間格式）。"""
    return re.sub(r'\D', '', stamp or '')


async def _migrate_fingerprints_once(db) -> None:
    """一次性：用現行 normalize_title 重算既有列的指紋，並回填 core_name。

    為什麼非做不可：normalize_title 一改，既有指紋全部失配 → 去重表等同失效 →
    所有還在跑的活動會被**重新建立一次**（created_events 是持久化的）。
    重算基準用列裡存的 title：現行 code 的「活動顯示名」與「指紋基準」已經一致
    （全庫 217 個活動實測 0 筆不一致），所以從 title 重算會得到正確的新指紋。
    冪等：跑過一次之後不會再有列變動；只在程序生命週期內做一次。
    """
    global _fp_migration_done
    if _fp_migration_done:
        return
    try:
        rows = await db.list_created_events()
    except Exception as e:
        # 刻意**不**標記完成：沒遷移就拿新指紋去比對舊列 = 舊活動整批重建。
        # 寧可下一篇公告進來時再試一次。
        logger.warning("[event] 指紋遷移讀取失敗（下次再試；本次跳過去重升級）：%s", e)
        raise

    taken = {r["event_fingerprint"] for r in rows}
    changed = collided = failed = 0
    for row in rows:
        core = normalize_title(row.get("title") or "")
        new_fp = f"{core}|{_compact_stamp(row.get('start_utc8'))}|{_compact_stamp(row.get('end_utc8'))}"
        old_fp = row["event_fingerprint"]
        if new_fp == old_fp:
            if (row.get("core_name") or "") != core:
                try:
                    await db.update_created_event(old_fp, core_name=core)
                except Exception as e:
                    failed += 1
                    logger.warning("[event] 指紋遷移回填 core_name 失敗：%s | %s", old_fp, e)
            continue
        if new_fp in taken:
            # 兩列其實是同一個活動（本次 normalize_title 修正後才看得出來）。
            # 指紋不動（PRIMARY KEY 會撞），但 core_name 照樣回填並標成「分身」：
            # 留空 core_name 會讓這一列對兩條比對路徑同時隱形，一旦正本那列出事，
            # 它完全擋不住重複，會再建第三個活動。標成分身後 find_overlapping_event
            # 仍撈得到它，只是排序永遠排在正本後面。自動刪 Discord 活動是破壞性動作，不做。
            collided += 1
            try:
                await db.update_created_event(old_fp, core_name=core, superseded_by=new_fp)
            except Exception as e:
                failed += 1
                logger.warning("[event] 指紋遷移標記分身失敗：%s | %s", old_fp, e)
            logger.error("[event] ⚠️ 指紋遷移發現重複活動：《%s》(event_id=%s) 與既有 fp=%s 相撞。"
                         "本列維持舊指紋不動；Discord 上有兩個同一活動，請手動刪掉其中一個。",
                         row.get("title"), row.get("discord_event_id"), new_fp)
            continue
        try:
            await db.update_created_event(old_fp, new_fingerprint=new_fp, core_name=core)
        except Exception as e:
            failed += 1
            logger.warning("[event] 指紋遷移單列失敗（略過該列）：%s | %s", old_fp, e)
            continue
        taken.discard(old_fp)
        taken.add(new_fp)
        changed += 1

    # 有任何一列沒寫成功就不標記完成：那種列的舊指紋用現行 normalize_title 已經算不出來，
    # 留著等於一筆「知道活動存在、卻完全沒有去重能力」的列。下一篇公告進來時再試一次。
    if failed == 0:
        _fp_migration_done = True
    logger.info("[event] 指紋遷移%s：共 %s 列，更新 %s 列，重複活動 %s 組，失敗 %s 列",
                "完成" if failed == 0 else "未完成（下次重試）",
                len(rows), changed, collided, failed)
    if failed:
        raise RuntimeError(f"指紋遷移有 {failed} 列未寫入")


# ── 各來源薄 adapter（欄位對應住「活動功能自己家」；monitor 呼叫端變一行、best-effort 不拋） ──

async def schedule_from_article(bot, article: dict, channel_id: int,
                                message_url: Optional[str] = None,
                                force: bool = False) -> None:
    """從官方文章 dict 觸發活動偵測。欄位對應集中於此，article_monitor 只需一行呼叫。"""
    try:
        # 官方原文網址的唯一來源在 article_monitor（article 領域的家），這裡不另寫一份
        from services.article_monitor import official_article_url

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
            url=official_article_url(article.get("article_id")),
            channel_id=channel_id, is_html=True,
            image_url=image_url, message_url=message_url, force=force,
        )
    except Exception as e:
        logger.warning("[event] article 活動偵測失敗（已吞）: %s", e)


async def schedule_from_fb(bot, fb_post: dict, channel_id: int,
                           message_url: Optional[str] = None,
                           force: bool = False) -> None:
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
            message_url=message_url, force=force,
        )
    except Exception as e:
        logger.warning("[event] fb 活動偵測失敗（已吞）: %s", e)
