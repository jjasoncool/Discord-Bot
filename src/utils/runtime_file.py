"""程式自己寫的狀態 JSON（`settings/*_runtime.json`：面板訊息 id、點名狀態、音樂狀態…）的唯一讀寫機制。

架構定位：基礎層（`utils`）。上層：所有要記「我上次做到哪」的功能與介面層模組（面板置底 `panel_bump`、
點名、音樂、自介投稿、隔離 thread、週期提醒）。下層：`utils.hot_files`（讀，mtime 快取、壞檔沿用上次）、
`utils.safe_write`（寫，暫存檔換名、每天第一次改寫前備份到 `default_backup_dir()`，預設 `LOGS_DIR/runtime_backup`）。

介面：
- `load(path) -> dict`：讀整份；缺檔或壞檔回空 dict，回傳的是複本，改它不會寫回。
- `save(path, data)`：整份換掉（呼叫端自己持有完整狀態時用）。
- `update(path, **fields)`：重讀最新內容、只合併這幾個頂層欄位再寫回（多個地方各寫自己的欄位時用）。
- 寫入失敗拋例外，要不要吞由呼叫端決定（面板置底吞掉記 log，點名記 log）。

規則：
- `*_runtime.json` 只能經過這裡讀寫（守衛 `test_shared_conventions`）；格式與位置不變，所以沒有資料遷移。
- 人手改的設定檔（`article_runtime.json`、`llm_runtime_config.json`、字典、prompt）不是這裡的對象，
  它們走各自的熱讀檔。`music_runtime.json` 兩者都是（歌單人手改、面板 id 程式寫），讀寫一樣走這裡。

例外與決策：
- 留 JSON 檔、不搬進 SQLite（StateDB）：九個檔加起來不到 10 KB，問題是七套讀寫各自為政，不是容量；搬進資料庫要遷移資料、
  每個檔都要備份與確認，換到的只是少幾個檔。
- 備份放 `LOGS_DIR/runtime_backup`（和 config.json、字典的備份同一處），不放 `settings/`：備份是歷史紀錄，不該和程式一起掛載。
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path

from sys_settings.paths import LOGS_DIR
from utils.hot_files import read_parsed
from utils.safe_write import replace_text

#: 每天第一次改寫前備份到這裡；環境變數 `RUNTIME_BACKUP_DIR` 可換（測試套件換成暫存目錄）
DEFAULT_BACKUP_DIR = str(LOGS_DIR / "runtime_backup")


def default_backup_dir() -> str:
    return os.environ.get("RUNTIME_BACKUP_DIR") or DEFAULT_BACKUP_DIR


def _parse(raw: str):
    return json.loads(raw)   # 不是 dict 的內容由呼叫端當成空的


def load(path: str | Path) -> dict:
    data = read_parsed(path, parse=_parse, label="狀態檔", missing_ok=True)
    return copy.deepcopy(data) if isinstance(data, dict) else {}


def save(path: str | Path, data: dict, *, backup_dir: str | Path | None = None) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    replace_text(path, json.dumps(data, ensure_ascii=False, indent=2),
                 backup_dir=backup_dir if backup_dir is not None else default_backup_dir())


def update(path: str | Path, *, backup_dir: str | Path | None = None, **fields) -> None:
    data = load(path)
    data.update(fields)
    save(path, data, backup_dir=backup_dir)
