import logging
import json
import os
import asyncio
import discord

# 獲取 logger
logger = logging.getLogger('discord_bot')


async def safe_send_interaction_message(
    interaction: discord.Interaction,
    content: str = None,
    *,
    ephemeral: bool = True,
    prefer_followup: bool = False,
    defer_first: bool = False,
    max_retries: int = 2,
    retry_base_delay: float = 0.8,
    **kwargs
):
    """
    安全回覆 Interaction（含基礎 retry/backoff）：
    - 若尚未回覆，使用 interaction.response.send_message
    - 若已回覆，改用 interaction.followup.send
    - 對 Discord API 的 429 / 5xx 做有限次重試
    """
    data = interaction.data if isinstance(interaction.data, dict) else {}
    custom_id = data.get("custom_id")
    command_name = data.get("name")
    guild_id = interaction.guild.id if interaction.guild else None
    channel_id = interaction.channel.id if interaction.channel else None

    for attempt in range(max_retries + 1):
        try:
            # 長任務場景可先 defer，後續統一走 followup
            if defer_first and not interaction.response.is_done():
                await interaction.response.defer(ephemeral=ephemeral)

            if prefer_followup:
                return await interaction.followup.send(content=content, ephemeral=ephemeral, **kwargs)

            if interaction.response.is_done():
                return await interaction.followup.send(content=content, ephemeral=ephemeral, **kwargs)
            return await interaction.response.send_message(content=content, ephemeral=ephemeral, **kwargs)
        except discord.InteractionResponded:
            # 競態下 response 可能剛被其他流程回覆，改走 followup
            return await interaction.followup.send(content=content, ephemeral=ephemeral, **kwargs)
        except discord.HTTPException as e:
            status = getattr(e, "status", None)
            retryable = status == 429 or (isinstance(status, int) and 500 <= status < 600)
            is_last_attempt = attempt >= max_retries

            # 10062 Unknown interaction 多半是 token 已失效，直接停止重試
            error_code = getattr(e, "code", None)
            if status == 404 and error_code == 10062:
                logger.error(
                    "safe_send_interaction_message 互動已失效(10062): attempt=%s/%s user_id=%s guild_id=%s channel_id=%s command=%s custom_id=%s",
                    attempt + 1,
                    max_retries + 1,
                    interaction.user.id if interaction.user else None,
                    guild_id,
                    channel_id,
                    command_name,
                    custom_id,
                )
                raise

            if not retryable or is_last_attempt:
                logger.error(
                    "safe_send_interaction_message 失敗: status=%s retryable=%s attempt=%s/%s user_id=%s guild_id=%s channel_id=%s command=%s custom_id=%s error=%s",
                    status,
                    retryable,
                    attempt + 1,
                    max_retries + 1,
                    interaction.user.id if interaction.user else None,
                    guild_id,
                    channel_id,
                    command_name,
                    custom_id,
                    str(e),
                )
                raise

            delay = retry_base_delay * (2 ** attempt)
            logger.warning(
                "safe_send_interaction_message 遇到可重試錯誤，將重試: status=%s attempt=%s/%s delay=%.2fs user_id=%s guild_id=%s channel_id=%s command=%s custom_id=%s",
                status,
                attempt + 1,
                max_retries + 1,
                delay,
                interaction.user.id if interaction.user else None,
                guild_id,
                channel_id,
                command_name,
                custom_id,
            )
            await asyncio.sleep(delay)

class ChannelConfig:
    """管理從配置文件中讀取頻道 ID 的類別"""
    DEFAULT_ID = 1234567890  # 預設佔位符 ID

    @staticmethod
    def load_config(config_file="config.json", caller="unknown") -> dict:
        """讀取完整設定檔，讀取失敗時回傳空 dict。"""
        logger.debug(f"開始讀取設定檔: {config_file} (調用者: {caller})")
        config = {}
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    config = json.load(f)
            except json.JSONDecodeError as e:
                logger.error(f"無法讀取 {config_file}，JSON 解碼錯誤: {str(e)} (調用者: {caller})")
            except Exception as e:
                logger.error(f"讀取 {config_file} 時發生未知錯誤: {str(e)} (調用者: {caller})")
        else:
            logger.warning(f"配置文件 {config_file} 不存在，回傳空設定 (調用者: {caller})")
        return config

    @staticmethod
    def save_config(config: dict, config_file="config.json", caller="unknown") -> None:
        """寫入完整設定檔。"""
        try:
            with open(config_file, 'w') as f:
                json.dump(config, f, indent=2)
            logger.debug(f"設定檔已寫入: {config_file} (調用者: {caller})")
        except Exception as e:
            logger.error(f"寫入 {config_file} 失敗: {str(e)} (調用者: {caller})")
            raise

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

async def get_intro_channel_id(config_file="config.json", caller="unknown"):
    """從配置文件中讀取自我介紹頻道 ID"""
    return await ChannelConfig.get_channel_id('intro_channel_id', config_file, caller)

async def check_role(user, required_role: str = None) -> bool:
    """
    檢查使用者是否具有特定角色

    Args:
        user: Discord 使用者或成員對象
        required_role: 所需的角色名稱（例如 'Trader' 或 'Moderator'）

    Returns:
        bool: 使用者是否具有所需角色
    """
    if required_role:
        owner_id = int(os.getenv('OWNER_ID', '0'))
        if user.id == owner_id:
            logger.info(f'使用者 {user.name} 是 owner，自動通過角色權限檢查')
            return True
        config_file = "config.json"
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    config = json.load(f)
                    allowed_role_ids = config.get("role_mapping", {}).get(required_role, [])
                    if allowed_role_ids:  # 檢查是否有設定任何身份組 ID
                        user_roles = [role.id for role in user.roles] if hasattr(user, 'roles') else []
                        if any(role_id in user_roles for role_id in allowed_role_ids):
                            return True
                        else:
                            logger.info(f'使用者 {user.name} 嘗試使用需要 {required_role} 角色的功能，已被拒絕')
                            return False
            except json.JSONDecodeError as e:
                logger.error(f"無法讀取 {config_file}，JSON 解碼錯誤: {str(e)}")
            except Exception as e:
                logger.error(f"讀取 {config_file} 時發生未知錯誤: {str(e)}")
        return False  # 如果配置文件不存在或角色未定義，則拒絕訪問
    return True

async def check_guild(interaction: discord.Interaction, owner_only: bool = False, admin_only: bool = False, required_role: str = None) -> bool:
    """
    檢查命令使用權限

    Args:
        interaction: Discord 互動物件
        owner_only: 是否僅限擁有者使用
        admin_only: 是否僅限管理員使用
        required_role: 所需的角色名稱（例如 'Trader' 或 'Moderator'）

    Returns:
        bool: 是否通過權限檢查
    """
    # 檢查是否在伺服器中使用
    if not interaction.guild:
        await safe_send_interaction_message(interaction, "此命令只能在伺服器中使用，無法在私人訊息中使用。", ephemeral=True)
        logger.info(f'使用者 {interaction.user} 嘗試在私人訊息中使用命令，已被拒絕')
        return False

    # 檢查擁有者權限（最高優先級）
    if owner_only:
        owner_id = int(os.getenv('OWNER_ID', '0'))
        if interaction.user.id != owner_id:
            await safe_send_interaction_message(interaction, "❌ 此命令僅限指定擁有者使用！", ephemeral=True)
            logger.info(f'使用者 {interaction.user} 嘗試使用僅限擁有者的命令，已被拒絕')
            return False

    # 檢查管理員權限
    elif admin_only:
        if not interaction.user.guild_permissions.administrator:
            await safe_send_interaction_message(interaction, "❌ 此命令僅限管理員使用！", ephemeral=True)
            logger.info(f'使用者 {interaction.user} 嘗試使用僅限管理員的命令，已被拒絕')
            return False

    # 檢查角色權限
    if required_role:
        if not await check_role(interaction.user, required_role):
            await safe_send_interaction_message(interaction, f"❌ 此命令僅限具有 {required_role} 角色的使用者使用！", ephemeral=True)
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

def create_paginated_view(
    options,
    placeholder_text,
    embed_title,
    embed_description,
    embed_color,
    on_select_callback,
    custom_id_prefix: str = "paginated",
):
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
        safe_prefix = (custom_id_prefix or "paginated").replace(" ", "_")
        if callable(placeholder_text):
            placeholder = placeholder_text(page)
        else:
            placeholder = placeholder_text + (f" (第 {page + 1} 頁)" if len(options) > ITEMS_PER_PAGE else "")

        channel_select = discord.ui.Select(
            placeholder=placeholder,
            custom_id=f"{safe_prefix}_select_{page}",
            options=get_paginated_options(options, page, ITEMS_PER_PAGE)
        )

        async def channel_select_callback(interaction: discord.Interaction):
            try:
                logger.info(
                    "interaction_start source=paginated_select custom_id=%s user_id=%s guild_id=%s channel_id=%s",
                    getattr(channel_select, "custom_id", None),
                    interaction.user.id if interaction.user else None,
                    interaction.guild.id if interaction.guild else None,
                    interaction.channel.id if interaction.channel else None,
                )
                selected_value = channel_select.values[0]
                await on_select_callback(interaction, selected_value)
            except Exception as e:
                logger.error(
                    "interaction_error source=paginated_select custom_id=%s user_id=%s guild_id=%s channel_id=%s error=%s",
                    getattr(channel_select, "custom_id", None),
                    interaction.user.id if interaction.user else None,
                    interaction.guild.id if interaction.guild else None,
                    interaction.channel.id if interaction.channel else None,
                    str(e),
                    exc_info=True,
                )
                await safe_send_interaction_message(interaction, "操作時發生錯誤，請稍後再試。", ephemeral=True)

        channel_select.callback = channel_select_callback

        view = discord.ui.View()
        view.add_item(channel_select)

        if len(options) > ITEMS_PER_PAGE:
            prev_button = discord.ui.Button(
                label="上一頁",
                style=discord.ButtonStyle.primary,
                disabled=page <= 0,
                custom_id=f"{safe_prefix}_prev_{page}",
            )
            next_button = discord.ui.Button(
                label="下一頁",
                style=discord.ButtonStyle.primary,
                disabled=(page + 1) * ITEMS_PER_PAGE >= len(options),
                custom_id=f"{safe_prefix}_next_{page}",
            )

            async def prev_button_callback(interaction: discord.Interaction):
                try:
                    logger.info(
                        "interaction_start source=paginated_prev custom_id=%s user_id=%s guild_id=%s channel_id=%s",
                        getattr(prev_button, "custom_id", None),
                        interaction.user.id if interaction.user else None,
                        interaction.guild.id if interaction.guild else None,
                        interaction.channel.id if interaction.channel else None,
                    )
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
                except Exception as e:
                    logger.error(
                        "interaction_error source=paginated_prev custom_id=%s user_id=%s guild_id=%s channel_id=%s error=%s",
                        getattr(prev_button, "custom_id", None),
                        interaction.user.id if interaction.user else None,
                        interaction.guild.id if interaction.guild else None,
                        interaction.channel.id if interaction.channel else None,
                        str(e),
                        exc_info=True,
                    )
                    await safe_send_interaction_message(interaction, "切換頁面時發生錯誤，請稍後再試。", ephemeral=True)

            async def next_button_callback(interaction: discord.Interaction):
                try:
                    logger.info(
                        "interaction_start source=paginated_next custom_id=%s user_id=%s guild_id=%s channel_id=%s",
                        getattr(next_button, "custom_id", None),
                        interaction.user.id if interaction.user else None,
                        interaction.guild.id if interaction.guild else None,
                        interaction.channel.id if interaction.channel else None,
                    )
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
                except Exception as e:
                    logger.error(
                        "interaction_error source=paginated_next custom_id=%s user_id=%s guild_id=%s channel_id=%s error=%s",
                        getattr(next_button, "custom_id", None),
                        interaction.user.id if interaction.user else None,
                        interaction.guild.id if interaction.guild else None,
                        interaction.channel.id if interaction.channel else None,
                        str(e),
                        exc_info=True,
                    )
                    await safe_send_interaction_message(interaction, "切換頁面時發生錯誤，請稍後再試。", ephemeral=True)

            prev_button.callback = prev_button_callback
            next_button.callback = next_button_callback

            view.add_item(prev_button)
            view.add_item(next_button)

        return view

    return current_page, update_view(current_page)
