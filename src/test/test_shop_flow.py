"""商品上架（services.community.shop_service ＋ commands.shop_commands ＋ 交易模組）。

用真的交易模組與真的 Discord 元件，只把 Discord 本身換成假的伺服器（沿用 test_trade_flow 的 World）。

守的底線：
  1. 上架：只有觀星者；bot 代發商品貼文（標題、說明、上架者暱稱、商品圖換固定檔名並由 embed 引用第一張）；
     幣別有數字（只能填符號，金額在品項）、太長（塞不進按鈕的 custom_id）、圖太大都在發文前擋下；
     還沒有品項就沒有購買選單；不是圖片、商品論壇沒綁定都說清楚原因。之後更新貼文不傳附件清單（圖才不會被刪）。
  2. 管理：只有上架者或管理員（含群主）；新增（單一、批次）後購買選單出現，有預購就掛「預購中」；
     全部賣完時購買選單停用並寫「已售完」，管理按鈕照常可按，補貨後選單恢復；
     最多 25 個；品項編號不重用；編輯時數量填「剩餘數量」（預填目前剩幾個、賣光預填 0，存的上限＝已下單＋剩餘，
     填 0＝停賣）；有進行中訂單的品項不能刪；
     下架後選單與按鈕停用、標題【已下架】、鎖定，但預購截止照樣提醒。
  3. 下單：不能買自己的；一次最多 5 種；賣完、截止、超過剩餘都擋下；下單就預留（貼文上的剩餘跟著變）；
     開出只有買家與上架者的交易 thread，訂單訊息有明細，總計寫在底下的訂單紀錄按鈕上（文字不重複）；
     留底也帶上總計；同一位買家加購沿用 thread、
     另一位買家各開一個；交易 thread 開不起來就把預留還回去；加購會作廢原本的領收通知；
     正在取消的 thread 不再收訂單。
  4. 接上交易模組：商品交易完成時在封存頻道另發一篇留底（下單紀錄＋溝通紀錄，格式同自由市場封存，寫名字不寫 @；
     封存頻道沒設定就說沒留底），不搬、不刪商品貼文、不結束其他買家的 thread——商品論壇改綁或解除也一樣
     （交易種類看交易 thread 裡的訂單紀錄，不看來源貼文在哪）；取消時把這個 thread 所有訂單（首次＋加購，
     多長的 thread 都讀完）的預留還回去。
  5. 預購截止：截止時在含這個品項、還沒完成的交易 thread @ 雙方提醒一次；品項標成已截止、不能再買；
     重啟後不重複提醒；一個 thread 發不出去不影響其他人、也不會每小時重複 @；沒有未截止的預購就拿掉標籤；
     已被封存的商品貼文也找得到，處理完封存回去。
  6. 置頂上架說明：綁定時發一篇並置頂、建好「預購中」標籤（建不了要告訴管理員）；已經有就不重發，
     但說明文字改過（例：品相改叫品項）時，重綁會把置頂那篇更新成最新版，按鈕留著。
     說明附橫幅圖（論壇列表的縮圖也用它）：舊的置頂文重綁時補上、換了圖才重傳；圖檔不在就只發文字、不拿掉原本的圖。
  7. 名字一律是伺服器暱稱（快取拿不到就向 API 查）。
  8. 分層：商品模組不 import 指令層；介面層按鈕與選單的 custom_id 解析得回同一筆資料。
  9. 選單不會卡住：Discord 的選單選過同一項就不會再通知 bot（使用者 2026-10-03 實測：編輯一次後
     第二次編輯不了；按了取消就沒辦法重新選擇）。買家在購買選單選完、填數量的視窗一跳出，
     商品貼文就重畫清空選單，視窗裡仍是剛選的商品；管理面板每次操作完都重畫，編輯品項選了就跳出視窗、
     跳出後重畫面板（改不了原始回應就改指定訊息，都不行只留 log、不出錯），刪除與下架的確認換在面板上。
  10. 給群友看的訊息不寫程式用語：交易 thread 一律說「對話」（使用者 2026-10-04）。
"""

import ast
import asyncio
import itertools
import os
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import discord  # noqa: E402

from commands import shop_commands  # noqa: E402
from commands.shop_commands import DiscordShopViews  # noqa: E402
from services.community import shop_service, trade_service  # noqa: E402
from services.community.shop_listing import (  # noqa: E402
    ShopError, Variant, listing_from_message, parse_batch, parse_draft,
)
from services.community.shop_service import ListingSource, ShopService  # noqa: E402
from services.community.trade_service import CANCEL, NOTIFY, RECEIVE, TradeService  # noqa: E402
from sys_settings.shop_settings import ShopSettings  # noqa: E402
from test.test_trade_flow import (  # noqa: E402  只拿假物件，不拿 TestCase（免得被重跑）
    ARCHIVE_ID, BOT, CART_ID, FORUM_ID, OUTSIDER, OWNER, REQUESTER, SUPPLIER, SUPPLIER_B,
    FakeMessage, FakeThread, World, _make_view,
)

SHOP_ID = 400
SELLER = SUPPLIER          # 上架者（Trader）
BUYER = REQUESTER
BUYER_B = OUTSIDER
TRADERS = {SUPPLIER.id, SUPPLIER_B.id}


class ShopForum:
    def __init__(self, world):
        self.world = world
        self.id = SHOP_ID
        self.guild = world.guild
        self.available_tags = []
        self.all_threads = []
        self._tag_ids = itertools.count(900)

    @property
    def threads(self):
        return [t for t in self.all_threads if not t.archived]

    async def archived_threads(self, *, limit=100):
        for thread in sorted((t for t in self.all_threads if t.archived),
                             key=lambda t: t.archive_timestamp, reverse=True):
            yield thread

    async def create_tag(self, *, name):
        tag = SimpleNamespace(id=next(self._tag_ids), name=name)
        self.available_tags.append(tag)
        return tag


class ForumThread(FakeThread):
    """商品論壇裡的貼文（商品、置頂說明）。"""

    def __init__(self, world, tid, name, forum, owner_id):
        super().__init__(world, tid, name, parent_id=forum.id)
        self.parent = forum
        self.owner_id = owner_id
        self.applied_tags = []
        self.flags = SimpleNamespace(pinned=False)
        self.jump_url = f"https://discord.com/channels/1/{tid}"
        self.mention = f"<#{tid}>"

    async def edit(self, **kwargs):
        if "applied_tags" in kwargs:
            self.applied_tags = list(kwargs.pop("applied_tags"))
        if "pinned" in kwargs:
            self.flags.pinned = kwargs.pop("pinned")
        if "auto_archive_duration" in kwargs:
            self.auto_archive_duration = kwargs.pop("auto_archive_duration")
        await super().edit(**kwargs)

    def tag_names(self):
        return [t.name for t in self.applied_tags]


class FakeAttachment:
    def __init__(self, filename, content_type="image/png", size=1000):
        self.filename = filename
        self.content_type = content_type
        self.size = size

    async def to_file(self, *, filename):
        return SimpleNamespace(filename=filename, source=self.filename)


class ShopTestCase(unittest.TestCase):
    def setUp(self):
        self.world = World()
        self.forum = ShopForum(self.world)
        self.world.channels[SHOP_ID] = self.forum
        self.config = {
            "trade_forum_channel_id": FORUM_ID,
            "cart_delivery_channel_id": CART_ID,
            "archive_channel_id": ARCHIVE_ID,
            "shop_forum_channel_id": SHOP_ID,
        }
        self.posts = []

        async def get_configured_id(key, *args, **kwargs):
            return self.config.get(key)

        async def check_role(member, role):
            return role == "Trader" and member.id in TRADERS

        async def shop_post(channel, *, embed=None, files=None, thread_title=None, view=None, **kwargs):
            thread = ForumThread(self.world, next(self.world.ids), thread_title, channel, owner_id=BOT.id)
            message = FakeMessage(self.world, thread.id, BOT, "", view=view, embed=embed, thread=thread)
            message.files = list(files or [])
            thread.messages.append(message)
            channel.all_threads.append(thread)
            self.world.channels[thread.id] = thread
            self.posts.append(thread)
            return message

        async def trade_post(channel, **kwargs):
            self.world.archived_posts.append((channel, kwargs))
            return SimpleNamespace(id=next(self.world.ids))

        self.ephemeral = mock.AsyncMock(name="safe_send_interaction_message")
        for p in (
            mock.patch.object(trade_service.ChannelConfig, "get_configured_id", side_effect=get_configured_id),
            mock.patch.object(trade_service, "check_role", side_effect=check_role),
            mock.patch.object(shop_service, "check_role", side_effect=check_role),
            mock.patch.object(trade_service, "post_to_channel", side_effect=trade_post),
            mock.patch.object(shop_service, "post_to_channel", side_effect=shop_post),
            mock.patch.object(trade_service, "safe_send_interaction_message", self.ephemeral),
            mock.patch.object(trade_service, "send_dm", mock.AsyncMock(return_value=True)),
        ):
            p.start()
            self.addCleanup(p.stop)
        self.trade, self.shop = self.services()

    def services(self):
        """新的服務實例＝模擬 bot 重啟：記憶體裡什麼都沒有，只剩 Discord 上的東西。"""
        trade = TradeService(self.world.bot, make_view=_make_view)
        shop = ShopService(self.world.bot, trade=trade, views=DiscordShopViews(ShopSettings()),
                           now=lambda: self.world.now)
        trade.add_source_kind(shop.source)
        return trade, shop

    def call(self, coro):
        return asyncio.run(coro)

    # ── 操作捷徑 ──

    def list_item(self, seller=SELLER, title="月相代儲", attachments=(), unit=""):
        return self.call(self.shop.create_listing(seller, title=title, description="交付方式：遊戲內交易",
                                                  unit=unit, attachments=attachments))

    def add(self, thread, *lines, actor=SELLER):
        drafts, errors = parse_batch("\n".join(lines), now=self.world.now)
        assert not errors, errors
        return self.call(self.shop.add_variants(thread.id, actor, drafts))

    def listing(self, thread):
        return listing_from_message(thread.messages[0])

    def order(self, thread, buyer, picks):
        return self.call(self.shop.place_order(thread.id, buyer, picks))

    def cutoff_text(self, **delta):
        moment = (self.world.now + timedelta(**delta)).astimezone(shop_service.APP_TZ)
        return moment.strftime("%Y/%m/%d %H:%M")

    def press(self, thread, user, action, ref):
        interaction = SimpleNamespace(
            user=user, channel=thread, message=None,
            response=SimpleNamespace(is_done=lambda: False, defer=mock.AsyncMock()),
        )
        self.call(self.trade.handle_button(interaction, action, ref))

    def ref_of(self, thread):
        return trade_service.TradeRef(*map(int, thread.messages[0].view.custom_ids[0].split(":")[2:]))


class ListingCreateTests(ShopTestCase):

    def test_only_sellers_can_list(self):
        with self.assertRaises(ShopError):
            self.list_item(seller=BUYER)
        self.assertEqual(self.posts, [])

    def test_listing_post(self):
        thread = self.list_item(attachments=[FakeAttachment("a.PNG"), FakeAttachment("b.jpg", "image/jpeg")])

        message = thread.messages[0]
        self.assertEqual(thread.name, "月相代儲")
        self.assertEqual(message.embed.author.name, f"上架者：{SELLER.display_name}")
        self.assertEqual([f.filename for f in message.files], ["item_1.png", "item_2.jpg"])
        self.assertEqual(message.embed.image.url, "attachment://item_1.png")
        listing = self.listing(thread)
        self.assertEqual((listing.owner_id, listing.unit, listing.variants), (SELLER.id, "NT$", ()))
        self.assertEqual([getattr(c, "options", None) for c in message.components[0].children], [None])  # 只有管理按鈕
        self.assertEqual(thread.auto_archive_duration, 10080)

    def test_rejections_explain_why(self):
        with self.assertRaises(ShopError) as caught:
            self.list_item(attachments=[FakeAttachment("x.pdf", "application/pdf")])
        self.assertIn("不是圖片", str(caught.exception))
        with self.assertRaises(ShopError) as caught:
            self.list_item(attachments=[FakeAttachment("big.png", size=50 * 1024 * 1024)])
        self.assertIn("太大", str(caught.exception))
        with self.assertRaises(ShopError) as caught:
            self.list_item(unit="NT$100")  # 把金額填進幣別
        self.assertIn("不能有數字", str(caught.exception))
        self.assertIn("USD$", str(caught.exception))  # 擋下來時附範例
        with self.assertRaises(ShopError) as caught:
            self.list_item(unit="鳴潮遊戲內星聲幣")  # 中文編碼後塞不進按鈕的 custom_id
        self.assertIn("幣別太長", str(caught.exception))
        self.assertEqual(self.posts, [])
        self.assertEqual(self.listing(self.list_item(unit="遊戲內星聲幣")).unit, "遊戲內星聲幣")
        del self.config["shop_forum_channel_id"]
        with self.assertRaises(ShopError) as caught:
            self.list_item()
        self.assertIn("/server_manager", str(caught.exception))


class ManageTests(ShopTestCase):

    def setUp(self):
        super().setUp()
        self.thread = self.list_item()

    def test_only_owner_or_admin(self):
        with self.assertRaises(ShopError):
            self.add(self.thread, "60 月相｜30｜10｜", actor=BUYER)
        with self.assertRaises(ShopError):
            self.add(self.thread, "60 月相｜30｜10｜", actor=SUPPLIER_B)  # 別的觀星者也不行
        self.add(self.thread, "60 月相｜30｜10｜", actor=OWNER)  # 群主可以
        self.assertEqual(len(self.listing(self.thread).variants), 1)

    def test_variants_show_the_buy_menu_and_preorder_tag(self):
        self.add(self.thread, "60 月相｜30｜10｜", f"6480 月相｜3000｜3｜{self.cutoff_text(days=1)}")

        select = self.thread.messages[0].components[0].children[0]
        self.assertEqual([o.label for o in select.options], ["60 月相", "6480 月相"])
        self.assertEqual(select.max_values, 2)
        self.assertEqual(len(self.thread.messages[0].embed.fields), 2)
        self.assertEqual(self.thread.tag_names(), ["預購中"])
        # 一般更新不傳附件清單：傳了（就算是空的）Discord 會把 embed 引用的商品圖刪掉
        self.assertEqual(self.thread.messages[0].edits[-1]["attachments"], "unchanged")

    def test_at_most_25_variants(self):
        self.add(self.thread, *[f"品項{n}｜1" for n in range(25)])
        with self.assertRaises(ShopError):
            self.add(self.thread, "多一個｜1")

    def test_adding_or_editing_wakes_the_cutoff_check(self):
        # 截止時間改到一小時內也要準時提醒：新增、編輯品項就叫醒排程重算（2026-10-04 實測晚了 40 分鐘）
        self.add(self.thread, f"6480 月相｜3000｜3｜{self.cutoff_text(minutes=20)}")
        self.assertTrue(self.shop.cutoffs_changed.is_set())

        self.shop.cutoffs_changed.clear()
        sooner = parse_draft("6480 月相", "3000", "3", self.cutoff_text(minutes=10), preorder=True,
                             now=self.world.now, min_limit=0)
        self.call(self.shop.edit_variant(self.thread.id, SELLER, 1, sooner))
        self.assertTrue(self.shop.cutoffs_changed.is_set())

    def test_editing_quantity_means_remaining(self):
        # 編輯時填的是「還要賣幾個」：系統自動加上已下單的（TR-Q27）
        self.add(self.thread, "60 月相｜30｜4｜")
        self.order(self.thread, BUYER, {1: 2})

        async def form_default():
            return shop_commands.VariantModal(self.thread.id, self.listing(self.thread).variant(1)).limit.default

        self.assertEqual(self.call(form_default()), "2")  # 4 件賣掉 2 件，預填 2
        restock = parse_draft("60 月相", "30", "5", "", preorder=False, now=self.world.now, min_limit=0)
        self.call(self.shop.edit_variant(self.thread.id, SELLER, 1, restock))
        variant = self.listing(self.thread).variant(1)
        self.assertEqual((variant.taken, variant.limit, variant.remaining), (2, 7, 5))  # 補貨 5 件就填 5

        stop = parse_draft("60 月相", "30", "0", "", preorder=False, now=self.world.now, min_limit=0)
        self.call(self.shop.edit_variant(self.thread.id, SELLER, 1, stop))
        self.assertEqual(self.listing(self.thread).variant(1).remaining, 0)  # 填 0＝停賣
        self.assertEqual(self.call(form_default()), "0")  # 賣光時預填 0
        with self.assertRaises(ShopError):
            self.call(self.shop.delete_variant(self.thread.id, SELLER, 1))  # 有進行中訂單不能刪

    def buy_menu(self):
        return next(c for c in self.thread.messages[0].components[0].children if isinstance(c, discord.ui.Select))

    def test_buy_menu_is_disabled_when_everything_is_sold_out(self):
        self.add(self.thread, "60 月相｜30｜2｜")
        self.order(self.thread, BUYER, {1: 2})

        self.assertTrue(self.buy_menu().disabled)
        self.assertEqual(self.buy_menu().placeholder, "已售完")
        manage = [c for c in self.thread.messages[0].components[0].children if isinstance(c, discord.ui.Button)]
        self.assertFalse(manage[0].disabled)  # 上架者還要能補貨
        self.assertEqual(self.listing(self.thread).variant(1).remaining, 0)  # 停用的選單照樣讀得回品項

        restock = parse_draft("60 月相", "30", "3", "", preorder=False, now=self.world.now, min_limit=0)
        self.call(self.shop.edit_variant(self.thread.id, SELLER, 1, restock))
        self.assertFalse(self.buy_menu().disabled)
        self.assertEqual(self.buy_menu().placeholder, "選擇要購買的商品（可多選）")

    def test_deleted_numbers_are_not_reused(self):
        self.add(self.thread, "60 月相｜30｜10｜", "300 月相｜150｜｜")
        self.call(self.shop.delete_variant(self.thread.id, SELLER, 2))
        self.add(self.thread, "980 月相｜490｜｜")
        self.assertEqual([v.key for v in self.listing(self.thread).variants], [1, 3])

    def test_close_listing(self):
        self.add(self.thread, f"6480 月相｜3000｜3｜{self.cutoff_text(days=1)}")

        self.call(self.shop.close_listing(self.thread.id, SELLER))

        children = self.thread.messages[0].components[0].children
        self.assertTrue(all(c.disabled for c in children))
        self.assertEqual(self.buy_menu().placeholder, "已下架")
        self.assertTrue(self.thread.name.startswith("【已下架】"))
        self.assertTrue(self.thread.locked)
        self.assertEqual(self.thread.tag_names(), ["預購中"])  # 已成立的預購交易，截止時仍要提醒
        with self.assertRaises(ShopError):
            self.call(self.shop.check_pick(self.thread.id, BUYER, [1]))


class OrderTests(ShopTestCase):

    def setUp(self):
        super().setUp()
        self.thread = self.list_item()
        self.add(self.thread, "60 月相｜30｜10｜", "寰宇電台｜20｜｜", "一條龍｜40｜1｜")

    def test_cannot_buy_own_listing(self):
        with self.assertRaises(ShopError):
            self.call(self.shop.check_pick(self.thread.id, SELLER, [1]))

    def test_order_reserves_and_opens_a_private_thread(self):
        opened = self.order(self.thread, BUYER, {1: 2, 2: 1})

        listing = self.listing(self.thread)
        self.assertEqual((listing.variant(1).taken, listing.variant(1).remaining), (2, 8))
        self.assertIn("剩 8", self.thread.messages[0].embed.fields[0].value)
        trade = opened.thread
        self.assertEqual(sorted(trade.members), sorted([BUYER.id, SELLER.id]))
        self.assertTrue(trade.name.startswith("【交易中】需求者 與 供應者甲"))
        self.assertEqual(trade.messages[0].embed.fields[0].name, "商品貼文")
        note = trade.messages[-1]
        self.assertIn("60 月相 ×2", note.content)
        self.assertNotIn("總計", note.content)  # 總計只寫在按鈕上，不重複
        self.assertEqual(note.components[0].children[0].label, "總計 NT$80")
        self.assertTrue(note.components[0].children[0].custom_id.startswith("shop:order:"))
        self.assertTrue(note.components[0].children[0].disabled)

    def test_same_buyer_adds_on_other_buyer_gets_own_thread(self):
        first = self.order(self.thread, BUYER, {1: 1})
        again = self.order(self.thread, BUYER, {2: 1})
        other = self.order(self.thread, BUYER_B, {1: 1})

        self.assertFalse(again.created)
        self.assertIs(again.thread, first.thread)
        self.assertIn("寰宇電台", first.thread.messages[-1].content)
        self.assertIsNot(other.thread, first.thread)
        self.assertEqual(len(self.world.cart.all_threads), 2)

    def test_at_most_five_kinds_per_order(self):
        self.add(self.thread, *[f"加購{n}｜1" for n in range(3)])
        with self.assertRaises(ShopError) as caught:
            self.call(self.shop.check_pick(self.thread.id, BUYER, [1, 2, 3, 4, 5, 6]))
        self.assertIn("最多挑 5 種", str(caught.exception))

    def test_add_on_voids_the_receipt_notice(self):
        trade = self.order(self.thread, BUYER, {1: 1}).thread
        self.press(trade, SELLER, NOTIFY, self.ref_of(trade))
        notice = trade.messages[-1]

        self.order(self.thread, BUYER, {2: 1})
        self.world.advance(hours=25)
        self.call(self.trade.run_receipt_deadlines(self.world.now))

        self.assertEqual(notice.components, [])
        self.assertIn("作廢", notice.content)
        self.assertFalse(trade.locked)

    def test_thread_being_cancelled_takes_no_more_orders(self):
        first = self.order(self.thread, BUYER, {1: 1}).thread

        async def race():
            # 取消拿著 thread 的鎖時又來一筆加購：加購列出 thread 時它還沒結束，等到鎖時已經結束了
            lock = self.trade._lock(first.id)
            await lock.acquire()
            order = asyncio.create_task(self.shop.place_order(self.thread.id, BUYER, {1: 1}))
            for _ in range(5):
                await asyncio.sleep(0)
            self.trade._closed.add(first.id)
            lock.release()
            return await order

        again = self.call(race())

        self.assertTrue(again.created)
        self.assertIsNot(again.thread, first)
        self.assertEqual(sum("🧾" in (c or "") for c in first.sent()), 1)  # 加購沒有發進正在取消的 thread

    def test_unavailable_choices_are_refused(self):
        self.order(self.thread, BUYER, {3: 1})
        with self.assertRaises(ShopError) as caught:
            self.call(self.shop.check_pick(self.thread.id, BUYER_B, [3]))
        self.assertIn("已售完", str(caught.exception))
        with self.assertRaises(ShopError) as caught:
            self.order(self.thread, BUYER_B, {1: 11})
        self.assertIn("只剩", str(caught.exception))

    def test_reservation_is_returned_when_the_trade_cannot_open(self):
        del self.config["cart_delivery_channel_id"]
        with self.assertRaises(ShopError) as caught:
            self.order(self.thread, BUYER, {1: 2})
        self.assertEqual(str(caught.exception), "目前無法開啟交易，請通知管理員。")  # 原因寫在 log，不給買家看
        self.assertEqual(self.listing(self.thread).variant(1).taken, 0)


class TradeIntegrationTests(ShopTestCase):

    def setUp(self):
        super().setUp()
        self.thread = self.list_item()
        self.add(self.thread, "60 月相｜30｜10｜", "寰宇電台｜20｜5｜")

    def test_completing_keeps_the_listing_and_other_buyers(self):
        mine = self.order(self.thread, BUYER, {1: 2}).thread
        theirs = self.order(self.thread, BUYER_B, {1: 1}).thread
        mine.messages.append(FakeMessage(self.world, next(self.world.ids), BUYER, "什麼時候方便交易？"))

        self.press(mine, BUYER, RECEIVE, self.ref_of(mine))

        self.assertTrue(mine.locked)
        # 成功留底就不提封存的事，只說交易完成（使用者 2026-10-04）
        self.assertIn("交易完成。此對話將鎖定。", mine.sent()[-1])
        # 交易按鈕拿掉了，但 🧾 訂單紀錄要留著（取消還回、認出商品交易都靠它）
        remaining = [c.custom_id for m in mine.messages for row in m.components for c in row.children]
        self.assertTrue(remaining and all(i.startswith("shop:order:") for i in remaining))
        self.assertFalse(self.thread.deleted)
        self.assertFalse(theirs.locked)
        # 留底：另發一篇備份（不是搬商品貼文），摘要是下單紀錄，後面接溝通紀錄；寫名字不寫 @
        (_, post), = self.world.archived_posts
        self.assertTrue(post["thread_title"].startswith("【市集】月相代儲｜需求者 與 供應者甲"))
        self.assertIn("60 月相 ×2", post["content"])
        self.assertIn("總計 NT$60", post["content"])  # 總計在按鈕上，留底要帶上
        self.assertIn("需求者: 什麼時候方便交易", post["content"])  # 整個交易 thread 的對話都在
        self.assertNotIn("<@", post["content"])
        self.assertFalse(post.get("files"))
        self.assertEqual(self.listing(self.thread).variant(1).taken, 3)  # 完成的算賣出，不還回

    def test_listing_is_safe_even_if_the_shop_forum_is_unbound(self):
        mine = self.order(self.thread, BUYER, {1: 2}).thread
        theirs = self.order(self.thread, BUYER_B, {1: 1}).thread
        del self.config["shop_forum_channel_id"]  # 管理員解除綁定（或讀不到設定）

        self.press(mine, BUYER, RECEIVE, self.ref_of(mine))

        self.assertIn("交易完成", mine.sent()[-1])
        self.assertFalse(self.thread.deleted)
        self.assertTrue(all(post["thread_title"].startswith("【市集】") for _, post in self.world.archived_posts))
        self.assertFalse(theirs.locked)

    def test_no_record_when_the_archive_channel_is_unset(self):
        mine = self.order(self.thread, BUYER, {1: 1}).thread
        del self.config["archive_channel_id"]

        with self.assertLogs(shop_service.logger, level="WARNING"):  # 原因寫在 log
            self.press(mine, BUYER, RECEIVE, self.ref_of(mine))

        self.assertIn("交易紀錄沒能自動保存，請通知管理員。", mine.sent()[-1])
        self.assertTrue(mine.locked)

    def test_record_failure_asks_to_tell_an_admin(self):
        mine = self.order(self.thread, BUYER, {1: 1}).thread
        with mock.patch.object(trade_service, "post_to_channel", side_effect=RuntimeError("boom")):
            self.press(mine, BUYER, RECEIVE, self.ref_of(mine))

        self.assertIn("交易紀錄沒能自動保存，請通知管理員。", mine.sent()[-1])
        self.assertTrue(mine.locked)

    def test_long_threads_are_read_to_the_first_order(self):
        mine = self.order(self.thread, BUYER, {1: 2}).thread
        for _ in range(250):
            mine.messages.append(FakeMessage(self.world, next(self.world.ids), BUYER, "聊天"))

        self.press(mine, SELLER, CANCEL, self.ref_of(mine))

        self.assertEqual(self.listing(self.thread).variant(1).taken, 0)

    def test_cancel_returns_every_order_in_the_thread(self):
        mine = self.order(self.thread, BUYER, {1: 2}).thread
        self.order(self.thread, BUYER, {1: 1, 2: 1})  # 加購
        self.assertEqual(self.listing(self.thread).variant(1).taken, 3)

        self.press(mine, SELLER, CANCEL, self.ref_of(mine))

        listing = self.listing(self.thread)
        self.assertEqual((listing.variant(1).taken, listing.variant(2).taken), (0, 0))
        self.assertIn("預留的數量會還回", mine.sent()[-1])
        self.assertNotIn("thread", mine.sent()[-1])


class PreorderTests(ShopTestCase):

    def setUp(self):
        super().setUp()
        self.thread = self.list_item()
        self.add(self.thread, f"6480 月相｜3000｜3｜{self.cutoff_text(days=1)}", "60 月相｜30｜｜")
        self.cutoff = self.listing(self.thread).variant(1).cutoff
        self.pre = self.order(self.thread, BUYER, {1: 1}).thread
        self.instant = self.order(self.thread, BUYER_B, {2: 1}).thread

    def run_cutoffs(self, shop=None):
        return self.call((shop or self.shop).run_preorder_cutoffs(self.world.now))

    def test_cutoff_reminds_open_trades_once(self):
        self.world.advance(hours=12)
        self.assertEqual(self.run_cutoffs(), self.cutoff)

        self.world.advance(days=1)
        self.run_cutoffs()

        reminder = self.pre.sent()[-1]
        self.assertIn("⏰", reminder)
        self.assertIn(BUYER.mention, reminder)
        self.assertIn(SELLER.mention, reminder)
        self.assertNotIn("⏰", self.instant.sent()[-1])
        self.assertTrue(self.listing(self.thread).variant(1).closed)
        self.assertEqual(self.thread.tag_names(), [])
        count = len(self.pre.messages)
        _, restarted = self.services()
        self.run_cutoffs(restarted)
        self.assertEqual(len(self.pre.messages), count)
        with self.assertRaises(ShopError):
            self.call(self.shop.check_pick(self.thread.id, OUTSIDER, [1]))

    def test_archived_listing_is_still_found(self):
        self.thread.auto_archive()
        self.world.advance(days=2)

        self.run_cutoffs()

        self.assertIn("⏰", self.pre.sent()[-1])
        self.assertTrue(self.listing(self.thread).variant(1).closed)
        self.assertTrue(self.thread.archived)  # 改之前解除封存，改完封存回去

    def test_closed_listing_still_reminds(self):
        self.call(self.shop.close_listing(self.thread.id, SELLER))
        self.world.advance(days=2)

        self.run_cutoffs()

        self.assertIn("⏰", self.pre.sent()[-1])
        self.assertTrue(self.thread.archived and self.thread.locked)

    def test_one_failed_reminder_does_not_repeat_the_others(self):
        other = self.order(self.thread, SUPPLIER_B, {1: 1}).thread

        async def broken(*args, **kwargs):
            raise discord.HTTPException(mock.MagicMock(status=500), "send failed")

        self.pre.send = broken
        self.world.advance(days=2)
        with self.assertLogs(shop_service.logger, level="ERROR"):
            self.run_cutoffs()
        self.assertIn("⏰", other.sent()[-1])
        count = len(other.messages)

        self.run_cutoffs()

        self.assertEqual(len(other.messages), count)
        self.assertTrue(self.listing(self.thread).variant(1).closed)


class GuideTests(ShopTestCase):

    def setUp(self):
        super().setUp()
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.banner = Path(folder.name) / "banner.jpg"
        self.banner.write_bytes(b"first banner")
        self.use_banner(self.banner)

    def use_banner(self, path):
        self.shop.settings = ShopSettings(guide_image=str(path))  # 絕對路徑：不靠 repo 裡真的那張圖

    def banner_name(self, message):
        return message.embed.image.url.removeprefix("attachment://") if message.embed.image.url else None

    def test_guide_is_posted_with_the_banner(self):
        self.call(self.shop.ensure_guide(self.forum))
        starter = self.posts[-1].messages[0]
        (upload,) = starter.files
        self.assertTrue(upload.filename.startswith("guide_") and upload.filename.endswith(".jpg"))
        self.assertEqual(self.banner_name(starter), upload.filename)  # 說明裡顯示的就是這張附件

    def test_rebinding_adds_the_banner_to_an_old_guide_and_only_reuploads_a_new_one(self):
        self.use_banner(self.banner.with_name("missing.jpg"))
        with self.assertLogs(shop_service.logger, level="WARNING"):  # 圖檔不在：只發文字、留 log
            self.call(self.shop.ensure_guide(self.forum))
        starter = self.posts[-1].messages[0]
        self.assertIsNone(self.banner_name(starter))

        self.use_banner(self.banner)
        self.call(self.shop.ensure_guide(self.forum))
        (upload,) = starter.edits[-1]["attachments"]
        self.assertEqual(self.banner_name(starter), upload.filename)
        self.assertEqual(starter.components[0].children[0].custom_id, shop_commands.GUIDE_CUSTOM_ID)

        edits = len(starter.edits)
        self.call(self.shop.ensure_guide(self.forum))  # 同一張圖：不重傳
        self.assertEqual(len(starter.edits), edits)

        first = self.banner_name(starter)
        self.banner.write_bytes(b"second banner")  # 換了圖：檔名跟著變，重傳
        self.call(self.shop.ensure_guide(self.forum))
        (upload,) = starter.edits[-1]["attachments"]
        self.assertNotEqual(upload.filename, first)
        self.assertEqual(self.banner_name(starter), upload.filename)

    def test_missing_banner_keeps_the_one_already_posted(self):
        self.call(self.shop.ensure_guide(self.forum))
        starter = self.posts[-1].messages[0]
        posted = self.banner_name(starter)
        self.use_banner(self.banner.with_name("missing.jpg"))

        with self.assertLogs(shop_service.logger, level="WARNING"):
            self.call(self.shop.ensure_guide(self.forum))

        self.assertEqual(starter.edits, [])
        self.assertEqual(self.banner_name(starter), posted)

    def test_guide_is_posted_and_pinned_once(self):
        note = self.call(self.shop.ensure_guide(self.forum))
        guide = self.posts[-1]
        self.assertEqual(guide.name, "📌 上架說明")
        self.assertTrue(guide.flags.pinned)
        self.assertIn(guide.jump_url, note)
        self.assertEqual(guide.messages[0].components[0].children[0].custom_id, shop_commands.GUIDE_CUSTOM_ID)
        self.assertNotIn("thread", guide.messages[0].embed.description)

        guide.auto_archive()
        self.call(self.shop.ensure_guide(self.forum))

        self.assertEqual(len(self.posts), 1)
        self.assertFalse(guide.archived)
        self.assertEqual([t.name for t in self.forum.available_tags], ["預購中"])

    def test_rebinding_refreshes_outdated_guide_text(self):
        self.call(self.shop.ensure_guide(self.forum))
        guide = self.posts[-1]
        starter = guide.messages[0]
        starter.embed.description = "舊版說明：到商品貼文加入品相"
        guide.auto_archive()  # 置頂文也可能被自動封存，封存中改不了訊息

        note = self.call(self.shop.ensure_guide(self.forum))

        self.assertEqual(len(self.posts), 1)
        self.assertIn("品項", starter.embed.description)
        self.assertNotIn("品相", starter.embed.description)
        self.assertEqual(starter.edits[-1]["attachments"], "unchanged")  # 圖沒換就不動附件
        self.assertEqual(starter.components[0].children[0].custom_id, shop_commands.GUIDE_CUSTOM_ID)
        self.assertIn("已更新", note)

        edits = len(starter.edits)
        self.call(self.shop.ensure_guide(self.forum))  # 已經是最新版就不再改
        self.assertEqual(len(starter.edits), edits)

    def test_missing_tag_permission_is_reported(self):
        async def refuse(**kwargs):
            raise discord.Forbidden(mock.MagicMock(status=403), "Missing Permissions")

        self.forum.create_tag = refuse
        note = self.call(self.shop.ensure_guide(self.forum))
        self.assertIn("⚠️", note)
        self.assertIn("預購中", note)


class ServerNicknameTests(ShopTestCase):

    def test_seller_name_comes_from_the_server_when_the_cache_misses(self):
        thread = self.list_item()
        self.world.cached = set()

        self.add(thread, "60 月相｜30｜10｜")

        self.assertEqual(thread.messages[0].embed.author.name, f"上架者：{SELLER.display_name}")
        self.assertIn(SELLER.id, self.world.api_lookups)


class PanelRedrawTests(ShopTestCase):

    def setUp(self):
        super().setUp()
        self.thread = self.list_item()
        self.add(self.thread, "60 月相｜30｜10｜", "寰宇電台｜20｜｜")
        p = mock.patch.object(shop_commands, "safe_send_interaction_message", mock.AsyncMock())
        self.sent_ephemeral = p.start()
        self.addCleanup(p.stop)

    def interaction(self, user=SELLER, message=None):
        return SimpleNamespace(
            client=SimpleNamespace(get_cog=lambda name: SimpleNamespace(shop=self.shop)),
            user=user, guild=self.world.guild, channel=self.thread, message=message,
            response=SimpleNamespace(defer=mock.AsyncMock(), edit_message=mock.AsyncMock(),
                                     send_modal=mock.AsyncMock(), is_done=lambda: True),
            edit_original_response=mock.AsyncMock(),
        )

    def assert_panel_redrawn(self, interaction, text):
        kwargs = interaction.edit_original_response.await_args.kwargs
        self.assertIn(text, kwargs["content"])
        picks = [c for c in kwargs["view"].children if isinstance(c, shop_commands.ShopPickSelect)]
        self.assertEqual(len(picks), 2)  # 重畫出新的選單＝回到未選取
        return kwargs

    def test_confirming_an_order_points_to_the_conversation(self):
        pressing = self.interaction(user=BUYER)
        self.call(shop_commands.ShopConfirmOrder(self.thread.id, {1: 1}).callback(pressing))
        text = pressing.edit_original_response.await_args.kwargs["content"]
        self.assertTrue(text.startswith("已下單，請到交易對話跟上架者確認細節："), text)
        self.assertNotIn("thread", text)

    def test_panel_marks_unavailable_items_like_the_listing(self):
        self.add(self.thread, "一條龍｜40｜1｜")
        self.order(self.thread, BUYER, {3: 1})
        description = shop_commands._panel_embed(self.listing(self.thread)).description
        self.assertIn("一條龍｜~~NT$40｜立即購買~~ `已售完`", description)

    def test_buy_menu_is_cleared_as_soon_as_the_quantity_form_opens(self):
        message = self.thread.messages[0]
        before = len(message.edits)

        async def run():
            listing = self.listing(self.thread)
            select = shop_commands.ShopBuySelect(self.thread.id, options=[
                discord.SelectOption(label=v.name, value=v.encode()) for v in listing.variants], max_values=2)
            select.item._values = [listing.variant(2).encode()]
            interaction = self.interaction(user=BUYER, message=message)
            await select.callback(interaction)
            return interaction

        interaction = self.call(run())

        modal = interaction.response.send_modal.await_args.args[0]
        self.assertEqual([key for key, _, _ in modal.inputs], [2])  # 視窗問的是剛選的商品
        self.assertEqual(len(message.edits), before + 1)  # 商品貼文重畫＝選單清空，取消後還能再選

    def test_editing_a_variant_redraws_the_panel(self):
        async def run():
            listing = self.listing(self.thread)
            modal = shop_commands.VariantModal(self.thread.id, listing.variant(1))
            modal.name._value, modal.price._value, modal.limit._value, modal.cutoff._value = "60 月相", "35", "10", ""
            modal.kind._values = ["instant"]
            interaction = self.interaction()
            await modal.on_submit(interaction)
            return interaction

        interaction = self.call(run())

        interaction.response.defer.assert_awaited_once_with()  # 延後回應＝之後改的是面板那則
        kwargs = self.assert_panel_redrawn(interaction, "已更新")
        self.assertIn("NT$35", kwargs["embed"].description)
        self.assertEqual(self.listing(self.thread).variant(1).price, 35)

    def test_delete_confirmation_stays_in_the_panel(self):
        async def run():
            listing = self.listing(self.thread)
            pick = shop_commands._panel_view(listing).children[-1]  # 刪除品項選單
            pick.item._values = [pick.item.options[1].value]
            asking = self.interaction()
            await pick.callback(asking)
            confirm = asking.response.edit_message.await_args.kwargs["view"].children[0]
            doing = self.interaction()
            await confirm.callback(doing)
            return asking, doing

        asking, doing = self.call(run())

        self.assertIn("寰宇電台", asking.response.edit_message.await_args.kwargs["content"])
        self.assert_panel_redrawn(doing, "已刪除")
        self.assertEqual([v.name for v in self.listing(self.thread).variants], ["60 月相"])

    def choose_to_edit(self, choosing):
        async def run():
            pick = shop_commands._panel_view(self.listing(self.thread)).children[-2]  # 編輯品項選單
            pick.item._values = [pick.item.options[0].value]
            await pick.callback(choosing)
        self.call(run())

    def panel_picks(self, call):
        return [c for c in call.kwargs["view"].children if isinstance(c, shop_commands.ShopPickSelect)]

    def test_edit_menu_opens_the_form_and_clears_the_panel(self):
        choosing = self.interaction()
        # 重畫一定在跳出視窗之後：互動只能回應一次，先改面板視窗就跳不出來
        choosing.edit_original_response.side_effect = \
            lambda **kw: self.assertEqual(choosing.response.send_modal.await_count, 1)

        self.choose_to_edit(choosing)

        modal = choosing.response.send_modal.await_args.args[0]
        self.assertEqual(modal.name.default, "60 月相")  # 選了就跳出編輯視窗，帶入原本的內容
        self.assertEqual(len(self.panel_picks(choosing.edit_original_response.await_args)), 2)  # 選單回到未選取

    def test_panel_is_cleared_through_the_message_when_the_original_response_fails(self):
        choosing = self.interaction(message=SimpleNamespace(id=4242))
        choosing.edit_original_response.side_effect = discord.NotFound(mock.MagicMock(status=404), "Unknown Message")
        choosing.followup = SimpleNamespace(edit_message=mock.AsyncMock())

        self.choose_to_edit(choosing)

        call = choosing.followup.edit_message.await_args
        self.assertEqual(call.args[0], 4242)
        self.assertEqual(len(self.panel_picks(call)), 2)

    def test_panel_that_cannot_be_cleared_is_only_logged(self):
        choosing = self.interaction(message=SimpleNamespace(id=4242))
        refused = discord.NotFound(mock.MagicMock(status=404), "Unknown Message")
        choosing.edit_original_response.side_effect = refused
        choosing.followup = SimpleNamespace(edit_message=mock.AsyncMock(side_effect=refused))

        with self.assertLogs(shop_commands.logger, level="WARNING"):
            self.choose_to_edit(choosing)  # 不丟例外：視窗已經跳出，上架者照常編輯

        choosing.response.send_modal.assert_awaited_once()


class LayeringTests(unittest.TestCase):

    def test_shop_service_does_not_import_commands(self):
        for module in (shop_service, sys.modules["services.community.shop_listing"]):
            tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
            names = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
            names |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
            with self.subTest(module.__name__):
                self.assertFalse([n for n in names if n.split(".")[0] == "commands"])

    def test_custom_ids_resolve_back(self):
        async def check():
            cases = [
                shop_commands.ShopManageButton(21, 7, "PY:幣"),
                shop_commands.ShopConfirmOrder(500, {1: 2, 3: 1}),
                shop_commands.ShopPanelButton("batch", 500),
                shop_commands.ShopConfirmButton("delete", 500, 7),
                shop_commands.ShopConfirmButton("close", 500),
                shop_commands.ShopBatchButton("fix", 500),
                shop_commands.ShopBuySelect(500, options=[discord.SelectOption(label="x", value="1:2:::0:0")]),
            ]
            for original in cases:
                cls = type(original)
                match = cls.__discord_ui_compiled_template__.fullmatch(original.item.custom_id)
                self.assertIsNotNone(match, original.item.custom_id)
                restored = await cls.from_custom_id(None, original.item, match)
                self.assertEqual(restored.item.custom_id, original.item.custom_id)
                self.assertLessEqual(len(original.item.custom_id), 100)
            self.assertEqual(cases[1].picks, (await shop_commands.ShopConfirmOrder.from_custom_id(
                None, cases[1].item,
                shop_commands.ShopConfirmOrder.__discord_ui_compiled_template__.fullmatch(cases[1].item.custom_id))).picks)

        asyncio.run(check())

    def test_panel_menus_carry_the_variant(self):
        from services.community.shop_listing import Listing
        from datetime import datetime, timezone

        async def check():
            variant = Variant(3, "6480 月相", 3000, limit=3, taken=1,
                              cutoff=datetime(2099, 10, 20, 15, 59, tzinfo=timezone.utc))
            listing = Listing(thread_id=500, owner_id=21, unit="NT$", title="t", description="", variants=(variant,))
            view = shop_commands._panel_view(listing)
            picks = [c for c in view.children if isinstance(c, shop_commands.ShopPickSelect)]
            self.assertEqual([p.item.custom_id for p in picks], ["shop:pick:edit:500", "shop:pick:delete:500"])
            option = picks[0].item.options[0]
            self.assertEqual(Variant.decode(option.value, option.label.split(". ", 1)[-1]), variant)

        asyncio.run(check())

    def test_modals_stay_within_discord_limits(self):
        """欄位標題 45 字、欄位描述 100 字、一張 modal 最多 5 個欄位；超過的話 Discord 直接拒絕，modal 打不開。"""
        from services.community.shop_listing import Listing

        async def check():
            variant = Variant(1, "6480 月相", 3000, limit=3)
            listing = Listing(thread_id=500, owner_id=21, unit="NT$", title="t", description="", variants=(variant,))
            modals = [shop_commands.BatchModal(500, "a｜1"), shop_commands.VariantModal(500),
                      shop_commands.VariantModal(500, variant), shop_commands.ListingInfoModal(),
                      shop_commands.ListingInfoModal(listing=listing), shop_commands.QuantityModal(500, [variant])]
            for modal in modals:
                rows = modal.to_components()
                with self.subTest(type(modal).__name__):
                    self.assertLessEqual(len(rows), 5)
                    self.assertLessEqual(len(modal.title), 45)
                    for row in rows:
                        self.assertLessEqual(len(row.get("label") or ""), 45)
                        self.assertLessEqual(len(row.get("description") or ""), 100)
                        self.assertLessEqual(len(row.get("content") or ""), 4000)

        asyncio.run(check())

    def test_batch_preview_round_trip(self):
        async def check():
            text = "6480 月相｜3000｜3｜2099/10/20 23:59\n寰宇電台｜20"
            embed, view = shop_commands._batch_preview(500, text)
            restored = shop_commands._preview_text(SimpleNamespace(embeds=[embed]))
            self.assertEqual(parse_batch(restored, now=shop_commands._now()), parse_batch(text, now=shop_commands._now()))
            self.assertEqual([c.item.custom_id for c in view.children], ["shop:batchok:500", "shop:batchfix:500"])
            bad, bad_view = shop_commands._batch_preview(500, "壞掉的一行")
            self.assertIn("第 1 行", bad.description)
            self.assertEqual([c.item.custom_id for c in bad_view.children], ["shop:batchfix:500"])

        asyncio.run(check())

    def test_cog_wires_the_listing_source_into_trades(self):
        async def check():
            trade = TradeService(mock.MagicMock(), make_view=_make_view)
            bot = mock.MagicMock()
            bot.get_cog.return_value = SimpleNamespace(trade=trade)
            bot.wait_until_ready = mock.AsyncMock()
            cog = shop_commands.ShopCommands(bot)
            with mock.patch.object(shop_commands, "run_due_loop", new=mock.MagicMock(
                    side_effect=lambda *a, **k: asyncio.sleep(3600))) as loop_call:
                await cog.cog_load()
            try:
                self.assertIs(cog.shop.trade, trade)
                self.assertTrue(any(isinstance(k, ListingSource) for k in trade._kinds))
                bot.add_dynamic_items.assert_called_once()
                bot.add_view.assert_called_once()
                # 預購截止的排程跟著品項新增、編輯提早醒來
                self.assertIs(loop_call.call_args.kwargs["wake"], cog.shop.cutoffs_changed)
            finally:
                await cog.cog_unload()

        asyncio.run(check())


if __name__ == "__main__":
    unittest.main()
