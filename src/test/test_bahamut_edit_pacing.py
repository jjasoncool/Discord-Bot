"""巴哈轉發：更新已轉發的討論串時，編輯要自己排隊、只編有變的訊息（services.relay.bahamut_monitor）。

守的底線：
  1. 同一個討論串裡，兩次編輯至少間隔 THREAD_EDIT_INTERVAL。Discord 對編輯舊訊息有未公開的較嚴限速
     （實測同一串約 5 秒只能編一則），不自己排隊就會每則都先吃 429 再等。
     間隔從真正編完起算（discord.py 吃到 429 會自己等完重試）；被拒絕的編輯（討論串已封存）不佔名額。
  2. 不同討論串各自排隊，不互相等待。
  3. 只編內容有變的訊息、有變的一定編：同一份資料再來一輪不編任何訊息；剛建好的串第一輪就有新留言，
     留言格也要更新（曾經只記下 hash 不編，新留言要等下一次有變動才出現）；溢出格（建串時或更新時開的）也一樣。
  4. 續文（主文／回覆太長切出來的後續訊息）：只有推噓數變時不編；後段內文改了只編那一則；
     每則續文（最後一則除外）底部都有「⬇️ 更多內文」連到下一則——切到滿也塞得下，
     被舊版重編洗掉的下一輪補回；續文變多、變少再變多，順著連結都讀得到最後一行，
     多出來的改成「此段已更新移除」，之後再變多時重新用上。
  5. 本文（主文／回覆）被切斷時，底部也有「⬇️ 更多內文」連到第一則續文，讀者從本文就讀得到全文
     （改文變長時新續文在串尾）。連結算進 hash，同一份資料再來一輪不會被判定有變；
     建立當下補連結失敗就記沒連結的版本、下一輪補；套用前建的長文只補一次；改回短的就拿掉。
  6. 封存的討論串不去編（一定被拒），等有新回覆時先解除封存再一起補上；更新時新增的回覆編號接續正確。

Discord 以假物件取代；StateDB 用暫存目錄裡的新檔案，不碰正式資料。
"""

import asyncio
import itertools
import os
import re
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import discord

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import services.relay.bahamut_monitor as bm  # noqa: E402
from services.relay.bahamut_monitor import BahamutMonitor  # noqa: E402
from services.state_db import StateDB  # noqa: E402
from utils.discord_content import content_hash  # noqa: E402

FORUM_ID = 900
GUILD_ID = 1_276_158_258_503_094_400
# 測試用的間隔：真實值是秒級，測試縮短，只驗「有排隊」
INTERVAL = 0.2
# 斷言「不超過多久」的測試用較長間隔：完整測試也是啟動 gate，機器忙時不能誤紅
SLACK_INTERVAL = 0.5
# 計時誤差容許
EPS = 0.02

# 長得像 Discord snowflake（19 位數），導航連結的長度才跟正式環境一樣
_ids = itertools.count(1_555_000_000_000_000_000)


class _Message:
    def __init__(self, channel, embed):
        self.id = next(_ids)
        self.channel = channel
        self.embeds = [embed] if embed is not None else []

    async def edit(self, *, embed=None, **_):
        thread = self.channel
        thread.edit_attempts += 1
        if thread.rejects_edits or thread.archived:
            raise RuntimeError("400 Bad Request (error code: 50083): Thread is archived")
        thread.edit_log.append((time.monotonic(), thread.id, self.id))
        # 模擬 discord.py 吃到 429 後自己等完再重試：呼叫端要等這麼久才拿到結果
        await asyncio.sleep(thread.edit_takes)
        thread.edit_done_at[self.id] = time.monotonic()
        self.embeds = [embed]


class _Thread:
    """論壇討論串：記住每則訊息，編輯時記下時間、哪個串、哪則訊息。"""

    def __init__(self, edit_log):
        self.id = next(_ids)
        self.guild = SimpleNamespace(id=GUILD_ID)
        self.messages = {}
        self.edit_log = edit_log
        self.edit_done_at = {}
        self.edit_takes = 0
        self.edit_attempts = 0
        self.rejects_edits = False
        self.archived = False

    def add(self, embed):
        msg = _Message(self, embed)
        self.messages[msg.id] = msg
        return msg

    async def send(self, content=None, embed=None, files=None, reference=None):
        # Discord：對沒上鎖的封存串發文會自動解除封存
        self.archived = False
        return self.add(embed)

    async def edit(self, *, archived=None, **_):
        if archived is not None:
            self.archived = archived

    async def fetch_message(self, msg_id):
        return self.messages[msg_id]


def _forum(edit_log):
    forum = mock.MagicMock(spec=discord.ForumChannel)
    forum.id = FORUM_ID
    forum.available_tags = []
    forum.created = []
    forum.rejects_edits_on_create = False
    threads = {}

    async def create_thread(name, embed, applied_tags):
        thread = _Thread(edit_log)
        thread.rejects_edits = forum.rejects_edits_on_create
        threads[thread.id] = thread
        forum.created.append(thread)
        starter = thread.add(embed)
        return SimpleNamespace(thread=thread, message=starter)

    forum.create_thread = create_thread
    forum.get_thread = threads.get
    return forum


def _post(sn, gp=0, content="內文第一行\n內文第二行", comments=()):
    return {
        "sn": sn, "title": "【討論】測試串", "author_name": "作者", "author_id": "author1",
        "category": "", "gp_count": gp, "bp_count": 0,
        "url": "https://forum.gamer.com.tw/C.php?bsn=74934&snA=1",
        "published_at": "2026-10-01 12:00:00", "content": content,
        "content_images": [], "comments": list(comments),
    }


def _comment(cid, text="留言", gp=0):
    return {
        "comment_id": cid, "floor": f"B{cid}", "user_name": "留言者", "user_id": "commenter1",
        "content": text, "gp_count": gp, "bp_count": 0, "is_hot": False,
    }


def _long_comments(n):
    """每則約 1,100 字：一格放 3 則，14 則會開出 2 個溢出格。"""
    return [_comment(str(i), text=f"{i}號" + "長" * 1000) for i in range(1, n + 1)]


def _thread_data(post_id, main, replies):
    return {"board_id": "74934", "post_id": post_id, "main_post": main, "replies": list(replies)}


class _Base(unittest.IsolatedAsyncioTestCase):
    interval = INTERVAL

    async def asyncSetUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = StateDB(Path(self._tmp.name) / "state.db")
        await self.db.connect()
        self.edits = []
        self.forum = _forum(self.edits)
        bot = SimpleNamespace(
            get_channel=lambda cid: self.forum if cid == FORUM_ID else None,
            fetch_channel=mock.AsyncMock(side_effect=Exception("not found")),
        )
        self.monitor = BahamutMonitor(bot)
        self.monitor._state_db = self.db
        for patcher in (
            mock.patch.object(bm, "SEND_DELAY", 0),
            mock.patch.object(bm, "THREAD_EDIT_INTERVAL", self.interval),
            mock.patch.object(bm, "get_article_runtime_config", return_value={}),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    async def asyncTearDown(self):
        await self.db.close()
        self._tmp.cleanup()

    async def relay(self, data):
        return await self.monitor.send_bahamut_thread_to_forum(FORUM_ID, data)

    async def edits_of_update(self, before, after):
        """先轉發 before（建串），再收到 after 那一輪；回傳那一輪的編輯紀錄。"""
        await self.relay(before)
        self.edits.clear()
        await self.relay(after)
        return list(self.edits)

    def edited_messages(self, edits):
        threads = {t.id: t for t in self.forum.created}
        return [threads[channel].messages[msg_id] for _, channel, msg_id in edits]


class SameThreadPacingTests(_Base):
    async def test_edits_in_one_thread_are_spaced(self):
        before = _thread_data("1", _post("100"), [_post("101"), _post("102"), _post("103")])
        after = _thread_data("1", _post("100"), [_post("101", gp=1), _post("102", gp=2), _post("103", gp=3)])

        edits = await self.edits_of_update(before, after)

        self.assertEqual(len(edits), 3, "三則回覆的推數都變了，應該各編一次")
        times = [t for t, _, _ in edits]
        for earlier, later in zip(times, times[1:]):
            self.assertGreaterEqual(later - earlier, INTERVAL - EPS)

    async def test_interval_counts_from_when_the_edit_went_through(self):
        # discord.py 吃到 429 會自己等完重試；那段等待不能算進間隔，否則下一則又撞上
        before = _thread_data("1", _post("100"), [_post("101"), _post("102")])
        after = _thread_data("1", _post("100"), [_post("101", gp=1), _post("102", gp=1)])
        await self.relay(before)
        thread = self.forum.created[0]
        thread.edit_takes = INTERVAL
        self.edits.clear()

        await self.relay(after)

        (_, _, first), (second_start, _, _) = self.edits
        self.assertGreaterEqual(second_start - thread.edit_done_at[first], INTERVAL - EPS)


class RejectedEditTests(_Base):
    interval = SLACK_INTERVAL

    async def test_rejected_edits_do_not_hold_up_the_round(self):
        # 討論串封存時 Discord 會直接拒絕編輯；被拒的不佔排隊名額，否則每則都白等一個間隔
        before = _thread_data("1", _post("100"), [_post("101"), _post("102"), _post("103")])
        after = _thread_data("1", _post("100"), [_post("101", gp=1), _post("102", gp=1), _post("103", gp=1)])
        await self.relay(before)
        self.forum.created[0].rejects_edits = True

        start = time.monotonic()
        await self.relay(after)

        self.assertLess(time.monotonic() - start, self.interval)


class ArchivedThreadTests(_Base):
    async def test_archived_thread_waits_for_a_new_reply(self):
        # 封存的串編輯一定被拒：不去試，變動留著；等有新回覆（本來就會解除封存）再一起補上
        await self.relay(_thread_data("1", _post("100"), [_post("101")]))
        thread = self.forum.created[0]
        thread.archived = True

        await self.relay(_thread_data("1", _post("100"), [_post("101", gp=3)]))
        self.assertEqual(thread.edit_attempts, 0)
        self.assertTrue(thread.archived, "只有推數變動，不為此把舊貼文頂回活躍列表")

        self.edits.clear()
        await self.relay(_thread_data("1", _post("100"), [_post("101", gp=3), _post("102")]))

        self.assertFalse(thread.archived)
        shown = [m.embeds[0].description for m in self.edited_messages(self.edits)]
        self.assertTrue(any("👍 3" in d for d in shown), "封存期間累積的推數變動要補上")
        self.assertTrue(any(m.embeds and m.embeds[0].title == "📝 回覆 #3" for m in thread.messages.values()))


class CrossThreadPacingTests(_Base):
    interval = SLACK_INTERVAL

    async def test_threads_do_not_wait_for_each_other(self):
        before = {pid: _thread_data(pid, _post(f"{pid}00"), [_post(f"{pid}01"), _post(f"{pid}02")])
                  for pid in ("1", "2")}
        after = {pid: _thread_data(pid, _post(f"{pid}00"), [_post(f"{pid}01", gp=1), _post(f"{pid}02", gp=1)])
                 for pid in ("1", "2")}
        for data in before.values():
            await self.relay(data)
        self.edits.clear()

        start = time.monotonic()
        await asyncio.gather(*(self.relay(data) for data in after.values()))

        self.assertEqual(len({channel for _, channel, _ in self.edits}), 2)
        self.assertEqual(len(self.edits), 4)
        # 各自排隊：兩串各編兩則，總共只要等一個間隔；互相等待的話要三個間隔
        self.assertLess(max(t for t, _, _ in self.edits) - start, 2 * self.interval)


class OnlyChangedMessagesTests(_Base):
    async def test_same_data_again_edits_nothing(self):
        data = _thread_data("1", _post("100", comments=[_comment("1")]),
                            [_post("101", comments=[_comment("2")]), _post("102")])

        edits = await self.edits_of_update(data, data)

        self.assertEqual(edits, [])

    async def test_only_changed_messages_are_edited(self):
        before = _thread_data("1", _post("100"), [
            _post("101", comments=[_comment("1")]),
            _post("102", comments=[_comment("2")]),
            _post("103"),
        ])
        after = _thread_data("1", _post("100"), [
            _post("101", comments=[_comment("1")]),
            _post("102", comments=[_comment("2"), _comment("3", text="第一輪就來的新留言")]),
            _post("103", gp=7),
        ])

        edits = await self.edits_of_update(before, after)

        shown = [m.embeds[0].description for m in self.edited_messages(edits)]
        self.assertEqual(len(shown), 2, shown)
        self.assertTrue(any("👍 7" in d for d in shown), "回覆 #4 的推數要更新")
        self.assertTrue(any("第一輪就來的新留言" in d for d in shown), "新留言要出現在留言格")

    async def test_reply_added_during_update_gets_later_changes(self):
        first = _thread_data("1", _post("100"), [_post("101")])
        added = _thread_data("1", _post("100"), [_post("101"), _post("102")])
        later = _thread_data("1", _post("100"), [_post("101"), _post("102", gp=5)])
        await self.relay(first)

        edits = await self.edits_of_update(added, later)

        shown = [m.embeds[0].description for m in self.edited_messages(edits)]
        self.assertEqual(len(shown), 1, shown)
        self.assertIn("👍 5", shown[0])

    async def test_overflow_opened_during_update_is_not_edited_again(self):
        few = _thread_data("1", _post("100"), [_post("101", comments=_long_comments(4))])
        many = _thread_data("1", _post("100"), [_post("101", comments=_long_comments(14))])
        await self.relay(few)

        edits = await self.edits_of_update(many, many)

        self.assertEqual(edits, [])

    async def test_new_comment_in_overflow_opened_during_update_is_shown(self):
        few = _thread_data("1", _post("100"), [_post("101", comments=_long_comments(4))])
        many = _thread_data("1", _post("100"), [_post("101", comments=_long_comments(14))])
        more = _thread_data("1", _post("100"), [_post("101", comments=_long_comments(15))])
        await self.relay(few)

        edits = await self.edits_of_update(many, more)

        shown = [m.embeds[0].description for m in self.edited_messages(edits)]
        self.assertEqual(len(shown), 1, "只有最後一個溢出格多了一則留言")
        self.assertIn("15號", shown[0])

    async def test_thread_created_with_overflow_is_not_edited_again(self):
        many = _thread_data("1", _post("100"), [_post("101", comments=_long_comments(14))])

        self.assertEqual(await self.edits_of_update(many, many), [])

    async def test_new_comment_right_after_thread_created_with_overflow_is_shown(self):
        many = _thread_data("1", _post("100"), [_post("101", comments=_long_comments(14))])
        more = _thread_data("1", _post("100"), [_post("101", comments=_long_comments(15))])

        edits = await self.edits_of_update(many, more)

        shown = [m.embeds[0].description for m in self.edited_messages(edits)]
        self.assertEqual(len(shown), 1, "只有最後一個溢出格多了一則留言")
        self.assertIn("15號", shown[0])


class ReplyNumberTests(_Base):
    async def test_reply_added_later_continues_the_numbering(self):
        await self.relay(_thread_data("1", _post("100"), [_post("101"), _post("102")]))

        await self.relay(_thread_data("1", _post("100"), [_post("101"), _post("102"), _post("103")]))

        thread = self.forum.created[0]
        titles = [m.embeds[0].title for m in thread.messages.values() if m.embeds and m.embeds[0].title
                  and m.embeds[0].title.startswith("📝 回覆")]
        self.assertEqual(titles, ["📝 回覆 #2", "📝 回覆 #3", "📝 回覆 #4"])


def _long_content(changed_line=None, n_lines=250):
    """每行 50 字：250 行時本文之外會切出 3 則續文（140 行 1 則、330 行 4 則）。"""
    lines = [f"第{i:03d}行" + "字" * 45 for i in range(n_lines)]
    if changed_line is not None:
        lines[changed_line] = f"第{changed_line:03d}行（作者後來改過）" + "改" * 36
    return "\n".join(lines)


class ContinuationTests(_Base):
    def continuations(self, reply_no=None):
        """依訊息順序找出某篇的續文：本文訊息之後、留言格之前那幾則沒有標題、同色的訊息。
        reply_no 為 None 時找主文的續文。"""
        thread = self.forum.created[0]
        msgs = list(thread.messages.values())
        if reply_no is None:
            start, color = 0, bm.COLOR_MAIN_POST
        else:
            start = next(i for i, m in enumerate(msgs)
                         if m.embeds and m.embeds[0].title and f"#{reply_no}" in m.embeds[0].title)
            color = bm.COLOR_REPLY
        conts = []
        for m in msgs[start + 1:]:
            if m.embeds and m.embeds[0].title is None and m.embeds[0].color.value == color:
                conts.append(m)
            else:
                break
        return conts

    def post_message(self, reply_no=None):
        """主文（reply_no 為 None）或「📝 回覆 #reply_no」那則訊息。"""
        msgs = list(self.forum.created[0].messages.values())
        if reply_no is None:
            return msgs[0]
        return next(m for m in msgs if m.embeds and m.embeds[0].title == f"📝 回覆 #{reply_no}")

    def follow_continuations(self, reply_no=None):
        """讀者看到的續文：從本文底部的「更多內文」開始，順著連結一路往下讀。"""
        thread = self.forum.created[0]
        chain = []
        current = self.post_message(reply_no)
        while True:
            link = re.search(r"更多內文\.\.\.\]\(https://discord\.com/channels/\d+/\d+/(\d+)\)$",
                             current.embeds[0].description)
            if not link:
                return chain
            current = thread.messages[int(link.group(1))]
            chain.append(current)

    def placeholders(self):
        thread = self.forum.created[0]
        return [m for m in thread.messages.values()
                if m.embeds and m.embeds[0].description == bm.CONTINUATION_REMOVED_PLACEHOLDER]

    async def relay_reply_lines(self, n_lines):
        await self.relay(_thread_data("1", _post("100"), [_post("101", content=_long_content(n_lines=n_lines))]))

    def assert_reads_to_the_end(self, n_lines, count):
        """順著連結讀得到 count 則續文，最後一則有原文最後一行。"""
        chain = self.follow_continuations(2)
        self.assertEqual(len(chain), count)
        self.assertIn(f"第{n_lines - 1:03d}行", chain[-1].embeds[0].description)
        self.assert_nav_chain(chain, min_count=count)

    async def test_continuations_grow(self):
        await self.relay_reply_lines(140)
        self.assert_reads_to_the_end(140, 1)

        await self.relay_reply_lines(250)

        self.assert_reads_to_the_end(250, 3)

    async def test_continuations_shrink_then_grow_again(self):
        await self.relay_reply_lines(250)

        await self.relay_reply_lines(140)
        self.assert_reads_to_the_end(140, 1)
        self.assertEqual(len(self.placeholders()), 2, "多出來的兩則改成「此段已更新移除」")

        await self.relay_reply_lines(330)
        self.assert_reads_to_the_end(330, 4)
        self.assertEqual(self.placeholders(), [], "清空過的續文重新用上，不夠的再追加")

    async def test_long_post_links_to_its_first_continuation_and_stays_put(self):
        # 本文的連結算進 hash：同一份資料再來一輪，本文與續文都不該被判定有變
        data = _thread_data("1", _post("100", content=_long_content()), [_post("101", content=_long_content())])

        edits = await self.edits_of_update(data, data)

        self.assertEqual(edits, [])
        for reply_no in (None, 2):
            self.assertEqual(self.follow_continuations(reply_no), self.continuations(reply_no))
            self.assert_nav_chain(self.follow_continuations(reply_no))

    async def test_post_that_grows_past_one_message_links_to_the_new_continuation(self):
        # 改文變長：新續文追加在串尾，本文要有連結找得到它；改回短的就拿掉連結
        await self.relay_reply_lines(20)
        self.assertEqual(self.follow_continuations(2), [])

        await self.relay_reply_lines(140)
        self.assert_reads_to_the_end(140, 1)
        self.assertIs(self.follow_continuations(2)[0], list(self.forum.created[0].messages.values())[-1])

        await self.relay_reply_lines(20)
        self.assertEqual(self.follow_continuations(2), [])
        self.assertEqual(len(self.placeholders()), 1)

        self.edits.clear()
        await self.relay_reply_lines(20)
        self.assertEqual(self.edits, [], "改回短的之後也穩定")

    async def test_links_that_failed_when_created_are_added_next_round(self):
        # 建串當下補連結的編輯被拒：記的 hash 要是「沒連結」的版本，下一輪才會補上
        data = _thread_data("1", _post("100"), [_post("101", content=_long_content())])
        self.forum.rejects_edits_on_create = True
        await self.relay(data)
        thread = self.forum.created[0]
        self.assertEqual(self.follow_continuations(2), [])
        thread.rejects_edits = False

        await self.relay(data)

        self.assertEqual(self.follow_continuations(2), self.continuations(2))
        self.assert_nav_chain(self.follow_continuations(2))

    async def test_existing_long_post_gets_the_link_once(self):
        # 套用前建的長文：本文沒有連結、記的 hash 也是沒連結的版本 → 補一次，之後不再編
        data = _thread_data("1", _post("100"), [_post("101", content=_long_content())])
        await self.relay(data)
        reply = self.post_message(2)
        old_desc = reply.embeds[0].description.split("\n\n⬇️")[0]
        reply.embeds = [discord.Embed(title=reply.embeds[0].title, description=old_desc, color=bm.COLOR_REPLY)]
        state = await self.db.get_bahamut_thread("74934", "1")
        state["posts"]["101"]["content_hash"] = content_hash(old_desc)
        await self.db.save_bahamut_thread("74934", "1", state)

        self.edits.clear()
        await self.relay(data)
        self.assertEqual([m for m in self.edited_messages(self.edits)], [reply])
        self.assert_nav_chain(self.follow_continuations(2))

        self.edits.clear()
        await self.relay(data)
        self.assertEqual(self.edits, [])

    def assert_nav_chain(self, conts, min_count=3):
        """每則續文（最後一則除外）底部都有「更多內文」連到下一則，而且不超過 Discord 上限。"""
        self.assertGreaterEqual(len(conts), min_count)
        for cur, nxt in zip(conts, conts[1:]):
            desc = cur.embeds[0].description
            self.assertIn("更多內文", desc)
            self.assertTrue(desc.endswith(f"/{nxt.id})"), desc[-120:])
            self.assertLessEqual(len(desc), bm.EMBED_DESC_LIMIT)
        self.assertNotIn("更多內文", conts[-1].embeds[0].description)

    async def test_gp_change_does_not_touch_continuations(self):
        before = _thread_data("1", _post("100"), [_post("101", content=_long_content())])
        after = _thread_data("1", _post("100"), [_post("101", gp=9, content=_long_content())])

        edits = await self.edits_of_update(before, after)

        shown = [m.embeds[0].description for m in self.edited_messages(edits)]
        self.assertEqual(len(shown), 1, "只有回覆本文（推數）要編，續文沒變")
        self.assertIn("👍 9", shown[0])
        self.assert_nav_chain(self.continuations(2))

    async def test_text_change_in_later_part_updates_that_continuation_only(self):
        before = _thread_data("1", _post("100"), [_post("101", content=_long_content())])
        after = _thread_data("1", _post("100"), [_post("101", content=_long_content(changed_line=150))])

        edits = await self.edits_of_update(before, after)

        self.assertEqual(len(edits), 1)
        conts = self.continuations(2)
        self.assertTrue(any("作者後來改過" in c.embeds[0].description for c in conts))
        self.assert_nav_chain(conts)

    async def test_main_post_later_part_change_is_updated_too(self):
        before = _thread_data("1", _post("100", content=_long_content()), [_post("101")])
        after = _thread_data("1", _post("100", content=_long_content(changed_line=150)), [_post("101")])

        edits = await self.edits_of_update(before, after)

        self.assertEqual(len(edits), 1)
        conts = self.continuations()
        self.assertTrue(any("作者後來改過" in c.embeds[0].description for c in conts))
        self.assert_nav_chain(conts)

    async def test_lost_nav_links_come_back(self):
        data = _thread_data("1", _post("100"), [_post("101", content=_long_content())])
        await self.relay(data)
        for cont in self.continuations(2):
            # 模擬舊版重編把導航連結洗掉
            desc = cont.embeds[0].description
            cont.embeds = [discord.Embed(description=desc.split("\n\n⬇️")[0], color=bm.COLOR_REPLY)]

        await self.relay(data)

        self.assert_nav_chain(self.continuations(2))

    async def test_nav_link_fits_when_continuation_is_full(self):
        # 沒有換行的長段落會被硬切成剛好上限的續文，導航連結也要塞得下
        data = _thread_data("1", _post("100"), [_post("101", content="長" * 12000)])

        await self.relay(data)

        self.assert_nav_chain(self.continuations(2))


if __name__ == "__main__":
    unittest.main()
