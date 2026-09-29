"""單元測試套件。

import 這個套件時就進入「測試模式」：所有 log 檔（含 prompt 除錯檔）改寫到
`/logs/test_run.log`（見 `utils.logger_config.TEST_LOG_ENV`），啟動 gate 與手動跑測試
都不會把假紀錄混進正式 log。整合測試（`test/integration/it_*.py`）也在這個套件底下，一併適用。
"""
import os
import sys

os.environ.setdefault("APP_TEST_LOG_FILE", "test_run.log")

_SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

# 一定要在設定環境變數之後才 import：import 當下就會套用 settings/logging.json
from utils.logger_config import configure_logging  # noqa: E402

configure_logging()
