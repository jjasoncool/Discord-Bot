"""交易進度（services.community.trade_progress）：品項走到哪一步、等誰、能不能按、等待提醒何時發。

守的底線：
  1. 定金＋尾款：待付定金 →（已收到定金）已付定金・等貨 →（開始收尾款）待付尾款 →（已收到尾款）待交付／待寄出。
     一次付清：待付款 →（已收到款項）待交付／待寄出。數位：已交付；實體：已寄出 →（需求方）已收到。
  2. 加購的份數另外從頭走；取消還回的份數不算。
  3. 錢沒收齊不能交付（單一品項或剩下的一起交付都一樣），理由列出哪些品項還沒收齊；沒東西可確認時說清楚。
  4. 需求方按了「我已付」就改等供應方；同一筆不能一直按；之後又請了一筆尾款，就可以再按（講的是新的那筆）。
     重複按已交付的品項，理由說「已經交付了」，不是說錢沒收齊。
  5. 等待提醒：沒付錢 3、10、17 天各一次、之後不再催；按了我已付 3 天後提醒供應方一次；錢收齊沒交付 3 天後一次
     （預購從可以交貨那一刻算）；數位商品需求方按「還沒領收」3 天後提醒供應方一次（被加購作廢的不算）；
     實體寄出 7 天起每 3 天；等貨中不提醒；22:00～10:00 順延到 10:00；同一個對話一天最多一則。
  6. 交易進度卡過期的判斷：只看會改變卡片的事件，提醒、通知不算。
"""

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC_DIR = HERE.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from services.community import trade_progress as tp  # noqa: E402
from sys_settings.time_settings import APP_TZ  # noqa: E402

T0 = datetime(2026, 11, 10, 12, 0, tzinfo=APP_TZ)


def item(key, qty, kind="deposit", name=None, price=500, balance=1300, returned=0):
    return dict(variant_key=key, name=name or f"玩偶{key}", kind=kind, qty=qty, unit_price=price,
                unit_balance=balance if kind == "deposit" else None, returned=returned)


class Log:
    """照時間順序累積事件（id 遞增）。"""

    def __init__(self):
        self.events = []

    def add(self, kind, at, items=None, amount=None, reference=None):
        self.events.append(dict(id=len(self.events) + 1, kind=kind, created_at=at.isoformat(),
                                items=items or {}, amount=amount, reference=reference))
        return self


class StateTests(unittest.TestCase):

    def test_deposit_line_walks_every_state(self):
        items = [item(1, 1)]
        log = Log().add(tp.ORDER, T0, {1: 1})
        states = []

        def state(delivery="digital"):
            return tp.progress(items, log.events, delivery=delivery).line(1).state(delivery)

        states.append(state())
        log.add(tp.DEPOSIT_RECEIVED, T0, {1: 1}, 500)
        states.append(state())
        log.add(tp.BALANCE_REQUESTED, T0, {1: 1}, 1300)
        states.append(state())
        log.add(tp.BALANCE_RECEIVED, T0, {1: 1}, 1300)
        states += [state(), state("physical")]
        log.add(tp.DELIVERED, T0, {1: 1})
        states.append(state())
        self.assertEqual(states, [tp.AWAIT_DEPOSIT, tp.WAIT_GOODS, tp.AWAIT_BALANCE, tp.AWAIT_DELIVERY,
                                  tp.AWAIT_SHIPPING, tp.DELIVERED_STATE])
        prog = tp.progress(items, log.events, delivery="digital")
        self.assertTrue(prog.money_done and prog.all_delivered)
        self.assertEqual(prog.paid, {"deposit": 500, "balance": 1300, "full": 0})

    def test_full_payment_and_physical_receipt(self):
        items = [item(3, 2, kind="instant", price=800)]
        log = Log().add(tp.ORDER, T0, {3: 2})
        prog = tp.progress(items, log.events, delivery="physical")
        self.assertEqual(prog.line(3).state("physical"), tp.AWAIT_PAYMENT)
        self.assertEqual(prog.line(3).waiting_for("physical"), tp.REQUESTER)
        log.add(tp.FULL_RECEIVED, T0, {3: 2}, 1600).add(tp.SHIPPED, T0, {3: 2})
        prog = tp.progress(items, log.events, delivery="physical")
        self.assertEqual(prog.line(3).state("physical"), tp.SHIPPED_STATE)
        self.assertEqual(prog.line(3).waiting_for("physical"), tp.REQUESTER)
        self.assertTrue(prog.all_delivered and not prog.all_received)
        log.add(tp.RECEIVED, T0, {3: 2})
        self.assertTrue(tp.progress(items, log.events, delivery="physical").all_received)

    def test_add_on_restarts_only_the_new_portion_and_returned_items_do_not_count(self):
        items = [item(1, 1), item(1, 1), item(2, 1, returned=1), item(3, 3, kind="instant", returned=1)]
        log = Log().add(tp.ORDER, T0, {1: 1, 2: 1}).add(tp.DEPOSIT_RECEIVED, T0, {1: 1}, 500)
        log.add(tp.ORDER, T0 + timedelta(hours=1), {1: 1})
        prog = tp.progress(items, log.events, delivery="digital")
        self.assertEqual([(line.key, line.qty) for line in prog.lines], [(1, 2), (3, 2)])
        self.assertEqual(prog.line(1).state("digital"), tp.AWAIT_DEPOSIT)
        self.assertEqual(tp.pending_for(prog, tp.CONFIRM_DEPOSIT), {1: 1})

    def test_a_new_balance_request_resets_the_paid_claim(self):
        items = [item(1, 1), item(2, 1)]
        log = Log().add(tp.ORDER, T0, {1: 1, 2: 1}).add(tp.DEPOSIT_RECEIVED, T0, {1: 1, 2: 1}, 1000)
        log.add(tp.BALANCE_REQUESTED, T0, {1: 1}, 1300).add(tp.PAID_CLAIM, T0, reference="balance")
        self.assertIsNotNone(tp.allowed(tp.progress(items, log.events, delivery="digital"), tp.CLAIM_PAID))
        log.add(tp.BALANCE_REQUESTED, T0 + timedelta(days=30), {2: 1}, 1300)   # 玩偶2 晚一個月到貨
        prog = tp.progress(items, log.events, delivery="digital")
        self.assertIsNone(tp.allowed(prog, tp.CLAIM_PAID))
        self.assertEqual(tp.pending_for(prog, tp.CLAIM_PAID), {2: 1})          # 只剩玩偶2 要按
        self.assertEqual(prog.line(2).waiting_for("digital"), tp.REQUESTER)
        self.assertEqual(prog.line(1).waiting_for("digital"), tp.SUPPLIER)     # 玩偶1 按過的「我已付」還算數
        log.add(tp.BALANCE_RECEIVED, T0 + timedelta(days=31), {1: 1}, 1300)
        self.assertFalse(tp.progress(items, log.events, delivery="digital").line(1).claimed)

    def test_paid_deposit_claim_survives_an_early_balance_request(self):
        # 需求方說付了定金、供應方還沒確認就開始收尾款：說過的「已付定金」照樣算數，不會被催
        items = [item(1, 1)]
        log = Log().add(tp.ORDER, T0, {1: 1}).add(tp.PAID_CLAIM, T0 + timedelta(days=1), {1: 1}, reference="deposit")
        log.add(tp.BALANCE_REQUESTED, T0 + timedelta(days=20), {1: 1}, 1300)
        prog = tp.progress(items, log.events, delivery="digital")
        self.assertTrue(prog.line(1).claimed)
        self.assertEqual(prog.line(1).waiting_for("digital"), tp.SUPPLIER)

    def test_a_claim_on_an_old_card_does_not_cover_a_later_add_on(self):
        items = [item(1, 1), item(1, 1)]
        log = Log().add(tp.ORDER, T0, {1: 1}).add(tp.ORDER, T0, {1: 1})   # 卡片 v1 之後又加購（事件 2）
        log.events.append(dict(id=3, kind=tp.PAID_CLAIM, created_at=T0.isoformat(), items={1: 1}, amount=500,
                               reference="deposit", source="v1"))
        prog = tp.progress(items, log.events, delivery="digital")
        self.assertFalse(prog.line(1).claimed)   # 加購那份還要再按一次
        self.assertEqual(tp.pending_for(prog, tp.CLAIM_PAID), {1: 2})

    def test_repeated_delivery_says_it_was_delivered(self):
        items = [item(1, 1, kind="instant"), item(2, 1)]
        log = Log().add(tp.ORDER, T0, {1: 1, 2: 1}).add(tp.FULL_RECEIVED, T0, {1: 1}, 500)
        log.add(tp.DELIVERED, T0, {1: 1})
        prog = tp.progress(items, log.events, delivery="digital")
        self.assertEqual(tp.allowed(prog, tp.DELIVER, 1), "這些品項都已經交付了。")
        self.assertIn("錢沒收齊", tp.allowed(prog, tp.DELIVER, 2))

    def test_card_staleness_ignores_notices(self):
        log = Log().add(tp.ORDER, T0, {1: 1}).add(tp.REMINDER, T0, reference="pay:1:1:1")
        log.add(tp.PAID_CLAIM, T0, reference="full").add(tp.CUTOFF_NOTICE, T0, reference="1")
        self.assertEqual(tp.latest_state_event(log.events), 1)
        self.assertIsNone(tp.latest_state_event([]))

    def test_paid_claim_switches_to_waiting_for_the_supplier(self):
        items = [item(1, 1)]
        log = Log().add(tp.ORDER, T0, {1: 1})
        self.assertIsNone(tp.allowed(tp.progress(items, log.events, delivery="digital"), tp.CLAIM_PAID))
        log.add(tp.PAID_CLAIM, T0, reference="deposit")
        prog = tp.progress(items, log.events, delivery="digital")
        self.assertEqual(prog.line(1).waiting_for("digital"), tp.SUPPLIER)
        self.assertIn("已經通知過", tp.allowed(prog, tp.CLAIM_PAID))
        log.add(tp.DEPOSIT_RECEIVED, T0, {1: 1}, 500).add(tp.BALANCE_REQUESTED, T0, {1: 1}, 1300)
        prog = tp.progress(items, log.events, delivery="digital")
        self.assertEqual(prog.line(1).waiting_for("digital"), tp.REQUESTER)  # 新的一筆（尾款）又等需求方
        self.assertIsNone(tp.allowed(prog, tp.CLAIM_PAID))


class AllowedTests(unittest.TestCase):

    def test_no_delivery_before_the_money_is_in(self):
        items = [item(1, 1), item(2, 1)]
        log = Log().add(tp.ORDER, T0, {1: 1, 2: 1}).add(tp.DEPOSIT_RECEIVED, T0, {1: 1, 2: 1}, 1000)
        log.add(tp.BALANCE_REQUESTED, T0, {1: 1}, 1300).add(tp.BALANCE_RECEIVED, T0, {1: 1}, 1300)
        prog = tp.progress(items, log.events, delivery="digital")
        self.assertIsNone(tp.allowed(prog, tp.DELIVER, 1))
        reason = tp.allowed(prog, tp.DELIVER, 2)
        self.assertIn("玩偶2", reason)
        self.assertIn(tp.WAIT_GOODS, reason)
        rest = tp.allowed(prog, tp.DELIVER_REST)
        self.assertIn("玩偶2", rest)
        self.assertNotIn("玩偶1", rest)

    def test_nothing_to_confirm_says_so(self):
        prog = tp.progress([item(1, 1, kind="instant")], Log().add(tp.ORDER, T0, {1: 1}).events, delivery="digital")
        self.assertIn("沒有待收的定金", tp.allowed(prog, tp.CONFIRM_DEPOSIT))
        self.assertIsNone(tp.allowed(prog, tp.CONFIRM_FULL))
        self.assertIn("沒有這個品項", tp.allowed(prog, tp.DELIVER, 9))

    def test_ship_and_receive_follow_the_delivery_kind(self):
        items = [item(1, 1, kind="instant")]
        log = Log().add(tp.ORDER, T0, {1: 1}).add(tp.FULL_RECEIVED, T0, {1: 1}, 500)
        digital = tp.progress(items, log.events, delivery="digital")
        physical = tp.progress(items, log.events, delivery="physical")
        self.assertEqual(tp.pending_for(digital, tp.SHIP), {})
        self.assertEqual(tp.pending_for(physical, tp.SHIP), {1: 1})
        self.assertEqual(tp.pending_for(physical, tp.DELIVER_REST), {1: 1})
        self.assertIsNotNone(tp.allowed(physical, tp.RECEIVE, 1))
        log.add(tp.SHIPPED, T0, {1: 1})
        self.assertIsNone(tp.allowed(tp.progress(items, log.events, delivery="physical"), tp.RECEIVE, 1))
        self.assertEqual(tp.actor_of(tp.RECEIVE), tp.REQUESTER)
        self.assertEqual(tp.actor_of(tp.SHIP), tp.SUPPLIER)


class ReminderTests(unittest.TestCase):

    def remind(self, items, log, now, delivery="digital", ready_at=None):
        prog = tp.progress(items, log.events, delivery=delivery)
        return tp.due_reminders(prog, log.events, now=now, ready_at=ready_at)

    def send(self, log, reminders, at):
        for reminder in reminders:
            log.add(tp.REMINDER, at, reference=reminder.reference)

    def test_unpaid_three_times_then_stop(self):
        items, log = [item(1, 1)], Log().add(tp.ORDER, T0, {1: 1})
        due, wake = self.remind(items, log, T0 + timedelta(days=2))
        self.assertEqual((due, wake), ([], T0 + timedelta(days=3)))
        sent_days = []
        for day in range(3, 30):
            now = T0 + timedelta(days=day)
            due, _ = self.remind(items, log, now)
            if due:
                self.assertEqual([r.to for r in due], [tp.REQUESTER])
                sent_days.append(day)
                self.send(log, due, now)
        self.assertEqual(sent_days, [3, 10, 17])

    def test_claim_reminds_the_supplier_once(self):
        items = [item(1, 1)]
        log = Log().add(tp.ORDER, T0, {1: 1}).add(tp.PAID_CLAIM, T0 + timedelta(days=1), reference="deposit")
        due, wake = self.remind(items, log, T0 + timedelta(days=2))
        self.assertEqual((due, wake), ([], T0 + timedelta(days=4)))
        due, _ = self.remind(items, log, T0 + timedelta(days=4))
        self.assertEqual([(r.to, r.reason) for r in due], [(tp.SUPPLIER, "confirm")])
        self.send(log, due, T0 + timedelta(days=4))
        self.assertEqual(self.remind(items, log, T0 + timedelta(days=20)), ([], None))

    def test_waiting_for_goods_is_quiet(self):
        items = [item(1, 1)]
        log = Log().add(tp.ORDER, T0, {1: 1}).add(tp.DEPOSIT_RECEIVED, T0, {1: 1}, 500)
        self.assertEqual(self.remind(items, log, T0 + timedelta(days=90)), ([], None))

    def test_delivery_reminder_counts_from_when_preorder_can_ship(self):
        items = [item(4, 1, kind="preorder")]
        log = Log().add(tp.ORDER, T0, {4: 1}).add(tp.FULL_RECEIVED, T0, {4: 1}, 500)
        cutoff = T0 + timedelta(days=20)
        due, wake = self.remind(items, log, T0 + timedelta(days=5), ready_at={4: cutoff})
        self.assertEqual((due, wake), ([], cutoff + timedelta(days=3)))
        due, _ = self.remind(items, log, cutoff + timedelta(days=3), ready_at={4: cutoff})
        self.assertEqual([(r.to, r.reason) for r in due], [(tp.SUPPLIER, "deliver")])

    def test_deposit_and_balance_reminders_are_counted_separately(self):
        # 定金一直沒確認、貨就到了：催定金用掉的次數，不會吃掉之後催尾款的次數
        items, log = [item(1, 1)], Log().add(tp.ORDER, T0, {1: 1})
        for day in (3, 10, 17):
            due, _ = self.remind(items, log, T0 + timedelta(days=day))
            self.send(log, due, T0 + timedelta(days=day))
        log.add(tp.BALANCE_REQUESTED, T0 + timedelta(days=20), {1: 1}, 1300)
        self.assertEqual(self.remind(items, log, T0 + timedelta(days=25))[0], [])   # 還在等定金：已經催滿 3 次
        log.add(tp.DEPOSIT_RECEIVED, T0 + timedelta(days=26), {1: 1}, 500)
        sent = []
        for day in range(26, 60):
            now = T0 + timedelta(days=day, hours=1)
            due, _ = self.remind(items, log, now)
            if due:
                sent.append(day)
                self.send(log, due, now)
        # 定金第 26 天才確認：尾款從那天才輪到需求方付，照 3、10、17 天後催（不是一確認就連催）
        self.assertEqual(sent, [29, 36, 43])

    def test_new_delivery_after_not_received_waits_for_a_new_notice(self):
        items = [item(1, 1, kind="instant"), item(2, 1, kind="instant")]
        log = Log().add(tp.ORDER, T0, {1: 1}).add(tp.FULL_RECEIVED, T0, {1: 1}, 500).add(tp.DELIVERED, T0, {1: 1})
        log.add(tp.RECEIPT_REQUESTED, T0).add(tp.RECEIPT_HELD, T0, reference="held")
        self.assertIsNotNone(tp.held_by_requester(log.events))
        log.add(tp.DELIVERED, T0 + timedelta(days=1), {1: 1})
        self.assertIsNone(tp.held_by_requester(log.events))   # 補交了：不再算是在等供應方

    def test_not_received_reminds_the_supplier_once(self):
        items = [item(1, 1, kind="instant")]
        log = Log().add(tp.ORDER, T0, {1: 1}).add(tp.FULL_RECEIVED, T0, {1: 1}, 500).add(tp.DELIVERED, T0, {1: 1})
        log.add(tp.RECEIPT_REQUESTED, T0).add(tp.RECEIPT_HELD, T0 + timedelta(hours=1), reference="held")
        due, wake = self.remind(items, log, T0 + timedelta(days=2))
        self.assertEqual((due, wake), ([], T0 + timedelta(days=3, hours=1)))
        due, _ = self.remind(items, log, T0 + timedelta(days=3, hours=2))
        self.assertEqual([(r.to, r.reason) for r in due], [(tp.SUPPLIER, "redeliver")])
        self.send(log, due, T0 + timedelta(days=3, hours=2))
        self.assertEqual(self.remind(items, log, T0 + timedelta(days=30)), ([], None))
        superseded = Log().add(tp.ORDER, T0, {1: 1}).add(tp.FULL_RECEIVED, T0, {1: 1}, 500).add(tp.DELIVERED, T0, {1: 1})
        superseded.add(tp.RECEIPT_REQUESTED, T0).add(tp.RECEIPT_HELD, T0, reference="superseded")
        self.assertEqual(self.remind(items, superseded, T0 + timedelta(days=5))[0], [])

    def test_shipped_reminds_both_every_three_days_after_a_week(self):
        items = [item(1, 1, kind="instant")]
        log = Log().add(tp.ORDER, T0, {1: 1}).add(tp.FULL_RECEIVED, T0, {1: 1}, 500).add(tp.SHIPPED, T0, {1: 1})
        days = []
        for day in range(1, 20):
            now = T0 + timedelta(days=day)
            due, _ = self.remind(items, log, now, delivery="physical")
            if due:
                self.assertEqual([r.to for r in due], [tp.BOTH])
                days.append(day)
                self.send(log, due, now)
        self.assertEqual(days, [7, 10, 13, 16, 19])

    def test_overdue_reminders_still_wait_for_the_morning(self):
        # 白天到期、停機到晚上才重啟補做：一樣等到早上才發
        items, log = [item(1, 1)], Log().add(tp.ORDER, T0, {1: 1})   # 第 3 天中午到期
        late = datetime(2026, 11, 13, 23, 30, tzinfo=APP_TZ)
        due, wake = self.remind(items, log, late)
        self.assertEqual(due, [])
        self.assertEqual(wake, datetime(2026, 11, 14, 10, 0, tzinfo=APP_TZ))
        self.assertEqual(len(self.remind(items, log, wake)[0]), 1)

    def test_a_late_reminder_pushes_the_next_one_back(self):
        # 停機好幾天：重啟後那一次照發，下一次照實際發的時間再隔一段，不會接連幾天每天催；寄出天數寫實際的
        items = [item(1, 1, kind="instant")]
        log = Log().add(tp.ORDER, T0, {1: 1}).add(tp.FULL_RECEIVED, T0, {1: 1}, 500).add(tp.SHIPPED, T0, {1: 1})
        back = T0 + timedelta(days=16)
        due, _ = self.remind(items, log, back, delivery="physical")
        self.assertEqual([(r.reason, r.number, r.days) for r in due], [("receive", 1, 16)])
        self.send(log, due, back)
        due, wake = self.remind(items, log, back + timedelta(days=1), delivery="physical")
        self.assertEqual((due, wake), ([], back + tp.SHIPPED_REPEAT))

        items, log = [item(1, 1)], Log().add(tp.ORDER, T0, {1: 1})
        back = T0 + timedelta(days=9)   # 第一次催款原本排在第 3 天
        due, _ = self.remind(items, log, back)
        self.send(log, due, back)
        due, wake = self.remind(items, log, back + timedelta(days=1))
        self.assertEqual((due, wake), ([], back + tp.REPEAT_PAYMENT))

    def test_quiet_hours_and_one_a_day(self):
        night = datetime(2026, 11, 10, 23, 0, tzinfo=APP_TZ)
        items = [item(1, 1), item(2, 1, kind="instant")]
        log = Log().add(tp.ORDER, night - timedelta(days=3), {1: 1, 2: 1})
        due, wake = self.remind(items, log, night)
        self.assertEqual(due, [])
        self.assertEqual(wake, datetime(2026, 11, 11, 10, 0, tzinfo=APP_TZ))
        due, _ = self.remind(items, log, wake)
        self.assertEqual(sorted(r.key for r in due), [1, 2])  # 同時到期的併成一則
        self.send(log, due, wake)
        # 另一件事當天也到期（停機補做）：等到隔天早上
        log.add(tp.PAID_CLAIM, wake - timedelta(days=4), reference="full")
        due, wake2 = self.remind(items, log, wake + timedelta(hours=3))
        self.assertEqual(due, [])
        self.assertEqual(wake2, datetime(2026, 11, 12, 10, 0, tzinfo=APP_TZ))


if __name__ == "__main__":
    unittest.main()
