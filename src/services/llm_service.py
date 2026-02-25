"""
Ollama LLM 服務模組
提供與 Ollama API 的非同步互動封裝
"""
from __future__ import annotations

import os
import logging
from typing import List, Dict, Optional

import aiohttp
from dotenv import load_dotenv

logger = logging.getLogger("discord_bot")

DEFAULT_BASE_URL = "http://192.168.56.1:11434"
DEFAULT_MODEL = "gemma3:12b"
DEFAULT_TIMEOUT = 180


class OllamaService:
    """Ollama LLM 服務封裝"""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        load_dotenv()
        self.base_url = base_url or os.getenv("OLLAMA_BASE_URL", DEFAULT_BASE_URL)
        self.model = model or os.getenv("OLLAMA_MODEL", DEFAULT_MODEL)
        self.timeout = timeout

    async def generate_reply(
        self,
        prompt: str,
        system: Optional[str] = None,
        context: Optional[List[Dict[str, str]]] = None,
        images: Optional[List[str]] = None,
        temperature: float = 0.7,
        top_p: float = 0.9,
    ) -> str:
        """使用 Ollama 產生回覆

        Args:
            prompt: 使用者輸入
            system: 系統提示詞
            context: 對話上下文（role/content 格式）
            temperature: 取樣溫度
            top_p: nucleus sampling
        """
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        if context:
            messages.extend(context)
        user_message = {"role": "user", "content": prompt}
        if images:
            user_message["images"] = images
        messages.append(user_message)

        payload = {
            "model": self.model,
            "messages": messages,
            "options": {
                "temperature": temperature,
                "top_p": top_p,
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
