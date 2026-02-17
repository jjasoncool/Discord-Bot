
import json
import os
import logging
import discord
from discord import app_commands
from discord.ext import commands
from constants import ITEMS

# 獲取 logger
logger = logging.getLogger('discord_bot')

# 監控頻道的字典，格式: {guild_id: {channel_id: [{關鍵字列表, 使用者ID, 通知設定}]}}
monitored_channels = {}
monitored_channels_file = "settings/monitored_channels.json"

import json
import os
from utils.utils import create_paginated_view, ITEMS_PER_PAGE, safe_send_interaction_message

def load_monitored_channels():
    """從檔案中讀取監控設定"""
    global monitored_channels
    if os.path.exists(monitored_channels_file):
        try:
            with open(monitored_channels_file, 'r') as f:
                # 將鍵轉換為整數
                data = json.load(f)
                monitored_channels = {
                    int(guild_id): {
                        int(channel_id): settings if isinstance(settings, list) else [settings]
                        for channel_id, settings in channels.items()
                    }
                    for guild_id, channels in data.items()
                }
        except json.JSONDecodeError:
            logger.error(f"無法讀取 {monitored_channels_file}，將使用空設定")
            monitored_channels = {}
        except Exception as e:
            logger.error(f"讀取監控設定時發生錯誤: {str(e)}")
            monitored_channels = {}

def save_monitored_channels():
    """將監控設定保存到檔案"""
    try:
        # 將鍵轉換為字符串以便保存到 JSON
        data = {
            str(guild_id): {
                str(channel_id): settings
                for channel_id, settings in channels.items()
            }
            for guild_id, channels in monitored_channels.items()
        }
        with open(monitored_channels_file, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"保存監控設定時發生錯誤: {str(e)}")

class UserCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        load_monitored_channels()
        logger.info("監控設定已從檔案中讀取")

    async def _check_guild_and_owner(self, interaction: discord.Interaction, owner_only: bool = False) -> bool:
        """檢查命令是否在伺服器中使用且使用者是否為伺服器擁有者（如果啟用了限制）"""
        from utils.utils import check_guild
        return await check_guild(interaction, owner_only)

    async def _send_error_message(self, interaction: discord.Interaction, message: str):
        """發送錯誤訊息"""
        await safe_send_interaction_message(interaction, message, ephemeral=True)

    class KeywordsModal(discord.ui.Modal, title="設定監控關鍵字"):
        def __init__(self, cog: "UserCommands", notify: bool = True):
            super().__init__()
            self.cog = cog
            self.notify = notify
            self.keywords_input = discord.ui.TextInput(
                label="監控關鍵字（用逗號分隔）",
                placeholder="輸入要監控的關鍵字，例如：交易,出售,求購",
                required=True,
                style=discord.TextStyle.short
            )
            self.add_item(self.keywords_input)

        async def on_submit(self, interaction: discord.Interaction):
            keywords = self.keywords_input.value
            await self.cog.monitor_channel_cmd(interaction, keywords, self.notify)

    async def monitor_channel_cmd(self, interaction: discord.Interaction, keywords: str = None, notify: bool = True):
        """設定監控特定頻道的訊息"""
        logger.info(f'收到來自 {interaction.user} 的 /monitor_channel 斜線命令，參數: keywords="{keywords}", notify={notify}')

        if not await self._check_guild_and_owner(interaction, owner_only=False):
            return

        # 獲取使用者有權限查看的文字頻道和論壇頻道
        member = interaction.guild.me if interaction.guild.me else interaction.guild.get_member(interaction.user.id)
        if member is None:
            await safe_send_interaction_message(interaction, "無法獲取您的成員資訊，請重試。", ephemeral=True)
            return

        channels = [channel for channel in interaction.guild.channels
                   if isinstance(channel, (discord.TextChannel, discord.ForumChannel))
                   and channel.permissions_for(member).view_channel]

        if not channels:
            await safe_send_interaction_message(interaction, "您沒有權限查看任何文字或論壇頻道！", ephemeral=True)
            return

        # 創建頻道選單，實現分頁功能
        channel_options = [
            discord.SelectOption(
                label=channel.name,
                value=str(channel.id),
                description=f"ID: {channel.id}",
                emoji="📝" if isinstance(channel, discord.TextChannel) else "📌"
            )
            for channel in channels
        ]

        if not channel_options:
            await safe_send_interaction_message(interaction, "沒有可供選擇的頻道！", ephemeral=True)
            return

        async def on_select_callback(interaction, selected_value):
            selected_channel_id = int(selected_value)
            channel = interaction.guild.get_channel(selected_channel_id)
            if channel and isinstance(channel, (discord.TextChannel, discord.ForumChannel)):
                # 解析關鍵字列表
                keyword_list = [kw.strip() for kw in keywords.split(',') if kw.strip()]
                if not keyword_list:
                    await safe_send_interaction_message(interaction, "請提供至少一個要監控的關鍵字！", ephemeral=True)
                    return

                # 設定監控
                guild_id = interaction.guild.id
                if guild_id not in monitored_channels:
                    monitored_channels[guild_id] = {}

                if selected_channel_id not in monitored_channels[guild_id]:
                    monitored_channels[guild_id][selected_channel_id] = []

                # 檢查是否已有該使用者的設定
                user_settings = next(
                    (setting for setting in monitored_channels[guild_id][selected_channel_id] if setting['user_id'] == interaction.user.id),
                    None
                )

                if user_settings:
                    # 更新現有設定
                    user_settings['keywords'] = keyword_list
                    user_settings['notify'] = notify
                else:
                    # 新增設定
                    monitored_channels[guild_id][selected_channel_id].append({
                        'keywords': keyword_list,
                        'user_id': interaction.user.id,
                        'notify': notify
                    })

                save_monitored_channels()

                await interaction.response.edit_message(view=None)
                await safe_send_interaction_message(
                    interaction,
                    f"✅ 已開始監控頻道 **{channel.name}**！\n"
                    f"監控關鍵字: {', '.join(f'`{kw}`' for kw in keyword_list)}\n"
                    f"通知設定: {'開啟' if notify else '關閉'}",
                    ephemeral=True
                )
            else:
                await safe_send_interaction_message(interaction, "選擇的頻道無效或不是文字/論壇頻道，請重試。", ephemeral=True)

        current_page, channel_view = create_paginated_view(
            channel_options,
            "選擇要監控的頻道...",
            "選擇監控頻道",
            "請從以下選項中選擇一個文字或論壇頻道進行監控。",
            discord.Color.blue(),
            on_select_callback,
            custom_id_prefix="user_watch_keywords_channel"
        )

        embed = discord.Embed(
            title="選擇監控頻道",
            description="請從以下選項中選擇一個文字或論壇頻道進行監控。",
            color=discord.Color.blue()
        )
        await safe_send_interaction_message(interaction, embed=embed, view=channel_view, ephemeral=True)

    async def stop_monitoring_cmd(self, interaction: discord.Interaction):
        """停止監控指定頻道"""
        logger.info(f'收到來自 {interaction.user} 的 /stop_monitoring 斜線命令')

        if not await self._check_guild_and_owner(interaction, owner_only=False):
            return

        guild_id = interaction.guild.id
        user_id = interaction.user.id

        # 檢查使用者是否有任何監控設定
        if guild_id not in monitored_channels or not monitored_channels[guild_id]:
            await self._send_error_message(interaction, "您未設定任何監控！")
            return

        # 找出使用者有監控設定的頻道
        user_monitored_channels = []
        for channel_id, settings_list in monitored_channels[guild_id].items():
            if any(setting['user_id'] == user_id for setting in settings_list):
                channel = interaction.guild.get_channel(channel_id)
                if channel and isinstance(channel, (discord.TextChannel, discord.ForumChannel)):
                    user_monitored_channels.append(channel)

        if not user_monitored_channels:
            await self._send_error_message(interaction, "您未設定任何監控！")
            return

        # 創建頻道選單，實現分頁功能
        channel_options = [
            discord.SelectOption(
                label=channel.name,
                value=str(channel.id),
                description=f"ID: {channel.id}",
                emoji="📝" if isinstance(channel, discord.TextChannel) else "📌"
            )
            for channel in user_monitored_channels
        ]

        async def on_select_callback(interaction, selected_value):
            selected_channel_id = int(selected_value)
            channel = interaction.guild.get_channel(selected_channel_id)

            if channel and isinstance(channel, (discord.TextChannel, discord.ForumChannel)):
                # 移除該頻道中使用者的監控設定
                settings_list = monitored_channels[guild_id][selected_channel_id]
                user_settings = [setting for setting in settings_list if setting['user_id'] == user_id]

                if user_settings:
                    # 移除使用者的設定
                    monitored_channels[guild_id][selected_channel_id] = [
                        setting for setting in settings_list if setting['user_id'] != user_id
                    ]

                    # 如果該頻道沒有其他人的監控設定了，則刪除該頻道
                    if not monitored_channels[guild_id][selected_channel_id]:
                        del monitored_channels[guild_id][selected_channel_id]

                    # 如果該伺服器沒有任何監控設定了，則刪除該伺服器
                    if not monitored_channels[guild_id]:
                        del monitored_channels[guild_id]

                    save_monitored_channels()

                    # 顯示停止的監控詳情
                    keywords_info = []
                    for setting in user_settings:
                        keywords = ", ".join(f"`{kw}`" for kw in setting['keywords'])
                        keywords_info.append(keywords)

                    await interaction.response.edit_message(view=None)
                    await safe_send_interaction_message(
                        interaction,
                        f"✅ 已停止監控頻道 **{channel.name}**！\n"
                        f"停止的監控關鍵字: {', '.join(keywords_info)}",
                        ephemeral=True
                    )
                else:
                    await safe_send_interaction_message(interaction, "您在此頻道沒有任何監控設定！", ephemeral=True)
            else:
                await safe_send_interaction_message(interaction, "選擇的頻道無效或不是文字/論壇頻道，請重試。", ephemeral=True)

        current_page, channel_view = create_paginated_view(
            channel_options,
            lambda page: f"選擇要停止監控的頻道... (第 {page + 1} 頁)" if len(channel_options) > ITEMS_PER_PAGE else "選擇要停止監控的頻道...",
            "選擇要停止監控的頻道",
            lambda page: f"請從以下選項中選擇一個要停止監控的頻道。(第 {page + 1} 頁)" if len(channel_options) > ITEMS_PER_PAGE else "請從以下選項中選擇一個要停止監控的頻道。",
            discord.Color.red(),
            on_select_callback,
            custom_id_prefix="user_stop_monitoring_channel"
        )

        description_text = f"請從以下選項中選擇一個要停止監控的頻道。" if len(channel_options) <= ITEMS_PER_PAGE else f"請從以下選項中選擇一個要停止監控的頻道。(第 {current_page + 1} 頁)"
        embed = discord.Embed(
            title="選擇要停止監控的頻道",
            description=description_text,
            color=discord.Color.red()
        )

        # 第一個訊息：嵌入 + 選擇框
        await safe_send_interaction_message(interaction, embed=embed, view=channel_view, ephemeral=True)

        # 新增「停止所有監控」按鈕
        class StopAllButton(discord.ui.Button):
            def __init__(self):
                super().__init__(label="🛑 停止所有監控", style=discord.ButtonStyle.danger, custom_id="stop_all_monitoring")

            async def callback(self, interaction: discord.Interaction):
                guild_id = interaction.guild.id
                user_id = interaction.user.id
                removed_channels = []
                if guild_id in monitored_channels:
                    for channel_id in list(monitored_channels[guild_id].keys()):
                        settings_list = monitored_channels[guild_id][channel_id]
                        original_length = len(settings_list)
                        settings_list = [setting for setting in settings_list if setting['user_id'] != user_id]
                        if len(settings_list) < original_length:
                            channel = interaction.guild.get_channel(channel_id)
                            channel_name = channel.name if channel else f"ID: {channel_id}"
                            removed_channels.append(channel_name)
                        if settings_list:
                            monitored_channels[guild_id][channel_id] = settings_list
                        else:
                            del monitored_channels[guild_id][channel_id]
                    if not monitored_channels[guild_id]:
                        del monitored_channels[guild_id]
                    if removed_channels:
                        save_monitored_channels()
                        await interaction.response.edit_message(view=None)
                        await safe_send_interaction_message(
                            interaction,
                            f"✅ 已停止監控以下所有頻道：\n" + "\n".join(f"- **{name}**" for name in removed_channels),
                            ephemeral=True
                        )
                        return
                await safe_send_interaction_message(interaction, "您未設定任何監控！", ephemeral=True)

        stop_all_view = discord.ui.View()
        stop_all_view.add_item(StopAllButton())

        # 第二個訊息：文字 + 按鈕
        await safe_send_interaction_message(interaction, "如果要取消所有頻道的監控，請點選下方按鈕：", view=stop_all_view, ephemeral=True)

    async def list_monitored_cmd(self, interaction: discord.Interaction):
        """列出目前監控的所有頻道"""
        logger.info(f'收到來自 {interaction.user} 的 /list_monitored 斜線命令')

        if not await self._check_guild_and_owner(interaction, owner_only=False):
            return

        # 檢查是否有監控的頻道
        guild_id = interaction.guild.id
        if (guild_id not in monitored_channels or
            not monitored_channels[guild_id]):
            await self._send_error_message(interaction, "目前沒有監控任何頻道！")
            return

        # 創建嵌入訊息
        embed = discord.Embed(
            title="監控頻道列表",
            description="以下是目前正在監控的頻道列表：",
            color=discord.Color.green()
        )

        for ch_id, settings_list in monitored_channels[guild_id].items():
            channel = interaction.guild.get_channel(ch_id)
            channel_name = channel.name if channel else f"未知頻道 (ID: {ch_id})"

            for idx, settings in enumerate(settings_list):
                keywords = ", ".join(f"`{kw}`" for kw in settings['keywords'])
                user = self.bot.get_user(settings['user_id'])
                if user:
                    user_name = user.mention
                else:
                    # 嘗試從伺服器成員中查找使用者，使用 fetch_member
                    try:
                        member = await interaction.guild.fetch_member(settings['user_id'])
                        user_name = member.mention
                    except discord.NotFound:
                        user_name = f"無法獲取使用者資訊"
                        logger.warning(f"無法獲取使用者資訊，ID: {settings['user_id']}，可能已離開伺服器")
                    except discord.Forbidden:
                        user_name = f"無法獲取使用者資訊"
                        logger.warning(f"無法獲取使用者資訊，ID: {settings['user_id']}，機器人無權限")
                    except Exception as e:
                        user_name = f"無法獲取使用者資訊"
                        logger.warning(f"無法獲取使用者資訊，ID: {settings['user_id']}，錯誤: {str(e)}")

                embed.add_field(
                    name=f"📝 {channel_name} - 設定 {idx + 1}",
                    value=f"監控關鍵字: {keywords}\n"
                          f"設定者: {user_name}\n"
                          f"通知設定: {'開啟' if settings.get('notify', True) else '關閉'}\n"
                          f"頻道 ID: {ch_id}",
                    inline=False
                )

        await safe_send_interaction_message(interaction, embed=embed, ephemeral=True)

    # 處理所有訊息以實現監控功能
    @commands.Cog.listener()
    async def on_message(self, message):
        # 避免處理機器人訊息（包括自己的訊息），除非是在交易論壇頻道中
        if message.author.bot:
            from utils.utils import get_trade_forum_channel_id
            # 獲取交易論壇頻道 ID
            try:
                trade_forum_channel_id = await get_trade_forum_channel_id(config_file="config.json", caller="UserCommands")
            except Exception as e:
                logger.error(f"無法獲取交易論壇頻道 ID: {str(e)}")
                trade_forum_channel_id = None
            # 如果訊息是在交易論壇頻道中，則允許處理
            if trade_forum_channel_id and isinstance(message.channel, discord.Thread) and message.channel.parent_id == trade_forum_channel_id:
                logger.debug(f"處理機器人訊息，因為是在交易論壇頻道 (ID: {trade_forum_channel_id})")
            else:
                logger.debug(f"跳過處理機器人訊息 - 作者: {message.author.name} (ID: {message.author.id})")
                return

        # 檢查訊息是否在監控的頻道中
        if not message.guild:
            return

        guild_id = message.guild.id
        channel_id = message.channel.id
        parent_channel_id = None

        # 檢查訊息是否在線程（貼文）中，並獲取父頻道 ID
        if hasattr(message.channel, 'parent') and message.channel.parent:
            parent_channel_id = message.channel.parent.id
        elif hasattr(message.channel, 'parent_id') and message.channel.parent_id:
            parent_channel_id = message.channel.parent_id

        # 檢查訊息是否直接在監控的頻道中，或是監控頻道的線程中
        if guild_id in monitored_channels:
            monitored_channel_id = None
            if channel_id in monitored_channels[guild_id]:
                monitored_channel_id = channel_id
            elif parent_channel_id and parent_channel_id in monitored_channels[guild_id]:
                monitored_channel_id = parent_channel_id

            if monitored_channel_id:
                settings_list = monitored_channels[guild_id][monitored_channel_id]
                content_lower = message.content.lower() if not message.author.bot else ""
                thread_title_lower = message.channel.name.lower() if message.author.bot and isinstance(message.channel, discord.Thread) else ""

                # 記錄所有被監控頻道的對話，以便除錯
                channel_name = message.channel.parent.name if parent_channel_id else message.channel.name
                thread_name = f"貼文: {message.channel.name}" if parent_channel_id else ""
                logger.debug(f"監控頻道訊息 - 伺服器: {message.guild.name}, 頻道: {channel_name} {thread_name}, 發送者: {message.author.display_name} ({message.author.id}), 內容: {message.content[:200]}...")

                import re
                for settings in settings_list:
                    # 檢查訊息是否包含監控的關鍵字
                    found_keywords = []
                    for kw in settings['keywords']:
                        # 使用正則表達式進行匹配，忽略大小寫，不要求整詞匹配
                        pattern = re.escape(kw.lower())
                        if message.author.bot and thread_title_lower:
                            if re.search(pattern, thread_title_lower):
                                found_keywords.append(kw)
                        elif re.search(pattern, content_lower):
                            found_keywords.append(kw)

                    if found_keywords and settings.get('notify', True):
                        # 獲取監控者，優先使用 fetch_member
                        user = None
                        try:
                            user = await message.guild.fetch_member(settings['user_id'])
                        except discord.NotFound:
                            logger.warning(f"無法獲取監控者資訊，ID: {settings['user_id']}，可能已離開伺服器")
                        except discord.Forbidden:
                            logger.warning(f"無法獲取監控者資訊，ID: {settings['user_id']}，機器人無權限")
                        except Exception as e:
                            logger.warning(f"無法獲取監控者資訊，ID: {settings['user_id']}，錯誤: {str(e)}")

                        if not user:
                            # 嘗試其他方法
                            user = self.bot.get_user(settings['user_id'])
                            if not user:
                                user = message.guild.get_member(settings['user_id'])
                                if not user:
                                    logger.warning(f"所有方法均無法獲取監控者資訊，ID: {settings['user_id']}")

                        if user:
                            try:
                                channel_name = message.channel.parent.name if parent_channel_id else message.channel.name
                                thread_name = f"貼文: {message.channel.name}" if parent_channel_id else ""
                                # 建立嵌入訊息以通知監控者
                                embed = discord.Embed(
                                    title="🔔 關鍵字偵測通知",
                                    description=f"在頻道 **{channel_name}** {thread_name} 中偵測到您監控的關鍵字！",
                                    color=discord.Color.gold(),
                                    timestamp=message.created_at
                                )

                                embed.add_field(
                                    name="偵測到的關鍵字",
                                    value=", ".join(f"`{kw}`" for kw in found_keywords),
                                    inline=False
                                )

                                embed.add_field(
                                    name="訊息內容",
                                    value=message.content[:1024],  # Discord 限制欄位值最多 1024 字元
                                    inline=False
                                )

                                embed.add_field(
                                    name="訊息連結",
                                    value=f"[點擊前往查看]({message.jump_url})",
                                    inline=False
                                )

                                embed.set_author(
                                    name=f"{message.author.display_name}",
                                    icon_url=message.author.display_avatar.url
                                )

                                await user.send(embed=embed)
                                logger.info(f"已向使用者 {user.name}#{user.discriminator} 發送關鍵字偵測通知")

                            except discord.Forbidden:
                                logger.warning(f"無法向使用者 {user.name}#{user.discriminator} 發送訊息，可能因為他們已關閉私人訊息")
                            except Exception as e:
                                logger.error(f"發送關鍵字通知時發生錯誤: {str(e)}")

    @app_commands.command(name="watch_keywords", description="設定頻道中的關鍵字監控")
    async def watch_keywords_cmd(self, interaction: discord.Interaction):
        """斜線命令：設定頻道中的關鍵字監控"""
        logger.info(f'收到來自 {interaction.user} 的 /watch_keywords 斜線命令')

        if not await self._check_guild_and_owner(interaction, owner_only=False):
            return

        # 創建操作按鈕
        monitor_button = discord.ui.Button(label="監控頻道關鍵字", style=discord.ButtonStyle.primary, custom_id="monitor_channel")
        stop_button = discord.ui.Button(label="停止監控", style=discord.ButtonStyle.danger, custom_id="stop_monitoring")
        list_button = discord.ui.Button(label="顯示監控列表", style=discord.ButtonStyle.secondary, custom_id="list_monitored")

        async def monitor_button_callback(interaction: discord.Interaction):
            await interaction.response.send_modal(self.KeywordsModal(self, notify=True))

        async def stop_button_callback(interaction: discord.Interaction):
            await self.stop_monitoring_cmd(interaction)

        async def list_button_callback(interaction: discord.Interaction):
            await self.list_monitored_cmd(interaction)

        monitor_button.callback = monitor_button_callback
        stop_button.callback = stop_button_callback
        list_button.callback = list_button_callback

        action_view = discord.ui.View()
        action_view.add_item(monitor_button)
        action_view.add_item(list_button)
        action_view.add_item(stop_button)

        embed = discord.Embed(
            title="頻道關鍵字監控",
            description="請選擇您要執行的操作：\n- **監控頻道關鍵字**：設定要在頻道中監控的關鍵字，當訊息包含這些關鍵字時您會收到通知。\n- **停止監控**：停止對特定頻道的關鍵字監控。\n- **顯示監控列表**：查看所有人設定的監控項目。",
            color=discord.Color.greyple()
        )
        await safe_send_interaction_message(interaction, embed=embed, view=action_view, ephemeral=True)

    async def get_user_item_prices(self, user_id: int, guild: discord.Guild = None) -> dict:
        """根據用戶 ID 獲取物品價格資訊"""
        prices_file_path = "/app/settings/item_prices.json"
        prices = {}
        if os.path.exists(prices_file_path):
            try:
                with open(prices_file_path, 'r', encoding='utf-8') as f:
                    prices = json.load(f)
            except Exception as e:
                logger.error(f"讀取價格檔案時發生錯誤: {str(e)}")
                return {}

        user_id_str = str(user_id)
        if user_id_str not in prices:
            return {}

        user_prices = prices.get(user_id_str, {})
        result = {}
        for item in ITEMS:
            price = user_prices.get(item['value'], "無價格設定")
            result[item['value']] = {
                'label': item['label'],
                'description': item['description'],
                'price': price
            }
        return result

    @app_commands.command(name="list_item_price", description="查看物品價格")
    async def list_item_price_cmd(self, interaction: discord.Interaction):
        """斜線命令：查看物品價格"""
        logger.info(f'收到來自 {interaction.user} 的 /list_item_price 斜線命令')

        from utils.utils import check_guild
        if not await check_guild(interaction):
            return

        prices_file_path = "/app/settings/item_prices.json"
        prices = {}
        if os.path.exists(prices_file_path):
            try:
                with open(prices_file_path, 'r', encoding='utf-8') as f:
                    prices = json.load(f)
            except Exception as e:
                logger.error(f"讀取價格檔案時發生錯誤: {str(e)}")
                await safe_send_interaction_message(interaction, "無法讀取價格設定，請稍後再試。", ephemeral=True)
                return

        if not prices:
            await safe_send_interaction_message(interaction, "目前沒有設定任何物品價格。", ephemeral=True)
            return

        seller_options = []
        for user_id in prices.keys():
            member = interaction.guild.get_member(int(user_id))
            if member:
                user_name = member.display_name if hasattr(member, 'display_name') else member.name if hasattr(member, 'name') else f"使用者ID: {user_id}"
            else:
                try:
                    member = await interaction.guild.fetch_member(int(user_id))
                    user_name = member.display_name if hasattr(member, 'display_name') else member.name if hasattr(member, 'name') else f"使用者ID: {user_id}"
                except (discord.NotFound, discord.HTTPException):
                    user_name = f"使用者ID: {user_id}"
            seller_options.append(discord.SelectOption(label=user_name, value=user_id))

        if not seller_options:
            await safe_send_interaction_message(interaction, "目前沒有賣家設定價格。", ephemeral=True)
            return

        seller_select = discord.ui.Select(
            placeholder="選擇一位賣家...",
            custom_id="user_list_item_price_seller_select",
            options=seller_options
        )

        async def seller_select_callback(interaction: discord.Interaction):
            selected_seller_id = seller_select.values[0]
            selected_seller = interaction.guild.get_member(int(selected_seller_id))
            if not selected_seller:
                try:
                    selected_seller = await interaction.guild.fetch_member(int(selected_seller_id))
                    seller_name = selected_seller.display_name if hasattr(selected_seller, 'display_name') else selected_seller.name if hasattr(selected_seller, 'name') else f"使用者ID: {selected_seller_id}"
                except (discord.NotFound, discord.HTTPException):
                    seller_name = f"使用者ID: {selected_seller_id}"
            else:
                seller_name = selected_seller.display_name if hasattr(selected_seller, 'display_name') else selected_seller.name if hasattr(selected_seller, 'name') else f"使用者ID: {selected_seller_id}"

            embed = discord.Embed(
                title=f"{seller_name} 的物品價格",
                description="以下是所有物品的價格資訊：",
                color=discord.Color.blue()
            )
            seller_prices = await self.get_user_item_prices(int(selected_seller_id))
            if seller_prices:
                for item_value, details in seller_prices.items():
                    embed.add_field(
                        name=f"{details['label']} ({details['description']})",
                        value=f"價格: {details['price']}",
                        inline=False
                    )
            else:
                embed.description = "此用戶未設定任何物品價格。"
            await safe_send_interaction_message(interaction, embed=embed, ephemeral=True)

        seller_select.callback = seller_select_callback
        seller_view = discord.ui.View()
        seller_view.add_item(seller_select)

        embed = discord.Embed(
            title="查看物品價格",
            description="請從以下選項中選擇一位賣家來查看其設定的價格。",
            color=discord.Color.blue()
        )
        await safe_send_interaction_message(interaction, embed=embed, view=seller_view, ephemeral=True)

async def setup(bot):
    await bot.add_cog(UserCommands(bot))
