"""全程式共用的 StateDB 連線（services.state_db.get_shared_state_db）。

守的底線：
  1. 整個 bot 只開一個 StateDB 連線：多次、同時呼叫 get_shared_state_db 都拿到同一個實例，只連線一次。
  2. 這個取得函式只定義在 services/state_db.py。轉發、活動、社群 ID 查詢、週期提醒都向它拿，
     不必為了拿資料庫去 import 轉發（relay）的模組；在別處另寫一份，就會變成兩個連線、兩份狀態。

實際資料庫不會被打開：StateDB.connect 以假物件取代。
"""

import ast
import asyncio
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
SRC_DIR = HERE.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from services import state_db  # noqa: E402


class SharedStateDBTests(unittest.TestCase):

    def setUp(self):
        self._saved = state_db._shared_state_db
        state_db._shared_state_db = None

    def tearDown(self):
        state_db._shared_state_db = self._saved

    def test_concurrent_calls_share_one_connection(self):
        async def scenario():
            with mock.patch.object(state_db.StateDB, "connect", new=mock.AsyncMock()) as connect:
                results = await asyncio.gather(*(state_db.get_shared_state_db() for _ in range(5)))
                again = await state_db.get_shared_state_db()
            return results, again, connect

        results, again, connect = asyncio.run(scenario())
        self.assertTrue(all(r is results[0] for r in results))
        self.assertIs(again, results[0])
        connect.assert_awaited_once()

    def test_accessor_is_defined_only_in_state_db(self):
        defined_in = []
        for dirpath, dirnames, filenames in os.walk(SRC_DIR):
            rel = Path(dirpath).relative_to(SRC_DIR)
            if rel.parts[:1] and rel.parts[0] in ("scraper", "telegram_scraper"):
                dirnames[:] = []
                continue
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for name in filenames:
                if not name.endswith(".py"):
                    continue
                path = Path(dirpath) / name
                for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "get_shared_state_db":
                        defined_in.append(path.relative_to(SRC_DIR).as_posix())
        self.assertEqual(defined_in, ["services/state_db.py"])


if __name__ == "__main__":
    unittest.main()
