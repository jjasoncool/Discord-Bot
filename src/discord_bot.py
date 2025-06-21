import os
import sys
import time
import logging
import asyncio
from logging.handlers import RotatingFileHandler
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()

# 創建日誌目錄（確保與 docker-compose.yaml 中的掛載配置一致）
os.makedirs('/logs', exist_ok=True)

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
    backupCount=5,          # 保留5個備份
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

# 指令模組清單
COMMAND_MODULES = [
    'commands.test_commands',
    'commands.trade_commands',
    'commands.management_commands'
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
                logger.error(f"載入指令模組 {module} 時發生錯誤: {str(e)}")

        # 同步斜線命令
        try:
            logger.info("開始同步斜線命令...")
            # 同步全局命令
            cmds = await self.tree.sync()
            logger.info(f"已同步 {len(cmds)} 個全局斜線命令")

        except Exception as e:
            logger.error(f"斜線命令同步失敗: {str(e)}")

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
    logger.debug(f'收到訊息: {message.content} (來自: {message.author})')

    # 繼續處理命令
    await bot.process_commands(message)

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
