"""批次執行：挑人、輪替、到點收手（hermetic，不碰 DB 也不碰 LLM）。

每條測試都對應一個實測得出的設計決定：

  - 活躍使用者約 4.4 分／人、符合門檻 67 人 → 全跑要 4.5 小時，會跑到早上
  - production 的 14 天／10 則門檻把 12 個安靜使用者排除在外，而那是 agent
    唯一明確贏的族群（7 天 1 則、90 天 91 則那個案例）
  - 單人失敗不影響其他人：失敗率是調參的唯一依據，中斷整批等於失去資料

執行：
    cd src && python -m unittest test.test_persona_agent_batch -v
"""

import asyncio
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from llm.persona_agent import batch  # noqa: E402
from sys_settings.llm_settings import PersonaAgentSettings  # noqa: E402

GUILD = 1


class SelectionTests(unittest.TestCase):
    def _with_rows(self, rows):
        cur = mock.MagicMock()
        cur.fetchall.return_value = rows
        ctx = mock.MagicMock()
        ctx.__enter__.return_value = cur
        return mock.patch(
            "sys_settings.llm_settings.LLMServiceSettings.pgvector_cursor",
            return_value=ctx,
        ), cur

    def test_sample_mode_takes_only_sample_size(self):
        patcher, _ = self._with_rows([(f"u{i}",) for i in range(20)])
        with patcher:
            got = batch.select_targets(GUILD, PersonaAgentSettings(sample_size=6))
        self.assertEqual(len(got), 6)

    def test_all_mode_takes_everyone(self):
        patcher, _ = self._with_rows([(f"u{i}",) for i in range(20)])
        with patcher:
            got = batch.select_targets(GUILD, PersonaAgentSettings(mode="all"))
        self.assertEqual(len(got), 20, "改設定就能全跑，不必改程式")

    def test_threshold_is_wider_than_production(self):
        """production 是 14 天 10 則；門檻外的人正是 agent 唯一明確贏的族群。"""
        s = PersonaAgentSettings()
        self.assertGreater(s.min_messages_days, 14)
        self.assertLess(s.min_messages, 10)

    def test_never_run_users_come_first(self):
        """SQL 用 NULLS FIRST：沒跑過的人自動排前面，不必手動維護清單。"""
        patcher, cur = self._with_rows([])
        with patcher:
            batch.select_targets(GUILD, PersonaAgentSettings())
        sql = cur.execute.call_args[0][0]
        self.assertIn("NULLS FIRST", sql)
        self.assertIn("LEFT JOIN", sql)

    def test_selection_failure_returns_empty_not_raise(self):
        with mock.patch(
            "sys_settings.llm_settings.LLMServiceSettings.pgvector_cursor",
            side_effect=RuntimeError("db down"),
        ):
            self.assertEqual(batch.select_targets(GUILD, PersonaAgentSettings()), [])


class RunBatchTests(unittest.TestCase):
    def _run(self, settings, targets, side_effect, past_deadline=False):
        # `_past_deadline` 讀的是真實時鐘。不釘死的話這些測試只有在
        # `deadline_hour`（07:00）之前才會過——白天跑 gate 一定紅，
        # 而重啟大多發生在白天，等於擋住自己的部署。
        with mock.patch.object(batch, "select_targets", return_value=targets), \
             mock.patch.object(batch, "_past_deadline", return_value=past_deadline), \
             mock.patch.object(batch.persona_agent, "run_and_persist",
                               side_effect=side_effect) as ran:
            stats = asyncio.run(
                batch.run_batch(guild_id=GUILD, model="m", settings=settings)
            )
        return stats, ran

    def test_disabled_does_nothing(self):
        stats, ran = self._run(PersonaAgentSettings(enabled=False), ["a"], None)
        self.assertEqual(stats, {"skipped": 1})
        ran.assert_not_called()

    def test_one_failure_does_not_stop_the_rest(self):
        calls = []

        async def side(**kw):
            calls.append(kw["user_id"])
            if kw["user_id"] == "b":
                raise RuntimeError("boom")
            return mock.MagicMock(status="ok"), mock.MagicMock(skip_reason=None)

        stats, _ = self._run(
            PersonaAgentSettings(enabled=True), ["a", "b", "c"], side
        )
        self.assertEqual(calls, ["a", "b", "c"], "b 炸掉之後仍要繼續跑 c")
        self.assertEqual(stats["ok"], 2)
        self.assertEqual(stats["failed"], 1)

    def test_deadline_leaves_the_rest_for_tomorrow(self):
        async def side(**kw):
            return mock.MagicMock(status="ok"), mock.MagicMock(skip_reason=None)

        stats, ran = self._run(
            PersonaAgentSettings(enabled=True), ["a", "b", "c"], side,
            past_deadline=True,
        )
        ran.assert_not_called()
        self.assertEqual(stats["unrun"], 3, "沒跑到的要記下來，明晚才排得到前面")

    def test_whitelist_contains_only_the_current_user(self):
        seen = []

        async def side(**kw):
            seen.append(sorted(kw["ctx"].allowed_ids))
            return mock.MagicMock(status="ok"), mock.MagicMock(skip_reason=None)

        self._run(PersonaAgentSettings(enabled=True), ["a", "b"], side)
        self.assertEqual(seen, [["a"], ["b"]],
                         "工具層的白名單一次只能有當前這一人")


if __name__ == "__main__":
    unittest.main()
