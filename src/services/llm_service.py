"""
Ollama LLM 服務模組
提供與 Ollama API 的非同步互動封裝
"""
from __future__ import annotations

import logging
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
        self._runtime_think_cached_value: Optional[bool] = None

    def _load_runtime_config_cached(self) -> bool:
        """在 service 層讀取並快取 runtime config。"""
        runtime_config_path = Path(self.settings.ollama_runtime_model_path)

        try:
            if not runtime_config_path.exists():
                self._runtime_model_cached_value = None
                self._runtime_model_cached_mtime_ns = None
                self._runtime_think_cached_value = None
                return False

            current_mtime_ns = runtime_config_path.stat().st_mtime_ns
            if (
                self._runtime_model_cached_mtime_ns == current_mtime_ns
                and self._runtime_model_cached_value is not None
                and self._runtime_think_cached_value is not None
            ):
                return True

            runtime_config = load_ollama_runtime_config(runtime_config_path)
            candidate_model = runtime_config.model.strip()

            if not candidate_model:
                self._runtime_model_cached_value = None
                self._runtime_think_cached_value = None
                self._runtime_model_cached_mtime_ns = None
                return False

            self._runtime_model_cached_value = candidate_model or None
            self._runtime_think_cached_value = runtime_config.think
            self._runtime_model_cached_mtime_ns = current_mtime_ns
            return True
        except Exception as exc:
            logger.warning("讀取 runtime config 失敗: %s", exc)
            return False

    def _load_runtime_model_from_file(self) -> Optional[str]:
        """回傳 runtime config 中的 model，並沿用 service 內快取。"""
        if not self._load_runtime_config_cached():
            return None
        return self._runtime_model_cached_value

    def _load_runtime_think_from_file(self) -> Optional[bool]:
        """回傳 runtime config 中的 think，並沿用 service 內快取。"""
        if not self._load_runtime_config_cached():
            return None
        return self._runtime_think_cached_value

    def _resolve_runtime_model(self, override_model: Optional[str] = None) -> str:
        """解析本次請求模型：call override > runtime file > 預設。"""
        request_override = (override_model or "").strip()
        if request_override:
            return request_override

        runtime_model = self._load_runtime_model_from_file()
        if runtime_model:
            return runtime_model

        return self.model_default

    def resolve_request_model(self, override_model: Optional[str] = None) -> str:
        """對外提供本次請求最終模型名稱（供記錄/觀測使用）。"""
        return self._resolve_runtime_model(override_model)

    def resolve_request_think(self, override_think: Optional[bool] = None) -> bool:
        """對外提供本次請求最終 think 設定（供記錄/觀測使用）。"""
        if override_think is not None:
            return bool(override_think)

        runtime_think = self._load_runtime_think_from_file()
        if runtime_think is not None:
            return runtime_think

        return True

    @staticmethod
    def _sanitize_text(text: str) -> str:
        """移除可能破壞標記邊界的字元。"""
        return text.replace("\x00", "")

    def _build_prompt_bundle(
        self,
        *,
        system: Optional[str],
        user_query_text: str,
        chat_context: Optional[List[str]] = None,
        bot_history: Optional[List[str]] = None,
        persona_context: Optional[List[str]] = None,
        images: Optional[List[str]] = None,
    ) -> PromptBundle:
        """建立同源 prompt bundle（給 Ollama 與給 log 共用）。

        chat_context: 純文字聊天記錄（每則一個字串，例如 "[14:30] 老哥: 昨天抽卡又保底了"）
        bot_history: Bot 自身先前的回覆（獨立於 chat_history 額度外）
        persona_context: 自然語言人物描述（每人一個字串，例如 "「老哥」— 群裡的非酋代表"）
        """
        composed_user_prompt = ""

        has_context = bool(chat_context or bot_history or persona_context)
        if has_context:
            composed_user_prompt += (
                f"{self.context_safety_rules.untrusted_context_intro}\n\n"
            )

        if chat_context:
            composed_user_prompt += "<chat_history>\n"
            for line in chat_context:
                composed_user_prompt += f"{self._sanitize_text(line)}\n"
            composed_user_prompt += "</chat_history>\n\n"

        if bot_history:
            composed_user_prompt += "<bot_history>\n"
            for line in bot_history:
                composed_user_prompt += f"{self._sanitize_text(line)}\n"
            composed_user_prompt += "</bot_history>\n\n"

        if persona_context:
            composed_user_prompt += "<member_profiles>\n"
            for line in persona_context:
                composed_user_prompt += f"{self._sanitize_text(line)}\n"
            composed_user_prompt += "</member_profiles>\n\n"

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
        system_parts: list[str] = []
        if system:
            system_parts.append(system)
        system_parts.append(self.context_safety_rules.system_safety_prompt)
        messages.append({"role": "system", "content": "\n\n".join(system_parts)})

        user_message: dict[str, object] = {"role": "user", "content": composed_user_prompt}
        if images:
            user_message["images"] = images
        messages.append(user_message)

        parts: list[str] = []
        if system:
            parts.extend(["<system>", system, "", self.context_safety_rules.system_safety_prompt])
        else:
            parts.extend(["<system>", self.context_safety_rules.system_safety_prompt])
        parts.extend(["<user_message>", composed_user_prompt])
        prompt_record_log = "\n".join(parts)
        return PromptBundle(messages=messages, prompt_record_log=prompt_record_log)

    async def generate_reply(
        self,
        prompt: str,
        system: Optional[str] = None,
        chat_context: Optional[List[str]] = None,
        bot_history: Optional[List[str]] = None,
        persona_context: Optional[List[str]] = None,
        images: Optional[List[str]] = None,
        model: Optional[str] = None,
        think: Optional[bool] = None,
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
            chat_context=chat_context,
            bot_history=bot_history,
            persona_context=persona_context,
            images=images,
        )

        target_model = self._resolve_runtime_model(model)
        target_think = self.resolve_request_think(think)
        payload = {
            "model": target_model,
            "messages": bundle.messages,
            "think": target_think,
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
