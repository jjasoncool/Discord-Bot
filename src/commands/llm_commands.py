import logging
from pathlib import Path
import asyncio
import functools
import json
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, NamedTuple
import base64
import io
import discord
from discord import app_commands
from discord.ext import commands

from llm.logger_factory import build_askai_prompt_log, get_or_create_file_logger
from llm.persona.persona_card_builder import extract_mentioned_user_ids
from llm.retrievers.context_retriever import retrieve_discord_context, retrieve_rag_context_sync
from llm.retrievers.intel import run_with_intel
from llm.retrievers.web import WebSearchTools, format_web_context_lines, search_web, should_search
from llm.client.lemonade_gate import imagegen_busy, note_foreground_activity
from llm.persona.member_names import member_names_from_guild, name_map_lines
from llm.preprocess import person_anchor
from llm.preprocess.external_emoji import external_emoji_context
from llm.preprocess.tweet_context import expand_tweets
from llm.preprocess.chat_line import name_with_anchor
from llm.preprocess.vision_image import (
    DEFAULT_MAX_FRAMES,
    VISION_IMAGE_EXTS,
    extract_key_frames,
    is_vision_image,
)
from services.llm_service import LLMService
from sys_settings import switches
from sys_settings.llm_settings import AskAICommandSettings, AskAIIntelSettings, AskAIWebSettings
from sys_settings.time_settings import APP_TZ
from utils.discord_content import DISCORD_MESSAGE_LIMIT, split_message
from utils.dm_notifier import send_dm
from utils.utils import safe_send_interaction_message, check_guild
from utils.background_tasks import supervise

logger = logging.getLogger(__name__)

ASKAI_SETTINGS = AskAICommandSettings()
WEB_SETTINGS = AskAIWebSettings()
INTEL_SETTINGS = AskAIIntelSettings()
PROMPT_FILE_PATH = Path(ASKAI_SETTINGS.prompt_file_path)
IDENTITY_FILE_PATH = Path(ASKAI_SETTINGS.identity_file_path)
GUARDRAILS_FILE_PATH = Path(ASKAI_SETTINGS.guardrails_file_path)
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
    ts = datetime.now(APP_TZ).strftime("%Y-%m-%d %H:%M:%S %z")
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
    """從檔案載入 system prompt（模組化拼裝）：身份 → 守則 → 深聊風格+任務 → few-shot 範例。

    身份(persona_identity)與守則(persona_guardrails)跟 ambient 共用同檔；深聊風格+問答任務
    在 askai_system_prompt（ambient 不載這層 → 較不端著）。範例放最末，因 LLM 對 prompt
    尾端模仿力最強；範例缺檔不影響主流程。主規則與身份都缺才降級至預設值。
    """
    identity = _read_prompt_file(IDENTITY_FILE_PATH)
    guardrails = _read_prompt_file(GUARDRAILS_FILE_PATH)
    main_prompt = _read_prompt_file(PROMPT_FILE_PATH)
    examples = _read_prompt_file(EXAMPLES_FILE_PATH)
    # 模組化拼裝：人格 → 守則 → 深聊風格+任務 → few-shot（守則與人格跟 ambient 共用同檔）
    parts = [p for p in (identity, guardrails, main_prompt, examples) if p]
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
    intel_meta: dict[str, object] | None = None,
) -> None:
    """將每次 askai 的輸入/輸出與必要統計 append 到 jsonl，供後續觀察改善。

    `trace_id` 可串到 discord_bot.log / askai_prompt.txt / llm_anomaly.log。
    `messages_sent` 只在失敗時保留（含圖片佔位符），成功時不存——askai_prompt.txt
    已記錄同源 prompt_record_log，重複落盤一份完整 messages 會讓 jsonl 體積膨脹過快。
    `error_kind` 在失敗時標記類型（no_choices / empty_content / http_error / timeout / connection / unknown）。
    `intel_meta` 是查遊戲情報的經過：開關、有沒有連上 search-mcp、呼叫了哪些工具（參數、花多久、結果 id 或錯誤）。
    """
    guild_id = interaction.guild.id if interaction.guild else None
    channel_id = interaction.channel.id if interaction.channel else None
    author_name = getattr(interaction.user, "display_name", interaction.user.name)

    # 只在錯誤時保留 messages_sent；圖片 base64 一律換成佔位符
    persisted_messages = (
        _strip_images_for_log(messages_sent) if error_kind is not None else None
    )

    record = {
        "time": datetime.now(APP_TZ).isoformat(),
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
        "intel_meta": intel_meta,
    }

    response_logger = get_or_create_file_logger(
        name="askai_response_trace",
        log_path=RESPONSE_LOG_PATH,
        mode="size",
        max_bytes=ASKAI_SETTINGS.response_log_max_bytes,
        backup_count=ASKAI_SETTINGS.response_log_backup_count,
    )
    response_logger.info(json.dumps(record, ensure_ascii=False))


async def send_followup_in_parts(interaction: discord.Interaction, text: str) -> None:
    """把 /askai 的回覆送出去；超過 Discord 一則 2000 字就切成多則，只有第一則 @ 發問者。

    問題（斜線指令可以打到 6000 字）＋回答＋引用網址很容易超過（2026-05-04 出過錯，使用者只看到「執行命令時
    發生錯誤」）。split_message 平衡暴雷標記時每段最多多 4 個字，所以留點餘裕。"""
    chunks = split_message(text, DISCORD_MESSAGE_LIMIT - 10)
    await interaction.followup.send(
        content=chunks[0],
        allowed_mentions=discord.AllowedMentions(users=[interaction.user]),
    )
    for chunk in chunks[1:]:
        await interaction.followup.send(content=chunk, allowed_mentions=discord.AllowedMentions.none())


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


@dataclass
class _AskaiInputs:
    """一次 /askai 收集完、要交給模型的東西，加上記錄要用的 meta（第 1 段的產出，第 2～4 段只讀它）。"""

    trace_id: str
    question: str                 # 使用者打的原句：回覆、記錄用
    resolved_question: str        # <@id> 換成「名字#尾碼」：檢索、工具輪用
    llm_question: str             # 再加上 X 貼文、別的伺服器表情的說明：給模型的問題
    system_prompt: str
    chat_context: list[str] | None
    bot_history: list[str] | None
    persona_context: list[str] | None
    target_profiles: list[str] | None
    asker_profile: str
    asker_display_name: str
    web_mode: str
    web_context: list[str] | None
    web_meta: dict[str, object]
    image_payload: list[str] | None
    image_meta: dict[str, str | int | bool] | None
    discord_context: list[dict[str, str]]
    discord_meta: dict[str, object]
    rag_context: list[dict[str, object]]
    rag_meta: dict[str, object]
    interaction: Any = None       # 記錄回應歷史要 guild／channel／user
    model: str | None = None      # 第 2 段決定後填回，第 3 段記錄用
    think: bool | None = None


def _context_limits(*, has_image: bool) -> dict[str, int]:
    """聊天紀錄要抓多少、送多少。視覺請求時縮短，降低 token 與 timeout 風險。

    `max_context_to_send` 在 retriever 內代表「聊天訊息數」，另會保留 1 行 header，
    所以最終 sent_count 可能是 6（1 header + 5 聊天）。
    """
    limits = {
        "max_context_messages": ASKAI_SETTINGS.max_context_messages,
        "min_recent_context": ASKAI_SETTINGS.min_recent_context,
        "max_relevant_context": ASKAI_SETTINGS.max_relevant_context,
        "max_context_to_send": ASKAI_SETTINGS.max_context_to_send,
    }
    if has_image:
        limits["max_context_messages"] = min(limits["max_context_messages"], 20)
        limits["min_recent_context"] = min(limits["min_recent_context"], 5)
        limits["max_relevant_context"] = min(limits["max_relevant_context"], 5)
        limits["max_context_to_send"] = 5
    return limits


def _resolve_mentions(question: str, guild) -> tuple[str, list[str]]:
    """把問題裡的 <@id> 換成「顯示名稱#尾碼」，跟 chat_history / persona card 的錨點對齊。

    否則 LLM 看到問題裡的「二口氣上吧」對不上卡標題「NNN#7489」（display_name vs alias 不同字串）。
    回傳 (換過的問題, 被提到的 user_id 字串清單)。
    """
    mentioned_user_ids = extract_mentioned_user_ids(question)
    resolved_question = question
    if mentioned_user_ids and guild:
        for uid_str in mentioned_user_ids:
            member = guild.get_member(int(uid_str))
            if member:
                name_with_id = person_anchor.label(member.display_name, uid_str)
                resolved_question = resolved_question.replace(f"<@{uid_str}>", name_with_id).replace(
                    f"<@!{uid_str}>", name_with_id
                )
    return resolved_question, mentioned_user_ids


def _start_web_search(resolved_question: str):
    """網路搜尋（開關 askai_web_search_mode）：keyword＝關鍵字判斷要不要查、背景先查好塞進 prompt（與 discord / rag
    檢索並行）；tool＝做成工具，由模型和遊戲情報一起決定查哪邊（兩邊不會同時塞資料，見 run_with_intel）；off＝不查。

    回傳 (web_mode, intent, run_web, 背景查詢的 task 或 None)。
    """
    web_mode = switches.current().askai_web_search_mode
    intent = should_search(resolved_question)
    run_web = web_mode == "keyword" and intent.triggered

    web_task: asyncio.Task | None = None
    if run_web:
        # 送給 SearXNG 的 query 用 cleaned_query（已剝除贅字／改寫成關鍵字）；引擎、類別、時間範圍照 intent 的路由，
        # 窄路由結果太少時由 search_web 換通用引擎補查
        web_task = asyncio.create_task(
            search_web(
                intent.cleaned_query or resolved_question,
                settings=WEB_SETTINGS,
                categories=intent.categories,
                time_range=intent.time_range,
                language=intent.language,
                logger_override=logger,
            )
        )
    return web_mode, intent, run_web, web_task


async def _collect_web(web_task, *, web_mode: str, run_web: bool, intent) -> tuple[list[str] | None, dict[str, object]]:
    """回收背景 web_task 結果（若有觸發），組 web_context 與 web_meta。"""
    web_context: list[str] | None = None
    # 工具模式也記下關鍵字會不會觸發（reason、trigger_keyword…），方便和模型實際的決定對照
    web_meta: dict[str, object] = {
        "mode": web_mode,
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
            if outcome.results or outcome.answers:
                web_context = format_web_context_lines(outcome.results, outcome.answers)
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
    return web_context, web_meta


def _participant_ids(discord_context: list[dict]) -> list[int]:
    """聊天紀錄裡的發言者 id，去重、照出現順序。"""
    ids: list[int] = []
    for item in discord_context:
        author_id_raw = str(item.get("author_id", "")).strip()
        if author_id_raw.isdigit():
            ids.append(int(author_id_raw))
    return list(dict.fromkeys(ids))


def _split_persona(rag_context: list[dict], asker_uid: str, mentioned_user_ids: list[str] | None):
    """人物卡三路分流（依優先序）：發問者本人的卡 → asker_profile；發問者明確 mention 的對象 → target_profiles，
    緊鄰問題；其餘參與者 → persona_context，背景資訊。

    回傳 (發問者的卡文字或 None, 被 @ 的人的卡清單, 其餘的卡清單或 None, 有卡的被 @ 的 id 集合)。
    """
    mentioned = set(mentioned_user_ids or [])
    asker_persona_text: str | None = None
    target_items: list[str] = []
    other_items: list[str] = []
    matched: set[str] = set()
    for item in rag_context or []:
        content = item.get("content")
        if not content or item.get("metadata") == "persona_card_header":
            continue
        person_id = item.get("person_id")
        if person_id == asker_uid and asker_persona_text is None:
            asker_persona_text = content
        elif person_id in mentioned:
            target_items.append(content)
            matched.add(person_id)
        else:
            other_items.append(content)
    return asker_persona_text, target_items, (other_items or None), matched


def _mention_hints(unmatched_mention_ids: set[str], guild) -> list[str]:
    """mention 了但 DB 沒卡：放退場提示，避免 LLM 反問或硬猜（新進群、未填自介、AI 觀察未跑、或已不在群內）。"""
    hints: list[str] = []
    for uid in unmatched_mention_ids:
        member = guild.get_member(int(uid)) if guild else None
        label = person_anchor.label(member.display_name if member else "某人", uid)
        hints.append(
            f"「{label}」— 群內尚無此人的 persona 紀錄；"
            f"可從 chat_history 推測，否則請老實說對此人不熟悉"
        )
    return hints


def _asker_profile_text(interaction: discord.Interaction, asker_display_name: str, asker_persona_text: str | None) -> str:
    """可信的發問者身份資訊（給 system block）。display_name 永遠帶 #XXXX，跟 chat_history / persona card 對齊。"""
    now_str = datetime.now(APP_TZ).strftime("%Y-%m-%d %H:%M (UTC+8)")
    guild_name = interaction.guild.name if interaction.guild else "(DM)"
    channel_name = getattr(interaction.channel, "name", "") or "(unknown)"
    lines = [
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
    return "\n".join(lines)


# ── 第 3 段：記錄 ───────────────────────────────────────────────────────
def _askai_record(inputs: "_AskaiInputs", result, *, intel_meta: dict[str, object], web_tools) -> None:
    """三份紀錄：askai_prompt.txt（真正送出的 prompt）、askai_prompt_debug.txt（檢索／融合細節）、回應歷史 jsonl。
    任何一份寫失敗只記 WARNING，不影響回覆。"""
    trace_id = inputs.trace_id
    try:
        prompt_trace_logger = get_or_create_file_logger(
            name="askai_prompt_trace",
            log_path=PROMPT_LOG_PATH,
            mode="time",
            when=ASKAI_SETTINGS.prompt_log_when,
            interval=ASKAI_SETTINGS.prompt_log_interval,
            backup_count=ASKAI_SETTINGS.prompt_log_backup_count,
        )
        prompt_trace_logger.info(_format_log_block(title=f"ASKAI_PROMPT trace={trace_id}", body=result.prompt_record_log))
    except Exception as exc:
        logger.warning("寫入 askai prompt 失敗 trace=%s: %s", trace_id, exc)

    try:
        retrieval_debug = inputs.discord_meta.get("retrieval_debug")
        prompt_debug_text = build_askai_prompt_log(
            system_prompt=inputs.system_prompt,
            question=inputs.question,
            discord_context=inputs.discord_context,
            rag_context=inputs.rag_context,
            discord_meta=inputs.discord_meta,
            rag_meta=inputs.rag_meta,
            retrieval_debug=retrieval_debug if isinstance(retrieval_debug, dict) else None,
            image_meta=inputs.image_meta,
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
                    f"<prompt_record_log>\n{result.prompt_record_log}\n</prompt_record_log>\n"
                    f"<debug>\n{prompt_debug_text}\n</debug>"
                ),
            )
        )
    except Exception as exc:
        logger.warning("寫入 askai prompt debug 失敗 trace=%s: %s", trace_id, exc)

    try:
        append_askai_response_log(
            interaction=inputs.interaction,
            question=inputs.question,
            reply=result.reply,
            model=inputs.model,
            think=inputs.think,
            discord_meta=inputs.discord_meta,
            rag_meta=inputs.rag_meta,
            web_meta=inputs.web_meta,
            trace_id=trace_id,
            messages_sent=result.messages_sent,
            error_kind=result.error_kind,
            intel_meta=intel_meta,
        )
    except Exception as exc:
        logger.warning("寫入 askai response history 失敗 trace=%s: %s", trace_id, exc)


# ── 第 4 段：送出 ───────────────────────────────────────────────────────
async def _askai_send(interaction: discord.Interaction, inputs: "_AskaiInputs", reply: str, image, cancel_view, thinking_msg) -> None:
    """用 followup 回覆（避免互動超時）：@ 發問者、問題、回答、附圖網址；完成後把取消按鈕改成「已完成」。"""
    response_lines = [
        f"{interaction.user.mention}",
        f"❓ **問題：** {inputs.question}",
        f"💬 **回答：** {reply}",
    ]
    if image and image.url:
        response_lines.append(f"🖼️ **圖片：** {image.url}")
    response_text = "\n".join(response_lines)

    await send_followup_in_parts(interaction, response_text)

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


class LLMCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.llm_service = LLMService()
        self._askai_worker_task: asyncio.Task | None = None

    def _ensure_askai_worker(self) -> None:
        """確保處理 AI 請求的背景任務正在運行。"""
        if self._askai_worker_task is None or self._askai_worker_task.done():
            self._askai_worker_task = supervise(self._askai_worker, name="askai_worker")

    @app_commands.command(name="askai", description="向 AI 詢問問題")
    @app_commands.describe(
        question="想問 AI 的問題",
        image="可選的圖片（jpg/png/webp/gif；動畫 gif 只看得到第一幀）",
    )
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

        if imagegen_busy():
            # 產圖會獨佔 GPU 數十分鐘，這期間 chat_raw 會卡在閘門上。仍然照常排隊
            # （不丟掉使用者的問題），但要講清楚為什麼慢——差別是使用者看到
            # 「機器人壞了」還是「機器人在忙」。
            queue_msg = "🎨 目前正在排程產圖，GPU 被佔用中；你的問題已排進佇列，產圖結束後會立刻處理"
        elif pending:
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
        """處理一次 /askai（在排隊工作者裡執行）：收集上下文 → 生成 → 記錄 → 送出。

        四段各自是一個函式，這裡只排順序；哪一段要改，改那一段就好。取消檢查放在
        「上下文收集完、叫模型前」與「生成途中」兩處。
        """
        # trace_id 串接所有 askai log（discord_bot.log / askai_prompt.txt /
        # askai_response_history.jsonl / llm_anomaly.log）— 出錯時複製此 ID 即可一次定位
        trace_id = f"ask-{str(interaction.user.id)[-4:]}-{int(time.time() * 1000)}"
        logger.info("askai 開始 trace=%s user_id=%s q=%r", trace_id, interaction.user.id, question[:30])

        # 標記前景（大模型）活動：功能二的背景插話會在此窗口內讓位，避免換模型 ping-pong
        note_foreground_activity()

        cancel_view = _AskaiCancelButton(interaction.user.id, cancel_event) if cancel_event else None
        thinking_msg = await interaction.followup.send(
            "🔄 AI 思考中，請耐心等候...",
            ephemeral=True,
            view=cancel_view,
            wait=True,
        )

        inputs = await self._askai_gather(interaction, question, image, trace_id=trace_id)
        if inputs is None:
            return  # 圖不合格，已回覆使用者

        # 取消檢查：context 檢索完、LLM 呼叫前
        if cancel_event and cancel_event.is_set():
            return

        generated = await self._askai_generate(inputs, interaction, cancel_event, thinking_msg)
        if generated is None:
            return  # 使用者取消、或底層連帶取消（已回覆）
        result, intel_meta, web_tools = generated

        _askai_record(inputs, result, intel_meta=intel_meta, web_tools=web_tools)
        await _askai_send(interaction, inputs, result.reply, image, cancel_view, thinking_msg)

    # ── 第 1 段：收集上下文 ────────────────────────────────────────────────
    async def _askai_gather(
        self,
        interaction: discord.Interaction,
        question: str,
        image: discord.Attachment | None,
        *,
        trace_id: str,
    ) -> "_AskaiInputs | None":
        """把要給模型的東西收齊：聊天紀錄、人物卡、名字對照、發問者資料、網搜（keyword 模式）、圖。

        順序刻意保留：網搜先在背景起跑，和聊天／人物卡檢索並行；人物卡檢索要等聊天紀錄
        回來（參與者名單從那裡來）。圖不合格回 None（已回覆使用者）。
        """
        system_prompt = load_system_prompt()
        guild = interaction.guild
        resolved_question, mentioned_user_ids = _resolve_mentions(question, guild)
        web_mode, intent, run_web, web_task = _start_web_search(resolved_question)

        limits = _context_limits(has_image=image is not None)
        discord_context, bot_history_context, discord_meta = await retrieve_discord_context(
            interaction,
            resolved_question,
            max_context_messages=limits["max_context_messages"],
            min_recent_context=limits["min_recent_context"],
            max_relevant_context=limits["max_relevant_context"],
            max_context_to_send=limits["max_context_to_send"],
            taipei_tz=APP_TZ,
            logger=logger,
        )
        participant_user_ids = _participant_ids(discord_context)

        # retrieve_rag_context 內部呼叫 LlamaIndex 同步 API（embedding + pgvector），
        # 在 executor 中執行以避免阻塞 event loop（影響語音 heartbeat 等）。
        # mentioned_user_ids 必須顯式傳入：resolved_question 已把 <@id> 換成 display_name，
        # 內部重抽會失敗，會導致 +35 mention boost 永遠不生效（2026-04-27 修正）
        member_names = member_names_from_guild(guild)
        rag_context, rag_meta = await asyncio.get_running_loop().run_in_executor(
            None,
            functools.partial(
                retrieve_rag_context_sync,
                resolved_question,
                guild.id if guild else None,
                interaction.user.id if interaction.user else None,
                participant_user_ids,
                logger,
                5,
                mentioned_user_ids=mentioned_user_ids,
                member_names=member_names,
            ),
        )

        web_context, web_meta = await _collect_web(web_task, web_mode=web_mode, run_web=run_web, intent=intent)

        # 聊天記錄：每行已是「顯示名稱#尾碼: 內容」（_build_discord_context_item）。其他叫法
        # （自介暱稱、全域名稱…）統一放 persona_context 尾端的「名字對照」，不再逐行加註——
        # 以前只有拿到人物卡的人才有加註，卡最多 3 張
        chat_context = [item["content"] for item in discord_context if item.get("content")] or None
        bot_history = [item["content"] for item in bot_history_context if item.get("content")] or None

        asker_uid_str = str(interaction.user.id)
        asker_persona_text, target_items, persona_context, matched_mention_ids = _split_persona(
            rag_context, asker_uid_str, mentioned_user_ids,
        )
        target_items += _mention_hints(set(mentioned_user_ids or []) - matched_mention_ids, guild)
        target_profiles = target_items or None

        # 名字對照：發問者、聊天裡的人、被提到的人、有卡的人，誰還有別的叫法
        name_map = await asyncio.get_running_loop().run_in_executor(
            None,
            name_map_lines,
            guild.id if guild else 0,
            [
                asker_uid_str,
                *(item.get("author_id") for item in discord_context or []),
                *(mentioned_user_ids or []),
                *(item.get("person_id") for item in rag_context or []),
            ],
            member_names,
        ) if guild else []
        if name_map:
            persona_context = [*(persona_context or []), *name_map]

        asker_display_name = person_anchor.label(
            getattr(interaction.user, "display_name", interaction.user.name), asker_uid_str,
        )
        asker_profile = _asker_profile_text(interaction, asker_display_name, asker_persona_text)

        image_payload = None
        if image:
            image_payload = await self._prepare_image_payload(interaction, image)
            if image_payload is None:
                return None

        # X 貼文連結、別的伺服器的表情：補上說明與圖給模型看（只加在給模型的問題，檢索與網搜照舊用原問題）
        tweet_notes, tweet_images = await expand_tweets(question)
        emoji_notes, emoji_images = await external_emoji_context(question)
        extra_notes = tweet_notes + emoji_notes
        llm_question = resolved_question + ("\n\n" + "\n".join(extra_notes) if extra_notes else "")
        if tweet_images or emoji_images:
            image_payload = (image_payload or []) + tweet_images + emoji_images

        image_meta = None
        if image and image_payload:
            image_meta = {
                "attached": True,
                "count": len(image_payload),
                "filename": image.filename or "",
                "size_bytes": image.size or 0,
            }

        return _AskaiInputs(
            trace_id=trace_id, question=question, resolved_question=resolved_question, llm_question=llm_question,
            system_prompt=system_prompt, chat_context=chat_context, bot_history=bot_history,
            persona_context=persona_context, target_profiles=target_profiles,
            asker_profile=asker_profile, asker_display_name=asker_display_name,
            web_mode=web_mode, web_context=web_context, web_meta=web_meta,
            image_payload=image_payload, image_meta=image_meta,
            discord_context=discord_context, discord_meta=discord_meta, rag_context=rag_context, rag_meta=rag_meta,
            interaction=interaction,
        )

    # ── 第 2 段：生成 ───────────────────────────────────────────────────────
    async def _askai_generate(
        self,
        inputs: "_AskaiInputs",
        interaction: discord.Interaction,
        cancel_event: asyncio.Event | None,
        thinking_msg,
    ):
        """叫模型（含情報與網搜工具輪）。回傳 (結果, intel_meta, web_tools)；使用者取消或底層連帶取消回 None。"""
        target_model = self.llm_service.resolve_request_model()
        target_think = self.llm_service.resolve_request_think()
        inputs.model, inputs.think = target_model, target_think
        llm_question = inputs.llm_question

        # Bot 自身身份：伺服器暱稱優先 → 全域 username → None（僅極端情境）。
        # 帶 #XXXX 錨點，與 <bot_history> 區塊內各行的 name_with_anchor 格式一致，
        # 讓 name 屬性精準對上塊內發言。
        bot_display_name = None
        if interaction.guild and interaction.guild.me:
            bot_display_name = name_with_anchor(interaction.guild.me)
        elif interaction.client.user:
            bot_display_name = name_with_anchor(interaction.client.user)

        # 查遊戲情報（llm.retrievers.intel → search-mcp）：開關開著才連；連不上就照原本的方式回答。
        # 要不要查、查什麼由模型決定（之前定案：關鍵字觸發會漏掉該查的，見 generate_reply 的工具輪）
        intel_mode = switches.current().askai_intel_search_mode
        intel_meta: dict[str, object] = {"mode": intel_mode}

        async def _generate(tool_runner=None):
            return await self.llm_service.generate_reply(
                prompt=llm_question,
                system=inputs.system_prompt,
                chat_context=inputs.chat_context,
                bot_history=inputs.bot_history,
                persona_context=inputs.persona_context,
                target_profiles=inputs.target_profiles,
                web_context=inputs.web_context,
                images=inputs.image_payload,
                model=target_model,
                think=target_think,
                asker_profile=inputs.asker_profile,
                asker_display_name=inputs.asker_display_name,
                bot_display_name=bot_display_name,
                # 閒置 1h 後才釋放 VRAM，避開反覆 unload/reload 觸發的 Windows
                # ephemeral port 與 runner crash（Ollama 時代的實戰教訓，值刻意保留）。
                # ⚠️ 只有 Ollama 吃這個值：Lemonade 沒有 TTL 概念，會被
                # `_build_chat_extra_body` 丟進 ignored。Lemonade 下要讓出 VRAM 只有
                # 一條路——產圖排程在 `gpu_exclusive` 內呼叫 `LLMService.release_model()`。
                keep_alive="1h",
                trace_id=inputs.trace_id,
                tool_runner=tool_runner,
                max_tool_rounds=INTEL_SETTINGS.max_tool_rounds,
            )

        # 網路搜尋的工具模式：和情報工具合成一組交給模型（輪數兩邊共用 INTEL_SETTINGS 的值）
        web_mode = inputs.web_mode
        web_tools = WebSearchTools(settings=WEB_SETTINGS) if web_mode == "tool" else None

        # 用 asyncio.Task 包裝，取消時可中斷 LLM 的 HTTP 請求；查情報、查網路都在同一個 task 裡，按取消時一起中斷
        llm_task = asyncio.create_task(run_with_intel(
            _generate, question=inputs.resolved_question, enabled=intel_mode == "on", meta=intel_meta,
            settings=INTEL_SETTINGS, also=[web_tools] if web_tools else (),
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
                return None
        else:
            await asyncio.wait([llm_task])
        if llm_task.cancelled():
            # 不是使用者按的取消，回答卻被取消了（例如底層連線出錯時的連帶取消）：當成這次失敗、正常結束，
            # 別讓 CancelledError 一路穿出去——排隊的工作者接不到它會整個結束，後面排隊的人都卡住
            logger.error("askai 回答意外被取消 trace=%s", inputs.trace_id)
            if thinking_msg:
                try:
                    await thinking_msg.edit(content="⚠️ 這次沒有順利回答，請再試一次。", view=None)
                except Exception:
                    pass
            return None
        llm_result = llm_task.result()

        if intel_mode == "on":
            intel_calls = intel_meta.get("calls") or []
            logger.info("askai 查情報 trace=%s 連上=%s 呼叫=%s", inputs.trace_id, intel_meta.get("connected"),
                        [(c.get("tool"), c.get("elapsed_ms"), c.get("error") or len(c.get("result_ids") or []))
                         for c in intel_calls])
        if web_tools is not None:
            inputs.web_meta["calls"] = web_tools.calls
            logger.info("askai 網路搜尋 trace=%s 呼叫=%s", inputs.trace_id,
                        [(c.get("kind"), c.get("query"), c.get("elapsed_ms"),
                          c.get("error") or f"{c.get('result_count')} 筆＋答案 {c.get('answer_count', 0)}")
                         for c in web_tools.calls])
        return llm_result, intel_meta, web_tools

    async def _prepare_image_payload(
        self,
        interaction: discord.Interaction,
        image: discord.Attachment,
    ) -> list[str] | None:
        """下載並轉換圖片為 Ollama 可接受的 base64 清單。"""
        filename = (image.filename or "").lower()
        if not is_vision_image(filename):
            await interaction.followup.send(
                "⚠️ 目前僅支援 " + " / ".join(e.lstrip(".") for e in VISION_IMAGE_EXTS) + " 圖片。",
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

        # 動圖拆成關鍵幀再送（後端直接吃 gif 只讀得到第一幀）；靜圖回原圖一張
        frames = extract_key_frames(image_bytes, max_frames=DEFAULT_MAX_FRAMES)
        return [base64.b64encode(f).decode("utf-8") for f in frames]


class PersonalityCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._extract_tasks: set[asyncio.Task] = set()

    def _track_task(self, task: asyncio.Task) -> None:
        self._extract_tasks.add(task)

        def _cleanup(done_task: asyncio.Task) -> None:
            self._extract_tasks.discard(done_task)

        task.add_done_callback(_cleanup)


    @app_commands.command(
        name="persona_agent_test",
        description="測試人格 Agent（管理員限定，只跑一人；預設不寫入資料庫）",
    )
    @app_commands.describe(
        target="要分析的成員",
        model="指定模型（不填則跟夜間批次一樣：personality_model，未設才用主 model）",
        save="是否寫入 persona_agent 版本表（預設否，只看結果不留痕）",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def persona_agent_test_cmd(
        self,
        interaction: discord.Interaction,
        target: discord.Member,
        model: str | None = None,
        save: bool = False,
    ):
        """對單一成員跑一次 persona agent（除錯入口）。

        **為什麼一定要有這個指令**：agent 走 `stream_exclusive()` 那把 process 內的
        全域鎖來跟 /askai、插話 協調「一次只做一件事」。用 `docker exec` 在旁邊的
        process 跑，鎖是各自一份 → 禮讓機制完全失效、與插話正面對撞（實測：共用 KV
        池被瓜分導致 context 超限、吞吐 33→7 tok/s）。**必須跑在 bot 自己的 process 內**
        才測得到真實行為，這個指令就是那個入口。M4 排程上線後也是手動抽查的工具。

        預設只回報與寫 log、不碰任何資料表；`save=True` 時跟夜間批次走同一條路徑，
        寫入版本表與 runs 表。模型不指定時也跟夜間批次用同一個，結果才代表 04:00 的行為。
        """
        if not interaction.guild:
            await safe_send_interaction_message(
                interaction, "⚠️ 僅限伺服器內使用。", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        from llm.persona.agent import agent as persona_agent
        from llm.persona.agent import tools as persona_tools

        from sys_settings.llm_settings import (
            LLMServiceSettings,
            load_llm_runtime_config,
        )
        runtime_config = load_llm_runtime_config(
            LLMServiceSettings().llm_runtime_model_path
        )
        target_model = model or runtime_config.personality_model or runtime_config.model
        user_id = str(target.id)
        guild_id = interaction.guild.id

        await interaction.followup.send(
            f"🔬 persona agent 開始跑 **{target.display_name}**（model=`{target_model}`）\n"
            f"會禮讓 /askai 與插話，白天可能要等上一段時間。\n"
            f"**結果會私訊給你** —— interaction token 只有 15 分鐘，這支常跑更久。",
            ephemeral=True,
        )

        async def _run_and_report() -> None:
            from llm.persona.agent.batch import load_nickname_note
            from llm.persona.member_names import member_names_from_guild

            ctx = persona_tools.ToolContext.build(
                guild_id=guild_id,
                allowed_ids=[user_id],   # 白名單只放這一人，工具層會擋掉其他查詢
                # 跟每晚批次附同一份名字表，手動跑的結果才代表晚上會寫出什麼
                nickname_note=await load_nickname_note(
                    guild_id, target_id=user_id,
                    member_names=member_names_from_guild(interaction.guild),
                ),
            )
            try:
                run, validated = await persona_agent.run_and_persist(
                    user_id=user_id, guild_id=guild_id, ctx=ctx,
                    model=target_model,
                    run_id=f"test-{interaction.id}",
                    save=save,
                )
            except Exception as exc:
                logger.error("persona_agent_test 失敗: %s", exc, exc_info=True)
                await self._report_agent_result(interaction, target, None, str(exc))
                return

            # 完整結果一律進 log：Discord 有長度限制、followup token 也只有 15 分鐘，
            # 跑久了送不出去也不能讓結果消失
            logger.info(
                "persona_agent_test 結果 target=%s status=%s steps=%d tools=%d "
                "tokens≈%d %.0fs diff=%s",
                user_id, run.status, run.steps, len(run.trace),
                run.estimated_tokens, run.duration_ms / 1000,
                json.dumps(run.diff, ensure_ascii=False) if run.diff else None,
            )
            await self._report_agent_result(
                interaction, target, run, None, validated=validated, saved=save
            )

        task = asyncio.create_task(_run_and_report())
        self._track_task(task)

    async def _report_agent_result(
        self,
        interaction: discord.Interaction,
        target: discord.Member,
        run,
        error: str | None,
        *,
        validated=None,
        saved: bool = False,
    ) -> None:
        """把 agent 結果私訊給發起人；送不出去只記 log，不讓例外往外炸。

        **為什麼用 DM 而不是 followup**：interaction token 只有 15 分鐘，而這支 agent
        會禮讓 /askai 與插話，實測跑過 34 分鐘——結果只能吞掉（實際發生過
        `401 Invalid Webhook Token`）。DM 沒有時限，而且同樣只有發起人看得到。

        **為什麼送出前要再驗一次管理員**：權限檢查在指令入口做過，但那是幾十分鐘前的事。
        中間權限被移除的話，結果就不該再送過去——內容含成員的完整發言證據。
        縱深防禦：入口擋一次、出口再擋一次，兩處都用同一支 `check_guild`。
        """
        if error is not None:
            summary = f"❌ persona agent 執行失敗：`{error[:300]}`"
            attachment = None
        else:
            icon = {"ok": "✅", "context_exceeded": "🈵", "max_steps": "⏱️"}.get(
                run.status, "⚠️"
            )
            tool_lines = "\n".join(
                f"  step{t.step} {t.tool} {t.arguments[:60]} ({t.elapsed_ms}ms)"
                for t in run.trace
            ) or "  （沒有任何工具呼叫）"
            summary = (
                f"{icon} **{target.display_name}** status=`{run.status}` "
                f"steps={run.steps} 工具={len(run.trace)} "
                f"tokens≈{run.estimated_tokens} 耗時={run.duration_ms / 1000:.0f}s\n"
                f"```\n{tool_lines[:1200]}\n```"
            )
            if run.thinking_exhausted:
                summary += "\n⚠️ thinking 把 context 用光，本次未經深思（品質要打折看）"
            details = ""
            if validated is not None:
                summary += (
                    f"\n驗證：通過 **{len(validated.accepted)}** 項／拒絕 "
                    f"{len(validated.rejected)} 項｜證據 {validated.evidence_claimed} 個、"
                    f"假 {validated.evidence_bogus} 個（幻覺率 {validated.hallucination_rate}）"
                )
                if validated.skip_reason:
                    summary += f"\n未寫入版本：{validated.skip_reason}"
                for rej in validated.rejected[:3]:
                    details += f"\n  ✗ {rej['change'].get('trait')}：{rej['why'][:90]}"
                # 同一項被交代多次時落選／併入的（不算退件，但除錯時要看得到）
                superseded = (validated.ref_accounting or {}).get("superseded") or []
                for sup in superseded[:3]:
                    details += f"\n  ↺ {sup['change'].get('trait')}：{sup['why'][:90]}"
            summary += f"\n寫入版本表：{'是' if saved else '否（dry-run）'}"
            if run.error:
                summary += f"\nerror: `{run.error[:200]}`"
            # 細節放最後：訊息超過私訊上限時是從尾巴截，被切掉的只會是細節、不會是上面的狀態
            summary += details
            attachment = None
            if run.diff is not None:
                payload = json.dumps(run.diff, ensure_ascii=False, indent=2)
                attachment = discord.File(
                    io.BytesIO(payload.encode("utf-8")),
                    filename=f"persona_diff_{target.id}.json",
                )

        # 出口再驗一次管理員（沿用入口那支 check_guild，不另寫判斷）
        if not await check_guild(interaction, admin_only=True):
            logger.warning(
                "persona_agent_test 結果不送出：發起人 %s 已非管理員", interaction.user
            )
            return

        if not await send_dm(interaction.user, content=summary[:1900], file=attachment):
            logger.warning(
                "persona_agent_test 結果無法私訊（可能對方關閉 DM）；結果已寫入 log"
            )

    @app_commands.command(
        name="ai_diary", description="立即產生並發布 AI 今日日記（管理員限定）"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def ai_diary_cmd(self, interaction: discord.Interaction):
        """手動觸發每日日記（不必等到午夜）；用來測試與臨時補發。"""
        if not interaction.guild:
            await safe_send_interaction_message(
                interaction, "⚠️ 僅限伺服器內使用。", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        from llm.ambient.ambient_diary import run_daily_reflection
        try:
            diary = await run_daily_reflection(self.bot)
        except Exception as exc:
            logger.error("手動 AI 日記失敗: %s", exc, exc_info=True)
            diary = None
        if diary:
            await interaction.followup.send(
                "🖊️ 今天的日記寫好、發到日記頻道了。", ephemeral=True
            )
        else:
            await interaction.followup.send(
                "⚠️ 沒寫成——可能未設定 AI 日記頻道、或生成失敗（看 log）。", ephemeral=True
            )


async def setup(bot):
    await bot.add_cog(LLMCommands(bot))
    await bot.add_cog(PersonalityCommands(bot))
