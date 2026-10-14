"""守的底線：每個指令模組（`commands/*.py`）與 `music` 套件都 import 得起來。

bot 啟動時逐個 `load_extension`，哪個模組在 import 階段炸掉（名字在 import 之前就被用到、少了依賴），
那組指令就整個消失，其他功能照常——log 裡只有一行 ERROR，很容易沒人發現。啟動 gate 跑的單元測試
只 import 各自需要的模組，守不到這件事；這裡把全部實際 import 一遍。
"""
import importlib
import os
import pkgutil
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)


def _modules(package: str) -> list[str]:
    pkg = importlib.import_module(package)
    return [f"{package}.{m.name}" for m in pkgutil.iter_modules(pkg.__path__) if not m.name.startswith("_")]


class CogModulesImportTests(unittest.TestCase):
    def test_every_command_module_imports(self):
        failures = {}
        for name in _modules("commands") + _modules("music"):
            try:
                importlib.import_module(name)
            except Exception as exc:   # noqa: BLE001 - 要的就是任何一種炸法
                failures[name] = f"{type(exc).__name__}: {exc}"
        self.assertEqual({}, failures)


if __name__ == "__main__":
    unittest.main()
