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
from llm.logger_factory import get_or_create_file_logger
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


def _format_log_block(*, title: str, body: str) -> str:
    """用明顯分隔符與時間戳包住每筆 log，便於人工閱讀。"""
    ts = datetime.now(TAIPEI_TZ).strftime("%Y-%m-%d %H:%M:%S %z")
    line = "=" * 28
    return (
        f"\n{line} {title} {line}\n"
        f"time: {ts}\n"
        f"{body}\n"
        f"{line} END {title} {line}\n"
    )


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
    """管理員免冷卻、一般成員 3 分鐘一次"""
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
    model: str,
    think: bool,
    discord_meta: dict[str, int],
    rag_meta: dict[str, int | bool | str],
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
        "model": model,
        "think": think,
        "discord_context_meta": discord_meta,
        "rag_context_meta": rag_meta,
    }

    response_logger = get_or_create_file_logger(
        name="askai_response_trace",
        log_path=RESPONSE_LOG_PATH,
        mode="size",
        max_bytes=ASKAI_SETTINGS.response_log_max_bytes,
        backup_count=ASKAI_SETTINGS.response_log_backup_count,
    )
    response_logger.info(json.dumps(record, ensure_ascii=False))


class _AskaiCancelButton(discord.ui.View):
    """AI 思考中的取消按鈕。"""

    def __init__(self, user_id: int, cancel_event: asyncio.Event):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.cancel_event = cancel_event

    @discord.ui.button(label="取消", style=discord.ButtonStyle.danger)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            try:
                await interaction.response.send_message("只有發問者可以取消。", ephemeral=True)
            except Exception:
                pass
            return
        # 先觸發取消（讓 asyncio.wait 盡快醒來）
        self.cancel_event.set()
        # 更新按鈕狀態
        button.disabled = True
        button.label = "已取消"
        # 嘗試多種方式回應（ephemeral followup 的交互行為不一致）
        try:
            await interaction.response.edit_message(content="❌ 已取消 AI 回覆。", view=self)
        except (discord.NotFound, discord.HTTPException):
            try:
                await interaction.followup.edit_message(
                    interaction.message.id,
                    content="❌ 已取消 AI 回覆。",
                    view=self,
                )
            except Exception:
                pass
        self.stop()

    async def on_timeout(self) -> None:
        """超時後停用按鈕。"""
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True


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
        cancel_event = asyncio.Event()
        queue_item = (interaction, question, image, completion, cancel_event)

        # 將請求加入佇列以避免阻塞主執行緒
        queue_size = ASKAI_QUEUE.qsize()
        await ASKAI_QUEUE.put(queue_item)
        await safe_send_interaction_message(
            interaction,
            f"🧾 已加入 AI 排隊（前面排隊人數：{queue_size}）。請稍候...",
            ephemeral=True
        )

        await completion

    async def _askai_worker(self) -> None:
        """背景任務：依序從佇列中取出請求並處理"""
        while True:
            interaction, question, image, completion, cancel_event = await ASKAI_QUEUE.get()
            try:
                if cancel_event.is_set():
                    if not completion.done():
                        completion.set_result("cancelled")
                    continue
                await self._handle_askai_request(interaction, question, image, cancel_event)
                if not completion.done():
                    if cancel_event.is_set():
                        completion.set_result("cancelled")
                    else:
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
        cancel_event: asyncio.Event | None = None,
    ):
        """實際處理 AI 回覆流程（在隊列鎖內執行）"""
        system_prompt = load_system_prompt()

        cancel_view = None
        if cancel_event:
            cancel_view = _AskaiCancelButton(interaction.user.id, cancel_event)

        thinking_msg = await interaction.followup.send(
            "🔄 AI 思考中，請耐心等候...",
            ephemeral=True,
            view=cancel_view,
            wait=True,
        )

        # 取得歷史聊天上下文（統一契約：list[dict[str, str]]）
        # 視覺請求時縮短聊天上下文，降低 token 與 timeout 風險。
        # 注意：max_context_to_send 在 retriever 內代表「聊天訊息數」，
        # 另會保留 1 行 header，因此最終 sent_count 可能是 6（1 header + 5 聊天）。
        max_context_messages = ASKAI_SETTINGS.max_context_messages
        min_recent_context = ASKAI_SETTINGS.min_recent_context
        max_relevant_context = ASKAI_SETTINGS.max_relevant_context
        max_context_to_send = ASKAI_SETTINGS.max_context_to_send

        if image is not None:
            max_context_messages = min(max_context_messages, 20)
            min_recent_context = min(min_recent_context, 5)
            max_relevant_context = min(max_relevant_context, 5)
            max_context_to_send = 5

        discord_context, discord_meta = await llm.retrieve_discord_context(
            interaction,
            question,
            max_context_messages=max_context_messages,
            min_recent_context=min_recent_context,
            max_relevant_context=max_relevant_context,
            max_context_to_send=max_context_to_send,
            taipei_tz=TAIPEI_TZ,
            logger=logger,
        )

        participant_user_ids: list[int] = []
        for item in discord_context:
            author_id_raw = str(item.get("author_id", "")).strip()
            if author_id_raw.isdigit():
                participant_user_ids.append(int(author_id_raw))
        participant_user_ids = list(dict.fromkeys(participant_user_ids))

        # retrieve_rag_context 內部呼叫 LlamaIndex 同步 API（embedding + pgvector），
        # 在 executor 中執行以避免阻塞 event loop（影響語音 heartbeat 等）。
        rag_context, rag_meta = await asyncio.get_running_loop().run_in_executor(
            None,
            llm.retrieve_rag_context_sync,
            question,
            interaction.guild.id if interaction.guild else None,
            interaction.user.id if interaction.user else None,
            participant_user_ids,
            logger,
            5,
        )

        # 聊天記錄：提取純文字，並用 persona card alias 標註身份
        alias_map: dict[str, str] = rag_meta.get("alias_map", {})
        chat_context: list[str] | None = None
        if discord_context:
            lines: list[str] = []
            for item in discord_context:
                content = item.get("content", "")
                if not content:
                    continue
                # 如果這個人有 persona card，在 display_name 後標註 alias
                author_id = item.get("author_id", "")
                card_alias = alias_map.get(author_id, "")
                if card_alias and card_alias not in content:
                    # content 格式: "[14:30] ❤️柔柔喵❤️: 內容"
                    # 改成:        "[14:30] ❤️柔柔喵❤️(喵董): 內容"
                    content = content.replace(": ", f"({card_alias}): ", 1)
                lines.append(content)
            chat_context = lines or None

        # 人物描述：由 persona card builder 產出的自然語言
        persona_context: list[str] | None = None
        if rag_context:
            persona_context = [
                item["content"]
                for item in rag_context
                if item.get("content") and item.get("metadata") != "persona_card_header"
            ] or None

        image_payload = None
        if image:
            image_payload = await self._prepare_image_payload(interaction, image)
            if image_payload is None:
                return

        image_meta: dict[str, str | int | bool] | None = None
        if image and image_payload:
            image_meta = {
                "attached": True,
                "count": len(image_payload),
                "filename": image.filename or "",
                "size_bytes": image.size or 0,
            }

        # 取消檢查：context 檢索完、LLM 呼叫前
        if cancel_event and cancel_event.is_set():
            return

        # === 呼叫 Service：各司其職，只傳遞乾淨的參數與字串 ===
        target_model = self.llm_service.resolve_request_model()
        target_think = self.llm_service.resolve_request_think()

        # 用 asyncio.Task 包裝，取消時可中斷 Ollama HTTP 請求
        llm_task = asyncio.create_task(self.llm_service.generate_reply(
            prompt=question,
            system=system_prompt,
            chat_context=chat_context,
            persona_context=persona_context,
            images=image_payload,
            model=target_model,
            think=target_think,
        ))

        # 同時等 LLM 回覆和取消事件
        if cancel_event:
            cancel_waiter = asyncio.create_task(cancel_event.wait())
            done, pending = await asyncio.wait(
                [llm_task, cancel_waiter],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for t in pending:
                t.cancel()
            # 確保被取消的 task 完全結束，釋放 HTTP 連線資源
            await asyncio.gather(llm_task, cancel_waiter, return_exceptions=True)
            if cancel_event.is_set():
                return
            reply, prompt_record_log = llm_task.result()
        else:
            reply, prompt_record_log = await llm_task

        # askai_prompt.txt：只記錄「真正送給 Ollama 的文字」
        try:
            prompt_trace_logger = get_or_create_file_logger(
                name="askai_prompt_trace",
                log_path=PROMPT_LOG_PATH,
                mode="time",
                when=ASKAI_SETTINGS.prompt_log_when,
                interval=ASKAI_SETTINGS.prompt_log_interval,
                backup_count=ASKAI_SETTINGS.prompt_log_backup_count,
            )
            prompt_trace_logger.info(
                _format_log_block(
                    title="ASKAI_PROMPT",
                    body=prompt_record_log,
                )
            )
        except Exception as exc:
            logger.warning("寫入 askai prompt 失敗: %s", exc)

        # askai_prompt_debug.txt：記錄檢索/融合等 debug 細節
        try:
            retrieval_debug = discord_meta.get("retrieval_debug")
            prompt_debug_text = llm.build_askai_prompt_log(
                system_prompt=system_prompt,
                question=question,
                discord_context=discord_context,
                rag_context=rag_context,
                discord_meta=discord_meta,
                rag_meta=rag_meta,
                retrieval_debug=retrieval_debug if isinstance(retrieval_debug, dict) else None,
                image_meta=image_meta,
                max_context_messages=ASKAI_SETTINGS.max_context_messages,
                discord_context_begin=ASKAI_SETTINGS.discord_context_begin,
                discord_context_end=ASKAI_SETTINGS.discord_context_end,
                rag_context_begin=ASKAI_SETTINGS.rag_context_begin,
                rag_context_end=ASKAI_SETTINGS.rag_context_end,
            )
            prompt_debug_logger = get_or_create_file_logger(
                name="askai_prompt_debug",
                log_path=Path(ASKAI_SETTINGS.prompt_debug_log_path),
                mode="size",
                max_bytes=ASKAI_SETTINGS.prompt_debug_log_max_bytes,
                backup_count=ASKAI_SETTINGS.prompt_debug_log_backup_count,
            )
            prompt_debug_logger.info(
                _format_log_block(
                    title="ASKAI_PROMPT_DEBUG",
                    body=(
                        f"<prompt_record_log>\n{prompt_record_log}\n</prompt_record_log>\n"
                        f"<debug>\n{prompt_debug_text}\n</debug>"
                    ),
                )
            )
        except Exception as exc:
            logger.warning("寫入 askai prompt debug 失敗: %s", exc)

        # 記錄回應歷史
        try:
            append_askai_response_log(
                interaction=interaction,
                question=question,
                reply=reply,
                model=target_model,
                think=target_think,
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

        # 回覆完成後停用取消按鈕
        if cancel_view and thinking_msg:
            for item in cancel_view.children:
                if isinstance(item, discord.ui.Button):
                    item.disabled = True
                    item.label = "已完成"
            cancel_view.stop()
            try:
                await thinking_msg.edit(content="✅ AI 已回覆。", view=cancel_view)
            except Exception:
                pass

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
