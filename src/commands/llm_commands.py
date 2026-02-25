import logging
from pathlib import Path
import asyncio
import json
from datetime import datetime, timezone, timedelta
import base64
import discord
from discord import app_commands
from discord.ext import commands

import llm
from services.llm_service import OllamaService
from utils.utils import safe_send_interaction_message, check_guild

logger = logging.getLogger("discord_bot")


MAX_CONTEXT_MESSAGES = 50
MAX_CONTEXT_TO_SEND = 20
MIN_RECENT_CONTEXT = 15
MAX_RELEVANT_CONTEXT = 14
TAIPEI_TZ = timezone(timedelta(hours=8))
DISCORD_CONTEXT_BEGIN = "[context:discord_chat_begin]"
DISCORD_CONTEXT_END = "[context:discord_chat_end]"
RAG_CONTEXT_BEGIN = "[context:rag_begin]"
RAG_CONTEXT_END = "[context:rag_end]"
DEFAULT_SYSTEM_PROMPT = (
    "你是 Discord 群組中的一位群友，請用自然口吻聊天。"
    "回覆時只能使用繁體中文，避免使用英文或簡體中文。"
)
PROMPT_FILE_PATH = Path("/app/settings/prompts/askai_system_prompt.txt")
PROMPT_LOG_PATH = Path("/logs/askai_prompt.txt")
RESPONSE_LOG_PATH = Path("/logs/askai_response_history.jsonl")
ASKAI_QUEUE = asyncio.Queue()
MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024


def load_system_prompt() -> str:
    """從檔案載入可維護的 system prompt，找不到則使用預設值。"""
    try:
        if PROMPT_FILE_PATH.exists():
            content = PROMPT_FILE_PATH.read_text(encoding="utf-8").strip()
            if content:
                return content
        logger.warning("找不到或讀不到 prompt 檔案，改用預設 SYSTEM PROMPT: %s", PROMPT_FILE_PATH)
    except Exception as exc:
        logger.warning("載入 prompt 檔案失敗，改用預設 SYSTEM PROMPT: %s", exc)
    return DEFAULT_SYSTEM_PROMPT


def askai_cooldown(interaction: discord.Interaction):
    """管理員免冷卻、一般成員 5 分鐘一次"""
    if interaction.guild and interaction.user.guild_permissions.administrator:
        return None
    return app_commands.Cooldown(1, 300.0)


def append_askai_response_log(
    *,
    interaction: discord.Interaction,
    question: str,
    reply: str,
    discord_meta: dict[str, int],
    rag_meta: dict[str, int | bool],
) -> None:
    """將每次 askai 的輸入/輸出與必要統計 append 到 jsonl，供後續觀察改善。"""
    guild_id = interaction.guild.id if interaction.guild else None
    channel_id = interaction.channel.id if interaction.channel else None
    author_name = getattr(interaction.user, "display_name", interaction.user.name)

    record = {
        "time": datetime.now(TAIPEI_TZ).isoformat(),
        "guild_id": guild_id,
        "channel_id": channel_id,
        "user_id": interaction.user.id,
        "username": author_name,
        "question": question,
        "reply": reply,
        "discord_context_meta": discord_meta,
        "rag_context_meta": rag_meta,
    }

    RESPONSE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with RESPONSE_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


class LLMCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.llm_service = OllamaService()
        self._askai_worker_task: asyncio.Task | None = None

    def _ensure_askai_worker(self) -> None:
        if self._askai_worker_task is None or self._askai_worker_task.done():
            self._askai_worker_task = asyncio.create_task(self._askai_worker())

    @app_commands.command(name="askai", description="向 AI 詢問問題")
    @app_commands.describe(question="想問 AI 的問題", image="可選的圖片（支援 jpg/png/webp）")
    @app_commands.checks.dynamic_cooldown(askai_cooldown)
    async def askai_cmd(
        self,
        interaction: discord.Interaction,
        question: str,
        image: discord.Attachment | None = None,
    ):
        """斜線命令：向 AI 詢問問題"""
        logger.info(f"收到 /askai：user={interaction.user} question={question[:200]}")

        if not await check_guild(interaction):
            return

        self._ensure_askai_worker()

        loop = asyncio.get_running_loop()
        completion = loop.create_future()
        queue_item = (interaction, question, image, completion)
        await ASKAI_QUEUE.put(queue_item)
        queue_size = ASKAI_QUEUE.qsize()
        await safe_send_interaction_message(
            interaction,
            f"🧾 已加入 AI 排隊（目前排隊人數：{queue_size}）。請稍候...",
            ephemeral=True
        )

        await completion

    async def _askai_worker(self) -> None:
        while True:
            interaction, question, image, completion = await ASKAI_QUEUE.get()
            try:
                await self._handle_askai_request(interaction, question, image)
                if not completion.done():
                    completion.set_result(True)
            except Exception as exc:
                logger.error("/askai 排隊處理失敗: %s", exc, exc_info=True)
                if not completion.done():
                    completion.set_exception(exc)
            finally:
                ASKAI_QUEUE.task_done()

    async def _handle_askai_request(
        self,
        interaction: discord.Interaction,
        question: str,
        image: discord.Attachment | None,
    ):
        """實際處理 AI 回覆流程（在隊列鎖內執行）"""
        system_prompt = load_system_prompt()

        await interaction.followup.send(
            "🔄 AI 思考中，請耐心等候...",
            ephemeral=True
        )

        discord_context, discord_meta = await llm.retrieve_discord_context(
            interaction,
            question,
            max_context_messages=MAX_CONTEXT_MESSAGES,
            min_recent_context=MIN_RECENT_CONTEXT,
            max_relevant_context=MAX_RELEVANT_CONTEXT,
            max_context_to_send=MAX_CONTEXT_TO_SEND,
            taipei_tz=TAIPEI_TZ,
            logger=logger,
        )
        rag_context, rag_meta = await llm.retrieve_rag_context(question)
        context = [*discord_context, *rag_context]

        image_payload = None
        if image:
            image_payload = await self._prepare_image_payload(interaction, image)
            if image_payload is None:
                return

        reply = await self.llm_service.generate_reply(
            question,
            system=system_prompt,
            context=context if context else None,
            images=image_payload,
            temperature=0.7,
            top_p=0.8,
        )

        try:
            prompt_log_text = llm.build_askai_prompt_log(
                system_prompt=system_prompt,
                question=question,
                discord_context=discord_context,
                rag_context=rag_context,
                discord_meta=discord_meta,
                rag_meta=rag_meta,
                max_context_messages=MAX_CONTEXT_MESSAGES,
                discord_context_begin=DISCORD_CONTEXT_BEGIN,
                discord_context_end=DISCORD_CONTEXT_END,
                rag_context_begin=RAG_CONTEXT_BEGIN,
                rag_context_end=RAG_CONTEXT_END,
            )
            PROMPT_LOG_PATH.write_text(prompt_log_text, encoding="utf-8")
        except Exception as exc:
            logger.warning("寫入 askai prompt 失敗: %s", exc)

        try:
            append_askai_response_log(
                interaction=interaction,
                question=question,
                reply=reply,
                discord_meta=discord_meta,
                rag_meta=rag_meta,
            )
        except Exception as exc:
            logger.warning("寫入 askai response history 失敗: %s", exc)

        # 使用 followup 回覆以避免互動超時
        response_lines = [
            f"{interaction.user.mention}",
            f"❓ **問題：** {question}",
            f"💬 **回答：** {reply}",
        ]
        if image and image.url:
            response_lines.append(f"🖼️ **圖片：** {image.url}")
        response_text = "\n".join(response_lines)

        await interaction.followup.send(
            content=response_text,
            allowed_mentions=discord.AllowedMentions(users=[interaction.user])
        )

    async def _prepare_image_payload(
        self,
        interaction: discord.Interaction,
        image: discord.Attachment,
    ) -> list[str] | None:
        """下載並轉換圖片為 Ollama 可接受的 base64 清單。"""
        filename = (image.filename or "").lower()
        allowed_ext = (".jpg", ".jpeg", ".png", ".webp")
        if not filename.endswith(allowed_ext):
            await interaction.followup.send(
                "⚠️ 目前僅支援 jpg/png/webp 圖片，gif 不支援。",
                ephemeral=True,
            )
            return None

        if image.size and image.size > MAX_IMAGE_SIZE_BYTES:
            await interaction.followup.send(
                "⚠️ 圖片大小超過 10MB，請縮圖或換小一點的檔案。",
                ephemeral=True,
            )
            return None

        try:
            image_bytes = await image.read()
        except Exception as exc:
            logger.warning("讀取圖片失敗: %s", exc)
            await interaction.followup.send(
                "⚠️ 圖片讀取失敗，請重新上傳。",
                ephemeral=True,
            )
            return None

        if not image_bytes:
            await interaction.followup.send(
                "⚠️ 圖片內容為空，請重新上傳。",
                ephemeral=True,
            )
            return None

        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        return [image_b64]


async def setup(bot):
    await bot.add_cog(LLMCommands(bot))
