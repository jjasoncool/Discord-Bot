import os
import sys
import time
import logging
from logging.handlers import RotatingFileHandler
import discord
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

# 建立機器人實例
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    logger.info(f'機器人 {bot.user.name} 已連接到 Discord!')
    logger.info(f'機器人 ID: {bot.user.id}')

@bot.command(name='ping')
async def ping(ctx):
    """回應一個 Pong 訊息，用於測試機器人是否在線"""
    logger.info(f'收到來自 {ctx.author} 的 ping 命令')
    await ctx.send('Pong!')

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
