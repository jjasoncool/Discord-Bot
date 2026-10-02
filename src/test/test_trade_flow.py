"""交易流程（services.community.trade_service ＋ commands.forum_monitor）。

守的底線：
  1. 接單：供應方（Trader）對自由市場貼文本身按接單表情，就在購物車開私人 thread（不可邀請），
     只加入需求方與這位供應方，開單訊息 @ 雙方。需求方是誰：自己發的貼文是作者，
     /select_item 由 bot 代發的是內文被 @ 的人。開單做到一半失敗不留下沒有按鈕的 thread。
  2. 不開單：沒有 Trader 身份組、對貼文裡的回覆按、別的論壇、不是接單表情、bot 自己、
     供應方對自己的需求按、需求方是別的 bot。
  3. 同一篇需求，每位供應方各開一個 thread；同一位再按不重開，只在原 thread 提醒——
     即使那個 thread 已經被 Discord 自動封存（封存後就不在 discord.py 的快取裡）。
  4. 按鈕各有其人：只有供應方能通知領收與取消，只有需求方能按已領收；別人按不改變任何狀態。
  5. 完成：先發完成訊息再鎖定（反過來 thread 會被重新打開），標題改成【已完成】；
     需求貼文的對話以附檔封存後刪除原貼文（封存失敗就保留、刪除失敗要說）；同一篇的其他
     供應方 thread @ 雙方後結束，已被自動封存的也一樣。結束後再按通知不會把 thread 打開。
  6. 取消：標題【已取消】並鎖定；需求貼文保留；只清掉這位供應方的接單表情（需求貼文
     已被自動封存也清得掉）。
  7. 領收期限：通知後滿 24 小時沒確認就自動完成；期限從 Discord 上的訊息時間推算，
     重啟（新的服務實例、沒有任何記憶體狀態）後照樣補做，停機期間 thread 被自動封存也一樣。
     保護需求方（TR-Q18）：按「還沒領收」就暫停，等供應方再通知才重新計時；新通知讓舊通知失效；
     到期前 @ 需求方提醒一次，提醒過的記號在 Discord 上，重啟也不會重複提醒。
     有爭議時雙方都能請群主（伺服器擁有者）進 thread，只會請一次（TR-Q19）。
  8. 改版前的舊交易 thread：舊文字讀得回交易身分，舊按鈕走同一套流程。
  9. 分層：交易模組不 import 指令層；介面層的按鈕 custom_id 解析得回同一筆交易。
 10. 名字一律是伺服器暱稱：成員快取拿不到人時向 Discord API 查（2025-07 b456d91 的教訓：
     只看快取曾經讓接單失敗）。thread 標題、封存摘要、封存附檔的對話者都一樣；查不到要留 log。
"""

import ast
import asyncio
import itertools
import os
import sys
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

from services.community import trade_service  # noqa: E402
from services.community.trade_service import (  # noqa: E402
    CANCEL,
    HELP,
    HOLD,
    NOTIFY,
    RECEIVE,
    TradeRef,
    TradeService,
)

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
    def __init__(self, world, mid, author, content="", *, mentions=(), view=None, embed=None, thread=None):
        self.id = mid
        self.thread = thread
        self.author = author
        self.content = content or ""
        self.mentions = list(mentions)
        self.embed = embed
        self.view = view
        self.created_at = world.now
        self.attachments = []
        self._set_view(view)
        self.reactions = []
        self.removed_reactions = []

    def _set_view(self, view):
        self.view = view
        self.components = []
        if view is not None:
            self.components = [SimpleNamespace(children=[SimpleNamespace(custom_id=c) for c in view.custom_ids])]

    async def edit(self, *, content=None, view="unchanged"):
        if content is not None:
            self.content = content
        if view != "unchanged":
            self._set_view(view)

    async def add_reaction(self, emoji):
        self.reactions.append(SimpleNamespace(emoji=emoji, me=True))

    async def remove_reaction(self, emoji, user):
        # 對封存中的 thread 改反應會被 Discord 拒絕
        if self.thread is not None and self.thread.archived:
            raise discord.HTTPException(mock.MagicMock(status=400), "Thread is archived")
        self.removed_reactions.append((emoji, user.id))


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
        self.events = []  # ("send", 內容) / ("edit", kwargs)，用來檢查先後順序

    async def send(self, content=None, *, embed=None, view=None):
        # 跟 Discord 一樣：對已封存的 thread 發訊息會把它重新打開
        self.archived = False
        msg = FakeMessage(self.world, next(self.world.ids), BOT, content, view=view, embed=embed, thread=self)
        self.messages.append(msg)
        self.events.append(("send", content))
        return msg

    async def edit(self, **kwargs):
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
        self.members.append(user.id)

    async def fetch_message(self, mid):
        return next(m for m in self.messages if m.id == mid)

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


class FakeCart:
    def __init__(self, world, cid):
        self.world = world
        self.id = cid
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


class TradeFlowTestCase(unittest.TestCase):
    def setUp(self):
        self.world = World()
        config = {
            "trade_forum_channel_id": FORUM_ID,
            "cart_delivery_channel_id": CART_ID,
            "archive_channel_id": ARCHIVE_ID,
        }

        async def get_channel_id(key, *args, **kwargs):
            return config.get(key, trade_service.ChannelConfig.DEFAULT_ID)

        async def check_role(member, role):
            return role == "Trader" and member.id in TRADERS

        async def post_to_channel(channel, **kwargs):
            self.world.archived_posts.append((channel, kwargs))
            return SimpleNamespace(id=next(self.world.ids))

        self.ephemeral = mock.AsyncMock(name="safe_send_interaction_message")
        patches = [
            mock.patch.object(trade_service.ChannelConfig, "get_channel_id", side_effect=get_channel_id),
            mock.patch.object(trade_service, "check_role", side_effect=check_role),
            mock.patch.object(trade_service, "post_to_channel", side_effect=post_to_channel),
            mock.patch.object(trade_service, "safe_send_interaction_message", self.ephemeral),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.service = self.new_service()

    def new_service(self):
        """新的服務實例＝模擬 bot 重啟：記憶體裡什麼都沒有，只剩 Discord 上的東西。"""
        return TradeService(self.world.bot, make_view=_make_view)

    def call(self, coro):
        return asyncio.run(coro)

    def react(self, post, user, emoji="✅", *, message_id=None, with_member=True):
        payload = SimpleNamespace(
            emoji=emoji, guild_id=GUILD_ID, channel_id=post.id,
            message_id=post.id if message_id is None else message_id,
            user_id=user.id, member=user if with_member else None,
        )
        return self.call(self.service.handle_reaction(payload))

    def press(self, thread, user, action, ref, *, message=None):
        interaction = SimpleNamespace(
            user=user, channel=thread, message=message,
            response=SimpleNamespace(is_done=lambda: False, defer=mock.AsyncMock()),
        )
        self.call(self.service.handle_button(interaction, action, ref))
        return interaction

    def opening(self, thread):
        return thread.messages[0]

    def ref_of(self, thread):
        return TradeRef(*map(int, self.opening(thread).view.custom_ids[0].split(":")[2:]))


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
        self.assertIn(REQUESTER.mention, first.content)
        self.assertIn(SUPPLIER.mention, first.content)
        self.assertEqual(first.view.actions, (NOTIFY, CANCEL, HELP))
        self.assertEqual(self.ref_of(thread), TradeRef(post.id, REQUESTER.id, SUPPLIER.id))

    def test_bot_post_requester_is_the_mentioned_member(self):
        post = self.world.post(BOT, f"群友 {REQUESTER.mention} 需要購買：\n1 個 60月相", mentions=[REQUESTER])

        opened = self.react(post, SUPPLIER)

        self.assertEqual(self.ref_of(opened.thread).requester_id, REQUESTER.id)

    def test_reactions_that_do_not_open_a_trade(self):
        post = self.world.post(REQUESTER, "需要代儲")
        other_forum_post = self.world.post(REQUESTER, "別的論壇", forum_id=OTHER_FORUM_ID)
        own_post = self.world.post(SUPPLIER, "供應方自己的需求")
        bot_post = self.world.post(OTHER_BOT, "別的 bot 發的")
        reply_id = next(self.world.ids)
        post.messages.append(FakeMessage(self.world, reply_id, REQUESTER, "補充說明"))

        cases = {
            "沒有 Trader 身份組": lambda: self.react(post, OUTSIDER),
            "對貼文裡的回覆按": lambda: self.react(post, SUPPLIER, message_id=reply_id),
            "別的論壇": lambda: self.react(other_forum_post, SUPPLIER),
            "不是接單表情": lambda: self.react(post, SUPPLIER, emoji="😂"),
            "bot 自己": lambda: self.react(post, BOT),
            "供應方對自己的需求": lambda: self.react(own_post, SUPPLIER),
            "需求方是別的 bot": lambda: self.react(bot_post, SUPPLIER),
        }
        for label, act in cases.items():
            with self.subTest(label):
                self.assertIsNone(act())
        self.assertEqual(self.world.cart.threads, [])

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
        self.assertIn(SUPPLIER.mention, first.thread.sent()[-1])

    def test_repeat_reaction_finds_the_thread_after_it_was_auto_archived(self):
        post = self.world.post(REQUESTER, "需要代儲")
        first = self.react(post, SUPPLIER)
        first.thread.auto_archive()
        self.world.advance(days=8)

        again = self.react(post, SUPPLIER)

        self.assertFalse(again.created)
        self.assertIs(again.thread, first.thread)
        self.assertEqual(len(self.world.cart.all_threads), 1)

    def test_failed_opening_leaves_no_thread_behind(self):
        post = self.world.post(REQUESTER, "需要代儲")
        self.world.fail_add_user = True

        with self.assertRaises(discord.HTTPException):
            self.react(post, SUPPLIER)

        self.assertEqual(self.world.cart.all_threads, [])
        self.world.fail_add_user = False
        self.assertTrue(self.react(post, SUPPLIER).created)


class ButtonPermissionTests(TradeFlowTestCase):

    def test_wrong_person_cannot_press_and_nothing_changes(self):
        post = self.world.post(REQUESTER, "需要代儲")
        thread = self.react(post, SUPPLIER).thread
        ref = self.ref_of(thread)
        sent_before = len(thread.messages)

        self.press(thread, REQUESTER, NOTIFY, ref)
        self.press(thread, REQUESTER, CANCEL, ref)
        self.press(thread, SUPPLIER, RECEIVE, ref)
        self.press(thread, OUTSIDER, RECEIVE, ref)
        self.press(thread, SUPPLIER, HOLD, ref)
        self.press(thread, OUTSIDER, HOLD, ref)
        self.press(thread, OUTSIDER, HELP, ref)

        self.assertEqual(self.ephemeral.await_count, 7)
        self.assertNotIn(OWNER.id, thread.members)
        self.assertEqual(len(thread.messages), sent_before)
        self.assertFalse(thread.locked)
        self.assertIn(post.id, self.world.channels)


class CompleteTests(TradeFlowTestCase):

    def setUp(self):
        super().setUp()
        self.post = self.world.post(REQUESTER, "需要購買2000個PY幣\n幫我換成台幣謝謝")
        self.thread = self.react(self.post, SUPPLIER).thread
        self.other = self.react(self.post, SUPPLIER_B).thread
        self.ref = self.ref_of(self.thread)

    def test_notify_then_requester_confirms(self):
        self.press(self.thread, SUPPLIER, NOTIFY, self.ref)
        request = self.thread.messages[-1]
        self.assertIn(REQUESTER.mention, request.content)
        self.assertEqual(request.view.actions, (RECEIVE, HOLD, HELP))

        self.press(self.thread, REQUESTER, RECEIVE, self.ref)

        # 完成訊息在鎖定之前，最後狀態是鎖定且封存
        kinds = [kind for kind, _ in self.thread.events]
        self.assertEqual(kinds[-2:], ["send", "edit"])
        self.assertIn("交易完成", self.thread.sent()[-1])
        self.assertTrue(self.thread.locked)
        self.assertTrue(self.thread.archived)
        self.assertTrue(self.thread.name.startswith("【已完成】"))
        self.assertTrue(self.thread.name.endswith(f" - {self.post.id}"))

    def test_source_is_archived_with_transcript_then_deleted(self):
        self.press(self.thread, REQUESTER, RECEIVE, self.ref)

        self.assertEqual(len(self.world.archived_posts), 1)
        channel, kwargs = self.world.archived_posts[0]
        self.assertIs(channel, self.world.archive)
        self.assertEqual([t.name for t in kwargs["tags"]], ["封存"])
        transcript = kwargs["files"][0].fp.getvalue().decode("utf-8")
        self.assertIn("幫我換成台幣謝謝", transcript)
        self.assertNotIn(REQUESTER.mention, kwargs["content"])  # 封存貼文不 @ 人
        self.assertTrue(self.post.deleted)

    def test_other_suppliers_threads_are_ended(self):
        self.other.auto_archive()  # 另一位供應方那邊三天沒人講話
        self.press(self.thread, REQUESTER, RECEIVE, self.ref)

        self.assertTrue(self.other.locked)
        self.assertTrue(self.other.archived)
        self.assertTrue(self.other.name.startswith("【已結束】"))
        notice = self.other.sent()[-1]
        self.assertIn(REQUESTER.mention, notice)
        self.assertIn(SUPPLIER_B.mention, notice)

    def test_archive_failure_keeps_the_source(self):
        with mock.patch.object(trade_service, "post_to_channel", side_effect=RuntimeError("boom")):
            self.press(self.thread, REQUESTER, RECEIVE, self.ref)

        self.assertFalse(self.post.deleted)
        self.assertIn("封存失敗", self.thread.sent()[-1])
        self.assertTrue(self.thread.locked)

    def test_source_kept_when_delete_fails(self):
        async def refuse():
            raise discord.HTTPException(mock.MagicMock(status=403), "no permission")

        self.post.delete = refuse
        self.press(self.thread, REQUESTER, RECEIVE, self.ref)

        self.assertEqual(len(self.world.archived_posts), 1)
        self.assertIn("刪除原貼文失敗", self.thread.sent()[-1])

    def test_notify_after_the_trade_ended_does_not_reopen_it(self):
        self.call(self.service.complete(self.thread, self.ref, auto=False))
        count = len(self.thread.messages)

        self.call(self.service.request_receipt(self.thread, self.ref))

        self.assertEqual(len(self.thread.messages), count)
        self.assertTrue(self.thread.archived)

    def test_pressing_after_the_trade_ended(self):
        self.press(self.thread, REQUESTER, RECEIVE, self.ref)
        count = len(self.thread.messages)

        self.press(self.thread, SUPPLIER, CANCEL, self.ref)

        self.assertEqual(len(self.thread.messages), count)
        self.assertIn("已經結束", self.ephemeral.await_args.args[1])


class CancelTests(TradeFlowTestCase):

    def test_supplier_cancels(self):
        post = self.world.post(REQUESTER, "需要代儲")
        thread = self.react(post, SUPPLIER).thread
        ref = self.ref_of(thread)
        post.auto_archive()  # 自由市場一小時沒人講話就封存

        self.press(thread, SUPPLIER, CANCEL, ref)

        self.assertIn(REQUESTER.mention, thread.sent()[-1])
        self.assertEqual([kind for kind, _ in thread.events][-2:], ["send", "edit"])
        self.assertTrue(thread.locked and thread.archived)
        self.assertTrue(thread.name.startswith("【已取消】"))
        self.assertFalse(post.deleted)
        removed = post.messages[0].removed_reactions
        self.assertTrue(removed)
        self.assertEqual({uid for _, uid in removed}, {SUPPLIER.id})


class ReceiptDeadlineTests(TradeFlowTestCase):

    def test_auto_complete_after_timeout_even_after_restart(self):
        post = self.world.post(REQUESTER, "需要代儲")
        thread = self.react(post, SUPPLIER).thread
        self.press(thread, SUPPLIER, NOTIFY, self.ref_of(thread))
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

    def test_auto_complete_when_the_thread_was_archived_while_the_bot_was_down(self):
        post = self.world.post(REQUESTER, "需要代儲")
        thread = self.react(post, SUPPLIER).thread
        self.press(thread, SUPPLIER, NOTIFY, self.ref_of(thread))
        self.world.advance(days=7)
        thread.auto_archive()
        self.world.advance(days=1)

        self.call(self.new_service().run_receipt_deadlines(self.world.now))

        self.assertTrue(thread.locked)
        self.assertTrue(thread.name.startswith("【已完成】"))

    def test_one_unreadable_thread_does_not_block_the_others(self):
        broken_post = self.world.post(REQUESTER, "需要代儲")
        post = self.world.post(REQUESTER, "需要代幣")
        broken = self.react(broken_post, SUPPLIER).thread
        thread = self.react(post, SUPPLIER).thread
        self.press(thread, SUPPLIER, NOTIFY, self.ref_of(thread))

        async def unreadable(*args, **kwargs):
            raise discord.HTTPException(mock.MagicMock(status=500), "history failed")
            yield  # pragma: no cover — 讓它是 async generator

        broken.history = unreadable
        self.world.advance(hours=25)
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
        self.ref = self.ref_of(self.thread)
        self.press(self.thread, SUPPLIER, NOTIFY, self.ref)
        self.request = self.thread.messages[-1]

    def scan(self, service=None):
        return self.call((service or self.service).run_receipt_deadlines(self.world.now))

    def test_not_received_pauses_auto_receipt_until_notified_again(self):
        self.press(self.thread, REQUESTER, HOLD, self.ref, message=self.request)

        self.assertEqual(self.request.components, [])
        self.assertIn("暫停", self.request.content)
        self.assertIn(SUPPLIER.mention, self.thread.sent()[-1])
        self.world.advance(days=3)
        self.assertIsNone(self.scan())
        self.assertFalse(self.thread.locked)

        self.press(self.thread, SUPPLIER, NOTIFY, self.ref)
        self.world.advance(hours=25)
        self.scan()
        self.assertTrue(self.thread.locked)

    def test_a_new_notice_replaces_the_old_one(self):
        self.world.advance(hours=20)
        self.press(self.thread, SUPPLIER, NOTIFY, self.ref)
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
        reminder = self.thread.sent()[-1]
        self.assertIn("⏰", reminder)
        self.assertIn(REQUESTER.mention, reminder)
        count = len(self.thread.messages)

        self.scan()
        self.scan(self.new_service())  # 重啟後也看得到提醒過的記號
        self.assertEqual(len(self.thread.messages), count)
        self.assertFalse(self.thread.locked)

    def test_help_brings_the_owner_in_once(self):
        self.press(self.thread, REQUESTER, HELP, self.ref)

        self.assertIn(OWNER.id, self.thread.members)
        self.assertIn(OWNER.mention, self.thread.sent()[-1])
        count = len(self.thread.messages)

        self.press(self.thread, SUPPLIER, HELP, self.ref)

        self.assertEqual(len(self.thread.messages), count)
        self.assertIn("已經在", self.ephemeral.await_args.args[1])


class LegacyTradeTests(TradeFlowTestCase):

    LEGACY_TEXT = ("使用者 <@21> 對交易貼文 https://discord.com/channels/1/2/3 有興趣\n"
                   "貼文者為 <@11>\n來源貼文 ID: {source}\n請在這裡確認交易細節。")

    def test_legacy_text_and_thread_are_recognised(self):
        post = self.world.post(BOT, f"群友 {REQUESTER.mention} 需要購買", mentions=[REQUESTER])
        legacy = FakeThread(self.world, next(self.world.ids), f"交易確認 - 需求者 和 供應者甲 - {post.id}",
                            parent_id=CART_ID)
        legacy.messages.append(FakeMessage(self.world, next(self.world.ids), BOT,
                                           self.LEGACY_TEXT.format(source=post.id)))
        self.world.cart.all_threads.append(legacy)

        self.assertEqual(trade_service.legacy_ref_from_text(legacy.messages[0].content),
                         TradeRef(post.id, REQUESTER.id, SUPPLIER.id))
        again = self.react(post, SUPPLIER)

        self.assertFalse(again.created)
        self.assertIs(again.thread, legacy)


class ServerNicknameTests(TradeFlowTestCase):

    def test_names_come_from_the_server_when_the_cache_misses(self):
        # 抓回來的訊息作者只有全域名稱；伺服器暱稱要從成員資料拿
        author = SimpleNamespace(id=REQUESTER.id, display_name="全域名稱", mention=REQUESTER.mention, bot=False)
        post = self.world.post(author, "需要購買2000個PY幣\n幫我換成台幣謝謝")
        self.world.cached = set()

        thread = self.react(post, SUPPLIER, with_member=False).thread
        self.press(thread, REQUESTER, RECEIVE, self.ref_of(thread))

        self.assertIn("需求者 與 供應者甲", thread.name)
        _, kwargs = self.world.archived_posts[0]
        self.assertIn("需求方：需求者", kwargs["content"])
        self.assertIn("供應方：供應者甲", kwargs["content"])
        transcript = kwargs["files"][0].fp.getvalue().decode("utf-8")
        self.assertIn("需求者: 需要購買", transcript)
        self.assertNotIn("全域名稱", transcript)
        self.assertIn(REQUESTER.id, self.world.api_lookups)
        self.assertIn(SUPPLIER.id, self.world.api_lookups)

    def test_member_who_left_the_server_is_logged(self):
        post = self.world.post(REQUESTER, "需要代儲")
        self.world.cached = set()
        del self.world.members[REQUESTER.id]

        with self.assertLogs(trade_service.logger, level="WARNING"):
            self.assertIsNone(self.react(post, SUPPLIER))
        self.assertEqual(self.world.cart.all_threads, [])


class NamingTests(unittest.TestCase):

    def test_custom_id_round_trip(self):
        ref = TradeRef(1466085282771239230, 430244604688990212, 770544230685999124)
        for action in (NOTIFY, CANCEL, RECEIVE):
            custom_id = ref.custom_id(action)
            self.assertLessEqual(len(custom_id), 100)  # Discord custom_id 上限
            self.assertEqual(trade_service.parse_custom_id(custom_id), (action, ref))

    def test_closed_title_keeps_the_source_id(self):
        long_name = "很長的名字" * 30
        title = trade_service.open_title(long_name, long_name, 123)
        self.assertLessEqual(len(title), 100)
        closed = trade_service.closed_title(title, trade_service.COMPLETED_PREFIX)
        self.assertTrue(closed.startswith("【已完成】"))
        self.assertTrue(closed.endswith(" - 123"))
        self.assertLessEqual(len(closed), 100)


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

    def test_buttons_from_the_cog_resolve_back_to_the_trade(self):
        from commands import forum_monitor

        ref = TradeRef(5, 6, 7)
        view = forum_monitor.make_trade_view(ref, (NOTIFY, CANCEL))
        buttons = [child for child in view.children]
        self.assertEqual(len(buttons), 2)
        for button, action in zip(buttons, (NOTIFY, CANCEL)):
            match = forum_monitor.TradeButton.__discord_ui_compiled_template__.fullmatch(button.custom_id)
            restored = asyncio.run(forum_monitor.TradeButton.from_custom_id(None, None, match))
            self.assertEqual((restored.action, restored.ref), (action, ref))

    def test_cog_hands_its_view_factory_to_the_service(self):
        from commands import forum_monitor

        cog = forum_monitor.ForumMonitor(mock.MagicMock())
        self.assertIs(cog.trade._make_view, forum_monitor.make_trade_view)


if __name__ == "__main__":
    unittest.main()
