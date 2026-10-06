from pathlib import Path
from typing import Optional
import copy
import logging
import json
import os
import asyncio
import threading
import discord

from utils.safe_write import replace_text

# 獲取 logger
logger = logging.getLogger(__name__)


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

class ConfigWriteError(RuntimeError):
    """設定檔讀不到或格式壞掉，這次沒有寫入（避免把整份檔寫成只剩這次改的那一項）。"""


class ChannelConfig:
    """讀寫 config.json（綁頻道、綁身分組、Telegram 路由等）。

    **讀**：依檔案修改時間快取，手改後下一次讀就生效（以前是 5 分鐘 TTL）。回傳的是複本，呼叫端改了也不會
    影響別人。檔案壞掉（JSON 寫錯）時沿用上一次讀到的正確內容並記 error，不會讓所有綁頻道的功能一起停。

    **寫**：一律 `update_config`。寫入前重讀磁碟上最新的內容、只套用這次的變動、安全寫入（暫存檔換名，每天第一次
    改寫前備份到 `/logs/config_backup`）。以前是拿 5 分鐘快取裡的整份設定寫回：使用者手改後 5 分鐘內有人從
    Discord 存任何設定，手改的內容就被舊快取蓋掉；檔案壞掉時更會寫成只剩一個 key（使用者 10-06 SW-Q4）。
    """
    DEFAULT_ID = 1234567890  # 預設佔位符 ID
    #: {config_file: (修改時間 ns, 設定)}
    _cache: dict = {}
    #: 同一個行程裡的寫入排隊（讀檔、改、寫回這三步不能交錯）
    _write_lock = threading.Lock()
    BACKUP_DIR = "/logs/config_backup"
    BACKUP_KEEP = 14

    @staticmethod
    def load_config(config_file="config.json", caller="unknown") -> dict:
        """讀取完整設定檔（檔案沒改就用快取）；回傳複本。讀不到時回上次的正確內容，從來沒讀到過就回空 dict。"""
        try:
            mtime_ns = os.stat(config_file).st_mtime_ns
        except FileNotFoundError:
            logger.warning(f"配置文件 {config_file} 不存在，回傳空設定 (調用者: {caller})")
            return {}
        cached = ChannelConfig._cache.get(config_file)
        if cached is not None and cached[0] == mtime_ns:
            return copy.deepcopy(cached[1])
        logger.debug(f"從磁碟讀取設定檔: {config_file} (調用者: {caller})")
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config = json.load(f)
            if not isinstance(config, dict):
                raise ValueError("最外層不是 JSON 物件")
        except Exception as e:
            logger.error(f"無法讀取 {config_file}（沿用上次讀到的內容）：{e} (調用者: {caller})")
            return copy.deepcopy(cached[1]) if cached is not None else {}
        ChannelConfig._cache[config_file] = (mtime_ns, config)
        return copy.deepcopy(config)

    @staticmethod
    def _update_sync(apply, config_file: str, caller: str) -> dict:
        with ChannelConfig._write_lock:
            path = Path(config_file)
            # 檔案不見（被刪、編輯器存檔換名的瞬間）也拒絕：當成空的寫回去，整份設定就只剩這次改的那一項
            if not path.exists():
                raise ConfigWriteError(f"{config_file} 不存在，沒有寫入")
            try:
                config = json.loads(path.read_text(encoding="utf-8"))
            except Exception as e:
                raise ConfigWriteError(f"{config_file} 格式錯誤，沒有寫入：{e}") from e
            if not isinstance(config, dict):
                raise ConfigWriteError(f"{config_file} 最外層不是 JSON 物件，沒有寫入")
            apply(config)
            try:
                replace_text(path, json.dumps(config, indent=2), backup_dir=ChannelConfig.BACKUP_DIR,
                             keep=ChannelConfig.BACKUP_KEEP)
            except OSError as e:
                # 備份目錄不能寫、磁碟滿：原檔不動，讓呼叫端回覆使用者（不然按了沒反應）
                raise ConfigWriteError(f"{config_file} 寫入失敗，沒有寫入：{e}") from e
            ChannelConfig._cache[config_file] = (path.stat().st_mtime_ns, config)
            logger.info(f"設定檔已寫入: {config_file} (調用者: {caller})")
            return copy.deepcopy(config)

    @staticmethod
    async def update_config(apply, config_file="config.json", caller="unknown") -> dict:
        """改設定檔：`apply(config)` 直接改傳進來的 dict（磁碟上最新的內容），回傳寫入後的複本。

        `apply` 會在執行緒裡跑，只能改 dict，不要在裡面呼叫 Discord。檔案讀不到或格式錯誤時拋 `ConfigWriteError`，
        檔案不動。
        """
        return await asyncio.to_thread(ChannelConfig._update_sync, apply, config_file, caller)

    @staticmethod
    async def get_channel_id(config_key, config_file="config.json", caller="unknown"):
        """從配置文件中讀取指定鍵的頻道 ID（使用快取）"""
        config = ChannelConfig.load_config(config_file, caller)
        channel_id = config.get(config_key, ChannelConfig.DEFAULT_ID)
        if channel_id != ChannelConfig.DEFAULT_ID:
            logger.debug(f"取得頻道 ID: {channel_id} (鍵: {config_key}，調用者: {caller})")
        else:
            logger.warning(f"頻道 ID 未設定，使用預設佔位符 (鍵: {config_key}，調用者: {caller})")
        return channel_id

    @staticmethod
    async def get_configured_id(config_key, config_file="config.json", caller="unknown") -> Optional[int]:
        """有設定才回頻道 id；沒設定（佔位符或缺 key）回 None，不記警告。

        給「頻道可以不綁」的功能用：呼叫端拿到 None 就自己決定要不要記 log，
        不用各自再比一次 DEFAULT_ID（以前全專案有八份這種比對）。"""
        channel_id = ChannelConfig.load_config(config_file, caller).get(config_key)
        if not channel_id or channel_id == ChannelConfig.DEFAULT_ID:
            return None
        return int(channel_id)

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

async def get_forum_article_channel_id(config_file="config.json", caller="unknown"):
    """從配置文件中讀取論壇文章頻道 ID"""
    return await ChannelConfig.get_channel_id('forum_article_channel_id', config_file, caller)

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

# check_guild(permission=...) 不通過時給使用者看的權限名稱
_PERMISSION_NAMES = {"manage_messages": "管理訊息"}


async def check_guild(interaction: discord.Interaction, owner_only: bool = False, admin_only: bool = False,
                      required_role: str = None, permission: str = None) -> bool:
    """
    檢查命令使用權限

    Args:
        interaction: Discord 互動物件
        owner_only: 是否僅限擁有者使用
        admin_only: 是否僅限管理員使用
        required_role: 所需的角色名稱（例如 'Trader' 或 'Moderator'）
        permission: 所需的 Discord 權限（例如 'manage_messages'）。看的是**這個頻道**解析過覆寫的權限
            （`interaction.permissions`，thread 繼承母頻道）；`OWNER_ID` 自動通過，跟 check_role 一致

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

    # 檢查 Discord 權限
    if permission:
        owner_id = int(os.getenv('OWNER_ID', '0'))
        if not (getattr(interaction.permissions, permission, False) or interaction.user.id == owner_id):
            name = _PERMISSION_NAMES.get(permission, permission)
            await safe_send_interaction_message(interaction, f"❌ 需要「{name}」權限才能操作。", ephemeral=True)
            logger.info(f'使用者 {interaction.user} 沒有 {permission} 權限，已被拒絕')
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
