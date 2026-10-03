"""商品上架的設定：觀星者在商品論壇上架商品，買家挑選下單後走交易流程。

商品論壇的頻道 id 由使用者在 `/server_manager` 綁定、寫在 `config.json`，這裡只放它的 key。
"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class ShopSettings(BaseSettings):
    #: channel_registry 寫入 config.json 的 key
    forum_channel_key: str = "shop_forum_channel_id"
    #: 能上架的身份組：`config.json` 裡 `role_mapping` 的 key（伺服器上叫觀星者）
    seller_role: str = "Trader"
    #: 幣別預設值（每篇商品可以自己改）
    default_unit: str = "NT$"
    #: 一篇商品最多幾個品項（一個下拉選單最多 25 個選項）
    max_variants: int = 25
    #: 一次最多買幾種（填數量的視窗最多 5 欄）
    max_pick: int = 5
    #: 一篇商品最多幾張圖（上傳欄位一次最多 10 個檔案）
    max_images: int = 10
    #: 還有沒截止的預購時，商品貼文掛的論壇標籤（預購截止的提醒靠它找商品）
    preorder_tag_name: str = "預購中"
    #: 置頂上架說明的標題（綁定商品論壇時自動發，也用它找回既有的那篇）
    guide_title: str = "📌 上架說明"
    #: 商品貼文多久沒人講話才自動封存（分鐘，Discord 允許的最長值）
    listing_auto_archive_minutes: int = 10080
    #: 檢查預購截止的最長間隔（秒）
    cutoff_check_max_sleep_seconds: int = 3600

    model_config = SettingsConfigDict(env_prefix="SHOP_", extra="ignore", frozen=True)
