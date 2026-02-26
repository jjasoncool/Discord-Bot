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
from sys_settings.llm_settings import AskAICommandSettings
from utils.utils import safe_send_interaction_message, check_guild

logger = logging.getLogger("discord_bot")

ASKAI_SETTINGS = AskAICommandSettings()
TAIPEI_TZ = timezone(timedelta(hours=ASKAI_SETTINGS.taipei_utc_offset_hours))
PROMPT_FILE_PATH = Path(ASKAI_SETTINGS.prompt_file_path)
PROMPT_LOG_PATH = Path(ASKAI_SETTINGS.prompt_log_path)
RESPONSE_LOG_PATH = Path(ASKAI_SETTINGS.response_log_path)
ASKAI_QUEUE = asyncio.Queue()
MAX_IMAGE_SIZE_BYTES = ASKAI_SETTINGS.max_image_size_bytes


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
    return ASKAI_SETTINGS.default_system_prompt


def askai_cooldown(interaction: discord.Interaction):
    """管理員免冷卻、一般成員 5 分鐘一次"""
    if interaction.guild and interaction.user.guild_permissions.administrator:
        return None
    return app_commands.Cooldown(
        ASKAI_SETTINGS.askai_cooldown_count,
        ASKAI_SETTINGS.askai_cooldown_seconds,
    )


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
        """確保處理 AI 請求的背景任務正在運行。"""
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

        # 將請求加入佇列以避免阻塞主執行緒
        await ASKAI_QUEUE.put(queue_item)
        queue_size = ASKAI_QUEUE.qsize()
        await safe_send_interaction_message(
            interaction,
            f"🧾 已加入 AI 排隊（目前排隊人數：{queue_size}）。請稍候...",
            ephemeral=True
        )

        await completion

    async def _askai_worker(self) -> None:
        """背景任務：依序從佇列中取出請求並處理"""
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

        # 取得歷史聊天上下文（統一契約：list[dict[str, str]]）
        discord_context, discord_meta = await llm.retrieve_discord_context(
            interaction,
            question,
            max_context_messages=ASKAI_SETTINGS.max_context_messages,
            min_recent_context=ASKAI_SETTINGS.min_recent_context,
            max_relevant_context=ASKAI_SETTINGS.max_relevant_context,
            max_context_to_send=ASKAI_SETTINGS.max_context_to_send,
            taipei_tz=TAIPEI_TZ,
            logger=logger,
        )
        rag_context, rag_meta = await llm.retrieve_rag_context(question)

        # 統一把多來源 context 合併後交給 Service 層做安全序列化
        context_items = [*discord_context, *rag_context] if (discord_context or rag_context) else None

        image_payload = None
        if image:
            image_payload = await self._prepare_image_payload(interaction, image)
            if image_payload is None:
                return

        # === 呼叫 Service：各司其職，只傳遞乾淨的參數與字串 ===
        reply = await self.llm_service.generate_reply(
            prompt=question,              # 單純的使用者問題
            system=system_prompt,         # 單純的系統規則
            context_items=context_items,  # 結構化上下文（由 Service 層統一安全封裝）
            images=image_payload,
        )

        # 記錄 prompt 日誌，供後續除錯與調優
        try:
            prompt_log_text = llm.build_askai_prompt_log(
                system_prompt=system_prompt,
                question=question,
                discord_context=discord_context,
                rag_context=rag_context,
                discord_meta=discord_meta,
                rag_meta=rag_meta,
                max_context_messages=ASKAI_SETTINGS.max_context_messages,
                discord_context_begin=ASKAI_SETTINGS.discord_context_begin,
                discord_context_end=ASKAI_SETTINGS.discord_context_end,
                rag_context_begin=ASKAI_SETTINGS.rag_context_begin,
                rag_context_end=ASKAI_SETTINGS.rag_context_end,
            )
            PROMPT_LOG_PATH.write_text(prompt_log_text, encoding="utf-8")
        except Exception as exc:
            logger.warning("寫入 askai prompt 失敗: %s", exc)

        # 記錄回應歷史
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

        # 使用 followup 回覆，避免互動超時，並組合最終排版
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
                "⚠️ 圖片大小超過 5MB，請縮圖或換小一點的檔案。",
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
