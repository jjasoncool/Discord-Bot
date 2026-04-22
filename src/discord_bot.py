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
from sys_settings.llm_settings import LLMServiceSettings, load_ollama_runtime_config
from utils.logger_config import get_discord_bot_logger
from utils.utils import safe_send_interaction_message
from services.telegram_relay_service import (
    DiscordMessagePublisher,
    MessageRelayWorker,
    MessageRouteResolver,
    TelegramMessageRepository,
    TelegramRenderAdapter,
    build_telegram_pg_dsn_from_env,
)

# 載入環境變數
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# 設置日誌系統（使用統一配置）
logger = get_discord_bot_logger()
LLM_SETTINGS = LLMServiceSettings()

# 記錄環境變數和系統信息（安全方式）
logger.info(f"Discord 機器人啟動於 {time.strftime('%Y-%m-%d %H:%M:%S')}")
logger.info(f"Python 版本: {sys.version}")
logger.info(f"日誌文件位置: /logs/discord_bot.log")
logger.info(f"環境變數中的 DISCORD_TOKEN: {'已設置' if TOKEN else '未設置'}")
logger.info(f"當前工作目錄: {os.getcwd()}")
logger.info(f"當前目錄內容: {os.listdir('.')}")
logger.info(f"日誌目錄內容: {os.listdir('/logs') if os.path.exists('/logs') else '日誌目錄不存在'}")

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
    'commands.rollcall_commands',
    'commands.trade_commands',
    'commands.test_commands',
    'commands.user_commands'
]

# 建立機器人實例
class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='!', intents=intents)
        self.echo_tracker = {}
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
    logger.info(f'機器人 {bot.user.name} 已連接到 Discord!')
    logger.info(f'機器人 ID: {bot.user.id}')

    # 創建邀請連結
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
        scopes=("bot", "applications.commands")  # 重要：需要包含 applications.commands 範圍
    )

    logger.info(f"邀請連結: {invite_url}")
    logger.info("如果斜線命令未顯示，請使用上面的連結重新邀請機器人，確保包含應用程序命令權限")

    # 預載貼圖描述快取
    from llm.sticker_cache import load_guild_stickers
    await load_guild_stickers(bot)

    # 啟動聊天訊息定期持久化 flush
    from llm.chat_persistence import flush_buffer, FLUSH_INTERVAL_SECONDS
    if not getattr(bot, '_chat_persist_task_started', False):
        async def _periodic_flush():
            while True:
                await asyncio.sleep(FLUSH_INTERVAL_SECONDS)
                try:
                    await flush_buffer()
                except Exception as exc:
                    logger.warning("定期 flush 聊天 buffer 失敗: %s", exc)
        bot._chat_persist_task = asyncio.create_task(_periodic_flush())
        bot._chat_persist_task_started = True
        logger.info("聊天訊息定期持久化已啟動（每 %d 秒）", FLUSH_INTERVAL_SECONDS)

    # 啟動 raw 訊息備份表定期 flush（含 reaction 事件）
    from llm.raw_message_store import flush_raw_buffer, RAW_FLUSH_INTERVAL_SECONDS
    if not getattr(bot, '_raw_persist_task_started', False):
        async def _periodic_raw_flush():
            while True:
                await asyncio.sleep(RAW_FLUSH_INTERVAL_SECONDS)
                try:
                    await flush_raw_buffer()
                except Exception as exc:
                    logger.warning("定期 flush raw 訊息 buffer 失敗: %s", exc)
        bot._raw_persist_task = asyncio.create_task(_periodic_raw_flush())
        bot._raw_persist_task_started = True
        logger.info("raw 訊息備份定期 flush 已啟動（每 %d 秒）", RAW_FLUSH_INTERVAL_SECONDS)

    # 啟動人格萃取定期排程
    if not getattr(bot, '_personality_task_started', False):
        from datetime import datetime, timezone, timedelta
        TAIPEI_TZ = timezone(timedelta(hours=8))

        async def _run_personality_extraction_once():
            """跑一次完整的人格萃取（refresh emoji 字典 → 萃取 → register 結果）。

            排程與啟動補跑共用此函式。若遇到鎖（`PersonalityExtractionInProgressError`）
            只 log INFO 後返回，不視為錯誤。
            """
            guild = bot.guilds[0] if bot.guilds else None
            if not guild:
                logger.warning("人格萃取：無可用 guild")
                return

            try:
                from llm.personality_extractor import refresh_emoji_dictionary
                refresh_emoji_dictionary(guild)
            except Exception as exc:
                logger.warning("emoji 字典自動更新失敗: %s", exc)

            from llm.personality_extractor import (
                PersonalityExtractionInProgressError,
                run_personality_extraction,
            )
            try:
                results = await run_personality_extraction(guild=guild, days=14)
            except PersonalityExtractionInProgressError:
                logger.info("人格萃取略過：已有萃取正在執行中")
                return

            personality_cog = bot.get_cog("PersonalityCommands")
            if personality_cog:
                runtime_config = load_ollama_runtime_config(LLM_SETTINGS.ollama_runtime_model_path)
                scheduled_model = runtime_config.personality_model or runtime_config.model
                personality_cog.register_scheduled_result(
                    guild_id=guild.id,
                    results=results,
                    model=scheduled_model,
                    days=14,
                )
            logger.info("人格萃取排程完成：萃取 %d 位使用者", len(results))

        async def _personality_schedule():
            # 啟動後等 60 秒再開始，讓其他服務先就緒
            await asyncio.sleep(60)

            # 啟動補跑檢查：若上次排程被錯過（容器重啟 / 中斷），立即補一次
            try:
                from llm.personality_extractor import get_last_extraction_time
                guild_for_check = bot.guilds[0] if bot.guilds else None
                if guild_for_check:
                    now = datetime.now(TAIPEI_TZ)
                    # 「上一個應該跑的 04:00」：如果現在還沒過今天 04:00，上個就是昨天 04:00
                    last_scheduled_run = now.replace(hour=4, minute=0, second=0, microsecond=0)
                    if now < last_scheduled_run:
                        last_scheduled_run -= timedelta(days=1)

                    last_extract_utc = get_last_extraction_time(guild_for_check.id)
                    # metadata 存的是 UTC；轉台北時區再比
                    last_extract_local = (
                        last_extract_utc.astimezone(TAIPEI_TZ)
                        if last_extract_utc else None
                    )

                    if last_extract_local is None or last_extract_local < last_scheduled_run:
                        logger.info(
                            "啟動補跑檢查：last_extract=%s, 上個排程=%s → 立即補跑",
                            last_extract_local, last_scheduled_run.isoformat(),
                        )
                        await _run_personality_extraction_once()
                    else:
                        logger.info(
                            "啟動補跑檢查：last_extract=%s ≥ 上個排程=%s，跳過",
                            last_extract_local, last_scheduled_run.isoformat(),
                        )
            except Exception as exc:
                logger.error("啟動補跑檢查失敗: %s", exc, exc_info=True)

            while True:
                try:
                    now = datetime.now(TAIPEI_TZ)
                    # 計算到下一個 04:00 的秒數
                    target = now.replace(hour=4, minute=0, second=0, microsecond=0)
                    if now >= target:
                        target += timedelta(days=1)
                    wait_seconds = (target - now).total_seconds()
                    logger.info("人格萃取排程：下次執行 %s（等待 %.0f 秒）", target.isoformat(), wait_seconds)
                    await asyncio.sleep(wait_seconds)
                    await _run_personality_extraction_once()
                except Exception as exc:
                    logger.error("人格萃取排程失敗: %s", exc, exc_info=True)
                    # 失敗後等 1 小時再試
                    await asyncio.sleep(3600)

        bot._personality_task = asyncio.create_task(_personality_schedule())
        bot._personality_task_started = True
        logger.info("人格萃取定期排程已啟動（每日 04:00 UTC+8，含啟動補跑檢查）")

    # 自動啟動官方文章更新
    await auto_start_article_monitor(bot)
    await auto_start_telegram_relay(bot)

    # 啟動 Notify Server（接收 Scraper webhook 通知）
    await auto_start_notify_server(bot)

    try:
        # 列出已註冊的命令
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
        from llm.chat_persistence import enqueue_message, flush_buffer, buffer_size, FLUSH_THRESHOLD
        enqueue_message(message)
        if buffer_size() >= FLUSH_THRESHOLD:
            asyncio.create_task(flush_buffer())

    # 同步寫入 raw 備份表（獨立於 pgvector，包含純附件/純 embed 訊息）
    if not message.author.bot:
        from llm.raw_message_store import (
            enqueue_raw_message,
            flush_raw_buffer,
            should_trigger_flush,
        )
        enqueue_raw_message(message)
        if should_trigger_flush():
            asyncio.create_task(flush_raw_buffer())

    # 繼續處理命令
    await bot.process_commands(message)

@bot.event
async def on_message_edit(before, after):
    if after.author.bot:
        return
    from llm.chat_persistence import enqueue_message_edit
    from llm.raw_message_store import enqueue_raw_edit
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
    from llm.raw_message_store import enqueue_raw_delete
    enqueue_raw_delete(payload.message_id)


@bot.event
async def on_raw_reaction_add(payload):
    """Reaction 增加 → 更新 raw 表結構化統計。
    用 raw 版本以涵蓋 bot 啟動前發的舊訊息（非 cache）。"""
    # 跳過 bot 自己點的 reaction
    if bot.user and payload.user_id == bot.user.id:
        return
    from llm.raw_message_store import enqueue_reaction_change
    enqueue_reaction_change(
        message_id=payload.message_id,
        emoji_name=payload.emoji.name,
        emoji_id=payload.emoji.id,
        user_id=payload.user_id,
        action="add",
    )


@bot.event
async def on_raw_reaction_remove(payload):
    """Reaction 移除 → 反向更新 raw 表。"""
    if bot.user and payload.user_id == bot.user.id:
        return
    from llm.raw_message_store import enqueue_reaction_change
    enqueue_reaction_change(
        message_id=payload.message_id,
        emoji_name=payload.emoji.name,
        emoji_id=payload.emoji.id,
        user_id=payload.user_id,
        action="remove",
    )

async def auto_start_article_monitor(bot):
    """自動啟動官方文章更新功能"""
    try:
        # 等待一下讓所有 Cog 完全載入
        await asyncio.sleep(2)

        # 讀取配置文件
        config_file = "config.json"
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

    new_task = asyncio.create_task(start_coro_factory(channel_id))
    setattr(task_owner, task_attr, new_task)
    logger.info(success_log_factory(channel, channel_id))


async def _auto_start_official_article_monitor(bot, article_commands, article_monitor_channel_id):
    """自動啟動官方文章監控。"""
    def _get_channel(channel_id):
        return bot.get_channel(channel_id)

    async def _start(channel_id):
        if channel_id not in article_commands.monitored_channels:
            article_commands.monitored_channels.append(channel_id)
        await article_commands.article_monitor.start_monitoring(
            channel_ids=article_commands.monitored_channels,
            check_interval=180,
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
        resolver = MessageRouteResolver(config_path="config.json")
        adapter = TelegramRenderAdapter(app_root="/app")
        publisher = DiscordMessagePublisher()

        worker = MessageRelayWorker(
            bot=bot,
            repository=repository,
            route_resolver=resolver,
            render_adapter=adapter,
            publisher=publisher,
            dsn=dsn,
            notify_channel=os.getenv("TELEGRAM_PG_NOTIFY_CHANNEL", "telegram_new_message"),
            poll_interval_sec=3600,
        )

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
                    bot.run(new_token)
                    break  # 如果成功啟動，跳出循環
                except Exception as e:
                    logger.error(f"啟動失敗: {str(e)}")
    else:
        try:
            logger.info("嘗試啟動 Discord 機器人...")
            bot.run(TOKEN)
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
