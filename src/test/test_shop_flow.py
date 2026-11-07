"""商品上架與商品交易（shop_service、shop_trade、market_import ＋ commands.shop_commands ＋ 交易模組），正本在市集資料庫。

用真的交易模組、真的 Discord 元件與暫存的資料庫，只把 Discord 本身換成假的伺服器（沿用 test_trade_flow 的 World）。

守的底線：
  1. 上架：只有觀星者；bot 代發商品貼文（標題、說明、供應方暱稱、商品圖換固定檔名並由 embed 引用第一張），
     資料庫記下這篇（交付方式預設實體）；幣別有數字、太長、不是圖、圖太大、論壇沒綁都在發文前擋下並說明；
     寫資料庫失敗就把貼文刪掉。商品圖照使用者選的順序（第一張當大圖）。上架與編輯視窗的欄位順序是
     標題、幣別、交付方式、商品圖、說明。
  2. 管理：只有供應方或管理員（含群主）；購買選單的選項只帶品項編號；有預購或收定金就掛「預購中」；最多 25 個；
     品項編號不重用；編輯時數量是「剩餘數量」；定金品項不能和一次付清的放同一篇；交易中的品項不能改類型、
     改價格只影響之後的新訂單（回覆說已下單的照原金額）；有人下單後截止時間鎖住；有交易時不能改交付方式、
     不能刪那個品項；還有定金或預購的交易沒做完不能下架；下架後選單與按鈕停用、標題【已下架】、鎖定。
  3. 下單：不能買自己的；一次最多 5 種；賣完、截止、停收定金、超過剩餘都擋下；確認畫面之後價格改了就擋下重新確認；
     開出只有需求方與供應方的交易對話，資料庫記下這次下單的品項與下單當時的金額；訂單明細不 @ 人（加購 @ 供應方一次）；
     交易進度卡列出每個品項的狀態與這一步能按的按鈕；同一位需求方加購沿用對話、作廢原本的領收通知、
     上一張交易進度的按鈕收起來；另一位需求方各開一個；已取消的對話不再收訂單；開不起來就什麼都不留。
  4. 交易進度：錢只由供應方確認，需求方「我已付」只 @ 供應方；每個品項的錢收齊才能交付；數位全部交付後自動發領收通知，
     實體寄出後需求方每個品項按已收到、全部收到就完成；按錯人、重複按都不記兩次；「通知需求方領收」＝剩下的一起交付，
     錢沒收齊照擋；需求方還沒領收後，供應方再按一次就重新通知。
  5. 定金＋尾款：確認定金後等貨；開始收尾款停收定金、照每筆下單時的尾款在每個對話請款（定金還沒確認的請供應方先確認）；
     做到一半重啟，排程補發沒發出去的；取消時有已收的款先確認，取消訊息與私訊提醒「定金已付」，
     沒交付、沒寄出的數量還回商品，已寄出的不還。
  6. 截止：一次付清的預購截止時在每個對話 @ 雙方可以開始交貨，只通知一次（重啟也不重複，一個對話發不出去不影響別人）；
     定金截止只停收定金、不 @ 人；「開始交貨」提早截止；延期只能往後：還沒截止就延長收單，已截止只設預計交貨日，@ 需求方。
  7. 等待提醒：需求方沒付款 3 天後在對話裡 @ 他、記在資料庫不重發；上線前的舊交易不提醒。
  8. 上線匯入：舊商品貼文與還開著的交易一次搬進資料庫（交付方式一律實體），已下單數量不變，貼文改畫成新格式；
     商品的舊交易接上新流程、補發交易進度（不 @ 人、舊的領收通知作廢），【定金】商品的等整篇改成定金＋尾款才接，
     自由市場的照舊流程；匯入完才開放按鈕；重跑不重複；失敗時按鈕維持擋住。改成定金＋尾款的表單品項不多時每個品項一格、
     格子底下寫出定金；填錯的整張不存；改好之前不能拿掉標題開頭的【定金】。
  9. 置頂上架說明：綁定時發一篇並置頂、建好「預購中」標籤；說明或按鈕改過時重綁會更新；橫幅圖換了才重傳。
 10. 名字一律是伺服器暱稱；給群友看的字是品項、供應方、需求方，不說 thread、上架者、買家。
 11. 分層與元件：商品模組不 import 指令層；按鈕與選單的 custom_id 解析得回同一個動作（舊貼文的管理按鈕也認得）；
     表單都在 Discord 的上限內；管理面板最多 5 列，延期、開始收尾款或開始交貨只在用得到時出現。
"""

import ast
import asyncio
import itertools
import json
import os
import re
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
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
from services.community import market_import, market_report, shop_service, shop_trade, trade_service  # noqa: E402
from services.community import trade_progress as tp  # noqa: E402
from services.community.shop_listing import ShopError, Variant, parse_batch, parse_draft  # noqa: E402
from services.community import market_transition  # noqa: E402
from services.community.shop_service import PriceChanged, ShopService  # noqa: E402
import services.community.shop_listing as shop_listing_module  # noqa: E402
from services.community.trade_service import CANCEL, CANCEL_OK, HOLD, NOTIFY, RECEIVE, TradeRef, TradeService  # noqa: E402
from sys_settings.shop_settings import ShopSettings  # noqa: E402
from sys_settings.switches import Switches  # noqa: E402
from test.test_trade_flow import (  # noqa: E402  只拿假物件，不拿 TestCase（免得被重跑）
    ARCHIVE_ID, BOT, CART_ID, FORUM_ID, OUTSIDER, OWNER, REQUESTER, SUPPLIER, SUPPLIER_B,
    FakeMessage, FakeThread, MarketTestMixin, World, _make_view,
)

SHOP_ID = 400
SELLER = SUPPLIER          # 供應方（Trader）
BUYER = REQUESTER
BUYER_B = OUTSIDER
TRADERS = {SUPPLIER.id, SUPPLIER_B.id}


class ShopForum:
    """商品論壇。標籤照真的 discord.py：`edit(available_tags=)` 整份覆寫 Discord 上的清單，
    本地的 `available_tags` 是快取，要等 Discord 推送頻道更新才跟上（stale_cache 時不自動跟上，用 sync_cache）；
    `guild.fetch_channel` 拿到的是 Discord 上最新的。"""

    def __init__(self, world):
        self.world = world
        self.id = SHOP_ID
        self.guild = world.guild
        self.available_tags = []
        self.server_tags = []      # Discord 上真正的標籤清單
        self.stale_cache = False
        self.tag_edits = 0
        self.fetches = 0
        self.all_threads = []
        self._tag_ids = itertools.count(900)
        self.fail_archived = False

    @property
    def threads(self):
        return [t for t in self.all_threads if not t.archived]

    async def archived_threads(self, *, limit=100):
        if self.fail_archived:
            raise discord.HTTPException(mock.MagicMock(status=500), "archived threads failed")
        for thread in sorted((t for t in self.all_threads if t.archived),
                             key=lambda t: t.archive_timestamp, reverse=True):
            yield thread

    async def create_tag(self, *, name):
        raise AssertionError("create_tag 拿快取整份覆寫、建完不更新快取，連著建會互相蓋掉，要用 edit 一次送")

    async def edit(self, *, available_tags):
        self.tag_edits += 1
        tags = []
        for tag in available_tags:
            if not tag.id:
                tag = discord.ForumTag(name=tag.name)
                tag.id = next(self._tag_ids)
            tags.append(tag)
        self.server_tags = tags
        if not self.stale_cache:
            self.sync_cache()
        return SimpleNamespace(available_tags=list(tags))

    def sync_cache(self):
        self.available_tags = list(self.server_tags)

    async def fetch(self):
        self.fetches += 1
        return SimpleNamespace(id=self.id, guild=self.guild, available_tags=list(self.server_tags), edit=self.edit)


class ForumThread(FakeThread):
    """商品論壇裡的貼文（商品、置頂說明）。"""

    def __init__(self, world, tid, name, forum, owner_id):
        super().__init__(world, tid, name, parent_id=forum.id)
        self.parent = forum
        self.owner_id = owner_id
        self.applied_tags = []
        self.flags = SimpleNamespace(pinned=False)

    async def edit(self, **kwargs):
        self.check_editable(kwargs)
        if "applied_tags" in kwargs:
            self.applied_tags = list(kwargs.pop("applied_tags"))
        if "pinned" in kwargs:
            self.flags.pinned = kwargs.pop("pinned")
        if "auto_archive_duration" in kwargs:
            self.auto_archive_duration = kwargs.pop("auto_archive_duration")
        await super().edit(**kwargs)

    async def delete(self):
        self.deleted = True
        self.world.channels.pop(self.id, None)
        if self in self.parent.all_threads:
            self.parent.all_threads.remove(self)

    def tag_names(self):
        return [t.name for t in self.applied_tags]


class FakeAttachment:
    def __init__(self, filename, content_type="image/png", size=1000):
        self.filename = filename
        self.content_type = content_type
        self.size = size

    async def to_file(self, *, filename):
        return SimpleNamespace(filename=filename, source=self.filename)


class ShopTestCase(MarketTestMixin, unittest.TestCase):
    def setUp(self):
        self.world = World()
        self.start_market()
        self.forum = ShopForum(self.world)
        self.world.channels[SHOP_ID] = self.forum

        async def fetch_channel(channel_id):
            assert channel_id == SHOP_ID, channel_id
            return await self.forum.fetch()

        self.world.guild.fetch_channel = fetch_channel
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
        self.dms = mock.AsyncMock(name="send_dm", return_value=True)
        exports = tempfile.TemporaryDirectory()
        self.addCleanup(exports.cleanup)
        self.exports = Path(exports.name)
        for p in (
            mock.patch.object(market_import, "MARKET_BACKUP_DIR", self.exports),
            mock.patch.object(trade_service.ChannelConfig, "get_configured_id", side_effect=get_configured_id),
            mock.patch.object(shop_service.ChannelConfig, "get_configured_id", side_effect=get_configured_id),
            mock.patch.object(trade_service, "check_role", side_effect=check_role),
            mock.patch.object(shop_service, "check_role", side_effect=check_role),
            mock.patch.object(trade_service, "post_to_channel", side_effect=trade_post),
            mock.patch.object(shop_service, "post_to_channel", side_effect=shop_post),
            mock.patch.object(trade_service, "safe_send_interaction_message", self.ephemeral),
            mock.patch.object(trade_service, "send_dm", self.dms),
        ):
            p.start()
            self.addCleanup(p.stop)
        self.trade, self.shop = self.services()

    def call(self, coro):
        """跑完再等商品服務在背景改完貼文標題（下架、改標題），斷言才看得到結果。"""
        result = super().call(coro)
        shop = getattr(self, "shop", None)
        if shop is not None:
            super().call(shop.settle())
        return result

    def services(self, *, ready=True):
        """新的服務實例＝模擬 bot 重啟：記憶體裡什麼都沒有，只剩資料庫與 Discord 上的東西。"""
        trade = TradeService(self.world.bot, make_view=_make_view, db=self.get_db, now=lambda: self.world.now)
        if ready:
            trade.ready.set()
        shop = ShopService(self.world.bot, trade=trade, views=DiscordShopViews(ShopSettings()),
                           now=lambda: self.world.now)
        trade.add_source_kind(shop.source)
        return trade, shop

    # ── 操作捷徑 ──

    def list_item(self, seller=SELLER, title="月相代儲", attachments=(), unit="", delivery="digital"):
        return self.call(self.shop.create_listing(seller, title=title, description="交付方式：遊戲內交易",
                                                  unit=unit, delivery=delivery, attachments=attachments))

    def add(self, thread, *lines, actor=SELLER):
        drafts, errors = parse_batch("\n".join(lines), now=self.world.now)
        assert not errors, errors
        return self.call(self.shop.add_variants(thread.id, actor, drafts))

    def listing(self, thread):
        return self.call(self.shop.load(thread.id))

    def order(self, thread, buyer, picks):
        return self.call(self.shop.place_order(thread.id, buyer, picks)).thread

    def cutoff_text(self, **delta):
        moment = (self.world.now + timedelta(**delta)).astimezone(shop_service.APP_TZ)
        return moment.strftime("%Y/%m/%d %H:%M")

    def step(self, trade_thread, user, action, key=None):
        """像真的按交易進度上的按鈕：帶著那張卡按鈕上的版本（卡上沒有這顆按鈕就不帶）。"""
        wanted = shop_trade.step_custom_id(action, key)
        version = None
        try:
            for custom_id in self.card_buttons(trade_thread, with_version=True):
                if re.sub(r":v\d+$", "", custom_id) == wanted and ":v" in custom_id:
                    version = int(custom_id.rsplit(":v", 1)[1])
        except StopIteration:
            pass
        return self.call(self.shop.trades.handle_step(user, trade_thread, action, key, version))

    def press(self, trade_thread, user, action):
        interaction = self.interaction(user, trade_thread)
        self.call(self.trade.handle_button(interaction, action, TradeRef(0, 0, 0)))
        return interaction

    def out_of_reach(self, trade_thread):
        """這個交易對話一時取不到（不在快取、Discord 回 5xx）；回傳恢復的函式。"""
        self.world.channels.pop(trade_thread.id)
        real_fetch = self.world.bot.fetch_channel

        async def hiccup(channel_id):
            if channel_id == trade_thread.id:
                raise discord.HTTPException(mock.MagicMock(status=503), "Service Unavailable")
            return await real_fetch(channel_id)

        self.world.bot.fetch_channel = hiccup

        def back():
            self.world.channels[trade_thread.id] = trade_thread
            self.world.bot.fetch_channel = real_fetch

        return back

    def card(self, trade_thread):
        return next(m for m in reversed(trade_thread.messages) if m.embed is not None and m.embed.title == "交易進度")

    def card_buttons(self, trade_thread, *, with_version=False):
        """交易進度上的按鈕 custom_id；平常拿掉結尾的卡片版本（:v編號）比較好讀。"""
        ids = [c.custom_id for row in self.card(trade_thread).components for c in row.children]
        return ids if with_version else [re.sub(r":v\d+$", "", i) for i in ids]

    def taken(self, thread, key):
        return self.listing(thread).variant(key).taken

    def edit(self, thread, key, name, price, limit, cutoff, kind):
        draft = parse_draft(name, price, limit, cutoff, kind=kind, now=self.world.now, min_limit=0,
                            allow_unused_cutoff=True)
        return self.call(self.shop.edit_variant(thread.id, SELLER, key, draft))

    def buy_menu(self, thread):
        return next(c for c in thread.messages[0].components[0].children if isinstance(c, discord.ui.Select))


class ListingCreateTests(ShopTestCase):

    def test_only_sellers_can_list(self):
        with self.assertRaises(ShopError):
            self.list_item(seller=BUYER)
        self.assertEqual(self.posts, [])

    def test_listing_post_and_record(self):
        thread = self.call(self.shop.create_listing(
            SELLER, title="月相代儲", description="說明", unit="",
            attachments=[FakeAttachment("a.PNG"), FakeAttachment("b.jpg", "image/jpeg")]))

        message = thread.messages[0]
        self.assertEqual(thread.name, "月相代儲")
        self.assertEqual(message.embed.author.name, f"供應方：{SELLER.display_name}")
        self.assertEqual([f.filename for f in message.files], ["item_1.png", "item_2.jpg"])
        self.assertEqual(message.embed.image.url, "attachment://item_1.png")
        row = self.call(self.db.get_listing(thread.id))
        self.assertEqual((row.owner_id, row.unit, row.delivery, row.image), (SELLER.id, "NT$", "physical", "item_1.png"))
        self.assertEqual([c.custom_id for c in message.components[0].children], ["shop:manage"])  # 只有管理按鈕
        self.assertEqual(thread.auto_archive_duration, 10080)

    def test_rejections_explain_why(self):
        cases = {
            "不是圖片": dict(attachments=[FakeAttachment("x.pdf", "application/pdf")]),
            "太大": dict(attachments=[FakeAttachment("big.png", size=50 * 1024 * 1024)]),
            "不能有數字": dict(unit="NT$100"),
            "最多 10 個字": dict(unit="鳴潮遊戲內星聲幣專用代幣"),
        }
        for reason, kwargs in cases.items():
            with self.subTest(reason), self.assertRaises(ShopError) as caught:
                self.list_item(**kwargs)
            self.assertIn(reason, str(caught.exception))
        self.assertEqual(self.posts, [])
        del self.config["shop_forum_channel_id"]
        with self.assertRaises(ShopError) as caught:
            self.list_item()
        self.assertIn("/server_manager", str(caught.exception))

    def test_database_failure_deletes_the_post(self):
        with mock.patch.object(type(self.db), "insert_listing", side_effect=RuntimeError("disk full")):
            with self.assertRaises(RuntimeError):
                self.list_item()
        self.assertTrue(self.posts[0].deleted)
        self.assertEqual(self.call(self.db.listings()), [])


class UploadOrderTests(unittest.TestCase):
    """表單上傳的商品圖：交給服務層的順序＝使用者選的順序，不是 discord.py 給的順序。"""

    @staticmethod
    def submit(modal, selected, resolved_order):
        """照 discord.py 處理表單送出的方式把上傳元件填好：元件帶選的順序，附件對照表是另一個順序。"""
        from discord.app_commands.namespace import ResolveKey

        components = [{"type": 18, "component": {"type": 19, "custom_id": modal.images.custom_id,
                                                 "values": [str(i) for i in selected]}}]
        resolved = {ResolveKey(id=str(i), type=-1): SimpleNamespace(id=i) for i in resolved_order}
        interaction = SimpleNamespace(data={"components": components})
        modal._refresh(interaction, components, resolved)
        return interaction

    def test_images_follow_the_selected_order(self):
        async def check():
            modal = shop_commands.ListingInfoModal()
            interaction = self.submit(modal, selected=[11, 12, 13], resolved_order=[13, 12, 11])
            return [a.id for a in shop_commands._uploaded_in_order(interaction, modal.images)]

        self.assertEqual(asyncio.run(check()), [11, 12, 13])

    def test_without_the_selected_order_keep_what_arrived(self):
        async def check():
            modal = shop_commands.ListingInfoModal()
            self.submit(modal, selected=[11, 12], resolved_order=[12, 11])
            bare = SimpleNamespace(data={"components": []})
            return [a.id for a in shop_commands._uploaded_in_order(bare, modal.images)]

        self.assertEqual(asyncio.run(check()), [12, 11])

    def test_fields_are_title_unit_delivery_images_description(self):
        from services.community.shop_listing import Listing

        listing = Listing(thread_id=500, owner_id=1, unit="NT$", title="t", description="", variants=())
        expected = {"上架商品": ["標題", "幣別", "交付方式", "商品圖", "說明"],
                    "編輯商品資訊": ["標題", "幣別", "交付方式", "換商品圖", "說明"]}
        for modal in (shop_commands.ListingInfoModal(), shop_commands.ListingInfoModal(listing=listing)):
            labels = [row.get("label") or row["components"][0]["label"] for row in modal.to_components()]
            with self.subTest(modal.title):
                self.assertEqual([label.split("（")[0] for label in labels], expected[modal.title])

    def test_listing_and_editing_both_pass_the_selected_order(self):
        from services.community.shop_listing import Listing

        async def run(editing):
            listing = Listing(thread_id=500, owner_id=1, unit="NT$", title="t", description="", variants=())
            modal = shop_commands.ListingInfoModal(listing=listing if editing else None)
            interaction = self.submit(modal, selected=[21, 22, 23], resolved_order=[23, 22, 21])
            interaction.user = SimpleNamespace(id=1)
            interaction.response = SimpleNamespace(defer=mock.AsyncMock())
            shop = SimpleNamespace(create_listing=mock.AsyncMock(return_value=SimpleNamespace(mention="#x")),
                                   edit_info=mock.AsyncMock(return_value=None))
            with mock.patch.object(shop_commands, "_shop", return_value=shop), \
                    mock.patch.object(shop_commands, "_reply", mock.AsyncMock()), \
                    mock.patch.object(shop_commands, "_show_panel", mock.AsyncMock()):
                await modal.on_submit(interaction)
            called = shop.edit_info if editing else shop.create_listing
            return [a.id for a in called.await_args.kwargs["attachments"]], called.await_args.kwargs["delivery"]

        self.assertEqual(asyncio.run(run(False)), ([21, 22, 23], "physical"))   # 新上架預設實體
        self.assertEqual(asyncio.run(run(True))[0], [21, 22, 23])


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

        select = self.buy_menu(self.thread)
        self.assertEqual([(o.label, o.value) for o in select.options], [("60 月相", "1"), ("6480 月相", "2")])
        self.assertEqual(select.max_values, 2)
        self.assertEqual(len(self.thread.messages[0].embed.fields), 2)
        self.assertEqual(self.thread.tag_names(), ["預購中"])
        # 一般更新不傳附件清單：傳了（就算是空的）Discord 會把 embed 引用的商品圖刪掉
        self.assertEqual(self.thread.messages[0].edits[-1]["attachments"], "unchanged")

    def test_at_most_25_variants(self):
        self.add(self.thread, *[f"品項{n}｜1" for n in range(25)])
        with self.assertRaises(ShopError):
            self.add(self.thread, "多一個｜1")

    def test_deposit_and_one_time_items_cannot_share_a_listing(self):
        self.add(self.thread, f"玩偶A｜500/1300｜10｜{self.cutoff_text(days=20)}",
                 f"玩偶B｜500/1300｜10｜{self.cutoff_text(days=20)}")
        with self.assertRaises(ShopError) as caught:
            self.add(self.thread, "現貨｜100｜｜")
        self.assertIn("另開一篇", str(caught.exception))
        with self.assertRaises(ShopError):
            self.edit(self.thread, 1, "玩偶A", "500", "10", "", "instant")   # 改成一次付清也算混放

    def test_adding_or_editing_wakes_the_cutoff_check(self):
        # 截止時間改到一小時內也要準時處理：新增、編輯品項就叫醒排程重算
        self.add(self.thread, f"6480 月相｜3000｜3｜{self.cutoff_text(minutes=20)}")
        self.assertTrue(self.shop.cutoffs_changed.is_set())
        self.shop.cutoffs_changed.clear()
        self.edit(self.thread, 1, "6480 月相", "3000", "3", self.cutoff_text(minutes=10), "preorder")
        self.assertTrue(self.shop.cutoffs_changed.is_set())

    def test_editing_quantity_means_remaining(self):
        # 編輯時填的是「還要賣幾個」：系統自動加上已下單的
        self.add(self.thread, "60 月相｜30｜4｜")
        self.order(self.thread, BUYER, {1: 2})

        async def modal_default(variant):
            return shop_commands.VariantModal(self.thread.id, variant).limit.default

        def form_default():
            return modal_default(self.listing(self.thread).variant(1))

        self.assertEqual(self.call(form_default()), "2")  # 4 件賣掉 2 件，預填 2
        self.edit(self.thread, 1, "60 月相", "30", "5", "", "instant")
        variant = self.listing(self.thread).variant(1)
        self.assertEqual((variant.taken, variant.limit, variant.remaining), (2, 7, 5))  # 補貨 5 件就填 5
        self.edit(self.thread, 1, "60 月相", "30", "0", "", "instant")
        self.assertEqual(self.listing(self.thread).variant(1).remaining, 0)  # 填 0＝停賣
        self.assertEqual(self.call(form_default()), "0")

    def test_trading_items_keep_their_kind_and_old_prices(self):
        self.add(self.thread, "60 月相｜30｜10｜")
        trade_thread = self.order(self.thread, BUYER, {1: 2})

        with self.assertRaises(ShopError) as caught:
            self.edit(self.thread, 1, "60 月相", "30", "8", self.cutoff_text(days=3), "preorder")
        self.assertIn("交易中不能改類型", str(caught.exception))
        self.assertIn(f"<#{trade_thread.id}>", str(caught.exception))
        _, note = self.edit(self.thread, 1, "60 月相", "35", "8", "", "instant")
        self.assertIn("已下單的 2 份照原本的金額", note)
        (item,) = self.call(self.db.items(trade_thread.id))
        self.assertEqual(item.unit_price, 30)

    def test_cutoff_is_locked_once_someone_ordered(self):
        self.add(self.thread, f"6480 月相｜3000｜3｜{self.cutoff_text(days=3)}")
        before = self.listing(self.thread).variant(1).cutoff
        self.assertFalse(self.shop.cutoff_locked(self.listing(self.thread).variant(1)))
        self.order(self.thread, BUYER, {1: 1})
        variant = self.listing(self.thread).variant(1)
        self.assertTrue(self.shop.cutoff_locked(variant))

        self.edit(self.thread, 1, "6480 月相（改名）", "3000", "2", self.cutoff_text(days=9), "preorder")

        after = self.listing(self.thread).variant(1)
        self.assertEqual((after.name, after.cutoff), ("6480 月相（改名）", before))  # 改日期要走延期

    def test_buy_menu_is_disabled_when_everything_is_sold_out(self):
        self.add(self.thread, "60 月相｜30｜2｜")
        self.order(self.thread, BUYER, {1: 2})

        self.assertTrue(self.buy_menu(self.thread).disabled)
        self.assertEqual(self.buy_menu(self.thread).placeholder, "已售完")
        manage = [c for c in self.thread.messages[0].components[0].children if isinstance(c, discord.ui.Button)]
        self.assertFalse(manage[0].disabled)  # 供應方還要能補貨

        self.edit(self.thread, 1, "60 月相", "30", "3", "", "instant")
        self.assertFalse(self.buy_menu(self.thread).disabled)
        self.assertEqual(self.buy_menu(self.thread).placeholder, "選擇要購買的品項（可多選）")

    def test_deleting(self):
        self.add(self.thread, "60 月相｜30｜10｜", "300 月相｜150｜｜")
        self.order(self.thread, BUYER, {1: 1})
        with self.assertRaises(ShopError):
            self.call(self.shop.delete_variant(self.thread.id, SELLER, 1))  # 有進行中的交易不能刪
        self.call(self.shop.delete_variant(self.thread.id, SELLER, 2))
        self.add(self.thread, "980 月相｜490｜｜")
        self.assertEqual([v.key for v in self.listing(self.thread).variants], [1, 3])  # 編號不重用

    def test_close_listing(self):
        self.add(self.thread, "60 月相｜30｜10｜")
        self.order(self.thread, BUYER, {1: 1})  # 一次付清的現貨交易不擋下架

        self.call(self.shop.close_listing(self.thread.id, SELLER))

        children = self.thread.messages[0].components[0].children
        self.assertTrue(all(c.disabled for c in children))
        self.assertEqual(self.buy_menu(self.thread).placeholder, "已下架")
        self.assertTrue(self.thread.name.startswith("【已下架】"))
        self.assertTrue(self.thread.locked)
        with self.assertRaises(ShopError):
            self.add(self.thread, "多一個｜1")

    def test_an_old_quiet_listing_can_be_renamed_and_closed(self):
        # 上架一週以上的貼文多半是封存的（只改首則不算新動靜）；封存中的貼文要先解封才改得了名、鎖得了
        self.add(self.thread, "60 月相｜30｜10｜")
        self.thread.auto_archive()
        self.call(self.shop.edit_info(self.thread.id, SELLER, title="新標題", description="", unit="NT$"))
        self.assertEqual(self.thread.name, "新標題")
        self.thread.auto_archive()

        self.call(self.shop.close_listing(self.thread.id, SELLER))

        self.assertTrue(self.thread.name.startswith("【已下架】"))
        self.assertTrue(self.thread.locked and self.thread.archived)

    def test_unchanged_title_is_not_renamed(self):
        # 改名每 10 分鐘只能 2 次：標題沒改（只是清理後的寫法不同）就不送
        self.call(self.shop.edit_info(self.thread.id, SELLER, title="月相代儲", description="新說明", unit="NT$"))
        self.assertFalse([kw for kind, kw in self.thread.events if kind == "edit" and "name" in kw])

    def test_a_rate_limited_rename_does_not_hold_up_the_panel(self):
        # 撞到改名限速時 discord.py 會睡到解除（九分多鐘）：資料庫寫好就回，改名在背景等
        release = asyncio.Event()
        real_edit = type(self.thread).edit

        async def slow_edit(thread, **kwargs):
            if "name" in kwargs:
                await release.wait()
            return await real_edit(thread, **kwargs)

        with mock.patch.object(type(self.thread), "edit", slow_edit):
            listing = self.loop.run_until_complete(self.shop.edit_info(
                self.thread.id, SELLER, title="新標題", description="", unit="NT$"))
            self.assertEqual(listing.title, "新標題")
            self.assertNotEqual(self.thread.name, "新標題")
            # 前一個改名還在等，又改了一次：最後要是最新的標題，不能停在舊的
            self.loop.run_until_complete(self.shop.edit_info(
                self.thread.id, SELLER, title="第三個標題", description="", unit="NT$"))
            release.set()
            self.call(self.shop.settle())
        self.assertEqual(self.thread.name, "第三個標題")

    def test_a_close_cut_short_by_a_restart_is_finished_later(self):
        # 下架後背景改名撞到限速、還沒改好就重啟：排程照資料庫補改名與鎖定
        real_edit = type(self.thread).edit

        async def server_error(thread, **kwargs):
            if "name" in kwargs:
                raise discord.HTTPException(mock.MagicMock(status=503), "Service Unavailable")
            return await real_edit(thread, **kwargs)

        with mock.patch.object(type(self.thread), "edit", server_error), \
                self.assertLogs(shop_service.logger, level="WARNING"):
            self.call(self.shop.close_listing(self.thread.id, SELLER))
        self.assertFalse(self.thread.name.startswith("【已下架】"))
        trade, self.shop = self.services()   # 重啟

        self.call(self.shop.run_cutoffs(self.world.now))

        self.assertTrue(self.thread.name.startswith("【已下架】"))
        self.assertTrue(self.thread.locked)
        self.assertFalse(self.call(self.db.get_listing(self.thread.id)).post_pending)

    def test_currency_cannot_change_while_trading(self):
        # 金額存的是數字、幣別在商品上：交易進行中改幣別，已收的錢會整批換成新幣別顯示
        self.add(self.thread, "60 月相｜30｜10｜")
        self.order(self.thread, BUYER, {1: 1})
        with self.assertRaises(ShopError) as caught:
            self.call(self.shop.edit_info(self.thread.id, SELLER, title="月相代儲", description="", unit="USD$"))
        self.assertIn("不能改幣別", str(caught.exception))

    def test_changing_back_right_after_a_rename_still_renames(self):
        # 剛改完名、快取裡的 thread 還是舊名字（Discord 的更新事件還沒到）：改回原本的標題不能被當成不用改
        renamed = []
        release = asyncio.Event()
        real_edit = type(self.thread).edit

        async def stale_cache_edit(thread, **kwargs):
            if "name" in kwargs:
                await release.wait()
                renamed.append(kwargs.pop("name"))   # Discord 上改了，手上這份 thread 的名字不變
            return await real_edit(thread, **kwargs)

        with mock.patch.object(type(self.thread), "edit", stale_cache_edit):
            self.loop.run_until_complete(self.shop.edit_info(self.thread.id, SELLER, title="新標題",
                                                             description="", unit="NT$"))
            self.loop.run_until_complete(self.shop.edit_info(self.thread.id, SELLER, title="月相代儲",
                                                             description="", unit="NT$"))
            release.set()
            self.call(self.shop.settle())
        self.assertEqual(renamed, ["新標題", "月相代儲"])

    def test_currency_cannot_change_with_only_old_trades(self):
        # 上線前的舊交易也存了下單金額（完成時的留底照商品幣別寫）
        self.add(self.thread, "60 月相｜30｜10｜")
        self.order(self.thread, BUYER, {1: 1})
        self.call(self.db.db.execute("UPDATE trades SET legacy=1"))
        with self.assertRaises(ShopError):
            self.call(self.shop.edit_info(self.thread.id, SELLER, title="月相代儲", description="", unit="USD$"))

    def test_a_long_list_of_blocking_trades_still_fits(self):
        trades = [SimpleNamespace(id=10 ** 18 + n) for n in range(40)]
        text = shop_service._thread_list(trades)
        self.assertIn("等 40 筆", text)
        self.assertLess(len(text), 500)

    def test_unfinished_preorder_or_deposit_trades_block_closing(self):
        self.add(self.thread, f"6480 月相｜3000｜3｜{self.cutoff_text(days=3)}")
        trade_thread = self.order(self.thread, BUYER, {1: 1})

        with self.assertRaises(ShopError) as caught:
            self.call(self.shop.close_listing(self.thread.id, SELLER))

        self.assertIn(f"<#{trade_thread.id}>", str(caught.exception))
        self.assertFalse(self.listing(self.thread).closed)

    def test_delivery_cannot_change_while_trading(self):
        self.add(self.thread, "60 月相｜30｜10｜")
        self.order(self.thread, BUYER, {1: 1})

        with self.assertRaises(ShopError):
            self.call(self.shop.edit_info(self.thread.id, SELLER, title="月相代儲", description="", unit="NT$",
                                          delivery="physical"))
        listing = self.call(self.shop.edit_info(self.thread.id, SELLER, title="新標題", description="", unit="NT$",
                                                delivery="digital"))
        self.assertEqual((listing.title, listing.delivery, self.thread.name), ("新標題", "digital", "新標題"))


class OrderTests(ShopTestCase):

    def setUp(self):
        super().setUp()
        self.thread = self.list_item()
        self.add(self.thread, "60 月相｜30｜10｜", "300 月相｜150｜1｜", "寰宇電台｜20｜｜")

    def test_cannot_buy_own_listing(self):
        with self.assertRaises(ShopError):
            self.order(self.thread, SELLER, {1: 1})

    def test_order_opens_a_conversation_with_the_order_and_progress(self):
        trade_thread = self.order(self.thread, BUYER, {1: 2, 3: 1})

        self.assertEqual(sorted(trade_thread.members), sorted([BUYER.id, SELLER.id]))
        opening, receipt = trade_thread.messages[0], trade_thread.messages[1]
        self.assertEqual(opening.pinged, sorted([BUYER.id, SELLER.id]))
        self.assertEqual(receipt.pinged, [])   # 訂單明細不再 @
        self.assertIn("60 月相 ×2", receipt.content)
        self.assertIn("總計 NT$80", receipt.content)
        self.assertEqual(self.card_buttons(trade_thread), ["trade:step:confirm_full", "trade:step:claim_paid"])
        self.assertIn("待付款 NT$60", self.card(trade_thread).embed.description)
        items = self.call(self.db.items(trade_thread.id))
        self.assertEqual([(i.variant_key, i.qty, i.unit_price) for i in items], [(1, 2, 30), (3, 1, 20)])
        self.assertEqual(self.taken(self.thread, 1), 2)
        self.assertIn("剩 8", self.thread.messages[0].embed.fields[0].value)  # 貼文上的剩餘跟著變
        self.assertEqual(self.trade_row(trade_thread).source_kind, "listing")

    def test_same_buyer_adds_on_and_other_buyer_gets_own_conversation(self):
        first = self.order(self.thread, BUYER, {1: 1})
        old_card = self.card(first)
        again = self.order(self.thread, BUYER, {3: 2})
        other = self.order(self.thread, BUYER_B, {1: 1})

        self.assertIs(again, first)
        self.assertIsNot(other, first)
        add_on = next(m for m in first.messages if m.content.startswith("🧾") and "加購" in m.content)
        self.assertEqual(add_on.pinged, [SELLER.id])   # 加購沒有開單訊息，@ 供應方一次
        self.assertEqual(old_card.components, [])     # 上一張交易進度的按鈕收起來
        self.assertEqual([i.variant_key for i in self.call(self.db.items(first.id))], [1, 3])

    def test_at_most_five_kinds_per_order(self):
        self.add(self.thread, *[f"品項{n}｜1" for n in range(3)])
        with self.assertRaises(ShopError):
            self.call(self.shop.check_pick(self.thread.id, BUYER, [1, 2, 3, 4, 5, 6]))
        self.assertEqual(len(self.call(self.shop.check_pick(self.thread.id, BUYER, [1, 3, 4, 5, 6]))), 5)

    def test_add_on_voids_the_receipt_notice(self):
        trade_thread = self.order(self.thread, BUYER, {1: 1})
        self.step(trade_thread, SELLER, tp.CONFIRM_FULL)
        self.step(trade_thread, SELLER, tp.DELIVER, 1)
        notice = trade_thread.last()
        self.assertEqual(notice.view.actions, (RECEIVE, "hold", "help"))

        self.order(self.thread, BUYER, {3: 1})

        self.assertIsNone(notice.view)
        self.assertIn("加購", notice.content)
        self.world.advance(hours=25)
        self.call(self.trade.run_receipt_deadlines(self.world.now))
        self.assertEqual(self.trade_row(trade_thread).status, "open")   # 加購的還沒交付，不能被自動領收

    def test_cancelled_conversation_takes_no_more_orders(self):
        first = self.order(self.thread, BUYER, {1: 1})
        self.press(first, SELLER, CANCEL)
        self.assertEqual(self.trade_row(first).status, "cancelled")
        self.assertEqual(self.taken(self.thread, 1), 0)   # 取消還回

        second = self.order(self.thread, BUYER, {1: 1})

        self.assertIsNot(second, first)

    def test_unavailable_choices_are_refused(self):
        self.order(self.thread, BUYER, {2: 1})
        for picks in ({2: 1}, {1: 11}, {9: 1}):
            with self.subTest(picks), self.assertRaises(ShopError):
                self.order(self.thread, BUYER_B, picks)

    def test_nothing_is_kept_when_the_conversation_cannot_open(self):
        self.world.fail_add_user = True
        with self.assertRaises(discord.HTTPException):
            self.order(self.thread, BUYER, {1: 3})
        self.assertEqual(self.taken(self.thread, 1), 0)
        self.assertEqual(self.call(self.db.trades()), [])
        self.assertEqual(self.world.cart.all_threads, [])

    def test_currency_change_after_the_confirmation_screen_is_refused(self):
        quote = self.call(self.shop.quote(self.thread.id, BUYER, {1: 2}))
        self.call(self.shop.edit_info(self.thread.id, SELLER, title="月相代儲", description="", unit="USD$"))
        with self.assertRaises(PriceChanged):
            self.call(self.shop.place_order(self.thread.id, BUYER, {1: 2}, quote.signature))

    def test_a_supplier_without_the_role_takes_no_new_orders(self):
        # 被拿掉觀星者身份組＝不讓他繼續賣：新訂單（含加購）不接，進行中的照常做完
        trade_thread = self.order(self.thread, BUYER, {1: 1})
        TRADERS.discard(SELLER.id)
        self.addCleanup(TRADERS.add, SELLER.id)
        for attempt in (lambda: self.shop.quote(self.thread.id, BUYER_B, {1: 1}),
                        lambda: self.shop.place_order(self.thread.id, BUYER, {1: 1})):
            with self.assertRaises(ShopError) as caught:
                self.call(attempt())
            self.assertIn("不接新訂單", str(caught.exception))
        self.step(trade_thread, SELLER, tp.CONFIRM_FULL)   # 進行中的照常做
        self.assertEqual(self.taken(self.thread, 1), 1)

    def test_price_change_after_the_confirmation_screen_is_refused(self):
        quote = self.call(self.shop.quote(self.thread.id, BUYER, {1: 2}))
        self.assertEqual((quote.now_total, quote.later_total), (60, 0))
        self.edit(self.thread, 1, "60 月相", "35", "10", "", "instant")

        with self.assertRaises(PriceChanged):
            self.call(self.shop.place_order(self.thread.id, BUYER, {1: 2}, quote.signature))

        self.assertEqual(self.call(self.db.trades()), [])
        fresh = self.call(self.shop.quote(self.thread.id, BUYER, {1: 2}))
        self.call(self.shop.place_order(self.thread.id, BUYER, {1: 2}, fresh.signature))


class OneTimeFlowTests(ShopTestCase):
    """一次付清、數位交付：付款 → 收款確認 → 分品項交付 → 全部交付後領收 → 完成。"""

    def setUp(self):
        super().setUp()
        self.thread = self.list_item()
        self.add(self.thread, "60 月相｜30｜10｜", "寰宇電台｜20｜｜")
        self.trade_thread = self.order(self.thread, BUYER, {1: 2, 2: 1})

    def test_pay_deliver_and_receive(self):
        self.assertIn("只有供應方", self.step(self.trade_thread, BUYER, tp.CONFIRM_FULL))
        self.assertIn("只有需求方", self.step(self.trade_thread, SELLER, tp.CLAIM_PAID))

        self.assertIsNone(self.step(self.trade_thread, BUYER, tp.CLAIM_PAID))
        claim = self.trade_thread.last()
        self.assertEqual(claim.pinged, [SELLER.id])
        self.assertIn("NT$80", claim.content)

        self.assertIsNone(self.step(self.trade_thread, SELLER, tp.CONFIRM_FULL))
        receipt = self.trade_thread.last()
        self.assertEqual(receipt.pinged, [BUYER.id])
        self.assertIn("已確認收到款項 NT$80", receipt.content)
        self.assertEqual(self.card_buttons(self.trade_thread), ["trade:step:deliver:1", "trade:step:deliver:2"])

        self.step(self.trade_thread, SELLER, tp.DELIVER, 1)
        self.assertIn("寰宇電台 還沒交付", self.trade_thread.last().content)
        self.assertEqual(self.card_buttons(self.trade_thread), ["trade:step:deliver:2"])
        self.step(self.trade_thread, SELLER, tp.DELIVER, 2)

        notice = self.trade_thread.last()   # 最後一個品項交付後自動發領收通知
        self.assertEqual(notice.view.actions, (RECEIVE, "hold", "help"))
        self.assertEqual(notice.pinged, [BUYER.id])
        self.press(self.trade_thread, BUYER, RECEIVE)

        self.assertEqual(self.trade_row(self.trade_thread).status, "completed")
        self.assertEqual([m.components for m in self.trade_thread.messages if m.components], [])
        (_, record), = self.world.archived_posts
        self.assertIn("60 月相 ×2（NT$30）", record["content"])
        self.assertIn(f"<#{self.trade_thread.id}>", record["content"])
        self.assertNotIn("對話紀錄", record["content"])   # 私人對話的內容不複製進封存頻道
        self.assertFalse(self.thread.locked)          # 商品保留，可以賣給別人

    def test_delivery_waits_for_the_money(self):
        reason = self.step(self.trade_thread, SELLER, tp.DELIVER, 1)
        self.assertIn("錢沒收齊", reason)
        self.press(self.trade_thread, SELLER, NOTIFY)   # 開單訊息的「通知需求方領收」＝剩下的一起交付
        self.assertIn("暫時不能全部交付", self.ephemeral.await_args.args[1])
        self.assertEqual(self.events(self.trade_thread), [tp.OPENED, tp.ORDER])

    def test_progress_buttons_after_the_trade_ended(self):
        self.press(self.trade_thread, SELLER, CANCEL)
        trade, shop = self.services()   # 重啟後也一樣：狀態看資料庫

        reason = self.call(shop.trades.handle_step(SELLER, self.trade_thread, tp.CONFIRM_FULL, None))

        self.assertEqual(reason, "這筆交易已經結束。")
        self.assertNotIn(tp.FULL_RECEIVED, self.events(self.trade_thread))

    def test_repeated_presses_record_once(self):
        self.step(self.trade_thread, SELLER, tp.CONFIRM_FULL)
        self.assertIn("沒有待收的款項", self.step(self.trade_thread, SELLER, tp.CONFIRM_FULL))
        self.assertEqual(self.events(self.trade_thread).count(tp.FULL_RECEIVED), 1)

    def test_notify_delivers_the_rest_and_renotifies_after_not_received(self):
        self.step(self.trade_thread, SELLER, tp.CONFIRM_FULL)
        self.press(self.trade_thread, SELLER, NOTIFY)
        notice = self.trade_thread.last()
        self.assertEqual(notice.view.actions, (RECEIVE, "hold", "help"))
        self.assertEqual(self.events(self.trade_thread).count(tp.DELIVERED), 1)

        interaction = self.interaction(BUYER, self.trade_thread, notice)
        self.call(self.trade.handle_button(interaction, HOLD, None))
        self.press(self.trade_thread, SELLER, NOTIFY)   # 補交後再按一次：重新通知

        self.assertEqual(self.trade_thread.last().view.actions, (RECEIVE, "hold", "help"))
        self.assertEqual(self.events(self.trade_thread).count(tp.RECEIPT_REQUESTED), 2)


class DepositFlowTests(ShopTestCase):
    """定金＋尾款、實體交付：定金 → 等貨 → 開始收尾款 → 尾款 → 分品項寄出 → 需求方分品項收到 → 完成。"""

    def setUp(self):
        super().setUp()
        self.thread = self.list_item(title="座姿玩偶", delivery="physical")
        self.add(self.thread, f"玩偶A｜500/1300｜10｜{self.cutoff_text(days=20)}",
                 f"玩偶B｜500/1300｜10｜{self.cutoff_text(days=20)}")
        self.mine = self.order(self.thread, BUYER, {1: 1, 2: 1})
        self.other = self.order(self.thread, BUYER_B, {1: 1})

    def test_the_first_card_says_what_to_pay(self):
        card = self.card(self.mine)
        self.assertIn(f"<@{BUYER.id}> 請照供應方說的方式付定金 NT$1,000。付了可以按「我已付定金」通知供應方。", card.content)
        self.assertEqual(card.pinged, [])   # 開單訊息已經 @ 過了
        self.assertIn("付了可以按「我已付定金」", self.mine.messages[0].embed.fields[-1].value
                      if self.mine.messages[0].embed and self.mine.messages[0].embed.fields else self.mine.messages[0].content)
        self.order(self.thread, BUYER, {2: 1})   # 加購
        self.assertIn("請照供應方說的方式付這次加購的定金 NT$500", self.card(self.mine).content)

    def test_balance_menu_lists_confirmed_deposits(self):
        self.step(self.mine, SELLER, tp.CONFIRM_DEPOSIT)

        async def press():
            button = shop_commands.ShopPanelButton("balance", self.thread.id)
            interaction = SimpleNamespace(client=SimpleNamespace(get_cog=lambda name: SimpleNamespace(shop=self.shop)),
                                          user=SELLER, response=SimpleNamespace(defer=mock.AsyncMock()),
                                          edit_original_response=mock.AsyncMock())
            await button.callback(interaction)
            return interaction.edit_original_response.await_args.kwargs["view"]

        view = self.call(press())
        (select,) = [getattr(c, "item", c) for c in view.children
                     if isinstance(getattr(c, "item", c), discord.ui.Select)]
        self.assertEqual([o.label for o in select.options], ["玩偶A（已確認定金 1 份）", "玩偶B（已確認定金 1 份）"])

    def test_an_unsent_balance_request_already_paid_is_not_sent(self):
        # 請尾款那則沒發出去，卡片先被等待提醒重畫、供應方照卡片確認收了尾款：補發時不能再叫需求方去付
        self.step(self.mine, SELLER, tp.CONFIRM_DEPOSIT)
        back = self.out_of_reach(self.mine)
        with self.assertLogs(shop_trade.logger, level="WARNING"):
            self.call(self.shop.start_balance(self.thread.id, SELLER, 1))
        back()
        self.call(self.shop.trades.run_waiting_reminders(self.world.now))   # 卡片過期：重畫
        self.step(self.mine, SELLER, tp.CONFIRM_BALANCE)
        count = len(self.mine.messages)

        self.call(self.shop.run_cutoffs(self.world.now))

        self.assertFalse(any("請付尾款" in (m.content or "") for m in self.mine.messages[count:]))

    def test_many_balance_prices_are_shown_as_a_range(self):
        # 收定金期間改過很多次尾款：確認畫面全列會超過一則的上限，只寫範圍
        for n in range(6):
            self.edit(self.thread, 1, "玩偶A", f"500/{1301 + n}", "10", self.cutoff_text(days=20), "deposit")
            self.order(self.thread, BUYER, {1: 1})
        preview = self.call(self.shop.balance_preview(self.thread.id, SELLER, 1))
        self.assertIn("NT$1,300～NT$1,306，共 7 種", preview)

    def test_an_old_card_cannot_turn_a_deposit_claim_into_a_balance_claim(self):
        # 定金還沒確認就開始收尾款；供應方確認定金（畫了新卡）時，需求方剛好在舊卡上按了「我已付定金」：
        # 照現況會被說成付了尾款，改成請他看新的那張
        self.call(self.shop.start_balance(self.thread.id, SELLER, 1))
        old = max(int(c.rsplit(":v", 1)[1]) for c in self.card_buttons(self.other, with_version=True) if ":v" in c)
        self.step(self.other, SELLER, tp.CONFIRM_DEPOSIT)
        count = len(self.other.messages)

        reply = self.call(self.shop.trades.handle_step(BUYER_B, self.other, tp.CLAIM_PAID, None, old))

        self.assertIn("交易進度剛更新過", reply)
        self.assertFalse(any("已付尾款" in (m.content or "") for m in self.other.messages[count:]))
        self.assertNotIn(tp.PAID_CLAIM, [e.kind for e in self.call(self.db.events(self.other.id))])

    def test_full_journey(self):
        self.assertEqual(self.card_buttons(self.mine), ["trade:step:confirm_deposit", "trade:step:claim_paid"])
        self.step(self.mine, SELLER, tp.CONFIRM_DEPOSIT)
        self.assertIn("已確認收到定金 NT$1,000", self.mine.last().content)
        self.assertIn("到貨後會在這裡通知付尾款", self.mine.last().content)
        self.assertEqual(self.card(self.mine).components, [])  # 等貨中沒有按鈕

        preview = self.call(self.shop.balance_preview(self.thread.id, SELLER, 1))
        self.assertIn("會通知 2 個交易對話，共 2 份", preview)
        self.assertIn("其中 1 份你還沒按「已收到定金」", preview)
        self.assertIn("提早停收定金", preview)
        result = self.call(self.shop.start_balance(self.thread.id, SELLER, 1))
        self.assertIn("已通知 2 個交易對話", result)

        self.assertIn("請付尾款 NT$1,300（×1）", self.mine.last().content)
        self.assertEqual(self.mine.last().pinged, [BUYER.id])
        self.assertIn("定金還沒確認", self.other.last().content)
        self.assertEqual(self.other.last().pinged, [SELLER.id])
        self.assertEqual(self.listing(self.thread).variant(1).unavailable_reason(self.world.now), "已停收定金")
        self.assertIn("玩偶B ×1　⚪ 已付定金・等貨", self.card(self.mine).embed.description)

        self.step(self.mine, SELLER, tp.CONFIRM_BALANCE)
        self.assertEqual(self.card_buttons(self.mine), ["trade:step:ship:1"])
        self.step(self.mine, SELLER, tp.SHIP, 1)
        self.assertEqual(self.mine.last().pinged, [BUYER.id])
        self.assertEqual(self.card_buttons(self.mine), ["trade:step:receive:1"])
        self.assertIn("只有需求方", self.step(self.mine, SELLER, tp.RECEIVE, 1))
        self.step(self.mine, BUYER, tp.RECEIVE, 1)
        self.assertEqual(self.trade_row(self.mine).status, "open")   # 玩偶B 還在等貨

        self.call(self.shop.start_balance(self.thread.id, SELLER, 2))
        self.step(self.mine, SELLER, tp.CONFIRM_BALANCE)
        self.step(self.mine, SELLER, tp.SHIP, 2)
        self.step(self.mine, BUYER, tp.RECEIVE, 2)

        self.assertEqual(self.trade_row(self.mine).status, "completed")
        self.assertIn("已收到全部品項，交易完成", self.mine.sent()[-1])
        self.assertEqual(self.mine.last().pinged, [])

        self.step(self.other, SELLER, tp.CONFIRM_DEPOSIT)   # 晚確認定金的那位：接著請付尾款
        self.assertIn("接著請付尾款 NT$1,300", self.other.last().content)

    def test_add_on_after_a_price_change_uses_the_new_price_for_the_new_units(self):
        self.step(self.mine, SELLER, tp.CONFIRM_DEPOSIT)
        self.edit(self.thread, 1, "玩偶A", "600/1400", "10", self.cutoff_text(days=20), "deposit")
        self.order(self.thread, BUYER, {1: 1})   # 加購一份：照新的價格

        self.assertIn("玩偶A ×2　🟡 待付定金 NT$600", self.card(self.mine).embed.description)
        self.step(self.mine, SELLER, tp.CONFIRM_DEPOSIT)
        self.assertIn("已確認收到定金 NT$600（玩偶A ×1）", self.mine.last().content)
        self.call(self.shop.start_balance(self.thread.id, SELLER, 1))
        self.assertIn("請付尾款 NT$2,700（×2）", self.mine.last().content)   # 1,300＋1,400：各照下單時說好的

    def test_balance_requests_resume_after_a_restart(self):
        self.step(self.mine, SELLER, tp.CONFIRM_DEPOSIT)
        self.step(self.other, SELLER, tp.CONFIRM_DEPOSIT)
        self.other.fail_send = True
        with self.assertLogs(shop_trade.logger, level="ERROR"):
            self.call(self.shop.start_balance(self.thread.id, SELLER, 1))
        sent_mine = len(self.mine.messages)
        self.other.fail_send = False

        trade, shop = self.services()
        self.call(shop.run_cutoffs(self.world.now))

        self.assertIn("請付尾款", self.other.last().content)
        self.assertEqual(len(self.mine.messages), sent_mine)   # 已經發過的不重發
        self.assertEqual(self.events(self.other).count(tp.BALANCE_REQUESTED), 1)

    def test_cancel_with_a_paid_deposit_asks_first_and_reminds_both(self):
        self.step(self.mine, SELLER, tp.CONFIRM_DEPOSIT)

        self.press(self.mine, SELLER, CANCEL)
        text = self.ephemeral.await_args.args[1]
        self.assertIn("定金 NT$1,000（玩偶A ×1、玩偶B ×1）", text)
        self.assertEqual(self.ephemeral.await_args.kwargs["view"].actions, (CANCEL_OK, "keep"))
        self.assertEqual(self.trade_row(self.mine).status, "open")

        self.press(self.mine, SELLER, CANCEL_OK)

        self.assertEqual(self.trade_row(self.mine).status, "cancelled")
        self.assertIn("⚠️ 定金已付：玩偶A ×1、玩偶B ×1，共 NT$1,000。請雙方記得處理後續。", self.mine.sent()[-1])
        self.assertIn("定金已付", self.dms.await_args.kwargs["embed"].description)
        self.assertEqual((self.taken(self.thread, 1), self.taken(self.thread, 2)), (1, 0))

    def test_owner_can_cancel_and_shipped_items_stay_counted(self):
        self.step(self.mine, SELLER, tp.CONFIRM_DEPOSIT)
        self.call(self.shop.start_balance(self.thread.id, SELLER, 1))
        self.step(self.mine, SELLER, tp.CONFIRM_BALANCE)
        self.step(self.mine, SELLER, tp.SHIP, 1)

        self.press(self.mine, OWNER, CANCEL_OK)

        self.assertEqual(self.trade_row(self.mine).status, "cancelled")
        self.assertIn("已交付或寄出的不還回：玩偶A ×1", self.mine.sent()[-1])
        self.assertEqual((self.taken(self.thread, 1), self.taken(self.thread, 2)), (2, 0))


class CutoffTests(ShopTestCase):

    def setUp(self):
        super().setUp()
        self.thread = self.list_item()
        self.add(self.thread, f"6480 月相｜3000｜3｜{self.cutoff_text(hours=1)}", "60 月相｜30｜｜")
        self.first = self.order(self.thread, BUYER, {1: 1})
        self.second = self.order(self.thread, BUYER_B, {1: 1, 2: 1})

    def test_preorder_cutoff_tells_both_sides_once(self):
        self.world.advance(hours=2)
        self.call(self.shop.run_cutoffs(self.world.now))

        for trade_thread, buyer in ((self.first, BUYER), (self.second, BUYER_B)):
            self.assertIn("可以開始交貨", trade_thread.last().content)
            self.assertEqual(trade_thread.last().pinged, sorted([buyer.id, SELLER.id]))
        self.assertTrue(self.call(self.db.get_variant(self.thread.id, 1)).cutoff_done)
        self.assertEqual(self.buy_menu(self.thread).options[0].description[:5], "預購已截止")
        counts = (len(self.first.messages), len(self.second.messages))

        trade, shop = self.services()
        self.call(shop.run_cutoffs(self.world.now))
        self.assertEqual((len(self.first.messages), len(self.second.messages)), counts)

    def test_a_delay_right_after_the_cutoff_time_comes_after_the_cutoff(self):
        # 截止時間到了、排程還沒醒來（剛重啟）就按延期：先照時間截止，延期接在後面，不會變成「貨提早到了」
        self.world.advance(hours=2)
        self.call(self.shop.delay(self.thread.id, SELLER, 1, self.cutoff_text(days=10), "工廠延誤"))
        self.call(self.shop.run_cutoffs(self.world.now))
        for trade_thread in (self.first, self.second):
            texts = [m.content or "" for m in trade_thread.messages]
            cut = next(i for i, t in enumerate(texts) if "已截止" in t)
            late = next(i for i, t in enumerate(texts) if "延後到" in t)
            self.assertLess(cut, late)
            self.assertFalse(any("提早" in t for t in texts))

    def test_starting_delivery_right_after_the_cutoff_time_just_cuts_off(self):
        self.world.advance(hours=2)
        result = self.call(self.shop.start_delivery(self.thread.id, SELLER, 1))
        self.assertIn("剛好到了截止時間", result)
        for trade_thread in (self.first, self.second):
            self.assertIn("已截止", trade_thread.last().content)
            self.assertFalse(any("提早" in (m.content or "") for m in trade_thread.messages))

    def test_a_second_early_start_still_reaches_everyone(self):
        # 截止後延期 → 貨到了開始交貨 → 發現還沒到又延期 → 真的到了再開始交貨：第二次也要通知到
        self.world.advance(hours=2)
        self.call(self.shop.run_cutoffs(self.world.now))
        self.call(self.shop.delay(self.thread.id, SELLER, 1, self.cutoff_text(days=10), ""))
        self.call(self.shop.start_delivery(self.thread.id, SELLER, 1))
        self.world.advance(hours=1)
        self.call(self.shop.delay(self.thread.id, SELLER, 1, self.cutoff_text(days=10), "其實還沒到"))

        result = self.call(self.shop.start_delivery(self.thread.id, SELLER, 1))

        self.assertIn("通知了 2 個交易對話", result)
        for trade_thread in (self.first, self.second):
            self.assertEqual(sum("貨提早到了" in (m.content or "") for m in trade_thread.messages), 2)

    def test_a_conversation_out_of_reach_gets_the_cutoff_notice_later(self):
        self.world.advance(hours=2)
        back = self.out_of_reach(self.first)
        with self.assertLogs(shop_trade.logger, level="WARNING"):
            wake = self.call(self.shop.run_cutoffs(self.world.now))
        self.assertLessEqual(wake, self.world.now + timedelta(minutes=10))
        self.assertFalse(self.call(self.db.get_variant(self.thread.id, 1)).cutoff_noticed)
        self.assertIn("可以開始交貨", self.second.last().content)

        back()
        self.world.advance(minutes=10)
        self.call(self.shop.run_cutoffs(self.world.now))

        self.assertIn("可以開始交貨", self.first.last().content)
        self.assertEqual(sum("可以開始交貨" in (m.content or "") for m in self.second.messages), 1)
        self.assertTrue(self.call(self.db.get_variant(self.thread.id, 1)).cutoff_noticed)

    def test_a_conversation_out_of_reach_gets_the_delay_notice_later(self):
        back = self.out_of_reach(self.first)
        with self.assertLogs(shop_trade.logger, level="WARNING"):
            result = self.call(self.shop.delay(self.thread.id, SELLER, 1, self.cutoff_text(days=3), "工廠延誤"))
        self.assertIn("稍後會補發", result)
        with self.assertLogs(shop_trade.logger, level="WARNING"):
            self.call(self.shop.run_cutoffs(self.world.now))   # 排程補發時還是取不到：照樣等下一輪
        self.assertEqual(self.call(self.db.get_variant(self.thread.id, 1)).delays_noticed, 0)
        back()

        self.call(self.shop.run_cutoffs(self.world.now))

        self.assertIn("延後到", self.first.last().content)
        self.assertEqual(sum("延後到" in (m.content or "") for m in self.second.messages), 1)
        self.assertEqual(self.call(self.db.get_variant(self.thread.id, 1)).delays_noticed, 1)

    def test_a_delay_while_cutoff_notices_are_unfinished(self):
        # 截止通知有對話一時取不到、還沒補發就延期了：補發的仍是截止通知，不是「貨提早到了」
        self.world.advance(hours=2)
        back = self.out_of_reach(self.first)
        with self.assertLogs(shop_trade.logger, level="WARNING"):
            self.call(self.shop.run_cutoffs(self.world.now))
            self.call(self.shop.delay(self.thread.id, SELLER, 1, self.cutoff_text(days=10), "工廠延誤"))
        back()
        self.world.advance(days=11)   # 補發時延期的日子也過了：日子過了不等於貨提早到

        self.call(self.shop.run_cutoffs(self.world.now))

        texts = [m.content or "" for m in self.first.messages]
        self.assertTrue(any("已截止" in t and "預計" in t for t in texts))   # 照延期後的日子講
        self.assertFalse(any("提早到" in t for t in texts))
        self.assertFalse(any("可以開始交貨" in t for t in texts))   # 跟剛收到的延期通知矛盾

    def test_a_delay_after_starting_takes_back_the_arrival(self):
        # 按了開始交貨、還沒通知完就又延期（貨其實還沒到）：補發時不能再說「貨提早到了」
        self.world.advance(hours=2)
        self.call(self.shop.run_cutoffs(self.world.now))
        self.call(self.shop.delay(self.thread.id, SELLER, 1, self.cutoff_text(days=10), ""))
        back = self.out_of_reach(self.first)
        with self.assertLogs(shop_trade.logger, level="WARNING"):
            self.call(self.shop.start_delivery(self.thread.id, SELLER, 1))
            self.call(self.shop.delay(self.thread.id, SELLER, 1, self.cutoff_text(days=10), "其實還沒到"))
        back()
        self.world.advance(minutes=10)

        self.call(self.shop.run_cutoffs(self.world.now))

        self.assertFalse(any("提早到" in (m.content or "") for m in self.first.messages))
        self.assertIn("延後到", self.first.last().content)

    def test_trades_that_already_have_the_goods_are_left_alone(self):
        # 截止前就先交貨了（規格允許）：截止時不用再叫雙方「可以開始交貨」
        self.step(self.first, SELLER, tp.CONFIRM_FULL)
        self.step(self.first, SELLER, tp.DELIVER, 1)
        count = len(self.first.messages)
        self.world.advance(hours=2)

        self.call(self.shop.run_cutoffs(self.world.now))

        self.assertFalse(any("可以開始交貨" in (m.content or "") for m in self.first.messages[count:]))
        self.assertIn("可以開始交貨", self.second.last().content)

    def test_a_delay_still_being_told_is_dropped_once_delivery_starts(self):
        # 延期通知還沒補完，貨就到了、按了開始交貨：補發的延期內容已經過期，不發
        self.world.advance(hours=2)
        self.call(self.shop.run_cutoffs(self.world.now))
        back = self.out_of_reach(self.first)
        with self.assertLogs(shop_trade.logger, level="WARNING"):
            self.call(self.shop.delay(self.thread.id, SELLER, 1, self.cutoff_text(days=10), ""))
            self.call(self.shop.start_delivery(self.thread.id, SELLER, 1))
        back()
        self.world.advance(minutes=10)

        self.call(self.shop.run_cutoffs(self.world.now))

        texts = [m.content or "" for m in self.first.messages]
        self.assertTrue(any("貨提早到了" in t for t in texts))
        self.assertFalse(any("延後到" in t for t in texts))

    def test_a_delay_overtaken_by_an_early_start_is_dropped(self):
        # 截止前延期、通知還沒補完就按了開始交貨（現在就截止）：延期的內容已經過期，不補
        back = self.out_of_reach(self.first)
        with self.assertLogs(shop_trade.logger, level="WARNING"):
            self.call(self.shop.delay(self.thread.id, SELLER, 1, self.cutoff_text(days=3), "工廠延誤"))
            self.call(self.shop.start_delivery(self.thread.id, SELLER, 1))
        back()
        self.world.advance(minutes=10)

        self.call(self.shop.run_cutoffs(self.world.now))

        texts = [m.content or "" for m in self.first.messages]
        self.assertTrue(any("可以開始交貨" in t for t in texts))
        self.assertFalse(any("延後到" in t for t in texts))

    def test_old_trades_waiting_for_deposit_get_no_cutoff_notice(self):
        # 還在等改成定金＋尾款的舊交易：截止時不講「可以開始交貨」（照舊流程走就沒有尾款），改好接上新流程時再補發
        self.call(self.db.db.execute(f"UPDATE trades SET legacy=1 WHERE id={self.first.id}"))
        self.call(self.db.db.execute(f"UPDATE listings SET title='【定金】月相代儲' WHERE id={self.thread.id}"))
        count = len(self.first.messages)
        self.world.advance(hours=2)
        self.call(self.shop.run_cutoffs(self.world.now))
        self.assertFalse(any("可以開始交貨" in (m.content or "") for m in self.first.messages[count:]))
        self.assertIn("可以開始交貨", self.second.last().content)

    def test_stopping_halfway_through_the_cutoff_notices(self):
        # 先停止下單、再逐一通知：通知發到一半停機，下一輪補發還沒發的，已經通知過的不再 @
        self.world.advance(hours=2)
        real = shop_trade.ListingTrades._notify_once
        seen = []

        async def stop_after_the_first(trades, trade, kind, reference, notify):
            if seen:
                raise RuntimeError("停機")
            seen.append(trade.id)
            return await real(trades, trade, kind, reference, notify)

        with mock.patch.object(shop_trade.ListingTrades, "_notify_once", stop_after_the_first), \
                self.assertLogs(shop_service.logger, level="ERROR"):
            self.call(self.shop.run_cutoffs(self.world.now))
        variant = self.call(self.db.get_variant(self.thread.id, 1))
        self.assertTrue(variant.cutoff_done and not variant.cutoff_noticed)   # 已經停止下單
        with self.assertRaises(ShopError):
            self.order(self.thread, BUYER, {1: 1})
        notified = [t for t in (self.first, self.second) if "可以開始交貨" in (t.last().content or "")]
        self.assertEqual(len(notified), 1)

        trade, shop = self.services()   # 重啟
        self.call(shop.run_cutoffs(self.world.now))

        for trade_thread in (self.first, self.second):   # 每個對話剛好一則
            self.assertEqual(sum("可以開始交貨" in (m.content or "") for m in trade_thread.messages), 1)
        self.assertTrue(self.call(self.db.get_variant(self.thread.id, 1)).cutoff_noticed)

    def test_one_failed_notice_does_not_block_or_repeat(self):
        self.world.advance(hours=2)
        self.first.fail_send = True
        with self.assertLogs(shop_trade.logger, level="ERROR"):
            self.call(self.shop.run_cutoffs(self.world.now))
        self.assertIn("可以開始交貨", self.second.last().content)
        self.first.fail_send = False
        count = len(self.first.messages)
        self.call(self.shop.run_cutoffs(self.world.now))
        self.assertEqual(len(self.first.messages), count)

    def test_start_delivery_early(self):
        preview = self.call(self.shop.delivery_preview(self.thread.id, SELLER, 1))
        self.assertIn("會通知 2 個交易對話", preview)

        self.call(self.shop.start_delivery(self.thread.id, SELLER, 1))

        self.assertIn("提早開始交貨", self.first.last().content)
        self.assertTrue(self.call(self.db.get_variant(self.thread.id, 1)).cutoff_done)
        with self.assertRaises(ShopError):
            self.order(self.thread, BUYER, {1: 1})

    def test_delay_only_moves_later(self):
        later = self.cutoff_text(days=5)
        text = self.call(self.shop.delay(self.thread.id, SELLER, 1, later, "原廠延後"))
        self.assertIn("第 1 次延期", text)
        self.assertIn("第 1 次延期", self.first.last().content)
        self.assertIn("原因：原廠延後", self.first.last().content)
        self.assertEqual(self.first.last().pinged, [BUYER.id])
        self.assertEqual(self.listing(self.thread).variant(1).delays, 1)
        with self.assertRaises(ShopError):
            self.call(self.shop.delay(self.thread.id, SELLER, 1, self.cutoff_text(days=1), ""))

        self.world.advance(days=6)
        self.call(self.shop.run_cutoffs(self.world.now))
        self.call(self.shop.delay(self.thread.id, SELLER, 1, self.cutoff_text(days=30), ""))
        variant = self.listing(self.thread).variant(1)
        self.assertIsNotNone(variant.expected_at)
        self.assertEqual(variant.unavailable_reason(self.world.now), "預購已截止")   # 已截止的延期不重新開放下單
        self.assertIn("預計交貨", self.first.last().content)

    def test_deposit_cutoff_only_stops_deposits(self):
        deposit = self.list_item(title="座姿玩偶", delivery="physical")
        self.add(deposit, f"玩偶A｜500/1300｜10｜{self.cutoff_text(hours=1)}")
        trade_thread = self.order(deposit, BUYER, {1: 1})
        count = len(trade_thread.messages)
        self.world.advance(hours=2)

        self.call(self.shop.run_cutoffs(self.world.now))

        # 不 @ 人，只重畫交易進度、標成收定金已截止；重跑不再畫
        self.assertEqual(len(trade_thread.messages), count + 1)
        self.assertEqual(trade_thread.last().pinged, [])
        self.assertIn("待付定金 NT$500（收定金已截止，這筆已經下單，定金照樣要付）", self.card(trade_thread).embed.description)
        self.assertEqual(self.listing(deposit).variant(1).unavailable_reason(self.world.now), "已停收定金")
        self.call(self.services()[1].run_cutoffs(self.world.now))
        self.assertEqual(len(trade_thread.messages), count + 1)


class RecoveryTests(ShopTestCase):
    """Discord 發失敗、重啟、同時按：資料庫是對的，之後補得回來，不會因為少一則訊息就完成或卡住。"""

    def digital(self, *lines):
        thread = self.list_item()
        self.add(thread, *(lines or ("60 月相｜30｜｜",)))
        return thread

    def delivered(self, thread, buyer=BUYER):
        trade_thread = self.order(thread, buyer, {1: 1})
        self.step(trade_thread, SELLER, tp.CONFIRM_FULL)
        self.step(trade_thread, SELLER, tp.DELIVER, 1)
        return trade_thread

    def test_add_on_voids_the_notice_even_when_its_messages_fail(self):
        thread = self.digital()
        trade_thread = self.delivered(thread)
        notice = trade_thread.last()
        trade_thread.fail_send = True
        with self.assertLogs(trade_service.logger, level="ERROR"):
            self.order(thread, BUYER, {1: 1})   # 加購寫進資料庫了，訂單明細發不出去
        trade_thread.fail_send = False

        self.world.advance(hours=25)
        self.call(self.trade.run_receipt_deadlines(self.world.now))
        self.assertEqual(self.trade_row(trade_thread).status, "open")   # 舊通知不能把加購的也自動完成
        interaction = self.interaction(BUYER, trade_thread, notice)
        self.call(self.trade.handle_button(interaction, RECEIVE, None))   # 舊通知上的按鈕也不行
        self.assertIn("失效", self.ephemeral.await_args.args[1])
        self.assertEqual(self.trade_row(trade_thread).status, "open")

    def test_a_notice_cannot_complete_undelivered_items(self):
        # 保險：就算通知沒被作廢（資料不一致），還有沒交付的品項也不能被領收
        thread = self.digital()
        trade_thread = self.delivered(thread)
        notice = trade_thread.last()

        async def sneak_in_an_order():
            async with self.db.transaction():
                order = await self.db.add_event(trade_thread.id, tp.ORDER, now=self.world.now.isoformat(), items={1: 1})
                await self.db.insert_items(trade_thread.id, order, [dict(variant_key=1, name="60 月相", kind="instant",
                                                                        qty=1, unit_price=30)])
        self.call(sneak_in_an_order())

        self.call(self.trade.handle_button(self.interaction(BUYER, trade_thread, notice), RECEIVE, None))
        self.assertIn("還有品項沒交付", self.ephemeral.await_args.args[1])
        self.world.advance(hours=25)
        with self.assertLogs(trade_service.logger, level="WARNING"):
            self.call(self.trade.run_receipt_deadlines(self.world.now))
        self.assertEqual(self.trade_row(trade_thread).status, "open")
        self.assertIsNone(notice.view)   # 那則通知作廢了，不會每次醒來都再碰到

    def test_a_discord_hiccup_does_not_open_a_second_conversation(self):
        thread = self.digital()
        first = self.order(thread, BUYER, {1: 1})
        first.auto_archive()
        self.world.channels.pop(first.id)   # 封存的對話不在快取裡，要再問 API

        async def hiccup(channel_id):
            raise discord.HTTPException(mock.MagicMock(status=503), "Service Unavailable")

        self.world.bot.fetch_channel = hiccup
        with self.assertRaises(discord.HTTPException):
            self.order(thread, BUYER, {1: 1})
        self.assertEqual(len(self.call(self.db.trades())), 1)
        self.assertEqual(len(self.world.cart.all_threads), 1)

    def test_a_card_that_failed_to_post_is_drawn_again(self):
        thread = self.list_item(delivery="physical")
        self.add(thread, "吊飾｜300｜｜")
        trade_thread = self.order(thread, BUYER, {1: 1})
        self.step(trade_thread, SELLER, tp.CONFIRM_FULL)
        trade_thread.fail_send = True
        with self.assertRaises(discord.HTTPException):
            self.step(trade_thread, SELLER, tp.SHIP, 1)   # 已寄出記下了，新的交易進度沒發出去
        trade_thread.fail_send = False
        self.assertIn(tp.SHIPPED, self.events(trade_thread))

        self.call(self.shop.trades.run_waiting_reminders(self.world.now))   # 排程醒來就補畫

        self.assertEqual(self.card_buttons(trade_thread), ["trade:step:receive:1"])
        self.call(self.shop.trades.run_waiting_reminders(self.world.now))
        self.assertEqual(sum(1 for m in trade_thread.messages if m.embed and m.embed.title == "交易進度"), 3)

    def test_a_missing_receipt_notice_is_sent_again(self):
        thread = self.digital()
        trade_thread = self.order(thread, BUYER, {1: 1})
        self.step(trade_thread, SELLER, tp.CONFIRM_FULL)
        with mock.patch.object(TradeService, "request_receipt_locked",
                               side_effect=discord.HTTPException(mock.MagicMock(status=500), "x")):
            with self.assertRaises(discord.HTTPException):
                self.step(trade_thread, SELLER, tp.DELIVER, 1)
        self.assertNotIn(tp.RECEIPT_REQUESTED, self.events(trade_thread))

        self.call(self.shop.trades.run_waiting_reminders(self.world.now))

        self.assertEqual(trade_thread.last().view.actions, (RECEIVE, "hold", "help"))
        self.world.advance(hours=25)
        self.call(self.trade.run_receipt_deadlines(self.world.now))
        self.assertEqual(self.trade_row(trade_thread).status, "completed")

    def test_not_received_goes_back_to_the_supplier(self):
        thread = self.digital()
        trade_thread = self.delivered(thread)
        notice = trade_thread.last()
        self.call(self.trade.handle_button(self.interaction(BUYER, trade_thread, notice), HOLD, None))
        summary = next(s for s in self.call(market_report.summarize(self.shop, self.world.now))
                       if s.trade_id == trade_thread.id)
        self.assertIn("還沒領收", "；".join(summary.todo))
        self.call(self.shop.trades.run_waiting_reminders(self.world.now))   # 不會自己再發一次領收通知
        self.assertEqual(self.events(trade_thread).count(tp.RECEIPT_REQUESTED), 1)

        self.world.advance(days=3, hours=1)
        self.call(self.shop.trades.run_waiting_reminders(self.world.now))

        self.assertIn("需求方表示還沒領收", trade_thread.last().content)
        self.assertEqual(trade_thread.last().pinged, [SELLER.id])

    def test_an_old_card_only_confirms_what_it_showed(self):
        thread = self.list_item(title="座姿玩偶", delivery="physical")
        self.add(thread, f"玩偶A｜500/1300｜10｜{self.cutoff_text(days=20)}")
        trade_thread = self.order(thread, BUYER, {1: 1})
        old = next(i for i in self.card_buttons(trade_thread, with_version=True) if "confirm_deposit" in i)
        version = int(old.rsplit(":v", 1)[1])
        self.order(thread, BUYER, {1: 1})   # 加購剛好排在前面

        self.call(self.shop.trades.handle_step(SELLER, trade_thread, tp.CONFIRM_DEPOSIT, None, version))

        (received,) = [e for e in self.call(self.db.events(trade_thread.id)) if e.kind == tp.DEPOSIT_RECEIVED]
        self.assertEqual((received.items, received.amount), ({1: 1}, 500))
        self.assertIn("待付定金 NT$500", self.card(trade_thread).embed.description)   # 加購那份還要確認

    def test_buyer_with_an_old_trade_gets_a_new_conversation(self):
        thread = self.digital()
        first = self.order(thread, BUYER, {1: 1})
        self.call(self.db.db.execute("UPDATE trades SET legacy=1"))

        second = self.order(thread, BUYER, {1: 1})

        self.assertIsNot(second, first)
        self.assertFalse(self.trade_row(second).legacy)
        self.assertEqual([i.qty for i in self.call(self.db.items(first.id))], [1])

    def test_old_trades_do_not_block_changing_delivery_or_kind(self):
        thread = self.digital()
        self.order(thread, BUYER, {1: 1})
        self.call(self.db.db.execute("UPDATE trades SET legacy=1"))

        listing = self.call(self.shop.edit_info(thread.id, SELLER, title="月相代儲", description="", unit="NT$",
                                                delivery="physical"))
        self.assertEqual(listing.delivery, "physical")
        listing, _ = self.edit(thread, 1, "60 月相", "30", "", self.cutoff_text(days=5), "preorder")
        self.assertEqual(listing.variant(1).kind, "preorder")
        self.call(self.shop.close_listing(thread.id, SELLER))   # 舊交易也不擋下架

    def test_start_delivery_starts_the_delivery_clock_now(self):
        thread = self.digital(f"吊飾C｜300｜｜{self.cutoff_text(days=20)}")
        trade_thread = self.order(thread, BUYER, {1: 1})
        self.step(trade_thread, SELLER, tp.CONFIRM_FULL)
        self.call(self.shop.start_delivery(thread.id, SELLER, 1))
        self.assertLessEqual(self.listing(thread).variant(1).cutoff, self.world.now)   # 貼文上寫的截止也是現在

        self.world.advance(days=3, hours=1)
        self.call(self.shop.trades.run_waiting_reminders(self.world.now))

        self.assertIn("錢收齊了", trade_thread.last().content)
        self.assertEqual(trade_thread.last().pinged, [SELLER.id])

    def test_cancel_reports_when_the_trade_already_ended(self):
        thread = self.digital()
        trade_thread = self.delivered(thread)
        self.press(trade_thread, BUYER, RECEIVE)
        self.assertFalse(self.call(self.trade.cancel(trade_thread, trade_thread.id, actor=SELLER)))

    def deposit_pair(self):
        thread = self.list_item(title="座姿玩偶", delivery="physical")
        self.add(thread, f"玩偶A｜500/1300｜10｜{self.cutoff_text(days=20)}",
                 f"玩偶B｜500/1400｜10｜{self.cutoff_text(days=20)}")
        trade_thread = self.order(thread, BUYER, {1: 1, 2: 1})
        self.step(trade_thread, SELLER, tp.CONFIRM_DEPOSIT)
        return thread, trade_thread

    def test_an_add_on_card_names_the_button_that_is_on_it(self):
        # 加購時同一個對話還有沒付的尾款：卡片上只有一顆「我已付款」，指示要寫這顆
        thread, trade_thread = self.deposit_pair()
        self.call(self.shop.start_balance(thread.id, SELLER, 1))
        self.order(thread, BUYER, {2: 1})
        card = self.card(trade_thread)
        self.assertIn("請照供應方說的方式付這次加購的定金 NT$500。付了可以按「我已付款」", card.content)
        self.assertIn("我已付款", [c.label for row in card.components for c in row.children])

    def test_a_long_partial_delivery_still_fits_with_its_card(self):
        thread = self.list_item()
        self.add(thread, *[f"{'很長的品項名稱' * 11}{n:02d}｜30｜｜" for n in range(25)])
        trade_thread = self.order(thread, BUYER, {n: 1 for n in range(1, 26)})
        self.step(trade_thread, SELLER, tp.CONFIRM_FULL)
        self.step(trade_thread, SELLER, tp.DELIVER, 1)
        notice = self.card(trade_thread)
        self.assertIn("還沒交付", notice.content)
        self.assertIn("等 24 項", notice.content)

    def test_reminders_name_the_button_that_is_on_the_card(self):
        # 一個品項待付尾款、另一個加購的待付定金：卡片上只有一顆「我已付款」，提醒要叫他按這顆
        thread, trade_thread = self.deposit_pair()
        self.call(self.shop.start_balance(thread.id, SELLER, 1))
        self.order(thread, BUYER, {2: 1})
        self.assertIn("trade:step:claim_paid", self.card_buttons(trade_thread))
        self.assertIn("我已付款", [c.label for row in self.card(trade_thread).components for c in row.children])
        self.world.advance(days=3, minutes=1)
        self.call(self.shop.trades.run_waiting_reminders(self.world.now))
        reminder = trade_thread.last().content
        self.assertIn("還沒付尾款", reminder)
        self.assertIn("「我已付款」", reminder)
        self.assertNotIn("我已付尾款", reminder)
        self.assertNotIn("我已付定金", reminder)

    def test_paid_claims_are_kept_per_item(self):
        thread, trade_thread = self.deposit_pair()
        self.call(self.shop.start_balance(thread.id, SELLER, 1))
        self.step(trade_thread, BUYER, tp.CLAIM_PAID)            # 付了玩偶A 的尾款
        self.call(self.shop.start_balance(thread.id, SELLER, 2))  # 玩偶B 也到了

        self.step(trade_thread, BUYER, tp.CLAIM_PAID)

        claims = [e for e in self.call(self.db.events(trade_thread.id)) if e.kind == tp.PAID_CLAIM]
        self.assertEqual([(c.items, c.amount) for c in claims], [({1: 1}, 1300), ({2: 1}, 1400)])
        self.assertIn("NT$1,400（玩偶B ×1）", trade_thread.last().content)   # 只講這次新付的
        self.world.advance(days=3, hours=1)
        self.call(self.shop.trades.run_waiting_reminders(self.world.now))
        self.assertNotIn("還沒付", trade_thread.last().content)          # 已經說付了的不會被催

    def test_an_old_card_does_not_confirm_balances_requested_later(self):
        thread, trade_thread = self.deposit_pair()
        self.call(self.shop.start_balance(thread.id, SELLER, 1))
        old = next(i for i in self.card_buttons(trade_thread, with_version=True) if "confirm_balance" in i)
        self.call(self.shop.start_balance(thread.id, SELLER, 2))

        self.call(self.shop.trades.handle_step(SELLER, trade_thread, tp.CONFIRM_BALANCE, None,
                                               int(old.rsplit(":v", 1)[1])))

        (received,) = [e for e in self.call(self.db.events(trade_thread.id)) if e.kind == tp.BALANCE_RECEIVED]
        self.assertEqual((received.items, received.amount), ({1: 1}, 1300))

    def test_cancel_cut_short_keeps_the_paid_reminder(self):
        thread, trade_thread = self.deposit_pair()
        with mock.patch.object(TradeService, "_finish", side_effect=RuntimeError("停機")), \
                self.assertLogs(trade_service.logger, level="ERROR"):
            self.press(trade_thread, SELLER, CANCEL_OK)
        self.world.advance(minutes=15)

        self.call(self.services()[0].run_receipt_deadlines(self.world.now))

        self.assertIn("定金已付：玩偶A ×1、玩偶B ×1", trade_thread.sent()[-1])
        self.assertIn("定金已付", self.dms.await_args.kwargs["embed"].description)

    def test_cancel_note_counts_each_payment_separately(self):
        thread, trade_thread = self.deposit_pair()
        self.order(thread, BUYER, {1: 1})   # 加購一份玩偶A，定金還沒付
        self.press(trade_thread, SELLER, CANCEL_OK)
        self.assertIn("定金已付：玩偶A ×1、玩偶B ×1，共 NT$1,000", trade_thread.sent()[-1])

    def test_record_is_posted_once_when_closing_is_finished_later(self):
        thread = self.digital()
        trade_thread = self.delivered(thread)
        notice = trade_thread.last()
        with mock.patch.object(TradeService, "_finish", side_effect=RuntimeError("停機")), \
                self.assertLogs(trade_service.logger, level="ERROR"):
            self.call(self.trade.handle_button(self.interaction(BUYER, trade_thread, notice), RECEIVE, None))
        self.assertEqual(len(self.world.archived_posts), 1)   # 留底已經發了，收尾沒做完

        self.world.advance(minutes=15)
        self.call(self.services()[0].run_receipt_deadlines(self.world.now))

        self.assertTrue(trade_thread.locked)
        self.assertEqual(len(self.world.archived_posts), 1)   # 補收尾不會再發一篇留底
        self.assertFalse(thread.locked)                       # 商品貼文照樣留著

    def test_a_late_record_keeps_the_real_completion_time(self):
        # 完成後留底前就停機，隔天才補：留底上寫的是當初完成的時間
        thread = self.digital()
        trade_thread = self.delivered(thread)
        notice = trade_thread.last()
        done_at = self.world.now
        with mock.patch.object(TradeService, "_archive_once", side_effect=RuntimeError("停機")), \
                self.assertLogs(trade_service.logger, level="ERROR"):
            self.call(self.trade.handle_button(self.interaction(BUYER, trade_thread, notice), RECEIVE, None))
        self.world.advance(days=1)

        self.call(self.services()[0].run_receipt_deadlines(self.world.now))

        (_, record), = self.world.archived_posts
        self.assertIn(f"完成時間：{done_at.astimezone(shop_service.APP_TZ):%Y-%m-%d %H:%M}", record["content"])

    def test_a_late_shipping_reminder_says_how_long_it_really_has_been(self):
        thread = self.list_item(delivery="physical")
        self.add(thread, "60 月相｜30｜｜")
        trade_thread = self.order(thread, BUYER, {1: 1})
        self.step(trade_thread, SELLER, tp.CONFIRM_FULL)
        self.step(trade_thread, SELLER, tp.SHIP, 1)
        self.world.advance(days=16)   # 停機了一陣子，第一次提醒晚了 9 天才發

        self.call(self.shop.trades.run_waiting_reminders(self.world.now))

        self.assertIn("寄出超過 16 天", trade_thread.last().content)

    def test_a_shipped_and_received_trade_left_open_is_completed(self):
        thread = self.list_item(delivery="physical")
        self.add(thread, "吊飾｜300｜｜")
        trade_thread = self.order(thread, BUYER, {1: 1})
        self.step(trade_thread, SELLER, tp.CONFIRM_FULL)
        self.step(trade_thread, SELLER, tp.SHIP, 1)
        with mock.patch.object(TradeService, "complete_locked", side_effect=RuntimeError("停機")):
            with self.assertRaises(RuntimeError):
                self.step(trade_thread, BUYER, tp.RECEIVE, 1)   # 已收到記下了，完成沒做到
        self.assertEqual(self.trade_row(trade_thread).status, "open")

        self.call(self.shop.trades.run_waiting_reminders(self.world.now))

        self.assertEqual(self.trade_row(trade_thread).status, "completed")
        self.assertIn("已收到全部品項", trade_thread.sent()[-1])

    def test_receipt_notice_is_healed_after_a_not_received_and_a_new_delivery(self):
        thread = self.digital("60 月相｜30｜｜", "300 月相｜150｜｜")
        trade_thread = self.order(thread, BUYER, {1: 1})
        self.step(trade_thread, SELLER, tp.CONFIRM_FULL)
        self.step(trade_thread, SELLER, tp.DELIVER, 1)
        notice = trade_thread.last()
        self.call(self.trade.handle_button(self.interaction(BUYER, trade_thread, notice), HOLD, None))
        self.order(thread, BUYER, {2: 1})
        self.step(trade_thread, SELLER, tp.CONFIRM_FULL)
        with mock.patch.object(TradeService, "request_receipt_locked",
                               side_effect=discord.HTTPException(mock.MagicMock(status=500), "x")):
            with self.assertRaises(discord.HTTPException):
                self.step(trade_thread, SELLER, tp.DELIVER, 2)

        self.call(self.shop.trades.run_waiting_reminders(self.world.now))

        self.assertEqual(trade_thread.last().view.actions, (RECEIVE, "hold", "help"))

    def test_quote_does_not_promise_joining_an_old_trade(self):
        thread = self.digital()
        self.order(thread, BUYER, {1: 1})
        self.call(self.db.db.execute("UPDATE trades SET legacy=1"))
        quote = self.call(self.shop.quote(thread.id, BUYER, {1: 1}))
        self.assertFalse(quote.joins_open_trade)

    def test_delay_notices_are_resent_after_a_restart(self):
        thread = self.digital(f"吊飾C｜300｜｜{self.cutoff_text(days=5)}")
        trade_thread = self.order(thread, BUYER, {1: 1})
        with mock.patch.object(shop_trade.ListingTrades, "announce_delay", side_effect=RuntimeError("停機")):
            with self.assertRaises(RuntimeError):
                self.call(self.shop.delay(thread.id, SELLER, 1, self.cutoff_text(days=9), "原廠延後"))
        self.assertEqual(self.listing(thread).variant(1).delays, 1)   # 日期已經改了

        trade, shop = self.services()
        self.call(shop.run_cutoffs(self.world.now))

        self.assertIn("第 1 次延期", trade_thread.last().content)
        self.assertEqual(self.call(self.db.get_variant(thread.id, 1)).delays_noticed, 1)
        count = len(trade_thread.messages)
        self.call(shop.run_cutoffs(self.world.now))
        self.assertEqual(len(trade_thread.messages), count)

    def test_goods_arriving_early_after_a_late_delay(self):
        thread = self.digital(f"吊飾C｜300｜｜{self.cutoff_text(hours=1)}")
        trade_thread = self.order(thread, BUYER, {1: 1})
        self.world.advance(hours=2)
        self.call(self.shop.run_cutoffs(self.world.now))
        self.call(self.shop.delay(thread.id, SELLER, 1, self.cutoff_text(days=30), "原廠延後"))
        targets = self.call(self.shop.schedule_targets(thread.id, SELLER, "deliver"))
        self.assertEqual([v.key for v in targets], [1])   # 截止後延期過的也能提早開始

        self.call(self.shop.start_delivery(thread.id, SELLER, 1))

        self.assertEqual(self.listing(thread).variant(1).expected_at, self.world.now)   # 預計交貨日改成今天
        self.assertIn("貨提早到了", trade_thread.last().content)
        self.assertEqual(self.call(self.shop.schedule_targets(thread.id, SELLER, "deliver")), [])   # 不能再按一次
        self.step(trade_thread, SELLER, tp.CONFIRM_FULL)
        self.world.advance(hours=12)
        self.call(self.shop.trades.run_waiting_reminders(self.world.now))
        self.assertNotIn("錢收齊了", trade_thread.last().content or "")   # 催交貨從現在起算，不是原本的截止日

    def test_paid_claim_names_the_real_quantity(self):
        thread = self.list_item(title="座姿玩偶", delivery="physical")
        self.add(thread, f"玩偶A｜500/1300｜10｜{self.cutoff_text(days=20)}")
        trade_thread = self.order(thread, BUYER, {1: 2})
        self.step(trade_thread, BUYER, tp.CLAIM_PAID)
        self.assertIn("已付定金 NT$1,000（玩偶A ×2）", trade_thread.last().content)

    def test_mixed_claim_points_to_both_buttons(self):
        thread, trade_thread = self.deposit_pair()
        self.call(self.shop.start_balance(thread.id, SELLER, 1))   # 玩偶A 待付尾款
        self.order(thread, BUYER, {2: 1})                          # 加購玩偶B：待付定金
        self.step(trade_thread, BUYER, tp.CLAIM_PAID)
        self.assertIn("「已收到定金」和「已收到尾款」", trade_thread.last().content)

    def test_notify_does_not_replace_a_live_receipt_notice(self):
        thread = self.digital()
        trade_thread = self.delivered(thread)
        self.press(trade_thread, SELLER, NOTIFY)
        self.assertIn("已經通知需求方領收了", self.ephemeral.await_args.args[1])
        self.assertEqual(self.events(trade_thread).count(tp.RECEIPT_REQUESTED), 1)

    def test_panel_fits_with_many_long_names(self):
        thread = self.list_item(title="座姿玩偶")
        self.add(thread, *[f"{'很長的品項名稱' * 11}{n:02d}｜500/1300｜10｜{self.cutoff_text(days=20)}" for n in range(25)])
        for start in range(1, 26, 5):   # 每個品項都有人下單：多一行進度
            self.order(thread, BUYER, {key: 1 for key in range(start, start + 5)})
        embed, _ = self.call(shop_commands._panel(self.shop, self.listing(thread)))
        self.assertLessEqual(len(embed.description), 4096)
        self.assertEqual(len(embed.description.splitlines()), 25)

    def test_early_start_after_a_late_delay_is_resent_after_a_restart(self):
        thread = self.digital(f"吊飾C｜300｜｜{self.cutoff_text(hours=1)}")
        first = self.order(thread, BUYER, {1: 1})
        second = self.order(thread, BUYER_B, {1: 1})
        self.world.advance(hours=2)
        self.call(self.shop.run_cutoffs(self.world.now))
        self.call(self.shop.delay(thread.id, SELLER, 1, self.cutoff_text(days=30), ""))
        real = shop_trade.ListingTrades._notify_once
        seen = []

        async def stop_after_the_first(trades, trade, kind, reference, notify):
            if seen:
                raise RuntimeError("停機")
            seen.append(trade.id)
            return await real(trades, trade, kind, reference, notify)

        with mock.patch.object(shop_trade.ListingTrades, "_notify_once", stop_after_the_first):
            with self.assertRaises(RuntimeError):
                self.call(self.shop.start_delivery(thread.id, SELLER, 1))

        self.call(self.services()[1].run_cutoffs(self.world.now))

        for trade_thread in (first, second):
            self.assertEqual(sum("貨提早到了" in (m.content or "") for m in trade_thread.messages), 1)

    def test_a_listing_post_left_half_made_is_removed(self):
        self.call(self.db.db.execute("DELETE FROM listings"))   # 從空的開始
        self.trade.orphans_after = self.world.now - timedelta(days=1)
        orphan = ForumThread(self.world, discord.utils.time_snowflake(self.world.now), "沒上架成功", self.forum,
                             owner_id=BOT.id)
        self.forum.all_threads.append(orphan)
        kept = self.list_item()   # 有紀錄的不動
        self.world.advance(minutes=3)
        wake = self.call(self.shop.run_cutoffs(self.world.now))   # 剛發的可能還在上架：先不刪、7 分鐘後再來看
        self.assertFalse(orphan.deleted)
        self.assertLessEqual(wake, self.world.now + timedelta(minutes=7, seconds=1))
        self.world.advance(minutes=12)

        self.call(self.shop.run_cutoffs(self.world.now))

        self.assertTrue(orphan.deleted)
        self.assertFalse(kept.deleted)

    def test_notifying_before_the_money_is_in_points_at_the_confirm_button(self):
        # 照舊習慣直接按「通知需求方領收」：告訴他先按「已收到款項」，不要指向畫面上沒有的按鈕
        thread = self.digital()
        trade_thread = self.order(thread, BUYER, {1: 1})
        self.press(trade_thread, SELLER, NOTIFY)
        reply = self.ephemeral.await_args.args[1]
        self.assertIn("先在交易進度按「已收到款項（供應方）」", reply)
        self.assertNotIn("錢收齊的品項可以先按", reply)

    def test_notifying_after_some_items_are_delivered_does_not_point_at_a_missing_button(self):
        # 玩偶A 已經交付、加購的還沒付：卡片上沒有「已交付」可以按，不能叫他先按它
        thread = self.digital("60 月相｜30｜｜", "寰宇電台｜20｜｜")
        trade_thread = self.delivered(thread)
        self.order(thread, BUYER, {2: 1})
        self.press(trade_thread, SELLER, NOTIFY)
        reply = self.ephemeral.await_args.args[1]
        self.assertIn("已收到款項（供應方）", reply)
        self.assertNotIn("先按它自己的", reply)

    def test_long_cancel_and_unpaid_lists_still_fit(self):
        thread = self.list_item()
        self.add(thread, *[f"{'很長的品項名稱' * 11}{n:02d}｜30｜｜" for n in range(25)])
        trade_thread = self.order(thread, BUYER, {n: 1 for n in range(1, 26)})
        self.press(trade_thread, SELLER, NOTIFY)   # 錢都還沒收：理由列出沒收齊的品項
        self.assertLessEqual(len(self.ephemeral.await_args.args[1]), 2000)
        self.step(trade_thread, SELLER, tp.CONFIRM_FULL)
        self.press(trade_thread, SELLER, CANCEL)   # 已收過錢：先跳確認畫面，列已收的錢
        self.assertLessEqual(len(self.ephemeral.await_args.args[1]), 2000)
        self.assertIn("等 25 項", self.ephemeral.await_args.args[1])

    def test_a_cancel_finished_later_redraws_the_listing_outside_the_trade_lock(self):
        # 補收尾重畫商品貼文要拿商品鎖：鎖的順序是商品鎖 → 交易鎖，拿著交易鎖去等會跟截止通知互等
        thread = self.digital()
        trade_thread = self.order(thread, BUYER, {1: 1})
        with mock.patch.object(TradeService, "_finish", side_effect=RuntimeError("停機")), \
                self.assertLogs(trade_service.logger, level="ERROR"):
            self.press(trade_thread, SELLER, CANCEL)
        held = []
        real = shop_trade.ListingTrades.after_cancel

        async def check(trades, trade):
            lock = self.trade._locks.get(trade.id)
            held.append(lock is not None and lock.locked())
            return await real(trades, trade)

        self.world.advance(minutes=15)
        with mock.patch.object(shop_trade.ListingTrades, "after_cancel", check):
            self.call(self.trade.run_receipt_deadlines(self.world.now))
        self.assertEqual(held, [False])
        self.assertEqual(self.taken(thread, 1), 0)

    def test_paid_claim_from_the_card_counts(self):
        thread = self.digital()
        trade_thread = self.order(thread, BUYER, {1: 1})
        self.step(trade_thread, BUYER, tp.CLAIM_PAID)   # 跟真的按鈕一樣帶著卡片版本
        self.assertIn("已經通知過供應方了", self.step(trade_thread, BUYER, tp.CLAIM_PAID))
        self.world.advance(days=3, hours=1)
        self.call(self.shop.trades.run_waiting_reminders(self.world.now))
        self.assertIn("需求方表示已付款", trade_thread.last().content)   # 提醒的是供應方，不是催需求方
        self.assertEqual(trade_thread.last().pinged, [SELLER.id])

    def test_a_late_delay_cannot_be_in_the_past(self):
        thread = self.digital(f"吊飾C｜300｜｜{self.cutoff_text(hours=1)}")
        self.order(thread, BUYER, {1: 1})
        self.world.advance(days=5)
        self.call(self.shop.run_cutoffs(self.world.now))
        with self.assertRaises(ShopError) as caught:
            self.call(self.shop.delay(thread.id, SELLER, 1, self.cutoff_text(days=-1), ""))
        self.assertIn("已經過了", str(caught.exception))
        self.assertEqual(self.listing(thread).variant(1).delays, 0)

    def test_odd_digits_in_the_quantity_are_refused_politely(self):
        thread = self.digital()
        variants = list(self.listing(thread).variants)

        async def submit():
            modal = shop_commands.QuantityModal(thread.id, variants)
            modal.inputs[0][2]._value = "²"
            interaction = SimpleNamespace(client=SimpleNamespace(get_cog=lambda name: SimpleNamespace(shop=self.shop)),
                                          user=BUYER, response=SimpleNamespace(defer=mock.AsyncMock()))
            with mock.patch.object(shop_commands, "_reply", mock.AsyncMock()) as reply:
                await modal.on_submit(interaction)
            return reply.await_args.args[1]

        self.assertIn("要填正整數", self.call(submit()))

    def test_listing_cannot_take_the_guide_title(self):
        with self.assertRaises(ShopError):
            self.list_item(title=ShopSettings().guide_title)

    def test_listing_post_fits_in_one_embed(self):
        # 每一欄都填到上限：標題、說明、25 個品項、最長的名稱與價格，全部截止後狀態加刪除線與標籤最長
        thread = self.call(self.shop.create_listing(SELLER, title="座" * 90, description="說明" * 1000,
                                                    unit="新臺幣" * 3 + "元"))
        self.add(thread, *[f"{'很長的品項名稱' * 11}{n:02d}｜999999999/999999999｜10｜{self.cutoff_text(hours=1)}"
                           for n in range(25)])
        self.world.advance(hours=2)
        self.call(self.shop.run_cutoffs(self.world.now))
        self.assertLessEqual(len(thread.messages[0].embed), 6000)
        self.assertEqual(len(thread.messages[0].embed.fields), 25)

    def test_a_long_reason_from_a_card_button_is_split(self):
        # 理由會列出卡住的品項：品項很多、名稱又長時超過一則的上限，要切段回、不能整則被退件
        reason = "「很長的品項名稱很長的品項名稱」還沒付款。\n" * 120
        shop = SimpleNamespace(trades=SimpleNamespace(handle_step=mock.AsyncMock(return_value=reason)))
        interaction = SimpleNamespace(client=SimpleNamespace(get_cog=lambda name: SimpleNamespace(shop=shop)),
                                      user=BUYER, channel=SimpleNamespace(id=1),
                                      response=SimpleNamespace(defer=mock.AsyncMock()))
        send = mock.AsyncMock()
        with mock.patch("utils.utils.safe_send_interaction_message", send), \
                mock.patch.object(shop_commands, "safe_send_interaction_message", send):
            self.call(shop_commands._run_step(interaction, tp.CLAIM_PAID, None, 3))
        sent = [c.args[1] for c in send.await_args_list]
        self.assertGreater(len(sent), 1)
        self.assertTrue(all(len(text) <= 2000 for text in sent))

    def test_my_trades_is_for_sellers_and_reads_only_theirs(self):
        thread = self.digital()
        self.order(thread, BUYER, {1: 1})
        summaries = self.call(market_report.summarize(self.shop, self.world.now, supplier_id=SUPPLIER_B.id))
        self.assertEqual(summaries, [])

        async def press(user):
            view = shop_commands.GuideView()
            interaction = SimpleNamespace(client=SimpleNamespace(get_cog=lambda name: SimpleNamespace(shop=self.shop)),
                                          user=user, response=SimpleNamespace(defer=mock.AsyncMock()))
            with mock.patch.object(shop_commands, "_reply", mock.AsyncMock()) as reply, \
                    mock.patch.object(shop_commands, "safe_send_interaction_text", mock.AsyncMock()) as text:
                await view.my_trades.callback(interaction)
            return reply, text

        reply, text = self.call(press(BUYER))
        self.assertIn("只有觀星者", reply.await_args.args[1])
        reply, text = self.call(press(SELLER))
        self.assertIn("1 筆還沒結束", text.await_args.args[1])
        # 被拿掉觀星者身份組、手上還有交易的：週報會叫他來按，照樣給看自己的
        with mock.patch.object(ShopService, "can_sell", mock.AsyncMock(return_value=False)):
            reply, text = self.call(press(SELLER))
        self.assertIn("1 筆還沒結束", text.await_args.args[1])

    def test_buttons_wait_for_the_import(self):
        thread = self.digital()
        trade, shop = self.services(ready=False)
        for call in (lambda: shop.place_order(thread.id, BUYER, {1: 1}),
                     lambda: shop.add_variants(thread.id, SELLER, []),
                     lambda: shop.delay(thread.id, SELLER, 1, "2099/01/01", "")):
            with self.assertRaises(ShopError) as caught:
                self.call(call())
            self.assertIn("更新中", str(caught.exception))

    def test_long_batch_errors_fit_in_the_preview(self):
        note = "需要先提供帳號密碼與遊戲內暱稱，" * 8   # 第 4 欄寫成備註：每行錯誤都帶著這段
        text = "\n".join(f"代練{n}｜300｜｜{note}" for n in range(20))
        self.assertLess(len(text), 4000)
        embeds, _ = shop_commands._batch_preview(500, text)
        self.assertLessEqual(sum(len(e.title) + len(e.description) for e in embeds), 6000)   # 一則訊息的上限
        errors = embeds[0].description.splitlines()
        self.assertEqual(len(errors), 16)   # 15 行錯誤＋「還有幾行有錯」
        self.assertTrue(all(len(line) <= 120 for line in errors))
        # 「回去修改」拿得回完整的原文（表單上限 4000 字）
        self.assertEqual(shop_commands._preview_text(SimpleNamespace(embeds=embeds)), text)


class WaitingReminderTests(ShopTestCase):

    def test_unpaid_orders_are_reminded_once_per_step(self):
        thread = self.list_item()
        self.add(thread, "60 月相｜30｜｜")
        trade_thread = self.order(thread, BUYER, {1: 1})

        self.world.advance(days=3, minutes=1)
        self.call(self.shop.trades.run_waiting_reminders(self.world.now))

        reminder = trade_thread.last()
        self.assertIn("還沒付款（第 1 次提醒）", reminder.content)
        self.assertEqual(reminder.pinged, [BUYER.id])
        count = len(trade_thread.messages)
        trade, shop = self.services()
        self.call(shop.trades.run_waiting_reminders(self.world.now))
        self.assertEqual(len(trade_thread.messages), count)

    def test_a_long_receipt_still_fits_with_its_card(self):
        # 收款確認跟交易進度卡在同一則（不能切段）：品項很多、名稱又長時列前面幾項，後面寫「等 N 項」
        thread = self.list_item()
        self.add(thread, *[f"{'很長的品項名稱' * 11}{n:02d}｜30｜｜" for n in range(25)])
        trade_thread = self.order(thread, BUYER, {n: 1 for n in range(1, 26)})
        self.step(trade_thread, SELLER, tp.CONFIRM_FULL)
        receipt = self.card(trade_thread)
        self.assertIn("已確認收到款項 NT$750", receipt.content)
        self.assertIn("等 25 項", receipt.content)

    def test_a_long_reminder_is_split_instead_of_lost(self):
        # 很多品項、名稱又長時，併成一則的提醒會超過 2000 字：切成幾則送，@ 只放第一則
        thread = self.list_item()
        self.add(thread, *[f"{'很長的品項名稱' * 11}{n:02d}｜30｜｜" for n in range(20)])
        trade_thread = self.order(thread, BUYER, {n: 1 for n in range(1, 21)})
        self.world.advance(days=3, minutes=1)
        count = len(trade_thread.messages)

        self.call(self.shop.trades.run_waiting_reminders(self.world.now))

        parts = trade_thread.messages[count:]
        self.assertGreater(len(parts), 1)
        self.assertEqual("".join(m.content for m in parts).count("還沒付款（第 1 次提醒）"), 20)
        self.assertEqual([m.pinged for m in parts], [[BUYER.id]] + [[]] * (len(parts) - 1))

    def test_legacy_trades_are_not_reminded(self):
        thread = self.list_item()
        self.add(thread, "60 月相｜30｜｜")
        trade_thread = self.order(thread, BUYER, {1: 1})
        self.call(self.db.db.execute("UPDATE trades SET legacy=1"))
        self.world.advance(days=4)

        self.call(self.shop.trades.run_waiting_reminders(self.world.now))

        self.assertNotIn("提醒", trade_thread.last().content or "")


class ImportTests(ShopTestCase):
    """上線匯入：Discord 上的舊商品貼文與交易對話 → 資料庫。"""

    def setUp(self):
        super().setUp()
        self.trade, self.shop = self.services(ready=False)
        self.post = ForumThread(self.world, next(self.world.ids), "月相代儲", self.forum, owner_id=BOT.id)
        embed = discord.Embed(title="月相代儲", description="說明")
        embed.set_image(url="attachment://item_1.png")
        starter = FakeMessage(self.world, self.post.id, BOT, "", embed=embed, thread=self.post)
        starter.components = [SimpleNamespace(children=[
            SimpleNamespace(custom_id=f"shop:buy:{self.post.id}", options=[
                SimpleNamespace(label="60 月相", value="1:30:10:5::0"),
                SimpleNamespace(label="寰宇電台", value="2:20::0::0")]),
            SimpleNamespace(custom_id=f"shop:manage:{SELLER.id}:3:NT%24", disabled=False)])]
        self.post.messages.append(starter)
        self.forum.all_threads.append(self.post)
        self.world.channels[self.post.id] = self.post

        self.old_trade = self.cart_thread(TradeRef(self.post.id, BUYER.id, SELLER.id))
        order = FakeMessage(self.world, next(self.world.ids), BOT,
                            f"🧾 {BUYER.mention} 向 {SELLER.mention} 下單（月相代儲）：\n・60 月相 ×2（NT$30）＝NT$60",
                            thread=self.old_trade)
        order.components = [SimpleNamespace(children=[
            SimpleNamespace(custom_id=f"shop:order:{self.post.id}:1x2", label="總計 NT$60")])]
        self.old_trade.messages.append(order)
        self.old_trade.messages.append(FakeMessage(
            self.world, next(self.world.ids), BOT, "請領收", thread=self.old_trade,
            view=_make_view(TradeRef(self.post.id, BUYER.id, SELLER.id), (RECEIVE, HOLD, "help"))))
        self.forum_trade = self.cart_thread(TradeRef(7777, BUYER_B.id, SELLER.id))
        self.forum_trade.auto_archive()

    def cart_thread(self, ref):
        thread = FakeThread(self.world, next(self.world.ids), f"【交易中】誰 與 誰 - {ref.source_id}",
                            parent_id=CART_ID, type_=discord.ChannelType.private_thread)
        thread.messages.append(FakeMessage(self.world, next(self.world.ids), BOT, "開單", thread=thread,
                                           view=_make_view(ref, (NOTIFY, CANCEL, "help"))))
        self.world.cart.all_threads.append(thread)
        self.world.channels[thread.id] = thread
        return thread

    def test_old_deposit_trades_wait_for_the_conversion(self):
        # 【定金】商品還沒改成定金＋尾款：舊交易不能照舊流程發領收通知（照舊流程做完就變成一次付清、沒有尾款）
        self.post.messages[0].embed.title = "【定金】月相代儲"
        self.call(market_import.run_import(self.shop))
        self.assertTrue(self.trade_row(self.old_trade).legacy)
        count = len(self.old_trade.messages)
        self.call(self.trade.handle_button(self.interaction(SELLER, self.old_trade), NOTIFY, None))
        self.assertIn("要先改成定金＋尾款", self.ephemeral.await_args.args[1])
        self.assertEqual(len(self.old_trade.messages), count)
        self.world.advance(hours=25)   # 匯入前就在等的領收通知也不會自動完成
        self.call(self.trade.run_receipt_deadlines(self.world.now))
        self.assertEqual(self.trade_row(self.old_trade).status, "open")
        with self.assertRaises(ShopError):   # 也不能先下架（下架後就改不了，舊交易永遠接不上）
            self.call(self.shop.close_listing(self.post.id, SELLER))
        _, view = self.call(shop_commands._panel(self.shop, self.listing(self.post)))
        embed, _ = self.call(shop_commands._panel(self.shop, self.listing(self.post)))
        self.assertIn("目前不接新訂單", "".join(f.name for f in embed.fields))

    def test_preview_lists_everything_and_writes_nothing(self):
        # 上線前給群主核對：照正式匯入的讀法列出來，資料庫、Discord 都不寫，按鈕照樣擋著
        edits = [list(m.edits) for m in self.post.messages]
        text = self.call(market_import.preview_import(self.shop))
        self.assertIn("商品 1 篇（交付方式一律實體）、進行中的交易 2 筆", text)
        self.assertIn("「60 月相」30", text)
        self.assertIn("舊貼文上的已下單 5 ＝ 上線前賣掉的 3 ＋ 進行中的交易 2", text)
        self.assertIn(f"交易對話 {self.old_trade.id}　商品「月相代儲」", text)
        self.assertIn("有一則還在等的領收通知", text)
        self.assertIn(f"自由市場需求 7777", text)
        self.assertEqual((self.call(self.db.listings()), self.call(self.db.trades())), ([], []))
        self.assertEqual([list(m.edits) for m in self.post.messages], edits)
        self.assertFalse(self.trade.ready.is_set())

    def deposit_listing_imported(self):
        """標題寫【定金】的舊商品匯入後：交易先留在舊流程。"""
        self.post.messages[0].embed.title = "【定金】月相代儲"
        self.call(market_import.run_import(self.shop))
        return self.listing(self.post)

    def test_a_deposit_listing_is_converted_as_a_whole(self):
        listing = self.deposit_listing_imported()
        self.assertTrue(self.call(market_transition.can_convert(self.trade, listing)))
        _, view = self.call(shop_commands._panel(self.shop, listing))
        self.assertIn(f"shop:panel:convert:{self.post.id}", [c.item.custom_id for c in view.children
                                                              if hasattr(c, "item")])
        # 一個一個改會被「不能跟一次付清混放」擋下，錯誤訊息指到這顆按鈕
        with self.assertRaises(ShopError) as caught:
            self.edit(self.post, 1, "60 月相", "30/100", "", self.cutoff_text(days=30), "deposit")
        self.assertIn("改成定金＋尾款", str(caught.exception))

        result = self.call(market_transition.convert(self.shop, self.post.id, SELLER, self.cutoff_text(days=30),
                                                        "1. 60 月相｜100\n2. 寰宇電台｜50"))

        self.assertIn("補發了 1 個交易對話", result)
        listing = self.listing(self.post)
        self.assertEqual([(v.kind, v.price, v.balance) for v in listing.variants],
                         [("deposit", 30, 100), ("deposit", 20, 50)])
        self.assertFalse(self.trade_row(self.old_trade).legacy)
        self.assertEqual([(i.kind, i.unit_price, i.unit_balance) for i in self.call(self.db.items(self.old_trade.id))],
                         [("deposit", 30, 100)])
        card = self.card(self.old_trade)
        self.assertIn("付定金 NT$60，到貨後這裡會通知付尾款", card.content)
        self.assertIn("「我已付定金」", card.content)
        self.assertEqual(card.pinged, [])
        self.assertFalse(self.call(market_transition.can_convert(self.trade, listing)))   # 改好了，按鈕不再出現

    def convert_interaction(self):
        return SimpleNamespace(
            client=SimpleNamespace(get_cog=lambda name: SimpleNamespace(shop=self.shop)),
            user=SELLER, guild=self.world.guild, channel=self.post, message=None,
            response=SimpleNamespace(defer=mock.AsyncMock(), is_done=lambda: True),
            edit_original_response=mock.AsyncMock())

    def submit_convert_form(self, balances, cutoff=None):
        """像觀星者在「改成定金＋尾款」表單裡填：balances 照格子的順序。"""
        async def run():
            modal = shop_commands.DepositConvertModal(await self.shop.load(self.post.id))
            modal.cutoff._value = cutoff or self.cutoff_text(days=30)
            for field, value in zip(modal.fields.values(), balances):
                field._value = value
            interaction = self.convert_interaction()
            await modal.on_submit(interaction)
            return interaction.edit_original_response.await_args.kwargs["content"]
        return self.call(run())

    def test_the_convert_form_has_one_field_per_item_showing_the_deposit(self):
        modal = shop_commands.DepositConvertModal(self.deposit_listing_imported())
        rows = modal.to_components()
        self.assertEqual([row["label"] for row in rows], ["收定金截止", "1. 60 月相的尾款", "2. 寰宇電台的尾款"])
        self.assertIn("定金 NT$30", rows[1]["description"])
        self.assertIn("總價減掉 30", rows[1]["description"])
        self.assertIn("定金 NT$20", rows[2]["description"])
        self.assertIsNone(modal.balances)

    def test_the_convert_form_saves_each_field_to_its_item(self):
        self.deposit_listing_imported()

        text = self.submit_convert_form(["1,300", "50"])

        self.assertIn("已把「【定金】月相代儲」改成定金＋尾款", text)
        self.assertEqual([(v.kind, v.price, v.balance) for v in self.listing(self.post).variants],
                         [("deposit", 30, 1300), ("deposit", 20, 50)])
        self.assertEqual([(i.unit_price, i.unit_balance) for i in self.call(self.db.items(self.old_trade.id))],
                         [(30, 1300)])

    def test_a_wrong_field_saves_nothing(self):
        self.deposit_listing_imported()
        for balances in (["100", ""], ["100", "五十"], ["100", "0"], ["100", ",,"], ["100", "NT$50"]):
            with self.subTest(balances=balances):
                self.assertIn("⚠️", self.submit_convert_form(balances))
                self.assertEqual([v.kind for v in self.listing(self.post).variants], ["instant", "instant"])
        self.assertTrue(self.trade_row(self.old_trade).legacy)

    def test_items_changed_after_opening_the_form_save_nothing(self):
        listing = self.deposit_listing_imported()
        for values in ({1: "100"}, {1: "100", 2: "50", 99: "10"}):
            with self.subTest(values=values), self.assertRaises(ShopError) as caught:
                self.call(market_transition.convert(self.shop, self.post.id, SELLER, self.cutoff_text(days=30), values))
            self.assertIn("重新按", str(caught.exception))
        self.assertEqual(self.listing(self.post), listing)

    def test_many_items_fall_back_to_one_box(self):
        from dataclasses import replace

        from services.community.shop_listing import Listing

        many = Listing(thread_id=500, owner_id=SELLER.id, unit="NT$", title="【定金】t", description="",
                       variants=tuple(Variant(n, f"品項{n}", 100) for n in range(1, 6)))
        modal = shop_commands.DepositConvertModal(many)
        self.assertEqual(modal.fields, {})
        self.assertEqual([row["label"] for row in modal.to_components()], ["收定金截止", "每個品項的尾款"])
        self.assertEqual(modal.balances.default.splitlines()[0], "1. 品項1｜")
        four = shop_commands.DepositConvertModal(replace(many, variants=many.variants[:4]))   # 4 個還是每個一格
        self.assertEqual((len(four.fields), four.balances), (4, None))

    def test_the_deposit_prefix_stays_until_converted(self):
        # 只從標題認這幾篇：拿掉【定金】按鈕就不見、舊交易會被當成一次付清接上，收不回來
        self.deposit_listing_imported()
        with self.assertRaises(ShopError) as caught:
            self.call(self.shop.edit_info(self.post.id, SELLER, title="月相代儲", description="說明", unit="NT$"))
        self.assertIn("【定金】先不能拿掉", str(caught.exception))
        self.assertEqual(self.listing(self.post).title, "【定金】月相代儲")
        self.assertTrue(self.call(market_transition.can_convert(self.trade, self.listing(self.post))))
        # 標題後面的字、說明照樣能改
        self.call(self.shop.edit_info(self.post.id, SELLER, title="【定金】月相代儲 新版", description="新說明",
                                      unit="NT$"))
        self.assertEqual(self.listing(self.post).title, "【定金】月相代儲 新版")

        self.call(market_transition.convert(self.shop, self.post.id, SELLER, self.cutoff_text(days=30),
                                            {1: "100", 2: "50"}))
        self.call(self.shop.edit_info(self.post.id, SELLER, title="月相代儲", description="說明", unit="NT$"))
        self.assertEqual(self.listing(self.post).title, "月相代儲")   # 改好之後隨他改

    def test_a_new_deposit_titled_listing_can_drop_the_prefix(self):
        self.call(market_import.run_import(self.shop))
        thread = self.list_item(title="【定金】新的手辦")
        self.call(self.shop.edit_info(thread.id, SELLER, title="新的手辦", description="", unit="NT$"))
        self.assertEqual(self.listing(thread).title, "新的手辦")

    def test_adopted_trades_are_reminded_from_the_conversion_not_the_old_order(self):
        # 舊訂單是上線前下的：催款照下單時間算的話，一轉過來就 @ 需求方「第 1 次提醒」
        self.world.advance(days=10)   # 上線時舊訂單已經下了十天
        self.call(market_import.run_import(self.shop))
        count = len(self.old_trade.messages)
        self.call(self.shop.trades.run_waiting_reminders(self.world.now))
        self.assertEqual(len(self.old_trade.messages), count)
        self.world.advance(days=3, minutes=1)
        self.call(self.shop.trades.run_waiting_reminders(self.world.now))
        self.assertIn("第 1 次提醒", self.old_trade.last().content)

    def test_adopted_trades_are_not_idle_right_after_going_live(self):
        # 舊訂單是上線前好一陣子下的：接上新流程那一刻重新算，不會一上線就被週報算成超過 14 天沒動靜
        self.world.advance(days=20)
        self.call(market_import.run_import(self.shop))
        summary = next(s for s in self.call(market_report.summarize(self.shop, self.world.now))
                       if s.trade_id == self.old_trade.id)
        self.assertEqual(summary.days_idle, 0)

    def test_the_opening_message_gets_the_new_flow(self):
        self.call(market_import.run_import(self.shop))
        flow = next(f.value for f in self.old_trade.messages[0].embed.fields if f.name == "流程")
        self.assertIn("已寄出", flow)            # 實體交付：寄出、需求方按已收到
        self.assertNotIn("自動視為已領收", flow)

    def test_a_card_cut_short_during_conversion_is_sent_later(self):
        # 轉成新流程寫好了、補發交易進度時 Discord 出錯：等待提醒的排程照 adopted 那筆補發，帶說明
        self.post.messages[0].embed.title = "【定金】月相代儲"
        self.call(market_import.run_import(self.shop))
        with mock.patch.object(shop_trade.ListingTrades, "post_card", side_effect=discord.HTTPException(
                mock.MagicMock(status=503), "Service Unavailable")), self.assertLogs(shop_service.logger, level="ERROR"):
            self.call(market_transition.convert(self.shop, self.post.id, SELLER, self.cutoff_text(days=30),
                                                   "1. 60 月相｜100\n2. 寰宇電台｜50"))
        self.assertFalse(self.trade_row(self.old_trade).legacy)

        self.call(self.shop.trades.run_waiting_reminders(self.world.now))

        card = self.card(self.old_trade)
        self.assertIn("交易功能更新了", card.content)
        self.assertIn("付定金", card.content)
        self.call(self.shop.trades.run_waiting_reminders(self.world.now))   # 補發過就不再發
        cards = [m for m in self.old_trade.messages if m.embed is not None and m.embed.title == "交易進度"]
        self.assertEqual(sum("交易功能更新了" in (m.content or "") for m in cards), 1)

    def test_a_conversion_that_failed_midway_is_finished_by_the_schedule(self):
        self.post.messages[0].embed.title = "【定金】月相代儲"
        self.call(market_import.run_import(self.shop))
        with mock.patch.object(shop_trade.ListingTrades, "adopt_legacy", side_effect=RuntimeError("停機")), \
                self.assertLogs(shop_service.logger, level="ERROR"):
            self.call(market_transition.convert(self.shop, self.post.id, SELLER, self.cutoff_text(days=30),
                                                   "1. 60 月相｜100\n2. 寰宇電台｜50"))
        self.assertTrue(self.trade_row(self.old_trade).legacy)   # 品項改好了、交易還沒轉

        self.call(self.shop.run_cutoffs(self.world.now))

        self.assertFalse(self.trade_row(self.old_trade).legacy)
        self.assertIn("付定金", self.card(self.old_trade).content)

    def test_editing_the_only_item_to_deposit_also_adopts_the_old_trades(self):
        # 只有一個品項的【定金】舊商品，觀星者用熟悉的「編輯品項」改：舊交易一樣接上新流程
        self.post.messages[0].embed.title = "【定金】月相代儲"
        self.call(market_import.run_import(self.shop))
        self.call(self.shop.delete_variant(self.post.id, SELLER, 2))   # 寰宇電台沒有交易，可以刪
        listing, note = self.edit(self.post, 1, "60 月相", "30/100", "", self.cutoff_text(days=30), "deposit")
        self.assertIn("上線前的 1 筆交易已接上新流程", note)
        self.assertNotIn("照原本的金額", note)   # 舊交易的尾款就是這次填的，不是「原本的金額」
        self.assertFalse(self.trade_row(self.old_trade).legacy)
        self.assertEqual([(i.kind, i.unit_balance) for i in self.call(self.db.items(self.old_trade.id))],
                         [("deposit", 100)])

    def test_converting_keeps_items_that_already_closed(self):
        # 已經截止的預購改成定金＋尾款：照樣截止，不能因為改類型就重新開放收定金
        past = int((self.world.now - timedelta(days=3)).timestamp())
        self.post.messages[0].components[0].children[0].options[0] = SimpleNamespace(
            label="60 月相", value=f"1:30:10:5:{past}:1")
        self.post.messages[0].embed.title = "【定金】月相代儲"
        self.call(market_import.run_import(self.shop))
        self.call(market_transition.convert(self.shop, self.post.id, SELLER, self.cutoff_text(days=30),
                                               "1. 60 月相｜100\n2. 寰宇電台｜50"))
        first, second = self.call(self.db.variants(self.post.id))
        self.assertTrue(first.cutoff_done)
        self.assertFalse(second.cutoff_done)

    def test_weekly_report_says_to_set_up_the_deposit_first(self):
        self.post.messages[0].embed.title = "【定金】月相代儲"
        self.call(market_import.run_import(self.shop))
        summaries = self.call(market_report.summarize(self.shop, self.world.now))
        text = market_report.my_trades_text(summaries, SELLER.id)
        self.assertIn("改成定金＋尾款", text)
        self.assertNotIn("交付了請按「通知需求方領收」", text.split(f"<#{self.forum_trade.id}>")[0])

    def test_an_old_trade_whose_listing_is_gone_does_not_stop_the_import(self):
        lost = self.cart_thread(TradeRef(424242, BUYER_B.id, SELLER.id))
        order = FakeMessage(self.world, next(self.world.ids), BOT, f"🧾 下單：\n・不見的品項 ×1（NT$10）＝NT$10",
                            thread=lost)
        order.components = [SimpleNamespace(children=[
            SimpleNamespace(custom_id="shop:order:424242:1x1", label="總計 NT$10")])]
        lost.messages.append(order)

        self.call(market_import.run_import(self.shop))

        self.assertTrue(self.trade.ready.is_set())
        self.assertTrue(self.trade_row(lost).legacy)

    def test_a_new_deposit_titled_listing_still_takes_orders(self):
        # 上線後新開、標題剛好寫【定金】的商品沒有舊交易要等：照常接單
        self.call(market_import.run_import(self.shop))
        thread = self.list_item(title="【定金】新的手辦")
        self.add(thread, "標準版｜700｜｜")
        self.assertIsNotNone(self.order(thread, BUYER, {1: 1}))

    def test_an_old_trade_without_orders_stays_on_the_old_flow(self):
        # 沒讀到訂單的舊交易：轉過來沒有任何品項、再也完成不了，留在舊流程
        self.old_trade.messages = [m for m in self.old_trade.messages if not m.content.startswith("🧾")]
        self.call(market_import.run_import(self.shop))
        self.assertTrue(self.trade_row(self.old_trade).legacy)

    def test_weekly_report_with_only_old_trades_lists_each_todo(self):
        self.post.messages[0].embed.title = "【定金】月相代儲"
        self.call(market_import.run_import(self.shop))
        summaries = self.call(market_report.summarize(self.shop, self.world.now))
        text = market_report.weekly_text(summaries, SELLER.id, self.world.now)
        self.assertIn("都是新功能上線前開的", text)
        self.assertIn("改成定金＋尾款", text)

    def test_turning_the_transition_off_goes_back_to_the_normal_rules(self):
        # 那幾篇都改好之後把開關關掉：【定金】的規則全部不再作用，照一般規則
        listing = self.deposit_listing_imported()
        off = mock.patch.object(market_transition.switches, "current", lambda: Switches(market_transition="off"))
        with off:
            self.assertFalse(self.call(market_transition.can_convert(self.trade, listing)))
            _, view = self.call(shop_commands._panel(self.shop, listing))
            self.assertNotIn(f"shop:panel:convert:{self.post.id}",
                             [c.item.custom_id for c in view.children if hasattr(c, "item")])
            self.assertEqual(self.call(self.shop.quote(self.post.id, BUYER_B, {2: 1})).now_total, 20)
            self.assertEqual(self.call(market_transition.adopt_ready(self.shop)), 0)
            self.call(self.trade.handle_button(self.interaction(SELLER, self.old_trade), NOTIFY, None))
            self.assertEqual(self.old_trade.last().view.actions, (RECEIVE, HOLD, "help"))   # 照舊流程發領收通知
        self.assertTrue(self.trade_row(self.old_trade).legacy)

    def test_converting_needs_every_balance(self):
        self.deposit_listing_imported()
        for text in ("1. 60 月相｜100", "1. 60 月相 100\n2. 寰宇電台｜50", "1. 60 月相｜0\n2. 寰宇電台｜50",
                     "1. 60 月相｜100\n2. 寰宇電台｜,"):
            with self.assertRaises(ShopError):
                self.call(market_transition.convert(self.shop, self.post.id, SELLER, self.cutoff_text(days=30), text))
        self.assertTrue(self.trade_row(self.old_trade).legacy)

    def test_a_deposit_listing_takes_no_orders_until_it_is_set_up(self):
        # 改好之前開的單會是一次付清、沒有尾款，而且一有上線後的交易，整篇就改不成定金了
        self.deposit_listing_imported()
        for attempt in (lambda: self.shop.quote(self.post.id, BUYER_B, {2: 1}),
                        lambda: self.shop.place_order(self.post.id, BUYER_B, {2: 1})):
            with self.assertRaises(ShopError) as caught:
                self.call(attempt())
            self.assertIn("付款方式還在設定", str(caught.exception))

    def test_converting_is_refused_once_new_trades_exist(self):
        self.deposit_listing_imported()
        self.call(self.db.db.execute("UPDATE trades SET legacy=0"))   # 有上線後的交易：交易中不能改類型
        with self.assertRaises(ShopError):
            self.call(market_transition.convert(self.shop, self.post.id, SELLER, self.cutoff_text(days=30),
                                                   "1. 60 月相｜100\n2. 寰宇電台｜50"))

    def test_old_trades_keep_when_people_last_talked(self):
        # 看板算「幾天沒動靜」直接查資料庫：舊交易在匯入時從對話讀一次最後一則真人訊息
        said_at = self.world.now
        self.old_trade.messages.append(FakeMessage(self.world, next(self.world.ids), BUYER, "到貨了嗎",
                                                   thread=self.old_trade))
        self.world.advance(days=3)
        self.call(market_import.run_import(self.shop))
        self.assertEqual(self.trade_row(self.old_trade).last_chat_at, said_at.isoformat())
        self.assertIsNone(self.trade_row(self.forum_trade).last_chat_at)   # 只有 bot 講過話

    def test_import_moves_everything_and_opens_the_buttons(self):
        result = self.call(market_import.run_import(self.shop))

        self.assertEqual((result.listings, result.trades), (1, 2))
        self.assertTrue(self.trade.ready.is_set())
        listing = self.listing(self.post)
        self.assertEqual((listing.delivery, listing.unit, listing.owner_id), ("physical", "NT$", SELLER.id))
        self.assertEqual([(v.key, v.taken, v.remaining) for v in listing.variants], [(1, 5, 5), (2, 0, None)])
        self.assertEqual(self.call(self.db.get_variant(self.post.id, 1)).sold_before, 3)
        old = self.trade_row(self.old_trade)
        self.assertEqual(old.source_kind, "listing")
        self.assertEqual([(i.variant_key, i.qty, i.unit_price) for i in self.call(self.db.items(self.old_trade.id))],
                         [(1, 2, 30)])
        self.assertEqual(self.events(self.old_trade)[:3], [tp.OPENED, tp.ORDER, tp.RECEIPT_REQUESTED])
        self.assertEqual(self.trade_row(self.forum_trade).source_kind, "forum")
        self.assertTrue(self.trade_row(self.forum_trade).legacy)   # 自由市場照舊流程
        starter = self.post.messages[0]
        self.assertEqual([o.value for o in self.buy_menu(self.post).options], ["1", "2"])   # 改畫成新格式
        self.assertIn("shop:manage", [c.custom_id for c in starter.components[0].children])
        self.assertEqual(self.call(self.db.listings())[0].next_key, 3)

    def test_old_trades_move_to_the_new_flow_at_import(self):
        # 上線時都還沒付：商品的舊交易轉成新流程，每個對話補發一張交易進度，不 @ 人；舊流程的領收通知作廢
        notice = self.old_trade.messages[-1]
        self.call(market_import.run_import(self.shop))
        self.assertFalse(self.trade_row(self.old_trade).legacy)
        card = self.card(self.old_trade)
        self.assertIn("交易功能更新了", card.content)
        self.assertIn("請需求方照供應方說的方式付款 NT$60", card.content)
        self.assertEqual(card.pinged, [])
        self.assertIn("trade:step:claim_paid", self.card_buttons(self.old_trade))
        self.assertIn("作廢", notice.content)
        self.assertEqual(notice.components, [])
        self.assertIn(tp.RECEIPT_HELD, self.events(self.old_trade))
        self.world.advance(hours=25)   # 舊的領收通知不會再自動完成
        self.call(self.trade.run_receipt_deadlines(self.world.now))
        self.assertEqual(self.trade_row(self.old_trade).status, "open")

    def test_rerun_does_not_duplicate(self):
        self.call(market_import.run_import(self.shop))
        trade, shop = self.services(ready=False)

        result = self.call(market_import.run_import(shop))

        self.assertTrue(result.already_done)
        self.assertTrue(trade.ready.is_set())
        self.assertEqual(len(self.call(self.db.trades())), 2)

    def test_failure_keeps_the_buttons_closed_and_can_be_rerun(self):
        self.forum.fail_archived = True
        with self.assertRaises(discord.HTTPException):
            self.call(market_import.run_import(self.shop))
        self.assertFalse(self.trade.ready.is_set())
        self.assertEqual(self.call(self.db.listings()), [])
        with self.assertRaises(ShopError):   # 留在畫面上的舊確認、舊面板也擋著
            self.call(self.shop.place_order(self.post.id, BUYER, {1: 1}))

        self.forum.fail_archived = False
        self.call(market_import.run_import(self.shop))
        self.assertTrue(self.trade.ready.is_set())

    def test_unbound_channels_fail_instead_of_importing_nothing(self):
        for key in ("shop_forum_channel_id", "cart_delivery_channel_id"):
            with self.subTest(key):
                saved = self.config.pop(key)
                with self.assertRaises(RuntimeError) as caught:
                    self.call(market_import.run_import(self.shop))
                self.assertIn("重新偵測", str(caught.exception))
                self.assertIsNone(self.call(self.db.get_meta(market_import.META_DONE)))
                self.config[key] = saved

    def test_old_text_is_exported_and_unreadable_items_are_reported(self):
        self.post.messages[0].components[0].children[0].options.append(SimpleNamespace(label="壞掉的", value="x:y"))
        with self.assertLogs(market_import.logger, level="WARNING") as logs:
            self.call(market_import.run_import(self.shop))
        self.assertTrue(any("壞掉的" in line for line in logs.output))
        (export,) = self.exports.glob("import_source_*.json")
        data = json.loads(export.read_text(encoding="utf-8"))
        self.assertIn({"label": "60 月相", "value": "1:30:10:5::0"}, data["listings"][0]["options"])
        self.assertEqual(data["listings"][0]["skipped"], ["壞掉的"])
        self.assertEqual(len(data["trades"]), 2)

    def test_redraw_failure_is_rerun_with_the_first_numbers(self):
        with mock.patch.object(ShopService, "redraw", side_effect=discord.HTTPException(mock.MagicMock(status=500), "x")):
            with self.assertRaises(discord.HTTPException):
                self.call(market_import.run_import(self.shop))
        self.assertFalse(self.trade.ready.is_set())

        result = self.call(market_import.run_import(self.shop))

        self.assertEqual((result.listings, result.trades), (1, 2))
        self.assertEqual(len(self.call(self.db.trades())), 2)
        self.assertEqual([o.value for o in self.buy_menu(self.post).options], ["1", "2"])

    def test_reactions_while_starting_up_after_the_import_are_handled_too(self):
        self.call(market_import.run_import(self.shop))
        trade, shop = self.services(ready=False)   # 平常的重啟：連上到檢查完匯入的那幾秒
        post = self.world.post(BUYER, "需要代練")
        self.world.put_reaction(post, "✅", SELLER)
        payload = SimpleNamespace(emoji="✅", guild_id=1, channel_id=post.id, message_id=post.id,
                                  user_id=SELLER.id, member=SELLER)
        self.assertIsNone(self.call(trade.handle_reaction(payload)))

        self.call(market_import.run_import(shop))

        self.assertEqual(self.trade_row(self.world.cart.all_threads[-1]).source_id, post.id)

    def test_closed_old_preorders_are_not_announced_again(self):
        # 舊商品已經截止的預購：舊程式早就 @ 過大家了，上線後不能再發一輪
        past = int((self.world.now - timedelta(days=3)).timestamp())
        self.post.messages[0].components[0].children[0].options[0] = SimpleNamespace(
            label="60 月相", value=f"1:30:10:5:{past}:1")
        self.call(market_import.run_import(self.shop))
        count = len(self.old_trade.messages)

        self.call(self.shop.run_cutoffs(self.world.now))

        self.assertEqual(len(self.old_trade.messages), count)
        self.assertTrue(self.call(self.db.get_variant(self.post.id, 1)).cutoff_noticed)

    def test_quantity_warnings_reach_the_log_and_the_export(self):
        self.post.messages[0].components[0].children[0].options[0] = SimpleNamespace(label="60 月相", value="1:30:10:1::0")
        with self.assertLogs(market_import.logger, level="WARNING") as logs:
            self.call(market_import.run_import(self.shop))
        self.assertTrue(any("sold_before 記 0" in line for line in logs.output))
        (export,) = self.exports.glob("import_source_*.json")
        self.assertTrue(any("sold_before" in w for w in json.loads(export.read_text(encoding="utf-8"))["warnings"]))

    def test_reactions_during_the_import_are_handled_afterwards(self):
        post = self.world.post(BUYER, "需要代儲")
        self.world.put_reaction(post, "✅", SELLER)
        payload = SimpleNamespace(emoji="✅", guild_id=1, channel_id=post.id, message_id=post.id,
                                  user_id=SELLER.id, member=SELLER)
        self.assertIsNone(self.call(self.trade.handle_reaction(payload)))
        self.assertIn("接單已經記下了", self.dms.await_args.kwargs["content"])   # 不然他看不出有沒有接到
        self.call(self.trade.handle_reaction(payload))
        self.assertEqual(self.dms.await_count, 1)   # 同一篇只說一次
        before = len(self.world.cart.all_threads)

        self.call(market_import.run_import(self.shop))

        self.assertEqual(len(self.world.cart.all_threads), before + 1)
        opened = self.world.cart.all_threads[-1]
        self.assertEqual(self.trade_row(opened).source_id, post.id)


    def test_reactions_during_a_failed_import_survive_a_restart(self):
        # 匯入失敗、修好前重啟過：記進資料庫的接單照樣補開；這段期間拿掉表情的不開
        kept, dropped = self.world.post(BUYER, "需要代儲"), self.world.post(BUYER_B, "需要代練")
        for post in (kept, dropped):
            self.world.put_reaction(post, "✅", SELLER)
            self.call(self.trade.handle_reaction(SimpleNamespace(
                emoji="✅", guild_id=1, channel_id=post.id, message_id=post.id, user_id=SELLER.id, member=SELLER)))
        dropped.messages[0].reactions[0].people.clear()
        before = len(self.world.cart.all_threads)
        trade, shop = self.services(ready=False)   # 重啟：記憶體裡的清單沒了

        self.call(market_import.run_import(shop))

        self.assertEqual(len(self.world.cart.all_threads), before + 1)
        self.assertEqual(self.trade_row(self.world.cart.all_threads[-1]).source_id, kept.id)
        self.assertEqual(self.call(self.db.get_meta(trade_service.DEFERRED_META)), "[]")


    def test_only_real_suppliers_are_told_their_reaction_was_kept(self):
        # 匯入期間不能接單的人（沒有觀星者身份組）按了：不記、不私訊「接單記下了」
        post = self.world.post(BUYER, "需要代儲")
        self.world.put_reaction(post, "✅", OUTSIDER)
        self.call(self.trade.handle_reaction(SimpleNamespace(
            emoji="✅", guild_id=1, channel_id=post.id, message_id=post.id, user_id=OUTSIDER.id, member=OUTSIDER)))
        self.dms.assert_not_awaited()
        self.assertIn(self.call(self.db.get_meta(trade_service.DEFERRED_META)), (None, "[]"))

    def test_a_reaction_that_fails_to_open_is_kept_for_next_time(self):
        post = self.world.post(BUYER, "需要代儲")
        self.world.put_reaction(post, "✅", SELLER)
        payload = SimpleNamespace(emoji="✅", guild_id=1, channel_id=post.id, message_id=post.id,
                                  user_id=SELLER.id, member=SELLER)
        self.call(self.trade.handle_reaction(payload))
        with mock.patch.object(TradeService, "open_trade", side_effect=RuntimeError("Discord 暫時出錯")), \
                self.assertLogs(trade_service.logger, level="ERROR"):
            self.call(market_import.run_import(self.shop))
        saved = json.loads(self.call(self.db.get_meta(trade_service.DEFERRED_META)))
        self.assertEqual([e["channel_id"] for e in saved], [post.id])   # 私訊說過不用重按：下次啟動再補


    def test_a_hiccup_while_opening_a_replayed_reaction_keeps_it(self):
        # 補開時第二次取需求貼文才碰到 Discord 暫時出錯：照樣留著下次再補，不能當成不符條件丟掉
        post = self.world.post(BUYER, "需要代儲")
        self.world.put_reaction(post, "✅", SELLER)
        self.call(self.trade.handle_reaction(SimpleNamespace(
            emoji="✅", guild_id=1, channel_id=post.id, message_id=post.id, user_id=SELLER.id, member=SELLER)))
        self.world.channels.pop(post.id)
        calls = []

        async def second_fails(channel_id):
            if channel_id == post.id:
                calls.append(channel_id)
                if len(calls) > 1:
                    raise discord.HTTPException(mock.MagicMock(status=503), "Service Unavailable")
                return post
            raise discord.NotFound(mock.MagicMock(status=404), "unknown channel")

        self.world.bot.fetch_channel = second_fails
        with self.assertLogs(trade_service.logger, level="ERROR"):
            self.call(market_import.run_import(self.shop))
        saved = json.loads(self.call(self.db.get_meta(trade_service.DEFERRED_META)))
        self.assertEqual([e["channel_id"] for e in saved], [post.id])

    def test_a_member_lookup_hiccup_while_replaying_keeps_the_reaction(self):
        # 重啟後補開時只剩資料庫裡的紀錄（沒有成員資料）：查成員碰到 Discord 暫時出錯，照樣留著下次補
        post = self.world.post(BUYER, "需要代儲")
        self.world.put_reaction(post, "✅", SELLER)
        self.call(self.trade.handle_reaction(SimpleNamespace(
            emoji="✅", guild_id=1, channel_id=post.id, message_id=post.id, user_id=SELLER.id, member=SELLER)))
        trade, shop = self.services(ready=False)   # 重啟：記憶體裡帶成員資料的那份沒了
        self.world.cached = {BUYER.id}
        real = self.world.guild.fetch_member

        async def hiccup(uid):
            if uid == SELLER.id:
                raise discord.HTTPException(mock.MagicMock(status=503), "Service Unavailable")
            return await real(uid)

        self.world.guild.fetch_member = hiccup
        with self.assertLogs(trade_service.logger, level="ERROR"):
            self.call(market_import.run_import(shop))
        saved = json.loads(self.call(self.db.get_meta(trade_service.DEFERRED_META)))
        self.assertEqual([e["channel_id"] for e in saved], [post.id])

    def test_a_reaction_on_a_deleted_post_is_dropped_but_a_hiccup_is_kept(self):
        gone, flaky = self.world.post(BUYER, "需要代儲"), self.world.post(BUYER_B, "需要代練")
        for post in (gone, flaky):
            self.world.put_reaction(post, "✅", SELLER)
            self.call(self.trade.handle_reaction(SimpleNamespace(
                emoji="✅", guild_id=1, channel_id=post.id, message_id=post.id, user_id=SELLER.id, member=SELLER)))
        gone.messages.clear()   # 需求方把第一則訊息刪了：確定不在了，不用每次啟動再試
        self.world.channels.pop(flaky.id)
        real_fetch = self.world.bot.fetch_channel

        async def hiccup(channel_id):
            if channel_id == flaky.id:
                raise discord.HTTPException(mock.MagicMock(status=503), "Service Unavailable")
            return await real_fetch(channel_id)

        self.world.bot.fetch_channel = hiccup
        with self.assertLogs(trade_service.logger, level="ERROR"):
            self.call(market_import.run_import(self.shop))
        saved = json.loads(self.call(self.db.get_meta(trade_service.DEFERRED_META)))
        self.assertEqual([e["channel_id"] for e in saved], [flaky.id])   # 暫時出錯的留著下次再補


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
        self.assertEqual(self.banner_name(starter), upload.filename)

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

    def test_a_listing_named_like_the_guide_is_left_alone(self):
        listing = self.list_item(title="舊商品")
        listing.name = ShopSettings().guide_title   # 不准用這個標題之前上架的舊商品
        self.call(self.shop.ensure_guide(self.forum))
        guide = self.posts[-1]
        self.assertIsNot(guide, listing)
        self.assertIn("需求方怎麼買", guide.messages[0].embed.description)
        self.assertNotIn("需求方怎麼買", listing.messages[0].embed.description or "")

    def test_restarting_refreshes_an_old_guide_but_never_posts_one(self):
        self.call(self.shop.refresh_guide())
        self.assertEqual(self.posts, [])   # 沒有置頂說明就不發（綁商品論壇時才發）
        self.call(self.shop.ensure_guide(self.forum))
        starter = self.posts[-1].messages[0]
        starter.embed.description = "舊版說明"
        self.posts[-1].auto_archive()

        self.call(self.shop.refresh_guide())

        self.assertIn("需求方怎麼買", starter.embed.description)

    def test_guide_is_posted_and_pinned_once(self):
        note = self.call(self.shop.ensure_guide(self.forum))
        guide = self.posts[-1]
        self.assertEqual(guide.name, "📌 上架說明")
        self.assertTrue(guide.flags.pinned)
        self.assertIn(guide.jump_url, note)
        description = guide.messages[0].embed.description
        self.assertIn("需求方怎麼買", description)
        self.assertIn("定金/尾款", description)
        for word in ("thread", "上架者", "買家"):
            self.assertNotIn(word, description)

        guide.auto_archive()
        self.call(self.shop.ensure_guide(self.forum))

        self.assertEqual(len(self.posts), 1)
        self.assertFalse(guide.archived)
        self.assertEqual([t.name for t in self.forum.available_tags], ["預購中"])

    def test_rebinding_refreshes_outdated_guide_text(self):
        self.call(self.shop.ensure_guide(self.forum))
        guide = self.posts[-1]
        starter = guide.messages[0]
        starter.embed.description = "舊版說明：上架者到商品貼文加入品相"
        guide.auto_archive()  # 置頂文也可能被自動封存，封存中改不了訊息

        note = self.call(self.shop.ensure_guide(self.forum))

        self.assertEqual(len(self.posts), 1)
        self.assertNotIn("品相", starter.embed.description)
        self.assertEqual(starter.edits[-1]["attachments"], "unchanged")  # 圖沒換就不動附件
        self.assertIn("已更新", note)
        edits = len(starter.edits)
        self.call(self.shop.ensure_guide(self.forum))  # 已經是最新版就不再改
        self.assertEqual(len(starter.edits), edits)

    def test_missing_tag_permission_is_reported(self):
        async def refuse(**kwargs):
            raise discord.Forbidden(mock.MagicMock(status=403), "Missing Permissions")

        self.forum.edit = refuse
        note = self.call(self.shop.ensure_guide(self.forum))
        self.assertIn("⚠️", note)
        self.assertIn("預購中", note)


class ServerNicknameTests(ShopTestCase):

    def test_seller_name_comes_from_the_server_when_the_cache_misses(self):
        thread = self.list_item()
        self.world.cached = set()

        self.add(thread, "60 月相｜30｜10｜")

        self.assertEqual(thread.messages[0].embed.author.name, f"供應方：{SELLER.display_name}")
        self.assertIn(SELLER.id, self.world.api_lookups)


class PanelTests(ShopTestCase):

    def setUp(self):
        super().setUp()
        self.thread = self.list_item()
        self.add(self.thread, "60 月相｜30｜10｜", "寰宇電台｜20｜｜")
        p = mock.patch.object(shop_commands, "safe_send_interaction_message", mock.AsyncMock())
        self.sent_ephemeral = p.start()
        self.addCleanup(p.stop)

    def panel_interaction(self, user=SELLER, message=None):
        return SimpleNamespace(
            client=SimpleNamespace(get_cog=lambda name: SimpleNamespace(shop=self.shop)),
            user=user, guild=self.world.guild, channel=self.thread, message=message,
            response=SimpleNamespace(defer=mock.AsyncMock(), edit_message=mock.AsyncMock(),
                                     send_modal=mock.AsyncMock(), is_done=lambda: True),
            edit_original_response=mock.AsyncMock(),
        )

    def panel(self, thread=None):
        return self.call(shop_commands._panel(self.shop, self.listing(thread or self.thread)))

    def assert_panel_redrawn(self, interaction, text):
        kwargs = interaction.edit_original_response.await_args.kwargs
        self.assertIn(text, kwargs["content"])
        picks = [c for c in kwargs["view"].children if isinstance(c, shop_commands.ShopPickSelect)]
        self.assertEqual(len(picks), 2)  # 重畫出新的選單＝回到未選取
        return kwargs

    def test_panel_layout(self):
        _, view = self.panel()
        rows = {}
        for child in view.children:
            rows.setdefault(child.item.row, []).append(child.item.custom_id.split(":")[2])
        self.assertEqual(rows, {0: ["add", "batch", "info"], 2: ["close"], 3: ["edit"], 4: ["delete"]})

        deposit = self.list_item(title="座姿玩偶", delivery="physical")
        self.add(deposit, f"玩偶A｜500/1300｜10｜{self.cutoff_text(days=20)}")
        self.order(deposit, BUYER, {1: 2})
        embed, view = self.panel(deposit)
        self.assertEqual([c.item.custom_id.split(":")[2] for c in view.children if c.item.row == 1],
                         ["delay", "balance"])
        self.assertIn("下單 2｜已確認定金 0｜已付尾款 0", embed.description)
        self.assertLessEqual(max(c.item.row for c in view.children), 4)

        preorder = self.list_item(title="吊飾")
        self.add(preorder, f"吊飾C｜300｜｜{self.cutoff_text(days=3)}")
        _, view = self.panel(preorder)
        self.assertEqual([c.item.custom_id.split(":")[2] for c in view.children if c.item.row == 1],
                         ["delay", "deliver"])

    def test_confirming_an_order_points_to_the_conversation(self):
        pressing = self.panel_interaction(user=BUYER)
        self.call(shop_commands.ShopConfirmOrder(self.thread.id, {1: 1}).callback(pressing))
        text = pressing.edit_original_response.await_args.kwargs["content"]
        self.assertTrue(text.startswith("已下單，請到交易對話跟供應方確認細節："), text)

    def test_panel_marks_unavailable_items_like_the_listing(self):
        self.add(self.thread, "一條龍｜40｜1｜")
        self.order(self.thread, BUYER, {3: 1})
        embed, _ = self.panel()
        self.assertIn("一條龍｜~~NT$40｜立即購買~~ `已售完`", embed.description)

    def test_buy_menu_is_cleared_as_soon_as_the_quantity_form_opens(self):
        message = self.thread.messages[0]
        before = len(message.edits)

        async def run():
            select = shop_commands.ShopBuySelect(self.thread.id, options=[
                discord.SelectOption(label="60 月相", value="1"), discord.SelectOption(label="寰宇電台", value="2")],
                max_values=2)
            select.item._values = ["2"]
            interaction = self.panel_interaction(user=BUYER, message=message)
            await select.callback(interaction)
            return interaction

        interaction = self.call(run())

        modal = interaction.response.send_modal.await_args.args[0]
        self.assertEqual([key for key, _, _ in modal.inputs], [2])  # 視窗問的是剛選的品項
        self.assertEqual(len(message.edits), before + 1)  # 商品貼文重畫＝選單清空，取消後還能再選

    def submit_variant_form(self, variant, *, name, price, limit, cutoff, kind):
        async def run():
            modal = shop_commands.VariantModal(self.thread.id, variant)
            modal.name._value, modal.price._value, modal.limit._value = name, price, limit
            modal.cutoff._value = modal.cutoff.default if cutoff is None else cutoff
            modal.kind._values = [kind]
            interaction = self.panel_interaction()
            await modal.on_submit(interaction)
            return interaction
        return self.call(run())

    def test_switching_a_preorder_to_instant_ignores_the_leftover_cutoff(self):
        self.add(self.thread, f"預購品｜100｜｜{self.cutoff_text(days=3)}")
        variant = self.listing(self.thread).variant(3)
        # 編輯視窗的截止欄預填原本的時間，只把類型改成立即購買就送出
        self.submit_variant_form(variant, name="預購品", price="100", limit="", cutoff=None, kind="instant")
        self.assertIsNone(self.listing(self.thread).variant(3).cutoff)

    def test_new_item_with_a_cutoff_but_instant_type_is_refused(self):
        interaction = self.submit_variant_form(None, name="新品", price="50", limit="5",
                                               cutoff=self.cutoff_text(days=3), kind="instant")
        self.assertEqual(len(self.listing(self.thread).variants), 2)  # 沒有加進去
        self.assertIn("類型選「預購」", interaction.edit_original_response.await_args.kwargs["content"])

    def test_deposit_form_round_trip(self):
        # 表單用的是真的現在時間（不是假伺服器的時間），截止時間要寫在那之後
        cutoff = (shop_commands._now() + timedelta(days=30)).strftime("%Y/%m/%d %H:%M")
        interaction = self.submit_variant_form(None, name="玩偶A", price="500/1300", limit="10",
                                               cutoff=cutoff, kind="deposit")
        self.assertIn("定金＋尾款的品項不能和一次付清", interaction.edit_original_response.await_args.kwargs["content"])
        deposit = self.list_item(title="座姿玩偶")
        self.thread = deposit
        self.submit_variant_form(None, name="玩偶A", price="500/1300", limit="10", cutoff=cutoff, kind="deposit")
        variant = self.listing(deposit).variant(1)
        self.assertEqual((variant.kind, variant.price, variant.balance), ("deposit", 500, 1300))
        self.assertEqual(shop_commands.VariantModal(deposit.id, variant).price.default, "500/1300")

    def test_editing_a_variant_redraws_the_panel(self):
        interaction = self.submit_variant_form(self.listing(self.thread).variant(1), name="60 月相", price="35",
                                               limit="10", cutoff="", kind="instant")
        interaction.response.defer.assert_awaited_once_with()  # 延後回應＝之後改的是面板那則
        kwargs = self.assert_panel_redrawn(interaction, "已更新")
        self.assertIn("NT$35", kwargs["embed"].description)
        self.assertEqual(self.listing(self.thread).variant(1).price, 35)

    def test_delete_confirmation_stays_in_the_panel(self):
        async def run():
            _, view = await shop_commands._panel(self.shop, await self.shop.load(self.thread.id))
            pick = view.children[-1]  # 刪除品項選單
            pick.item._values = [pick.item.options[1].value]
            asking = self.panel_interaction()
            await pick.callback(asking)
            confirm = asking.response.edit_message.await_args.kwargs["view"].children[0]
            doing = self.panel_interaction()
            await confirm.callback(doing)
            return asking, doing

        asking, doing = self.call(run())

        self.assertIn("寰宇電台", asking.response.edit_message.await_args.kwargs["content"])
        self.assert_panel_redrawn(doing, "已刪除")
        self.assertEqual([v.name for v in self.listing(self.thread).variants], ["60 月相"])

    def choose_to_edit(self, choosing):
        async def run():
            _, view = await shop_commands._panel(self.shop, await self.shop.load(self.thread.id))
            pick = view.children[-2]  # 編輯品項選單
            pick.item._values = [pick.item.options[0].value]
            await pick.callback(choosing)
        self.call(run())

    def panel_picks(self, call):
        return [c for c in call.kwargs["view"].children if isinstance(c, shop_commands.ShopPickSelect)]

    def test_edit_menu_opens_the_form_and_clears_the_panel(self):
        choosing = self.panel_interaction()
        # 重畫一定在跳出視窗之後：互動只能回應一次，先改面板視窗就跳不出來
        choosing.edit_original_response.side_effect = \
            lambda **kw: self.assertEqual(choosing.response.send_modal.await_count, 1)

        self.choose_to_edit(choosing)

        modal = choosing.response.send_modal.await_args.args[0]
        self.assertEqual(modal.name.default, "60 月相")
        self.assertEqual(len(self.panel_picks(choosing.edit_original_response.await_args)), 2)

    def test_panel_is_cleared_through_the_message_when_the_original_response_fails(self):
        choosing = self.panel_interaction(message=SimpleNamespace(id=4242))
        choosing.edit_original_response.side_effect = discord.NotFound(mock.MagicMock(status=404), "Unknown Message")
        choosing.followup = SimpleNamespace(edit_message=mock.AsyncMock())

        self.choose_to_edit(choosing)

        call = choosing.followup.edit_message.await_args
        self.assertEqual(call.args[0], 4242)
        self.assertEqual(len(self.panel_picks(call)), 2)

    def test_panel_that_cannot_be_cleared_is_only_logged(self):
        choosing = self.panel_interaction(message=SimpleNamespace(id=4242))
        refused = discord.NotFound(mock.MagicMock(status=404), "Unknown Message")
        choosing.edit_original_response.side_effect = refused
        choosing.followup = SimpleNamespace(edit_message=mock.AsyncMock(side_effect=refused))

        with self.assertLogs(shop_commands.logger, level="WARNING"):
            self.choose_to_edit(choosing)  # 不丟例外：視窗已經跳出，供應方照常編輯

        choosing.response.send_modal.assert_awaited_once()


class ReportTests(ShopTestCase):
    """週報、📋 我的交易、群主的交易看板：讀同一份整理。"""

    def setUp(self):
        super().setUp()
        p = mock.patch.object(market_report, "send_dm", self.dms)
        p.start()
        self.addCleanup(p.stop)
        thread = self.list_item()
        self.add(thread, "60 月相｜30｜｜")
        self.waiting = self.order(thread, BUYER, {1: 1})          # 等需求方付款：不用供應方處理
        self.claimed = self.order(thread, BUYER_B, {1: 1})
        self.step(self.claimed, BUYER_B, tp.CLAIM_PAID)          # 需求方說付了：要供應方確認
        other = self.list_item(seller=SUPPLIER_B, title="代練")
        self.add(other, "一條龍｜40｜｜", actor=SUPPLIER_B)
        self.order(other, BUYER, {1: 1})                          # 另一位觀星者只有等付款的：不發週報

    def summaries(self):
        return self.call(market_report.summarize(self.shop, self.world.now))

    def test_my_trades_lists_what_needs_me(self):
        text = market_report.my_trades_text(self.summaries(), SELLER.id)
        self.assertIn("2 筆還沒結束", text)
        todo, rest = text.split("**不用你處理**")
        self.assertIn(f"<#{self.claimed.id}>", todo)
        self.assertIn("需求方表示已付款，等你確認", todo)
        self.assertIn(f"<#{self.waiting.id}>", rest)
        self.assertIn("等需求方付款", rest)
        self.assertEqual(market_report.my_trades_text(self.summaries(), OUTSIDER.id), "你目前沒有還沒結束的交易。")

    def test_each_todo_says_how_long_it_has_waited(self):
        # 寫這一步等了幾天，不是交易開了幾天（定金交易一開就是好幾個月，看不出哪筆是剛卡住的）
        self.world.advance(days=30)
        self.step(self.waiting, BUYER, tp.CLAIM_PAID)   # 開單 30 天後才說付了：等確認從這時候算
        self.world.advance(days=2)
        text = market_report.my_trades_text(self.summaries(), SELLER.id)
        self.assertIn("需求方表示已付款，等你確認（2 天）", text)
        self.assertNotIn("開了 32 天", text)

    def test_waiting_for_goods_is_not_idle(self):
        # 定金收了、在等貨：本來就會安靜好幾個月，不算沒動靜，也不算要供應方處理（不然每週都被週報催）
        thread = self.list_item(seller=SUPPLIER_B, title="座姿玩偶", delivery="physical")
        self.add(thread, f"玩偶A｜500/1300｜10｜{self.cutoff_text(days=60)}", actor=SUPPLIER_B)
        waiting = self.order(thread, BUYER, {1: 1})
        self.step(waiting, SUPPLIER_B, tp.CONFIRM_DEPOSIT)
        self.world.advance(days=20)
        summary = next(s for s in self.summaries() if s.trade_id == waiting.id)
        self.assertEqual(summary.waiting, "等貨中")
        self.assertFalse(summary.needs_supplier)
        self.assertNotIn(f"<#{waiting.id}>", market_report.my_trades_text(self.summaries(), SUPPLIER_B.id).split(
            "不用你處理")[0])

    def test_the_owner_sees_whose_list_it_is(self):
        text = market_report.my_trades_text(self.summaries(), SELLER.id, name="觀星者小舖")
        self.assertIn("📋 **觀星者小舖 的交易", text)
        self.assertIn("**要他處理**", text)
        self.assertIn("等他確認", text)
        self.assertNotIn("要你", text)
        cog = shop_commands.ShopCommands(mock.MagicMock())
        cog.shop = self.shop
        text, _ = self.call(cog.dashboard(SELLER.id))
        self.assertIn(f"{SELLER.display_name} 的交易", text)

    def test_weekly_report_goes_out_once_on_monday(self):
        # T0 是週六晚上；週一中午才發
        due = self.call(market_report.run_weekly(self.shop, self.world.now))
        self.assertEqual((due.astimezone(shop_service.APP_TZ).weekday(), due.astimezone(shop_service.APP_TZ).hour),
                         (0, 12))
        self.dms.assert_not_awaited()

        self.world.now = due + timedelta(hours=3)
        self.call(market_report.run_weekly(self.shop, self.world.now))
        self.call(market_report.run_weekly(self.services()[1], self.world.now))   # 重啟後同一週不重發

        (call,) = self.dms.await_args_list
        self.assertEqual(call.args[0].id, SELLER.id)
        self.assertIn(f"<#{self.claimed.id}>", call.kwargs["embed"].description)
        self.assertIn("📋 我的交易", call.kwargs["embed"].description)
        week = market_report.week_key(due.astimezone(shop_service.APP_TZ).date())
        self.assertIsNotNone(self.call(self.db.weekly_report(week, SELLER.id))[0])
        self.assertIsNone(self.call(self.db.weekly_report(week, SUPPLIER_B.id)))   # 沒有待辦就不發

    def test_missed_monday_waits_for_next_week_and_failures_are_recorded(self):
        monday = self.call(market_report.run_weekly(self.shop, self.world.now))
        self.world.now = monday + timedelta(days=1)   # 週二才開機：等下週
        self.assertEqual(self.call(market_report.run_weekly(self.shop, self.world.now)), monday + timedelta(days=7))
        self.dms.assert_not_awaited()

        self.world.now = monday + timedelta(days=7, hours=1)
        self.dms.return_value = None   # 私訊關閉
        self.call(market_report.run_weekly(self.shop, self.world.now))
        week = market_report.week_key((monday + timedelta(days=7)).astimezone(shop_service.APP_TZ).date())
        self.assertEqual(self.call(self.db.weekly_report(week, SELLER.id))[1], "私訊沒送到")
        board = self.call(market_report.dashboard_text(self.shop, self.summaries(), self.world.now))
        self.assertIn("這週週報沒送到：1 位", board)

    def test_dashboard_counts_per_supplier(self):
        board = self.call(market_report.dashboard_text(self.shop, self.summaries(), self.world.now))
        self.assertIn("還沒結束 3 筆", board)
        self.assertIn(f"**{SELLER.display_name}**　還沒結束 2｜要他處理 1", board)
        self.assertIn(f"**{SUPPLIER_B.display_name}**　還沒結束 1｜要他處理 0", board)
        self.assertIn("認不出身分的舊交易：0 筆", board)

    def test_idle_trades_count_only_people_and_records(self):
        self.world.advance(days=15)
        self.call(self.shop.trades.run_waiting_reminders(self.world.now))   # bot 的提醒不算動靜
        summary = next(s for s in self.summaries() if s.trade_id == self.waiting.id)
        self.assertGreaterEqual(summary.days_idle, 14)
        self.assertTrue(summary.needs_supplier)
        # bot 自己的訊息不算
        self.call(self.trade.note_chat(FakeMessage(self.world, next(self.world.ids), BOT, "提醒", thread=self.waiting)))
        self.assertGreaterEqual(next(s for s in self.summaries() if s.trade_id == self.waiting.id).days_idle, 14)
        said = FakeMessage(self.world, next(self.world.ids), BUYER, "我明天付", thread=self.waiting)
        self.waiting.messages.append(said)
        self.call(self.trade.note_chat(said))   # 有人講話時 bot 收到訊息就記下，整理清單時不用回頭翻對話
        with mock.patch.object(TradeService, "read", side_effect=AssertionError("清單不該去讀交易對話")):
            summary = next(s for s in self.summaries() if s.trade_id == self.waiting.id)
        self.assertEqual(summary.days_idle, 0)

    def test_delayed_preorder_waits_for_goods(self):
        thread = self.list_item(title="吊飾")
        self.add(thread, f"吊飾C｜300｜｜{self.cutoff_text(hours=1)}")
        trade_thread = self.order(thread, BUYER_B, {1: 1})
        self.step(trade_thread, SELLER, tp.CONFIRM_FULL)
        self.world.advance(hours=2)
        self.call(self.shop.run_cutoffs(self.world.now))
        self.call(self.shop.delay(thread.id, SELLER, 1, self.cutoff_text(days=10), "原廠延後"))

        summary = next(s for s in self.summaries() if s.trade_id == trade_thread.id)

        self.assertEqual((summary.todo, summary.waiting), ([], "等貨中"))   # 跟等待提醒一樣，預計交貨日前不催

    def test_handled_unrecognized_trades_drop_off_the_board(self):
        kept = FakeThread(self.world, next(self.world.ids), "交易確認 - ? - 1", parent_id=CART_ID)
        handled = FakeThread(self.world, next(self.world.ids), "交易確認 - ? - 2", parent_id=CART_ID)
        handled.locked = True
        for thread in (kept, handled):
            self.world.channels[thread.id] = thread

        async def remember():
            async with self.db.transaction():
                await self.db.set_meta(market_import.UNRECOGNIZED_META, json.dumps([kept.id, handled.id, 424242]))
        self.call(remember())

        board = self.call(market_report.dashboard_text(self.shop, self.summaries(), self.world.now))
        self.assertIn(f"認不出身分的舊交易：1 筆（<#{kept.id}>）", board)

    def test_console_screen(self):
        from commands import admin_console

        async def build():
            return admin_console.render_market("總表", [(SELLER.id, "供應者甲"), (SUPPLIER_B.id, "供應者乙")])

        view = self.call(build())
        ids = [getattr(getattr(c, "item", c), "custom_id", None) for c in view.walk_children()]
        self.assertIn(f"console:market:seller:{SELLER.id}", ids)
        self.assertIn("console:home", ids)
        self.assertIn("market", [screen for screen, *_ in admin_console.ACTIONS])

        async def crowded(page):
            many = [(1000 + n, f"觀星者{n:02d}") for n in range(17)]
            view = admin_console.render_market("總表", many, page=page)
            return [getattr(getattr(c, "item", c), "custom_id", None) for c in view.walk_children()]

        first, second = self.call(crowded(0)), self.call(crowded(1))
        self.assertIn("console:market:page:1", first)            # 超過一頁就翻頁，每一位都點得到
        self.assertIn("console:market:seller:1000", first)
        self.assertIn("console:market:seller:1016", second)
        self.assertNotIn("console:market:seller:1016", first)


class LayeringTests(unittest.TestCase):

    def test_shop_modules_do_not_import_commands(self):
        for module in (shop_service, shop_trade, market_import, sys.modules["services.community.shop_listing"]):
            tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
            names = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
            names |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
            with self.subTest(module.__name__):
                self.assertFalse([n for n in names if n.split(".")[0] == "commands"])

    def test_custom_ids_resolve_back(self):
        async def check():
            cases = [
                shop_commands.ShopManageButton(),
                shop_commands.ShopConfirmOrder(500, {1: 2, 3: 1}, "0123abcd"),
                shop_commands.ShopPanelButton("balance", 500),
                shop_commands.ShopConfirmButton("delete", 500, 7),
                shop_commands.ShopConfirmButton("balance", 500, 7),
                shop_commands.ShopConfirmButton("deliver", 500, 2),
                shop_commands.ShopConfirmButton("close", 500),
                shop_commands.ShopBatchButton("fix", 500),
                shop_commands.ShopScheduleSelect("balance", 500, options=[discord.SelectOption(label="x", value="1")]),
                shop_commands.ShopBuySelect(500, options=[discord.SelectOption(label="x", value="1")]),
                shop_commands.ShopStepButton(tp.DELIVER, 3, label="📦 已交付：x"),
                shop_commands.ShopStepButton(tp.CONFIRM_DEPOSIT, None, label="已收到定金（供應方）"),
                shop_commands.ShopStepSelect(tp.SHIP, options=[discord.SelectOption(label="x", value="1")]),
            ]
            for original in cases:
                cls = type(original)
                match = cls.__discord_ui_compiled_template__.fullmatch(original.item.custom_id)
                self.assertIsNotNone(match, original.item.custom_id)
                restored = await cls.from_custom_id(None, original.item, match)
                self.assertEqual(restored.item.custom_id, original.item.custom_id)
                self.assertLessEqual(len(original.item.custom_id), 100)
            order = cases[1]
            restored = await shop_commands.ShopConfirmOrder.from_custom_id(
                None, order.item, shop_commands.ShopConfirmOrder.__discord_ui_compiled_template__.fullmatch(
                    order.item.custom_id))
            self.assertEqual((restored.picks, restored.signature), ({1: 2, 3: 1}, "0123abcd"))
            # 上線前發出去的管理按鈕（帶著上架者、編號、幣別）也認得
            self.assertIsNotNone(shop_commands.ShopManageButton.__discord_ui_compiled_template__.fullmatch(
                "shop:manage:21:7:PY%3A%E5%B9%A3"))
            self.assertIsNone(shop_commands.ShopStepButton.__discord_ui_compiled_template__.fullmatch(
                "trade:step:pick:ship"))   # 選單跟按鈕不會搶同一個 custom_id

        asyncio.run(check())

    def test_modals_stay_within_discord_limits(self):
        """欄位標題 45 字、欄位描述 100 字、一張 modal 最多 5 個欄位；超過的話 Discord 直接拒絕，modal 打不開。"""
        from dataclasses import replace
        from datetime import datetime, timezone

        from services.community.shop_listing import Listing

        async def check():
            cutoff = datetime(2099, 10, 20, 15, 59, tzinfo=timezone.utc)
            variant = Variant(1, "6480 月相", 3000, limit=3)
            deposit = Variant(2, "玩偶A", 500, kind="deposit", balance=1300, limit=3, cutoff=cutoff)
            listing = Listing(thread_id=500, owner_id=21, unit="NT$", title="t", description="", variants=(variant,))
            long_names = tuple(Variant(n, "【定金】鳴潮共鳴者主題尤諾1/7手辦宛如水中月Ver. 典藏限定版附特典", 700_000_000)
                               for n in range(1, 5))
            convert = Listing(thread_id=500, owner_id=21, unit="HK$$$$$$$$", title="【定金】t", description="",
                              variants=long_names)
            modals = [shop_commands.BatchModal(500, "a｜1"), shop_commands.VariantModal(500),
                      shop_commands.DepositConvertModal(convert),
                      shop_commands.DepositConvertModal(replace(convert, variants=long_names + (variant,))),
                      shop_commands.VariantModal(500, variant), shop_commands.VariantModal(500, deposit, cutoff_locked=True),
                      shop_commands.ListingInfoModal(), shop_commands.ListingInfoModal(listing=listing),
                      shop_commands.QuantityModal(500, [variant]), shop_commands.DelayModal(500, [deposit])]
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
            soon = (shop_commands._now() + timedelta(days=30)).strftime("%Y/%m/%d %H:%M")  # 截止時間最多五年內
            text = f"6480 月相｜3000｜3｜{soon}\n玩偶A｜500/1300｜｜{soon}\n寰宇電台｜20"
            embeds, view = shop_commands._batch_preview(500, text)
            restored = shop_commands._preview_text(SimpleNamespace(embeds=embeds))
            self.assertEqual(parse_batch(restored, now=shop_commands._now()), parse_batch(text, now=shop_commands._now()))
            self.assertEqual([c.item.custom_id for c in view.children], ["shop:batchok:500", "shop:batchfix:500"])
            bad, bad_view = shop_commands._batch_preview(500, "壞掉的一行")
            self.assertIn("第 1 行", bad[0].description)
            self.assertEqual(shop_commands._preview_text(SimpleNamespace(embeds=bad)), "壞掉的一行")
            self.assertEqual([c.item.custom_id for c in bad_view.children], ["shop:batchfix:500"])

        asyncio.run(check())

    def test_the_pinned_guide_is_refreshed_after_the_import(self):
        async def check():
            cog = shop_commands.ShopCommands(mock.MagicMock())
            cog.shop = SimpleNamespace(refresh_guide=mock.AsyncMock())
            with mock.patch.object(shop_commands, "run_import", mock.AsyncMock(
                    return_value=SimpleNamespace(already_done=True))):
                self.assertTrue(await cog._import())
            cog.shop.refresh_guide.assert_awaited_once()

        asyncio.run(check())

    def test_daily_backup_waits_for_its_time(self):
        # 排程最多睡 6 小時就醒一次：換日後、還沒到 03:30 的那次不做，備份時刻才不會跟著開機時間漂
        async def check():
            cog = shop_commands.ShopCommands(mock.MagicMock())
            ready = asyncio.Event()
            cog.shop = SimpleNamespace(db=mock.AsyncMock(return_value="db"), trade=SimpleNamespace(ready=ready))
            tz = shop_commands.APP_TZ
            with mock.patch.object(shop_commands, "backup_daily", mock.AsyncMock()) as backup:
                wake = await cog._backup(datetime(2026, 11, 7, 1, 0, tzinfo=tz))
                backup.assert_not_awaited()
                self.assertEqual(wake, datetime(2026, 11, 7, 3, 30, tzinfo=tz))
                # 上線匯入還沒做完：備份到的會是空的資料庫，而今天有了一份就不會再備
                self.assertEqual(await cog._backup(wake), wake + timedelta(minutes=5))
                backup.assert_not_awaited()
                ready.set()
                wake = await cog._backup(wake)
                backup.assert_awaited_once()
                self.assertEqual(wake, datetime(2026, 11, 8, 3, 30, tzinfo=tz))

        asyncio.run(check())

    def test_remaining_quantity_default_fits_its_field(self):
        variant = shop_listing_module.Variant(key=1, name="玩偶A", price=500, limit=1_000_004, taken=0)
        modal = shop_commands.VariantModal(1, variant)
        self.assertEqual(modal.limit.default, "999999")

    def test_the_buy_menu_redraws_under_the_listing_lock(self):
        # 跟截止、下單的重畫排隊：晚到的舊畫面才不會蓋掉新的
        async def check():
            held = []
            lock = asyncio.Lock()
            ready = asyncio.Event()
            ready.set()
            shop = SimpleNamespace(check_pick=mock.AsyncMock(return_value=[]), lock=lambda listing_id: lock,
                                   trade=SimpleNamespace(ready=ready))

            async def refresh(listing_id):
                held.append(lock.locked())

            shop.refresh_listing = refresh
            select = shop_commands.ShopBuySelect(1)
            select.item._values = ["1"]
            interaction = SimpleNamespace(client=SimpleNamespace(get_cog=lambda name: SimpleNamespace(shop=shop)),
                                          user=BUYER, response=SimpleNamespace(send_modal=mock.AsyncMock()))
            await select.callback(interaction)
            self.assertEqual(held, [True])

        asyncio.run(check())

    def test_balance_menu_shows_confirmed_deposits(self):
        variant = SimpleNamespace(name="玩偶A・漂泊者")
        self.assertEqual(shop_commands._schedule_label(variant, (4, 3, 0)), "玩偶A・漂泊者（已確認定金 3 份）")
        self.assertEqual(shop_commands._schedule_label(variant, None), "玩偶A・漂泊者")
        self.assertLessEqual(len(shop_commands._schedule_label(SimpleNamespace(name="長" * 100), (1, 1, 0))), 100)

    def test_cog_wires_the_listing_source_and_its_schedules(self):
        async def check():
            # 這個測試不准碰資料庫：匯入要等 bot 連上（這裡永遠不會），真的叫到就是測試寫錯
            trade = TradeService(mock.MagicMock(), make_view=_make_view,
                                 db=mock.AsyncMock(side_effect=AssertionError("測試不能開市集資料庫")))
            bot = mock.MagicMock()
            bot.get_cog.return_value = SimpleNamespace(trade=trade)
            bot.wait_until_ready = lambda: asyncio.sleep(3600)
            cog = shop_commands.ShopCommands(bot)
            with mock.patch.object(shop_commands, "run_due_loop", new=mock.MagicMock(
                    side_effect=lambda *a, **k: asyncio.sleep(3600))) as loop_call, \
                    mock.patch.object(shop_commands.owner_alerts, "register") as register:
                await cog.cog_load()
                await asyncio.sleep(0)
            try:
                self.assertIs(cog.shop.trade, trade)
                self.assertIs(trade.kind_of(SimpleNamespace(source_kind="listing")), cog.shop.source)
                bot.add_dynamic_items.assert_called_once()
                bot.add_view.assert_called_once()
                names = [c.args[0] for c in loop_call.call_args_list]
                self.assertEqual(names, ["商品截止", "商品交易等待提醒", "市集資料庫備份", "市集週報"])
                # 截止的排程跟著品項新增、編輯提早醒來
                self.assertIs(loop_call.call_args_list[0].kwargs["wake"], cog.shop.cutoffs_changed)
                self.assertEqual(register.call_args.args[0], shop_commands.ALERT_KIND)
                self.assertFalse(trade.ready.is_set())   # 匯入做完才開放
            finally:
                await cog.cog_unload()

        asyncio.run(check())


class WordingTests(unittest.TestCase):
    """給群友看的字：品項、供應方、需求方；不說 thread、上架者、買家（程式欄位名不算，只看字串）。"""

    def test_source_strings(self):
        from commands import forum_monitor

        modules = (shop_service, shop_trade, market_import, trade_service, shop_commands, forum_monitor,
                   sys.modules["services.community.shop_listing"])
        for module in modules:
            tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
            docstrings = {id(node.body[0].value) for node in ast.walk(tree)
                          if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                          and node.body and isinstance(node.body[0], ast.Expr)
                          and isinstance(node.body[0].value, ast.Constant)}
            strings = [node.value for node in ast.walk(tree)
                       if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings]
            with self.subTest(module.__name__):
                self.assertEqual([s for s in strings if "上架者" in s or "買家" in s], [])
                # log 的格式字串（帶 %s）是給管理員看的，可以寫 thread
                self.assertEqual([s for s in strings if "thread" in s.lower() and "%" not in s
                                  and any("一" <= ch <= "鿿" for ch in s)], [])


if __name__ == "__main__":
    unittest.main()
