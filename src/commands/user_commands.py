import logging
import discord
from discord import app_commands
from discord.ext import commands

# 獲取 logger
logger = logging.getLogger('discord_bot')

# 監控頻道的字典，格式: {guild_id: {channel_id: [{關鍵字列表, 使用者ID, 通知設定}]}}
monitored_channels = {}
monitored_channels_file = "monitored_channels.json"

import json
import os

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
        if not interaction.guild:
            await interaction.response.send_message("此命令只能在伺服器中使用！", ephemeral=True)
            return False
        if owner_only:
            import os
            owner_id = int(os.getenv('OWNER_ID', '0'))
            if interaction.user.id != owner_id:
                await interaction.response.send_message("此命令僅限指定擁有者使用！", ephemeral=True)
                return False
        return True

    async def _send_error_message(self, interaction: discord.Interaction, message: str):
        """發送錯誤訊息"""
        await interaction.response.send_message(message, ephemeral=True)

    @app_commands.command(name="monitor_channel", description="監控指定頻道的訊息，可用逗號分隔多個關鍵字")
    @app_commands.describe(
        keywords="要監控的關鍵字（用逗號分隔）",
        notify="是否在發現關鍵字時通知您"
    )
    async def monitor_channel_cmd(self, interaction: discord.Interaction, keywords: str, notify: bool = True):
        """斜線命令：設定監控特定頻道的訊息"""
        logger.info(f'收到來自 {interaction.user} 的 /monitor_channel 斜線命令，參數: keywords="{keywords}", notify={notify}')

        if not await self._check_guild_and_owner(interaction, owner_only=False):
            return

        # 獲取使用者有權限查看的文字頻道和論壇頻道
        member = interaction.guild.me if interaction.guild.me else interaction.guild.get_member(interaction.user.id)
        if member is None:
            await interaction.response.send_message("無法獲取您的成員資訊，請重試。", ephemeral=True)
            return

        channels = [channel for channel in interaction.guild.channels
                   if isinstance(channel, (discord.TextChannel, discord.ForumChannel))
                   and channel.permissions_for(member).view_channel]

        if not channels:
            await interaction.response.send_message("您沒有權限查看任何文字或論壇頻道！", ephemeral=True)
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
            await interaction.response.send_message("沒有可供選擇的頻道！", ephemeral=True)
            return

        ITEMS_PER_PAGE = 25
        current_page = 0

        def get_paginated_options(page):
            start_idx = page * ITEMS_PER_PAGE
            end_idx = start_idx + ITEMS_PER_PAGE
            return channel_options[start_idx:end_idx]

        def update_view(page):
            channel_select = discord.ui.Select(
                placeholder=f"選擇要監控的頻道... (第 {page + 1} 頁)",
                options=get_paginated_options(page)
            )

            async def channel_select_callback(interaction: discord.Interaction):
                selected_channel_id = int(channel_select.values[0])
                channel = interaction.guild.get_channel(selected_channel_id)
                if channel and isinstance(channel, (discord.TextChannel, discord.ForumChannel)):
                    # 解析關鍵字列表
                    keyword_list = [kw.strip() for kw in keywords.split(',') if kw.strip()]
                    if not keyword_list:
                        await interaction.response.send_message("請提供至少一個要監控的關鍵字！", ephemeral=True)
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
                    await interaction.followup.send(
                        f"✅ 已開始監控頻道 **{channel.name}**！\n"
                        f"監控關鍵字: {', '.join(f'`{kw}`' for kw in keyword_list)}\n"
                        f"通知設定: {'開啟' if notify else '關閉'}",
                        ephemeral=True
                    )
                else:
                    await interaction.response.send_message("選擇的頻道無效或不是文字/論壇頻道，請重試。", ephemeral=True)

            channel_select.callback = channel_select_callback

            prev_button = discord.ui.Button(label="上一頁", style=discord.ButtonStyle.primary, disabled=page <= 0)
            next_button = discord.ui.Button(label="下一頁", style=discord.ButtonStyle.primary, disabled=(page + 1) * ITEMS_PER_PAGE >= len(channel_options))

            async def prev_button_callback(interaction: discord.Interaction):
                nonlocal current_page
                current_page -= 1
                new_view = update_view(current_page)
                embed = discord.Embed(
                    title="選擇監控頻道",
                    description=f"請從以下選項中選擇一個文字或論壇頻道進行監控。(第 {current_page + 1} 頁)",
                    color=discord.Color.blue()
                )
                await interaction.response.edit_message(embed=embed, view=new_view)

            async def next_button_callback(interaction: discord.Interaction):
                nonlocal current_page
                current_page += 1
                new_view = update_view(current_page)
                embed = discord.Embed(
                    title="選擇監控頻道",
                    description=f"請從以下選項中選擇一個文字或論壇頻道進行監控。(第 {current_page + 1} 頁)",
                    color=discord.Color.blue()
                )
                await interaction.response.edit_message(embed=embed, view=new_view)

            prev_button.callback = prev_button_callback
            next_button.callback = next_button_callback

            view = discord.ui.View()
            view.add_item(channel_select)
            view.add_item(prev_button)
            view.add_item(next_button)
            return view

        channel_view = update_view(current_page)

        embed = discord.Embed(
            title="選擇監控頻道",
            description="請從以下選項中選擇一個文字或論壇頻道進行監控。",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, view=channel_view, ephemeral=True)

    @app_commands.command(name="stop_monitoring", description="停止您設定的所有監控")
    async def stop_monitoring_cmd(self, interaction: discord.Interaction):
        """斜線命令：停止您設定的所有監控"""
        logger.info(f'收到來自 {interaction.user} 的 /stop_monitoring 斜線命令')

        if not await self._check_guild_and_owner(interaction, owner_only=False):
            return

        guild_id = interaction.guild.id
        user_id = interaction.user.id
        removed_channels = []

        if guild_id in monitored_channels:
            for channel_id in list(monitored_channels[guild_id].keys()):
                settings_list = monitored_channels[guild_id][channel_id]
                # 移除符合使用者 ID 的設定
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
                await interaction.response.send_message(
                    f"✅ 已停止監控以下頻道：\n" + "\n".join(f"- **{name}**" for name in removed_channels),
                    ephemeral=True
                )
            else:
                await self._send_error_message(interaction, "您未設定任何監控！")
        else:
            await self._send_error_message(interaction, "您未設定任何監控！")

    @app_commands.command(name="list_monitored", description="列出目前監控的所有頻道")
    async def monitored_channels(self, interaction: discord.Interaction):
        """斜線命令：列出目前監控的所有頻道"""
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

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # 處理所有訊息以實現監控功能
    @commands.Cog.listener()
    async def on_message(self, message):
        # 避免處理機器人訊息（包括自己的訊息）
        if message.author.bot:
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
                content_lower = message.content.lower()

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
                        if re.search(pattern, content_lower):
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

async def setup(bot):
    await bot.add_cog(UserCommands(bot))
