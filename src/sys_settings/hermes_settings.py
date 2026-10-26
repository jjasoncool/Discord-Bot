"""Hermes（bot 的附屬 agent）相關設定：bot 對它開的模型端點，以及之後 bot 呼叫它用的金鑰。

架構定位：基礎層（`sys_settings`），不依賴專案內其他模組。上層：`services.llm_proxy`、`services.notify_server`。下層：無。

介面：`HermesSettings`。

規則：
- 金鑰由環境變數 `HERMES_API_KEY` 給；compose 從 `.env` 帶進 bot，也以 `API_SERVER_KEY` 帶進 hermes 容器，兩個方向同一把。
- 沒設金鑰就不開模型端點。和通知密鑰「沒設就放行」不同：模型端點會占用顯示卡，不能沒驗證就開。

例外與決策：等鎖上限、本文大小、輸出長度上限是參數不是開關，所以放這裡而不是 `settings/switches.json`。
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class HermesSettings(BaseSettings):
    #: bot 與 Hermes 雙向共用的金鑰；空字串＝不開 /v1 端點
    api_key: str = ""
    #: 一次轉發最多等 GPU 閘門幾秒；超過回 503 讓 Hermes 自己退避重試，不讓它的請求在 bot 裡排成一長串
    proxy_max_wait_seconds: float = 120.0
    #: 回 503 時給的 Retry-After（秒）
    proxy_retry_after_seconds: int = 30
    #: 請求本文上限（aiohttp 預設 1 MiB，長 context 的對話會超過）
    proxy_max_body_bytes: int = 32 * 1024 * 1024
    #: 每次呼叫最多讓模型寫幾個 token：串流時每一塊都會續租，租約擋不住寫不停的模型，只能靠這個上限
    proxy_max_tokens: int = 4096
    #: 租約比 LLM 逾時再多幾秒：第一塊要等 prompt 讀完才來，64k 冷讀約 200 秒，租約不能比它短
    proxy_lease_extra_seconds: float = 30.0

    model_config = SettingsConfigDict(env_prefix="HERMES_", extra="ignore", frozen=True)
