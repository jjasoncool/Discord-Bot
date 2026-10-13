"""config.json 的讀寫（utils/utils.py 的 ChannelConfig）。

守的底線（使用者 10-06 SW-Q4）：
- 手改的內容不會被 Discord 存設定蓋掉：寫入前重讀磁碟上最新的內容，只改這次的那一項
- 手改後下一次讀就生效（看檔案修改時間，不是等 5 分鐘快取過期）
- 檔案壞掉（JSON 寫錯）時：寫入拒絕、檔案不動；讀取沿用上次的正確內容，綁頻道的功能不會一起停
- 讀到的是複本，呼叫端改了不會影響別人
- 每天第一次改寫前備份
- 點名「新增身份組」只加選的那幾個，不動其他設定

執行：
    cd src && python -m unittest test.test_channel_config -v
"""
import asyncio
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from utils.utils import ChannelConfig, ConfigWriteError
from utils import hot_files  # noqa: E402


class ConfigTestBase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.path = self.tmp / "config.json"
        self.backup = self.tmp / "backup"
        self.write({"a_channel_id": 1, "role_mapping": {"Trader": [5]}})
        patcher = mock.patch.object(ChannelConfig, "BACKUP_DIR", str(self.backup))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(hot_files.forget, str(self.path))   # 快取在 hot_files

    def write(self, data, raw=None):
        self.path.write_text(raw if raw is not None else json.dumps(data, indent=2), encoding="utf-8")
        # 確保修改時間一定不同（同一瞬間連改兩次時，檔案系統的時間解析度不一定分得出來）
        st = self.path.stat()
        os.utime(self.path, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))

    def on_disk(self):
        return json.loads(self.path.read_text(encoding="utf-8"))

    def load(self):
        return ChannelConfig.load_config(str(self.path), caller="test")


class ConfigTests(ConfigTestBase):
    async def test_hand_edit_survives_discord_save(self):
        self.load()                                          # 快取裡是舊的
        self.write({"a_channel_id": 1, "role_mapping": {"Trader": [5]}, "hand_edited": True})
        await ChannelConfig.update_config(lambda c: c.__setitem__("b_channel_id", 2), str(self.path), caller="test")
        disk = self.on_disk()
        self.assertTrue(disk["hand_edited"], "手改的不能被舊快取蓋掉")
        self.assertEqual(disk["b_channel_id"], 2)
        self.assertEqual(disk["role_mapping"], {"Trader": [5]})

    async def test_hand_edit_is_read_right_away(self):
        self.assertEqual(self.load()["a_channel_id"], 1)
        self.write({"a_channel_id": 9})
        self.assertEqual(self.load()["a_channel_id"], 9, "不用等 5 分鐘")

    async def test_broken_file_is_not_written_and_reads_keep_last_good(self):
        self.load()
        self.write(None, raw='{"a_channel_id": 1,,}')
        with self.assertRaises(ConfigWriteError):
            await ChannelConfig.update_config(lambda c: c.__setitem__("b", 2), str(self.path), caller="test")
        self.assertEqual(self.path.read_text(encoding="utf-8"), '{"a_channel_id": 1,,}', "壞掉的檔案不能被覆寫")
        with self.assertLogs("utils.utils", "ERROR"):
            self.assertEqual(self.load()["a_channel_id"], 1, "沿用上次讀到的正確內容")

    async def test_write_is_visible_even_if_mtime_did_not_move(self):
        # 同一瞬間改兩次、檔案系統的修改時間解析度不夠時，mtime 可能沒變；寫完一定要丟掉快取，不然讀到的是舊的
        before = os.stat(self.path).st_mtime_ns
        self.load()
        await ChannelConfig.update_config(lambda c: c.__setitem__("b_channel_id", 2), str(self.path), caller="test")
        os.utime(self.path, ns=(before, before))
        self.assertEqual(self.load()["b_channel_id"], 2, "剛寫進去的內容要讀得到")

    async def test_reads_are_copies(self):
        self.load()["role_mapping"]["Trader"].append(99)
        self.assertEqual(self.load()["role_mapping"]["Trader"], [5])

    async def test_backup_before_first_write_of_the_day(self):
        await ChannelConfig.update_config(lambda c: c.__setitem__("b", 2), str(self.path), caller="test")
        await ChannelConfig.update_config(lambda c: c.__setitem__("b", 3), str(self.path), caller="test")
        [backup] = list(self.backup.glob("config_*.json"))
        self.assertNotIn("b", json.loads(backup.read_text(encoding="utf-8")), "備份的是改寫前的內容")

    async def test_concurrent_writes_keep_both(self):
        await asyncio.gather(*(
            ChannelConfig.update_config(lambda c, n=n: c.__setitem__(f"k{n}", n), str(self.path), caller="test")
            for n in range(5)
        ))
        disk = self.on_disk()
        self.assertEqual([disk.get(f"k{n}") for n in range(5)], list(range(5)))

    async def test_missing_file_is_not_created_with_only_one_key(self):
        self.path.unlink()
        with self.assertRaisesRegex(ConfigWriteError, "不存在"):
            await ChannelConfig.update_config(lambda c: c.__setitem__("b", 2), str(self.path), caller="test")
        self.assertFalse(self.path.exists(), "檔案不見時寫回去，整份設定就只剩這一項")

    async def test_write_error_is_reported_and_file_untouched(self):
        before = self.path.read_text(encoding="utf-8")
        with mock.patch("utils.utils.replace_text", side_effect=PermissionError("備份目錄不能寫")):
            with self.assertRaises(ConfigWriteError):
                await ChannelConfig.update_config(lambda c: c.__setitem__("b", 2), str(self.path), caller="test")
        self.assertEqual(self.path.read_text(encoding="utf-8"), before)

    async def test_missing_file_reads_empty(self):
        self.path.unlink()
        hot_files.forget(str(self.path))
        self.assertEqual(self.load(), {})


class RollCallRoleTests(ConfigTestBase):
    async def test_add_role_ids_only_adds_the_new_ones(self):
        from commands import rollcall_commands
        self.write({"rollcall_target_role_ids": [1], "other": "keep"})
        interaction = SimpleNamespace(response=SimpleNamespace(edit_message=mock.AsyncMock()))
        with mock.patch.object(rollcall_commands, "CONFIG_FILE", str(self.path)):
            ok = await rollcall_commands._add_role_ids(interaction, "rollcall_target_role_ids", [1, 2, 3])
        self.assertTrue(ok)
        self.assertEqual(self.on_disk(), {"rollcall_target_role_ids": [1, 2, 3], "other": "keep"})
        interaction.response.edit_message.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
