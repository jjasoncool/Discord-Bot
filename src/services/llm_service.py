"""
Ollama LLM 服務模組
提供與 Ollama API 的非同步互動封裝
"""
from __future__ import annotations

import logging
import json
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional

import aiohttp
from sys_settings.llm_settings import (
    LLMServiceSettings,
    load_context_safety_rules,
    load_ollama_runtime_config,
)

logger = logging.getLogger("discord_bot")

LLM_SERVICE_SETTINGS = LLMServiceSettings()


@dataclass(frozen=True)
class PromptBundle:
    """同源 prompt 組裝結果：API payload 與可讀記錄。"""

    messages: list[dict[str, object]]
    prompt_record_log: str


class OllamaService:
    """Ollama LLM 服務封裝"""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> None:
        self.settings = LLM_SERVICE_SETTINGS
        self.base_url = base_url or self.settings.ollama_base_url
        self.model_default = model or self.settings.ollama_model
        self.timeout = timeout if timeout is not None else self.settings.ollama_timeout
        self.context_safety_rules = load_context_safety_rules(self.settings.llm_context_safety_rules_path)
        self._runtime_model_cached_value: Optional[str] = None
        self._runtime_model_cached_mtime_ns: Optional[int] = None

    def _load_runtime_model_from_file(self) -> Optional[str]:
        """以 mtime 快取 runtime model，降低每次請求都讀檔的成本。"""
        runtime_config_path = Path(self.settings.ollama_runtime_model_path)

        try:
            if not runtime_config_path.exists():
                self._runtime_model_cached_value = None
                self._runtime_model_cached_mtime_ns = None
                return None

            stat_result = runtime_config_path.stat()
            current_mtime_ns = stat_result.st_mtime_ns

            if (
                self._runtime_model_cached_mtime_ns == current_mtime_ns
                and self._runtime_model_cached_value
            ):
                return self._runtime_model_cached_value

            raw_content = runtime_config_path.read_text(encoding="utf-8").strip()
            runtime_model_from_file: Optional[str] = None
            if raw_content:
                runtime_config = load_ollama_runtime_config(runtime_config_path)
                candidate = runtime_config.model.strip()
                if candidate:
                    runtime_model_from_file = candidate

            self._runtime_model_cached_value = runtime_model_from_file
            self._runtime_model_cached_mtime_ns = current_mtime_ns
            return runtime_model_from_file
        except Exception as exc:
            logger.warning("讀取 runtime model 檔案失敗: %s", exc)
            return None

    def _resolve_runtime_model(self, override_model: Optional[str] = None) -> str:
        """解析本次請求模型：call override > runtime file > 預設。"""
        request_override = (override_model or "").strip()
        if request_override:
            return request_override

        runtime_model = self._load_runtime_model_from_file()
        if runtime_model:
            return runtime_model

        return self.model_default

    def _serialize_context_items(self, items: List[dict[str, str]]) -> str:
        """將 context 安全序列化為 JSON 字串，避免標記邊界被輸入破壞。"""
        safe_items: list[dict[str, object]] = []
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue

            role = str(item.get("role", "user"))
            content = str(item.get("content", "")).replace("\x00", "")
            metadata = {
                str(k): str(v)
                for k, v in item.items()
                if k not in {"role", "content"} and v is not None
            }
            safe_items.append(
                {
                    "index": idx,
                    "role": role,
                    "content": content,
                    "metadata": metadata,
                }
            )
        return json.dumps(safe_items, ensure_ascii=False)

    def _build_prompt_bundle(
        self,
        *,
        system: Optional[str],
        user_query_text: str,
        context_items: Optional[List[dict[str, str]]] = None,
        images: Optional[List[str]] = None,
    ) -> PromptBundle:
        """建立同源 prompt bundle（給 Ollama 與給 log 共用）。"""
        composed_user_prompt = ""
        if context_items:
            serialized_context = self._serialize_context_items(context_items)
            composed_user_prompt += (
                f"{self.context_safety_rules.untrusted_context_intro}\n"
                f"{self.settings.context_open_tag}\n"
                f"{serialized_context}\n"
                f"{self.settings.context_close_tag}\n\n"
            )

        if images:
            composed_user_prompt += (
                "<image_instruction>\n"
                f"{self.context_safety_rules.image_instruction_prompt}\n"
                "</image_instruction>\n"
            )

        composed_user_prompt += (
            f"{self.settings.latest_open_tag}\n"
            f"{user_query_text}\n"
            f"{self.settings.latest_close_tag}"
        )

        messages: list[dict[str, object]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append(
            {
                "role": "system",
                "content": self.context_safety_rules.system_safety_prompt,
            }
        )

        user_message: dict[str, object] = {"role": "user", "content": composed_user_prompt}
        if images:
            user_message["images"] = images
        messages.append(user_message)

        parts: list[str] = []
        if system:
            parts.extend(["<system>", system])
        parts.extend(["<system_safety>", self.context_safety_rules.system_safety_prompt])
        parts.extend(["<user_message>", composed_user_prompt])
        prompt_record_log = "\n".join(parts)
        return PromptBundle(messages=messages, prompt_record_log=prompt_record_log)

    async def generate_reply(
        self,
        prompt: str,
        system: Optional[str] = None,
        context_items: Optional[List[dict[str, str]]] = None,
        images: Optional[List[str]] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        repeat_penalty: Optional[float] = None,
        num_ctx: Optional[int] = None,
    ) -> tuple[str, str]:
        """呼叫 Ollama 並回傳 (reply, prompt_record_log)。"""
        temperature = (
            temperature
            if temperature is not None
            else self.settings.default_temperature
        )
        top_p = top_p if top_p is not None else self.settings.default_top_p
        repeat_penalty = (
            repeat_penalty
            if repeat_penalty is not None
            else self.settings.default_repeat_penalty
        )
        num_ctx = num_ctx if num_ctx is not None else self.settings.default_num_ctx

        user_query_text = prompt
        bundle = self._build_prompt_bundle(
            system=system,
            user_query_text=user_query_text,
            context_items=context_items,
            images=images,
        )

        target_model = self._resolve_runtime_model(model)
        payload = {
            "model": target_model,
            "messages": bundle.messages,
            "options": {
                "temperature": temperature,
                "top_p": top_p,
                "repeat_penalty": repeat_penalty,
                "num_ctx": num_ctx,
            },
            "stream": False,
        }

        url = f"{self.base_url}/api/chat"
        try:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload) as response:
                    if response.status != 200:
                        detail = await response.text()
                        logger.error("Ollama 回應失敗: %s - %s", response.status, detail)
                        return "⚠️ LLM 回應失敗，請稍後再試。", bundle.prompt_record_log

                    data = await response.json()
                    message = data.get("message", {})
                    content = message.get("content")
                    if not content:
                        logger.error("Ollama 回應格式異常: %s", data)
                        return "⚠️ LLM 回應格式異常，請稍後再試。", bundle.prompt_record_log
                    return content, bundle.prompt_record_log

        except aiohttp.ClientError as exc:
            logger.error("Ollama 連線失敗: %s", exc)
            return "⚠️ 無法連線到 LLM 服務。", bundle.prompt_record_log
        except Exception as exc:
            logger.error("Ollama 呼叫發生未預期錯誤: %s", exc, exc_info=True)
            return "⚠️ LLM 發生未預期錯誤。", bundle.prompt_record_log
