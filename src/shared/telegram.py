"""bot 與 telegram-scraper 兩個容器都要用的 Telegram 定義：頻道識別值的正規化、媒體補圖的時限。

架構定位：基礎層（`shared`），兩個容器唯一共用的程式。bot 容器掛整個 src 所以看得到；telegram-scraper 容器只掛
自己的資料夾，compose 另外把 `src/shared` 唯讀掛到 `/opt/pylib/shared` 並設 `PYTHONPATH=/opt/pylib`。
  - 上層：bot 的 `services.relay.telegram_relay_service`（相簿補圖時限、頻道名稱比對）、`settings.channel_registry`
    （綁頻道時正規化識別值）；爬蟲的 `tg_config`、`media_download`。
  - 下層：只有標準庫。

介面：
- `normalize_channel_identifier(value)`：把 `https://t.me/s/xxx`、`@xxx`、`xxx/` 都變成 `xxx`。
- `MEDIA_RETRY_WINDOW`：下載失敗後，爬蟲補掃重試到「發文時間＋這段時間」為止；轉發端的相簿補圖時限要和它一致。
- `MEDIA_HOLD_NOTIFY`：新訊息的圖第一次下載失敗時，爬蟲先不通知轉發端、等補掃補到圖；發文超過這段時間還沒補到才通知讓文字先送。

規則：只放兩邊都要的東西，而且只能依賴標準庫（爬蟲容器沒有 bot 的套件）；不要 import 專案裡其他模組。

例外與決策：不把整個 src 掛給爬蟲——它只做爬蟲，不該看得到 bot 的程式；也不在兩邊各留一份靠測試比對——那是兩個真相。
所以單獨掛這一小包。
"""
from __future__ import annotations

from datetime import timedelta


def normalize_channel_identifier(value: str) -> str:
    """把頻道識別值正規化為 Telethon 可用格式。"""
    value = value.strip()
    value = value.replace("https://t.me/s/", "")
    value = value.replace("https://t.me/", "")
    value = value.strip("/")
    if value.startswith("@"):
        value = value[1:]
    return value


MEDIA_RETRY_WINDOW = timedelta(hours=12)
MEDIA_HOLD_NOTIFY = timedelta(minutes=30)
