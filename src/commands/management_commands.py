import logging
import discord
from discord import app_commands
from discord.ext import commands

# 獲取 logger
logger = logging.getLogger('discord_bot')

# 監控頻道的字典已移動到 user_commands.py

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

    # monitor_channel_cmd 已移動到 user_commands.py

    # stop_monitoring_cmd 已移動到 user_commands.py

    # list_monitored_cmd 已移動到 user_commands.py

    @app_commands.command(name="set_channel", description="設定特定功能的頻道")
    async def set_channel_cmd(self, interaction: discord.Interaction):
        """斜線命令：設定特定功能的頻道"""
        logger.info(f'收到來自 {interaction.user} 的 /set_channel 斜線命令')

        if not await self._check_guild_and_owner(interaction, owner_only=True):
            return

        channel_types = {
            "交易論壇": {"type": discord.ChannelType.forum, "key": "trade_forum_channel_id", "color": discord.Color.blue(), "desc": "交易記錄頻道"},
            "購物車交付": {"type": discord.ChannelType.text, "key": "cart_delivery_channel_id", "color": discord.Color.green(), "desc": "購物車交付通知頻道"}
        }

        # 創建頻道類型選單
        type_select = discord.ui.Select(
            placeholder="選擇要設定的頻道類型...",
            options=[
                discord.SelectOption(label=channel_type, value=channel_type, description=info["desc"])
                for channel_type, info in channel_types.items()
            ]
        )

        async def type_select_callback(interaction: discord.Interaction):
            selected_type = type_select.values[0]
            if selected_type not in channel_types:
                await interaction.response.send_message(f"無效的頻道類型：{selected_type}。請重試。", ephemeral=True)
                return

            channel_info = channel_types[selected_type]
            channels = [channel for channel in interaction.guild.channels if channel.type == channel_info["type"]]
            if not channels:
                await interaction.response.send_message(f"此伺服器中沒有找到{selected_type}頻道！", ephemeral=True)
                return

            # 創建頻道選單
            channel_select = discord.ui.Select(
                placeholder=f"選擇一個{selected_type}頻道...",
                options=[
                    discord.SelectOption(label=channel.name, value=str(channel.id), description=f"ID: {channel.id}")
                    for channel in channels
                ]
            )

            async def channel_select_callback(interaction: discord.Interaction):
                selected_channel_id = int(channel_select.values[0])
                channel = interaction.guild.get_channel(selected_channel_id)
                if channel and channel.type == channel_info["type"]:
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

                    config[channel_info["key"]] = selected_channel_id
                    with open(config_file, 'w') as f:
                        json.dump(config, f, indent=2)

                    await interaction.response.edit_message(view=None)
                    await interaction.followup.send(
                        f"✅ 已將{selected_type}頻道設定為 **{channel.name}** (ID: {selected_channel_id})！",
                        ephemeral=True
                    )
                    logger.info(f"{selected_type}頻道已設定為 {channel.name} (ID: {selected_channel_id})")
                else:
                    await interaction.response.send_message(f"選擇的頻道無效或不是{selected_type}頻道，請重試。", ephemeral=True)

            channel_select.callback = channel_select_callback
            channel_view = discord.ui.View()
            channel_view.add_item(channel_select)

            embed = discord.Embed(
                title=f"選擇{selected_type}頻道",
                description=f"請從以下選項中選擇一個{selected_type}頻道作為{channel_info['desc']}。",
                color=channel_info["color"]
            )
            await interaction.response.edit_message(embed=embed, view=channel_view)

        type_select.callback = type_select_callback
        type_view = discord.ui.View()
        type_view.add_item(type_select)

        embed = discord.Embed(
            title="選擇頻道類型",
            description="請選擇您要設定的頻道類型。",
            color=discord.Color.greyple()
        )
        await interaction.response.send_message(embed=embed, view=type_view, ephemeral=True)

    # on_message 監聽器已移動到 user_commands.py

async def setup(bot):
    await bot.add_cog(ManagementCommands(bot))
