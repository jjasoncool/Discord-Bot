"""log 設定（utils/logger_config.py ＋ settings/logging.json）。

守的底線：
- 設定檔載得起來，而且 root 有畫面與主 log 檔兩個輸出（模組 logger 才有地方去）
- 類別 logger（article_monitor、llm_anomaly）不往 root 傳，不會重複寫進主 log
- 會大量寫 log 的第三方套件（httpx 每次請求一筆）被壓到 WARNING
- 測試模式下所有檔案輸出都改寫到測試 log，不碰正式 log
- 設定檔裡寫的 logger 名稱都對得到東西：模組改名或打錯字時，設定不會悄悄失效

執行：
    cd src && python -m unittest test.test_logger_config -v
"""

import importlib.util
import json
import logging
import os
import sys
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from utils.logger_config import (  # noqa: E402
    ARTICLE_MONITOR_LOGGER,
    CONFIG_PATH,
    LLM_ANOMALY_LOGGER,
    TEST_LOG_ENV,
    build_config,
)

RAW = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


class BuildConfigTests(unittest.TestCase):
    def file_handlers(self, config):
        return {name: h for name, h in config["handlers"].items() if "filename" in h}

    def test_files_go_under_log_dir(self):
        config = build_config(RAW, log_dir="/somewhere")
        for name, handler in self.file_handlers(config).items():
            self.assertTrue(handler["filename"].startswith("/somewhere/"), name)
        self.assertIn("filename", RAW["handlers"]["main_file"])
        self.assertFalse(RAW["handlers"]["main_file"]["filename"].startswith("/"), "原始設定不可被改動")

    def test_test_mode_redirects_every_file(self):
        config = build_config(RAW, log_dir="/logs", test_log_name="test_run.log")
        files = {h["filename"] for h in self.file_handlers(config).values()}
        self.assertEqual(files, {"/logs/test_run.log"})

    def test_level_override(self):
        self.assertEqual(build_config(RAW, level="DEBUG")["root"]["level"], "DEBUG")


class SettingsFileTests(unittest.TestCase):
    def test_root_has_console_and_main_file(self):
        self.assertEqual(set(RAW["root"]["handlers"]), {"console", "main_file"})

    def test_category_loggers_do_not_propagate(self):
        for name in (ARTICLE_MONITOR_LOGGER, LLM_ANOMALY_LOGGER):
            self.assertIs(RAW["loggers"][name]["propagate"], False, name)

    def test_logger_names_exist(self):
        """每個名稱必須是：類別 logger、專案裡存在的模組／資料夾、或裝得起來的第三方套件。

        logger 名稱就是模組路徑，模組搬家或改名後，json 裡針對舊名稱的設定不會報錯、只會
        默默不再套用——這條就是為了讓它變紅。
        """
        missing = []
        for name in RAW["loggers"]:
            if name in (ARTICLE_MONITOR_LOGGER, LLM_ANOMALY_LOGGER):
                continue
            project_path = Path(SRC_DIR, *name.split("."))
            if Path(SRC_DIR, name.split(".")[0]).is_dir():
                if not (project_path.is_dir() or project_path.with_suffix(".py").is_file()):
                    missing.append(name)
            elif importlib.util.find_spec(name) is None:
                missing.append(name)
        self.assertEqual(missing, [], "settings/logging.json 裡這些 logger 名稱對不到任何模組")

    def test_noisy_libraries_are_quiet(self):
        for name in ("httpx", "httpcore"):
            self.assertEqual(RAW["loggers"][name]["level"], "WARNING", name)


class AppliedConfigTests(unittest.TestCase):
    """test/__init__.py 已經在測試模式下套用過真正的設定檔：驗證它真的生效。"""

    def test_every_file_handler_writes_test_log(self):
        test_log = os.environ[TEST_LOG_ENV]
        for logger in (logging.getLogger(), logging.getLogger(ARTICLE_MONITOR_LOGGER),
                       logging.getLogger(LLM_ANOMALY_LOGGER)):
            files = [h.baseFilename for h in logger.handlers if isinstance(h, logging.FileHandler)]
            self.assertTrue(files, f"{logger.name} 沒有檔案輸出")
            for path in files:
                self.assertTrue(path.endswith(test_log), f"{logger.name} 寫到 {path}")

    def test_module_logger_reaches_root(self):
        with self.assertLogs(level="INFO") as caught:
            logging.getLogger("services.some_module").info("hello")
        self.assertIn("hello", caught.output[0])


if __name__ == "__main__":
    unittest.main()
