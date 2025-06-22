import logging
import json
import os
import discord

# 獲取 logger
logger = logging.getLogger('discord_bot')

class ChannelConfig:
    """管理從配置文件中讀取頻道 ID 的類別"""
    DEFAULT_ID = 1234567890  # 預設佔位符 ID

    @staticmethod
    async def get_channel_id(config_key, config_file="config.json", caller="unknown"):
        """從配置文件中讀取指定鍵的頻道 ID"""
        logger.debug(f"開始讀取頻道 ID，鍵: {config_key}，配置文件: {config_file}，調用者: {caller}")
        channel_id = ChannelConfig.DEFAULT_ID
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    config = json.load(f)
                    channel_id = config.get(config_key, ChannelConfig.DEFAULT_ID)
                    if channel_id != ChannelConfig.DEFAULT_ID:
                        logger.info(f"從 {config_file} 讀取到頻道 ID: {channel_id} (鍵: {config_key}，調用者: {caller})")
                    else:
                        logger.warning(f"從 {config_file} 讀取到頻道 ID，但未設定，使用預設佔位符 ID (鍵: {config_key}，調用者: {caller})")
            except json.JSONDecodeError as e:
                logger.error(f"無法讀取 {config_file}，JSON 解碼錯誤: {str(e)}，使用預設佔位符 ID (鍵: {config_key}，調用者: {caller})")
            except Exception as e:
                logger.error(f"讀取 {config_file} 時發生未知錯誤: {str(e)}，使用預設佔位符 ID (鍵: {config_key}，調用者: {caller})")
        else:
            logger.warning(f"配置文件 {config_file} 不存在，使用預設佔位符 ID (鍵: {config_key}，調用者: {caller})")
        logger.debug(f"返回頻道 ID: {channel_id} (鍵: {config_key}，調用者: {caller})")
        return channel_id

async def get_trade_forum_channel_id(config_file="config.json", caller="unknown"):
    """從配置文件中讀取交易論壇頻道 ID"""
    return await ChannelConfig.get_channel_id('trade_forum_channel_id', config_file, caller)

async def get_cart_delivery_channel_id(config_file="config.json", caller="unknown"):
    """從配置文件中讀取購物車交付頻道 ID"""
    return await ChannelConfig.get_channel_id('cart_delivery_channel_id', config_file, caller)

async def get_archive_channel_id(config_file="config.json", caller="unknown"):
    """從配置文件中讀取封存頻道 ID"""
    return await ChannelConfig.get_channel_id('archive_channel_id', config_file, caller)

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
