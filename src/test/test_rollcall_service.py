"""點名服務（services.community.rollcall_service）與指令層（commands.rollcall_commands）的分工。

守的底線：
  1. 點名訊息會 @ 被點名的人，並附上「我是活人」按鈕；按鈕由指令層交進來的建立函式產生，
     建立時帶入服務本身與被點名者的 id（按下後才對得回同一個人、同一個服務）。
  2. 服務層不 import 指令層：按鈕屬於 Discord 介面（commands/），服務層只負責做事。
     兩邊互相 import 會形成循環，以前只能靠函式內的延遲 import 撐著，有人把它移到檔案頂端就起不來。
  3. 指令層（Cog，唯一的建立點）建立服務時，確實把按鈕類別交進去；漏交的話點名訊息就沒有按鈕。
  4. 兩層接起來也要能用（真的 Cog＋真的按鈕）：點名訊息上有「我是活人」按鈕；被點名本人按下會交給
     服務層處理，別人按只會收到「不是你的點名」提示、不會替本人解除點名。

執行期狀態檔（settings/rollcall_runtime.json）一律以假物件取代，測試不讀也不寫它。
"""

import ast
import asyncio
import os
import sys
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from services.community import rollcall_service  # noqa: E402
from sys_settings.time_settings import APP_TZ  # noqa: E402


def _make_service(view_factory):
    with mock.patch.object(rollcall_service, "RollCallRuntime"):
        return rollcall_service.RollCallService(mock.MagicMock(), response_view_factory=view_factory)


class RollCallMessageTests(unittest.TestCase):

    def test_message_mentions_member_and_attaches_button_from_factory(self):
        view_factory = mock.MagicMock(name="view_factory")
        service = _make_service(view_factory)
        channel = SimpleNamespace(send=mock.AsyncMock(return_value="sent-message"))
        member = SimpleNamespace(id=123, mention="<@123>")
        deadline = datetime(2026, 10, 6, 12, 0, tzinfo=APP_TZ)

        result = asyncio.run(service._send_rollcall_message(channel, member, deadline))

        self.assertEqual(result, "sent-message")
        view_factory.assert_called_once_with(service, 123)
        channel.send.assert_awaited_once()
        kwargs = channel.send.await_args.kwargs
        self.assertEqual(kwargs["content"], "<@123>")
        self.assertIs(kwargs["view"], view_factory.return_value)
        self.assertIn("2026-10-06 12:00", kwargs["embed"].description)


class LayeringTests(unittest.TestCase):

    def test_service_does_not_import_command_layer(self):
        source = Path(rollcall_service.__file__).read_text(encoding="utf-8")
        imported = []
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imported += [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
        self.assertEqual([m for m in imported if m.split(".")[0] == "commands"], [])

    def test_cog_hands_the_button_class_to_the_service(self):
        from commands import rollcall_commands
        bot = mock.MagicMock()
        with mock.patch.object(rollcall_commands, "RollCallService") as service_cls:
            rollcall_commands.RollCallCommands(bot)
        service_cls.assert_called_once_with(
            bot, response_view_factory=rollcall_commands.RollCallResponseView
        )


class CogAndServiceTogetherTests(unittest.TestCase):
    """真的 Cog、真的按鈕，只把執行期狀態換成假物件：兩層之間的接縫不能只靠各自的單元測試。"""

    def test_button_on_rollcall_message_reaches_the_service_only_for_the_member(self):
        from commands import rollcall_commands

        async def scenario():
            with mock.patch.object(rollcall_service, "RollCallRuntime"):
                cog = rollcall_commands.RollCallCommands(mock.MagicMock())
            service = cog.service
            channel = SimpleNamespace(send=mock.AsyncMock(return_value=SimpleNamespace(id=999)))
            member = SimpleNamespace(id=123, mention="<@123>")
            await service._send_rollcall_message(channel, member, datetime(2026, 10, 6, 12, 0, tzinfo=APP_TZ))

            view = channel.send.await_args.kwargs["view"]
            buttons = [c for c in view.children if getattr(c, "custom_id", None) == "rollcall_response"]
            self.assertEqual(len(buttons), 1, "點名訊息上要有「我是活人」按鈕")
            button = buttons[0]

            service.runtime.pending = {"123": {"message_id": 999}}
            service.runtime.is_pending.return_value = True
            service.handle_response = mock.AsyncMock()

            def interaction_from(user_id):
                return SimpleNamespace(
                    user=SimpleNamespace(id=user_id),
                    message=SimpleNamespace(id=999),
                    response=SimpleNamespace(send_message=mock.AsyncMock()),
                    client=mock.MagicMock(),
                )

            stranger = interaction_from(456)
            await button.callback(stranger)
            service.handle_response.assert_not_awaited()
            stranger.response.send_message.assert_awaited_once()
            self.assertTrue(stranger.response.send_message.await_args.kwargs.get("ephemeral"))

            owner = interaction_from(123)
            await button.callback(owner)
            service.handle_response.assert_awaited_once_with(123, owner)

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
