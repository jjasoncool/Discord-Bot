"""商品貼文的資料（services.community.shop_listing）。

守的底線：
  1. 品項資料寫進下拉選項的 value 再讀回來不會走樣（不限量、預購截止、已截止都一樣）；
     商品貼文上真的 Discord 元件讀得回同一篇商品：上架者、幣別（含冒號也行）、品項、是否下架。
  2. 批次新增一行一項「名稱｜價格｜數量｜預購截止」：全形半形分隔都可以、空行略過；
     截止時間一定要寫年份（使用者 2026-10-03）、要在未來；錯的行標出行號。
  3. 下單檢查：已下架、品項被刪、已售完、預購截止、數量超過剩餘都擋下並說明理由；
     下單預留、取消還回（不會變成負的）。
  4. 訂單紀錄（停用按鈕的 custom_id）讀得回同一筆，一次 5 種也不超過 Discord 的 100 字上限。
  5. 顯示：商品圖用 attachment://檔名 引用（改訊息時圖才不會不見）；狀態寫出價格、剩餘、截止時間；
     全部品項都不能買時，購買選單寫出原因（已售完、預購已截止，兩種都有就說沒有可購買的品項）。
     不能買的（已售完、預購已截止）：商品貼文上價格與類型劃掉、後面接標籤；選單說明文字沒有樣式，
     狀態放最前面（TR-Q38）。
"""

import asyncio
import os
import sys
import unittest
from datetime import datetime
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from dataclasses import replace  # noqa: E402

from services.community.shop_listing import (  # noqa: E402
    Draft,
    Listing,
    ShopError,
    Variant,
    apply_order,
    listing_from_message,
    order_custom_id,
    order_summary,
    order_total,
    orders_on,
    parse_batch,
    parse_draft,
    quote_order,
    release_order,
    render_embed,
    select_options,
    unavailable_text,
)
from sys_settings.time_settings import APP_TZ  # noqa: E402

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=APP_TZ)
CUTOFF = datetime(2026, 10, 20, 23, 59, tzinfo=APP_TZ)

INSTANT = Variant(1, "60 月相", 30, limit=10, taken=8)
PREORDER = Variant(2, "6480 月相", 3000, limit=3, taken=1, cutoff=CUTOFF)
UNLIMITED = Variant(3, "寰宇電台", 20)
SOLD_OUT = Variant(4, "一條龍", 40, limit=2, taken=2)
CLOSED = Variant(5, "舊預購", 100, cutoff=CUTOFF, closed=True)
LISTING = Listing(thread_id=500, owner_id=21, unit="NT$", title="月相代儲", description="說明",
                  image="item_1.png", variants=(INSTANT, PREORDER, UNLIMITED, SOLD_OUT, CLOSED))


def _message_from_view(view, embed, channel_id):
    # 從 Discord 讀回來的訊息元件沒有 DynamicItem 那層包裝，選項與停用狀態直接在元件上
    children = [getattr(child, "item", child) for child in view.children]
    return SimpleNamespace(channel=SimpleNamespace(id=channel_id),
                           components=[SimpleNamespace(children=children)], embeds=[embed])


class VariantTests(unittest.TestCase):

    def test_encode_round_trip(self):
        for variant in LISTING.variants:
            with self.subTest(variant.name):
                self.assertEqual(Variant.decode(variant.encode(), variant.name), variant)

    def test_status_text(self):
        self.assertEqual(INSTANT.status("NT$", NOW), "NT$30｜立即購買｜剩 2")
        self.assertEqual(UNLIMITED.status("NT$", NOW), "NT$20｜立即購買｜不限量")
        self.assertEqual(PREORDER.status("NT$", NOW), "NT$3,000｜預購（2026/10/20 23:59 截止）｜剩 2")  # 千分位
        self.assertEqual(INSTANT.status("NT$", NOW, rich=True), "NT$30｜立即購買｜剩 2")  # 能買的兩邊一樣
        # 選單說明文字：狀態放最前面
        self.assertEqual(SOLD_OUT.status("NT$", NOW), "已售完｜NT$40｜立即購買")
        self.assertEqual(CLOSED.status("NT$", NOW), "預購已截止｜NT$100｜預購（2026/10/20 23:59 截止）")
        after = datetime(2026, 10, 21, 0, 0, tzinfo=APP_TZ)
        self.assertTrue(PREORDER.status("NT$", after).startswith("預購已截止｜"))
        # 商品貼文：劃掉價格與類型，後面接灰底標籤
        self.assertEqual(SOLD_OUT.status("NT$", NOW, rich=True), "~~NT$40｜立即購買~~ `已售完`")
        self.assertEqual(CLOSED.status("NT$", NOW, rich=True),
                         "~~NT$100｜預購（2026/10/20 23:59 截止）~~ `預購已截止`")

    def test_unit_with_markdown_characters_does_not_break_the_strike(self):
        self.assertEqual(SOLD_OUT.status("*PY~幣", NOW, rich=True), r"~~\*PY\~幣40｜立即購買~~ `已售完`")


class ListingOnMessageTests(unittest.TestCase):

    def _round_trip(self, listing):
        from commands.shop_commands import DiscordShopViews
        from sys_settings.shop_settings import ShopSettings

        async def build():
            view = DiscordShopViews(ShopSettings()).listing(listing, NOW)
            return _message_from_view(view, render_embed(listing, "上架者", NOW), listing.thread_id)

        return listing_from_message(asyncio.run(build()))

    def assert_round_trip(self, listing):
        # 管理按鈕記的是「下一個品項編號」，讀回來的 key_seq 就是它
        self.assertEqual(self._round_trip(listing), replace(listing, key_seq=listing.next_key()))

    def test_components_round_trip(self):
        listing = Listing(thread_id=500, owner_id=21, unit="PY:幣", title="月相代儲", description="說明",
                          image="item_1.png", variants=LISTING.variants)
        self.assert_round_trip(listing)

    def test_closed_listing_and_no_variants(self):
        self.assert_round_trip(Listing(thread_id=501, owner_id=21, unit="NT$", title="t", description="", closed=True))

    def test_variant_numbers_are_never_reused(self):
        listing = Listing(thread_id=1, owner_id=21, unit="NT$", title="t", description="")
        listing = listing.add(Draft("a", 1, None, None)).add(Draft("b", 1, None, None))
        listing = listing.without_variant(2).add(Draft("c", 1, None, None))
        self.assertEqual([v.key for v in listing.variants], [1, 3])
        self.assertEqual(self._round_trip(listing).next_key(), 4)

    def test_message_that_is_not_a_listing(self):
        message = SimpleNamespace(channel=SimpleNamespace(id=1), components=[], embeds=[])
        self.assertIsNone(listing_from_message(message))

    def test_image_from_cdn_url(self):
        embed = render_embed(LISTING, "上架者", NOW)
        embed.set_image(url="https://cdn.discordapp.com/attachments/500/9/item_1.png?ex=abc&is=def")
        message = SimpleNamespace(channel=SimpleNamespace(id=500), embeds=[embed], components=[
            SimpleNamespace(children=[SimpleNamespace(custom_id="shop:manage:21:6:NT%24", disabled=False)])])
        self.assertEqual(listing_from_message(message).image, "item_1.png")


class BatchTests(unittest.TestCase):

    def test_valid_lines(self):
        drafts, errors = parse_batch("60 月相｜30｜10｜\n\n6480 月相|3000|3|2026/10/20 23:59\n寰宇電台｜20", now=NOW)

        self.assertEqual(errors, [])
        self.assertEqual([(d.name, d.price, d.limit, d.cutoff) for d in drafts], [
            ("60 月相", 30, 10, None), ("6480 月相", 3000, 3, CUTOFF), ("寰宇電台", 20, None, None)])

    def test_errors_are_marked_by_line(self):
        text = "a｜abc\nb｜10｜0\nc｜10｜｜10/20 23:59\nd｜10｜｜2026/10/01 10:00\ne\nok｜5"
        drafts, errors = parse_batch(text, now=NOW)

        self.assertEqual([d.name for d in drafts], ["ok"])
        self.assertEqual([e.split("：")[0] for e in errors], [f"第 {n} 行" for n in range(1, 6)])
        self.assertIn("2026/10/20 23:59", errors[2])  # 沒寫年份：提示要寫成含年份的格式
        self.assertIn("已經過了", errors[3])

    def test_digit_limits_match_the_single_variant_form(self):
        _, errors = parse_batch("a｜1234567890\nb｜1｜1234567", now=NOW)
        self.assertEqual(len(errors), 2)

    def test_preview_line_round_trip(self):
        drafts, _ = parse_batch("6480 月相｜3000｜3｜2026/10/20 23:59\n寰宇電台｜20｜｜", now=NOW)
        again, errors = parse_batch("\n".join(d.line() for d in drafts), now=NOW)
        self.assertEqual((again, errors), (drafts, []))

    def test_editing_allows_zero_remaining(self):
        with self.assertRaises(ShopError):
            parse_draft("a", "1", "0", "", preorder=False, now=NOW)  # 新增至少 1
        self.assertEqual(parse_draft("a", "1", "0", "", preorder=False, now=NOW, min_limit=0).limit, 0)

    def test_single_variant_type(self):
        with self.assertRaises(ShopError):
            parse_draft("預購品", "10", "", "", preorder=True, now=NOW)  # 預購一定要填截止
        # 新增時選立即購買卻填了截止：多半是忘了把類型改成預購，擋下來說清楚（TR-Q42）
        with self.assertRaises(ShopError) as caught:
            parse_draft("現貨", "10", "", "2026/10/20 23:59", preorder=False, now=NOW)
        self.assertIn("類型選「預購」", str(caught.exception))
        # 編輯時從預購改成立即購買，截止欄還留著預填的時間：忽略它
        instant = parse_draft("現貨", "10", "", "2026/10/20 23:59", preorder=False, now=NOW, allow_unused_cutoff=True)
        self.assertIsNone(instant.cutoff)

    def test_cutoff_spellings_and_limits(self):
        def cutoff(text):
            return parse_draft("預購品", "10", "", text, preorder=True, now=NOW).cutoff
        expected = datetime(2026, 10, 20, 23, 59, tzinfo=APP_TZ)
        self.assertEqual(cutoff("２０２６／１０／２０　２３：５９"), expected)  # 全形自動轉
        self.assertEqual(cutoff("2026/10/20"), expected)  # 只寫日期＝當天 23:59
        self.assertEqual(cutoff("2031/10/01 12:00"), datetime(2031, 10, 1, 12, 0, tzinfo=APP_TZ))  # 五年內可以
        with self.assertRaises(ShopError) as caught:
            cutoff("2062/10/20 23:59")  # 年份打錯
        self.assertIn("5 年內", str(caught.exception))
        with self.assertRaises(ShopError) as caught:
            cutoff("10/20 23:59")
        self.assertIn("2026/10/20 23:59", str(caught.exception))  # 讀不懂就給範例


class OrderTests(unittest.TestCase):

    def test_quote_rejections(self):
        from dataclasses import replace
        after_cutoff = datetime(2026, 10, 21, 0, 0, tzinfo=APP_TZ)
        cases = {
            "已經下架": (replace(LISTING, closed=True), {1: 1}, NOW),
            "刪除": (LISTING, {99: 1}, NOW),
            "已售完": (LISTING, {4: 1}, NOW),
            "預購已截止": (LISTING, {2: 1}, after_cutoff),
            "只剩 2 個": (LISTING, {1: 3}, NOW),
        }
        for reason, (listing, picks, now) in cases.items():
            with self.subTest(reason), self.assertRaises(ShopError) as caught:
                quote_order(listing, picks, now)
            self.assertIn(reason, str(caught.exception))

    def test_reserve_and_release(self):
        reserved = apply_order(LISTING, {1: 2, 3: 5})
        self.assertEqual((reserved.variant(1).taken, reserved.variant(3).taken), (10, 5))
        released = release_order(reserved, {1: 99, 3: 5, 42: 1})  # 還太多不會變負的、被刪的品項略過
        self.assertEqual((released.variant(1).taken, released.variant(3).taken), (0, 0))

    def test_order_record_round_trip(self):
        picks = {21: 999, 22: 999, 23: 999, 24: 999, 25: 999}
        custom_id = order_custom_id(1555659153110859850, picks)
        self.assertLessEqual(len(custom_id), 100)
        message = SimpleNamespace(components=[SimpleNamespace(children=[SimpleNamespace(custom_id=custom_id)])])
        self.assertEqual(list(orders_on(message)), [(1555659153110859850, picks)])

    def test_order_total_on_the_button(self):
        def message(label):
            button = SimpleNamespace(custom_id=order_custom_id(500, {1: 2}), label=label)
            return SimpleNamespace(components=[SimpleNamespace(children=[button])])
        self.assertEqual(order_total(message("總計 NT$80")), "總計 NT$80")
        self.assertIsNone(order_total(message("訂單紀錄")))  # 改版前的訂單：總計在文字裡，不重複帶

    def test_summary(self):
        rows, total = order_summary(quote_order(LISTING, {1: 2, 2: 1}, NOW), "NT$")
        self.assertEqual(total, 3060)
        self.assertIn("＝NT$3,000", rows[1])
        self.assertIn("60 月相 ×2", rows[0])
        self.assertIn("預購 2026/10/20 23:59 截止", rows[1])


class RenderTests(unittest.TestCase):

    def test_image_reference_and_fields(self):
        embed = render_embed(LISTING, "上架者", NOW)
        self.assertEqual(embed.image.url, "attachment://item_1.png")
        self.assertEqual(len(embed.fields), len(LISTING.variants))
        self.assertEqual(embed.author.name, "上架者：上架者")
        self.assertEqual(embed.fields[3].value, "~~NT$40｜立即購買~~ `已售完`")  # 商品貼文用有樣式的狀態

    def test_menu_text_when_nothing_can_be_bought(self):
        from dataclasses import replace
        self.assertIsNone(unavailable_text(LISTING, NOW))  # 還有能買的就不停用
        self.assertEqual(unavailable_text(replace(LISTING, variants=(SOLD_OUT,)), NOW), "已售完")
        self.assertEqual(unavailable_text(replace(LISTING, variants=(CLOSED,)), NOW), "預購已截止")
        self.assertEqual(unavailable_text(replace(LISTING, variants=(SOLD_OUT, CLOSED)), NOW), "目前沒有可購買的品項")

    def test_sold_out_options_lead_with_the_status(self):
        options = {o.label: o.description for o in select_options(LISTING, NOW)}
        self.assertTrue(options["一條龍"].startswith("已售完｜"))
        self.assertNotIn("~~", options["一條龍"])  # 選單不吃 Markdown

    def test_empty_and_closed(self):
        from dataclasses import replace
        empty = render_embed(replace(LISTING, variants=(), image=None), "上架者", NOW)
        self.assertIn("還沒加入商品", empty.fields[0].value)
        self.assertIn("已下架", render_embed(replace(LISTING, closed=True), "上架者", NOW).footer.text)


if __name__ == "__main__":
    unittest.main()
