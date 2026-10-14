import os
import sys
import time
import logging
import asyncio
import json
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from utils.logger_config import configure_logging  # import 即套用 settings/logging.json
from sys_settings.paths import LOGS_DIR
from utils.utils import CONFIG_FILE, safe_send_interaction_message
from services.relay.telegram_relay_service import (
    DiscordMessagePublisher,
    MessageRelayWorker,
    MessageRouteResolver,
    TelegramMessageRepository,
    TelegramRenderAdapter,
    build_telegram_pg_dsn_from_env,
)
from utils.background_tasks import periodic, spawn, supervise

# 載入環境變數
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# 設置日誌系統（使用統一配置）
configure_logging()
# 主程式以 `python discord_bot.py` 執行，__name__ 會是 __main__，所以這裡明確命名
logger = logging.getLogger("discord_bot")

# 記錄環境變數和系統信息（安全方式）
logger.info(f"Discord 機器人啟動於 {time.strftime('%Y-%m-%d %H:%M:%S')}")
logger.info(f"Python 版本: {sys.version}")
logger.info(f"日誌文件位置: {LOGS_DIR / 'discord_bot.log'}")
logger.info(f"環境變數中的 DISCORD_TOKEN: {'已設置' if TOKEN else '未設置'}")
logger.info(f"當前工作目錄: {os.getcwd()}")
logger.info(f"當前目錄內容: {os.listdir('.')}")
logger.info(f"日誌目錄內容: {os.listdir(LOGS_DIR) if LOGS_DIR.exists() else '日誌目錄不存在'}")

# 設定意圖
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.members = True  # 啟用成員意圖以獲取成員信息
intents.presences = True  # 啟用狀態意圖以獲取用戶狀態信息
intents.voice_states = True

# 指令模組清單
COMMAND_MODULES = [
    'commands.article_commands',
    'commands.community_lookup_commands',
    'commands.forum_monitor',
    'commands.llm_commands',
    'commands.management_commands',
    'commands.music_commands',
    'commands.periodic_reminder_commands',
    'commands.rollcall_commands',
    'commands.shop_commands',
    'commands.telegram_quarantine_commands',
    'commands.trade_commands',
    'commands.test_commands',
    'commands.user_commands'
]

# 建立機器人實例
class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='!', intents=intents)
        self.echo_tracker = {}
        self.ambient_tracker = {}  # 功能二：per-channel 插話冷卻/計數狀態
        self.telegram_relay_worker = None

    async def setup_hook(self):
        logger.info("正在載入指令模組...")

        # 載入所有指令模組
        for module in COMMAND_MODULES:
            try:
                await self.load_extension(module)
                logger.info(f"已載入指令模組: {module}")
            except Exception as e:
                logger.error(f"載入指令模組 {module} 時發生錯誤: {str(e)}", exc_info=True)

        # 同步斜線命令
        try:
            logger.info("開始同步斜線命令...")
            # 同步全局命令
            cmds = await self.tree.sync()
            logger.info(f"已同步 {len(cmds)} 個全局斜線命令")

        except Exception as e:
            logger.error(f"斜線命令同步失敗: {str(e)}", exc_info=True)

bot = MyBot()

@bot.event
async def on_ready():
    """連上 Discord 後把該啟動的東西依序掛上。

    這裡只決定「什麼時候跑什麼、順序、接線」；每一步的實作在各自的模組（維護五步在
    `llm.persona.daily_maintenance`、日記在 `llm.ambient.ambient_diary`、三個定期寫入在各自的 store）。
    on_ready 在 reconnect 時會再觸發，長跑迴圈與背景工作都只掛一次。
    """
    logger.info(f'機器人 {bot.user.name} 已連接到 Discord!')
    logger.info(f'機器人 ID: {bot.user.id}')
    _refresh_person_anchors()
    _log_invite_url()
    await _preload_stickers()
    _start_background_loops()
    await _ensure_tables()
    _start_embedding_backfill()
    await auto_start_article_monitor(bot)
    await auto_start_telegram_relay(bot)
    await auto_start_notify_server(bot)   # 接收 Scraper webhook 通知
    await _log_registered_commands()


def _log_invite_url() -> None:
    permissions = discord.Permissions(
        send_messages=True,
        read_messages=True,
        add_reactions=True,
        embed_links=True,
        attach_files=True,
        read_message_history=True,
        connect=True,
        speak=True,
    )
    invite_url = discord.utils.oauth_url(
        bot.user.id,
        permissions=permissions,
        scopes=("bot", "applications.commands"),  # 要含 applications.commands，斜線命令才會出現
    )
    logger.info(f"邀請連結: {invite_url}")
    logger.info("如果斜線命令未顯示，請使用上面的連結重新邀請機器人，確保包含應用程序命令權限")


async def _preload_stickers() -> None:
    """預載貼圖描述快取：向 Discord 要清單是介面層的事，快取本身（技術層）不認 Discord。"""
    from llm.preprocess.sticker_cache import remember as remember_stickers
    loaded = 0
    for guild in bot.guilds:
        try:
            loaded += remember_stickers(await guild.fetch_stickers())
        except Exception as exc:
            logger.warning("載入伺服器 %s 的貼圖失敗: %s", guild.id, exc)
    logger.info("已載入 %d 個貼圖描述", loaded)


def _start_once(task_attr: str, name: str, factory, started_log: str) -> None:
    """掛一個該一直跑的迴圈，只掛一次：task 記在 `bot.<task_attr>`、旗標記在 `bot.<task_attr>_started`。"""
    flag = f"{task_attr}_started"
    if getattr(bot, flag, False):
        return
    setattr(bot, task_attr, supervise(factory, name=name))
    setattr(bot, flag, True)
    logger.info(started_log)


def _start_background_loops() -> None:
    """五個該一直跑的迴圈，照原本的順序掛上；三個定期寫入用 `periodic`，兩個要算時刻的排程在各自的模組。"""
    from llm.ambient import ambient_diary, ambient_memory
    from llm.persona import daily_maintenance
    from llm.storage import raw_message_store, store_chat
    from sys_settings.llm_settings import AmbientChatSettings

    chat_every = store_chat.FLUSH_INTERVAL_SECONDS
    raw_every = raw_message_store.RAW_FLUSH_INTERVAL_SECONDS
    memory_every = AmbientChatSettings().memory_flush_interval_seconds
    _start_once("_chat_persist_task", "聊天記憶定期寫入",
                lambda: periodic(chat_every, store_chat.flush_buffer, name="聊天記憶定期寫入"),
                "聊天訊息定期持久化已啟動（每 %d 秒）" % chat_every)
    _start_once("_raw_persist_task", "原始訊息備份定期寫入",
                lambda: periodic(raw_every, raw_message_store.flush_raw_buffer, name="原始訊息備份定期寫入"),
                "raw 訊息備份定期 flush 已啟動（每 %d 秒）" % raw_every)
    _start_once("_ambient_memory_task", "插話記憶定期抽取",
                lambda: periodic(memory_every, ambient_memory.maybe_flush, name="插話記憶定期抽取"),
                "插話記憶定期抽取已啟動（每 %.0f 秒檢查）" % memory_every)
    _start_once("_personality_task", "每日維護排程", lambda: daily_maintenance.schedule_loop(bot),
                "每日維護排程已啟動（每日 04:00 UTC+8，含啟動補跑檢查）")
    _start_once("_diary_task", "日記排程", lambda: ambient_diary.schedule_loop(bot),
                "AI 日記定期排程已啟動（每日 00:00 UTC+8）")


async def _ensure_tables() -> None:
    """建表都是 idempotent、失敗只記 log：寫入功能不該拖垮 bot 啟動。"""
    try:
        # 插話寫入 + 日記讀取都靠它
        from llm.storage.ai_interactions_store import ensure_table as ensure_ai_interactions
        await asyncio.to_thread(ensure_ai_interactions)
    except Exception as exc:
        logger.error("ai_interactions 建表啟動失敗: %s", exc, exc_info=True)
    try:
        from llm.persona.agent.store import ensure_table as ensure_persona_agent
        await asyncio.to_thread(ensure_persona_agent)
    except Exception as exc:
        logger.warning("persona agent 資料表初始化失敗（agent 將無法寫入）: %s", exc)


def _start_embedding_backfill() -> None:
    """v2 風格召回：背景回填既有互動紀錄的 embedding（idempotent，embed 端就緒後逐批做，不阻塞啟動）。"""
    if getattr(bot, "_ai_emb_backfill_started", False):
        return
    bot._ai_emb_backfill_started = True
    try:
        from llm.storage.ai_interactions_store import backfill_embeddings
        spawn(asyncio.to_thread(backfill_embeddings), name="ai_interactions 向量回填")
        logger.info("ai_interactions embedding 背景回填已排程")
    except Exception as exc:
        logger.error("ai_interactions embedding 回填啟動失敗: %s", exc, exc_info=True)


async def _log_registered_commands() -> None:
    try:
        commands = await bot.tree.fetch_commands()
        logger.info(f"已註冊 {len(commands)} 個全局斜線命令:")
        for cmd in commands:
            logger.info(f"  /{cmd.name} - {cmd.description}")
    except Exception as e:
        logger.error(f"獲取命令列表失敗: {str(e)}")


# 添加斜線命令交互回應處理
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error):
    """處理斜線命令錯誤"""
    logger.error(f"斜線命令錯誤: {str(error)}")

    if isinstance(error, app_commands.errors.CommandOnCooldown):
        await safe_send_interaction_message(
            interaction,
            f"請稍等片刻再使用此命令。剩餘冷卻時間: {error.retry_after:.2f}秒",
            ephemeral=True
        )
    else:
        await safe_send_interaction_message(
            interaction,
            f"執行命令時發生錯誤: {str(error)}",
            ephemeral=True
        )

@bot.event
async def on_message(message):
    # 避免機器人回應自己的訊息
    if message.author == bot.user:
        return

    # 偵測 x.com / twitter.com 貼文連結，只在「影片貼文」時貼出 fixupx 可預覽版本。
    # 圖片貼文 Discord 原生預覽就正常，不轉。格式擋掉/類型查詢/開 session 都收在
    # select_video_links 內：非 x.com 訊息只付一次 regex 成本，命中才連網。
    if message.content:
        from utils.link_fix import select_video_links
        fixed_links = await select_video_links(message.content)
        if fixed_links:
            try:
                await message.channel.send(fixed_links)
            except Exception as exc:
                logger.warning(f'發送 fixupx 預覽連結失敗: {exc}')
            # 壓掉原訊息的失敗/破圖預覽卡（需 Manage Messages 權限，缺權限則略過）
            try:
                await message.edit(suppress=True)
            except discord.Forbidden:
                logger.warning('壓制原訊息預覽失敗：缺少 Manage Messages 權限')
            except Exception as exc:
                logger.warning(f'壓制原訊息預覽失敗: {exc}')

    # 記錄接收到的訊息
    if message.content:
        logger.debug(f'收到訊息: {message.content} (來自: {message.author}, 頻道: {message.channel.name} [ID: {message.channel.id}])')

        normalized_content = message.content.strip()
        if normalized_content:
            channel_id = message.channel.id
            tracker = bot.echo_tracker.get(channel_id)

            if not tracker or tracker["content"] != normalized_content:
                tracker = {"content": normalized_content, "user_ids": set()}
                bot.echo_tracker[channel_id] = tracker

            if message.author.id not in tracker["user_ids"]:
                tracker["user_ids"].add(message.author.id)

            if len(tracker["user_ids"]) >= 3:
                await message.channel.send(normalized_content)
                logger.info(
                    "三位不同使用者重複相同訊息，機器人已回覆: %s (頻道: %s [ID: %s], 觸發使用者: %s)",
                    normalized_content,
                    message.channel.name,
                    message.channel.id,
                    message.author.id,
                )
                bot.echo_tracker[channel_id] = {"content": None, "user_ids": set()}

    # 記錄圖片附件
    if message.attachments:
        for attachment in message.attachments:
            logger.debug(f'包含附件: {attachment.url} (類型: {attachment.content_type}, 頻道: {message.channel.name} [ID: {message.channel.id}])')

    # 記錄訊息中的嵌入內容
    if message.embeds:
        for embed in message.embeds:
            logger.debug(f'包含嵌入內容: {embed.url if embed.url else "無URL"} (頻道: {message.channel.name} [ID: {message.channel.id}])')

    # 記錄貼圖訊息
    if message.stickers:
        for sticker in message.stickers:
            logger.debug(f'包含貼圖: {sticker.name} (ID: {sticker.id}, 頻道: {message.channel.name} [ID: {message.channel.id}])')

    # 將訊息加入持久化 buffer（非 bot 訊息、有內容或貼圖）
    if not message.author.bot and (message.content or message.stickers):
        from llm.storage.store_chat import enqueue_message, flush_buffer, should_flush_now
        enqueue_message(message)
        if should_flush_now():
            spawn(flush_buffer(), name="聊天記憶寫入")

    # 同步寫入 raw 備份表（獨立於 pgvector，包含純附件/純 embed 訊息）
    if not message.author.bot:
        from llm.storage.raw_message_store import (
            enqueue_raw_message,
            flush_raw_buffer,
            should_trigger_flush,
        )
        enqueue_raw_message(message)
        if should_trigger_flush():
            spawn(flush_raw_buffer(), name="原始訊息備份寫入")

    # 功能二：AI 偶爾插話 / 閒聊（背景判斷，不阻塞訊息處理；自身過濾白名單頻道與 bot 訊息）
    if not message.author.bot and message.guild is not None:
        from llm.ambient.ambient_reply import maybe_ambient_reply
        spawn(maybe_ambient_reply(bot, message), name="插話評估")

    # 沒描述的表情／貼圖：背景讓模型看圖補字典（每個只看一次；節流與錯誤自己處理）
    if not message.author.bot and message.guild is not None and (message.stickers or "<" in (message.content or "")):
        from llm.preprocess.emoji_autofill import observe as observe_emoji
        spawn(observe_emoji(message), name="看圖補表情字典")

    # 繼續處理命令
    await bot.process_commands(message)

@bot.event
async def on_guild_stickers_update(guild, before, after):
    """伺服器貼圖有增刪改 → 更新描述快取。bot 長時間不重啟，不能只在啟動時載入。"""
    from llm.preprocess.sticker_cache import update_guild
    update_guild(before, after)

@bot.event
async def on_typing(channel, user, when):
    """有人正在打字 → 記給插話的靜默期用（等人打完再開口，不搶話）。

    `Intents.default()` 已含 typing（非 privileged），不必額外授權。Discord 沒有「停止打字」
    事件，client 持續打字時每約 9 秒重送一次 → 由 ambient 端以 grace 秒數判定過期。
    """
    if getattr(user, "bot", False):
        return
    try:
        from llm.ambient.ambient_reply import note_typing
        note_typing(channel.id, user.id)
    except Exception:
        pass  # 純訊號，壞掉不該影響任何事（收不到就退化成純時間靜默期）

@bot.event
async def on_message_edit(before, after):
    if after.author.bot:
        return
    from llm.storage.store_chat import enqueue_message_edit
    from llm.storage.raw_message_store import enqueue_raw_edit
    content_changed = before.content != after.content
    embeds_added = not before.embeds and after.embeds

    # 情況 1：使用者修改了訊息內容
    if content_changed:
        if after.content or after.stickers:
            enqueue_message_edit(after)
        enqueue_raw_edit(after)
        return
    # 情況 2：Discord 載入了連結預覽（content 沒變但 embeds 新增了）
    if embeds_added:
        enqueue_message_edit(after)
        enqueue_raw_edit(after)


@bot.event
async def on_raw_message_delete(payload):
    """使用者刪除訊息 → raw 表軟刪標記。
    用 raw 版本因為訊息可能不在 bot cache 裡（例如啟動前發的舊訊息）。"""
    from llm.storage.raw_message_store import enqueue_raw_delete
    enqueue_raw_delete(payload.message_id)


async def _cleanup_created_event(discord_event_id: int, reason: str) -> None:
    """Discord 端刪除/取消伺服器活動 → 在 created_events 立**墓碑**（不是刪掉那一列）。

    原本是實體刪除，理由是「下次重送可重建」。但同一個活動 article 與 FB 相隔 7~28 天
    才會各報一次（實測），列一刪掉指紋就不擋了，那篇晚到的公告會把使用者剛刪掉的活動
    原地復活。改成標記後，兩條比對路徑都還查得到，查到就什麼都不做。
    """
    try:
        from services.state_db import get_shared_state_db
        db = await get_shared_state_db()
        n = await db.mark_created_event_deleted(discord_event_id)
        if n:
            logger.info("[event] Discord 活動%s → 已立墓碑 %s 筆，之後任何來源都不會重建 (event_id=%s)",
                        reason, n, discord_event_id)
    except Exception as e:
        logger.warning("[event] 活動%s立墓碑失敗 (event_id=%s): %s", reason, discord_event_id, e)


@bot.event
async def on_scheduled_event_delete(event):
    """伺服器活動被刪除 → 連動清 created_events。"""
    await _cleanup_created_event(event.id, "刪除")


@bot.event
async def on_scheduled_event_update(before, after):
    """伺服器活動被取消（status→cancelled）→ 連動清 created_events。"""
    if after.status == discord.EventStatus.cancelled:
        await _cleanup_created_event(after.id, "取消")


@bot.event
async def on_raw_reaction_add(payload):
    """Reaction 增加 → 更新 raw 表結構化統計。
    用 raw 版本以涵蓋 bot 啟動前發的舊訊息（非 cache）。"""
    # 跳過 bot 自己點的 reaction
    if bot.user and payload.user_id == bot.user.id:
        return
    from llm.storage.raw_message_store import enqueue_reaction_change
    enqueue_reaction_change(
        message_id=payload.message_id,
        emoji_name=payload.emoji.name,
        emoji_id=payload.emoji.id,
        user_id=payload.user_id,
        action="add",
    )
    # 若被按的是 bot 自己的插話 → 記成正向/負向證據（先查記憶體集合，命中才打 DB）
    try:
        from llm.storage.ai_interactions_store import is_tracked_reply, note_reaction
        mid = str(payload.message_id)
        if is_tracked_reply(mid):
            await asyncio.to_thread(
                note_reaction, mid, payload.emoji.name, payload.emoji.id, "add",
                payload.user_id,
            )
    except Exception as _exc:
        logger.debug("ai_interactions 反應記錄略過(add): %s", _exc)


@bot.event
async def on_raw_reaction_remove(payload):
    """Reaction 移除 → 反向更新 raw 表。"""
    if bot.user and payload.user_id == bot.user.id:
        return
    from llm.storage.raw_message_store import enqueue_reaction_change
    enqueue_reaction_change(
        message_id=payload.message_id,
        emoji_name=payload.emoji.name,
        emoji_id=payload.emoji.id,
        user_id=payload.user_id,
        action="remove",
    )
    try:
        from llm.storage.ai_interactions_store import is_tracked_reply, note_reaction
        mid = str(payload.message_id)
        if is_tracked_reply(mid):
            await asyncio.to_thread(
                note_reaction, mid, payload.emoji.name, payload.emoji.id, "remove",
                payload.user_id,
            )
    except Exception as _exc:
        logger.debug("ai_interactions 反應記錄略過(remove): %s", _exc)


def _refresh_person_anchors() -> None:
    """prompt 裡「名字#尾碼」的撞號名單跟著成員名單走（見 `llm.preprocess.person_anchor`）。"""
    from llm.preprocess import person_anchor
    person_anchor.refresh(m.id for g in bot.guilds for m in g.members)


@bot.event
async def on_member_join(member):
    """新成員加入 → 在歡迎頻道發歡迎訊息（未綁歡迎頻道則靜默）。"""
    _refresh_person_anchors()
    from services.community.member_welcome import send_welcome
    await send_welcome(member)


@bot.event
async def on_member_remove(member):
    _refresh_person_anchors()

async def auto_start_article_monitor(bot):
    """自動啟動官方文章更新功能"""
    try:
        # 等待一下讓所有 Cog 完全載入
        await asyncio.sleep(2)

        # 讀取配置文件
        config_file = CONFIG_FILE
        if not os.path.exists(config_file):
            logger.info("配置文件不存在，跳過自動啟動官方文章更新")
            return

        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)

        article_monitor_channel_id = config.get('article_monitor_channel_id')
        forum_article_channel_id = config.get('forum_article_channel_id')

        # 獲取 ArticleCommands Cog
        article_commands = bot.get_cog('ArticleCommands')
        if not article_commands:
            logger.error("找不到 ArticleCommands Cog，無法啟動官方文章更新")
            return

        await _auto_start_official_article_monitor(bot, article_commands, article_monitor_channel_id)
        await _auto_start_ptt_forum_monitor(bot, article_commands, forum_article_channel_id)

    except Exception as e:
        logger.error(f"自動啟動官方文章更新時發生錯誤: {e}", exc_info=True)


async def _auto_start_monitor_task(
    *,
    task_owner,
    task_attr: str,
    get_channel_fn,
    channel_id,
    missing_config_log: str,
    invalid_channel_log: str,
    already_running_log: str,
    start_coro_factory,
    success_log_factory,
):
    """通用的監控任務啟動器。"""
    if not channel_id:
        logger.info(missing_config_log)
        return

    channel = get_channel_fn(channel_id)
    if not channel:
        logger.error(invalid_channel_log.format(channel_id=channel_id))
        return

    task = getattr(task_owner, task_attr, None)
    if task and not task.done():
        logger.info(already_running_log)
        return

    new_task = supervise(lambda: start_coro_factory(channel_id), name=task_attr)
    setattr(task_owner, task_attr, new_task)
    logger.info(success_log_factory(channel, channel_id))


async def _auto_start_official_article_monitor(bot, article_commands, article_monitor_channel_id):
    """自動啟動官方文章監控。

    註：article 已改「推送」為主（scraper 爬完打 /notify/article → notify_server._process_relay）。
    此輪詢降為 30 分 fallback safety net（webhook 漏掉時補發；去重靠 StateDB，不會重送）。
    """
    def _get_channel(channel_id):
        return bot.get_channel(channel_id)

    async def _start(channel_id):
        if channel_id not in article_commands.monitored_channels:
            article_commands.monitored_channels.append(channel_id)
        await article_commands.article_monitor.start_monitoring(
            channel_ids=article_commands.monitored_channels,
            check_interval=1800,  # 30 分 fallback（推送為主）
        )

    await _auto_start_monitor_task(
        task_owner=article_commands,
        task_attr="monitoring_task",
        get_channel_fn=_get_channel,
        channel_id=article_monitor_channel_id,
        missing_config_log="配置文件中沒有設定官方文章更新頻道 ID，跳過官方文章自動啟動",
        invalid_channel_log="找不到官方文章更新頻道 ID: {channel_id}",
        already_running_log="官方文章更新已經在運行中",
        start_coro_factory=_start,
        success_log_factory=lambda channel, channel_id: f"✅ 已自動啟動官方文章更新！更新頻道: {channel.name} (ID: {channel_id})",
    )


async def _auto_start_ptt_forum_monitor(bot, article_commands, forum_article_channel_id):
    """自動啟動 PTT 論壇文章監控。"""
    def _get_forum_channel(channel_id):
        channel = bot.get_channel(channel_id)
        return channel if isinstance(channel, discord.ForumChannel) else None

    async def _start(channel_id):
        await article_commands.ptt_monitor.start_ptt_monitoring(
            forum_channel_ids=[channel_id],
            check_interval=600,
        )

    await _auto_start_monitor_task(
        task_owner=article_commands,
        task_attr="ptt_monitoring_task",
        get_channel_fn=_get_forum_channel,
        channel_id=forum_article_channel_id,
        missing_config_log="配置文件中沒有設定論壇文章頻道 ID，跳過 PTT 論壇文章自動啟動",
        invalid_channel_log="找不到論壇文章頻道 ID: {channel_id}，或該頻道不是論壇頻道",
        already_running_log="PTT 論壇文章監控已經在運行中",
        start_coro_factory=_start,
        success_log_factory=lambda channel, channel_id: f"✅ 已自動啟動 PTT 論壇文章監控！論壇頻道: {channel.name} (ID: {channel_id})",
    )


async def auto_start_telegram_relay(bot):
    """自動啟動 Telegram Relay Worker。"""
    try:
        # on_ready 可能因 reconnect 被重複觸發，避免重複建立 worker
        worker = getattr(bot, "telegram_relay_worker", None)
        if worker and worker.running:
            logger.info("Telegram Relay Worker 已在運行中，略過重複啟動")
            return

        dsn = build_telegram_pg_dsn_from_env()
        repository = TelegramMessageRepository(dsn=dsn)
        resolver = MessageRouteResolver()
        adapter = TelegramRenderAdapter()
        publisher = DiscordMessagePublisher()

        from services.relay.telegram_filter import RelayFilter
        from services.relay.telegram_quarantine import RUNTIME_PATH, QuarantineThreads

        # 隔離區面板（commands.telegram_quarantine_commands）：隔離區有變動時置底重畫，放回也經過它
        panel_cog = bot.get_cog("TelegramQuarantineCommands")
        quarantine = QuarantineThreads(
            bot, RUNTIME_PATH, on_change=panel_cog.on_quarantine_change if panel_cog is not None else None,
        )
        worker = MessageRelayWorker(
            bot=bot,
            repository=repository,
            route_resolver=resolver,
            render_adapter=adapter,
            publisher=publisher,
            dsn=dsn,
            notify_channel=os.getenv("TELEGRAM_PG_NOTIFY_CHANNEL", "telegram_new_message"),
            poll_interval_sec=3600,
            # 過濾關掉（mode=off）時也要有隔離區：之前被隔離的相簿，晚到的圖才會跟著進 thread
            content_filter=RelayFilter(),
            quarantine=quarantine,
        )
        if panel_cog is not None:
            panel_cog.worker = worker

        await worker.start()
        bot.telegram_relay_worker = worker
        logger.info("Telegram Relay Worker 啟動流程完成")

    except Exception as e:
        logger.error(f"自動啟動 Telegram Relay Worker 時發生錯誤: {e}", exc_info=True)


async def auto_start_notify_server(bot):
    """啟動 Notify Server（接收 Scraper webhook 通知）。"""
    try:
        # 避免 on_ready reconnect 重複啟動
        if getattr(bot, "_notify_server", None):
            logger.info("Notify Server 已在運行中，略過重複啟動")
            return

        from services.notify_server import NotifyServer
        server = NotifyServer(bot)
        await server.start()
        bot._notify_server = server
        logger.info("✅ 已自動啟動 Notify Server (port 5000)")

    except Exception as e:
        logger.error(f"自動啟動 Notify Server 時發生錯誤: {e}", exc_info=True)


# 主函數
def main():
    if not TOKEN or TOKEN == 'your_discord_token_here':
        logger.error("錯誤：找不到有效的 DISCORD_TOKEN 環境變數")
        logger.error("請確保您已正確設置 .env 文件中的 DISCORD_TOKEN")

        # 無限循環以保持容器運行
        while True:
            logger.warning("等待有效的 Discord 令牌...（60秒後重試）")
            time.sleep(60)  # 每60秒檢查一次

            # 重新嘗試載入令牌
            load_dotenv(override=True)  # 添加 override=True 確保重新加載
            new_token = os.getenv('DISCORD_TOKEN')
            if new_token and new_token != 'your_discord_token_here':
                logger.info("檢測到新的令牌，嘗試啟動機器人...")
                try:
                    bot.run(new_token, log_handler=None)
                    break  # 如果成功啟動，跳出循環
                except Exception as e:
                    logger.error(f"啟動失敗: {str(e)}")
    else:
        try:
            logger.info("嘗試啟動 Discord 機器人...")
            bot.run(TOKEN, log_handler=None)
        except discord.errors.LoginFailure as e:
            logger.error(f"登錄失敗: {str(e)}")
            logger.error("請確保您提供了正確的 Discord 令牌")
            # 進入無限循環以保持容器運行
            while True:
                logger.warning("等待有效的 Discord 令牌...（60秒後重試）")
                time.sleep(60)
        except Exception as e:
            logger.error(f"發生未預期的錯誤: {str(e)}")
            # 進入無限循環以保持容器運行
            while True:
                logger.warning("機器人因錯誤停止...（60秒後重試）")
                time.sleep(60)

# 運行機器人
if __name__ == '__main__':
    logger.info("Discord 機器人程序啟動")
    main()
