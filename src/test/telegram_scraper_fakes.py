"""telegram_scraper 測試共用的假物件（檔名不是 test_ 開頭，discover 不會把它當測試收）。

- bot 容器沒裝 Telethon，但 runner、filters 一 import 就要它：**沒裝時才**注入最小的假模組。
  爬蟲容器有真 Telethon，用 `docker exec` 在那邊跑時就是真的。
- 假的 TelegramClient 一建構就拋例外：測試絕不可能連上 Telegram、動到爬蟲的 session。
- 要判斷有沒有真 Telethon，一律用這裡的 `REAL_TELETHON`，不要自己 `find_spec("telethon")`：假模組注入後
  find_spec 會找到假的（假模組都標了 `__fake__ = True`）。
- FakeDB 是記憶體版的 TelegramDatabase，只實作測試用得到的方法；FakeClient 記下每次呼叫，
  用來斷言「先做什麼、後做什麼」。

在爬蟲容器跑（真 Telethon）：
    docker cp src/test/. telegram-scraper:/tmp/scraper_tests/test/
    docker exec -w /tmp/scraper_tests -e PYTHONPATH=/app -e PYTHONDONTWRITEBYTECODE=1 telegram-scraper \\
        python -m unittest test.test_telegram_scraper_media test.test_telegram_scraper_updates -v
"""
import importlib.machinery
import importlib.util
import os
import sys
import types
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
_SCRAPER_DIR_CANDIDATES = (
    os.path.join(os.path.dirname(HERE), "telegram_scraper"),  # repo／bot 容器：src/telegram_scraper
    "/app",                                                    # 爬蟲容器：/app 就是 telegram_scraper
)

#: 在注入假模組之前判斷：之後 find_spec 會找到假的
REAL_TELETHON = importlib.util.find_spec("telethon") is not None

CHAT = -1009990000001
CHANNEL = "Seele_WW_leak"


def _install_fake_telethon() -> None:
    def mod(name: str) -> types.ModuleType:
        module = types.ModuleType(name)
        # test_logger_config 會對已載入的模組 find_spec；__spec__ 是 None 會拋 ValueError
        module.__spec__ = importlib.machinery.ModuleSpec(name, None)
        module.__fake__ = True
        sys.modules[name] = module
        return module

    telethon = mod("telethon")
    utils = mod("telethon.utils")
    events = mod("telethon.events")
    tl = mod("telethon.tl")
    tl_types = mod("telethon.tl.types")
    tl_functions = mod("telethon.tl.functions")
    tl_messages = mod("telethon.tl.functions.messages")

    def get_peer_id(peer, add_mark=True):
        if isinstance(peer, int):
            return peer
        channel_id = getattr(peer, "channel_id", None)
        if channel_id is not None:
            return -(1000000000000 + int(channel_id))
        raise TypeError("假 get_peer_id：不支援的 peer")

    class NewMessage:
        class Event:   # runner 的型別註記 `events.NewMessage.Event` 在定義函式時就會取值
            pass

        def __init__(self, chats=None):
            self.chats = chats

    class TelegramClient:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("測試不可建立真的 TelegramClient")

    class DocumentAttributeFilename:
        def __init__(self, file_name):
            self.file_name = file_name

    class GetCustomEmojiDocumentsRequest:
        def __init__(self, document_id):
            self.document_id = document_id

    utils.get_peer_id = get_peer_id
    events.NewMessage = NewMessage
    telethon.TelegramClient = TelegramClient
    telethon.events = events
    telethon.utils = utils
    telethon.tl = tl
    tl.types = tl_types
    tl.functions = tl_functions
    tl_functions.messages = tl_messages
    tl_types.DocumentAttributeFilename = DocumentAttributeFilename
    tl_messages.GetCustomEmojiDocumentsRequest = GetCustomEmojiDocumentsRequest


def load_scraper() -> SimpleNamespace:
    """import 爬蟲模組（容器內以 /app 為根、模組間裸 import，這裡照樣把目錄加進路徑）。"""
    if not REAL_TELETHON and "telethon" not in sys.modules:
        _install_fake_telethon()
    for path in _SCRAPER_DIR_CANDIDATES:
        if os.path.isfile(os.path.join(path, "handlers.py")):
            if path not in sys.path:
                sys.path.insert(0, path)
            break
    import handlers
    import media_download
    import runner
    return SimpleNamespace(handlers=handlers, runner=runner, media_download=media_download)


# ── 訊息與媒體 ─────────────────────────────────────────────────────────────

def media(type_name: str, **attrs):
    """建一個「類別名稱叫 type_name」的媒體物件，型別名才進得了 log。"""
    return type(type_name, (), {})() if not attrs else _with_attrs(type(type_name, (), {})(), attrs)


def _with_attrs(obj, attrs):
    for key, value in attrs.items():
        setattr(obj, key, value)
    return obj


def photo_media(photo_id: int = 501):
    return media("MessageMediaPhoto", photo=SimpleNamespace(id=photo_id, sizes=[object()]), spoiler=False)


def video_media(doc_id: int = 601, size: int = 10_000):
    return media("MessageMediaDocument",
                 document=SimpleNamespace(id=doc_id, mime_type="video/mp4", size=size, attributes=[]),
                 spoiler=False)


def webpage_media(*, with_photo: bool):
    page = SimpleNamespace(photo=SimpleNamespace(id=701, sizes=[object()]) if with_photo else None, document=None)
    return media("MessageMediaWebPage", webpage=page)


def msg(message_id: int, *, chat: int = CHAT, text: str = "", media_obj=None, date=None, grouped_id=None):
    return SimpleNamespace(
        id=message_id, chat_id=chat, message=text, media=media_obj,
        date=date or datetime.now(timezone.utc), grouped_id=grouped_id,
        fwd_from=None, entities=None,
    )


def hours_ago(hours: float) -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=hours)


# ── 設定 ───────────────────────────────────────────────────────────────────

class FakeWatcher:
    def __init__(self, media_dir: str, *, download_media: bool = True, catchup_interval_min: int = 15):
        self.snapshot = SimpleNamespace(
            history_hours=168, catchup_interval_min=catchup_interval_min, skip_forwards=True,
            forward_whitelist=set(), download_media=download_media, media_dir=media_dir,
        )

    def get_snapshot(self):
        return self.snapshot

    def refresh(self, force=False):
        return self.snapshot


def fake_config(tmpdir: str, channels=(CHANNEL,)):
    return SimpleNamespace(
        source_channels=list(channels), source_channel=channels[0],
        runtime_config_path=os.path.join(tmpdir, "runtime_config.json"),
        session_dir=os.path.join(tmpdir, "session"), session_name="test", media_dir=os.path.join(tmpdir, "media"),
        api_id=1, api_hash="x", pg_notify_channel="telegram_new_message", pg_db="telegram_data",
        history_limit=0, build_asyncpg_dsn=lambda: "postgresql://fake", build_admin_dsn=lambda: "postgresql://fake",
    )


# ── 資料庫 ─────────────────────────────────────────────────────────────────

class FakeDB:
    """記憶體版 TelegramDatabase。has_media 跟真的一樣只會由否變是。"""

    def __init__(self):
        self.rows: dict[tuple[int, int], dict] = {}
        self.media: dict[int, list[dict]] = {}
        self.notified: list[int] = []
        self.upserts: list[dict] = []
        self._next_pk = 1

    def add_row(self, message_id: int, *, chat: int = CHAT, has_media: bool = True, date=None, with_media=False):
        pk = self._next_pk
        self._next_pk += 1
        self.rows[(chat, message_id)] = {"pk": pk, "has_media": has_media, "message_date": date or hours_ago(1)}
        if with_media:
            self.media[pk] = [{"file_rel_path": f"telegram_scraper/media/{message_id}.jpg"}]
        return pk

    def pk_of(self, message_id: int, chat: int = CHAT) -> int:
        return self.rows[(chat, message_id)]["pk"]

    async def upsert_message_only(self, **kw):
        self.upserts.append(kw)
        key = (kw["telegram_chat_id"], kw["telegram_message_id"])
        row = self.rows.get(key)
        if row is not None:
            row["has_media"] = row["has_media"] or kw["has_media"]
            return row["pk"], False
        pk = self._next_pk
        self._next_pk += 1
        self.rows[key] = {"pk": pk, "has_media": kw["has_media"], "message_date": kw["message_date"]}
        return pk, True

    async def has_media_records(self, message_pk):
        return bool(self.media.get(message_pk))

    async def upsert_media_items(self, message_pk, media_items):
        if media_items:
            self.media.setdefault(message_pk, []).extend(media_items)

    async def update_media_spoiler(self, message_pk, is_spoiler):
        return False

    async def notify_new_message(self, message_pk):
        self.notified.append(message_pk)

    async def get_max_message_id(self, chat):
        ids = [mid for (c, mid) in self.rows if c == chat]
        return max(ids) if ids else None

    async def get_existing_message_ids(self, chat, lo, hi):
        return {mid for (c, mid) in self.rows if c == chat and lo <= mid <= hi}

    async def get_message_ids_missing_media(self, chat, lo, hi, posted_after):
        return {
            mid for (c, mid), row in self.rows.items()
            if c == chat and lo <= mid <= hi and row["has_media"] and not self.media.get(row["pk"])
            and row["message_date"] >= posted_after
        }

    async def update_message_entities(self, message_pk, entities):
        return None

    async def get_known_emoji_ids(self, doc_ids):
        return set()

    async def upsert_custom_emoji(self, **kw):
        return None


class FakeTelegramDatabase(FakeDB):
    """給 run_telegram_scraper 用：多了連線生命週期；pool 是 None，重抓監聽會被攔下只記 WARNING。"""

    pool = None

    def __init__(self, *args, **kwargs):
        super().__init__()

    @staticmethod
    async def ensure_database_exists(**kwargs):
        return None

    async def connect(self):
        return None

    async def init_db(self):
        return None

    async def close(self):
        return None


# ── Telegram client ────────────────────────────────────────────────────────

class FakeClient:
    """記下每次呼叫（`calls`）；下載行為可替換（`download_impl`）。"""

    def __init__(self, *, history=None, dialogs=None, dialogs_error=None):
        self.calls: list[tuple] = []
        self.history = history or {}
        self.dialogs = dialogs if dialogs is not None else [SimpleNamespace(id=CHAT, name=CHANNEL)]
        self.dialogs_error = dialogs_error
        self.download_impl = None
        self.downloads: list = []

    async def get_dialogs(self, *args, **kwargs):
        self.calls.append(("get_dialogs",))
        if ("start",) not in self.calls and hasattr(self, "handler"):
            raise ConnectionError("還沒連線（start 之前不能讀對話清單）")
        if self.dialogs_error is not None:
            raise self.dialogs_error
        return list(self.dialogs)

    async def get_entity(self, target):
        self.calls.append(("get_entity", target))
        return SimpleNamespace(id=target, title="假頻道", username=None)

    async def iter_messages(self, channel, reverse=False, offset_id=0, limit=None, **kwargs):
        self.calls.append(("iter_messages", channel))
        items = sorted(self.history.get(channel, []), key=lambda m: m.id, reverse=not reverse)
        if reverse and offset_id:
            items = [m for m in items if m.id > offset_id]
        for count, item in enumerate(items):
            if limit is not None and count >= limit:
                break
            yield item

    async def download_media(self, target, file=None, progress_callback=None, **kwargs):
        self.calls.append(("download_media", getattr(target, "id", None)))
        self.downloads.append(target)
        if self.download_impl is not None:
            return await self.download_impl(target, file, progress_callback)
        return file if file and file.endswith((".jpg", ".mp4", ".png")) else os.path.join(file or "/tmp", "x.jpg")

    async def start(self):
        self.calls.append(("start",))

    def on(self, event):
        def decorator(fn):
            self.handler = fn
            return fn
        return decorator

    async def run_until_disconnected(self):
        self.calls.append(("run_until_disconnected",))
