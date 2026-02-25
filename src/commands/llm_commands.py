import logging
from pathlib import Path
import asyncio
from datetime import timezone, timedelta
import discord
from discord import app_commands
from discord.ext import commands

import llm
from services.llm_service import OllamaService
from utils.utils import safe_send_interaction_message, check_guild

logger = logging.getLogger("discord_bot")


MAX_CONTEXT_MESSAGES = 50
MAX_CONTEXT_TO_SEND = 20
MIN_RECENT_CONTEXT = 6
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
ASKAI_QUEUE = asyncio.Queue()


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


class LLMCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.llm_service = OllamaService()
        self._askai_worker_task: asyncio.Task | None = None

    def _ensure_askai_worker(self) -> None:
        if self._askai_worker_task is None or self._askai_worker_task.done():
            self._askai_worker_task = asyncio.create_task(self._askai_worker())

    @app_commands.command(name="askai", description="向 AI 詢問問題")
    @app_commands.describe(question="想問 AI 的問題")
    @app_commands.checks.dynamic_cooldown(askai_cooldown)
    async def askai_cmd(self, interaction: discord.Interaction, question: str):
        """斜線命令：向 AI 詢問問題"""
        logger.info(f"收到 /askai：user={interaction.user} question={question[:200]}")

        if not await check_guild(interaction):
            return

        self._ensure_askai_worker()

        loop = asyncio.get_running_loop()
        completion = loop.create_future()
        queue_item = (interaction, question, completion)
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
            interaction, question, completion = await ASKAI_QUEUE.get()
            try:
                await self._handle_askai_request(interaction, question)
                if not completion.done():
                    completion.set_result(True)
            except Exception as exc:
                logger.error("/askai 排隊處理失敗: %s", exc, exc_info=True)
                if not completion.done():
                    completion.set_exception(exc)
            finally:
                ASKAI_QUEUE.task_done()

    async def _handle_askai_request(self, interaction: discord.Interaction, question: str):
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

        reply = await self.llm_service.generate_reply(
            question,
            system=system_prompt,
            context=context if context else None,
            temperature=0.35,
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

        # 使用 followup 回覆以避免互動超時
        response_text = (
            f"{interaction.user.mention}\n"
            f"❓ **問題：** {question}\n"
            f"💬 **回答：** {reply}"
        )

        await interaction.followup.send(
            content=response_text,
            allowed_mentions=discord.AllowedMentions(users=[interaction.user])
        )


async def setup(bot):
    await bot.add_cog(LLMCommands(bot))
