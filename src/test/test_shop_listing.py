"""商品與品項的模型、解析、畫面（services.community.shop_listing）。

守的底線：
  1. 價格欄：一個數字＝全額；「定金/尾款」（全形斜線也可以）＝定金＋尾款。類型與價格要對得上：
     定金＋尾款要填兩個數字、一次付清只能填一個；預購與定金一定要有截止時間，要寫年份、要在未來、不能太遠。
     批次新增不用選類型：價格有斜線就是定金＋尾款，填了截止就是預購；錯的行標出行號；一行寫出去再讀回來不走樣。
     截止欄鎖住時（有人下單、已截止）沿用原本的時間，不再檢查是不是過了。
  2. 資料庫的列轉成模型：已下單份數照算好的值、被刪的品項不出現、開始收尾款就算停收定金。
  3. 下單檢查：已下架、品項被刪、已售完、預購截止、停收定金、數量超過剩餘都擋下並說明理由。
  4. 下單明細：現在要付（定金、全額）與到貨後再付（尾款）分開算；價格指紋在金額或份數改了就變、順序不影響。
  5. 顯示：給群友看的字是「品項」「供應方」「需求方」；狀態寫出定金、尾款、截止、預計交貨、延期次數；
     不能買的價格劃掉、接灰底標籤；選單的 value 只有品項編號；全部都不能買時選單寫出原因。
"""

import os
import sys
import unittest
from datetime import datetime, timedelta

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
    decode_items,
    encode_items,
    listing_from_rows,
    order_summary,
    parse_batch,
    parse_draft,
    parse_price,
    price_signature,
    quote_order,
    render_embed,
    select_options,
    unavailable_text,
)
from services.market_db import ListingRow, VariantRow  # noqa: E402
from sys_settings.time_settings import APP_TZ  # noqa: E402

NOW = datetime(2026, 10, 3, 20, 0, tzinfo=APP_TZ)
LATER = NOW + timedelta(days=10)


def doll(key=1, **overrides):
    fields = dict(key=key, name=f"玩偶{key}", price=500, kind="deposit", balance=1300, limit=10, taken=2, cutoff=LATER)
    fields.update(overrides)
    return Variant(**fields)


def listing(*variants, **overrides):
    fields = dict(thread_id=500, owner_id=21, unit="NT$", title="座姿玩偶", description="預計二月到貨",
                  variants=tuple(variants), delivery="physical")
    fields.update(overrides)
    return Listing(**fields)


class PriceAndDraftTests(unittest.TestCase):

    def test_price_field(self):
        self.assertEqual(parse_price("500", "玩偶"), (500, None))
        self.assertEqual(parse_price(" 500/1300 ", "玩偶"), (500, 1300))
        self.assertEqual(parse_price("500／1300", "玩偶"), (500, 1300))
        for bad in ("", "abc", "500/", "1/2/3", "-5", "1000000000"):
            with self.subTest(bad), self.assertRaises(ShopError):
                parse_price(bad, "玩偶")

    def test_kind_and_price_must_agree(self):
        cutoff = "2026/10/20 23:59"
        deposit = parse_draft("玩偶A", "500/1300", "10", cutoff, kind="deposit", now=NOW)
        self.assertEqual((deposit.kind, deposit.price, deposit.balance, deposit.limit), ("deposit", 500, 1300, 10))
        cases = {
            "定金只填一個數字": dict(price="500", kind="deposit", cutoff=cutoff),
            "一次付清卻寫定金/尾款": dict(price="500/1300", kind="instant", cutoff=""),
            "定金沒填截止": dict(price="500/1300", kind="deposit", cutoff=""),
            "預購沒填截止": dict(price="500", kind="preorder", cutoff=""),
            "立即購買填了截止": dict(price="500", kind="instant", cutoff=cutoff),
            "截止已經過了": dict(price="500", kind="preorder", cutoff="2026/10/01"),
            "截止太遠（年份打錯）": dict(price="500", kind="preorder", cutoff="2062/10/01"),
        }
        for label, case in cases.items():
            with self.subTest(label), self.assertRaises(ShopError):
                parse_draft("玩偶A", case["price"], "", case["cutoff"], kind=case["kind"], now=NOW)

    def test_locked_cutoff_keeps_the_original(self):
        past = NOW - timedelta(days=1)
        draft = parse_draft("玩偶A", "600/1300", "3", "2026/01/01", kind="deposit", now=NOW, min_limit=0,
                            keep_cutoff=past)
        self.assertEqual(draft.cutoff, past)

    def test_batch_infers_the_kind(self):
        drafts, errors = parse_batch(
            "60 月相｜30｜10｜\n\n玩偶A｜500/1300｜10｜2026/11/30\n6480 月相 | 3000 | 3 | 2026/10/20 23:59\n"
            "壞掉的行\n玩偶B｜500/1300｜｜", now=NOW)
        self.assertEqual([(d.name, d.kind) for d in drafts],
                         [("60 月相", "instant"), ("玩偶A", "deposit"), ("6480 月相", "preorder")])
        self.assertEqual(len(errors), 2)
        self.assertTrue(errors[0].startswith("第 5 行"))
        self.assertTrue(errors[1].startswith("第 6 行"))   # 定金沒填截止

    def test_batch_line_round_trip(self):
        cutoff = LATER.replace(hour=23, minute=59)
        for draft in (Draft("玩偶A", 500, 10, cutoff, "deposit", 1300), Draft("月相", 30, None, None),
                      Draft("6480 月相", 3000, 3, cutoff, "preorder")):
            with self.subTest(draft.name):
                (again,), errors = parse_batch(draft.line(), now=NOW)
                self.assertEqual(errors, [])
                self.assertEqual(again, draft)


class ModelTests(unittest.TestCase):

    def test_rows_become_the_model(self):
        row = ListingRow(id=500, owner_id=21, title="座姿玩偶", description="", unit="NT$", delivery="physical",
                         image="item_1.png", closed=False, next_key=4, created_at="", updated_at="")

        def variant_row(key, **overrides):
            fields = dict(listing_id=500, key=key, name=f"玩偶{key}", kind="deposit", price=500, balance=1300,
                          limit_qty=10, sold_before=0, cutoff=LATER.isoformat(), cutoff_done=False, expected_at=None,
                          delays=0, balance_started_at=None, deleted=False, created_at="", updated_at="")
            fields.update(overrides)
            return VariantRow(**fields)

        model = listing_from_rows(row, [variant_row(1, balance_started_at=NOW.isoformat()),
                                        variant_row(2, deleted=True), variant_row(3)], {1: 4, 3: 1})
        self.assertEqual([v.key for v in model.variants], [1, 3])
        self.assertEqual((model.variant(1).taken, model.variant(3).remaining), (4, 9))
        self.assertTrue(model.variant(1).balance_started)
        self.assertEqual(model.variant(1).unavailable_reason(NOW), "已停收定金")
        self.assertIsNone(model.variant(3).unavailable_reason(NOW))
        self.assertEqual(model.variant(3).cutoff, LATER)

    def test_status_text(self):
        unit = "NT$"
        self.assertEqual(doll().status(unit, NOW),
                         f"定金 NT$500｜尾款 NT$1,300｜收定金至 {LATER:%Y/%m/%d %H:%M}｜剩 8")
        delayed = doll(cutoff=NOW - timedelta(days=1), cutoff_done=True, expected_at=LATER, delays=1)
        self.assertTrue(delayed.status(unit, NOW).startswith("已停收定金｜"))
        self.assertIn(f"預計 {LATER:%Y/%m/%d} 到貨（已延期 1 次）", delayed.status(unit, NOW))
        rich = delayed.status(unit, NOW, rich=True)
        self.assertTrue(rich.startswith("~~") and rich.endswith("`已停收定金`"))
        preorder = doll(kind="preorder", balance=None, cutoff=NOW - timedelta(hours=1))
        self.assertTrue(preorder.status(unit, NOW).startswith("預購已截止｜NT$500"))
        sold_out = doll(kind="instant", balance=None, cutoff=None, limit=2, taken=2)
        self.assertEqual(sold_out.status(unit, NOW), "已售完｜NT$500｜立即購買")

    def test_listing_post(self):
        model = listing(doll(1), doll(2, taken=10), image="item_1.png")
        embed = render_embed(model, "觀星者小舖", NOW)
        self.assertEqual(embed.author.name, "供應方：觀星者小舖")
        self.assertEqual(embed.image.url, "attachment://item_1.png")
        self.assertIn("交付方式：實體", embed.footer.text)
        self.assertIn("品項", embed.footer.text)
        self.assertEqual([f.name for f in embed.fields], ["1. 玩偶1", "2. 玩偶2"])
        empty = render_embed(listing(), "觀星者小舖", NOW)
        self.assertIn("供應方還沒加入品項", empty.fields[0].value)
        self.assertEqual([o.value for o in select_options(model, NOW)], ["1", "2"])

    def test_menu_reason_when_nothing_can_be_bought(self):
        self.assertIsNone(unavailable_text(listing(doll(1), doll(2, taken=10)), NOW))
        self.assertEqual(unavailable_text(listing(doll(1, taken=10), doll(2, limit=3, taken=3)), NOW), "已售完")
        mixed = listing(doll(1, taken=10), doll(2, balance_started=True))
        self.assertEqual(unavailable_text(mixed, NOW), "目前沒有可購買的品項")

    def test_wording(self):
        model = listing(doll(1))
        said = [render_embed(model, "x", NOW).footer.text, render_embed(listing(), "x", NOW).fields[0].value]
        with self.assertRaises(ShopError) as caught:
            quote_order(listing(doll(1)), {9: 1}, NOW)
        said.append(str(caught.exception))
        for text in said:
            self.assertNotIn("上架者", text)
            self.assertNotIn("買家", text)
            self.assertNotIn("商品已經被", text)


class OrderTests(unittest.TestCase):

    def test_order_checks(self):
        model = listing(doll(1), doll(2, limit=3, taken=3), doll(3, balance_started=True),
                        doll(4, kind="preorder", balance=None, cutoff=NOW - timedelta(minutes=1)))
        self.assertEqual([(v.key, q) for v, q in quote_order(model, {1: 8}, NOW)], [(1, 8)])
        cases = {
            "沒選": ({}, "沒有選任何品項"),
            "被刪": ({9: 1}, "被供應方刪除"),
            "售完": ({2: 1}, "已售完"),
            "停收定金": ({3: 1}, "已停收定金"),
            "預購截止": ({4: 1}, "預購已截止"),
            "超過剩餘": ({1: 9}, "只剩 8 個"),
        }
        for label, (picks, reason) in cases.items():
            with self.subTest(label), self.assertRaises(ShopError) as caught:
                quote_order(model, picks, NOW)
            self.assertIn(reason, str(caught.exception))
        with self.assertRaises(ShopError):
            quote_order(replace(model, closed=True), {1: 1}, NOW)

    def test_now_and_later_totals(self):
        lines = [(doll(1), 2), (doll(2, price=600, balance=1200), 1)]
        rows, now_total, later_total = order_summary(lines, "NT$")
        self.assertEqual((now_total, later_total), (500 * 2 + 600, 1300 * 2 + 1200))
        self.assertIn("定金 NT$500，尾款 NT$1,300", rows[0])
        preorder_rows, now_total, later_total = order_summary(
            [(doll(5, kind="preorder", balance=None), 3)], "NT$")
        self.assertEqual((now_total, later_total), (1500, 0))
        self.assertIn("預購", preorder_rows[0])

    def test_price_signature(self):
        base = [(doll(1), 2), (doll(2), 1)]
        self.assertEqual(price_signature(base), price_signature(list(reversed(base))))
        for changed in ([(doll(1, price=501), 2), (doll(2), 1)], [(doll(1, balance=1400), 2), (doll(2), 1)],
                        [(doll(1), 3), (doll(2), 1)]):
            self.assertNotEqual(price_signature(base), price_signature(changed))

    def test_items_round_trip(self):
        self.assertEqual(decode_items(encode_items({1: 2, 25: 999})), {1: 2, 25: 999})
        self.assertEqual(decode_items("1x2,壞掉"), {})


if __name__ == "__main__":
    unittest.main()
