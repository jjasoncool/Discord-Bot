import logging
import json
import os
import discord

# 獲取 logger
logger = logging.getLogger('discord_bot')

async def get_trade_forum_channel_id(config_file="config.json", caller="unknown"):
    """從配置文件中讀取交易論壇頻道 ID"""
    logger.debug(f"開始讀取交易論壇頻道 ID，配置文件: {config_file}，調用者: {caller}")
    forum_channel_id = 1234567890  # 預設佔位符 ID
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)
                forum_channel_id = config.get('trade_forum_channel_id', 1234567890)
                if forum_channel_id != 1234567890:
                    logger.info(f"從 {config_file} 讀取到交易論壇頻道 ID: {forum_channel_id} (調用者: {caller})")
                else:
                    logger.warning(f"從 {config_file} 讀取到交易論壇頻道 ID，但未設定，使用預設佔位符 ID (調用者: {caller})")
        except json.JSONDecodeError as e:
            logger.error(f"無法讀取 {config_file}，JSON 解碼錯誤: {str(e)}，使用預設佔位符 ID (調用者: {caller})")
        except Exception as e:
            logger.error(f"讀取 {config_file} 時發生未知錯誤: {str(e)}，使用預設佔位符 ID (調用者: {caller})")
    else:
        logger.warning(f"配置文件 {config_file} 不存在，使用預設佔位符 ID (調用者: {caller})")
    logger.debug(f"返回交易論壇頻道 ID: {forum_channel_id} (調用者: {caller})")
    return forum_channel_id

async def get_cart_delivery_channel_id(config_file="config.json", caller="unknown"):
    """從配置文件中讀取購物車交付頻道 ID"""
    logger.debug(f"開始讀取購物車交付頻道 ID，配置文件: {config_file}，調用者: {caller}")
    delivery_channel_id = 1234567890  # 預設佔位符 ID
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)
                delivery_channel_id = config.get('cart_delivery_channel_id', 1234567890)
                if delivery_channel_id != 1234567890:
                    logger.info(f"從 {config_file} 讀取到購物車交付頻道 ID: {delivery_channel_id} (調用者: {caller})")
                else:
                    logger.warning(f"從 {config_file} 讀取到購物車交付頻道 ID，但未設定，使用預設佔位符 ID (調用者: {caller})")
        except json.JSONDecodeError as e:
            logger.error(f"無法讀取 {config_file}，JSON 解碼錯誤: {str(e)}，使用預設佔位符 ID (調用者: {caller})")
        except Exception as e:
            logger.error(f"讀取 {config_file} 時發生未知錯誤: {str(e)}，使用預設佔位符 ID (調用者: {caller})")
    else:
        logger.warning(f"配置文件 {config_file} 不存在，使用預設佔位符 ID (調用者: {caller})")
    logger.debug(f"返回購物車交付頻道 ID: {delivery_channel_id} (調用者: {caller})")
    return delivery_channel_id

async def check_guild(interaction: discord.Interaction, owner_only: bool = False) -> bool:
    """檢查命令是否在伺服器中使用且使用者是否為伺服器擁有者（如果啟用了限制）"""
    if not interaction.guild:
        await interaction.response.send_message("此命令只能在伺服器中使用，無法在私人訊息中使用。", ephemeral=True)
        logger.info(f'使用者 {interaction.user} 嘗試在私人訊息中使用命令，已被拒絕')
        return False
    if owner_only:
        owner_id = int(os.getenv('OWNER_ID', '0'))
        if interaction.user.id != owner_id:
            await interaction.response.send_message("此命令僅限指定擁有者使用！", ephemeral=True)
            logger.info(f'使用者 {interaction.user} 嘗試使用僅限擁有者的命令，已被拒絕')
            return False
    return True
