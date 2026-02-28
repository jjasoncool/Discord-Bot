"""
Ollama LLM 服務模組
提供與 Ollama API 的非同步互動封裝
"""
from __future__ import annotations

import logging
import json
from pathlib import Path
from typing import List, Optional

import aiohttp
from sys_settings.llm_settings import LLMServiceSettings, load_context_safety_rules

logger = logging.getLogger("discord_bot")

LLM_SERVICE_SETTINGS = LLMServiceSettings()


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
                raw_data = json.loads(raw_content)
                if isinstance(raw_data, dict):
                    candidate = str(raw_data.get("model", "")).strip()
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
    ) -> str:
        """使用 Ollama 產生回覆

        Args:
            prompt: 使用者輸入
            system: 系統提示詞
            context_items: 結構化上下文（非可信資料）
            images: 圖片 Base64 列表
            model: 本次呼叫覆蓋模型（可選）
            temperature: 取樣溫度（None 時使用系統設定預設值）
            top_p: nucleus sampling（None 時使用系統設定預設值）
            repeat_penalty: 重複懲罰參數（None 時使用系統設定預設值）
            num_ctx: 上下文視窗大小（None 時使用系統設定預設值）
        """
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

        messages = []
        if system:
            messages.append({"role": "system", "content": system})

        # 固定安全規則：要求模型把歷史資料視為非可信內容，不得覆寫系統規則
        messages.append(
            {
                "role": "system",
                "content": self.context_safety_rules.system_safety_prompt,
            }
        )

        def _serialize_context(items: List[dict[str, str]]) -> str:
            """將 context 安全序列化為 JSON 字串，避免標記邊界被使用者輸入破壞。"""
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

        # 在 Service 層負責把 context 與 prompt 安全地組裝起來
        final_user_content = ""
        if context_items:
            serialized_context = _serialize_context(context_items)
            final_user_content += (
                f"{self.context_safety_rules.untrusted_context_intro}\n"
                f"{self.settings.context_open_tag}\n"
                f"{serialized_context}\n"
                f"{self.settings.context_close_tag}\n\n"
            )

        # 明確標示出最新使用者的問題
        final_user_content += (
            f"{self.settings.latest_open_tag}\n"
            f"{prompt}\n"
            f"{self.settings.latest_close_tag}"
        )

        user_message = {"role": "user", "content": final_user_content}
        if images:
            user_message["images"] = images

        messages.append(user_message)

        target_model = self._resolve_runtime_model(model)
        payload = {
            "model": target_model,
            "messages": messages,
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
                        return "⚠️ LLM 回應失敗，請稍後再試。"

                    data = await response.json()
                    message = data.get("message", {})
                    content = message.get("content")
                    if not content:
                        logger.error("Ollama 回應格式異常: %s", data)
                        return "⚠️ LLM 回應格式異常，請稍後再試。"
                    return content

        except aiohttp.ClientError as exc:
            logger.error("Ollama 連線失敗: %s", exc)
            return "⚠️ 無法連線到 LLM 服務。"
        except Exception as exc:
            logger.error("Ollama 呼叫發生未預期錯誤: %s", exc, exc_info=True)
            return "⚠️ LLM 發生未預期錯誤。"


async def quick_reply(prompt: str) -> str:
    """簡易單次呼叫（無上下文）"""
    service = OllamaService()
    return await service.generate_reply(prompt)
