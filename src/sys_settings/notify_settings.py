"""通知伺服器（`services.notify_server`）的設定：爬蟲打進來要帶的共用密鑰。

架構定位：基礎層（`sys_settings`），不依賴專案內其他模組。上層：`services.notify_server`。下層：無。

介面：`NotifyServerSettings`（`shared_secret`）。

規則：
- 密鑰由環境變數 `NOTIFY_SHARED_SECRET` 給；compose 從 `.env` 帶進 bot 與 scraper 兩個容器，兩邊是同一個值。
- 沒設就不驗，只在 bot 啟動時警告一次。

例外與決策：通知伺服器只在 docker 內網開放、原本沒有任何驗證，爬蟲容器被攻破就能叫 bot 發文，所以加一把共用密鑰。
沒設不擋、只警告，是讓升級順序不受限：先重啟哪一邊都不會讓通知斷掉；要真的擋就把值設上，兩邊重啟後生效。
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class NotifyServerSettings(BaseSettings):
    shared_secret: str = ""

    model_config = SettingsConfigDict(env_prefix="NOTIFY_", extra="ignore", frozen=True)
