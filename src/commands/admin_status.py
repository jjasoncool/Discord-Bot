"""機器人狀態面板：九項紅黃綠、每項旁邊一顆重測、全部重測、重新整理、看詳細、補跑今天的 04:00 維護；私訊與伺服器裡同一份。

架構定位：介面層（commands）的 view、各項狀況的狀態與重測函式，沒有自己的 cog。
  上層：`commands.owner_alert_commands`（`cog_load` 呼叫 `register_kinds`、登記這裡的 DynamicItem；按鈕的重測交回它的
  `handle_retest`）、`commands.admin_console`（主控台的「機器人狀態」）。
  下層：`utils.owner_alerts`（登記表、燈號）、各功能自己暴露的現況：`services.notify_server.last_notify_at`、
  `llm.retrievers.web.searxng.blocked_engines`、`llm.client.gpu_gate.cross_process_status`、
  `llm.storage.raw_message_store.flush_health`、`llm.storage.store_chat.buffer_status`、Telegram worker 的 `status()`
  與 repository 的 `latest_message_time()`、`llm.retrievers.intel.prepare_intel_session`、`settings.channel_registry`、
  `services.events.event_scheduler.schedule_flags`、`llm.persona.daily_maintenance.run_once`。

介面：
- `register_kinds(bot)`：登記除了模型後端以外的八項（模型後端由 owner_alert_commands 自己登記）。
- `render_status(*, expanded, headline="") -> LayoutView`：面板本體（主控台的「機器人狀態」把它畫在主控台那一則上）；
  `render_details(*, expanded, page)`：每一項的完整說明、還沒解除的警報、最近的探測，分頁；`render_maintenance(*, expanded)`：補跑維護的確認畫面。
- `PanelRetestButton`／`StatusButton`：DynamicItem，custom_id `owner:panel:<expanded>:<kind>:<key>`、`owner:status:<action>[1][:<page>]`
  （動作後面的 1＝面板展開中、頁碼給看詳細）；
  `DYNAMIC_ITEMS` 給 cog_load 登記。`STATUS_REFRESH_ID` 是舊面板上「重新整理」的 custom_id，照樣能按。
- `retest_all(interaction)`、`run_maintenance(interaction, guild, *, expanded)`：底下那排按鈕做的事；都改面板這一則。

規則：
- 狀態函式只讀現有的計數與設定，不打網路、不拿 GPU：面板要能秒開。會打網路的（爬蟲 health、網路搜尋、情報搜尋）只在重測時做，
  結果記在 `_LAST_PROBE`，狀態列顯示「上次探測幾點、結果」。
- 只有群主能按（`_ACCESS`）；要放寬只改那一行。面板上一次操作走 `_guarded`（`guarded_screen`）：做壞了換成只剩「重新整理」「回主控台」的畫面並標錯誤。
- 每個操作都改面板這一則（`utils.discord_content.edit_screen`：舊 embed 版面板上的按鈕按下去也換得成新版版面）：看詳細、補跑維護的確認
  都是面板上的子畫面，有「回上一層」；面板上有「回主控台」（`commands.admin_console.back_button`）。
  元件上限 40、文字總長 4000：每列三個元件，放得下的列數算出來（`_ROW_BUDGET`），多的收成一行文字請按「看詳細」；
  每列文字照剩下的預算截，完整內容在「看詳細」。

例外與決策：
- 紅（alert）＝要人處理，黃（watch）＝自己會好、或剛好過要看一下，綠（ok）＝正常；正常的收成一行、按「展開」才逐項列。
- 「跑今天的 04:00 維護」白天按只會做字典、衰減、發布三步：persona agent 那步有 07:00 的截止，過了就不跑；要先確認才跑，
  因為它會佔模型一段時間。
- Discord 權限只看權限位元，不真的送訊息、不建活動、不跑點名（點名那條會再私訊、再踢人）。
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Awaitable, Callable, Optional

import aiohttp
import discord

from llm.client import gpu_gate
from llm.retrievers.intel import prepare_intel_session
from llm.retrievers.web import search_web, searxng
from llm.storage import raw_message_store, store_chat
from services import notify_server
from services.events import event_scheduler
from services.relay.base_monitor import SCRAPER_API_URL
from settings import channel_registry
from sys_settings import switches
from sys_settings.llm_settings import AskAIWebSettings, LLMServiceSettings
from sys_settings.time_settings import APP_TZ
from utils import owner_alerts
from utils.background_tasks import spawn
from utils.discord_members import bot_owner_id, home_guild, require_access
from utils.owner_alerts import RetestResult, Status
from utils.discord_content import edit_screen, guarded_screen
from utils.utils import ChannelConfig, safe_send_interaction_message
from commands.admin_console import back_button, screen_box, screen_view

logger = logging.getLogger(__name__)

PANEL_RETEST_TEMPLATE = r"owner:panel:(?P<expanded>[01]):(?P<kind>[a-z0-9_]+):(?P<key>[A-Za-z0-9._*\-]+)"
#: 底下那排按鈕：動作後面接 1＝面板展開中（看詳細、確認維護回來時才知道要畫哪一版）；看詳細再接頁碼
STATUS_TEMPLATE = r"owner:status:(?P<action>refresh|expand|collapse|all|details|maintenance|go)(?P<expanded>1?)(?::(?P<page>\d+))?"
STATUS_REFRESH_ID = "owner:status:refresh"
#: 誰能按；要放寬到管理員只改這裡（私訊裡只放得了群主）
_ACCESS = dict(owner_only=True, allow_dm=True)
_NO_COG = "狀態功能目前沒有在運作，請看 log。"
#: 面板上各項的順序（照草稿）；模型後端那項由 owner_alert_commands 登記
KIND_ORDER = ("discord_perm", "scraper", "web_search", "lemonade", "gpu_lock", "pgvector", "telegram_scraper", "intel", "settings")
_ICON = {"alert": "🔴", "watch": "🟡", "ok": "🟢"}
_LEVEL_WORD = {"alert": "要處理", "watch": "觀察", "ok": "正常"}
#: 爬蟲各來源多久沒推送算有事（秒）：公告每 15 分鐘推一次（0 筆也推），其他每小時
_SCRAPER_QUIET = {"article": 45 * 60}
_SCRAPER_QUIET_DEFAULT = 3 * 3600
#: telegram-scraper 多久沒寫入新列先當觀察（情報頻道平常一天好幾則；真的掛了 worker 那邊也會紅）
_TELEGRAM_QUIET_S = 12 * 3600
#: 探測（會打網路）的結果多久內還算新；密鑰不符被拒也看這段時間
_PROBE_FRESH_S = 3600
#: 整則文字的預算（Discord 上限 4000，留餘裕給「…（看詳細）」這類尾巴）
_TEXT_BUDGET = 3700
#: 看詳細一頁放多少字（一則新版版面的文字總長上限 4000）
_DETAILS_PAGE_CHARS = 3400
#: 每列至少留幾個字，再少就看不懂
_ROW_MIN_CHARS = 80
#: 本行程啟動的時刻：啟動後還沒收過推送的來源，從這裡起算安靜多久
_STARTED = time.time()
#: 重測時才打網路的項目，最近一次探測：kind → (time.time(), Status)
_LAST_PROBE: dict[str, tuple[float, Status]] = {}
#: 每個頻道型別要有的權限：must 缺了就紅，nice 缺了黃
_PERMS_TEXT = {"must": (("view_channel", "看頻道"), ("send_messages", "發送訊息"), ("embed_links", "嵌入連結")),
               "nice": (("attach_files", "附加檔案"),)}
_PERMS_FORUM = {"must": (("view_channel", "看頻道"), ("send_messages", "發送訊息"), ("send_messages_in_threads", "在討論串發送訊息"),
                         ("embed_links", "嵌入連結")), "nice": (("attach_files", "附加檔案"),)}
_PERMS_VOICE = {"must": (("view_channel", "看頻道"), ("connect", "連接"), ("speak", "說話")), "nice": ()}
_PERMS_BY_TYPE = {discord.ChannelType.forum: _PERMS_FORUM, discord.ChannelType.voice: _PERMS_VOICE}


def _stamp(at: Optional[float] = None) -> str:
    return datetime.fromtimestamp(at if at is not None else time.time(), APP_TZ).strftime("%H:%M")


def _ago(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 90:
        return f"{seconds} 秒前"
    if seconds < 5400:
        return f"{seconds // 60} 分鐘前"
    return f"{seconds / 3600:.1f} 小時前"


def _only_guild(bot) -> Optional[discord.Guild]:
    guilds = list(getattr(bot, "guilds", None) or [])
    return guilds[0] if len(guilds) == 1 else None


def probe_note(kind: str) -> str:
    """那一項最近一次探測的結果（沒探測過回提示）。"""
    entry = _LAST_PROBE.get(kind)
    if entry is None:
        return "還沒探測過，按重測才會真的連一次"
    at, status = entry
    return f"{_stamp(at)} 探測：{status.text}"


def _remember(kind: str, status: Status) -> Status:
    _LAST_PROBE[kind] = (time.time(), status)
    return status


def _probe_level(kind: str) -> Optional[str]:
    """最近一次探測若失敗且還新，狀態列也要紅。"""
    entry = _LAST_PROBE.get(kind)
    if entry is None or time.time() - entry[0] > _PROBE_FRESH_S:
        return None
    return entry[1].level


# ---------- ① Discord 權限 ----------

async def discord_perm_status(bot) -> Status:
    guild = _only_guild(bot)
    if guild is None:
        return Status("watch", "bot 還沒連上伺服器，或不只在一個伺服器：略過權限檢查")
    me = guild.me
    problems: list[str] = []
    watch: list[str] = []
    checked = 0
    for setting in channel_registry.display_order():
        if not setting.config_key:
            continue
        channel_id = await channel_registry.bound_channel_id(setting)
        if not channel_id:
            continue
        checked += 1
        _check_channel(guild, me, channel_id, setting.label, problems, watch)
    for source, ids in channel_registry.telegram_routes().items():
        for channel_id in ids:
            if channel_id:
                checked += 1
                _check_channel(guild, me, channel_id, f"Telegram {source}", problems, watch, thread_ok=True)
    gp = me.guild_permissions
    enabled, dry_run = event_scheduler.schedule_flags(ChannelConfig.load_config(caller="admin_status"))
    if enabled and not gp.manage_events:
        (watch if dry_run else problems).append("缺「管理活動」，公告裡的活動建不起來" + ("（排程還是 dry_run，先觀察）" if dry_run else ""))
    rollcall = bot.get_cog("RollCallCommands") if hasattr(bot, "get_cog") else None
    runtime = getattr(getattr(rollcall, "service", None), "runtime", None)
    if runtime is not None and getattr(runtime, "enabled", False) and not gp.kick_members:
        problems.append("點名開著但缺「踢出成員」，到期的人踢不掉")
    if problems:
        return Status("alert", "；".join(problems)[:700])
    if watch:
        return Status("watch", "；".join(watch)[:700])
    return Status("ok", f"已綁的 {checked} 個頻道都能發文；管理活動、踢出成員也都有")


def _check_channel(guild, me, channel_id: int, label: str, problems: list[str], watch: list[str], *, thread_ok: bool = False) -> None:
    channel = guild.get_channel(channel_id)
    if channel is None:
        problems.append(f"{label}：找不到頻道 <#{channel_id}>（被刪或 bot 看不到）")
        return
    perms = channel.permissions_for(me)
    need = _PERMS_BY_TYPE.get(getattr(channel, "type", None), _PERMS_TEXT)
    missing = [name for attr, name in need["must"] if not getattr(perms, attr, False)]
    if missing:
        problems.append(f"{label}（<#{channel_id}>）缺「{'、'.join(missing)}」")
    soft = [name for attr, name in need["nice"] if not getattr(perms, attr, False)]
    if thread_ok and not getattr(perms, "create_public_threads", False):
        soft.append("建立公開討論串（隔離區用）")
    if soft:
        watch.append(f"{label}（<#{channel_id}>）缺「{'、'.join(soft)}」")


async def discord_perm_retest(bot, key: str) -> RetestResult:
    status = await discord_perm_status(bot)
    return RetestResult(status.level != "alert", status.text)


# ---------- ② scraper ----------

def scraper_status(bot) -> Status:
    if getattr(bot, "_notify_server", None) is None:
        return Status("alert", "通知伺服器沒起來（port 5000 被占？），爬蟲的推送進不來，重啟 bot 才會好")
    now = time.time()
    last = notify_server.last_notify_at()
    problems: list[str] = []
    parts: list[str] = []
    for source, quiet in (("article", _SCRAPER_QUIET["article"]), ("bahamut", _SCRAPER_QUIET_DEFAULT),
                          ("fb", _SCRAPER_QUIET_DEFAULT), ("it_article", _SCRAPER_QUIET_DEFAULT)):
        at = last.get(source)
        silent = now - (at if at is not None else _STARTED)
        parts.append(f"{source} {_ago(now - at) if at is not None else '啟動後還沒推送'}")
        if silent > quiet:
            problems.append(f"{source} {'超過 ' + _ago(silent)[:-1] + '沒推送' if at is not None else '啟動後 ' + _ago(silent)[:-1] + '都沒推送'}")
    level = "ok"
    if problems and any(p.startswith("article") for p in problems):
        level = "alert"
    elif problems:
        level = "watch"
    rejected = notify_server.rejected_count()
    rejected_at = notify_server.last_rejected_at()
    if rejected and now - rejected_at < _PROBE_FRESH_S:
        level = "alert" if level == "alert" else "watch"
        problems.append(f"密鑰不符被拒（最後一次 {_stamp(rejected_at)}，啟動以來 {rejected} 次；兩邊 NOTIFY_SHARED_SECRET 對不上）")
    text = ("；".join(problems) + "。" if problems else "") + "最後推送：" + "、".join(parts) + "。" + probe_note("scraper")
    probe = _probe_level("scraper")
    if probe == "alert":
        level = "alert"
    return Status(level, text[:700])


async def scraper_retest(bot, key: str) -> RetestResult:
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as session:
            async with session.get(f"{SCRAPER_API_URL}/health") as response:
                ok = response.status == 200
                status = _remember("scraper", Status("ok" if ok else "alert",
                                                     f"/health 回 {response.status}" if not ok else "容器活著（/health 200）"))
    except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as exc:
        status = _remember("scraper", Status("alert", f"連不上爬蟲容器：{type(exc).__name__}"))
    return RetestResult(status.level == "ok", status.text)


# ---------- ③ 網路搜尋 ----------

def web_search_status(bot) -> Status:
    mode = switches.current().askai_web_search_mode
    if mode == "off":
        return Status("ok", "開關 off：/askai 不查網路")
    blocked = searxng.blocked_engines()
    probe = _probe_level("web_search")
    if probe == "alert":
        return Status("alert", probe_note("web_search"))
    if blocked:
        detail = "、".join(f"{name} 暫避到 {_stamp(time.time() + left)}" for name, left in sorted(blocked.items()))
        return Status("watch", f"{detail}（到點自動恢復）。{probe_note('web_search')}")
    return Status("ok", f"沒有引擎在暫避（模式 {mode}）。{probe_note('web_search')}")


async def web_search_retest(bot, key: str) -> RetestResult:
    cleared = searxng.reset_blocked()
    try:
        outcome = await search_web(f"鳴潮 {int(time.time())}", settings=AskAIWebSettings())
    except Exception as exc:  # 邊界：面板的一次探測，任何錯都要回報成「壞」而不是炸掉面板
        status = _remember("web_search", Status("alert", f"查詢出錯：{type(exc).__name__}: {exc}"[:200]))
        return RetestResult(False, status.text)
    error = (outcome.meta or {}).get("error") if isinstance(getattr(outcome, "meta", None), dict) else None
    if error:
        status = _remember("web_search", Status("alert", f"SearXNG 回錯誤：{error}"))
    else:
        unresponsive = (outcome.meta or {}).get("unresponsive_engines") or []
        note = f"查到 {len(outcome.results)} 筆" + (f"，{len(unresponsive)} 個引擎沒回應" if unresponsive else "")
        if cleared:
            note += f"；已清掉 {'、'.join(cleared)} 的暫避"
        status = _remember("web_search", Status("ok", note))
    return RetestResult(status.level == "ok", status.text)


# ---------- ⑤ 顯示卡閘門 ----------

def gpu_lock_status(bot) -> Status:
    state = gpu_gate.cross_process_status()
    if state["skip_remaining_s"] > 0:
        return Status("alert", f"別的行程佔著鎖檔超過 15 分鐘，bot 現在不等、直接打模型（還有 {int(state['skip_remaining_s'] // 60)} 分鐘）；"
                               "看看 search-mcp 的批次或手動腳本有沒有卡住")
    if state["holder"] == "imagegen":
        return Status("watch", "產圖佔著顯示卡（會拿幾十分鐘）")
    if state["other_process"]:
        return Status("watch", "別的行程（search-mcp 批次、手動腳本）正拿著鎖檔；它們做完就好")
    if state["locked_here"]:
        return Status("ok", f"bot 自己正在用（{state['holder']}），正常")
    return Status("ok", "沒有別的行程佔著")


async def gpu_lock_retest(bot, key: str) -> RetestResult:
    status = gpu_lock_status(bot)
    return RetestResult(status.level != "alert", status.text)


# ---------- ⑥ 資料庫 ----------

def pgvector_status(bot) -> Status:
    raw = raw_message_store.flush_health()
    chat = store_chat.buffer_status()
    problems: list[str] = []
    watch: list[str] = []
    if raw["consecutive_failures"] >= 3:
        problems.append(f"原始備份連續 {raw['consecutive_failures']} 輪寫不進去")
    elif raw["consecutive_failures"]:
        watch.append(f"原始備份上一輪寫入失敗（連續 {raw['consecutive_failures']} 次）")
    if raw["buffered"] >= raw_message_store.RAW_FLUSH_THRESHOLD:
        watch.append(f"原始備份積了 {raw['buffered']} 則還沒寫")
    if chat["paused_s"] > 0:
        watch.append(f"聊天寫入上一輪中止、放回 {chat['size']} 則等重試（{int(chat['paused_s'])} 秒後；多半是模型後端的事）")
    if chat["dropped"]:
        problems.append(f"聊天緩衝超過上限丟了 {chat['dropped']} 則")
    last_ok = f"原始備份最後寫入 {_ago(time.time() - raw['last_ok_at'])}" if raw["last_ok_at"] else "原始備份啟動後還沒寫過（沒新訊息就不會寫）"
    probe = _probe_level("pgvector")
    level = "alert" if problems or probe == "alert" else "watch" if watch else "ok"
    text = "；".join(problems + watch)
    text = (text + "。" if text else "") + last_ok + "。" + probe_note("pgvector")
    return Status(level, text[:700])


async def pgvector_retest(bot, key: str) -> RetestResult:
    def query() -> Optional[Any]:
        with LLMServiceSettings().pgvector_cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
            cur.execute("SELECT max(ingested_at) FROM discord_messages_raw")
            row = cur.fetchone()
            return row[0] if row else None

    try:
        latest = await asyncio.to_thread(query)
    except Exception as exc:  # 邊界：面板的一次探測，連不上要回報成「壞」而不是炸掉面板
        status = _remember("pgvector", Status("alert", f"連不上資料庫：{type(exc).__name__}: {exc}"[:200]))
        return RetestResult(False, status.text)
    stats = await raw_message_store.flush_raw_buffer()
    written = sum(int(v) for k, v in stats.items() if k != "failed")
    when = latest.astimezone(APP_TZ).strftime("%m-%d %H:%M") if isinstance(latest, datetime) else "（表是空的）"
    status = _remember("pgvector", Status("ok", f"連得上；原始備份最新一列 {when}" + (f"，剛寫入 {written} 筆" if written else "")))
    return RetestResult(True, status.text)


# ---------- ⑦ telegram-scraper ----------

def telegram_status(bot) -> Status:
    worker = getattr(bot, "telegram_relay_worker", None)
    if worker is None or not getattr(worker, "running", False):
        return Status("alert", "bot 端的 Telegram 轉發沒在跑（啟動時連不上資料庫或缺設定），按重測會再啟動一次")
    state = worker.status()
    problems: list[str] = []
    watch: list[str] = []
    if not state["listening"]:
        problems.append("LISTEN 連線斷著（5 秒內會自己重連，一直斷就是資料庫的事）")
    if state["queued"] > 100:
        watch.append(f"佇列積了 {state['queued']} 則")
    probe = _probe_level("telegram_scraper")
    if probe == "alert":
        problems.append("最近一次探測失敗")
    elif probe == "watch":
        watch.append("最近一次探測有狀況")
    level = "alert" if problems else "watch" if watch else "ok"
    text = "；".join(problems + watch)
    text = (text + "。" if text else "") + f"轉發 worker 在跑，佇列 {state['queued']} 則。" + probe_note("telegram_scraper")
    return Status(level, text[:700])


async def telegram_retest(bot, key: str) -> RetestResult:
    worker = getattr(bot, "telegram_relay_worker", None)
    if worker is None or not getattr(worker, "running", False):
        starter = getattr(bot, "start_telegram_relay", None)
        if starter is not None:
            await starter()     # bot 自己掛的啟動函式；不在這裡 import discord_bot（它是 __main__，再 import 會把整個模組重跑一遍）
        worker = getattr(bot, "telegram_relay_worker", None)
        if worker is None or not getattr(worker, "running", False):
            status = _remember("telegram_scraper", Status("alert", "再啟動一次還是起不來，請看 log"))
            return RetestResult(False, status.text)
    try:
        latest = await worker.repository.latest_message_time()
    except Exception as exc:  # 邊界：面板的一次探測
        status = _remember("telegram_scraper", Status("alert", f"查 telegram_messages 失敗：{type(exc).__name__}: {exc}"[:200]))
        return RetestResult(False, status.text)
    if latest is None:
        status = _remember("telegram_scraper", Status("watch", "telegram_messages 是空的"))
    else:
        age = time.time() - latest.timestamp()
        when = latest.astimezone(APP_TZ).strftime("%m-%d %H:%M")
        if age > _TELEGRAM_QUIET_S:
            status = _remember("telegram_scraper", Status("watch", f"爬蟲最後寫入 {when}（{_ago(age)}）：超過 {_TELEGRAM_QUIET_S // 3600} 小時沒新訊息，看看 telegram-scraper 容器與 session"))
        else:
            status = _remember("telegram_scraper", Status("ok", f"爬蟲最後寫入 {when}（{_ago(age)}）"))
    return RetestResult(status.level != "alert", status.text, untested=False)


# ---------- ⑧ 情報搜尋 ----------

def intel_status(bot) -> Status:
    current = switches.current()
    if current.askai_intel_search_mode == "off" and current.ambient_search_mode == "off":
        return Status("ok", "開關都 off：/askai 與插話都不查情報")
    probe = _probe_level("intel")
    if probe == "alert":
        return Status("alert", probe_note("intel"))
    return Status("ok", probe_note("intel"))


async def intel_retest(bot, key: str) -> RetestResult:
    try:
        session = await prepare_intel_session(question="ping")
    except Exception as exc:  # 邊界：面板的一次探測
        session = None
        detail = f"{type(exc).__name__}: {exc}"[:160]
    else:
        detail = "連不上 search-mcp（服務沒開或網路斷）"
    if session is None:
        status = _remember("intel", Status("alert", detail))
    else:
        tools = getattr(session, "tool_names", None) or getattr(session, "tools", None)
        count = len(tools) if hasattr(tools, "__len__") else "?"
        status = _remember("intel", Status("ok", f"search-mcp 連得上，{count} 個工具"))
    return RetestResult(status.level == "ok", status.text)


# ---------- ⑨ 設定 ----------

async def settings_status(bot) -> Status:
    problems: list[str] = []
    watch: list[str] = []
    notes: list[str] = []
    try:
        owner = bot_owner_id()
    except ValueError:
        owner = 0
    if not owner:
        problems.append("OWNER_ID 沒設：通知送不出去、主控台沒人能用")
    try:
        config = ChannelConfig.load_config(caller="admin_status")
    except Exception as exc:  # 邊界：設定檔壞掉正是這一項要報的事
        problems.append(f"config.json 讀不到：{type(exc).__name__}")
        config = {}
    failed = list(getattr(bot, "failed_extensions", []) or [])
    if failed:
        problems.append(f"指令模組載不起來：{'、'.join(m.rsplit('.', 1)[-1] for m in failed)}")
    server = getattr(bot, "_notify_server", None)
    if server is None:
        problems.append("通知伺服器沒起來")
    elif not getattr(server, "model_endpoint_enabled", False):
        notes.append("模型端點關（沒設 HERMES_API_KEY）")
    enabled, dry_run = event_scheduler.schedule_flags(config)
    if not enabled:
        watch.append("活動排程關著（event_schedule_enabled=false）")
    elif dry_run:
        watch.append("活動排程 dry_run：只記 log、不建活動（首批保險，刻意關著）")
    else:
        notes.append("活動排程會建活動")
    ambient = channel_registry.get_setting("AI 插話頻道")
    if ambient is not None and not await channel_registry.bound_channel_id(ambient):
        watch.append("AI 插話頻道沒綁：插話整個靜默")
    unbound = []
    for setting in channel_registry.display_order():
        if setting.config_key and not await channel_registry.bound_channel_id(setting):
            unbound.append(setting.label)
    if unbound:
        notes.append(f"沒綁的頻道：{'、'.join(unbound)}")
    current = switches.current()
    notes.append(f"開關：telegram_filter {current.telegram_filter_mode}、ambient_search {current.ambient_search_mode}、"
                 f"intel {current.askai_intel_search_mode}、web {current.askai_web_search_mode}")
    level = "alert" if problems else "watch" if watch else "ok"
    text = "；".join(problems + watch + notes)
    return Status(level, text[:700] or "OWNER_ID 已設、設定檔讀得到")


async def settings_retest(bot, key: str) -> RetestResult:
    status = await settings_status(bot)
    return RetestResult(status.level != "alert", status.text)


# ---------- 登記 ----------

def register_kinds(bot) -> None:
    """登記模型後端以外的八項；狀態函式與重測都綁在這個 bot 上。"""
    def bind(fn: Callable[..., Any]):
        def status_fn():
            return fn(bot)
        return status_fn

    def bind_retest(fn: Callable[[Any, str], Awaitable[RetestResult]]):
        async def retest_fn(key: str) -> RetestResult:
            return await fn(bot, key)
        return retest_fn

    owner_alerts.register("discord_perm", title="Discord 權限", status=bind(discord_perm_status), retest=bind_retest(discord_perm_retest))
    owner_alerts.register("scraper", title="scraper（爬蟲容器）", status=bind(scraper_status), retest=bind_retest(scraper_retest))
    owner_alerts.register("web_search", title="網路搜尋（SearXNG）", status=bind(web_search_status), retest=bind_retest(web_search_retest))
    owner_alerts.register("gpu_lock", title="顯示卡閘門", status=bind(gpu_lock_status), retest=bind_retest(gpu_lock_retest))
    owner_alerts.register("pgvector", title="資料庫（pgvector）", status=bind(pgvector_status), retest=bind_retest(pgvector_retest))
    owner_alerts.register("telegram_scraper", title="telegram-scraper", status=bind(telegram_status), retest=bind_retest(telegram_retest))
    owner_alerts.register("intel", title="情報搜尋（search-mcp）", status=bind(intel_status), retest=bind_retest(intel_retest))
    owner_alerts.register("settings", title="設定", status=bind(settings_status), retest=bind_retest(settings_retest))


# ---------- 面板 ----------

def _ordered_kinds() -> list[owner_alerts.KindSpec]:
    specs = {spec.kind: spec for spec in owner_alerts.kinds()}
    ordered = [specs.pop(kind) for kind in KIND_ORDER if kind in specs]
    return ordered + list(specs.values())


async def collect() -> list[tuple[owner_alerts.KindSpec, Status, str]]:
    """每一項的 (登記, 燈號, 重測用的 key)：有警報的 key 用最早那把，沒有就 `*`。"""
    alerts = owner_alerts.active()
    rows = []
    for spec in _ordered_kinds():
        status = await owner_alerts.status_of(spec.kind)
        mine = [a for a in alerts if a.kind == spec.kind]
        rows.append((spec, status, mine[0].key if mine else "*"))
    return rows


def _retest_label(level: str) -> str:
    return {"alert": "重測", "watch": "現在試", "ok": "再測"}[level]


async def render_status(*, expanded: bool = False, headline: str = "") -> discord.ui.LayoutView:
    """面板：標題與統計、每一項一段加右邊一顆重測（正常的收成一行，可展開）、底部說明、一排按鈕。"""
    rows = await collect()
    counts = {level: sum(1 for _, s, _ in rows if s.level == level) for level in ("alert", "watch", "ok")}
    worst = "alert" if counts["alert"] else "watch" if counts["watch"] else "ok"
    colour = {"alert": discord.Color.red(), "watch": discord.Color.gold(), "ok": discord.Color.green()}[worst]
    flag = "1" if expanded else "0"

    box = discord.ui.Container(accent_colour=colour)
    summary = f"{counts['alert']} 項要你處理、{counts['watch']} 項觀察中、{counts['ok']} 項正常"
    title = f"## 機器人狀態\n-# {_stamp()} 更新 · {summary}" + (f"\n{headline[:500]}" if headline else "")
    footer = "-# 紅＝要你處理、黃＝觀察中、綠＝正常。按右邊的按鈕會重測那一項，結果直接改在這則訊息上。"
    box.add_item(discord.ui.TextDisplay(title))
    box.add_item(discord.ui.Separator())
    shown = [(spec, status, key) for spec, status, key in rows if expanded or status.level != "ok"]
    hidden = [(spec, status, key) for spec, status, key in rows if not expanded and status.level == "ok"]
    # 元件預算：容器 1＋標題 1＋分隔 2＋頁尾 1＋兩排按鈕 2＋最多 6 顆＝13，收合那列 3，每一項（Section＋文字＋按鈕）3
    fixed = 13 + (3 if hidden else 0)
    room = max(1, (40 - fixed) // 3)
    if len(shown) > room:
        rest, shown = shown[room - 1:], shown[:room - 1]
    else:
        rest = []
    # 文字預算：整則 4000，扣掉標題、頁尾、收合那行，剩下的平分給每一列（完整文字在「看詳細」）
    collapsed_line = f"🟢 正常 {len(hidden)} 項：{' · '.join(spec.title for spec, _, _ in hidden)}" if hidden else ""
    rest_line = ("-# 還有 " + "、".join(f"{_ICON[s.level]}{spec.title}" for spec, s, _ in rest) + "：放不下，按「看詳細」") if rest else ""
    per_row = max(_ROW_MIN_CHARS, (_TEXT_BUDGET - len(title) - len(footer) - len(collapsed_line) - len(rest_line)) // max(1, len(shown)))
    for spec, status, key in shown:
        head = f"{_ICON[status.level]} **{spec.title}**\n-# {_LEVEL_WORD[status.level]}："
        body = status.text or "—"
        if len(head) + len(body) > per_row:
            body = body[:max(10, per_row - len(head) - 8)] + "…（看詳細）"
        text = head + body
        if spec.retest is not None:
            box.add_item(discord.ui.Section(discord.ui.TextDisplay(text),
                                            accessory=PanelRetestButton(spec.kind, key, expanded, label=_retest_label(status.level))))
        else:
            box.add_item(discord.ui.TextDisplay(text))
    if rest_line:
        box.add_item(discord.ui.TextDisplay(rest_line))
    if hidden:
        box.add_item(discord.ui.Section(discord.ui.TextDisplay(collapsed_line), accessory=StatusButton("expand", label="展開")))
    if not rows:
        box.add_item(discord.ui.TextDisplay("（還沒有登記任何狀況）"))
    box.add_item(discord.ui.Separator())
    box.add_item(discord.ui.TextDisplay(footer))

    # 「展開」只在收合那一列右邊（同一則訊息的 custom_id 不能重複，Discord 會整則退件）；展開中底排才多一顆「收合」
    top_row: list[discord.ui.Item] = [
        StatusButton("all", expanded, label="全部重測", style=discord.ButtonStyle.success),
        StatusButton("refresh", expanded, label="重新整理"),
    ]
    if expanded:
        top_row.append(StatusButton("collapse", False, label="收合"))
    return screen_view(box, top_row, [
        StatusButton("details", expanded, label="看詳細"),
        StatusButton("maintenance", expanded, label="跑今天的 04:00 維護"),
        back_button(),
    ])


def _details_pages(rows: list[tuple[owner_alerts.KindSpec, Status, str]]) -> list[str]:
    """看詳細的內容切成幾頁：每一項的完整說明、還沒解除的警報、最近的探測；一行不切、滿了就換頁。"""
    lines = []
    for spec, status, _ in rows:
        lines.append(f"{_ICON[status.level]} **{spec.title}**：{status.text or '—'}")
    alerts = owner_alerts.active()
    if alerts:
        lines += ["", "**還沒解除的警報**"]
        lines += [f"- {owner_alerts.title(a.kind)}／{a.key}：{a.text[:300]}（{_stamp(a.at)} 起）" for a in alerts]
    if _LAST_PROBE:
        lines += ["", "**最近的探測**"]
        lines += [f"- {owner_alerts.title(kind)}：{_stamp(at)} {status.text[:200]}" for kind, (at, status) in _LAST_PROBE.items()]
    pages: list[list[str]] = [[]]
    for line in lines:
        line = line[:_DETAILS_PAGE_CHARS]
        if pages[-1] and sum(len(x) + 1 for x in pages[-1]) + len(line) > _DETAILS_PAGE_CHARS:
            pages.append([])
        pages[-1].append(line)
    return ["\n".join(page) or "（還沒有登記任何狀況）" for page in pages]


async def render_details(*, expanded: bool = False, page: int = 0) -> discord.ui.LayoutView:
    """看詳細：一頁一頁翻（超過一頁才有上一頁／下一頁，頁碼夾回合法範圍），回上一層回到面板。"""
    pages = _details_pages(await collect())
    page = min(max(0, int(page)), len(pages) - 1)
    box = discord.ui.Container(accent_colour=discord.Color.blurple())
    box.add_item(discord.ui.TextDisplay(f"## 機器人狀態詳細\n-# {_stamp()} · 第 {page + 1}／{len(pages)} 頁"))
    box.add_item(discord.ui.Separator())
    box.add_item(discord.ui.TextDisplay(pages[page]))
    buttons: list[discord.ui.Item] = []
    if len(pages) > 1:
        buttons.append(StatusButton("details", expanded, max(page - 1, 0), label="◀ 上一頁", disabled=page <= 0))
        buttons.append(StatusButton("details", expanded, min(page + 1, len(pages) - 1), label="下一頁 ▶",
                                    disabled=page >= len(pages) - 1))
    buttons.append(StatusButton("refresh", expanded, label="↩️ 回上一層"))
    return screen_view(box, buttons)


def render_maintenance(*, expanded: bool = False) -> discord.ui.LayoutView:
    """「跑今天的 04:00 維護」要先確認：它會佔模型一段時間。"""
    now = datetime.now(APP_TZ)
    note = ("現在過了 07:00：persona agent 那步會跳過，只做表情字典、招牌梗衰減、發布精簡版（幾秒到一分鐘）。"
            if now.hour >= 7 else "現在在 07:00 前：四步都會跑，persona agent 會佔模型到 07:00 為止。")
    box = discord.ui.Container(accent_colour=discord.Color.gold())
    box.add_item(discord.ui.TextDisplay(f"## 補跑今天的 04:00 維護\n{note}\n\n要現在跑嗎？做完會私訊你一行。"))
    return screen_view(box, [
        StatusButton("go", expanded, label="確定跑", style=discord.ButtonStyle.danger),
        StatusButton("refresh", expanded, label="取消"),
    ])


async def run_maintenance(interaction: discord.Interaction, guild: discord.Guild, *, expanded: bool = False) -> None:
    """確認後開始跑（背景），面板最上面寫一行；已經有一輪在跑就只講這件事。"""
    from llm.persona import daily_maintenance
    if daily_maintenance.is_running():
        await edit_screen(interaction, view=await render_status(expanded=expanded, headline="⚠️ 已經有一輪維護在跑，等它做完。"))
        return

    async def run_and_tell() -> None:
        ran = await daily_maintenance.run_once(guild)
        owner_alerts.inform("maintenance", "manual",
                            f"🧹 {_stamp()} 手動維護{'做完了' if ran else '沒跑（已有一輪在跑）'}；過了 07:00 的話 persona agent 那步不會跑，其餘三步照做。")

    spawn(run_and_tell(), name="手動每日維護")
    await edit_screen(interaction, view=await render_status(expanded=expanded, headline=f"⏳ {_stamp()} 開始跑維護，做完會私訊你一行。"))


async def _guarded(interaction: discord.Interaction, label: str, run: Callable[[], Awaitable[None]], *, expanded: bool) -> None:
    """面板上一次操作的外殼：先驗群主，做壞了換成只剩「重新整理」「回主控台」的畫面並標錯誤（救援畫面不算狀態，不會再失敗）。"""
    if not await require_access(interaction, **_ACCESS):
        return

    async def rescue(notice: str) -> None:
        box = screen_box("## 機器人狀態", notice=notice, colour=discord.Color.red())
        await edit_screen(interaction, view=screen_view(box, [StatusButton("refresh", expanded, label="重新整理"), back_button()]))

    await guarded_screen(interaction, f"機器人狀態面板：{label}", run, rescue=rescue, log=logger)


class PanelRetestButton(discord.ui.DynamicItem[discord.ui.Button], template=PANEL_RETEST_TEMPLATE):
    """面板上每一項右邊的重測；custom_id 帶種類、那一把的 key、面板現在是不是展開的。"""

    def __init__(self, kind: str, key: str, expanded: bool, *, label: str = "重測"):
        self.kind = kind
        self.key = owner_alerts.clean_key(key)
        self.expanded = bool(expanded)
        super().__init__(discord.ui.Button(
            label=label, style=discord.ButtonStyle.primary,
            custom_id=f"owner:panel:{'1' if self.expanded else '0'}:{kind}:{self.key}"))

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match, /):
        return cls(match["kind"], match["key"], match["expanded"] == "1", label=item.label or "重測")

    async def callback(self, interaction: discord.Interaction):
        async def run() -> None:
            cog = interaction.client.get_cog("OwnerAlertCommands")
            if cog is None:
                await safe_send_interaction_message(interaction, _NO_COG, ephemeral=True)
                return
            await cog.handle_retest(interaction, self.kind, self.key, panel_expanded=self.expanded)

        await _guarded(interaction, self.custom_id, run, expanded=self.expanded)


class StatusButton(discord.ui.DynamicItem[discord.ui.Button], template=STATUS_TEMPLATE):
    """底下那排：全部重測、重新整理、展開／收合、看詳細、跑今天的 04:00 維護、確認跑（動作後面帶 1＝面板展開中，看詳細帶頁碼）。"""

    def __init__(self, action: str, expanded: bool = False, page: Optional[int] = None, *, label: str,
                 style: discord.ButtonStyle = discord.ButtonStyle.secondary, disabled: bool = False):
        custom_id = f"owner:status:{action}{'1' if expanded else ''}" + (f":{int(page)}" if page is not None else "")
        super().__init__(discord.ui.Button(label=label, style=style, custom_id=custom_id, disabled=disabled))
        self.action, self.expanded = action, bool(expanded)
        self.page = int(page) if page is not None else 0

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match, /):
        return cls(match["action"], match["expanded"] == "1", match["page"], label=item.label or "重新整理",
                   style=item.style, disabled=item.disabled)

    async def callback(self, interaction: discord.Interaction):
        action, expanded = self.action, self.expanded

        async def run() -> None:
            if action in ("refresh", "expand", "collapse"):
                await edit_screen(interaction, view=await render_status(expanded=action == "expand" or (expanded and action != "collapse")))
            elif action == "all":
                await retest_all(interaction, expanded=expanded)
            elif action == "details":
                await edit_screen(interaction, view=await render_details(expanded=expanded, page=self.page))
            elif action == "maintenance":
                await edit_screen(interaction, view=render_maintenance(expanded=expanded))
            elif action == "go":
                guild = home_guild(interaction)
                if guild is None:
                    await safe_send_interaction_message(interaction, "bot 不只在一個伺服器裡，請到伺服器裡操作。", ephemeral=True)
                    return
                await run_maintenance(interaction, guild, expanded=expanded)

        await _guarded(interaction, self.custom_id, run, expanded=expanded)


async def retest_all(interaction: discord.Interaction, *, expanded: bool = False) -> None:
    """每一項都重測一次（模型後端最後，它會拿顯示卡）；結果寫在面板最上面、整個面板重畫。"""
    await interaction.response.defer()
    rows = await collect()
    rows.sort(key=lambda row: row[0].kind == "lemonade")
    summary: dict[str, int] = {"ok": 0, "bad": 0, "untested": 0}
    bad: list[str] = []
    cog = interaction.client.get_cog("OwnerAlertCommands")
    for spec, _, key in rows:
        if spec.retest is None:
            continue
        try:
            if spec.kind == "lemonade" and cog is not None:
                # 全部重測只是看看：模型後端只探測，不清自癒紀錄與放棄名單（那是它那一列「重測」才做的事）
                result = await cog.probe_lemonade()
            else:
                result = await owner_alerts.retest(spec.kind, key)
        except Exception as exc:  # 邊界：一項重測出錯不能讓整輪停住，寫成那項還是壞
            logger.error("全部重測 %s 出錯：%s", spec.kind, exc, exc_info=True)
            result = RetestResult(False, f"重測出錯：{type(exc).__name__}")
        if result.ok:
            summary["ok"] += 1
        elif result.untested:
            summary["untested"] += 1
        else:
            summary["bad"] += 1
            bad.append(spec.title)
    line = f"🔁 {_stamp()} 全部重測：{summary['ok']} 項正常、{summary['bad']} 項還是壞、{summary['untested']} 項沒測到"
    if bad:
        line += f"（{'、'.join(bad)}）"
    if cog is not None:
        line += "；模型後端只探測、沒清自癒紀錄"
        await cog.close_resolved_dms()
    try:
        await edit_screen(interaction, view=await render_status(expanded=expanded, headline=line))
    except discord.HTTPException as exc:
        logger.warning("全部重測後重畫面板失敗：%s", exc)


DYNAMIC_ITEMS = (PanelRetestButton, StatusButton)
