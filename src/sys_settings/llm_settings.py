"""LLM 系統級設定模型與載入工具。"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Tuple
from urllib.parse import quote_plus

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("discord_bot")


class LLMServiceSettings(BaseSettings):
    """Ollama 服務層設定（可由 env/dotenv 覆寫）。"""

    ollama_base_url: str = Field(
        default="http://192.168.56.1:11434",
        validation_alias="OLLAMA_BASE_URL",
    )
    ollama_model: str = Field(
        default="ministral-3:14b",
        validation_alias="OLLAMA_MODEL",
    )
    ollama_timeout: int = Field(
        default=300,
        validation_alias="OLLAMA_TIMEOUT",
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
    ollama_runtime_model_path: str = Field(
        default="/app/sys_settings/ollama_runtime_config.json",
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


class OllamaRuntimeConfig(BaseModel):
    """Ollama 執行時可熱更新設定。"""

    model: str
    embed_model: str
    moderation_model: str | None = None
    think: bool = True


class AskAICommandSettings(BaseSettings):
    """/askai 指令相關設定（集中常數來源，不使用 env 覆寫）。"""

    max_context_messages: int = 100
    max_context_to_send: int = 20
    min_recent_context: int = 15
    max_relevant_context: int = 14
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


def load_ollama_runtime_config(path: str | Path) -> OllamaRuntimeConfig:
    """讀取 Ollama 執行時設定（嚴格模式：缺檔或缺值直接拋錯）。"""
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

        return OllamaRuntimeConfig.model_validate(raw_data)
    except Exception as exc:
        logger.error("載入 ollama runtime config 失敗（嚴格模式）: %s", exc)
        raise RuntimeError(f"無法載入 ollama runtime config: {runtime_path}") from exc
