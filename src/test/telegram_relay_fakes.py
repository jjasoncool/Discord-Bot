"""Telegram 轉發端測試共用的假物件（不需 DB、Discord、模型）。

- `FakeRepository` 模擬爬蟲「先寫訊息列、下載完才寫媒體列」的順序，發送紀錄依 (pk, 頻道) 記。
- `FakeBot` 有頻道對照表：主頻道 `CHANNEL`，隔離 thread 由 `FakeChannel.create_thread` 開；跟 discord.py
  一樣，封存的 thread 不在 `threads`（快取）裡、`get_channel` 拿不到要 `fetch_channel`。
- `FakeFilter` 照 pk 回事先排好的判定，記下每次被叫的內容；`make_worker` 預設**不接過濾**，
  既有的相簿測試不會打到模型。

檔名不能用 test_ 開頭（discover 會當成測試收），也不能跟 src 的套件或爬蟲的裸模組同名。
"""
import asyncio
import contextlib
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import discord

from services.relay.telegram_filter import Verdict
from services.relay.telegram_quarantine import QuarantineThreads
from services.relay.telegram_relay_service import MessageRelayWorker, TelegramMediaRecord, TelegramMessageRecord

# 刻意用不存在的假 id：logger 會寫進正式 log，用真實 id 會和線上相簿的合併紀錄混在一起
CHAT = -1009990000001
GID = 990000000000001
CHANNEL = 990000000000002
BOT_ID = 990000000000009


class FakeRepository:
    """只實作 worker 會用到的查詢；模擬 scraper「先寫列、後寫媒體」的寫入順序。"""

    def __init__(self) -> None:
        self.rows: dict[int, dict] = {}
        self.media: dict[int, list[TelegramMediaRecord]] = {}
        self.delivered: dict[tuple[int, int], datetime] = {}
        self.replay_pk = None
        self.reads: list[int] = []
        self.read_delay = 0.0
        #: 改紀錄（搬移）要出錯的時機："start"＝一開始、"commit"＝區塊做完要寫入時
        self.fail_move: str | None = None

    def add_row(self, pk: int, msg_id: int, *, grouped_id=GID, text: str = "", has_media: bool = True,
                date: datetime | None = None) -> None:
        self.rows[pk] = {
            "chat": CHAT, "msg_id": msg_id, "gid": grouped_id, "text": text, "has_media": has_media, "date": date,
        }

    def add_media(self, pk: int) -> None:
        self.media[pk] = [TelegramMediaRecord(file_rel_path=f"media/{pk}.jpg", media_type="photo")]

    def add_ready(self, pk: int, msg_id: int, **kwargs) -> None:
        self.add_row(pk, msg_id, **kwargs)
        self.add_media(pk)

    def mark(self, pk: int, when: datetime | None = None, channel: int = CHANNEL) -> None:
        self.delivered[(pk, channel)] = when or datetime.now(timezone.utc)

    def channels_of(self, pk: int) -> set[int]:
        return {ch for (p, ch) in self.delivered if p == pk}

    async def get_message_by_pk(self, pk):
        self.reads.append(pk)
        row = self.rows.get(pk)
        record = None if row is None else TelegramMessageRecord(
            message_pk=pk,
            telegram_chat_id=row["chat"],
            telegram_message_id=row["msg_id"],
            text=row["text"],
            message_date=row["date"],
            has_media=row["has_media"],
            grouped_id=row["gid"],
            media_items=list(self.media.get(pk, [])),
        )
        # 跟真的資料庫一樣：查詢當下的資料，傳回來之前有延遲（這段期間寫入的不會出現在結果裡）
        if self.read_delay:
            await asyncio.sleep(self.read_delay)
        return record

    async def get_group_member_states(self, grouped_id, chat_id):
        members = sorted(
            (row["msg_id"], pk) for pk, row in self.rows.items()
            if row["gid"] == grouped_id and row["chat"] == chat_id
        )
        return [(pk, (not self.rows[pk]["has_media"]) or pk in self.media) for _, pk in members]

    async def get_deliveries(self, message_pks):
        out: dict[int, dict[int, datetime]] = {}
        for (pk, channel), when in self.delivered.items():
            if pk in message_pks and channel != 0:
                out.setdefault(pk, {})[channel] = when
        return out

    async def list_quarantined(self, thread_ids, main_channel_id):
        rows = []
        for (pk, channel) in list(self.delivered):
            if channel in thread_ids and (pk, main_channel_id) not in self.delivered and pk in self.rows:
                row = self.rows[pk]
                rows.append({
                    "pk": pk, "chat_id": row["chat"], "telegram_message_id": row["msg_id"], "grouped_id": row["gid"],
                    "message_date": row["date"], "text": row["text"],
                    "media": [m.media_type for m in self.media.get(pk, [])],
                })
        unique = {r["pk"]: r for r in rows}.values()
        return sorted(unique, key=lambda r: (r["message_date"] or datetime.min.replace(tzinfo=timezone.utc),
                                             r["telegram_message_id"]))

    async def mark_message_published(self, pk, discord_channel_id):
        self.delivered[(pk, discord_channel_id)] = datetime.now(timezone.utc)

    @contextlib.asynccontextmanager
    async def moving_deliveries(self, message_pks, from_channel_id, to_channel_id):
        """跟真的一樣是一筆交易：只改頻道、時間不動；區塊內出錯（或寫入失敗）就整批還原。"""
        if self.fail_move == "start":
            raise RuntimeError("資料庫斷線")
        if any((pk, from_channel_id) in self.delivered and (pk, to_channel_id) in self.delivered for pk in message_pks):
            raise RuntimeError("唯一鍵衝突（同一則已有 to 那列）")   # 跟真的一樣：(pk, 頻道) 是唯一鍵
        before = dict(self.delivered)
        moved = []
        for pk in message_pks:
            if (pk, from_channel_id) in self.delivered:
                self.delivered[(pk, to_channel_id)] = self.delivered.pop((pk, from_channel_id))
                moved.append((len(moved) + 1, pk))
        try:
            yield moved
            if self.fail_move == "commit":
                raise RuntimeError("寫入失敗")
        except BaseException:
            self.delivered = before
            raise

    async def set_runtime_cursor_pk(self, pk):
        pass

    async def get_pk_by_telegram_message_id(self, telegram_message_id, telegram_chat_id=None):
        return self.replay_pk


class FakeRouteResolver:
    def __init__(self) -> None:
        self.replay_msg_id = None
        self.routes = [CHANNEL]

    def resolve_telegram_routes(self, chat_id):
        return list(self.routes)

    def resolve_replay_msg_id(self, chat_id):
        return self.replay_msg_id


class FakePlan(dict):
    """跟 RenderPlan 一樣有 operations（第一則的 content 放隔離那行），內容用 dict 方便斷言。"""

    def __init__(self, **fields) -> None:
        super().__init__(**fields)
        self.operations = [SimpleNamespace(content="")]

    @property
    def header(self) -> str:
        return self.operations[0].content


class FakeRenderAdapter:
    app_root = "/tmp"

    def render(self, message, emoji_map=None, title_suffix=""):
        return FakePlan(
            pks=message.message_pk,
            media=[m.file_rel_path for m in message.media_items],
            title_suffix=title_suffix,
            text=message.text,
        )


class FakePublisher:
    def __init__(self) -> None:
        self.plans: list[FakePlan] = []
        #: (送到的頻道 id, plan)
        self.sent: list[tuple[int, FakePlan]] = []
        self.delay = 0.0
        self.on_publish = None
        self.fail_channels: set[int] = set()
        #: 跟真的一樣分則送：第一則 embed 帶第一張圖，其餘的圖另外一則、沒有 embed（只有檔名 tg_<pk>_<n>）
        self.split_media = False

    async def publish_to_channel(self, channel, plan, *, sent=None):
        if channel.id in self.fail_channels:
            raise RuntimeError("Discord 送出失敗")
        self.plans.append(plan)
        self.sent.append((channel.id, plan))
        files = [f"tg_{plan['pks']}_{n}.jpg" for n in range(1, len(plan["media"]) + 1)] if self.split_media else []
        # 跟真的一樣：第一則帶隔離那行（content）與 embed footer「msg #… · db#…」
        messages = [await channel.send(content=plan.header or None,
                                       footer=f"msg #{plan['pks']} · db#{plan['pks']}", attachments=files[:1])]
        if files[1:]:
            messages.append(await channel.send(attachments=files[1:]))
        if sent is not None:
            sent.extend(messages)
        if self.on_publish is not None:
            self.on_publish()
        if self.delay:
            await asyncio.sleep(self.delay)
        return 1

    def to(self, channel_id: int) -> list[FakePlan]:
        return [plan for ch, plan in self.sent if ch == channel_id]


class FakeMessage:
    def __init__(self, channel, mid: int, content=None, *, footer=None, view=None, attachments=(),
                 author_id: int = BOT_ID) -> None:
        self.channel = channel
        self.id = mid
        self.content = content
        self.author = SimpleNamespace(id=author_id)
        self.attachments = [SimpleNamespace(filename=name) for name in attachments]
        self.created_at = datetime.now(timezone.utc)
        #: 設了就在 delete() 時拋出（模擬 Discord 刪不掉）
        self.delete_error: Exception | None = None
        self.embeds = [SimpleNamespace(footer=SimpleNamespace(text=footer))] if footer else []
        self.components = [SimpleNamespace(children=list(view.children))] if view is not None else []
        self.view = view
        self.jump_url = f"https://discord.com/channels/1/{channel.id}/{mid}"
        self.edits: list[dict] = []
        self.deleted = False

    async def edit(self, **kwargs):
        if getattr(self.channel, "archived", False):
            # 跟 Discord 一樣：封存中的 thread 改不了訊息
            raise discord.HTTPException(SimpleNamespace(status=400, reason="Bad Request"), "Thread is archived")
        self.edits.append(kwargs)
        self.content = kwargs.get("content", self.content)

    async def delete(self):
        if getattr(self.channel, "archived", False):
            raise discord.HTTPException(SimpleNamespace(status=400, reason="Bad Request"), "Thread is archived")
        if self.delete_error is not None:
            raise self.delete_error
        if self.deleted:
            raise discord.NotFound(SimpleNamespace(status=404, reason="Not Found"), "Unknown Message")
        self.deleted = True
        if self in self.channel.messages:
            self.channel.messages.remove(self)


class _MessageHolder:
    """頻道與 thread 共用：送訊息、翻歷史、用 id 拿訊息。"""

    async def send(self, content=None, *, footer=None, view=None, attachments=(), **kwargs):
        if hasattr(self, "archived"):
            self.archived = False   # 跟 Discord 一樣：對封存的 thread 發訊息會把它打開
        message = FakeMessage(self, self.bot.next_id(), content, footer=footer, view=view, attachments=attachments)
        self.messages.append(message)
        return message

    async def history(self, *, limit=100, after=None):
        # 跟 discord.py 一樣：沒給 after 時新到舊；給了 after 時舊到新、只回之後的
        messages = list(self.messages) if after is not None else list(reversed(self.messages))
        if after is not None:
            messages = [m for m in messages if m.created_at > after]
        for message in messages[:limit]:
            yield message

    def get_partial_message(self, mid):
        for message in self.messages:
            if message.id == mid:
                return message
        raise discord.NotFound(SimpleNamespace(status=404, reason="Not Found"), "Unknown Message")


class FakeThread(_MessageHolder):
    def __init__(self, bot, tid: int, name: str, parent, auto_archive_duration=None) -> None:
        self.bot = bot
        self.id = tid
        self.name = name
        self.parent = parent
        self.parent_id = parent.id
        self.owner_id = BOT_ID
        self.archived = False
        self.auto_archive_duration = auto_archive_duration
        self.guild = parent.guild
        self.edits: list[dict] = []
        self.messages: list[FakeMessage] = []

    async def edit(self, **kwargs):
        self.edits.append(kwargs)
        self.archived = kwargs.get("archived", self.archived)

    def delete(self) -> None:
        self.parent.all_threads.remove(self)
        self.bot.channels.pop(self.id, None)


class FakeChannel(_MessageHolder):
    def __init__(self, bot, cid: int, name: str = "leak") -> None:
        self.bot = bot
        self.id = cid
        self.name = name
        self.guild = SimpleNamespace(me=SimpleNamespace(id=BOT_ID), get_channel=bot.get_channel, name="guild")
        self.all_threads: list[FakeThread] = []
        self.created: list[dict] = []
        self.fail_create = False
        self.messages: list[FakeMessage] = []

    @property
    def threads(self):
        # 跟 discord.py 一樣：快取裡只有活躍的 thread
        return [t for t in self.all_threads if not t.archived]

    async def archived_threads(self, *, limit=100, private=False):
        for t in [t for t in self.all_threads if t.archived]:
            yield t

    async def create_thread(self, *, name, type=None, auto_archive_duration=None, reason=None, **kwargs):
        if self.fail_create:
            raise discord.HTTPException(SimpleNamespace(status=403, reason="Forbidden"), "沒有權限")
        self.created.append({"name": name, "type": type, "auto_archive_duration": auto_archive_duration})
        thread = FakeThread(self.bot, self.bot.next_id(), name, self, auto_archive_duration)
        self.all_threads.append(thread)
        self.bot.channels[thread.id] = thread
        return thread


class FakeBot:
    def __init__(self) -> None:
        self.user = SimpleNamespace(id=BOT_ID)
        self._ids = iter(range(990000000000100, 990000000099999))
        self.channels: dict[int, object] = {}
        self.main = FakeChannel(self, CHANNEL)
        self.channels[CHANNEL] = self.main

    def next_id(self) -> int:
        return next(self._ids)

    def get_channel(self, channel_id):
        channel = self.channels.get(channel_id)
        # 封存的 thread 不在快取
        if channel is not None and getattr(channel, "archived", False):
            return None
        return channel

    async def fetch_channel(self, channel_id):
        channel = self.channels.get(channel_id)
        if channel is None:
            raise discord.NotFound(SimpleNamespace(status=404, reason="Not Found"), "Unknown Channel")
        return channel


class FakeFilter:
    """照 pk 回事先排好的判定（沒排的放行），記下每次被叫的內容。"""

    def __init__(self, mode: str = "on") -> None:
        self.mode = mode
        self.verdicts: dict[int, Verdict] = {}
        self.calls: list[dict] = []
        self.delay = 0.0
        self.active = 0
        self.max_active = 0

    def quarantine(self, pk: int, label: str = "灌水", reason: str = "每日打卡") -> None:
        self.verdicts[pk] = Verdict(True, label=label, reason=reason)

    async def judge(self, text, media, *, trace_id):
        pk = int(trace_id.rsplit("-", 1)[-1])
        self.calls.append({"pk": pk, "text": text, "media": [m.path.name for m in media]})
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
        finally:
            self.active -= 1
        return self.verdicts.get(pk, Verdict(False, reason="有情報"))


def make_worker(*, content_filter=None, quarantine: bool = False, bot: FakeBot | None = None,
                repo: FakeRepository | None = None, runtime_path: str | None = None):
    """回傳 (worker, repo, routes, publisher)；`quarantine=True` 時接上隔離區（runtime 檔放暫存目錄）。"""
    repo = repo or FakeRepository()
    routes = FakeRouteResolver()
    publisher = FakePublisher()
    bot = bot or FakeBot()
    registry = None
    if quarantine:
        # 沒指定時放進系統暫存目錄的固定子目錄（呼叫端要乾淨的就自己給、自己清）
        if runtime_path is None:
            folder = Path(tempfile.gettempdir()) / "telegram_relay_fakes"
            folder.mkdir(exist_ok=True)
            runtime_path = str(folder / f"quarantine_{uuid.uuid4().hex}.json")
        registry = QuarantineThreads(bot, runtime_path)
    worker = MessageRelayWorker(
        bot=bot,
        repository=repo,
        route_resolver=routes,
        render_adapter=FakeRenderAdapter(),
        publisher=publisher,
        dsn="",
        content_filter=content_filter,
        quarantine=registry,
    )
    # 測試用縮短等待；比例與正式值一致（輪詢 < 安靜期 < 上限）
    worker._GROUP_QUIET_SEC = 0.1
    worker._GROUP_POLL_INTERVAL = 0.01
    worker._GROUP_MAX_WAIT_SEC = 1.0
    return worker, repo, routes, publisher


def media_of(*pks):
    return [f"media/{pk}.jpg" for pk in pks]
