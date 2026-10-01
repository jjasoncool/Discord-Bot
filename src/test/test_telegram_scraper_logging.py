"""telegram-scraper 的 log 設定（telegram_scraper/log_config.py）。

守的底線：
- 入口設定後，scraper 的紀錄寫進 telegram_scraper.log（帶等級與模組名）；重建容器後 docker logs
  就沒了，查漏訊息要靠這個檔
- 失敗類訊息是 WARNING：runtime_config.json 壞掉時，log 檔看得到「沿用舊快照」的警告
- Telethon 的斷線重連訊息要留（查漏訊息用），逐檔下載的訊息不進檔
- log 檔開不了時 scraper 照樣啟動，只剩 console
- import scraper 模組不動全域 logging：bot 也會 import tg_config，不能洗掉 bot 的 log 設定

runner／handlers 需要 Telethon，bot 容器沒裝，不在這裡 import。

執行：
    cd src && python -m unittest test.test_telegram_scraper_logging -v
"""

import io
import logging
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# scraper 容器以 /app = src/telegram_scraper 執行、模組間用裸 import，這裡照樣把目錄加進路徑
HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
SCRAPER_DIR = os.path.join(SRC_DIR, "telegram_scraper")
if SCRAPER_DIR not in sys.path:
    sys.path.insert(0, SCRAPER_DIR)

from log_config import LOGGER_LEVELS, configure_logging  # noqa: E402
from tg_config import TelegramConfig, TelegramRuntimeConfigWatcher  # noqa: E402


class ConfiguredLoggingTestBase(unittest.TestCase):
    """configure_logging 會換掉 root 的 handler；每個測試結束後還原成測試套件的設定。"""

    def setUp(self):
        root = logging.getLogger()
        saved_handlers, saved_level = root.handlers[:], root.level
        saved_levels = {name: logging.getLogger(name).level for name in LOGGER_LEVELS}

        def restore():
            for handler in root.handlers:
                if handler not in saved_handlers:
                    handler.close()
            root.handlers[:] = saved_handlers
            root.setLevel(saved_level)
            for name, level in saved_levels.items():
                logging.getLogger(name).setLevel(level)

        self.addCleanup(restore)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.log_file = self.tmp / "telegram_scraper.log"
        # console handler 寫到這裡，不污染測試輸出
        self.console = io.StringIO()
        stdout = patch.object(sys, "stdout", self.console)
        stdout.start()
        self.addCleanup(stdout.stop)

    def logged(self) -> str:
        for handler in logging.getLogger().handlers:
            handler.flush()
        return self.log_file.read_text(encoding="utf-8") if self.log_file.exists() else ""


class LogFileTests(ConfiguredLoggingTestBase):
    def test_module_records_reach_log_file_and_console(self):
        configure_logging(str(self.log_file))
        logging.getLogger("runner").info("[CatchUp] Seele_WW_leak 補回漏收訊息")
        self.assertIn("[INFO] [runner] [CatchUp] Seele_WW_leak 補回漏收訊息", self.logged())
        self.assertIn("[CatchUp] Seele_WW_leak 補回漏收訊息", self.console.getvalue())

    def test_broken_runtime_config_is_a_warning(self):
        configure_logging(str(self.log_file))
        broken = self.tmp / "runtime_config.json"
        broken.write_text("{ 寫到一半", encoding="utf-8")
        TelegramRuntimeConfigWatcher(
            runtime_config_path=str(broken),
            fallback_config=TelegramConfig(api_id=1, api_hash="x", runtime_config_path=str(broken)),
        )
        warning = [line for line in self.logged().splitlines() if "沿用舊快照" in line]
        self.assertTrue(warning, "壞掉的 runtime_config.json 沒有留下紀錄")
        self.assertIn("[WARNING] [tg_config]", warning[0])

    def test_telethon_keeps_reconnects_but_not_per_file_downloads(self):
        configure_logging(str(self.log_file))
        logging.getLogger("telethon.network.mtprotosender").info("Closing current connection to begin reconnect...")
        logging.getLogger("telethon.client.downloads").info("Starting direct file download in chunks of 131072")
        logged = self.logged()
        self.assertIn("begin reconnect", logged)
        self.assertNotIn("Starting direct file download", logged)

    def test_unwritable_log_file_still_starts_with_console(self):
        blocker = self.tmp / "not_a_dir"
        blocker.write_text("", encoding="utf-8")
        configure_logging(str(blocker / "telegram_scraper.log"))  # 不能拋例外
        logging.getLogger("runner").info("[Telegram] 正在啟動 client...")
        console = self.console.getvalue()
        self.assertIn("無法寫入 log 檔", console)
        self.assertIn("[Telegram] 正在啟動 client...", console)


class ImportSideEffectTests(unittest.TestCase):
    def test_importing_scraper_modules_leaves_global_logging_alone(self):
        # 乾淨的直譯器裡 import：bot 的走法（套件路徑）與 scraper 容器的走法（裸 import）都檢查
        code = (
            "import logging, sys\n"
            f"sys.path[:0] = [{SRC_DIR!r}, {SCRAPER_DIR!r}]\n"
            "import telegram_scraper.tg_config, tg_config, db, log_config\n"
            "root = logging.getLogger()\n"
            "print(len(root.handlers), logging.getLevelName(root.level))\n"
        )
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.split(), ["0", "WARNING"])


if __name__ == "__main__":
    unittest.main()
