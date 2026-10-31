"""管理主控台（私訊裡的頻道綁定面板、機器人狀態）的設定。"""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AdminConsoleSettings(BaseSettings):
    #: 頻道綁定面板每頁幾項：超過就翻頁；一頁的選單只列本頁的項目（一個選單最多 25 個選項）
    bindings_page_size: int = Field(default=8, ge=1, le=25)

    model_config = SettingsConfigDict(env_prefix="ADMIN_CONSOLE_", extra="ignore", frozen=True)


ADMIN_CONSOLE_SETTINGS = AdminConsoleSettings()
