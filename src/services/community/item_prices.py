"""賣家物品價格表（`settings/item_prices.json`）的唯一讀寫點。

架構定位：功能層（`services/community`）。上層：指令層（`commands.user_commands` 查價、`commands.trade_commands`
設價、`commands.forum_monitor` 開交易時附上供應方價格）。下層：`utils.hot_files`（讀，改檔即生效）、
`utils.runtime_file`（寫，暫存檔換名、每天第一次改寫前備份）、`sys_settings.paths`（檔案位置）。

介面：
- `all_prices() -> dict[str, dict[str, int]]`：整份表，`{賣家 id 字串: {物品 value: 價格}}`；缺檔或壞檔回空 dict。
- `user_prices(user_id) -> dict[str, int]`：某賣家的價格；沒設過回空 dict。
- `set_user_prices(user_id, prices)`：換掉某賣家的整組價格，其他賣家不動；寫檔失敗拋例外。

規則：
- 要碰這個檔只能經過這裡（守衛 `test_shared_conventions`）；回傳的 dict 是複本，改它不會寫回。
- 檔案格式與位置不變（這次只收攏讀寫機制），所以現有資料不需遷移。

例外與決策：寫失敗往外丟、不吞——吞掉會讓賣家以為設好了；呼叫端接到要回「沒有存成功」。
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from sys_settings.paths import settings_file
from utils import runtime_file
from utils.hot_files import read_parsed

PRICES_PATH = settings_file("item_prices.json")


def _parse(raw: str):
    return json.loads(raw)   # 不是 dict 的內容由呼叫端當成空的


def all_prices(path: str | Path = PRICES_PATH) -> dict[str, dict[str, int]]:
    data = read_parsed(path, parse=_parse, label="物品價格表", missing_ok=True)
    return copy.deepcopy(data) if isinstance(data, dict) else {}


def user_prices(user_id: int | str, path: str | Path = PRICES_PATH) -> dict[str, int]:
    prices = all_prices(path).get(str(user_id))
    return dict(prices) if isinstance(prices, dict) else {}


def set_user_prices(user_id: int | str, prices: dict[str, int], path: str | Path = PRICES_PATH,
                    *, backup_dir: str | Path | None = None) -> None:
    """重讀最新內容、只換這位賣家那一組，再安全寫回（備份目錄同狀態檔，見 `runtime_file.default_backup_dir`）。"""
    data = all_prices(path)
    data[str(user_id)] = dict(prices)
    runtime_file.save(path, data, backup_dir=backup_dir)
