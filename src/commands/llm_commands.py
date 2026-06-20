import logging
from pathlib import Path
import asyncio
import functools
import json
import time
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from typing import NamedTuple
import base64
import discord
from discord import app_commands
from discord.ext import commands

import llm
from llm.logger_factory import get_or_create_file_logger
from llm.lemonade_gate import note_foreground_activity
from services.llm_service import LLMService
from sys_settings.llm_settings import AskAICommandSettings, AskAIWebSettings
from utils.utils import safe_send_interaction_message, check_guild

logger = logging.getLogger("discord_bot")

ASKAI_SETTINGS = AskAICommandSettings()
WEB_SETTINGS = AskAIWebSettings()
TAIPEI_TZ = timezone(timedelta(hours=ASKAI_SETTINGS.taipei_utc_offset_hours))
PROMPT_FILE_PATH = Path(ASKAI_SETTINGS.prompt_file_path)
IDENTITY_FILE_PATH = Path(ASKAI_SETTINGS.identity_file_path)
EXAMPLES_FILE_PATH = Path(ASKAI_SETTINGS.examples_file_path)
PROMPT_LOG_PATH = Path(ASKAI_SETTINGS.prompt_log_path)
RESPONSE_LOG_PATH = Path(ASKAI_SETTINGS.response_log_path)
MAX_IMAGE_SIZE_BYTES = ASKAI_SETTINGS.max_image_size_bytes


class _AskaiQueueItem(NamedTuple):
    interaction: discord.Interaction
    question: str
    image: discord.Attachment | None
    completion: asyncio.Future
    cancel_event: asyncio.Event


class _AskaiQueue:
    """封裝 asyncio.Queue，提供 pending 狀態查詢而不依賴私有屬性。"""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[_AskaiQueueItem] = asyncio.Queue()
        self._pending: list[_AskaiQueueItem] = []
        self._processing: _AskaiQueueItem | None = None

    async def put(self, item: _AskaiQueueItem) -> None:
        self._pending.append(item)
        await self._queue.put(item)

    async def get(self) -> _AskaiQueueItem:
        item = await self._queue.get()
        try:
            self._pending.remove(item)
        except ValueError:
            pass
        self._processing = item
        return item

    def task_done(self) -> None:
        self._processing = None
        self._queue.task_done()

    def pending_summaries(self) -> list[str]:
        """回傳目前排隊中的問題摘要，包含正在處理的項目。"""
        summaries: list[str] = []
        if self._processing is not None:
            summaries.append(self._processing.question[:30])
        summaries.extend(item.question[:30] for item in self._pending)
        return summaries


ASKAI_QUEUE = _AskaiQueue()


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


def _read_prompt_file(path: Path) -> str:
    """讀單一 prompt 檔；不存在或失敗回傳空字串並記 warning。"""
    try:
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
        logger.warning("找不到 prompt 檔案：%s", path)
    except Exception as exc:
        logger.warning("載入 prompt 檔案失敗 %s：%s", path, exc)
    return ""


def load_system_prompt() -> str:
    """從檔案載入 system prompt：身份 → 主規則 → few-shot 範例。

    範例放最末，因 LLM 對 prompt 尾端的模仿力最強；範例缺檔時不影響主流程。
    主規則與身份都缺才降級至預設值。
    """
    identity = _read_prompt_file(IDENTITY_FILE_PATH)
    main_prompt = _read_prompt_file(PROMPT_FILE_PATH)
    examples = _read_prompt_file(EXAMPLES_FILE_PATH)
    parts = [p for p in (identity, main_prompt, examples) if p]
    if not (identity or main_prompt):
        logger.warning("身份與主 prompt 皆無內容，改用預設 SYSTEM PROMPT")
        return ASKAI_SETTINGS.default_system_prompt
    return "\n\n".join(parts)


def askai_cooldown(interaction: discord.Interaction):
    """管理員免冷卻、一般成員 3 分鐘一次"""
    if interaction.guild and interaction.user.guild_permissions.administrator:
        return None
    return app_commands.Cooldown(
        ASKAI_SETTINGS.askai_cooldown_count,
        ASKAI_SETTINGS.askai_cooldown_seconds,
    )


def _strip_images_for_log(
    messages: list[dict[str, object]] | None,
) -> list[dict[str, object]] | None:
    """把 messages_sent 內的 base64 圖片換成佔位符，避免 jsonl 單筆暴增到 MB 等級。

    一張 1MB 圖 ≈ 1.3MB base64，原樣寫進 jsonl 會讓檔案幾天就難 grep / tail。
    保留長度資訊讓事後仍能判斷是否有圖、有幾張。
    支援兩種格式：
      - Ollama 風格：{"role": "user", "content": "...", "images": [b64, ...]}
      - OpenAI vision：{"role": "user", "content": [{"type":"image_url", "image_url": {"url": "data:..."}}]}
    """
    if not messages:
        return messages
    sanitized: list[dict[str, object]] = []
    for msg in messages:
        new_msg = dict(msg)
        if isinstance(new_msg.get("images"), list):
            new_msg["images"] = [
                f"<image_b64 stripped, len={len(img) if isinstance(img, str) else 0}>"
                for img in new_msg["images"]
            ]
        content = new_msg.get("content")
        if isinstance(content, list):
            new_parts: list[object] = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "image_url":
                    url = (part.get("image_url") or {}).get("url", "")
                    new_parts.append({
                        "type": "image_url",
                        "image_url": {"url": f"<image_url stripped, len={len(url)}>"},
                    })
                else:
                    new_parts.append(part)
            new_msg["content"] = new_parts
        sanitized.append(new_msg)
    return sanitized


def append_askai_response_log(
    *,
    interaction: discord.Interaction,
    question: str,
    reply: str,
    model: str,
    think: bool,
    discord_meta: dict[str, int],
    rag_meta: dict[str, int | bool | str],
    web_meta: dict[str, object] | None = None,
    trace_id: str | None = None,
    messages_sent: list[dict[str, object]] | None = None,
    error_kind: str | None = None,
) -> None:
    """將每次 askai 的輸入/輸出與必要統計 append 到 jsonl，供後續觀察改善。

    `trace_id` 可串到 discord_bot.log / askai_prompt.txt / llm_anomaly.log。
    `messages_sent` 只在失敗時保留（含圖片佔位符），成功時不存——askai_prompt.txt
    已記錄同源 prompt_record_log，重複落盤一份完整 messages 會讓 jsonl 體積膨脹過快。
    `error_kind` 在失敗時標記類型（no_choices / empty_content / http_error / timeout / connection / unknown）。
    """
    guild_id = interaction.guild.id if interaction.guild else None
    channel_id = interaction.channel.id if interaction.channel else None
    author_name = getattr(interaction.user, "display_name", interaction.user.name)

    # 只在錯誤時保留 messages_sent；圖片 base64 一律換成佔位符
    persisted_messages = (
        _strip_images_for_log(messages_sent) if error_kind is not None else None
    )

    record = {
        "time": datetime.now(TAIPEI_TZ).isoformat(),
        "trace_id": trace_id,
        "error_kind": error_kind,
        "guild_id": guild_id,
        "channel_id": channel_id,
        "user_id": interaction.user.id,
        "username": author_name,
        "question": question,
        "reply": reply,
        "model": model,
        "think": think,
        "messages_sent": persisted_messages,
        "discord_context_meta": discord_meta,
        "rag_context_meta": rag_meta,
        "web_context_meta": web_meta,
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
        self.llm_service = LLMService()
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
        queue_item = _AskaiQueueItem(interaction, question, image, completion, cancel_event)

        # 顯示排隊狀態（put 之前，pending 裡的都是排在前面的）
        pending = ASKAI_QUEUE.pending_summaries()
        await ASKAI_QUEUE.put(queue_item)

        if pending:
            pending_list = "\n".join(f"  • {q}" for q in pending)
            queue_msg = f"🧾 已加入 AI 排隊（前面 {len(pending)} 則）"
        else:
            queue_msg = "🧾 已加入 AI 排隊（前面 0 則），馬上處理..."
        await safe_send_interaction_message(interaction, queue_msg, ephemeral=True)

        await completion

    async def _askai_worker(self) -> None:
        """背景任務：依序從佇列中取出請求並處理"""
        while True:
            item = await ASKAI_QUEUE.get()
            interaction, question, image, completion, cancel_event = item
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
                # 請求結束時再記一次：大模型 keep_alive 仍熱，背景插話續讓位至 grace 過後
                note_foreground_activity()
                ASKAI_QUEUE.task_done()

    async def _handle_askai_request(
        self,
        interaction: discord.Interaction,
        question: str,
        image: discord.Attachment | None,
        cancel_event: asyncio.Event | None = None,
    ):
        """實際處理 AI 回覆流程（在隊列鎖內執行）"""
        # trace_id 串接所有 askai log（discord_bot.log / askai_prompt.txt /
        # askai_response_history.jsonl / llm_anomaly.log）— 出錯時複製此 ID 即可一次定位
        trace_id = f"ask-{str(interaction.user.id)[-4:]}-{int(time.time() * 1000)}"
        logger.info("askai 開始 trace=%s user_id=%s q=%r", trace_id, interaction.user.id, question[:30])

        # 標記前景（大模型）活動：功能二的背景插話會在此窗口內讓位，避免換模型 ping-pong
        note_foreground_activity()

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

        mentioned_user_ids = llm.extract_mentioned_user_ids(question)

        # 將 <@id> 解析為「顯示名稱#XXXX」，跟 chat_history / persona card 的錨點對齊
        # 否則 LLM 看到問題裡的「二口氣上吧」對不上卡標題「NNN#7489」（display_name vs alias 不同字串）
        resolved_question = question
        if mentioned_user_ids and interaction.guild:
            for uid_str in mentioned_user_ids:
                member = interaction.guild.get_member(int(uid_str))
                if member:
                    short_id = uid_str[-4:] if len(uid_str) >= 4 else ""
                    name_with_id = (
                        f"{member.display_name}#{short_id}"
                        if short_id else member.display_name
                    )
                    resolved_question = resolved_question.replace(
                        f"<@{uid_str}>", name_with_id
                    ).replace(
                        f"<@!{uid_str}>", name_with_id
                    )

        # 網路搜尋意圖判斷 + 背景 fetch（與 discord / rag 檢索並行）
        intent = llm.should_search(resolved_question)
        run_web = WEB_SETTINGS.enabled and intent.triggered

        web_task: asyncio.Task | None = None
        if run_web:
            # 送給 SearXNG 的 query 用 cleaned_query（剝除指令贅字），engines/categories
            # 由 intent 路由決定：股價走 news+day、新聞走 news+week、reddit 走 social media
            search_query = intent.cleaned_query or resolved_question
            search_engines: str | None = None
            if intent.categories == "news":
                search_engines = WEB_SETTINGS.news_engines
            web_task = asyncio.create_task(
                llm.fetch_web_results(
                    search_query,
                    settings=WEB_SETTINGS,
                    engines=search_engines,
                    categories=intent.categories,
                    time_range=intent.time_range,
                    language=intent.language,
                    logger_override=logger,
                )
            )

        discord_context, bot_history_context, discord_meta = await llm.retrieve_discord_context(
            interaction,
            resolved_question,
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
        # mentioned_user_ids 必須顯式傳入：resolved_question 已把 <@id> 換成 display_name，
        # 內部重抽會失敗，會導致 +35 mention boost 永遠不生效（2026-04-27 修正）
        rag_context, rag_meta = await asyncio.get_running_loop().run_in_executor(
            None,
            functools.partial(
                llm.retrieve_rag_context_sync,
                resolved_question,
                interaction.guild.id if interaction.guild else None,
                interaction.user.id if interaction.user else None,
                participant_user_ids,
                logger,
                5,
                mentioned_user_ids=mentioned_user_ids,
            ),
        )

        # 回收背景 web_task 結果（若有觸發），組 web_context 與 web_meta
        web_context: list[str] | None = None
        web_meta: dict[str, object] = {
            "enabled": WEB_SETTINGS.enabled,
            "triggered": run_web,
            "reason": intent.reason,
            "trigger_keyword": intent.trigger_keyword,
            "cleaned_query": intent.cleaned_query,
            "categories": intent.categories,
            "time_range": intent.time_range,
            "language": intent.language,
        }
        if web_task is not None:
            try:
                outcome = await web_task
                web_meta.update(outcome.meta)
                if outcome.results:
                    web_context = llm.format_web_context_lines(outcome.results)
                    # 記錄前 3 筆 preview 方便日後 debug：判斷 LLM 到底看到什麼
                    web_meta["results_preview"] = [
                        {
                            "title": r.title,
                            "url": r.url,
                            "engine": r.engine,
                            "published_date": r.published_date,
                        }
                        for r in outcome.results[:3]
                    ]
            except Exception as exc:
                logger.warning("web_task 收尾失敗: %s", exc, exc_info=True)
                web_meta["error"] = f"await_failed:{type(exc).__name__}"

        # 聊天記錄：提取純文字，並用 persona card alias 標註身份
        # _build_discord_context_item 已在每行 display_name 後加 #XXXX 錨點
        # 這裡只做 alias 註記，不再需要撞名偵測
        alias_map: dict[str, str] = rag_meta.get("alias_map", {})

        chat_context: list[str] | None = None
        if discord_context:
            lines: list[str] = []
            for item in discord_context:
                content = item.get("content", "")
                if not content:
                    continue
                author_id = item.get("author_id", "")

                # 如果這個人有 persona card，在 display_name#XXXX 後標註 alias
                # content 格式: "[14:30] ❤️柔柔喵❤️#4635: 內容"
                # 改成:        "[14:30] ❤️柔柔喵❤️#4635(喵董): 內容"
                card_alias = alias_map.get(author_id, "")
                if card_alias and card_alias not in content:
                    content = content.replace(": ", f"({card_alias}): ", 1)
                lines.append(content)
            chat_context = lines or None

        # Bot 自身回覆歷史（獨立於 chat_history 額度外）
        bot_history: list[str] | None = None
        if bot_history_context:
            bot_history = [
                item["content"] for item in bot_history_context
                if item.get("content")
            ] or None

        # 人物描述：由 persona card builder 產出的自然語言
        # 三路分流（依優先序）：
        # 1. 發問者本人的卡（asker_persona_text）→ 注入 asker_profile system block
        # 2. 發問者明確 mention 的對象（target_profiles）→ 放 <target_profile>，緊鄰問題
        # 3. 其餘參與者（persona_context）→ 放 <other_member_profiles>，背景資訊
        asker_uid_str = str(interaction.user.id)
        mentioned_uid_set = set(mentioned_user_ids or [])
        asker_persona_text: str | None = None
        target_items: list[str] = []
        persona_context: list[str] | None = None
        matched_mention_ids: set[str] = set()
        if rag_context:
            other_items: list[str] = []
            for item in rag_context:
                content = item.get("content")
                if not content or item.get("metadata") == "persona_card_header":
                    continue
                person_id = item.get("person_id")
                if person_id == asker_uid_str and asker_persona_text is None:
                    asker_persona_text = content
                elif person_id in mentioned_uid_set:
                    target_items.append(content)
                    matched_mention_ids.add(person_id)
                else:
                    other_items.append(content)
            persona_context = other_items or None

        # mention 了但 DB 沒卡：放退場提示，避免 LLM 反問或硬猜
        # 例：新進群、未填自介、AI 觀察未跑、或 user_id 已不在群內
        unmatched_mention_ids = mentioned_uid_set - matched_mention_ids
        for uid in unmatched_mention_ids:
            short_id = uid[-4:] if len(uid) >= 4 else ""
            member = interaction.guild.get_member(int(uid)) if interaction.guild else None
            display_name = member.display_name if member else f"user_{short_id}"
            label = f"{display_name}#{short_id}" if short_id else display_name
            target_items.append(
                f"「{label}」— 群內尚無此人的 persona 紀錄；"
                f"可從 chat_history 推測，否則請老實說對此人不熟悉"
            )
        target_profiles = target_items or None

        # 組 asker_profile：可信的發問者身份資訊（給 system block）
        # asker_display_name 永遠帶 #XXXX，跟 chat_history / persona card 對齊
        asker_display_name_raw = getattr(
            interaction.user, "display_name", interaction.user.name
        )
        asker_short_id = asker_uid_str[-4:] if len(asker_uid_str) >= 4 else ""
        asker_display_name = (
            f"{asker_display_name_raw}#{asker_short_id}"
            if asker_short_id else asker_display_name_raw
        )
        now_str = datetime.now(TAIPEI_TZ).strftime("%Y-%m-%d %H:%M (UTC+8)")
        guild_name = interaction.guild.name if interaction.guild else "(DM)"
        channel_name = getattr(interaction.channel, "name", "") or "(unknown)"
        asker_profile_lines = [
            "<asker_profile>",
            f"display_name: {asker_display_name}",
            f"user_id: {interaction.user.id}",
            "roles: (未啟用)",
            f"persona_summary: {asker_persona_text or '（無）'}",
            f"current_time: {now_str}",
            f"guild_name: {guild_name}",
            f"channel_name: {channel_name}",
            "</asker_profile>",
            "",
            "這是本次發問者的可信身份資訊。回覆時可個人化互動；但 user_id 與內部欄位不得對外揭露。",
        ]
        asker_profile_text = "\n".join(asker_profile_lines)

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

        # Bot 自身身份：伺服器暱稱優先 → 全域 username → None（僅極端情境）
        bot_display_name = None
        if interaction.guild and interaction.guild.me:
            bot_display_name = interaction.guild.me.display_name
        elif interaction.client.user:
            bot_display_name = interaction.client.user.name

        # 用 asyncio.Task 包裝，取消時可中斷 Ollama HTTP 請求
        llm_task = asyncio.create_task(self.llm_service.generate_reply(
            prompt=resolved_question,
            system=system_prompt,
            chat_context=chat_context,
            bot_history=bot_history,
            persona_context=persona_context,
            target_profiles=target_profiles,
            web_context=web_context,
            images=image_payload,
            model=target_model,
            think=target_think,
            asker_profile=asker_profile_text,
            asker_display_name=asker_display_name,
            bot_display_name=bot_display_name,
            # chat model 在最後一次 /askai 後 1h 內保持常駐，避開反覆 unload/reload
            # 觸發的 Windows ephemeral port 與 runner crash；閒置超過 1h 才釋放 VRAM
            keep_alive="1h",
            trace_id=trace_id,
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
            llm_result = llm_task.result()
        else:
            llm_result = await llm_task

        reply = llm_result.reply
        prompt_record_log = llm_result.prompt_record_log
        messages_sent = llm_result.messages_sent
        error_kind = llm_result.error_kind

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
                    title=f"ASKAI_PROMPT trace={trace_id}",
                    body=prompt_record_log,
                )
            )
        except Exception as exc:
            logger.warning("寫入 askai prompt 失敗 trace=%s: %s", trace_id, exc)

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
                    title=f"ASKAI_PROMPT_DEBUG trace={trace_id}",
                    body=(
                        f"<prompt_record_log>\n{prompt_record_log}\n</prompt_record_log>\n"
                        f"<debug>\n{prompt_debug_text}\n</debug>"
                    ),
                )
            )
        except Exception as exc:
            logger.warning("寫入 askai prompt debug 失敗 trace=%s: %s", trace_id, exc)

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
                web_meta=web_meta,
                trace_id=trace_id,
                messages_sent=messages_sent,
                error_kind=error_kind,
            )
        except Exception as exc:
            logger.warning("寫入 askai response history 失敗 trace=%s: %s", trace_id, exc)

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
                    item.style = discord.ButtonStyle.success
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


class _PersonalityResultPagerView(discord.ui.View):
    """人格萃取結果分頁 + 寫入/捨棄按鈕。"""

    def __init__(
        self,
        *,
        user_id: int,
        guild_id: int,
        results: dict,
        embeds: list[discord.Embed],
        job: "_PersonalityExtractJob | None" = None,
        message: discord.Message | None = None,
    ):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.guild_id = guild_id
        self.results = results
        self.embeds = embeds
        self.job = job
        self.message: discord.Message | None = message
        self.current_page = 0
        self._refresh_buttons()

    def _refresh_buttons(self) -> None:
        self.prev_button.disabled = self.current_page <= 0
        self.next_button.disabled = self.current_page >= len(self.embeds) - 1

    def _disable_all(self) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

    @discord.ui.button(label="上一頁", style=discord.ButtonStyle.primary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("只有執行者可以操作。", ephemeral=True)
            return
        self.current_page = max(0, self.current_page - 1)
        self._refresh_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

    @discord.ui.button(label="下一頁", style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("只有執行者可以操作。", ephemeral=True)
            return
        self.current_page = min(len(self.embeds) - 1, self.current_page + 1)
        self._refresh_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

    @discord.ui.button(label="寫入 RAG", style=discord.ButtonStyle.success)
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("只有執行者可以操作。", ephemeral=True)
            return
        self._disable_all()
        await interaction.response.edit_message(content="⏳ 正在寫入 RAG...", embed=None, view=self)

        total = len(self.results)
        progress_msg = await interaction.followup.send(
            f"⏳ 正在寫入 RAG（0/{total}）",
            ephemeral=True,
            wait=True,
        )

        last_reported = 0

        async def _report(written: int, tot: int) -> None:
            # 每 3 筆刷新一次，最後一筆由外層處理成 ✅
            nonlocal last_reported
            if written >= tot or written - last_reported < 3:
                return
            last_reported = written
            try:
                await progress_msg.edit(content=f"⏳ 正在寫入 RAG（{written}/{tot}）")
            except Exception as exc:
                logger.warning("更新寫入 RAG 進度訊息失敗: %s", exc)

        from llm.personality_extractor import save_personality_results
        written = await save_personality_results(
            guild_id=self.guild_id,
            results=self.results,
            progress_callback=_report,
        )
        if self.job:
            self.job.status = "written"
        final_text = f"✅ 已寫入 RAG：{written} 筆"
        try:
            await progress_msg.edit(content=final_text)
        except Exception as exc:
            logger.warning("最終寫入 RAG 結果訊息 edit 失敗，改用 followup send: %s", exc)
            await interaction.followup.send(final_text, ephemeral=True)
        self.stop()

    @discord.ui.button(label="捨棄", style=discord.ButtonStyle.secondary)
    async def discard_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("只有執行者可以操作。", ephemeral=True)
            return
        self._disable_all()
        if self.job:
            self.job.status = "discarded"
        await interaction.response.edit_message(content="🗑️ 已捨棄，不寫入 RAG。", embed=None, view=self)
        self.stop()

    async def on_timeout(self):
        self._disable_all()
        if self.message:
            try:
                await self.message.edit(content="⏰ 已逾時，未寫入 RAG。", embed=None, view=self)
            except Exception:
                pass


@dataclass
class _PersonalityExtractJob:
    """手動人格萃取工作的暫存狀態。"""

    user_id: int
    guild_id: int
    model: str | None
    days: int
    status: str = "running"  # running | done | empty | error
    results: dict[str, dict[str, str]] | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    current_stage: str | None = None
    current_model: str | None = None
    total_users: int = 0
    completed_users: int = 0
    current_batch: int = 0
    total_batches: int = 0


class _ExtractStatusView(discord.ui.View):
    """人格萃取啟動後附帶的「查看結果」按鈕。"""

    def __init__(self, cog: "PersonalityCommands", job_key: tuple[int, int], user_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.job_key = job_key
        self.user_id = user_id

    @staticmethod
    def _build_result_embeds(job: "_PersonalityExtractJob") -> list[discord.Embed]:
        """將人格萃取結果切成多篇 embed。"""
        title = f"🧪 人格萃取預覽（模型：{job.model or '預設'}，天數：{job.days}，共 {len(job.results or {})} 人）"
        chunks: list[str] = []
        current = ""

        for uid, data in (job.results or {}).items():
            alias = data.get("alias", uid)
            personality = data.get("personality", "")
            block = f"**{alias}**\n{personality}\n\n"
            if current and len(current) + len(block) > 4000:
                chunks.append(current.rstrip())
                current = block
            else:
                current += block

        if current:
            chunks.append(current.rstrip())

        if not chunks:
            chunks = ["(無結果)"]

        embeds: list[discord.Embed] = []
        total = len(chunks)
        for index, chunk in enumerate(chunks, start=1):
            embed = discord.Embed(
                title=title if index == 1 else f"🧪 人格萃取預覽（第 {index}/{total} 篇）",
                description=chunk,
                color=discord.Color.blurple(),
            )
            embed.set_footer(text=f"第 {index}/{total} 篇")
            embeds.append(embed)
        return embeds

    async def _show_status(self, interaction: discord.Interaction) -> None:
        job = self.cog._extract_jobs.get(self.job_key)
        if not job:
            await interaction.response.send_message("ℹ️ 找不到對應的萃取工作。", ephemeral=True)
            return

        time_str = ""
        if job.created_at:
            elapsed = datetime.now(timezone.utc) - job.created_at
            minutes = int(elapsed.total_seconds() // 60)
            time_str = f"，啟動於 {minutes} 分鐘前" if minutes > 0 else "，剛啟動"

        if job.status == "running":
            progress_bits: list[str] = []
            if job.total_batches > 0:
                progress_bits.append(f"batch {job.current_batch}/{job.total_batches}")
            if job.total_users > 0:
                progress_bits.append(f"已完成 {job.completed_users}/{job.total_users} 位使用者")
            if job.current_model:
                progress_bits.append(f"目前模型：{job.current_model}")
            if job.current_stage:
                progress_bits.append(f"階段：{job.current_stage}")
            progress_text = "\n" + "\n".join(f"- {item}" for item in progress_bits) if progress_bits else ""
            await interaction.response.send_message(
                f"⏳ 人格萃取仍在進行中（模型：{job.model or '預設'}，天數：{job.days}{time_str}）。請稍後再按一次。{progress_text}",
                ephemeral=True,
            )
            return

        if job.status == "error":
            await interaction.response.send_message(
                f"❌ 人格萃取失敗{time_str}：{job.error_message or '未知錯誤'}",
                ephemeral=True,
            )
            return

        if job.status in ("written", "discarded"):
            label = "已寫入 RAG" if job.status == "written" else "已捨棄"
            await interaction.response.send_message(
                f"ℹ️ 此次萃取結果{label}。如需重新萃取，請再次執行 `/personality_extract`。",
                ephemeral=True,
            )
            return

        if job.status == "empty" or not job.results:
            await interaction.response.send_message(
                f"⚠️ 人格萃取結果為空{time_str}，可能是訊息不足或模型錯誤。",
                ephemeral=True,
            )
            return

        embeds = self._build_result_embeds(job)

        pager_view = _PersonalityResultPagerView(
            user_id=self.user_id,
            guild_id=self.job_key[0],
            results=job.results,
            embeds=embeds,
            job=job,
        )
        await interaction.response.send_message(
            embed=embeds[0],
            ephemeral=True,
            view=pager_view,
        )
        msg = await interaction.original_response()
        pager_view.message = msg

    @discord.ui.button(label="查看結果", style=discord.ButtonStyle.primary)
    async def check_status(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("只有執行者可以操作。", ephemeral=True)
            return
        await self._show_status(interaction)


class PersonalityCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._extract_jobs: dict[tuple[int, int], _PersonalityExtractJob] = {}
        self._extract_tasks: set[asyncio.Task] = set()

    def _track_task(self, task: asyncio.Task) -> None:
        self._extract_tasks.add(task)

        def _cleanup(done_task: asyncio.Task) -> None:
            self._extract_tasks.discard(done_task)

        task.add_done_callback(_cleanup)

    def register_scheduled_result(
        self,
        *,
        guild_id: int,
        results: dict[str, dict[str, str]],
        model: str | None,
        days: int,
    ) -> None:
        """將排程執行的人格萃取結果寫入記憶體，供查詢指令讀取。"""
        job_key = (guild_id, 0)
        self._extract_jobs[job_key] = _PersonalityExtractJob(
            user_id=0,
            guild_id=guild_id,
            model=model,
            days=days,
            status="done" if results else "empty",
            results=results,
            created_at=datetime.now(timezone.utc),
            current_stage="排程完成",
            current_model=model,
            total_users=len(results),
            completed_users=len(results),
            current_batch=0,
            total_batches=0,
        )

    @app_commands.command(name="personality_extract_status", description="查看人格萃取進度或結果（管理員限定）")
    @app_commands.checks.has_permissions(administrator=True)
    async def personality_extract_status_cmd(self, interaction: discord.Interaction):
        if not interaction.guild:
            await safe_send_interaction_message(interaction, "⚠️ 僅限伺服器內使用。", ephemeral=True)
            return

        user_id = interaction.user.id
        guild_id = interaction.guild.id
        job_key = (guild_id, user_id)
        if job_key not in self._extract_jobs:
            scheduled_key = (guild_id, 0)
            if scheduled_key in self._extract_jobs:
                job_key = scheduled_key
                user_id = interaction.user.id
            else:
                await safe_send_interaction_message(
                    interaction,
                    "ℹ️ 目前沒有可查看的人格萃取工作，請先執行 `/personality_extract` 或等待排程完成。",
                    ephemeral=True,
                )
                return

        status_view = _ExtractStatusView(cog=self, job_key=job_key, user_id=user_id)
        await status_view._show_status(interaction)

    @app_commands.command(name="personality_extract", description="手動執行人格萃取（管理員限定）")
    @app_commands.describe(
        model="指定模型（不填則用 config 設定）",
        days="分析天數（預設 14）",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def personality_extract_cmd(
        self,
        interaction: discord.Interaction,
        model: str | None = None,
        days: int = 14,
    ):
        if not interaction.guild:
            await safe_send_interaction_message(
                interaction,
                "⚠️ 僅限伺服器內使用。",
                ephemeral=True,
            )
            return

        from llm.personality_extractor import (
            PersonalityExtractionInProgressError,
            run_personality_extraction,
        )
        guild = interaction.guild
        user_id = interaction.user.id
        guild_id = interaction.guild.id
        job_key = (guild_id, user_id)

        job = _PersonalityExtractJob(
            user_id=user_id,
            guild_id=guild_id,
            model=model,
            days=days,
            status="running",
            created_at=datetime.now(timezone.utc),
        )
        self._extract_jobs[job_key] = job

        status_view = _ExtractStatusView(cog=self, job_key=job_key, user_id=user_id)
        await safe_send_interaction_message(
            interaction,
            f"🔄 已啟動人格萃取工作（模型：{model or '預設'}，天數：{days}）。\n"
            "完成後請按下方按鈕查看結果；若按鈕失效，也可以使用 `/personality_extract_status`。",
            ephemeral=True,
            view=status_view,
        )

        async def _run_and_report():
            def _update_progress(
                *,
                stage: str,
                model: str,
                total_users: int,
                completed_users: int,
                current_batch: int,
                total_batches: int,
            ) -> None:
                stage_map = {
                    "initializing": "初始化中",
                    "grouped": "已完成分組",
                    "preparing": "準備批次資料",
                    "calling_llm": "正在呼叫 LLM",
                    "batch_done": "批次完成",
                    "finished": "全部完成",
                }
                job.current_stage = stage_map.get(stage, stage)
                job.current_model = model
                job.total_users = total_users
                job.completed_users = completed_users
                job.current_batch = current_batch
                job.total_batches = total_batches

            try:
                results = await run_personality_extraction(
                    guild=guild,
                    days=days,
                    model=model,
                    write_rag=False,
                    progress_callback=_update_progress,
                )
            except PersonalityExtractionInProgressError:
                job.status = "error"
                job.error_message = "目前已有一個人格萃取流程正在執行，請稍後再試。"
                return
            except Exception as exc:
                logger.error("人格萃取指令失敗: %s", exc, exc_info=True)
                job.status = "error"
                job.error_message = str(exc)
                return

            if not results:
                job.status = "empty"
                return

            job.status = "done"
            job.results = results

        task = asyncio.create_task(_run_and_report())
        self._track_task(task)


async def setup(bot):
    await bot.add_cog(LLMCommands(bot))
    await bot.add_cog(PersonalityCommands(bot))
