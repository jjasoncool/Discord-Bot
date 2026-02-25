import logging
from pathlib import Path
import asyncio
import re
from datetime import timezone, timedelta
import discord
from discord import app_commands
from discord.ext import commands

from services.llm_service import OllamaService
from utils.utils import safe_send_interaction_message, check_guild

logger = logging.getLogger("discord_bot")


MAX_CONTEXT_MESSAGES = 50
MAX_CONTEXT_TO_SEND = 20
MIN_RECENT_CONTEXT = 6
TAIPEI_TZ = timezone(timedelta(hours=8))
DEFAULT_SYSTEM_PROMPT = (
    "你是 Discord 群組中的一位群友，請用自然口吻聊天。"
    "回覆時只能使用繁體中文，避免使用英文或簡體中文。"
)
PROMPT_FILE_PATH = Path("/app/settings/prompts/askai_system_prompt.txt")
PROMPT_LOG_PATH = Path("/logs/askai_prompt.txt")
ASKAI_QUEUE = asyncio.Queue()


def _tokenize_for_relevance(text: str) -> set[str]:
    """簡易分詞：中英數混合，供關聯度判斷使用。"""
    tokens = set(re.findall(r"[\u4e00-\u9fff]{1,}|[a-zA-Z0-9_]{2,}", text.lower()))
    # 過短 token 容易造成誤判
    return {t for t in tokens if len(t) >= 2}


def _is_context_relevant(question: str, context_text: str) -> bool:
    q_tokens = _tokenize_for_relevance(question)
    c_tokens = _tokenize_for_relevance(context_text)
    if not q_tokens or not c_tokens:
        return False
    return len(q_tokens.intersection(c_tokens)) > 0


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

        context = []
        try:
            if isinstance(interaction.channel, (discord.TextChannel, discord.Thread)):
                history_messages = [
                    msg async for msg in interaction.channel.history(limit=MAX_CONTEXT_MESSAGES)
                    if not msg.author.bot
                ]

                ordered_messages = list(reversed(history_messages))  # 轉為舊 -> 新
                recent_start_index = max(0, len(ordered_messages) - MIN_RECENT_CONTEXT)

                for idx, msg in enumerate(ordered_messages):
                    if not msg.content or not msg.content.strip():
                        continue

                    is_recent = idx >= recent_start_index
                    is_relevant = _is_context_relevant(question, msg.content)
                    if not (is_recent or is_relevant):
                        continue

                    display_name = getattr(msg.author, "display_name", msg.author.name)
                    timestamp = msg.created_at.astimezone(TAIPEI_TZ)
                    context.append({
                        "role": "user",
                        "content": f"[{timestamp:%Y-%m-%d %H:%M:%S %z}] {display_name}: {msg.content}",
                    })

                # 避免 context 過大造成模型分心或回應不穩
                if len(context) > MAX_CONTEXT_TO_SEND:
                    context = context[-MAX_CONTEXT_TO_SEND:]
        except Exception as exc:
            logger.warning("讀取聊天上下文失敗: %s", exc)

        reply = await self.llm_service.generate_reply(
            question,
            system=system_prompt,
            context=context if context else None,
            temperature=0.35,
            top_p=0.8,
        )

        try:
            prompt_parts = ["[system]", system_prompt]
            if context:
                prompt_parts.append("[context]")
                for item in context:
                    prompt_parts.append(item.get("content", ""))
            prompt_parts.extend(["[question]", question])
            PROMPT_LOG_PATH.write_text("\n".join(prompt_parts), encoding="utf-8")
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
