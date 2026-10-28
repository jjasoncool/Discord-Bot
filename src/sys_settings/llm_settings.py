"""LLM 系統級設定模型與載入工具。"""

from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Literal, Tuple
from urllib.parse import quote_plus

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from sys_settings.paths import LOGS_DIR, SYS_SETTINGS_DIR, prompt_file

logger = logging.getLogger(__name__)


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
    #: 拿著 GPU 閘門算 embedding（聊天記憶寫入、情報搜尋算向量）時，單次請求、排隊等 embedding 名額、
    #: 載入模型各最多等幾秒，而且不重試（`make_safe_llm_embedding(holding_gpu_gate=True)`）。正常一批不到幾秒；
    #: 等滿 llm_timeout 再重試等於整段佔著顯示卡，插話與 /askai 全卡（2026-10-09 Lemonade 卡住時卡了一個多小時）
    gated_embed_timeout: int = Field(
        default=60,
        validation_alias="GATED_EMBED_TIMEOUT",
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
        default=prompt_file("llm_context_safety_rules.json"),
    )
    # 可熱更新模型設定：直接修改此 JSON 檔即可生效（無須重啟容器）
    llm_runtime_model_path: str = Field(
        default=str(SYS_SETTINGS_DIR / "llm_runtime_config.json"),
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

    def pgvector_connect(self):
        """開一條 pgvector 連線（psycopg2）。

        **憑證的擁有者負責提供連線方式**——原本專案有六處各自
        `psycopg2.connect(host=..., port=..., dbname=..., user=..., password=...)`，
        五個參數一字不差地抄了六遍。改連線池、加 timeout、換驅動時要記得改六個地方，
        而漏掉的那個不會報錯、只會行為不一致。

        延後 import psycopg2：讓沒裝驅動的環境（單元測試）也能匯入本設定模組。
        """
        import psycopg2

        return psycopg2.connect(
            host=self.pgvector_host,
            port=self.pgvector_port,
            dbname=self.pgvector_db,
            user=self.pgvector_user,
            password=self.pgvector_password,
        )

    @contextmanager
    def pgvector_cursor(self, *, commit: bool = False):
        """借一個 pgvector cursor，用完自動關連線。

        `commit=True` 時把整段包進交易（psycopg2 的 `with conn` 語意：正常結束就
        commit、拋例外就 rollback）。**憑證的擁有者一併提供存取方式**——不然每個
        呼叫端都要自己寫「開連線 → try → finally close」，`ai_interactions_store` 和
        `llm.persona.agent.store` 就各自抄了好幾份。
        """
        conn = self.pgvector_connect()
        try:
            if commit:
                with conn, conn.cursor() as cur:
                    yield cur
            else:
                with conn.cursor() as cur:
                    yield cur
        finally:
            conn.close()

    def pgvector_vector_store(self, *, table_name: str, embed_dim: int, hybrid_search: bool = True):
        """建 LlamaIndex 的 PGVectorStore；聊天、成員資料、檢索三個向量庫都從這裡拿。

        借出連線前先確認它還活著（`pool_pre_ping`）：資料庫會把閒置太久的連線關掉，池子不知道，
        下一個拿到那條連線的操作必定失敗；成員偏好寫入曾因此在「先刪舊的、再寫新的」中間失敗而丟資料。
        延後 import llama_index：讓沒裝它的環境也能匯入本設定模組。
        """
        from llama_index.vector_stores.postgres import PGVectorStore

        return PGVectorStore.from_params(
            database=self.pgvector_db,
            host=self.pgvector_host,
            password=self.pgvector_password,
            port=self.pgvector_port,
            user=self.pgvector_user,
            table_name=table_name,
            embed_dim=embed_dim,
            hybrid_search=hybrid_search,
            create_engine_kwargs={"pool_pre_ping": True},
        )

    def build_pgvector_database_url(self) -> str:
        """由 PGVECTOR_* 參數在程式內組裝 asyncpg 連線字串。"""
        encoded_user = quote_plus(self.pgvector_user)
        encoded_password = quote_plus(self.pgvector_password)
        return (
            f"postgresql+asyncpg://{encoded_user}:{encoded_password}"
            f"@{self.pgvector_host}:{self.pgvector_port}/{self.pgvector_db}"
        )


@contextmanager
def pg_savepoint(cur, name: str = "item"):
    """在交易裡開一個保存點包住一段寫入：這段失敗就只撤回這一段，交易回到可用狀態，可以接著寫下一段。

    PostgreSQL 的交易裡一句在伺服器端出錯，之後每一句都會被拒（current transaction is aborted），連 commit 都只會回滾；
    逐筆寫一批、想略過壞的那筆，就要每筆一個保存點。例外照樣往外丟：略過、記 log 還是整批放棄由呼叫端決定
    （連線斷了的話撤回那句也會失敗，丟出來的就是連線錯誤）。失敗後也 RELEASE，不然每壞一筆就多疊一層子交易。
    SAVEPOINT／RELEASE 之後 `cur.rowcount` 會變成 -1，要用筆數就在區段裡、資料語句之後馬上讀。
    交易本身（開、commit、rollback）照舊由呼叫端或 `pgvector_cursor(commit=True)` 管。
    """
    if not name.isidentifier():
        raise ValueError(f"保存點名稱只能是識別字：{name!r}")
    cur.execute(f"SAVEPOINT {name}")
    done = False
    try:
        yield
        done = True
    finally:
        if not done:
            cur.execute(f"ROLLBACK TO SAVEPOINT {name}")
        cur.execute(f"RELEASE SAVEPOINT {name}")


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
    #: 重新排序（rerank）用的模型；None＝沒有，情報搜尋就不重排
    rerank_model: str | None = None
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
    #: 一題回答最多產出幾個 token（含思考）。沒上限時一題寫不停會拿著顯示卡寫到逾時（實測 6,000～8,600 個 token 沒寫完）；
    #: 以常見的生成速度，這個值能在逾時前寫完
    answer_max_tokens: int = 4096
    #: 相關訊息的重排（開關 askai_rerank_mode）：融合名次前幾則送 reranker 連問題一起讀、重新打分
    rerank_candidates: int = 30
    #: 重排前最多等 GPU 幾秒（插話正在長回答時等不到就照融合名次）；拿到閘門後的租約秒數：reranker 是同步呼叫、途中
    #: 續不了租，租約要蓋過它單次 60 秒的逾時加上第一次冷載入（最多 180 秒），到期只會取消重排本身、照融合名次
    rerank_gpu_wait_seconds: float = 10.0
    rerank_lease_seconds: float = 240.0
    #: reranker 分數低於這個值的不進 prompt；None＝不設門檻。實測分數非常兩極（答得到的 0.95 以上、不相干的 0.0001
    #: 以下），0.1 只擋明顯不相干的；分布記在 askai_response_history 的 retrieval_debug.reranked，要調看那裡
    rerank_min_score: float | None = 0.1

    discord_context_begin: str = "<context:discord_chat_begin>"
    discord_context_end: str = "</context:discord_chat_end>"
    rag_context_begin: str = "<context:rag_begin>"
    rag_context_end: str = "</context:rag_end>"

    default_system_prompt: str = (
        "你是 Discord 群組中的一位群友，請用自然口吻聊天。"
        "回覆時只能使用繁體中文，避免使用英文或簡體中文。"
    )

    prompt_file_path: str = prompt_file("askai_system_prompt.txt")
    identity_file_path: str = prompt_file("persona_identity.txt")
    guardrails_file_path: str = prompt_file("persona_guardrails.txt")
    examples_file_path: str = prompt_file("persona_examples.txt")
    prompt_log_path: str = str(LOGS_DIR / "askai_prompt.txt")
    # askai_prompt：以時間輪替，並只保留固定份數
    prompt_log_when: str = "midnight"
    prompt_log_interval: int = 1
    prompt_log_backup_count: int = 3
    # debug 另存一份，避免混入真正送給 Ollama 的文字
    prompt_debug_log_path: str = str(LOGS_DIR / "askai_prompt_debug.txt")
    prompt_debug_log_max_bytes: int = 5 * 1024 * 1024
    prompt_debug_log_backup_count: int = 5

    # json line (多行格式)
    response_log_path: str = str(LOGS_DIR / "askai_response_history.jsonl")
    # response history：容量輪替
    response_log_max_bytes: int = 20 * 1024 * 1024
    response_log_backup_count: int = 10

    max_image_size_bytes: int = 10 * 1024 * 1024
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
    """/askai 網路搜尋整合設定（關鍵項可由 env/dotenv 覆寫）。開關在 settings/switches.json 的 `askai_web_search_mode`
    （10-09 由這裡的 `enabled`／`ASKAI_WEB_ENABLED` 搬過去；當時 .env 與 compose 都沒設）。"""

    searxng_url: str = Field(
        default="http://searxng:8080/search",
        validation_alias="SEARXNG_URL",
    )
    # 明確指定 engines 會繞過 SearXNG 的 disabled 設定，死掉的引擎要在這裡拿掉才有效。
    # 名單依 24 小時穩定度測試收斂：yahoo 72 次全查得到、全對題；duckduckgo 97%（偶爾真人驗證）。
    # bing 對題只七成、常回 0 筆，回垃圾時 SearXNG 不算錯誤、會直接混進結果（出過成人內容）；yandex 查得到但也回過成人網站
    default_engines: str = "yahoo,duckduckgo"
    # 新聞：有日期的引擎不限時間、結果照日期新到舊排（duckduckgo news 全附日期、七成是一週內的）；
    # 不給日期的引擎排不了，保留它自己支援的一週條件、排在有日期的後面（怎麼合併見 search._search_news）。
    # reuters 升級後回 401，拿掉
    news_engines: str = "duckduckgo news"
    news_undated_engines: str = "bing news"
    news_undated_time_range: str = "week"
    # 工具模式的天氣、匯率類型用 SearXNG 內建的專用引擎，答案在回應的 answers（不用註冊、不用授權碼）。
    # openmeteo 在 settings.yml 是 disabled，但明確指定 engines 一樣會跑（10-09 實測）；它只認英文地名
    weather_engines: str = "openmeteo"
    currency_engines: str = "currency"
    # 比 SearXNG 自己的最長等待（settings.yml max_request_timeout 4.0）多一點：剛好相等時，同一次查詢混進慢引擎，
    # 連已經回來的結果都一起丟掉
    timeout_seconds: float = 5.0
    top_k: int = 5
    # 引擎回報被擋（真人驗證、限流、拒絕存取）後，這段時間先不問它。SearXNG 對 duckduckgo 的真人驗證不會自己停用
    # （停用秒數寫死 0），每次都重打、每次都 0 筆；不問它也比較有機會讓封鎖自己解除（10-09 實測）
    blocked_engine_cooldown_seconds: float = 1800.0
    # 同一個查詢（同字串、同路由）這段時間內直接用上次的結果：少打引擎，降低被擋的機會
    cache_seconds: float = 300.0
    # 成人內容過濾：0 不過濾、1 一般、2 嚴格（SearXNG 的 safesearch 參數；settings.yml 預設 0）
    safesearch: int = 1
    # 主搜結果太少就走 general fallback。門檻不設 0：news 引擎常「只吐 1 筆」，
    # 那種結果答不了問題卻又擋掉救援，會安靜降級。
    fallback_min_results: int = 3
    language: str = "zh-TW"
    #: 工具模式（模型自己決定要不要查）時，怎麼用 web_search 的規則；只在有這個工具時接在系統提示詞後面
    rules_path: str = prompt_file("askai_web_rules.txt")

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


class AskAIIntelSettings(BaseSettings):
    """/askai 查遊戲情報（官網公告、官方 FB、PTT、巴哈）的細項參數；開關在 settings/switches.json 的
    `askai_intel_search_mode`。bot 當 MCP 客戶端連常駐的 search-mcp（`llm.retrievers.intel`）。

    只吃 class 預設值：`TOP_K` 這類通用環境變數名會誤蓋欄位（AskAIWebSettings 就有這個問題）。
    """

    #: search-mcp 的 MCP 端點（同一個 docker 網路用服務名稱連）
    mcp_url: str = "http://search-mcp:8765/mcp"
    #: 一次工具呼叫最多等幾秒。搜尋端冷啟動（Lemonade 把模型卸載後重新載入）實測 16.8 秒，
    #: 等顯示卡的額度另有 10 秒；逾時就把錯誤回給模型，讓它用手上的資料回答
    call_timeout_seconds: float = 40.0
    #: 最多查幾輪（每輪可同時呼叫好幾個工具）。每多一輪就多一次模型呼叫與搜尋（線上一次搜尋中位數約 12 秒）
    max_tool_rounds: int = 2
    #: 一次 search 最多給模型幾筆（工具結果也佔 context）
    search_limit: int = 6
    #: fetch 的全文最多給模型幾個字（PTT、巴哈的留言很長，而且是任何人都能寫的內容）。
    #: search-mcp 每頁的字數（SEARCH_SETTINGS.fetch_page_chars）不能超過這個值，否則每頁後段永遠讀不到
    fetch_max_chars: int = 2500
    #: 怎麼用情報工具的規則：只在真的有工具時接在系統提示詞後面（改檔即生效）
    rules_path: str = prompt_file("askai_intel_rules.txt")

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
    prompt_path: str = prompt_file("ambient_reply_prompt.txt")
    # 插話人設＝共用人格 + 共用守則 + 插話行為（模組化拼裝）。不載 askai 的「深聊風格」那層，
    # 所以 ambient 天生比較不端著，不必另維護一份精簡人格。
    use_shared_identity: bool = True
    identity_path: str = prompt_file("persona_identity.txt")
    guardrails_path: str = prompt_file("persona_guardrails.txt")
    # 風格對照範例（與 /askai 共用同一份 persona_examples.txt，人設共通不另維護）：
    # 教模型別跟著頻道互嗆口吻下場補刀、保持隔一層看戲的熟女調性。
    use_examples: bool = True
    examples_path: str = prompt_file("persona_examples.txt")

    # ── 風格召回（v2）：撈「被群裡按過讚、且與當下情境語意相近」的舊插話，當靈感注入（學味道別照抄）。
    #    走 ai_interactions.embedding（pgvector cosine）。保守起步：注入少、距離地板嚴；先 shadow 觀察。
    style_refs_enabled: bool = True       # True=注入進 prompt；False=純 shadow（只記 log、不影響回覆）
    style_refs_debug: bool = True         # 每次召回到什麼寫進 discord_bot.log（調參用，穩了再關）
    style_refs_top_k: int = 8             # pgvector 先撈幾條最近鄰
    style_refs_max_distance: float = 0.45 # cosine 距離地板（越小越像）；保守起步，看 debug 再放寬
    style_refs_inject_count: int = 2      # 過地板後最多注入幾條（在池子裡抽樣 → 每次不同、不跳針）
    style_refs_min_positive: int = 1      # 至少幾個正向反應才進召回池

    # 背景上下文：抓近期幾則當短期對話記憶（插話模型的 context 夠大，可帶完整脈絡）
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
    callback_top_k: int = 10                          # 最多注入幾條（上限／天花板）
    callback_min_results: int = 5                     # 至少湊幾條：地板內過閘的不足此數時，用「過品質閘但距離超
    #                                                  地板」的最近候選補滿（刻意放寬距離換數量；最終是否引用仍由
    #                                                  模型端「不貼切就忽略」把關）。設 0 = 回到純距離地板、不補。
    callback_candidate_pool: int = 25               # pgvector 先撈幾條再 gate（要 ≥ top_k，過濾/補滿後才有得挑）
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

    # 觸發門檻：插不插由模型判斷，「偶爾」感由冷卻 + 每小時上限保證（不用機率）
    min_chars: int = 4               # 太短（貼圖式單字）不插
    max_chars: int = 300             # 太長（長篇貼文）不插
    # 冷卻＝防洗版的安全網，不再是節拍器（話多話少的主旋鈕改為 hook_threshold）。
    # 300→180：撤掉等鎖上限後節奏全由冷卻決定，300s 會把鉤子閘架空（冷卻期內連鉤子都不看）。
    # 物理下限約 120s——一次生成實測中位 120s、一小時最多 30 次，冷卻低於生成時間會讓隊列越排越長。
    cooldown_seconds: float = 180.0
    hourly_cap: int = 20             # 同頻道每小時自發插話上限（太低會整個小時靜默）
    # per-channel 序列處理：一輪 burst 內最多重評估幾次。3→1：第二輪要再等一次生成（~120s），
    # 講出來已跟現場脫節；靜默期上線後 burst 內的新訊息本來就會被合併進同一次評估。
    max_passes_per_burst: int = 1

    # ── 靜默期（不搶話）：訊息進來不馬上開跑，等對話停一下再擷取完整脈絡 ──
    # 慢節奏的判準是「距最後一則夠久」**且**「沒人正在打字」；typing 是加分訊號，收不到
    # （手機/貼圖/第三方 client）就退化成純時間 debounce。`Intents.default()` 已含 typing。
    quiet_seconds: float = 15.0            # 最後一則訊息後要靜默多久（總延遲已 ~120s，多等不痛）
    typing_grace_seconds: float = 12.0     # 多久沒收到 typing 事件才算「沒人在打」（client 約每 9s 重送）
    quiet_max_wait_seconds: float = 60.0   # 總等待上限：一直有人打字也不能無限等
    quiet_directed_seconds: float = 0.0    # 被 @/reply → 不等，立刻處理

    # ── 熱聊快速通道：慢節奏要「等人講完」，熱絡時「看前面的就可以講」──
    # 熱聊時永遠等不到靜默（一直有人在講、在打字），用同一套規則只會被 max_wait 硬拖，
    # 而那時對話又前進了一段。而且熱聊插話本來就不需要空檔——真人也是直接接話。
    # 判定為熱時：只等一個很短的間隔（避免切在某人連發的中間），並且**忽略 typing**。
    hot_min_messages: int = 5              # 最近幾則拿來判斷節奏
    hot_window_seconds: float = 120.0      # 這幾則落在此秒數內＝熱
    hot_quiet_seconds: float = 3.0         # 熱聊時只等這麼久就開跑

    # ── 接續：它剛講完、有人接話 → 視為半 directed，允許馬上接下去 ──
    # 沒有這個機制的話是「講完就跑」：除非被 @，否則不管別人怎麼回它都要等下一個冷卻週期。
    followup_enabled: bool = True
    # 180→45→90：45 秒實測太緊（51 分鐘內 5 次自發插話，接續一次都沒觸發）。真人看到回覆要
    # 讀、要決定回不回、還要打字；何況它講的是兩分鐘前的話題，對方未必立刻接得上。
    # 收斂靠的是下面那條「發話者必須是它剛才回的那個人」，不是靠把時間壓短。
    followup_window_seconds: float = 90.0
    # 2→1：一來一回就好，別纏著同一個人連講三輪。
    followup_max_chain: int = 1
    # 註：接續還有一道更關鍵的判準寫在 code 裡——**發話者必須是它剛才回的那個人**
    # （見 ambient_reply._is_followup_to_bot）。少了它，「它插完話、群裡繼續聊自己的」也會被
    # 當成有人在接它，實測 15 次插話裡 9 次是這樣來的。
    # 看門狗：單一 pass 超過此秒數視為卡住 → 取消，避免一次生成卡死整個頻道的序列處理。
    # 要夠長以容納冷載入(model load 30-60s)+生成。
    pass_timeout_seconds: float = 180.0
    # 被 @、被回覆時的輸出上限（含思考）：想太久撞到就關掉思考再答一次，點名的人才一定收得到回覆。
    # 要比 180 秒逾時能寫完的量（約 20 token/秒 → 3,400）低，否則永遠是逾時先到、沒有重答的機會；
    # 自發插話不設上限，逾時就略過本來就沒差
    directed_max_tokens: int = 3000
    # （已移除 judge_sampling_rate 純機率減壓閥：隨機丟棄評估會丟掉好時機、留下爛時機，
    #   完全被下面有判斷依據的鉤子閘取代。要降載請調 hook_threshold，不要再加機率閥。）

    # ── 鉤子閘：決定「值不值得花那 ~120s 去想」。不用 LLM，見 llm/ambient/ambient_hooks.py ──
    hook_enabled: bool = True
    # sigmoid 分數門檻；調高＝話少、調低＝話多（話多話少的**主旋鈕**）。
    # 對照現行權重的實際分數（單一鉤子命中）：
    #   什麼都沒命中 0.23｜聊完停頓 0.45｜獨白・對話正熱 0.50｜徵詢 0.52
    #   ｜懸空問句 0.73｜叫名字 0.79　　（可疊加，例如熱聊+停頓＝0.73）
    # 取 0.4 的意義：**任一個鉤子命中就能開口**，只有「完全沒訊號的零星對話」才閉嘴（0.23）。
    hook_threshold: float = 0.4
    hook_explore_rate: float = 0.15  # ε-greedy：無視分數強制放行的比例，專收「鉤子不看好」的樣本。
    # 探索的前提：頻道最近真的有人在。沒人聊天時探索既學不到東西（沒人在，標籤必然是
    # 「沒人接」），又會在死寂的頻道突然冒一句——實測那正是「沒人聊天也硬回」的來源。
    explore_min_messages: int = 5           # 近期至少要有這麼多則
    explore_activity_window_seconds: float = 900.0   # 且第 N 則新於此秒數（15 分鐘）
    hook_knn_enabled: bool = True    # k-NN 特徵：過去語意相近情境下插話被接的比率（一次 embedding）
    hook_knn_top_k: int = 20
    hook_knn_max_distance: float = 0.50
    hook_debug: bool = True          # 把每次鉤子計分的細項寫進 discord_bot.log（調門檻用）

    # 與 /askai 的讓位：foreground 活躍此秒數內，背景插話暫停（防換模型 ping-pong）
    askai_grace_seconds: float = 90.0

    # 模型回此 sentinel（或空字串）代表「沒梗」→ 不發送
    silence_sentinel: str = "[PASS]"

    # ── 被點名罵（llm/ambient/ambient_insult.py；開關是 settings/switches.json 的 ambient_insult_mode）──
    insult_cold_days: int = 7            # 罵過它的人，幾天內不主動接他的話（期間再罵就從那天重算）
    insult_reaction_emoji: str = "sointeresting"   # 按的表情：本伺服器自訂表情的名稱（真有趣・反諷）；找不到用 🙄

    # ── 看圖（ambient 模型需具 vision）──
    image_max_count: int = 9             # 一次請求最多帶幾張圖（含動圖拆出來的幀），硬上限
    image_max_bytes: int = 5 * 1024 * 1024

    # ── Phase C 記憶寫入（preference_fact）──
    extractor_prompt_path: str = prompt_file("preference_extractor_prompt.txt")
    memory_min_confidence: float = 0.6   # 低於此不寫入（寧缺勿濫）
    trusted_promote_at: int = 2          # 不同批次提到達此次數 → tentative 升 trusted（才會被召回）
    memory_flush_threshold: int = 30     # 插話頻道訊息累積達此量觸發一次抽取批次
    memory_recall_top_k: int = 6         # 召回時最多帶幾筆 trusted 偏好
    memory_flush_interval_seconds: float = 180.0  # 背景排程多久檢查一次是否該 flush（閒置才真的跑）
    memory_buffer_max: int = 300         # 記憶緩衝上限，超過丟最舊

    # ── 招牌梗 signature_tag（持久印象層；corroboration + 慢衰減；與 preference_fact 平行）──
    tag_extractor_prompt_path: str = prompt_file("signature_tag_extractor_prompt.txt")
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
    debug_prompt_log_path: str = str(LOGS_DIR / "ambient_prompt.txt")
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


class AskAIChatSearchSettings(BaseSettings):
    """/askai 的聊天紀錄搜尋工具（`llm.retrievers.chat_search`）的細項；開關在 settings/switches.json 的
    `askai_chat_search_mode`。只吃 class 預設值。"""

    #: 怎麼用這個工具的規則：只在真的有工具時接在系統提示詞後面（改檔即生效）
    rules_path: str = prompt_file("askai_chat_search_rules.txt")
    #: 字面模式最多列幾個人、每個人最多列幾個頻道、附幾則原文；原文從最近幾則命中裡挑（整張表照時間排很貴，只排命中的）
    phrase_speakers: int = 5
    phrase_channels: int = 3
    phrase_examples: int = 2
    phrase_scan_rows: int = 300
    #: 語意模式回幾則例句、太短的不算（反應詞撐不起一個印象）
    topic_limit: int = 8
    topic_min_chars: int = 6
    #: 語意模式的統計（「最像的句子裡誰說了幾句」）最多看幾句、距離超過多少就不算像（每則訊息最近的鄰居約 0.2、前十名約 0.25～0.36）
    topic_tally_limit: int = 100
    topic_max_distance: float = 0.5
    #: 每則原文最多給模型幾個字（工具結果也佔 context）
    text_max_chars: int = 160
    #: 字面模式的查詢最多跑幾秒（沒有 trigram 索引時是全表掃描；逾時回錯誤給模型，別讓整個回答卡住）
    statement_timeout_seconds: float = 20.0

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


class AmbientSearchSettings(BaseSettings):
    """插話上網查（`llm.ambient.ambient_search`）的細項；開關在 settings/switches.json 的 `ambient_search_mode`。
    只吃 class 預設值。"""

    #: 每天最多幾次有查的插話（成本在多出來的那一輪模型呼叫）；用完當天不再宣告工具
    daily_limit: int = 30
    #: 一次插話最多查幾輪；同一輪只執行第一個工具呼叫
    max_tool_rounds: int = 1
    #: 插話專用的查詢規則（接在插話 prompt 後面，只在有工具時給；改檔即生效）
    rules_path: str = prompt_file("ambient_search_rules.txt")
    #: 準備情報工具（連 search-mcp 列工具）最多等幾秒：它卡住時不該拖住每一次插話
    intel_prepare_seconds: float = 5.0

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


class PersonaAgentSettings(BaseSettings):
    """人格擷取 agent 的排程設定。

    agent 的完整描述寫自己的表（`persona_agent_versions`），bot 讀不到；發布在 `publish_mode="on"`
    時才把挑過的精簡版寫進 `auto_personality`（見 `llm.persona.agent.publish`）。2026-10-13 起沒有
    production 萃取備援：agent 沒寫到的人維持最後一版描述。

    **只吃 class 預設值，不吃環境變數**（同 `AmbientChatSettings` /
    `DiaryReflectionSettings`）。少了下面那組 `model_config` 的話，欄位名會直接變成
    環境變數名——`ENABLED` 打得開這支排程、`MODE` 改得掉樣本模式，而這種通用名字誰都
    可能撞到；`mode` 又是 `Literal`，compose 隨便來一個 `MODE=production` 就會讓這個類
    建構失敗。開關留在 code 裡，git 也才看得出誰什麼時候開的。
    """

    #: 開啟後才會接上 `discord_bot` 04:00 排程的第 ④ 步（production 跑完才輪到它）。
    enabled: bool = True

    #: sample＝每晚只跑 `sample_size` 人（輪替，最久沒跑的優先）
    #: all   ＝跑所有符合門檻的人
    #: 先 sample 幾晚把剩餘的失敗模式抓出來，穩定後改 all——改設定不必改程式。
    mode: Literal["sample", "all"] = "sample"

    #: **26 是從「兩小時內幾乎不可能被 deadline 截斷」回推的**，不是憑感覺：
    #: 三晚實測平均 270／265／284 秒／人，26 人約 118 分；production 04:15 收工，
    #: agent 06:13 結束，離 07:00 還有 47 分緩衝。最壞情況（每人都跑滿最慢的 339 秒）
    #: 是 169 分，撞到 deadline 也只是把剩下的記 `unrun` 留到明晚，不會失控。
    #:
    #: **為什麼不是 6**：6 人時 68 人的池子要 11 晚才輪完一圈，一週下來會產出
    #: 42 個人的 v1、**零個 v2**——而 agent 的核心假設正是「累積式 diff 會不會越修
    #: 越準」，那一週完全驗不到。26 人輪一圈只要 2.6 晚，一週每人跑 2.7 次，
    #: 廣度（68 人全覆蓋）與深度（v2、v3）同時拿得到。
    #:
    #: 另一個好處是統計：6 個樣本時一個異常值就能歪掉當晚的幻覺率（8/31 那晚
    #: 假證據 5 個，數字直接翻三倍），26 個樣本才撐得起評比。
    #:
    #: 評比決定採用之後再往上調——那時關心的是覆蓋率，不再是版本演化。
    sample_size: int = 26

    #: 硬停時間（本地時；跨過就停手，沒跑到的人明晚優先）。
    #: 實測活躍使用者約 4.4 分／人，56 人約 3.4 小時 → 04:15 開始會跑到 07:40，
    #: 那時群裡開始有人聊天，agent 每步禮讓十分鐘再硬上反而最擾民。
    deadline_hour: int = 7

    #: 發布：把精簡版寫進 `auto_personality` 給插話／askai 讀（04:00 排程的第 ⑤ 步，見
    #: `llm.persona.agent.publish`）。off＝不做；dry_run＝只算、寫 log，不寫入——上線前先看
    #: 挑出來的東西對不對；on＝寫入。
    #: `enabled` 關掉時一律當 off（`publish.effective_publish_mode`）：沒有新版本可發布。
    publish_mode: Literal["off", "dry_run", "on"] = "on"

    #: 納入門檻。**刻意比 production 寬**（production 是 14 天 10 則）：
    #: 14 天 <10 則的人 production 直接跳過，而那正是 agent 唯一明確贏的族群
    #: （實測 7 天 1 則、90 天 91 則的案例，agent 自行擴大回溯後產出零幻覺的完整描述）。
    min_messages_days: int = 90
    min_messages: int = 5

    model_config = SettingsConfigDict(
        # siblings 用 extra="ignore" 是因為它們讀 `.env`——env_file 會把整份檔案的 key
        # 全餵進來，forbid 會被無關的 key 炸掉。這個類不讀 `.env`，所以維持 forbid：
        # 測試會用 `PersonaAgentSettings(mode="all")` 這種 kwargs 建構，打錯字要噴錯。
        extra="forbid",
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
    identity_path: str = prompt_file("persona_identity.txt")
    guardrails_path: str = prompt_file("persona_guardrails.txt")
    prompt_path: str = prompt_file("diary_reflection_prompt.txt")

    # 排程（台北時區）：每天幾點寫日記
    schedule_hour: int = 0
    schedule_minute: int = 0

    # 回顧範圍：過去幾小時、最多取幾則、每則截斷長度
    lookback_hours: int = 24
    max_messages: int = 180
    max_chars_per_msg: int = 200
    # 把回顧視窗切成幾個等長時段平均取樣（避免只抓到深夜那段、早上中午被截掉）
    transcript_buckets: int = 6

    # 生成：model=None 用 ambient_model；think=None 用後端預設；日記長度上限（post 前安全截）
    model: str | None = None
    think: bool | None = None
    max_diary_chars: int = 1500

    # debug 觀測
    debug_log: bool = True
    debug_prompt_log_path: str = str(LOGS_DIR / "diary_prompt.txt")
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



class EmojiAutofillSettings(BaseSettings):
    """看到沒描述的表情或貼圖時，背景讓模型看圖補字典（`llm.preprocess.emoji_autofill`）。

    補哪些：別的伺服器的表情與貼圖、本伺服器表情字典裡空白或只有類別字的行；使用者寫過的描述不動。
    每個只看一次（寫進字典就查得到），沒出現過的不處理。只吃 class 預設值，理由同 `PersonaAgentSettings`。
    """

    #: off＝不做；dry_run＝看圖、寫 log，不寫檔（改 prompt 後想先抽查時用）；on＝寫入字典
    #: 2026-10-02 使用者同意直接正式寫入（實測 10 個有 4 個偏，偏的由使用者看到再改，AI 不會再動）
    mode: Literal["off", "dry_run", "on"] = "on"

    #: 每天最多看幾張（含失敗與看不出來的）。近 30 天別的伺服器的表情 168 種，平均一天不到 6 種新的
    daily_limit: int = 30
    #: 看不出來、失敗、或試跑看過的，隔多久才再看同一個
    retry_hours: int = 24
    #: 04:00 維護（人格萃取、persona agent）在用模型，這段時間不跑；錯過的下次被看到再補
    quiet_start: str = "04:00"
    quiet_end: str = "07:30"

    #: 描述長度上限（字典檔頭的填寫指南寫 5～15 字）
    max_description_chars: int = 15
    #: 給模型看的訊息每則截斷長度
    max_context_chars: int = 200

    prompt_path: str = prompt_file("emoji_autofill_prompt.txt")
    #: 每天第一次改寫字典前備份到這裡，各保留 `backup_keep` 份
    backup_dir: str = str(LOGS_DIR / "dictionary_backup")
    backup_keep: int = 14

    #: 逾時就當這次失敗（下次被看到、過了 `retry_hours` 再試）。不另設 context 長度：
    #: 有的後端換 context 長度要重載模型，會拖慢插話
    timeout_seconds: int = 120

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


def _parse_llm_runtime_config(raw: str) -> LLMRuntimeConfig:
    content = raw.strip()
    if not content:
        raise ValueError("LLM runtime config 檔案為空")
    raw_data = json.loads(content)
    if not isinstance(raw_data, dict):
        raise ValueError("LLM runtime config 內容必須為 JSON object")
    return LLMRuntimeConfig.model_validate(raw_data)


def load_llm_runtime_config(path: str | Path) -> LLMRuntimeConfig:
    """讀取 LLM 執行時設定（哪個後端、哪個模型、embedding 模型）。

    走 `utils.hot_files` 的機制：檔案修改時間沒變就回上次解析的結果，改檔即生效；改壞了沿用上次的好內容（hot_files
    會記錯誤）。十幾個地方每次用到都呼叫這裡，所以不能每次都重讀重驗。缺檔、或從來沒有成功讀過一次（例如一開始就是壞的）
    就拋錯：這些設定沒有合理的預設值。回傳的物件是共用的，呼叫端不要改它。
    """
    from utils.hot_files import read_parsed

    runtime_config = read_parsed(path, parse=_parse_llm_runtime_config, label="LLM runtime config")
    if runtime_config is None:
        raise RuntimeError(f"無法載入 LLM runtime config: {path}")   # 缺檔，或從沒成功讀過一次
    return runtime_config
