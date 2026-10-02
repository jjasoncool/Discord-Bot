"""改寫使用者也會手改的文字檔：先寫暫存檔再換名，每天第一次改寫前備份一份。

**為什麼**：表情字典、貼圖字典由使用者維護，bot 也會自動補。直接 `open("w")` 寫到一半出錯
（磁碟滿、程序被殺）會留下半個檔；換名是原子的，檔案不是舊的就是新的。備份放 `/logs`，
誤寫時照 AGENTS.md「凍結 → 復原」從這裡拿回來（檔案有進 git 的也能用 git 還原）。
"""
from __future__ import annotations

import logging
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from sys_settings.time_settings import APP_TZ

logger = logging.getLogger(__name__)


def _backup_once_a_day(path: Path, backup_dir: Path, keep: int) -> None:
    if not path.exists():
        return
    backup_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now(APP_TZ).strftime("%Y-%m-%d")
    target = backup_dir / f"{path.stem}_{today}{path.suffix}"
    if target.exists():
        return
    shutil.copy2(path, target)
    logger.info("已備份 %s → %s", path, target)
    old = sorted(backup_dir.glob(f"{path.stem}_*{path.suffix}"))
    for stale in old[:-keep] if keep > 0 else []:
        stale.unlink(missing_ok=True)


def replace_text(path: str | Path, text: str, *, backup_dir: str | Path, keep: int = 14) -> None:
    """把 `path` 換成 `text`。失敗時拋例外、原檔不動。"""
    path = Path(path)
    _backup_once_a_day(path, Path(backup_dir), keep)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        if path.exists():
            shutil.copymode(path, tmp)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
