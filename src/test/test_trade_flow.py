"""交易流程（services.community.trade_service ＋ commands.forum_monitor），交易的正本在市集資料庫。

守的底線：
  1. 接單：供應方（Trader）對自由市場貼文本身按接單表情，就在購物車開私人對話（不可邀請），
     只加入需求方與這位供應方，開單訊息 @ 雙方，資料庫記下這筆交易與開單訊息。需求方是誰：自己發的貼文是作者，
     /select_item 由 bot 代發的是內文被 @ 的人。開單做到一半失敗不留下對話、也不留下資料庫的紀錄。
  2. 不開單：沒有 Trader 身份組、對貼文裡的回覆按、別的論壇、不是接單表情、bot 自己、
     供應方對自己的需求按、需求方是別的 bot、上線匯入還沒做完。
  3. 同一篇需求，每位供應方各開一個對話；同一位再按不重開，只在原對話提醒他——對話被自動封存了也一樣（查資料庫）。
  4. 按鈕各有其人，身分照資料庫、不照按鈕上寫的：只有供應方能通知領收；供應方與群主能取消；
     只有需求方能按已領收；別人按不改變任何狀態。沒有交易紀錄的對話、匯入還沒做完時按，都回一句說明。
  5. 完成：資料庫先記完成，再發完成訊息、收按鈕、鎖定（反過來對話會被重新打開）；對話裡不 @ 人，改私訊雙方
     並附交易對話的連結；需求貼文的對話封存後刪除原貼文（封存失敗就保留、刪除失敗要說；不在自由市場的貼文絕不刪）；
     同一篇的其他供應方對話結束（資料庫也記）並私訊。結束後再通知不會把對話打開。
     封存格式：放得下 2000 字就整段寫在貼文裡；放不下時貼文放摘要、完整對話放附檔；@ 換成名字，發封存不通知任何人。
  6. 取消：資料庫記取消；標題【已取消】並鎖定；需求貼文保留；只清掉這位供應方的接單表情（需求貼文
     已被自動封存也清得掉）；群主取消時私訊寫的是群主。
  7. 領收期限：通知後滿 24 小時沒確認就自動完成；期限從資料庫裡的通知時間算，重啟後照樣補做，
     停機期間對話被自動封存也一樣。按「還沒領收」就暫停（按到舊通知上的不算），等供應方再通知才重新計時；
     新通知讓舊通知失效；到期前 @ 需求方提醒一次，提醒過記在資料庫，重啟也不重複。
     有爭議時雙方都能請群主進對話，只會請一次。一筆交易壞了不影響其他交易這一輪的檢查。
  8. 只 @ 下一步要動手的人：通知領收只 @ 需求方、還沒領收只 @ 供應方、提醒只 @ 需求方。
  9. 改版前的舊交易對話：舊文字讀得回交易身分（上線匯入用），舊按鈕走同一套流程。
 10. 分層：交易模組不 import 指令層；介面層的按鈕 custom_id 解析得回同一個動作。
 11. 名字一律是伺服器暱稱：成員快取拿不到人時向 Discord API 查。查不到要留 log。
 12. 給群友看的訊息不寫程式用語：交易 thread 一律說「對話」。
 13. 讀交易對話只在 TradeThreadLog（上線匯入、收按鈕）：一律讀完整串；最新那則通知才算數；只認 bot 的訊息；
     收按鈕時連商品的交易進度一起收，訂單紀錄不算交易按鈕。
"""

import ast
import asyncio
import itertools
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import discord  # noqa: E402

from services.community import trade_progress as tp  # noqa: E402
from services.community import trade_service  # noqa: E402
from services.community.trade_service import (  # noqa: E402
    CANCEL,
    CANCEL_OK,
    HELP,
    HOLD,
    KEEP,
    NOTIFY,
    RECEIVE,
    TradeRef,
    TradeService,
    read_trade_thread,
)
from services.market_db import MarketDB  # noqa: E402

GUILD_ID = 1
FORUM_ID = 100
OTHER_FORUM_ID = 101
CART_ID = 200
ARCHIVE_ID = 300

T0 = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)


def _member(uid, name, *, bot=False):
    return SimpleNamespace(id=uid, display_name=name, mention=f"<@{uid}>", bot=bot, roles=[])


BOT = _member(9, "bot", bot=True)
OTHER_BOT = _member(8, "別的bot", bot=True)
REQUESTER = _member(11, "需求者")
SUPPLIER = _member(21, "供應者甲")
SUPPLIER_B = _member(22, "供應者乙")
OUTSIDER = _member(31, "路人")
OWNER = _member(5, "群主")
TRADERS = {SUPPLIER.id, SUPPLIER_B.id}


class World:
    """一個假的伺服器：自由市場論壇、購物車文字頻道、封存論壇。"""

    def __init__(self):
        self.now = T0
        self.ids = itertools.count(1000)
        self.channels = {}
        self.members = {m.id: m for m in (BOT, OTHER_BOT, REQUESTER, SUPPLIER, SUPPLIER_B, OUTSIDER, OWNER)}
        self.fail_add_user = False
        #: 成員快取裡有誰；None＝全部都在。設成空集合就是「快取拿不到人」
        self.cached = None
        self.api_lookups = []
        self.guild = SimpleNamespace(
            id=GUILD_ID,
            owner_id=OWNER.id,
            name="測試伺服器",
            get_member=self._get_member,
            fetch_member=self._fetch_member,
        )
        self.cart = FakeCart(self, CART_ID)
        self.archive = SimpleNamespace(id=ARCHIVE_ID, available_tags=[SimpleNamespace(name="封存")])
        self.channels.update({CART_ID: self.cart, ARCHIVE_ID: self.archive})
        self.archived_posts = []
        self.bot = SimpleNamespace(
            user=BOT,
            get_channel=self.channels.get,
            fetch_channel=self._fetch_channel,
            get_guild=lambda gid: self.guild if gid == GUILD_ID else None,
        )

    def _get_member(self, uid):
        if self.cached is not None and uid not in self.cached:
            return None
        return self.members.get(uid)

    async def _fetch_member(self, uid):
        self.api_lookups.append(uid)
        if uid not in self.members:
            raise discord.NotFound(mock.MagicMock(status=404), "unknown member")
        return self.members[uid]

    async def _fetch_channel(self, cid):
        raise discord.NotFound(mock.MagicMock(status=404), "unknown channel")

    def put_reaction(self, post, emoji, user):
        """有人在需求貼文本身按了表情（Discord 上看得到；只送事件不會留下表情）。"""
        starter = post.messages[0]
        reaction = next((r for r in starter.reactions if str(r.emoji) == emoji), None)
        if reaction is None:
            reaction = FakeReaction(emoji)
            starter.reactions.append(reaction)
        reaction.people.append(user)

    def post(self, author, content="", *, mentions=(), forum_id=FORUM_ID, title="需要購買2000個PY幣"):
        thread_id = next(self.ids)
        thread = FakeThread(self, thread_id, title, parent_id=forum_id)
        # 論壇貼文第一則訊息的 id 等於 thread id
        thread.messages.append(FakeMessage(self, thread_id, author, content, mentions=mentions, thread=thread))
        self.channels[thread_id] = thread
        return thread

    def advance(self, **delta):
        self.now += timedelta(**delta)


class FakeMessage:
    def __init__(self, world, mid, author, content="", *, mentions=(), view=None, embed=None, thread=None,
                 allowed_mentions=None):
        self.id = mid
        self.thread = thread
        self.channel = thread
        self.author = author
        self.content = content or ""
        self.mentions = list(mentions)
        self.embed = embed
        self.embeds = [embed] if embed is not None else []
        self.edits = []
        self.view = view
        self.created_at = world.now
        self.attachments = []
        self._set_view(view)
        self.reactions = []
        self.removed_reactions = []
        #: 這則訊息實際會 @ 到誰；None＝沒指定（全域預設：訊息裡寫到的人都會被 @）
        self.pinged = None if allowed_mentions is None else sorted(u.id for u in allowed_mentions.users or [])

    def _set_view(self, view):
        self.view = view
        self.components = []
        if view is not None:
            # 真的 discord.ui.View（商品上架的測試）直接用它的元件；交易測試的假 view 只有 custom_ids
            children = getattr(view, "children", None)
            if children is None:
                children = [SimpleNamespace(custom_id=c) for c in view.custom_ids]
            # 從 Discord 讀回來的訊息元件沒有 DynamicItem 那層包裝
            children = [getattr(child, "item", child) for child in children]
            self.components = [SimpleNamespace(children=list(children))]

    async def edit(self, *, content=None, view="unchanged", embed="unchanged", attachments="unchanged",
                   allowed_mentions=None):
        # 跟 Discord 一樣：封存中的 thread 改不了訊息（50083 Thread is archived）
        if self.thread is not None and self.thread.archived:
            raise discord.HTTPException(mock.MagicMock(status=400), "Thread is archived")
        self.edits.append({"content": content, "view": view, "embed": embed, "attachments": attachments})
        if content is not None:
            self.content = content
        if view != "unchanged":
            self._set_view(view)
        if embed != "unchanged":
            self.embed = embed
            self.embeds = [embed] if embed is not None else []

    async def add_reaction(self, emoji):
        self.reactions.append(SimpleNamespace(emoji=emoji, me=True))

    async def remove_reaction(self, emoji, user):
        # 對封存中的 thread 改反應會被 Discord 拒絕
        if self.thread is not None and self.thread.archived:
            raise discord.HTTPException(mock.MagicMock(status=400), "Thread is archived")
        self.removed_reactions.append((emoji, user.id))


class FakeReaction:
    def __init__(self, emoji, *, me=False):
        self.emoji = emoji
        self.me = me
        self.people = []

    async def users(self):
        for user in list(self.people):
            yield user


class FakeThread:
    def __init__(self, world, tid, name, *, parent_id, type_=None, invitable=True, auto_archive_duration=None):
        self.world = world
        self.id = tid
        self.name = name
        self.parent_id = parent_id
        self.type = type_
        self.invitable = invitable
        self.auto_archive_duration = auto_archive_duration
        self.locked = False
        self.archived = False
        self.archive_timestamp = None
        self.deleted = False
        self.members = []
        self.messages = []
        self.guild = world.guild
        self.jump_url = f"https://discord.com/channels/{GUILD_ID}/{tid}"
        self.mention = f"<#{tid}>"
        self.events = []  # ("send", 內容) / ("edit", kwargs)，用來檢查先後順序
        self.fail_send = False

    async def send(self, content=None, *, embed=None, view=None, allowed_mentions=None, **kwargs):
        if self.fail_send:
            raise discord.HTTPException(mock.MagicMock(status=500), "send failed")
        # 跟 Discord 一樣：一則訊息最多 2000 字，超過整則退回
        if content is not None and len(content) > 2000:
            raise discord.HTTPException(mock.MagicMock(status=400), "Must be 2000 or fewer in length")
        # 跟 Discord 一樣：對已封存的 thread 發訊息會把它重新打開
        self.archived = False
        msg = FakeMessage(self.world, next(self.world.ids), BOT, content, view=view, embed=embed, thread=self,
                          allowed_mentions=allowed_mentions)
        self.messages.append(msg)
        self.events.append(("send", content))
        return msg

    def check_editable(self, kwargs):
        """跟 Discord 一樣：封存中的 thread 要在同一個請求裡解封（archived=False）才改得了（50083）。"""
        if self.archived and kwargs.get("archived") is not False:
            raise discord.HTTPException(mock.MagicMock(status=400), "Thread is archived")

    async def edit(self, **kwargs):
        self.check_editable(kwargs)
        self.events.append(("edit", kwargs))
        self.name = kwargs.get("name", self.name)
        self.locked = kwargs.get("locked", self.locked)
        if kwargs.get("archived") and not self.archived:
            self.archive_timestamp = self.world.now
        self.archived = kwargs.get("archived", self.archived)

    def auto_archive(self):
        """Discord 在一段時間沒人講話後自動封存。"""
        self.archived = True
        self.archive_timestamp = self.world.now

    async def add_user(self, user):
        if self.world.fail_add_user:
            raise discord.HTTPException(mock.MagicMock(status=500), "add_user failed")
        # 跟 Discord 一樣：封存中的 thread 加不了人
        if self.archived:
            raise discord.HTTPException(mock.MagicMock(status=400), "Thread is archived")
        self.members.append(user.id)

    async def fetch_message(self, mid):
        found = next((m for m in self.messages if m.id == mid), None)
        if found is None:
            raise discord.NotFound(mock.MagicMock(status=404), "unknown message")
        return found

    async def fetch_member(self, uid):
        if uid not in self.members:
            raise discord.NotFound(mock.MagicMock(status=404), "unknown thread member")
        return SimpleNamespace(id=uid)

    async def delete(self):
        self.deleted = True
        self.world.channels.pop(self.id, None)
        if self in self.world.cart.all_threads:
            self.world.cart.all_threads.remove(self)

    async def history(self, limit=100, oldest_first=False):
        messages = self.messages if oldest_first else list(reversed(self.messages))
        for msg in messages[:limit]:
            yield msg

    def sent(self):
        return [content for kind, content in self.events if kind == "send"]

    def last(self):
        return self.messages[-1]


class FakeCart:
    def __init__(self, world, cid):
        self.world = world
        self.id = cid
        self.guild = world.guild
        self.all_threads = []

    @property
    def threads(self):
        # 跟 discord.py 一樣：快取裡只有活躍的 thread，一封存就被移出
        return [t for t in self.all_threads if not t.archived]

    async def archived_threads(self, *, private=False, limit=100):
        archived = [t for t in self.all_threads if t.archived and (t.type == discord.ChannelType.private_thread
                                                                    or not private)]
        for thread in sorted(archived, key=lambda t: t.archive_timestamp, reverse=True):
            yield thread

    async def create_thread(self, *, name, type, invitable, reason, auto_archive_duration=None):
        thread = FakeThread(self.world, next(self.world.ids), name, parent_id=self.id, type_=type,
                            invitable=invitable, auto_archive_duration=auto_archive_duration)
        self.all_threads.append(thread)
        self.world.channels[thread.id] = thread
        return thread


def _make_view(ref, actions):
    return SimpleNamespace(actions=tuple(actions), custom_ids=[ref.custom_id(a) for a in actions])


class MarketTestMixin:
    """一個測試一個 event loop、一個暫存的市集資料庫（商品流程的測試也用）。

    服務都在同一個 loop 上跑：資料庫的鎖與連線不能跨 loop。重啟＝同一個資料庫、新的服務實例。"""

    def start_market(self):
        self.loop = asyncio.new_event_loop()
        self.addCleanup(self.loop.close)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.db = MarketDB(Path(directory.name) / "market.db")
        self.call(self.db.connect())
        self.addCleanup(lambda: self.call(self.db.close()))

    async def get_db(self):
        return self.db

    def call(self, coro):
        return self.loop.run_until_complete(coro)

    def interaction(self, user, thread, message=None):
        return SimpleNamespace(
            user=user, channel=thread, message=message, guild=getattr(thread, "guild", None),
            response=SimpleNamespace(is_done=lambda: False, defer=mock.AsyncMock(),
                                     edit_message=mock.AsyncMock(), send_modal=mock.AsyncMock()),
            edit_original_response=mock.AsyncMock(),
            followup=SimpleNamespace(edit_message=mock.AsyncMock(), send=mock.AsyncMock()),
        )

    def trade_row(self, thread):
        return self.call(self.db.get_trade(thread.id))

    def events(self, thread):
        return [e.kind for e in self.call(self.db.events(thread.id))]


class TradeFlowTestCase(MarketTestMixin, unittest.TestCase):
    def setUp(self):
        self.world = World()
        self.start_market()
        self.config = {
            "trade_forum_channel_id": FORUM_ID,
            "cart_delivery_channel_id": CART_ID,
            "archive_channel_id": ARCHIVE_ID,
        }

        async def get_configured_id(key, *args, **kwargs):
            return self.config.get(key)

        async def check_role(member, role):
            return role == "Trader" and member.id in TRADERS

        async def post_to_channel(channel, **kwargs):
            self.world.archived_posts.append((channel, kwargs))
            return SimpleNamespace(id=next(self.world.ids))

        self.ephemeral = mock.AsyncMock(name="safe_send_interaction_message")
        self.dms = mock.AsyncMock(name="send_dm", return_value=True)
        patches = [
            mock.patch.object(trade_service.ChannelConfig, "get_configured_id", side_effect=get_configured_id),
            mock.patch.object(trade_service, "check_role", side_effect=check_role),
            mock.patch.object(trade_service, "post_to_channel", side_effect=post_to_channel),
            mock.patch.object(trade_service, "safe_send_interaction_message", self.ephemeral),
            mock.patch.object(trade_service, "send_dm", self.dms),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.service = self.new_service()

    def new_service(self, *, ready=True):
        """新的服務實例＝模擬 bot 重啟：記憶體裡什麼都沒有，只剩資料庫與 Discord 上的東西。"""
        service = TradeService(self.world.bot, make_view=_make_view, db=self.get_db, now=lambda: self.world.now)
        if ready:
            service.ready.set()
        return service

    def react(self, post, user, emoji="✅", *, message_id=None, with_member=True, service=None):
        payload = SimpleNamespace(
            emoji=emoji, guild_id=GUILD_ID, channel_id=post.id,
            message_id=post.id if message_id is None else message_id,
            user_id=user.id, member=user if with_member else None,
        )
        return self.call((service or self.service).handle_reaction(payload))

    def press(self, thread, user, action, ref=None, *, message=None, service=None):
        interaction = self.interaction(user, thread, message)
        self.call((service or self.service).handle_button(interaction, action, ref or self.ref_of(thread)))
        return interaction

    def opening(self, thread):
        return thread.messages[0]

    def confirm(self, thread, *, service=None):
        """供應方按通知需求方領收、需求方在那則通知上按已領收。"""
        trade = self.trade_row(thread)
        self.press(thread, self.world.members[trade.supplier_id], NOTIFY, service=service)
        notice = thread.last()
        return self.press(thread, self.world.members[trade.requester_id], RECEIVE, message=notice, service=service)

    def ref_of(self, thread):
        return TradeRef(*map(int, self.opening(thread).view.custom_ids[0].split(":")[2:]))

    def last_reply(self):
        return self.ephemeral.await_args.args[1]


class OpenTradeTests(TradeFlowTestCase):

    def test_self_post_opens_private_thread_with_only_both_parties(self):
        post = self.world.post(REQUESTER, "幫我換成台幣謝謝")

        opened = self.react(post, SUPPLIER)

        self.assertTrue(opened.created)
        thread = opened.thread
        self.assertEqual(self.world.cart.threads, [thread])
        self.assertEqual(thread.type, discord.ChannelType.private_thread)
        self.assertFalse(thread.invitable)
        self.assertEqual(thread.auto_archive_duration, 10080)
        self.assertEqual(sorted(thread.members), sorted([REQUESTER.id, SUPPLIER.id]))
        self.assertTrue(thread.name.startswith("【交易中】"))
        self.assertTrue(thread.name.endswith(f" - {post.id}"))
        first = self.opening(thread)
        self.assertEqual(first.pinged, sorted([REQUESTER.id, SUPPLIER.id]))
        self.assertEqual(first.view.actions, (NOTIFY, CANCEL, HELP))
        self.assertIn("供應方和群主可以取消", first.embed.fields[-1].value)
        self.assertEqual(self.ref_of(thread), TradeRef(post.id, REQUESTER.id, SUPPLIER.id))
        trade = self.trade_row(thread)
        self.assertEqual((trade.source_kind, trade.source_id, trade.requester_id, trade.supplier_id, trade.status),
                         ("forum", post.id, REQUESTER.id, SUPPLIER.id, "open"))
        (opened_event,) = self.call(self.db.events(thread.id))
        self.assertEqual((opened_event.kind, opened_event.message_id), (tp.OPENED, first.id))

    def test_bot_post_requester_is_the_mentioned_member(self):
        post = self.world.post(BOT, f"群友 {REQUESTER.mention} 需要購買：\n1 個 60月相", mentions=[REQUESTER])

        opened = self.react(post, SUPPLIER)

        self.assertEqual(self.trade_row(opened.thread).requester_id, REQUESTER.id)

    def test_reactions_that_do_not_open_a_trade(self):
        post = self.world.post(REQUESTER, "需要代儲")
        other_forum_post = self.world.post(REQUESTER, "別的論壇", forum_id=OTHER_FORUM_ID)
        own_post = self.world.post(SUPPLIER, "供應方自己的需求")
        bot_post = self.world.post(OTHER_BOT, "別的 bot 發的")
        reply_id = next(self.world.ids)
        post.messages.append(FakeMessage(self.world, reply_id, REQUESTER, "補充說明"))
        not_ready = self.new_service(ready=False)

        cases = {
            "沒有 Trader 身份組": lambda: self.react(post, OUTSIDER),
            "對貼文裡的回覆按": lambda: self.react(post, SUPPLIER, message_id=reply_id),
            "別的論壇": lambda: self.react(other_forum_post, SUPPLIER),
            "不是接單表情": lambda: self.react(post, SUPPLIER, emoji="😂"),
            "bot 自己": lambda: self.react(post, BOT),
            "供應方對自己的需求": lambda: self.react(own_post, SUPPLIER),
            "需求方是別的 bot": lambda: self.react(bot_post, SUPPLIER),
            "上線匯入還沒做完": lambda: self.react(post, SUPPLIER, service=not_ready),
        }
        for label, act in cases.items():
            with self.subTest(label):
                self.assertIsNone(act())
        self.assertEqual(self.world.cart.threads, [])
        self.assertEqual(self.call(self.db.trades()), [])

    def test_each_supplier_gets_own_thread_and_repeat_reaction_reuses_it(self):
        post = self.world.post(REQUESTER, "需要購買2000個PY幣")

        first = self.react(post, SUPPLIER)
        second = self.react(post, SUPPLIER_B)
        again = self.react(post, SUPPLIER, emoji="💰")

        self.assertEqual(len(self.world.cart.threads), 2)
        self.assertEqual(sorted(second.thread.members), sorted([REQUESTER.id, SUPPLIER_B.id]))
        self.assertNotIn(SUPPLIER_B.id, first.thread.members)
        self.assertFalse(again.created)
        self.assertIs(again.thread, first.thread)
        self.assertEqual(first.thread.last().pinged, [SUPPLIER.id])
        self.assertEqual(len(self.call(self.db.trades())), 2)

    def test_repeat_reaction_finds_the_thread_after_it_was_auto_archived(self):
        post = self.world.post(REQUESTER, "需要代儲")
        first = self.react(post, SUPPLIER)
        first.thread.auto_archive()
        self.world.advance(days=40)

        again = self.react(post, SUPPLIER, service=self.new_service())

        self.assertFalse(again.created)
        self.assertIs(again.thread, first.thread)
        self.assertEqual(len(self.world.cart.all_threads), 1)

    def test_failed_opening_leaves_no_thread_and_no_record(self):
        post = self.world.post(REQUESTER, "需要代儲")
        self.world.fail_add_user = True

        with self.assertRaises(discord.HTTPException):
            self.react(post, SUPPLIER)

        self.assertEqual(self.world.cart.all_threads, [])
        self.assertEqual(self.call(self.db.trades()), [])
        self.world.fail_add_user = False
        self.assertTrue(self.react(post, SUPPLIER).created)

    def test_database_failure_deletes_the_new_thread(self):
        post = self.world.post(REQUESTER, "需要代儲")

        with mock.patch.object(MarketDB, "insert_trade", side_effect=RuntimeError("disk full")):
            with self.assertRaises(RuntimeError):
                self.react(post, SUPPLIER)

        self.assertEqual(self.world.cart.all_threads, [])
        self.assertEqual(self.call(self.db.trades()), [])


class ButtonPermissionTests(TradeFlowTestCase):

    def setUp(self):
        super().setUp()
        self.post = self.world.post(REQUESTER, "需要代儲")
        self.thread = self.react(self.post, SUPPLIER).thread

    def test_wrong_person_cannot_press_and_nothing_changes(self):
        ref = self.ref_of(self.thread)
        sent_before = len(self.thread.messages)

        self.press(self.thread, REQUESTER, NOTIFY, ref)
        self.press(self.thread, REQUESTER, CANCEL, ref)
        self.press(self.thread, OUTSIDER, CANCEL_OK, ref)
        self.press(self.thread, SUPPLIER, RECEIVE, ref)
        self.press(self.thread, OUTSIDER, RECEIVE, ref)
        self.press(self.thread, SUPPLIER, HOLD, ref)
        self.press(self.thread, OUTSIDER, HOLD, ref)
        self.press(self.thread, OUTSIDER, HELP, ref)

        self.assertEqual(self.ephemeral.await_count, 8)
        self.assertNotIn(OWNER.id, self.thread.members)
        self.assertEqual(len(self.thread.messages), sent_before)
        self.assertFalse(self.thread.locked)
        self.assertEqual(self.trade_row(self.thread).status, "open")
        self.assertIn(self.post.id, self.world.channels)

    def test_identity_comes_from_the_database_not_the_button(self):
        # 按鈕上寫的供應方是路人：照資料庫，路人還是不能通知，真正的供應方可以
        forged = TradeRef(self.post.id, REQUESTER.id, OUTSIDER.id)

        self.press(self.thread, OUTSIDER, NOTIFY, forged)
        self.assertIn("只有供應方", self.last_reply())
        self.press(self.thread, SUPPLIER, NOTIFY, forged)
        self.assertEqual(self.thread.last().view.actions, (RECEIVE, HOLD, HELP))

    def test_owner_can_cancel(self):
        self.press(self.thread, OWNER, CANCEL)

        self.assertEqual(self.trade_row(self.thread).status, "cancelled")
        self.assertTrue(self.thread.name.startswith("【已取消】"))
        embed = self.dms.await_args.kwargs["embed"]
        self.assertTrue(embed.description.startswith("群主"))

    def test_thread_without_a_record(self):
        stray = FakeThread(self.world, next(self.world.ids), "【交易中】誰 與 誰 - 1", parent_id=CART_ID)

        self.press(stray, SUPPLIER, NOTIFY, TradeRef(1, REQUESTER.id, SUPPLIER.id))

        self.assertIn("找不到這筆交易的紀錄", self.last_reply())
        self.assertEqual(stray.messages, [])

    def test_buttons_wait_for_the_import(self):
        self.press(self.thread, SUPPLIER, NOTIFY, service=self.new_service(ready=False))

        self.assertIn("更新中", self.last_reply())
        self.assertEqual(self.events(self.thread), [tp.OPENED])


class CompleteTests(TradeFlowTestCase):

    def setUp(self):
        super().setUp()
        self.post = self.world.post(REQUESTER, "需要購買2000個PY幣\n幫我換成台幣謝謝")
        self.thread = self.react(self.post, SUPPLIER).thread
        self.other = self.react(self.post, SUPPLIER_B).thread

    def test_notify_then_requester_confirms(self):
        self.press(self.thread, SUPPLIER, NOTIFY)
        request = self.thread.last()
        self.assertEqual(request.pinged, [REQUESTER.id])  # 只 @ 下一步要動手的人
        self.assertEqual(request.view.actions, (RECEIVE, HOLD, HELP))

        self.press(self.thread, REQUESTER, RECEIVE, message=request)

        # 完成訊息在鎖定之前，最後狀態是鎖定且封存
        kinds = [kind for kind, _ in self.thread.events]
        self.assertEqual(kinds[-2:], ["send", "edit"])
        done = self.thread.last()
        self.assertIn("交易完成", done.content)
        self.assertEqual(done.pinged, [])  # 對話裡不 @，改私訊
        self.assertTrue(self.thread.locked)
        self.assertTrue(self.thread.archived)
        self.assertTrue(self.thread.name.startswith("【已完成】"))
        self.assertTrue(self.thread.name.endswith(f" - {self.post.id}"))
        # 做完了按鈕就拿掉（開單訊息、領收通知都是）
        self.assertEqual([m.components for m in self.thread.messages if m.components], [])
        self.assertEqual(self.trade_row(self.thread).status, "completed")
        self.assertEqual(self.events(self.thread),
                         [tp.OPENED, tp.RECEIPT_REQUESTED, tp.COMPLETED, tp.ARCHIVED, tp.NOTIFIED])
        self.assertTrue(self.trade_row(self.thread).wrapped_up)

    def say_in_post(self, author, text):
        self.post.messages.append(FakeMessage(self.world, next(self.world.ids), author, text, thread=self.post))

    def assert_silent(self, kwargs):
        quiet = kwargs["allowed_mentions"]
        self.assertFalse(quiet.everyone or quiet.users or quiet.roles)

    def test_source_is_archived_with_transcript_then_deleted(self):
        self.say_in_post(SUPPLIER, f"{REQUESTER.mention} 收到，晚上處理")
        self.confirm(self.thread)

        self.assertEqual(len(self.world.archived_posts), 1)
        channel, kwargs = self.world.archived_posts[0]
        self.assertIs(channel, self.world.archive)
        self.assertEqual([t.name for t in kwargs["tags"]], ["封存"])
        # 短對話整段寫在貼文裡，打開就看得到，不另附檔
        self.assertIn("需求方：需求者", kwargs["content"])
        self.assertIn("幫我換成台幣謝謝", kwargs["content"])
        self.assertIn("供應者甲: @需求者 收到，晚上處理", kwargs["content"])  # @ 換成名字
        self.assertNotIn("<@", kwargs["content"])
        self.assertFalse(kwargs.get("files"))
        self.assert_silent(kwargs)
        self.assertTrue(self.post.deleted)
        self.assertIn("交易完成。需求貼文已封存。此對話將關閉。", self.thread.sent()[-1])

    def test_long_conversation_goes_to_an_attachment(self):
        for i in range(40):
            self.say_in_post(REQUESTER, f"第{i}則補充：" + "交易細節說明" * 8 + f" {SUPPLIER.mention}")
        self.confirm(self.thread)

        (_, kwargs), = self.world.archived_posts
        # 貼文放摘要（放得進一則訊息），完整對話在附檔；附檔裡也是名字不是 @
        self.assertLessEqual(len(kwargs["content"]), 2000)
        self.assertIn("需求方：需求者", kwargs["content"])
        self.assertIn("見附檔", kwargs["content"])
        text = kwargs["files"][0].fp.getvalue().decode("utf-8")
        self.assertIn("需求方：需求者", text)
        self.assertIn("第0則補充", text)
        self.assertIn("第39則補充", text)
        self.assertIn("@供應者甲", text)
        self.assertNotIn("<@", text)
        self.assert_silent(kwargs)
        self.assertTrue(self.post.deleted)

    def test_oversized_summary_is_cut_but_kept_whole_in_the_attachment(self):
        # 商品留底的摘要是所有下單紀錄，加購很多次時摘要本身就可能超過一則訊息
        summary = "下單紀錄" + "・月相 ×1（NT$30）\n" * 200
        self.assertTrue(self.call(self.service.post_archive(
            title="封存", summary=summary, transcript="[時間] 需求者: 謝謝", filename="record.txt")))

        (_, kwargs), = self.world.archived_posts
        self.assertLessEqual(len(kwargs["content"]), 2000)
        self.assertIn("見附檔", kwargs["content"])
        text = kwargs["files"][0].fp.getvalue().decode("utf-8")
        self.assertIn(summary, text)
        self.assertIn("需求者: 謝謝", text)

    def dm_targets(self):
        return [(call.args[0].id, call.kwargs["embed"]) for call in self.dms.await_args_list]

    def test_both_parties_get_a_dm_with_the_link(self):
        self.confirm(self.thread)

        mine = [(uid, embed) for uid, embed in self.dm_targets() if self.thread.jump_url in embed.fields[-1].value]
        self.assertEqual(sorted(uid for uid, _ in mine), sorted([REQUESTER.id, SUPPLIER.id]))
        self.assertEqual(mine[0][1].title, "交易完成")
        self.assertIn("需求者", mine[0][1].description)
        self.assertNotIn("<@", mine[0][1].description)
        # 因別人成交而結束的那一組也收到私訊，連結是他們自己的對話
        ended = [(uid, embed) for uid, embed in self.dm_targets() if self.other.jump_url in embed.fields[-1].value]
        self.assertEqual(sorted(uid for uid, _ in ended), sorted([REQUESTER.id, SUPPLIER_B.id]))
        self.assertEqual(ended[0][1].title, "交易結束")

    def test_other_suppliers_threads_are_ended(self):
        self.other.auto_archive()  # 另一位供應方那邊三天沒人講話
        self.confirm(self.thread)

        self.assertTrue(self.other.locked)
        self.assertTrue(self.other.archived)
        self.assertTrue(self.other.name.startswith("【已結束】"))
        self.assertEqual([m.components for m in self.other.messages if m.components], [])
        self.assertIn("其他供應方完成", self.other.sent()[-1])
        self.assertEqual(self.trade_row(self.other).status, "ended")

    def test_archive_failure_keeps_the_source(self):
        with mock.patch.object(trade_service, "post_to_channel", side_effect=RuntimeError("boom")):
            self.confirm(self.thread)

        self.assertFalse(self.post.deleted)
        self.assertIn("需求貼文沒能自動封存，請通知管理員。", self.thread.sent()[-1])
        self.assertTrue(self.thread.locked)

    def test_post_outside_the_market_is_never_deleted(self):
        # 保險：刪掉的東西救不回來，只有確定在自由市場裡的貼文才封存、刪除
        self.config["trade_forum_channel_id"] = OTHER_FORUM_ID

        self.confirm(self.thread)

        self.assertTrue(self.thread.locked)
        self.assertFalse(self.post.deleted)
        self.assertEqual(self.world.archived_posts, [])
        self.assertFalse(self.other.locked)

    def test_source_kept_when_delete_fails(self):
        async def refuse():
            raise discord.HTTPException(mock.MagicMock(status=403), "no permission")

        self.post.delete = refuse
        self.confirm(self.thread)

        self.assertEqual(len(self.world.archived_posts), 1)
        self.assertIn("需求貼文沒能自動移除，請通知管理員。", self.thread.sent()[-1])

    def test_a_hiccup_reading_the_request_is_not_taken_as_gone(self):
        # 完成時取需求貼文碰到 Discord 暫時出錯：不能記成「貼文已經不在」（只做一次，貼文就一直開著、還能被接單）
        self.world.channels.pop(self.post.id)

        async def hiccup(channel_id):
            raise discord.HTTPException(mock.MagicMock(status=503), "Service Unavailable")

        self.world.bot.fetch_channel = hiccup
        with self.assertLogs(trade_service.logger, level="ERROR"):
            self.confirm(self.thread)
        self.assertIn("需求貼文沒能自動封存，請通知管理員。", self.thread.sent()[-1])
        (archived,) = [e for e in self.call(self.db.events(self.thread.id)) if e.kind == tp.ARCHIVED]
        self.assertEqual(archived.reference, "failed")

    def test_archive_channel_unset_only_locks_the_source(self):
        del self.config["archive_channel_id"]
        self.confirm(self.thread)

        self.assertTrue(self.post.locked)
        self.assertFalse(self.post.deleted)
        self.assertIn("交易完成。需求貼文已鎖定。此對話將關閉。", self.thread.sent()[-1])

    def test_an_archived_request_is_still_locked(self):
        # 需求貼文放久了會被自動封存，封存中的貼文要先解封才鎖得了
        del self.config["archive_channel_id"]
        self.post.auto_archive()
        self.confirm(self.thread)
        self.assertTrue(self.post.locked)
        self.assertIn("需求貼文已鎖定", self.thread.sent()[-1])

    def test_failing_to_lock_the_source_still_finishes_the_trade(self):
        # 資料庫已經記了完成：需求貼文鎖不了也要把結束訊息、鎖定、私訊、結束其他交易做完，不然對話永遠卡著
        del self.config["archive_channel_id"]

        async def refuse(**kwargs):
            raise discord.HTTPException(mock.MagicMock(status=403), "Missing Permissions")

        self.post.edit = refuse
        with self.assertLogs(trade_service.logger, level="ERROR"):
            self.confirm(self.thread)

        self.assertTrue(self.thread.locked)
        self.assertIn("需求貼文沒能自動鎖定，請通知管理員。", self.thread.sent()[-1])
        self.assertTrue(self.other.locked)
        self.assertEqual(self.trade_row(self.other).status, "ended")
        self.assertTrue(self.dms.await_count >= 2)

    def test_any_failure_with_the_source_still_finishes_the_trade(self):
        with mock.patch.object(TradeService, "_archive_source", side_effect=RuntimeError("讀不到頻道設定")), \
                self.assertLogs(trade_service.logger, level="ERROR"):
            self.confirm(self.thread)
        self.assertTrue(self.thread.locked)
        self.assertIn("需求貼文沒能自動封存，請通知管理員。", self.thread.sent()[-1])

    def test_not_received_on_an_old_notice_says_so(self):
        self.press(self.thread, SUPPLIER, NOTIFY)
        old = self.thread.last()
        self.world.advance(hours=1)
        self.press(self.thread, SUPPLIER, NOTIFY)

        self.press(self.thread, REQUESTER, HOLD, message=old)

        self.assertIn("失效", self.last_reply())   # 不說的話，他以為暫停了，有效的那則還在倒數

    def test_closing_cut_short_by_a_restart_is_finished_later(self):
        self.press(self.thread, SUPPLIER, NOTIFY)
        notice = self.thread.last()
        with mock.patch.object(TradeService, "_finish", side_effect=RuntimeError("停機")), \
                self.assertLogs(trade_service.logger, level="ERROR"):
            self.press(self.thread, REQUESTER, RECEIVE, message=notice)
        self.assertEqual(self.trade_row(self.thread).status, "completed")
        self.assertFalse(self.thread.locked)
        self.assertEqual(len(self.world.archived_posts), 1)

        service = self.new_service()
        self.world.advance(minutes=5)
        self.call(service.run_receipt_deadlines(self.world.now))
        self.assertFalse(self.thread.locked)                       # 剛結束的可能還在做，先不補
        self.world.advance(minutes=10)
        self.call(service.run_receipt_deadlines(self.world.now))

        self.assertTrue(self.thread.locked and self.thread.name.startswith("【已完成】"))
        self.assertEqual(len(self.world.archived_posts), 1)        # 封存做過了不重做
        self.assertTrue(self.other.locked)                         # 同一篇的其他交易也結束
        self.assertTrue(self.trade_row(self.thread).wrapped_up)
        count = len(self.thread.messages)
        self.call(service.run_receipt_deadlines(self.world.now))
        self.assertEqual(len(self.thread.messages), count)

    def test_finished_cancellations_are_not_redone(self):
        self.press(self.thread, SUPPLIER, CANCEL)
        count = len(self.thread.messages)
        self.world.advance(hours=1)
        self.call(self.new_service().run_receipt_deadlines(self.world.now))
        self.assertEqual(len(self.thread.messages), count)
        self.assertTrue(self.trade_row(self.thread).wrapped_up)

    def test_a_notice_recorded_but_never_sent_is_sent_again(self):
        # 領收通知記了、還沒發出去就停機：不能被自動領收（需求方根本沒看到），過一陣子補發一則
        async def record_only():
            async with self.db.transaction():
                await self.db.add_event(self.thread.id, tp.RECEIPT_REQUESTED, now=self.world.now.isoformat(),
                                        actor_id=SUPPLIER.id)
        self.call(record_only())
        self.world.advance(hours=25)

        self.call(self.new_service().run_receipt_deadlines(self.world.now))

        self.assertEqual(self.trade_row(self.thread).status, "open")
        self.assertEqual(self.thread.last().view.actions, (RECEIVE, HOLD, HELP))
        self.world.advance(hours=25)
        self.call(self.service.run_receipt_deadlines(self.world.now))
        self.assertEqual(self.trade_row(self.thread).status, "completed")

    def test_a_notice_that_fails_to_send_is_not_live(self):
        self.thread.fail_send = True
        with self.assertLogs(trade_service.logger, level="ERROR"):
            self.press(self.thread, SUPPLIER, NOTIFY)
        self.thread.fail_send = False
        self.assertIsNone(trade_service.receipt_state(self.call(self.db.events(self.thread.id))).request)

    def test_closing_is_not_marked_done_when_discord_hiccups(self):
        self.press(self.thread, SUPPLIER, NOTIFY)
        notice = self.thread.last()
        with mock.patch.object(TradeService, "_finish", side_effect=RuntimeError("停機")), \
                self.assertLogs(trade_service.logger, level="ERROR"):
            self.press(self.thread, REQUESTER, RECEIVE, message=notice)
        self.world.advance(minutes=15)
        self.world.channels.pop(self.thread.id)

        async def hiccup(channel_id):
            raise discord.HTTPException(mock.MagicMock(status=503), "Service Unavailable")

        self.world.bot.fetch_channel = hiccup
        with self.assertLogs(trade_service.logger, level="ERROR"):
            self.call(self.service.run_receipt_deadlines(self.world.now))
        self.assertFalse(self.trade_row(self.thread).wrapped_up)   # 下一輪再來，不能記成做完

    def test_half_opened_conversations_are_closed(self):
        self.service.orphans_after = self.world.now - timedelta(days=1)
        orphan = FakeThread(self.world, discord.utils.time_snowflake(self.world.now), "【交易中】誰 與 誰 - 1",
                            parent_id=CART_ID, type_=discord.ChannelType.private_thread)
        self.world.cart.all_threads.append(orphan)
        self.world.advance(minutes=3)
        wake = self.call(self.service.run_receipt_deadlines(self.world.now))   # 剛開的可能還在寫：7 分鐘後再來看
        self.assertFalse(orphan.locked)
        self.assertLessEqual(wake, self.world.now + timedelta(minutes=7, seconds=1))
        self.world.advance(minutes=12)

        self.call(self.service.run_receipt_deadlines(self.world.now))

        self.assertTrue(orphan.locked)
        self.assertTrue(orphan.name.startswith("【已取消】"))
        self.assertIn("沒有開成功", orphan.sent()[-1])
        self.assertFalse(self.thread.locked)   # 有紀錄的不動

    def test_a_half_opened_conversation_is_told_once(self):
        # 鎖不起來（例：沒有管理討論串的權限）時下一輪只重試鎖定，不會每輪再發同一句
        self.service.orphans_after = self.world.now - timedelta(days=1)
        orphan = FakeThread(self.world, discord.utils.time_snowflake(self.world.now), "【交易中】誰 與 誰 - 1",
                            parent_id=CART_ID, type_=discord.ChannelType.private_thread)
        self.world.cart.all_threads.append(orphan)

        async def refuse(**kwargs):
            raise discord.Forbidden(mock.MagicMock(status=403), "Missing Permissions")

        orphan.edit = refuse
        for _ in range(3):
            self.world.advance(minutes=15)
            with self.assertLogs(trade_service.logger, level="WARNING"):
                self.call(self.service.run_receipt_deadlines(self.world.now))
        self.assertEqual(sum("沒有開成功" in text for text in orphan.sent()), 1)

    def test_a_notice_cut_off_by_a_shutdown_is_sent_again(self):
        # 停機時連線斷了（不是 Discord 回錯誤）：不知道發出去沒有，留著紀錄，排程補發一則新的
        self.thread.send_error = OSError("connection reset")
        original = FakeThread.send

        async def broken(thread, *args, **kwargs):
            if getattr(thread, "send_error", None):
                raise thread.send_error
            return await original(thread, *args, **kwargs)

        with mock.patch.object(FakeThread, "send", broken), self.assertLogs(trade_service.logger, level="ERROR"):
            self.press(self.thread, SUPPLIER, NOTIFY)
        self.thread.send_error = None
        self.world.advance(minutes=15)

        self.call(self.new_service().run_receipt_deadlines(self.world.now))

        self.assertEqual(self.thread.last().view.actions, (RECEIVE, HOLD, HELP))

    def test_a_resend_that_discord_fumbles_is_tried_again(self):
        # 補發時 Discord 自己出錯（5xx）：一樣不知道發了沒、晚點可能就好了，留著紀錄下一輪再補
        self.thread.send_error = OSError("connection reset")
        original = FakeThread.send

        async def broken(thread, *args, **kwargs):
            if getattr(thread, "send_error", None):
                raise thread.send_error
            return await original(thread, *args, **kwargs)

        with mock.patch.object(FakeThread, "send", broken):
            with self.assertLogs(trade_service.logger, level="ERROR"):
                self.press(self.thread, SUPPLIER, NOTIFY)
            self.world.advance(minutes=15)
            self.thread.send_error = discord.DiscordServerError(mock.MagicMock(status=503), "Service Unavailable")
            with self.assertLogs(trade_service.logger, level="ERROR"):
                self.call(self.new_service().run_receipt_deadlines(self.world.now))
            self.thread.send_error = None
            self.world.advance(minutes=15)
            self.call(self.new_service().run_receipt_deadlines(self.world.now))

        self.assertEqual(self.thread.last().view.actions, (RECEIVE, HOLD, HELP))

    def test_a_notice_discord_refuses_is_dropped(self):
        # Discord 明確拒絕（沒權限）：確定沒發出去、再發也一樣，讓它失效，不會每輪重發
        self.thread.fail_send = True
        with self.assertLogs(trade_service.logger, level="ERROR"):
            self.press(self.thread, SUPPLIER, NOTIFY)
        self.thread.fail_send = False
        self.assertIn(tp.RECEIPT_HELD, self.events(self.thread))

    def test_ending_the_others_waits_out_a_discord_hiccup(self):
        # 結束另一位供應方的對話時一時取不到它：那筆還沒處理，不能記成結束（不然對話沒鎖、雙方也沒收到通知）
        self.world.channels.pop(self.other.id)
        real_fetch = self.world.bot.fetch_channel

        async def hiccup(channel_id):
            if channel_id == self.other.id:
                raise discord.HTTPException(mock.MagicMock(status=503), "Service Unavailable")
            return await real_fetch(channel_id)

        self.world.bot.fetch_channel = hiccup
        with self.assertLogs(trade_service.logger, level="ERROR"):
            self.confirm(self.thread)
        self.assertEqual(self.trade_row(self.other).status, "open")
        self.assertFalse(self.trade_row(self.thread).wrapped_up)

        self.world.channels[self.other.id] = self.other
        self.world.advance(minutes=15)
        self.call(self.service.run_receipt_deadlines(self.world.now))

        self.assertEqual(self.trade_row(self.other).status, "ended")
        self.assertTrue(self.other.locked)
        self.assertTrue(self.trade_row(self.thread).wrapped_up)

    def test_retrying_the_close_does_not_message_the_parties_again(self):
        # 另一位供應方的對話一直取不到：這筆每一輪都要再補一次，但雙方的私訊只發一次
        self.world.channels.pop(self.other.id)
        real_fetch = self.world.bot.fetch_channel

        async def hiccup(channel_id):
            if channel_id == self.other.id:
                raise discord.HTTPException(mock.MagicMock(status=503), "Service Unavailable")
            return await real_fetch(channel_id)

        self.world.bot.fetch_channel = hiccup
        with self.assertLogs(trade_service.logger, level="ERROR"):
            self.confirm(self.thread)
        sent = self.dms.await_count
        for _ in range(2):
            self.world.advance(minutes=15)
            with self.assertLogs(trade_service.logger, level="ERROR"):
                self.call(self.service.run_receipt_deadlines(self.world.now))
        self.assertEqual(self.dms.await_count, sent)
        self.assertFalse(self.trade_row(self.thread).wrapped_up)

    def test_a_request_outside_the_market_stays_that_way_after_a_restart(self):
        # 完成時需求貼文已經不在自由市場（論壇重綁了）：不封存、不結束其他交易；做到一半重啟補收尾也一樣
        self.config["trade_forum_channel_id"] = OTHER_FORUM_ID
        self.press(self.thread, SUPPLIER, NOTIFY)
        notice = self.thread.last()
        with mock.patch.object(TradeService, "_finish", side_effect=RuntimeError("停機")), \
                self.assertLogs(trade_service.logger, level="ERROR"):
            self.press(self.thread, REQUESTER, RECEIVE, message=notice)
        self.world.advance(minutes=15)

        self.call(self.new_service().run_receipt_deadlines(self.world.now))

        self.assertTrue(self.trade_row(self.thread).wrapped_up)
        self.assertEqual(self.trade_row(self.other).status, "open")
        self.assertFalse(self.other.locked)

    def test_the_archive_keeps_the_real_completion_time(self):
        # 完成後封存需求貼文前就停機，隔天才補：封存上寫的是當初完成的時間
        done_at = self.world.now
        self.press(self.thread, SUPPLIER, NOTIFY)
        notice = self.thread.last()
        with mock.patch.object(TradeService, "_archive_once", side_effect=RuntimeError("停機")), \
                self.assertLogs(trade_service.logger, level="ERROR"):
            self.press(self.thread, REQUESTER, RECEIVE, message=notice)
        self.world.advance(days=1)

        self.call(self.new_service().run_receipt_deadlines(self.world.now))

        (_, post), = self.world.archived_posts
        self.assertIn(f"完成時間：{done_at.astimezone(trade_service.APP_TZ):%Y-%m-%d %H:%M}", str(post))

    def test_closing_waits_for_the_other_suppliers_to_end(self):
        failures = ["完成時", "第一輪補做"]
        real = TradeService._end_one

        async def flaky(service, other):
            if failures:
                raise RuntimeError(f"連線斷了（{failures.pop(0)}）")
            return await real(service, other)

        with mock.patch.object(TradeService, "_end_one", flaky), \
                self.assertLogs(trade_service.logger, level="ERROR"):
            self.confirm(self.thread)
            self.assertFalse(self.trade_row(self.thread).wrapped_up)   # 另一位的對話還沒結束：不算收尾完
            self.assertEqual(self.trade_row(self.other).status, "open")
            self.world.advance(minutes=15)
            self.call(self.service.run_receipt_deadlines(self.world.now))
            self.assertFalse(self.trade_row(self.thread).wrapped_up)   # 補做時又壞一次：還是不算

        self.call(self.service.run_receipt_deadlines(self.world.now))

        self.assertEqual(self.trade_row(self.other).status, "ended")
        self.assertTrue(self.trade_row(self.thread).wrapped_up)

    def test_pressing_an_old_notice_does_not_complete(self):
        self.press(self.thread, SUPPLIER, NOTIFY)
        old = self.thread.last()
        self.world.advance(hours=1)
        self.press(self.thread, SUPPLIER, NOTIFY)   # 新通知取代舊的

        self.press(self.thread, REQUESTER, RECEIVE, message=old)

        self.assertIn("失效", self.last_reply())
        self.assertEqual(self.trade_row(self.thread).status, "open")

    def test_notify_after_the_trade_ended_does_not_reopen_it(self):
        self.call(self.service.complete(self.thread, self.thread.id, auto=False))
        count = len(self.thread.messages)

        self.call(self.new_service().notify(self.thread, self.thread.id, actor_id=SUPPLIER.id))

        self.assertEqual(len(self.thread.messages), count)
        self.assertTrue(self.thread.archived)

    def test_pressing_after_the_trade_ended(self):
        ref = self.ref_of(self.thread)
        self.confirm(self.thread)
        count = len(self.thread.messages)

        self.press(self.thread, SUPPLIER, CANCEL, ref)  # 畫面還沒更新、按到已經收掉的按鈕

        self.assertEqual(len(self.thread.messages), count)
        self.assertIn("已經結束", self.last_reply())

    def test_closing_still_finishes_when_discord_fails(self):
        # 資料庫先記完成：完成訊息發不出去，交易照樣算完成，對話照樣鎖起來
        self.press(self.thread, SUPPLIER, NOTIFY)
        notice = self.thread.last()
        self.thread.fail_send = True
        self.press(self.thread, REQUESTER, RECEIVE, message=notice)

        self.assertEqual(self.trade_row(self.thread).status, "completed")
        self.assertTrue(self.thread.locked)


class CancelTests(TradeFlowTestCase):

    def test_supplier_cancels(self):
        post = self.world.post(REQUESTER, "需要代儲")
        thread = self.react(post, SUPPLIER).thread
        post.auto_archive()  # 自由市場一小時沒人講話就封存

        self.press(thread, SUPPLIER, CANCEL)

        self.assertIn("已取消", thread.last().content)
        self.assertEqual(thread.last().pinged, [])
        self.assertEqual([kind for kind, _ in thread.events][-2:], ["send", "edit"])
        self.assertTrue(thread.locked and thread.archived)
        self.assertTrue(thread.name.startswith("【已取消】"))
        self.assertEqual([m.components for m in thread.messages if m.components], [])
        self.assertEqual(self.trade_row(thread).status, "cancelled")
        self.assertFalse(post.deleted)
        removed = post.messages[0].removed_reactions
        self.assertTrue(removed)
        self.assertEqual({uid for _, uid in removed}, {SUPPLIER.id})
        dms = [(call.args[0].id, call.kwargs["embed"]) for call in self.dms.await_args_list]
        self.assertEqual(sorted(uid for uid, _ in dms), sorted([REQUESTER.id, SUPPLIER.id]))
        self.assertTrue(all(e.title == "交易取消" and thread.jump_url in e.fields[-1].value for _, e in dms))
        self.assertTrue(dms[0][1].description.startswith("供應方"))


    def test_a_cancel_cut_short_still_frees_the_supplier_to_accept_again(self):
        # 取消寫進資料庫後、清接單表情前就停機：補收尾時補清，供應方之後才能直接重新接單
        post = self.world.post(REQUESTER, "需要代儲")
        thread = self.react(post, SUPPLIER).thread
        with mock.patch.object(TradeService, "_clear_supplier_reactions", side_effect=RuntimeError("停機")), \
                self.assertLogs(trade_service.logger, level="ERROR"):
            self.press(thread, SUPPLIER, CANCEL)
        self.assertEqual(post.messages[0].removed_reactions, [])
        self.world.advance(minutes=15)

        self.call(self.new_service().run_receipt_deadlines(self.world.now))

        self.assertEqual({uid for _, uid in post.messages[0].removed_reactions}, {SUPPLIER.id})


    def test_a_deleted_conversation_cancels_the_trade(self):
        # 交易對話被刪掉：交易不能永遠停在進行中（取消按鈕也跟著不見了），記成取消並私訊雙方
        from commands import forum_monitor
        self.assertIn("on_raw_thread_delete", [name for name, _ in forum_monitor.ForumMonitor.__cog_listeners__])
        post = self.world.post(REQUESTER, "需要代儲")
        self.world.put_reaction(post, "✅", SUPPLIER)
        thread = self.react(post, SUPPLIER).thread
        self.call(thread.delete())

        self.assertTrue(self.call(self.service.handle_thread_deleted(thread.id)))

        self.assertEqual(self.trade_row(thread).status, "cancelled")
        self.assertIn("交易對話被刪除了", self.dms.await_args.kwargs["embed"].description)
        self.assertFalse(self.call(self.service.handle_thread_deleted(thread.id)))   # 已經處理過

    def test_a_conversation_deleted_while_down_is_found_at_startup(self):
        post = self.world.post(REQUESTER, "需要代儲")
        thread = self.react(post, SUPPLIER).thread
        self.call(thread.delete())   # 停機期間刪掉：收不到刪除事件

        self.call(self.new_service().run_receipt_deadlines(self.world.now))

        self.assertEqual(self.trade_row(thread).status, "cancelled")


class ReceiptDeadlineTests(TradeFlowTestCase):

    def test_auto_complete_after_timeout_even_after_restart(self):
        post = self.world.post(REQUESTER, "需要代儲")
        thread = self.react(post, SUPPLIER).thread
        self.press(thread, SUPPLIER, NOTIFY)
        requested_at = self.world.now

        self.world.advance(hours=23)
        due = self.call(self.service.run_receipt_deadlines(self.world.now))
        self.assertEqual(due, requested_at + timedelta(hours=24))
        self.assertFalse(thread.locked)

        self.world.advance(hours=2)
        restarted = self.new_service()
        due = self.call(restarted.run_receipt_deadlines(self.world.now))

        self.assertIsNone(due)
        self.assertTrue(thread.locked)
        self.assertTrue(thread.name.startswith("【已完成】"))
        self.assertIn("自動視為已領收", thread.sent()[-1])
        self.assertTrue(post.deleted)
        self.assertEqual(self.trade_row(thread).status, "completed")

    def test_waits_for_the_import_before_checking(self):
        post = self.world.post(REQUESTER, "需要代儲")
        thread = self.react(post, SUPPLIER).thread
        self.press(thread, SUPPLIER, NOTIFY)
        self.world.advance(hours=25)

        due = self.call(self.new_service(ready=False).run_receipt_deadlines(self.world.now))

        self.assertEqual(due, self.world.now + timedelta(minutes=1))
        self.assertFalse(thread.locked)

    def test_auto_complete_when_the_thread_was_archived_while_the_bot_was_down(self):
        post = self.world.post(REQUESTER, "需要代儲")
        thread = self.react(post, SUPPLIER).thread
        self.press(thread, SUPPLIER, NOTIFY)
        self.world.advance(days=7)
        thread.auto_archive()
        self.world.advance(days=40)

        self.call(self.new_service().run_receipt_deadlines(self.world.now))

        self.assertTrue(thread.locked)
        self.assertTrue(thread.name.startswith("【已完成】"))

    def test_one_broken_trade_does_not_block_the_others(self):
        broken_post = self.world.post(REQUESTER, "需要代儲")
        post = self.world.post(REQUESTER, "需要代幣")
        broken = self.react(broken_post, SUPPLIER).thread
        thread = self.react(post, SUPPLIER).thread
        self.press(broken, SUPPLIER, NOTIFY)
        self.press(thread, SUPPLIER, NOTIFY)
        self.world.advance(hours=25)
        real = TradeService._archive_source

        async def archive_or_fail(service, trade):
            if trade.id == broken.id:
                raise RuntimeError("壞掉的那一筆")
            return await real(service, trade)

        with mock.patch.object(TradeService, "_archive_source", archive_or_fail):
            with self.assertLogs(trade_service.logger, level="ERROR"):
                self.call(self.service.run_receipt_deadlines(self.world.now))

        self.assertTrue(thread.locked)

    def test_trades_without_a_receipt_request_are_left_alone(self):
        post = self.world.post(REQUESTER, "需要代儲")
        thread = self.react(post, SUPPLIER).thread
        self.world.advance(days=10)

        self.assertIsNone(self.call(self.service.run_receipt_deadlines(self.world.now)))
        self.assertFalse(thread.locked)


class ReceiptProtectionTests(TradeFlowTestCase):

    def setUp(self):
        super().setUp()
        self.post = self.world.post(REQUESTER, "需要代儲")
        self.thread = self.react(self.post, SUPPLIER).thread
        self.press(self.thread, SUPPLIER, NOTIFY)
        self.request = self.thread.last()

    def scan(self, service=None):
        return self.call((service or self.service).run_receipt_deadlines(self.world.now))

    def test_not_received_pauses_auto_receipt_until_notified_again(self):
        self.press(self.thread, REQUESTER, HOLD, message=self.request)

        self.assertEqual(self.request.components, [])
        self.assertIn("暫停", self.request.content)
        self.assertEqual(self.thread.last().pinged, [SUPPLIER.id])
        self.world.advance(days=3)
        self.assertIsNone(self.scan())
        self.assertFalse(self.thread.locked)

        self.press(self.thread, SUPPLIER, NOTIFY)
        self.world.advance(hours=25)
        self.scan()
        self.assertTrue(self.thread.locked)

    def test_hold_on_an_old_notice_does_nothing(self):
        self.world.advance(hours=1)
        self.press(self.thread, SUPPLIER, NOTIFY)
        count = len(self.thread.messages)

        self.press(self.thread, REQUESTER, HOLD, message=self.request)  # 舊通知（按鈕已經拿掉，畫面沒更新）

        self.assertEqual(len(self.thread.messages), count)
        self.world.advance(hours=25)
        self.scan()
        self.assertTrue(self.thread.locked)

    def test_a_new_notice_replaces_the_old_one(self):
        self.world.advance(hours=20)
        self.press(self.thread, SUPPLIER, NOTIFY)
        self.assertEqual(self.request.components, [])

        self.world.advance(hours=5)  # 舊通知已滿 25 小時，新通知才 5 小時
        self.scan()

        self.assertFalse(self.thread.locked)

    def test_requester_is_reminded_once_before_auto_receipt(self):
        due = self.request.created_at + timedelta(hours=24)
        self.world.advance(hours=1)
        self.assertEqual(self.scan(), due - timedelta(hours=6))

        self.world.advance(hours=18)
        self.assertEqual(self.scan(), due)
        reminder = self.thread.last()
        self.assertIn("⏰", reminder.content)
        self.assertEqual(reminder.pinged, [REQUESTER.id])
        count = len(self.thread.messages)

        self.scan()
        self.scan(self.new_service())  # 重啟後也查得到提醒過
        self.assertEqual(len(self.thread.messages), count)
        self.assertFalse(self.thread.locked)

    def test_chat_in_trade_threads_is_noted(self):
        # 交易對話裡有人講話就記進資料庫（看板算幾天沒動靜直接查它）；cog 收到每則訊息都交給交易服務
        from commands import forum_monitor
        self.assertIn("on_message", [name for name, _ in forum_monitor.ForumMonitor.__cog_listeners__])
        self.world.advance(days=2)
        said = FakeMessage(self.world, next(self.world.ids), REQUESTER, "我明天付", thread=self.thread)
        self.call(self.service.note_chat(said))
        self.assertEqual(self.trade_row(self.thread).last_chat_at, self.world.now.isoformat())

    def test_only_trade_conversations_are_noted(self):
        # 伺服器每一則訊息都會進來：不是購物車裡的交易對話就不碰資料庫
        said = FakeMessage(self.world, next(self.world.ids), REQUESTER, "還有人要接嗎", thread=self.post)
        with mock.patch.object(MarketDB, "note_chat", side_effect=AssertionError("不是交易對話，不該寫資料庫")):
            self.call(self.service.note_chat(said))

    def test_help_works_in_a_quiet_archived_thread(self):
        # 等貨的交易可以安靜好幾週，對話早就自動封存；按鈕不會解封，封存中的對話加不了人
        self.thread.auto_archive()
        self.press(self.thread, REQUESTER, HELP)
        self.assertIn(OWNER.id, self.thread.members)
        self.assertEqual(self.thread.last().pinged, [OWNER.id])

    def test_help_brings_the_owner_in_once(self):
        self.press(self.thread, REQUESTER, HELP)

        self.assertIn(OWNER.id, self.thread.members)
        self.assertEqual(self.thread.last().pinged, [OWNER.id])
        count = len(self.thread.messages)

        self.press(self.thread, SUPPLIER, HELP)

        self.assertEqual(len(self.thread.messages), count)
        self.assertIn("已經在", self.last_reply())


class TradeThreadLogTests(TradeFlowTestCase):
    """直接讀一串假的交易對話：開單身分、有效通知、要拿掉按鈕的訊息各自認得對（上線匯入與收按鈕用）。"""

    def setUp(self):
        super().setUp()
        self.ref = TradeRef(500, REQUESTER.id, SUPPLIER.id)
        self.thread = FakeThread(self.world, next(self.world.ids), "【交易中】需求者 與 供應者甲 - 500", parent_id=CART_ID)

    def say(self, author, text="", actions=(), custom_ids=()):
        view = None
        if actions or custom_ids:
            view = SimpleNamespace(custom_ids=[self.ref.custom_id(a) for a in actions] + list(custom_ids))
        message = FakeMessage(self.world, next(self.world.ids), author, text, view=view, thread=self.thread)
        self.thread.messages.append(message)
        return message

    def read(self):
        return self.call(read_trade_thread(self.thread, bot_user_id=BOT.id))

    def test_reads_what_the_trade_is_doing(self):
        opening = self.say(BOT, "開單", (NOTIFY, CANCEL, HELP))
        self.say(REQUESTER, "你好", (RECEIVE,))  # 不是 bot 發的：不算通知
        older = self.say(BOT, "通知（已失效）")  # 按鈕已經拿掉
        newer = self.say(BOT, "通知", (RECEIVE, HOLD, HELP))
        order = self.say(BOT, "🧾 下單", custom_ids=["shop:order:500:1x2"])
        progress = self.say(BOT, "交易進度", custom_ids=["trade:step:confirm_full"])

        log = self.read()

        self.assertEqual(log.ref, self.ref)
        self.assertIs(log.opening(), opening)
        self.assertIs(log.pending_receipt(), newer)
        self.assertEqual(log.active_requests(), [newer])
        self.assertEqual(log.button_messages(), [opening, newer, progress])  # 訂單紀錄不算交易按鈕
        self.assertNotIn(order, log.button_messages())
        self.assertEqual([m.content for m in log.bot_messages()], ["開單", "通知（已失效）", "通知", "🧾 下單", "交易進度"])
        self.assertIsNot(older, log.pending_receipt())

    def test_newest_notice_wins(self):
        self.say(BOT, "開單", (NOTIFY, CANCEL, HELP))
        first = self.say(BOT, "第一次通知", (RECEIVE, HOLD, HELP))
        second = self.say(BOT, "第二次通知", (RECEIVE, HOLD, HELP))
        log = self.read()
        self.assertIs(log.pending_receipt(), second)
        self.assertEqual(log.active_requests(), [second, first])  # 由新到舊

    def test_nothing_to_find(self):
        self.say(REQUESTER, "還沒開單的聊天")
        log = self.read()
        self.assertIsNone(log.ref)
        self.assertIsNone(log.opening())
        self.assertIsNone(log.pending_receipt())
        self.assertEqual(log.button_messages(), [])


class LegacyTradeTests(TradeFlowTestCase):

    LEGACY_TEXT = ("使用者 <@21> 對交易貼文 https://discord.com/channels/1/2/3 有興趣\n"
                   "貼文者為 <@11>\n來源貼文 ID: {source}\n請在這裡確認交易細節。")

    def test_legacy_text_is_recognised_and_old_buttons_follow_the_database(self):
        from commands import forum_monitor

        post = self.world.post(BOT, f"群友 {REQUESTER.mention} 需要購買", mentions=[REQUESTER])
        legacy = FakeThread(self.world, next(self.world.ids), f"交易確認 - 需求者 和 供應者甲 - {post.id}",
                            parent_id=CART_ID)
        message = FakeMessage(self.world, next(self.world.ids), BOT, self.LEGACY_TEXT.format(source=post.id))
        legacy.messages.append(message)
        self.assertEqual(trade_service.legacy_ref_from_text(message.content),
                         TradeRef(post.id, REQUESTER.id, SUPPLIER.id))

        async def imported():
            async with self.db.transaction():
                await self.db.insert_trade(id=legacy.id, source_kind="forum", source_id=post.id,
                                           requester_id=REQUESTER.id, supplier_id=SUPPLIER.id,
                                           now=self.world.now.isoformat(), legacy=True)
        self.call(imported())
        view = forum_monitor.LegacyTransactionView.__new__(forum_monitor.LegacyTransactionView)
        view.cog = SimpleNamespace(trade=self.service)
        self.call(view._forward(self.interaction(SUPPLIER, legacy, message), NOTIFY))

        self.assertEqual(legacy.last().view.actions, (RECEIVE, HOLD, HELP))


class ServerNicknameTests(TradeFlowTestCase):

    def test_names_come_from_the_server_when_the_cache_misses(self):
        # 抓回來的訊息作者只有全域名稱；伺服器暱稱要從成員資料拿
        author = SimpleNamespace(id=REQUESTER.id, display_name="全域名稱", mention=REQUESTER.mention, bot=False)
        post = self.world.post(author, "需要購買2000個PY幣\n幫我換成台幣謝謝")
        self.world.cached = set()

        thread = self.react(post, SUPPLIER, with_member=False).thread
        self.confirm(thread)

        self.assertIn("需求者 與 供應者甲", thread.name)
        _, kwargs = self.world.archived_posts[0]
        self.assertIn("需求方：需求者", kwargs["content"])
        self.assertIn("供應方：供應者甲", kwargs["content"])
        self.assertIn("需求者: 需要購買", kwargs["content"])
        self.assertNotIn("全域名稱", kwargs["content"])
        self.assertIn(REQUESTER.id, self.world.api_lookups)
        self.assertIn(SUPPLIER.id, self.world.api_lookups)

    def test_member_who_left_the_server_is_logged(self):
        post = self.world.post(REQUESTER, "需要代儲")
        self.world.cached = set()
        del self.world.members[REQUESTER.id]

        with self.assertLogs("utils.discord_members", level="WARNING"):   # 取成員收成一份，log 在那裡
            self.assertIsNone(self.react(post, SUPPLIER))
        self.assertEqual(self.world.cart.all_threads, [])


class NamingTests(unittest.TestCase):

    def test_custom_id_round_trip(self):
        ref = TradeRef(1466085282771239230, 430244604688990212, 770544230685999124)
        for action in (NOTIFY, CANCEL, CANCEL_OK, KEEP, RECEIVE, HOLD, HELP):
            custom_id = ref.custom_id(action)
            self.assertLessEqual(len(custom_id), 100)  # Discord custom_id 上限
            self.assertEqual(trade_service.parse_custom_id(custom_id), (action, ref))

    def test_closed_title_does_not_stack_prefixes(self):
        once = trade_service.closed_title("【交易中】甲 與 乙 - 123", trade_service.CANCELLED_PREFIX)
        self.assertEqual(trade_service.closed_title(once, trade_service.CANCELLED_PREFIX), once)

    def test_closed_title_keeps_the_source_id(self):
        long_name = "很長的名字" * 30
        title = trade_service.open_title(long_name, long_name, 123)
        self.assertLessEqual(len(title), 100)
        closed = trade_service.closed_title(title, trade_service.COMPLETED_PREFIX)
        self.assertTrue(closed.startswith("【已完成】"))
        self.assertTrue(closed.endswith(" - 123"))
        self.assertLessEqual(len(closed), 100)


class WordingTests(TradeFlowTestCase):

    def test_messages_say_conversation_not_thread(self):
        post = self.world.post(REQUESTER, "需要代儲")
        mine = self.react(post, SUPPLIER).thread
        other = self.react(post, SUPPLIER_B).thread
        self.react(post, SUPPLIER)  # 同一位再按一次：提醒交易還在進行中
        self.press(mine, REQUESTER, HELP)
        self.press(mine, SUPPLIER, HELP)  # 群主已經在裡面
        self.confirm(mine)  # 完成，另一位供應方的交易跟著結束
        later = self.world.post(REQUESTER, "需要代練")
        cancelled = self.react(later, SUPPLIER).thread
        self.press(cancelled, SUPPLIER, CANCEL)

        said = [text for t in (mine, other, cancelled) for text in t.sent()]
        said += [call.args[1] for call in self.ephemeral.await_args_list]
        said += [call.kwargs["embed"].description for call in self.dms.await_args_list]
        self.assertTrue(any("群主已經在這個對話裡" in text for text in said))
        self.assertTrue(any("還在進行中" in text for text in said))
        self.assertEqual([text for text in said if "thread" in text.lower()], [])


class LayeringTests(unittest.TestCase):

    def test_trade_service_does_not_import_commands(self):
        tree = ast.parse(Path(trade_service.__file__).read_text(encoding="utf-8"))
        modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                modules.add(node.module)
            elif isinstance(node, ast.Import):
                modules.update(alias.name for alias in node.names)
        self.assertFalse([m for m in modules if m.split(".")[0] == "commands"])

    def test_buttons_from_the_cog_resolve_back_to_the_action(self):
        from commands import forum_monitor

        ref = TradeRef(5, 6, 7)
        actions = (NOTIFY, CANCEL, CANCEL_OK, KEEP)
        view = forum_monitor.make_trade_view(ref, actions)
        buttons = [child for child in view.children]
        self.assertEqual(len(buttons), len(actions))
        for button, action in zip(buttons, actions):
            match = forum_monitor.TradeButton.__discord_ui_compiled_template__.fullmatch(button.custom_id)
            restored = asyncio.run(forum_monitor.TradeButton.from_custom_id(None, None, match))
            self.assertEqual((restored.action, restored.ref), (action, ref))

    def test_cog_hands_its_view_factory_to_the_service(self):
        from commands import forum_monitor

        cog = forum_monitor.ForumMonitor(mock.MagicMock())
        self.assertIs(cog.trade._make_view, forum_monitor.make_trade_view)


if __name__ == "__main__":
    unittest.main()
