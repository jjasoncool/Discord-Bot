"""啟動 gate：bot 啟動前只跑守衛、import 解析與設定載入這幾組測試，完整測試交給 `make test` 與 CI。

用法（compose 的 command）：`APP_STARTUP_GATE=1 python -m test.gate`；手動：`cd src && python -m test.gate`。

為什麼不跑全部：完整套件一千五百多項要 90～120 秒，每次重啟都付；而重啟時最該擋的是「起不來」那類問題
（import 斷了、設定檔壞了、分層或共用元件被繞過），功能邏輯的回歸由收工前的完整測試與 CI 負責。
新的守衛加進 GATE_MODULES；功能測試不要加，gate 才會一直很快。
"""
import sys
import time
import unittest

#: 啟動時要跑的測試模組：守衛（結構與慣例）、import 解析、設定載入
GATE_MODULES = [
    "test.test_import_resolution",       # 所有指向本專案模組的 import 都找得到對象
    "test.test_cog_modules_import",      # 每個指令模組與 music 套件 import 得起來
    "test.test_layering",                # 分層方向、技術／服務層不認 discord、跨容器 import
    "test.test_shared_conventions",      # 共用元件只有一份
    "test.test_error_boundaries",        # 內層接所有例外的地方只准減不准增
    "test.test_paths",                   # 專案根目錄與 log 掛載點
    "test.test_data_file_paths",         # 資料檔位置不隨程式檔搬動
    "test.test_switches",                # 功能開關檔載得起來、值合法
    "test.test_channel_config",          # config.json 讀寫
    "test.test_llm_runtime_config_loader",  # LLM runtime 設定載得起來
    "test.test_logger_config",           # logging.json 載得起來、logger 名稱都對得到東西
]


def main(argv=None) -> int:
    started = time.monotonic()
    suite = unittest.defaultTestLoader.loadTestsFromNames(GATE_MODULES)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    print(f"gate: {result.testsRun} tests in {time.monotonic() - started:.1f}s "
          f"({'OK' if result.wasSuccessful() else 'FAILED'})", file=sys.stderr)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
