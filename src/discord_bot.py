import os
import sys
import time
import logging
import asyncio
import json
from logging.handlers import RotatingFileHandler
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()

# 設置日誌系統
logger = logging.getLogger('discord_bot')
# 設置日誌級別
log_level = getattr(logging, LOG_LEVEL, logging.INFO)
logger.setLevel(log_level)

# 控制台處理器
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(log_level)
console_format = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', '%Y-%m-%d %H:%M:%S')
console_handler.setFormatter(console_format)

# 文件處理器（帶輪替）
file_handler = RotatingFileHandler(
    '/logs/discord_bot.log',
    maxBytes=10*1024*1024,  # 10MB
    backupCount=50,          # 保留50個備份
    encoding='utf-8'
)

file_handler.setLevel(log_level)
file_format = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', '%Y-%m-%d %H:%M:%S')
file_handler.setFormatter(file_format)

# 添加處理器到logger
logger.addHandler(console_handler)
logger.addHandler(file_handler)

# 記錄環境變數和系統信息（安全方式）
logger.info(f"Discord 機器人啟動於 {time.strftime('%Y-%m-%d %H:%M:%S')}")
logger.info(f"Python 版本: {sys.version}")
logger.info(f"日誌級別設置為: {LOG_LEVEL}")
logger.info(f"日誌文件位置: /logs/discord_bot.log")
logger.info(f"環境變數中的 DISCORD_TOKEN: {'已設置' if TOKEN else '未設置'}")
logger.info(f"當前工作目錄: {os.getcwd()}")
logger.info(f"當前目錄內容: {os.listdir('.')}")
logger.info(f"日誌目錄內容: {os.listdir('/logs') if os.path.exists('/logs') else '日誌目錄不存在'}")

# 設定意圖
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True

# 指令模組清單
COMMAND_MODULES = [
    'commands.test_commands',
    'commands.trade_commands',
    'commands.management_commands',
    'commands.forum_monitor',
    'commands.user_commands',
    'commands.article_commands'
]

# 建立機器人實例
class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='!', intents=intents)

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
        read_message_history=True
    )

    invite_url = discord.utils.oauth_url(
        bot.user.id,
        permissions=permissions,
        scopes=("bot", "applications.commands")  # 重要：需要包含 applications.commands 範圍
    )

    logger.info(f"邀請連結: {invite_url}")
    logger.info("如果斜線命令未顯示，請使用上面的連結重新邀請機器人，確保包含應用程序命令權限")

    # 自動啟動官方文章更新
    await auto_start_article_monitor(bot)

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
        await interaction.response.send_message(
            f"請稍等片刻再使用此命令。剩餘冷卻時間: {error.retry_after:.2f}秒",
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
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

    # 繼續處理命令
    await bot.process_commands(message)

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

        if not article_monitor_channel_id:
            logger.info("配置文件中沒有設定官方文章更新頻道 ID，跳過自動啟動")
            return

        # 檢查頻道是否存在
        channel = bot.get_channel(article_monitor_channel_id)
        if not channel:
            logger.error(f"找不到官方文章更新頻道 ID: {article_monitor_channel_id}")
            return

        # 獲取 ArticleCommands Cog
        article_commands = bot.get_cog('ArticleCommands')
        if not article_commands:
            logger.error("找不到 ArticleCommands Cog，無法啟動官方文章更新")
            return

        # 檢查是否已經在監控
        if article_commands.monitoring_task and not article_commands.monitoring_task.done():
            logger.info("官方文章更新已經在運行中")
            return

        # 設定監控頻道
        if article_monitor_channel_id not in article_commands.monitored_channels:
            article_commands.monitored_channels.append(article_monitor_channel_id)

        # 啟動監控任務
        article_commands.monitoring_task = asyncio.create_task(
            article_commands.article_monitor.start_monitoring(
                channel_ids=article_commands.monitored_channels,
                check_interval=180  # 3分鐘檢查一次
            )
        )

        logger.info(f"✅ 已自動啟動官方文章更新！更新頻道: {channel.name} (ID: {article_monitor_channel_id})")

    except Exception as e:
        logger.error(f"自動啟動官方文章更新時發生錯誤: {e}", exc_info=True)

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
