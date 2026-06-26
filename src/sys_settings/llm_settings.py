"""LLM 系統級設定模型與載入工具。"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Tuple
from urllib.parse import quote_plus

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal

logger = logging.getLogger("discord_bot")


class LLMServiceSettings(BaseSettings):
    """LLM 服務層設定（可由 env/dotenv 覆寫；後端不限）。"""

    llm_base_url: str = Field(
        default="http://192.168.56.1:11434",
        validation_alias="LLM_BASE_URL",
    )
    llm_model: str = Field(
        default="gemma4:26b",
        validation_alias="LLM_MODEL",
    )
    llm_timeout: int = Field(
        default=300,
        validation_alias="LLM_TIMEOUT",
    )
    pgvector_host: str = Field(
        default="pgvector",
        validation_alias="PGVECTOR_HOST",
    )
    pgvector_port: int = Field(
        default=5432,
        validation_alias="PGVECTOR_PORT",
    )
    pgvector_db: str = Field(
        default="discord_data",
        validation_alias="PGVECTOR_DB",
    )
    pgvector_user: str = Field(
        validation_alias="PGVECTOR_USER",
    )
    pgvector_password: str = Field(
        validation_alias="PGVECTOR_PASSWORD",
    )
    llm_context_safety_rules_path: str = Field(
        default="/app/settings/prompts/llm_context_safety_rules.json",
    )
    # 可熱更新模型設定：直接修改此 JSON 檔即可生效（無須重啟容器）
    llm_runtime_model_path: str = Field(
        default="/app/sys_settings/llm_runtime_config.json",
    )

    default_temperature: float = 0.85
    default_top_p: float = 0.9
    default_repeat_penalty: float = 1.15
    default_num_ctx: int = 8192

    context_open_tag: str = "<context_json>"
    context_close_tag: str = "</context_json>"
    latest_open_tag: str = "<latest_user_message>"
    latest_close_tag: str = "</latest_user_message>"

    model_config = SettingsConfigDict(
        extra="ignore",
        frozen=True,
        env_file=".env",
        env_file_encoding="utf-8",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: Any,
        env_settings: Any,
        dotenv_settings: Any,
        file_secret_settings: Any,
    ) -> Tuple[Any, ...]:
        """允許 init > env > dotenv > file secrets 的覆寫順序。"""
        return (init_settings, env_settings, dotenv_settings, file_secret_settings)

    def build_pgvector_database_url(self) -> str:
        """由 PGVECTOR_* 參數在程式內組裝 asyncpg 連線字串。"""
        encoded_user = quote_plus(self.pgvector_user)
        encoded_password = quote_plus(self.pgvector_password)
        return (
            f"postgresql+asyncpg://{encoded_user}:{encoded_password}"
            f"@{self.pgvector_host}:{self.pgvector_port}/{self.pgvector_db}"
        )

class LLMContextSafetyRules(BaseModel):
    """LLM 對於不可信上下文的安全規則。"""

    system_safety_prompt: str
    untrusted_context_intro: str
    image_instruction_prompt: str
    impression_moderation_system_prompt: str
    impression_moderation_user_prompt_template: str
    impression_moderation_schema_hint: dict[str, str]


class BackendProfile(BaseModel):
    """單一後端的設定 profile。

    `extra_body`：chat completion request body 的後端專屬 top-level merge 欄位
      （Ollama 的 `think` / `keep_alive` / `options.num_ctx`、Lemonade 的
      `chat_template_kwargs` / `cache_prompt` 等）。

    `model_load_options`：server admin API 用的 per-model 載入參數
      （目前只 Lemonade 有用，bot 啟動或第一次呼叫某 model 時 push 到
      `/api/v1/load`，避免每次調 ctx_size 都要去 Lemonade UI 手動設）。
      key 是 model id，value 是 Lemonade `recipe_options` dict（如
      `{"ctx_size": 12288}`）。Ollama / vLLM 在這個欄位就空著（Ollama 走
      per-request `extra_body.options.num_ctx`；vLLM 是 server 啟動參數）。
    """

    extra_body: dict[str, Any] = Field(default_factory=dict)
    model_load_options: dict[str, dict[str, Any]] = Field(default_factory=dict)


class LLMRuntimeConfig(BaseModel):
    """LLM 執行時可熱更新設定（後端不限）。

    切後端的單一控制點：搭配 `.env` 的 `LLM_BASE_URL` 兩邊一起改即可。
    `backends` 內各 profile 的 `extra_body` 是後端專屬參數的歸宿。
    """

    backend: Literal["ollama", "lemonade", "vllm"] = "ollama"
    model: str
    embed_model: str
    moderation_model: str | None = None
    personality_model: str | None = None
    # 背景插話/傾聽用的小模型（功能二）；None 代表沿用主 model
    ambient_model: str | None = None
    backends: dict[str, BackendProfile] = Field(default_factory=dict)
    # 舊欄位：保留以避免舊 config 載入失敗；新 config 應將 think 放進 backends.ollama.extra_body
    think: bool = True


class AskAICommandSettings(BaseSettings):
    """/askai 指令相關設定（集中常數來源，不使用 env 覆寫）。"""

    max_context_messages: int = 100
    max_context_to_send: int = 50
    min_recent_context: int = 25
    max_relevant_context: int = 25
    taipei_utc_offset_hours: int = 8

    discord_context_begin: str = "<context:discord_chat_begin>"
    discord_context_end: str = "</context:discord_chat_end>"
    rag_context_begin: str = "<context:rag_begin>"
    rag_context_end: str = "</context:rag_end>"

    default_system_prompt: str = (
        "你是 Discord 群組中的一位群友，請用自然口吻聊天。"
        "回覆時只能使用繁體中文，避免使用英文或簡體中文。"
    )

    prompt_file_path: str = "/app/settings/prompts/askai_system_prompt.txt"
    identity_file_path: str = "/app/settings/prompts/persona_identity.txt"
    guardrails_file_path: str = "/app/settings/prompts/persona_guardrails.txt"
    examples_file_path: str = "/app/settings/prompts/persona_examples.txt"
    prompt_log_path: str = "/logs/askai_prompt.txt"
    # askai_prompt：以時間輪替，並只保留固定份數
    prompt_log_when: str = "midnight"
    prompt_log_interval: int = 1
    prompt_log_backup_count: int = 3
    # debug 另存一份，避免混入真正送給 Ollama 的文字
    prompt_debug_log_path: str = "/logs/askai_prompt_debug.txt"
    prompt_debug_log_max_bytes: int = 5 * 1024 * 1024
    prompt_debug_log_backup_count: int = 5

    # json line (多行格式)
    response_log_path: str = "/logs/askai_response_history.jsonl"
    # response history：容量輪替
    response_log_max_bytes: int = 20 * 1024 * 1024
    response_log_backup_count: int = 10

    max_image_size_bytes: int = 5 * 1024 * 1024
    askai_cooldown_count: int = 1
    askai_cooldown_seconds: float = 180.0

    model_config = SettingsConfigDict(
        extra="ignore",
        frozen=True,
    )

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


class AskAIWebSettings(BaseSettings):
    """/askai 網路搜尋整合設定（關鍵項可由 env/dotenv 覆寫）。"""

    enabled: bool = Field(
        default=True,
        validation_alias="ASKAI_WEB_ENABLED",
    )
    searxng_url: str = Field(
        default="http://searxng:8080/search",
        validation_alias="SEARXNG_URL",
    )
    default_engines: str = "google,bing,duckduckgo,brave"
    news_engines: str = "google news,bing news,duckduckgo news"
    timeout_seconds: float = 4.0
    top_k: int = 5
    language: str = "zh-TW"

    model_config = SettingsConfigDict(
        extra="ignore",
        frozen=True,
        env_file=".env",
        env_file_encoding="utf-8",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: Any,
        env_settings: Any,
        dotenv_settings: Any,
        file_secret_settings: Any,
    ) -> Tuple[Any, ...]:
        """允許 init > env > dotenv > file secrets 的覆寫順序。"""
        return (init_settings, env_settings, dotenv_settings, file_secret_settings)


class AmbientChatSettings(BaseSettings):
    """功能二「AI 偶爾插話 / 閒聊」設定（集中常數來源，不使用 env 覆寫）。

    觸發哲學：硬性過濾（零成本）→ 冷卻/上限 → 機率（偶爾感 + 減壓閥）→ 背景生成。
    被 @ 或 reply 機器人時走 must-reply，覆蓋冷卻與機率。
    與 /askai 共用 Lemonade 單流；`/askai` 活躍窗口內背景插話暫停，避免換模型 ping-pong。
    """

    enabled: bool = True
    # 綁定頻道的 config.json key（由 channel_registry「AI 插話頻道」寫入）
    channel_config_key: str = "ambient_chat_channel_id"
    # 插話「行為」規則（簡短、允許沉默…）；人設身份另由 identity_path 疊上
    prompt_path: str = "/app/settings/prompts/ambient_reply_prompt.txt"
    # 插話人設＝共用人格 + 共用守則 + 插話行為（模組化拼裝）。不載 askai 的「深聊風格」那層，
    # 所以 ambient 天生比較不端著，不必另維護一份精簡人格。
    use_shared_identity: bool = True
    identity_path: str = "/app/settings/prompts/persona_identity.txt"
    guardrails_path: str = "/app/settings/prompts/persona_guardrails.txt"

    # 背景上下文：抓近期幾則當短期對話記憶（12B ctx 已調到 16384，可帶完整脈絡）
    history_limit: int = 20
    # Phase B 認得人：召回在場成員 persona card（intro/impression/auto_personality）
    persona_top_k: int = 5
    persona_cache_seconds: float = 60.0  # per-channel persona 快取，避免 armed 期間每則打 pgvector
    # persona card 每行上限只當安全網（避免單張卡異常長），ctx 充足下設寬鬆即可
    persona_line_max_chars: int = 500
    persona_max_lines: int = 6

    # ── 實驗：chat 歷史 callback（預設關，灰度開關）。撈「這個頻道」過去語意相關的舊訊息，
    #    經 relevance×importance×recency 三因子 gate 後，當「模糊印象」折進 persona_context。
    #    詳見 ambient_reply._build_chat_callback_context。所有門檻/權重待實測調。
    callback_enabled: bool = True
    callback_top_k: int = 5                          # 最多注入幾條（實際筆數受距離地板限制：過閘的不足此數就更少）
    callback_candidate_pool: int = 25               # pgvector 先撈幾條再 gate（要 > top_k，過濾後才有得挑滿）
    # 唯一相關性閘＝絕對 cosine 距離地板（越小越近）。importance/recency 只排序、不當門檻。
    # topic 模式（全作者）嚴；target 模式（撈本人原話、低風險）放寬。實值待開 callback_debug
    # 看真實距離分布再調：把地板設在「相關舊話」與「無關舊話」距離的中間。
    callback_max_distance: float = 0.50             # topic 模式地板（起點偏寬，先讓結果出來，再用 debug 收緊）
    callback_target_max_distance: float = 0.70      # target 模式地板（更寬，因撈本人原話低風險）
    callback_recency_half_life_hours: float = 336.0 # recency 半衰期（時）；336≈2 週
    callback_recency_gap_hours: float = 2.0         # 比此時數更舊才算「過去」（排除近窗）
    callback_min_chars: int = 8                     # 候選品質：太短不當回憶點
    callback_w_relevance: float = 0.5               # 排序權重：relevance 最高（文不對題最糟）
    callback_w_importance: float = 0.35
    callback_w_recency: float = 0.15
    callback_line_max_chars: int = 120              # 注入行截斷（模糊印象不需長）
    callback_debug: bool = True                     # 調參用：把候選池/距離/三因子分/過哪關 log 進 discord_bot.log（調完關掉）

    # 觸發門檻：插不插由 12B 判斷，「偶爾」感由冷卻 + 每小時上限保證（不用機率）
    min_chars: int = 4               # 太短（貼圖式單字）不插
    max_chars: int = 300             # 太長（長篇貼文）不插
    cooldown_seconds: float = 300.0  # 同頻道兩次自發插話的最短間隔（5 分鐘→真的「偶爾」）；冷卻期內連判斷都不跑
    hourly_cap: int = 20             # 同頻道每小時自發插話上限（太低會整個小時靜默）
    # per-channel 序列處理：一輪 burst 內最多重評估幾次（生成期間有新訊息才重評估）；
    # 防超活躍頻道無限重評估空燒 12B。冷卻 + 減壓閥才是主要節流。
    max_passes_per_burst: int = 3
    # 看門狗：單一 pass 超過此秒數視為卡住 → 取消，避免一次生成卡死整個頻道的序列處理。
    # 要夠長以容納冷載入(model load 30-60s)+生成。
    pass_timeout_seconds: float = 180.0
    # 減壓閥（預設關閉）：1.0 = 每則都讓 12B 判斷；頻道太吵、12B 負載過高時才調 < 1.0 抽樣降載
    judge_sampling_rate: float = 1.0

    # 與 /askai 的讓位：foreground 活躍此秒數內，背景插話暫停（防換模型 ping-pong）
    askai_grace_seconds: float = 90.0

    # 模型回此 sentinel（或空字串）代表「沒梗」→ 不發送
    silence_sentinel: str = "[PASS]"

    # ── 看圖（ambient 模型需具 vision；QAT 12B 自帶 mmproj）──
    image_max_count: int = 1             # 一次最多帶幾張圖（成本控制）
    image_max_bytes: int = 5 * 1024 * 1024

    # ── Phase C 記憶寫入（preference_fact）──
    extractor_prompt_path: str = "/app/settings/prompts/preference_extractor_prompt.txt"
    memory_min_confidence: float = 0.6   # 低於此不寫入（寧缺勿濫）
    trusted_promote_at: int = 2          # 不同批次提到達此次數 → tentative 升 trusted（才會被召回）
    memory_flush_threshold: int = 30     # 插話頻道訊息累積達此量觸發一次抽取批次
    memory_recall_top_k: int = 6         # 召回時最多帶幾筆 trusted 偏好
    memory_flush_interval_seconds: float = 180.0  # 背景排程多久檢查一次是否該 flush（閒置才真的跑）
    memory_buffer_max: int = 300         # 記憶緩衝上限，超過丟最舊

    # ── 招牌梗 signature_tag（持久印象層；corroboration + 慢衰減；與 preference_fact 平行）──
    tag_extractor_prompt_path: str = "/app/settings/prompts/signature_tag_extractor_prompt.txt"
    tag_min_confidence: float = 0.7        # 比偏好嚴
    tag_promote_at_low: int = 3            # low（外號/口頭禪）升 trusted 門檻
    tag_promote_at_spicy: int = 5          # spicy（身材/調情）門檻更高；本人認領由守門階段保證，計數同樣每日去重
    tag_count_cap: int = 6                 # mention_count 上限（耐久靠半衰期、不靠刷 count）
    tag_recall_top_k: int = 4
    tag_halflife_low_days: float = 45.0
    tag_halflife_spicy_days: float = 20.0  # 敏感梗更快淡出
    tag_recall_floor: float = 0.75         # 召回時 effective 強度門檻
    tag_demote_floor: float = 0.4          # 低於此 → trusted 降 tentative
    tag_archive_floor: float = 0.15        # 低於此 → 封存（delete）
    tag_spicy_dark_launch: bool = True     # spicy 升級先寫庫、停 callback、只 log 人工抽看

    # ── debug 觀測（debug 完可關 debug_log）──
    debug_log: bool = True               # 把每次插話的完整 prompt 寫進檔案
    debug_prompt_log_path: str = "/logs/ambient_prompt.txt"
    debug_log_max_bytes: int = 5 * 1024 * 1024
    debug_log_backup_count: int = 3

    model_config = SettingsConfigDict(
        extra="ignore",
        frozen=True,
    )

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


class DiaryReflectionSettings(BaseSettings):
    """AI 每日日記回顧（v1）：每天在專屬頻道用琇紫口吻寫一段當天感想。

    純表達、不改行為——只反映它對今天的感受，不影響它對任何人的插話態度。
    與 ambient 共用人格/守則 prompt；社交來源預設＝插話頻道（ambient_chat_channel_id）。
    """

    enabled: bool = True
    # 日記發布頻道（channel_registry「AI 日記頻道」寫入 config.json 的 key）
    diary_channel_config_key: str = "ai_diary_channel_id"
    # 回顧哪個頻道的互動（預設＝插話頻道，就是它的社交場）
    source_channel_config_key: str = "ambient_chat_channel_id"

    # 日記人設＝共用人格 + 共用守則 + 日記行為（與 ambient 同源，只換最後一層）
    use_shared_identity: bool = True
    identity_path: str = "/app/settings/prompts/persona_identity.txt"
    guardrails_path: str = "/app/settings/prompts/persona_guardrails.txt"
    prompt_path: str = "/app/settings/prompts/diary_reflection_prompt.txt"

    # 排程（台北時區）：每天幾點寫日記
    schedule_hour: int = 0
    schedule_minute: int = 0

    # 回顧範圍：過去幾小時、最多取最近幾則、每則截斷長度
    lookback_hours: int = 24
    max_messages: int = 120
    max_chars_per_msg: int = 200

    # 生成：model=None 用 ambient_model；think=None 用後端預設；日記長度上限（post 前安全截）
    model: str | None = None
    think: bool | None = None
    max_diary_chars: int = 1500

    # debug 觀測
    debug_log: bool = True
    debug_prompt_log_path: str = "/logs/diary_prompt.txt"
    debug_log_max_bytes: int = 5 * 1024 * 1024
    debug_log_backup_count: int = 3

    model_config = SettingsConfigDict(extra="ignore", frozen=True)

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


def load_context_safety_rules(path: str | Path) -> LLMContextSafetyRules:
    """讀取並驗證 safety rules JSON（嚴格模式：缺檔或缺值直接拋錯）。"""
    safety_path = Path(path)

    if not safety_path.exists():
        raise FileNotFoundError(f"找不到 context safety rules 檔案: {safety_path}")

    try:
        content = safety_path.read_text(encoding="utf-8").strip()
        if not content:
            raise ValueError(f"context safety rules 檔案為空: {safety_path}")

        raw_data = json.loads(content)
        if not isinstance(raw_data, dict):
            raise ValueError(f"context safety rules 內容必須為 JSON object: {safety_path}")

        return LLMContextSafetyRules.model_validate(raw_data)
    except Exception as exc:
        logger.error("載入 context safety rules 失敗（嚴格模式）: %s", exc)
        raise RuntimeError(f"無法載入 context safety rules: {safety_path}") from exc


def load_llm_runtime_config(path: str | Path) -> LLMRuntimeConfig:
    """讀取 LLM 執行時設定（嚴格模式：缺檔或缺值直接拋錯）。"""
    runtime_path = Path(path)

    if not runtime_path.exists():
        raise FileNotFoundError(f"找不到 ollama runtime config: {runtime_path}")

    try:
        content = runtime_path.read_text(encoding="utf-8").strip()
        if not content:
            raise ValueError(f"ollama runtime config 檔案為空: {runtime_path}")

        raw_data = json.loads(content)
        if not isinstance(raw_data, dict):
            raise ValueError(f"ollama runtime config 內容必須為 JSON object: {runtime_path}")

        return LLMRuntimeConfig.model_validate(raw_data)
    except Exception as exc:
        logger.error("載入 ollama runtime config 失敗（嚴格模式）: %s", exc)
        raise RuntimeError(f"無法載入 ollama runtime config: {runtime_path}") from exc
