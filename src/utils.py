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

async def check_guild(interaction: discord.Interaction, owner_only: bool = False, admin_only: bool = False) -> bool:
    """
    檢查命令使用權限

    Args:
        interaction: Discord 互動物件
        owner_only: 是否僅限擁有者使用
        admin_only: 是否僅限管理員使用

    Returns:
        bool: 是否通過權限檢查
    """
    # 檢查是否在伺服器中使用
    if not interaction.guild:
        await interaction.response.send_message("此命令只能在伺服器中使用，無法在私人訊息中使用。", ephemeral=True)
        logger.info(f'使用者 {interaction.user} 嘗試在私人訊息中使用命令，已被拒絕')
        return False

    # 檢查擁有者權限（最高優先級）
    if owner_only:
        owner_id = int(os.getenv('OWNER_ID', '0'))
        if interaction.user.id != owner_id:
            await interaction.response.send_message("❌ 此命令僅限指定擁有者使用！", ephemeral=True)
            logger.info(f'使用者 {interaction.user} 嘗試使用僅限擁有者的命令，已被拒絕')
            return False

    # 檢查管理員權限
    elif admin_only:
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 此命令僅限管理員使用！", ephemeral=True)
            logger.info(f'使用者 {interaction.user} 嘗試使用僅限管理員的命令，已被拒絕')
            return False

    return True

def get_paginated_options(options, page, items_per_page=25):
    """
    獲取指定頁的分頁選項

    Args:
        options: 選項列表
        page: 頁數
        items_per_page: 每頁項目數，預設為25

    Returns:
        list: 指定頁的選項列表
    """
    start_idx = page * items_per_page
    end_idx = start_idx + items_per_page
    return options[start_idx:end_idx]

ITEMS_PER_PAGE = 25

def create_paginated_view(options, placeholder_text, embed_title, embed_description, embed_color, on_select_callback):
    """
    創建分頁視圖

    Args:
        options: 選項列表
        placeholder_text: 選擇框的佔位符文本
        embed_title: 嵌入訊息的標題
        embed_description: 嵌入訊息的描述
        embed_color: 嵌入訊息的顏色
        on_select_callback: 選擇回調函數

    Returns:
        tuple: (current_page, view)
    """
    current_page = 0

    def update_view(page):
        if callable(placeholder_text):
            placeholder = placeholder_text(page)
        else:
            placeholder = placeholder_text + (f" (第 {page + 1} 頁)" if len(options) > ITEMS_PER_PAGE else "")

        channel_select = discord.ui.Select(
            placeholder=placeholder,
            options=get_paginated_options(options, page, ITEMS_PER_PAGE)
        )

        async def channel_select_callback(interaction: discord.Interaction):
            selected_value = channel_select.values[0]
            await on_select_callback(interaction, selected_value)

        channel_select.callback = channel_select_callback

        view = discord.ui.View()
        view.add_item(channel_select)

        if len(options) > ITEMS_PER_PAGE:
            prev_button = discord.ui.Button(label="上一頁", style=discord.ButtonStyle.primary, disabled=page <= 0)
            next_button = discord.ui.Button(label="下一頁", style=discord.ButtonStyle.primary, disabled=(page + 1) * ITEMS_PER_PAGE >= len(options))

            async def prev_button_callback(interaction: discord.Interaction):
                nonlocal current_page
                current_page -= 1
                new_view = update_view(current_page)
                if callable(embed_description):
                    desc = embed_description(current_page)
                else:
                    desc = embed_description + (f" (第 {current_page + 1} 頁)" if len(options) > ITEMS_PER_PAGE else "")
                embed = discord.Embed(
                    title=embed_title,
                    description=desc,
                    color=embed_color
                )
                await interaction.response.edit_message(embed=embed, view=new_view)

            async def next_button_callback(interaction: discord.Interaction):
                nonlocal current_page
                current_page += 1
                new_view = update_view(current_page)
                if callable(embed_description):
                    desc = embed_description(current_page)
                else:
                    desc = embed_description + (f" (第 {current_page + 1} 頁)" if len(options) > ITEMS_PER_PAGE else "")
                embed = discord.Embed(
                    title=embed_title,
                    description=desc,
                    color=embed_color
                )
                await interaction.response.edit_message(embed=embed, view=new_view)

            prev_button.callback = prev_button_callback
            next_button.callback = next_button_callback

            view.add_item(prev_button)
            view.add_item(next_button)

        return view

    return current_page, update_view(current_page)
