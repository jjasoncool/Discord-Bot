import logging
import discord
from discord import app_commands
from discord.ext import commands

# 獲取 logger
logger = logging.getLogger('discord_bot')

# 監控頻道的字典，格式: {guild_id: {channel_id: {關鍵字列表, 使用者ID}}}
monitored_channels = {}

class ManagementCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _check_guild_and_owner(self, interaction: discord.Interaction, owner_only: bool = True) -> bool:
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

    @app_commands.command(name="list_channels", description="列出所有可見的頻道")
    async def list_channels_cmd(self, interaction: discord.Interaction):
        """斜線命令：列出伺服器中所有可見的頻道"""
        logger.info(f'收到來自 {interaction.user} 的 /list_channels 斜線命令')

        if not await self._check_guild_and_owner(interaction, owner_only=True):
            return

        # 建立頻道列表
        text_channels = []
        voice_channels = []
        categories = []
        forum_channels = []
        other_channels = []

        for channel in interaction.guild.channels:
            if isinstance(channel, discord.TextChannel):
                text_channels.append(f"📝 {channel.name} (ID: {channel.id})")
            elif isinstance(channel, discord.VoiceChannel):
                voice_channels.append(f"🔊 {channel.name} (ID: {channel.id})")
            elif isinstance(channel, discord.CategoryChannel):
                categories.append(f"📁 {channel.name} (ID: {channel.id})")
            elif isinstance(channel, discord.ForumChannel):
                forum_channels.append(f"📌 {channel.name} (ID: {channel.id})")
            else:
                other_channels.append(f"⚪ {channel.name} (ID: {channel.id})")

        # 創建嵌入訊息
        embed = discord.Embed(
            title=f"{interaction.guild.name} 的頻道列表",
            description="以下是此伺服器中所有可見的頻道列表，包含各頻道的 ID：",
            color=discord.Color.blue()
        )

        if categories:
            embed.add_field(name="📁 類別", value="\n".join(categories), inline=False)

        if text_channels:
            embed.add_field(name="📝 文字頻道", value="\n".join(text_channels), inline=False)

        if voice_channels:
            embed.add_field(name="🔊 語音頻道", value="\n".join(voice_channels), inline=False)

        if forum_channels:
            embed.add_field(name="📌 論壇頻道", value="\n".join(forum_channels), inline=False)

        if other_channels:
            embed.add_field(name="⚪ 其他頻道", value="\n".join(other_channels), inline=False)

        embed.set_footer(text="提示：您可以使用這些頻道 ID 來設定頻道監控")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="list_roles", description="列出所有身份組及其ID")
    async def list_roles_cmd(self, interaction: discord.Interaction):
        """斜線命令：列出伺服器中所有身份組及其ID"""
        logger.info(f'收到來自 {interaction.user} 的 /list_roles 斜線命令')

        if not await self._check_guild_and_owner(interaction, owner_only=True):
            return

        # 建立身份組列表
        roles = [f"🎭 {role.name} (ID: {role.id})" for role in interaction.guild.roles if not role.is_default()]

        # 創建嵌入訊息
        embed = discord.Embed(
            title=f"{interaction.guild.name} 的身份組列表",
            description="以下是此伺服器中所有身份組列表，包含各身份組的 ID：",
            color=discord.Color.purple()
        )

        if roles:
            embed.add_field(name="🎭 身份組", value="\n".join(roles), inline=False)
        else:
            embed.add_field(name="🎭 身份組", value="此伺服器中沒有自定義身份組。", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="monitor_channel", description="監控指定頻道的訊息")
    @app_commands.describe(
        channel_id="要監控的頻道 ID",
        keywords="要監控的關鍵字（用逗號分隔）",
        notify="是否在發現關鍵字時通知您"
    )
    async def monitor_channel_cmd(self, interaction: discord.Interaction, channel_id: str, keywords: str, notify: bool = True):
        """斜線命令：設定監控特定頻道的訊息"""
        logger.info(f'收到來自 {interaction.user} 的 /monitor_channel 斜線命令，參數: channel_id="{channel_id}", keywords="{keywords}", notify={notify}')

        if not await self._check_guild_and_owner(interaction, owner_only=True):
            return

        # 確認頻道 ID 格式正確
        try:
            channel_id = int(channel_id)
        except ValueError:
            await self._send_error_message(interaction, "頻道 ID 必須是一個數字！使用 `/list_channels` 獲取頻道 ID。")
            return

        # 嘗試獲取頻道
        channel = interaction.guild.get_channel(channel_id)
        if not channel:
            await self._send_error_message(interaction, f"找不到 ID 為 {channel_id} 的頻道！使用 `/list_channels` 獲取正確的頻道 ID。")
            return

        # 解析關鍵字列表
        keyword_list = [kw.strip() for kw in keywords.split(',') if kw.strip()]
        if not keyword_list:
            await self._send_error_message(interaction, "請提供至少一個要監控的關鍵字！")
            return

        # 設定監控
        guild_id = interaction.guild.id
        if guild_id not in monitored_channels:
            monitored_channels[guild_id] = {}

        monitored_channels[guild_id][channel_id] = {
            'keywords': keyword_list,
            'user_id': interaction.user.id,
            'notify': notify
        }

        await interaction.response.send_message(
            f"✅ 已開始監控頻道 **{channel.name}**！\n"
            f"監控關鍵字: {', '.join(f'`{kw}`' for kw in keyword_list)}\n"
            f"通知設定: {'開啟' if notify else '關閉'}",
            ephemeral=True
        )

    @app_commands.command(name="stop_monitoring", description="停止監控指定頻道")
    @app_commands.describe(
        channel_id="要停止監控的頻道 ID"
    )
    async def stop_monitoring_cmd(self, interaction: discord.Interaction, channel_id: str):
        """斜線命令：停止監控特定頻道的訊息"""
        logger.info(f'收到來自 {interaction.user} 的 /stop_monitoring 斜線命令，參數: channel_id="{channel_id}"')

        if not await self._check_guild_and_owner(interaction, owner_only=True):
            return

        # 確認頻道 ID 格式正確
        try:
            channel_id = int(channel_id)
        except ValueError:
            await self._send_error_message(interaction, "頻道 ID 必須是一個數字！")
            return

        # 嘗試獲取頻道
        channel = interaction.guild.get_channel(channel_id)
        channel_name = channel.name if channel else f"ID: {channel_id}"

        # 檢查是否正在監控該頻道
        guild_id = interaction.guild.id
        if (guild_id not in monitored_channels or
            channel_id not in monitored_channels[guild_id]):
            await self._send_error_message(interaction, f"未監控頻道 {channel_name}！")
            return

        # 停止監控
        del monitored_channels[guild_id][channel_id]
        if not monitored_channels[guild_id]:
            del monitored_channels[guild_id]

        await interaction.response.send_message(f"✅ 已停止監控頻道 **{channel_name}**！", ephemeral=True)

    @app_commands.command(name="list_monitored", description="列出目前監控的所有頻道")
    async def list_monitored_cmd(self, interaction: discord.Interaction):
        """斜線命令：列出目前監控的所有頻道"""
        logger.info(f'收到來自 {interaction.user} 的 /list_monitored 斜線命令')

        if not await self._check_guild_and_owner(interaction, owner_only=True):
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

        for ch_id, settings in monitored_channels[guild_id].items():
            channel = interaction.guild.get_channel(ch_id)
            channel_name = channel.name if channel else f"未知頻道 (ID: {ch_id})"

            keywords = ", ".join(f"`{kw}`" for kw in settings['keywords'])
            user = self.bot.get_user(settings['user_id'])
            user_name = user.mention if user else f"使用者 ID: {settings['user_id']}"

            embed.add_field(
                name=f"📝 {channel_name}",
                value=f"監控關鍵字: {keywords}\n"
                      f"設定者: {user_name}\n"
                      f"通知設定: {'開啟' if settings.get('notify', True) else '關閉'}\n"
                      f"頻道 ID: {ch_id}",
                inline=False
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="set_trade_forum_channel", description="設定交易論壇頻道")
    async def set_trade_forum_channel_cmd(self, interaction: discord.Interaction):
        """斜線命令：設定用於交易記錄的論壇頻道"""
        logger.info(f'收到來自 {interaction.user} 的 /set_trade_forum_channel 斜線命令')

        if not await self._check_guild_and_owner(interaction, owner_only=True):
            return

        # 獲取所有論壇頻道
        forum_channels = [channel for channel in interaction.guild.channels if channel.type == discord.ChannelType.forum]
        if not forum_channels:
            await self._send_error_message(interaction, "此伺服器中沒有找到論壇頻道！")
            return

        # 創建選單
        select = discord.ui.Select(
            placeholder="選擇一個論壇頻道...",
            options=[
                discord.SelectOption(label=channel.name, value=str(channel.id), description=f"ID: {channel.id}")
                for channel in forum_channels
            ]
        )

        async def select_callback(interaction: discord.Interaction):
            selected_channel_id = int(select.values[0])
            channel = interaction.guild.get_channel(selected_channel_id)
            if channel and channel.type == discord.ChannelType.forum:
                # 儲存設定到 JSON 檔案
                import json
                import os
                config_file = "config.json"
                config = {}
                if os.path.exists(config_file):
                    try:
                        with open(config_file, 'r') as f:
                            config = json.load(f)
                    except json.JSONDecodeError:
                        logger.error(f"無法讀取 {config_file}，將創建新檔案")

                config['trade_forum_channel_id'] = selected_channel_id
                with open(config_file, 'w') as f:
                    json.dump(config, f, indent=2)

                await interaction.response.edit_message(view=None)
                await interaction.followup.send(
                    f"✅ 已將交易論壇頻道設定為 **{channel.name}** (ID: {selected_channel_id})！",
                    ephemeral=True
                )
                logger.info(f"交易論壇頻道已設定為 {channel.name} (ID: {selected_channel_id})")
            else:
                await interaction.response.send_message("選擇的頻道無效或不是論壇頻道，請重試。", ephemeral=True)

        select.callback = select_callback
        view = discord.ui.View()
        view.add_item(select)

        embed = discord.Embed(
            title="選擇交易論壇頻道",
            description="請從以下選項中選擇一個論壇頻道作為交易記錄頻道。",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # 處理所有訊息以實現監控功能
    @commands.Cog.listener()
    async def on_message(self, message):
        # 避免處理機器人訊息
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
                settings = monitored_channels[guild_id][monitored_channel_id]
                content_lower = message.content.lower()

                # 檢查訊息是否包含監控的關鍵字
                found_keywords = [kw for kw in settings['keywords']
                                 if kw.lower() in content_lower]

                if found_keywords and settings.get('notify', True):
                    # 獲取監控者
                    user = self.bot.get_user(settings['user_id'])
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
    await bot.add_cog(ManagementCommands(bot))
