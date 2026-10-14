"""專案根目錄、log 掛載點與其下固定目錄的唯一來源：程式要找 settings、settings/runtime、prompts、scraper 資料、log 與備份時都問這裡。

架構定位：基礎層（`sys_settings`），不依賴專案內其他模組。上層：所有要讀專案內檔案的模組
（pydantic 設定的預設路徑、字典、prompt、交易價格檔、scraper 資料庫位置）。下層：只有 `os`、`pathlib`。

介面：
- `APP_ROOT`：根目錄。環境變數 `APP_ROOT` 有設就用它，沒設就是容器裡的掛載點 `/app`。
- `LOGS_DIR`：log、prompt 除錯檔與備份放的地方。環境變數 `LOGS_DIR` 有設就用它，沒設就是容器裡的掛載點 `/logs`。
- `SETTINGS_DIR`（你手改的設定，進版控）、`RUNTIME_DIR`（bot 執行時寫的資料：透過 Discord 設的值＋它自己的紀錄，整個資料夾
  不進版控）、`PROMPTS_DIR`、
  `SYS_SETTINGS_DIR`、`SCRAPER_DIR`、`TELEGRAM_SCRAPER_DIR`、`STATIC_DIR`：根目錄下的固定子目錄（`Path`）。
- `settings_file(name)`、`runtime_path(name)`、`prompt_file(name)`：`settings/`、`settings/runtime/`、`settings/prompts/` 下某個檔的
  路徑字串，給型別是 `str` 的設定欄位當預設值。

規則：
- 程式裡不再寫死 `"/app/..."`、`"/logs/..."`（守衛 `test_shared_conventions` 擋）；要路徑就從這裡拿。
- 在容器裡不用設環境變數，行為和寫死 `/app`、`/logs` 完全相同；在主機跑腳本或測試時設 `APP_ROOT=./src`、`LOGS_DIR=./logs` 即可。
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
#: bot 執行時寫的資料：透過 Discord 設的值（提醒的身分組與面板文字、點名開關、監控關鍵字、價格）加上它自己的紀錄
#: （面板訊息 id、thread id、放到哪首）。人手不改、整個資料夾不進版控
RUNTIME_DIR = SETTINGS_DIR / "runtime"
PROMPTS_DIR = SETTINGS_DIR / "prompts"
SYS_SETTINGS_DIR = APP_ROOT / "sys_settings"
SCRAPER_DIR = APP_ROOT / "scraper"
TELEGRAM_SCRAPER_DIR = APP_ROOT / "telegram_scraper"
STATIC_DIR = APP_ROOT / "static"

#: log、prompt 除錯檔、設定與字典的備份；compose 把 ./logs 掛到這裡
LOGS_DIR = Path(os.environ.get("LOGS_DIR") or "/logs")


def settings_file(name: str) -> str:
    """`settings/<name>` 的路徑字串。"""
    return str(SETTINGS_DIR / name)


def runtime_path(name: str) -> str:
    """`settings/runtime/<name>` 的路徑字串。"""
    return str(RUNTIME_DIR / name)


def prompt_file(name: str) -> str:
    """`settings/prompts/<name>` 的路徯字串。"""
    return str(PROMPTS_DIR / name)
