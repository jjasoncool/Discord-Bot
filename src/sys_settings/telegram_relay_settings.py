"""Telegram 轉發端的設定。目前只有 LLM 過濾（`services.relay.telegram_filter`）。"""
from __future__ import annotations

from typing import Any, Tuple

from pydantic_settings import BaseSettings, SettingsConfigDict

from sys_settings.paths import prompt_file


class TelegramFilterSettings(BaseSettings):
    """Telegram 訊息轉進 Discord 前，讓主模型判斷有沒有遊戲資訊；沒有的改送「垃圾訊息」thread。

    判斷標準：一定要看圖；文字或任一張圖有《鳴潮》資訊就放行；拿不準放行；
    模型不能用（產圖中、被佔太久、出錯）也放行——寧可漏掉一則垃圾，不能擋掉一則情報。
    只吃 class 預設值，理由同 `llm_settings.PersonaAgentSettings`（MODE 這種通用環境變數名會撞到）。

    **開關不在這裡**：off／dry_run／on 是 `settings/switches.json` 的 `telegram_filter_mode`（改了就生效、不用重啟，
    見 `sys_settings.switches`）。這裡只放很少改的細項。
    """

    prompt_path: str = prompt_file("telegram_filter_prompt.txt")

    #: 每個發送單位（單則或整本相簿）最多給模型看幾張圖：前幾個媒體各一張，媒體不到這個數時，
    #: 剩下的名額給動圖與影片多抽幾格（相簿看前 4 張）
    max_images: int = 4
    #: 送給模型前縮到長邊不超過這個像素（照片中位數剛好 1280）
    image_max_side: int = 1280
    #: 圖檔超過這個大小就不讀（避免把幾百 MB 的檔整個讀進記憶體）；影片不受限，ffmpeg 直接讀檔
    image_max_bytes: int = 64 * 1024 * 1024
    #: 影片先平均取幾格，再挑變化大的
    video_sample_frames: int = 12
    #: 影片抽幀的時限
    video_timeout_seconds: float = 60
    #: 文字太長時只給模型看前面這麼多字
    max_text_chars: int = 1500

    #: 單次模型呼叫的逾時（不含排隊）
    request_timeout_seconds: float = 60
    #: 排隊＋重問的總上限：模型忙就等、不放行，排滿這麼久還判不到才放行並認定模型掛了
    give_up_seconds: float = 30 * 60
    #: 模型逾時或連不上時，隔多久再排一次（逐次加倍，最多隔 `retry_max_seconds`）
    retry_initial_seconds: float = 30
    retry_max_seconds: float = 300
    #: 產圖佔著 GPU 時，隔多久看一次做完了沒
    busy_poll_seconds: float = 5

    model_config = SettingsConfigDict(extra="forbid", frozen=True)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: Any,
        env_settings: Any,
        dotenv_settings: Any,
        file_secret_settings: Any,
    ) -> Tuple[Any, ...]:
        """停用 env/dotenv，僅接受初始化參數與 class 預設值。"""
        return (init_settings,)
