"""全站時區：所有服務跑在同一台機器、同一個時區，不應各自硬編。

原本專案有 8 處各自寫 `timezone(timedelta(hours=8))`（`TAIPEI_TZ` / `_TAIPEI_TZ` /
`TZ_UTC8` / `SERVER_TZ` 四種命名），而 `AskAICommandSettings.taipei_utc_offset_hours`
是唯一可設定的來源、卻只有 /askai 一處在用——真去改那個設定值，只有它會跟著動。
收斂成單一來源後，要調整就只有這裡一個地方。

**唯一的例外是 scraper 容器**：它掛的是 `./src/scraper` → `/app`，根目錄看不到
`sys_settings`，所以 `scraper/tools/extract_fingerprint.py` 只能自己保留一份
（那裡有註解指回本檔）。要真正共用得改 compose 掛載，代價大於收益；兩邊都吃
compose 的 `TZ=Asia/Taipei`，實務上不會分岔。

若日後要處理其他國家的資料（例如非 UTC+8 的遊戲伺服器公告），**不要改這個值**——
那屬於「那份資料宣告的時區」，應該在該處另立常數，而不是把全站時區跟著搬。
"""
from __future__ import annotations

from datetime import timedelta, timezone

from pydantic_settings import BaseSettings


class TimeSettings(BaseSettings):
    """全站時區設定（可用環境變數 `APP_UTC_OFFSET_HOURS` 覆寫）。"""

    app_utc_offset_hours: int = 8


TIME_SETTINGS = TimeSettings()

#: 全站共用時區物件。需要 `datetime.now(...)` / `astimezone(...)` 時一律用它。
APP_TZ = timezone(timedelta(hours=TIME_SETTINGS.app_utc_offset_hours))
