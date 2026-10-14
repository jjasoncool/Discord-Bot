"""守的底線：專案根目錄只有一個來源（`sys_settings.paths`），容器裡沒設環境變數就是 /app、設了就跟著走。"""
import importlib
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)


def _load(env_root):
    env = {k: v for k, v in os.environ.items() if k != "APP_ROOT"}
    if env_root is not None:
        env["APP_ROOT"] = env_root
    with mock.patch.dict(os.environ, env, clear=True):
        import sys_settings.paths as paths
        return importlib.reload(paths)


class PathsTests(unittest.TestCase):
    def tearDown(self):
        import sys_settings.paths as paths
        importlib.reload(paths)   # 還原成目前環境的值，別影響其他測試

    def test_defaults_to_the_container_mount(self):
        paths = _load(None)
        self.assertEqual(Path("/app"), paths.APP_ROOT)
        self.assertEqual("/app/settings/prompts/x.txt", paths.prompt_file("x.txt"))
        self.assertEqual("/app/settings/x.json", paths.settings_file("x.json"))
        self.assertEqual(Path("/app/scraper"), paths.SCRAPER_DIR)

    def test_environment_variable_moves_everything(self):
        paths = _load("/srv/bot")
        self.assertEqual(Path("/srv/bot"), paths.APP_ROOT)
        self.assertEqual("/srv/bot/settings/prompts/x.txt", paths.prompt_file("x.txt"))
        self.assertEqual(Path("/srv/bot/static"), paths.STATIC_DIR)

    def test_empty_variable_counts_as_unset(self):
        self.assertEqual(Path("/app"), _load("").APP_ROOT)


if __name__ == "__main__":
    unittest.main()
