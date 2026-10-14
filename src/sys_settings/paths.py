"""專案根目錄與其下固定目錄的唯一來源：程式要找 settings、prompts、scraper 資料時都問這裡。

架構定位：基礎層（`sys_settings`），不依賴專案內其他模組。上層：所有要讀專案內檔案的模組
（pydantic 設定的預設路徑、字典、prompt、交易價格檔、scraper 資料庫位置）。下層：只有 `os`、`pathlib`。

介面：
- `APP_ROOT`：根目錄。環境變數 `APP_ROOT` 有設就用它，沒設就是容器裡的掛載點 `/app`。
- `SETTINGS_DIR`、`PROMPTS_DIR`、`SYS_SETTINGS_DIR`、`SCRAPER_DIR`、`TELEGRAM_SCRAPER_DIR`、`STATIC_DIR`：
  根目錄下的固定子目錄（`Path`）。
- `settings_file(name)`、`prompt_file(name)`：`settings/` 與 `settings/prompts/` 下某個檔的路徑字串，
  給型別是 `str` 的設定欄位當預設值。

規則：
- 程式裡不再寫死 `"/app/..."`（守衛 `test_shared_conventions` 擋）；要路徑就從這裡拿。
- 在容器裡不用設環境變數，行為和寫死 `/app` 完全相同；在主機跑腳本或測試時設 `APP_ROOT=./src` 即可。
- 爬蟲容器（`scraper/`、`telegram_scraper/`）各自掛子目錄到 `/app`，看不到這個模組，不在此規則內。

例外與決策：
- 用「環境變數、沒設就 /app」而不是從程式檔位置往上推：往上推的寫法搬檔就錯，相對路徑換啟動目錄就錯；
  容器裡不設變數就和原本寫死的 `/app` 完全相同，主機或 CI 設一個變數就能跑。
- `services/search/eval/evaluate.py` 的 `EVAL_DIR` 是它自己旁邊的報告資料夾，和專案根目錄無關，不走這裡。
"""
from __future__ import annotations

import os
from pathlib import Path

APP_ROOT = Path(os.environ.get("APP_ROOT") or "/app")
SETTINGS_DIR = APP_ROOT / "settings"
PROMPTS_DIR = SETTINGS_DIR / "prompts"
SYS_SETTINGS_DIR = APP_ROOT / "sys_settings"
SCRAPER_DIR = APP_ROOT / "scraper"
TELEGRAM_SCRAPER_DIR = APP_ROOT / "telegram_scraper"
STATIC_DIR = APP_ROOT / "static"


def settings_file(name: str) -> str:
    """`settings/<name>` 的路徑字串。"""
    return str(SETTINGS_DIR / name)


def prompt_file(name: str) -> str:
    """`settings/prompts/<name>` 的路徯字串。"""
    return str(PROMPTS_DIR / name)
