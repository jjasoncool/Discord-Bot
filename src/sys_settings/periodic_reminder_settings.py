"""週期活動提醒（深塔／海墟／終焉矩陣）的設定。

**起算日為什麼寫在程式裡**：官方從未公告這兩個週期，錨點是從聊天紀錄與管理員手記推出來的
（海墟另有 FB 貼文 273 佐證 2026-02-16 04:00）。週期幾乎不會變，真的改制時改這裡並重啟；
`config.json` 是使用者設定檔，不放這種資料。

時間一律是**伺服器時間**（`services.event_time_parser.SERVER_TZ`，遊戲決定、固定 UTC+8），
這裡的 datetime 不帶時區，由 `services.periodic_reminder` 補上。
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict
from pydantic_settings import BaseSettings, SettingsConfigDict


class ReminderCycle(BaseModel):
    """一個固定週期重置的項目。"""

    #: 英文代號：去重 key 與整合測試參數用，定了就不要改（改了會重發已發過的提醒）
    key: str
    #: 顯示名稱
    name: str
    emoji: str
    #: 任何一次已知的重置時刻（伺服器時間、不帶時區）；之前或之後都能推算
    anchor: datetime
    period_days: int = 28

    model_config = ConfigDict(frozen=True)


class VersionStageItem(BaseModel):
    """跟著版本走的項目（終焉矩陣）：每次版本更新維護開始後 `open_delay_days` 天的 04:00 開放新階段，
    下一次版本更新時結束。版本更新時刻由 `VersionDateResolver.update_starts()` 從官方公告推得。"""

    #: 英文代號：去重 key 用，定了就不要改
    key: str
    name: str
    emoji: str
    open_delay_days: int = 7

    model_config = ConfigDict(frozen=True)


class PeriodicReminderSettings(BaseSettings):
    """週期活動提醒：結束前一天提醒還沒打的人、重置／開放當下靜音提醒，成員自助訂閱身份組。"""

    enabled: bool = True
    #: channel_registry「週期提醒頻道」寫入 config.json 的 key
    channel_config_key: str = "periodic_reminder_channel_id"
    #: 訂閱身份組名稱：bot 會把記錄的身份組同步成這個名字（改名只要改這裡）；
    #: 找不到記錄的 id 時，也會先用這個名稱找既有身份組
    role_name: str = "週期活動提醒"
    #: 身份組 id 與面板訊息 id（不進版控，與自介面板的 runtime 檔同一套做法）
    runtime_path: str = "settings/periodic_reminder_runtime.json"

    #: 結束前提醒：重置前一天的幾點發（伺服器時間），正常 @
    ending_reminder_hour: int = 20
    #: 重置提醒錯過時最晚補到重置當天幾點；超過就不補（內容已經不新了）
    reset_catchup_until_hour: int = 12

    cycles: tuple[ReminderCycle, ...] = (
        ReminderCycle(key="tower", name="逆境深塔", emoji="🗼", anchor=datetime(2026, 3, 2, 4, 0)),
        ReminderCycle(key="sea", name="冥歌海墟", emoji="🌊", anchor=datetime(2026, 2, 16, 4, 0)),
    )
    version_stages: tuple[VersionStageItem, ...] = (
        VersionStageItem(key="matrix", name="終焉矩陣", emoji="🧩"),
    )

    model_config = SettingsConfigDict(env_prefix="PERIODIC_REMINDER_", extra="ignore", frozen=True)
