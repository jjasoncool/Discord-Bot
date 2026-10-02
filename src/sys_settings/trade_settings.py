"""交易流程的設定：自由市場接單 → 購物車私人 thread → 領收／取消 → 封存。

頻道 id 是使用者在 `/server_manager` 綁定、寫在 `config.json` 的，這裡只放它們的 key。
"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class TradeSettings(BaseSettings):
    #: 供應方對需求貼文按這些表情才算接單
    accept_emojis: tuple[str, ...] = ("✅", "🤝", "💰")
    #: 供應方的身份組：`config.json` 裡 `role_mapping` 的 key（伺服器上叫觀星者）
    supplier_role: str = "Trader"

    #: channel_registry 寫入 config.json 的 key
    forum_channel_key: str = "trade_forum_channel_id"
    cart_channel_key: str = "cart_delivery_channel_id"
    archive_channel_key: str = "archive_channel_id"
    #: 封存頻道是論壇時套用的標籤
    archive_tag_name: str = "封存"

    #: 供應方通知領收後，需求方多久沒按「已領收」就自動視為已領收
    receipt_timeout_hours: int = 24
    #: 自動領收前幾小時再 @ 需求方提醒一次（0＝不提醒）；讓「一直沒反應」才等於已領收
    receipt_reminder_hours_before: int = 6
    #: 提醒過的通知上，bot 按這個表情當記號
    receipt_reminded_emoji: str = "⏰"
    #: 檢查領收期限的最長間隔（秒）；新的通知最晚這麼久會被排進下一次檢查
    deadline_check_max_sleep_seconds: int = 3600
    #: 檢查領收期限時，往回翻幾天內封存的交易 thread（停機期間被自動封存的也要補做）
    archived_scan_days: int = 30
    #: 封存時最多複製幾則需求貼文裡的對話
    archive_history_limit: int = 100

    model_config = SettingsConfigDict(env_prefix="TRADE_", extra="ignore", frozen=True)
