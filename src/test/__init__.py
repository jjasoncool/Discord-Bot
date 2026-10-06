"""單元測試套件。

import 這個套件時就進入「測試模式」：所有 log 檔（含 prompt 除錯檔）改寫到
`/logs/test_run.log`（見 `utils.logger_config.TEST_LOG_ENV`），啟動 gate 與手動跑測試
都不會把假紀錄混進正式 log。整合測試（`test/integration/it_*.py`）也在這個套件底下，一併適用。
"""
import os
import sys

os.environ.setdefault("APP_TEST_LOG_FILE", "test_run.log")

# 跑單元測試時（啟動 gate、手動 unittest），GPU 閘門的跨行程鎖檔換成這次專用的暫存檔：
# 用正式的 /tmp/lemonade_gpu.lock 會跟執行中的 bot 互相排隊。手動抽查腳本（test/integration/it_*.py）
# 不經過 unittest，照樣用正式的鎖檔跟 bot 一起排隊（使用者 10-06：「我希望跑判斷還是要排隊的」）
if "unittest" in sys.modules:
    import atexit
    import shutil
    import tempfile

    _lock_dir = tempfile.mkdtemp(prefix="gpu_lock_")
    atexit.register(shutil.rmtree, _lock_dir, True)
    os.environ.setdefault("LEMONADE_GPU_LOCK_PATH", os.path.join(_lock_dir, "gpu.lock"))

_SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

# 一定要在設定環境變數之後才 import：import 當下就會套用 settings/logging.json
from utils.logger_config import configure_logging  # noqa: E402

configure_logging()
