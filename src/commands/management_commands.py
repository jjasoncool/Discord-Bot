import logging
import discord
from discord import app_commands
from discord.ext import commands
from utils import get_paginated_options, create_paginated_view, ITEMS_PER_PAGE

# 獲取 logger
logger = logging.getLogger('discord_bot')

# 監控頻道的字典已移動到 user_commands.py

class ManagementCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _check_guild_and_owner(self, interaction: discord.Interaction, owner_only: bool = True, admin_only: bool = False) -> bool:
        """檢查命令是否在伺服器中使用且使用者是否有相應權限"""
        from utils import check_guild
        return await check_guild(interaction, owner_only=owner_only, admin_only=admin_only)

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

    @app_commands.command(name="set_channel", description="設定特定功能的頻道")
    async def set_channel_cmd(self, interaction: discord.Interaction):
        """斜線命令：設定特定功能的頻道"""
        logger.info(f'收到來自 {interaction.user} 的 /set_channel 斜線命令')

        if not await self._check_guild_and_owner(interaction, owner_only=True):
            return

        channel_types = {
            "交易論壇": {"type": discord.ChannelType.forum, "key": "trade_forum_channel_id", "color": discord.Color.blue(), "desc": "交易記錄頻道"},
            "交易紀錄封存": {"type": discord.ChannelType.forum, "key": "archive_channel_id", "color": discord.Color.dark_grey(), "desc": "交易紀錄封存頻道"},
            "購物車交付": {"type": discord.ChannelType.text, "key": "cart_delivery_channel_id", "color": discord.Color.green(), "desc": "購物車交付通知頻道"},
            "官方文章更新": {"type": discord.ChannelType.text, "key": "article_monitor_channel_id", "color": discord.Color.orange(), "desc": "自動發送官方最新文章的頻道"}
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

            # 創建頻道選單，實現分頁功能（針對文字頻道）
            channel_options = [
                discord.SelectOption(
                    label=channel.name,
                    value=str(channel.id),
                    description=f"ID: {channel.id}",
                    emoji="📝" if channel_info["type"] == discord.ChannelType.text else "📌"
                )
                for channel in channels
            ]

            if not channel_options:
                await interaction.response.send_message(f"沒有可供選擇的{selected_type}頻道！", ephemeral=True)
                return

            async def on_select_callback(interaction, selected_value):
                selected_channel_id = int(selected_value)
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

            current_page, channel_view = create_paginated_view(
                channel_options,
                lambda page: f"選擇一個{selected_type}頻道... (第 {page + 1} 頁)" if len(channel_options) > ITEMS_PER_PAGE else f"選擇一個{selected_type}頻道...",
                f"選擇{selected_type}頻道",
                lambda page: f"請從以下選項中選擇一個{selected_type}頻道作為{channel_info['desc']}。(第 {page + 1} 頁)" if len(channel_options) > ITEMS_PER_PAGE else f"請從以下選項中選擇一個{selected_type}頻道作為{channel_info['desc']}",
                channel_info["color"],
                on_select_callback
            )

            embed = discord.Embed(
                title=f"選擇{selected_type}頻道",
                description=f"請從以下選項中選擇一個{selected_type}頻道作為{channel_info['desc']}。" + (f" (第 {current_page + 1} 頁)" if len(channel_options) > ITEMS_PER_PAGE else ""),
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

    @app_commands.command(name="set_role_permissions", description="設定角色的命令執行權限")
    async def set_role_permissions_cmd(self, interaction: discord.Interaction):
        """斜線命令：設定角色的命令執行權限"""
        logger.info(f'收到來自 {interaction.user} 的 /set_role_permissions 斜線命令')

        if not await self._check_guild_and_owner(interaction, owner_only=True):
            return

        role_types = {
            "Trader": {"desc": "交易員角色", "color": discord.Color.green()},
            "Moderator": {"desc": "版主角色", "color": discord.Color.blue()}
        }

        # 創建角色類型選單
        type_select = discord.ui.Select(
            placeholder="選擇要設定的角色類型...",
            options=[
                discord.SelectOption(label=role_type, value=role_type, description=info["desc"])
                for role_type, info in role_types.items()
            ]
        )

        async def type_select_callback(interaction: discord.Interaction):
            selected_type = type_select.values[0]
            if selected_type not in role_types:
                await interaction.response.send_message(f"無效的角色類型：{selected_type}。請重試。", ephemeral=True)
                return

            role_info = role_types[selected_type]
            roles = [role for role in interaction.guild.roles if not role.is_default()]
            if not roles:
                await interaction.response.send_message(f"此伺服器中沒有找到自定義身份組！", ephemeral=True)
                return

            # 創建身份組選單，實現分頁功能
            role_options = [
                discord.SelectOption(
                    label=role.name,
                    value=str(role.id),
                    description=f"ID: {role.id}",
                    emoji="🎭"
                )
                for role in roles
            ]

            if not role_options:
                await interaction.response.send_message(f"沒有可供選擇的身份組！", ephemeral=True)
                return

            async def on_select_callback(interaction, selected_value):
                selected_role_id = int(selected_value)
                role = interaction.guild.get_role(selected_role_id)
                if role and not role.is_default():
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

                    if "role_mapping" not in config:
                        config["role_mapping"] = {}
                    if selected_type not in config["role_mapping"]:
                        config["role_mapping"][selected_type] = []

                    if selected_role_id not in config["role_mapping"][selected_type]:
                        config["role_mapping"][selected_type].append(selected_role_id)
                        with open(config_file, 'w') as f:
                            json.dump(config, f, indent=2)

                        await interaction.response.edit_message(view=None)
                        await interaction.followup.send(
                            f"✅ 已將 {selected_type} 角色權限設定為 **{role.name}** (ID: {selected_role_id})！",
                            ephemeral=True
                        )
                        logger.info(f"{selected_type} 角色權限已設定為 {role.name} (ID: {selected_role_id})")
                    else:
                        await interaction.response.edit_message(view=None)
                        await interaction.followup.send(
                            f"⚠️ {selected_type} 角色權限已經包含 **{role.name}** (ID: {selected_role_id})！",
                            ephemeral=True
                        )
                else:
                    await interaction.response.send_message(f"選擇的身份組無效，請重試。", ephemeral=True)

            current_page, role_view = create_paginated_view(
                role_options,
                lambda page: f"選擇一個身份組... (第 {page + 1} 頁)" if len(role_options) > ITEMS_PER_PAGE else f"選擇一個身份組...",
                f"選擇身份組",
                lambda page: f"請從以下選項中選擇一個身份組作為 {selected_type} 角色。(第 {page + 1} 頁)" if len(role_options) > ITEMS_PER_PAGE else f"請從以下選項中選擇一個身份組作為 {selected_type} 角色。",
                role_info["color"],
                on_select_callback
            )

            embed = discord.Embed(
                title=f"選擇身份組",
                description=f"請從以下選項中選擇一個身份組作為 {selected_type} 角色。" + (f" (第 {current_page + 1} 頁)" if len(role_options) > ITEMS_PER_PAGE else ""),
                color=role_info["color"]
            )
            await interaction.response.edit_message(embed=embed, view=role_view)

        type_select.callback = type_select_callback
        type_view = discord.ui.View()
        type_view.add_item(type_select)

        embed = discord.Embed(
            title="選擇角色類型",
            description="請選擇您要設定的角色類型。",
            color=discord.Color.greyple()
        )
        await interaction.response.send_message(embed=embed, view=type_view, ephemeral=True)

    @app_commands.command(name="list_role_permissions", description="列出角色的命令執行權限設定")
    async def list_role_permissions_cmd(self, interaction: discord.Interaction):
        """斜線命令：列出角色的命令執行權限設定"""
        logger.info(f'收到來自 {interaction.user} 的 /list_role_permissions 斜線命令')

        if not await self._check_guild_and_owner(interaction, owner_only=True):
            return

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
                await interaction.response.send_message("無法讀取配置文件，請重試。", ephemeral=True)
                return

        role_mapping = config.get("role_mapping", {})
        if not role_mapping:
            await interaction.response.send_message("目前沒有設定任何角色權限。", ephemeral=True)
            return

        embed = discord.Embed(
            title="角色權限設定列表",
            description="以下是目前設定的角色權限列表：",
            color=discord.Color.purple()
        )

        for role_type, role_ids in role_mapping.items():
            if role_ids and role_ids != [0]:
                role_names = []
                for role_id in role_ids:
                    role = interaction.guild.get_role(role_id)
                    if role:
                        role_names.append(f"{role.name} (ID: {role_id})")
                    else:
                        role_names.append(f"未知身份組 (ID: {role_id})")
                embed.add_field(
                    name=f"🎭 {role_type} 角色",
                    value="\n".join(role_names),
                    inline=False
                )
            else:
                embed.add_field(
                    name=f"🎭 {role_type} 角色",
                    value="未設定",
                    inline=False
                )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="remove_role_permissions", description="移除角色的命令執行權限")
    async def remove_role_permissions_cmd(self, interaction: discord.Interaction):
        """斜線命令：移除角色的命令執行權限"""
        logger.info(f'收到來自 {interaction.user} 的 /remove_role_permissions 斜線命令')

        if not await self._check_guild_and_owner(interaction, owner_only=True):
            return

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
                await interaction.response.send_message("無法讀取配置文件，請重試。", ephemeral=True)
                return

        role_mapping = config.get("role_mapping", {})
        if not role_mapping:
            await interaction.response.send_message("目前沒有設定任何角色權限。", ephemeral=True)
            return

        # 創建角色類型選單
        type_select = discord.ui.Select(
            placeholder="選擇要移除的角色類型...",
            options=[
                discord.SelectOption(label=role_type, value=role_type, description=f"移除 {role_type} 角色權限")
                for role_type in role_mapping.keys()
            ]
        )

        async def type_select_callback(interaction: discord.Interaction):
            selected_type = type_select.values[0]
            if selected_type not in role_mapping:
                await interaction.response.send_message(f"無效的角色類型：{selected_type}。請重試。", ephemeral=True)
                return

            role_ids = role_mapping[selected_type]
            if not role_ids or role_ids == [0]:
                await interaction.response.send_message(f"目前沒有設定 {selected_type} 角色權限。", ephemeral=True)
                return

            # 創建身份組選單，實現分頁功能
            role_options = []
            for role_id in role_ids:
                role = interaction.guild.get_role(role_id)
                if role:
                    role_options.append(discord.SelectOption(
                        label=role.name,
                        value=str(role.id),
                        description=f"ID: {role.id}",
                        emoji="🎭"
                    ))
                else:
                    role_options.append(discord.SelectOption(
                        label=f"未知身份組 (ID: {role_id})",
                        value=str(role_id),
                        description=f"ID: {role_id}",
                        emoji="🎭"
                    ))

            async def on_select_callback(interaction, selected_value):
                selected_role_id = int(selected_value)
                if selected_role_id in role_mapping[selected_type]:
                    role_mapping[selected_type].remove(selected_role_id)
                    config["role_mapping"][selected_type] = role_mapping[selected_type]
                    with open(config_file, 'w') as f:
                        json.dump(config, f, indent=2)

                    role = interaction.guild.get_role(selected_role_id)
                    role_name = role.name if role else f"未知身份組 (ID: {selected_role_id})"
                    await interaction.response.edit_message(view=None)
                    await interaction.followup.send(
                        f"✅ 已移除 {selected_type} 角色權限中的 **{role_name}**！",
                        ephemeral=True
                    )
                    logger.info(f"已移除 {selected_type} 角色權限中的 {role_name}")
                else:
                    await interaction.response.send_message(f"選擇的身份組不在 {selected_type} 角色權限中，請重試。", ephemeral=True)

            current_page, role_view = create_paginated_view(
                role_options,
                lambda page: f"選擇要移除的身份組... (第 {page + 1} 頁)" if len(role_options) > ITEMS_PER_PAGE else f"選擇要移除的身份組...",
                f"選擇要移除的身份組",
                lambda page: f"請從以下選項中選擇一個要從 {selected_type} 角色權限中移除的身份組。(第 {page + 1} 頁)" if len(role_options) > ITEMS_PER_PAGE else f"請從以下選項中選擇一個要從 {selected_type} 角色權限中移除的身份組。",
                discord.Color.red(),
                on_select_callback
            )

            embed = discord.Embed(
                title=f"選擇要移除的身份組",
                description=f"請從以下選項中選擇一個要從 {selected_type} 角色權限中移除的身份組。" + (f" (第 {current_page + 1} 頁)" if len(role_options) > ITEMS_PER_PAGE else ""),
                color=discord.Color.red()
            )
            await interaction.response.edit_message(embed=embed, view=role_view)

        type_select.callback = type_select_callback
        type_view = discord.ui.View()
        type_view.add_item(type_select)

        embed = discord.Embed(
            title="選擇角色類型",
            description="請選擇您要移除的角色類型。",
            color=discord.Color.greyple()
        )
        await interaction.response.send_message(embed=embed, view=type_view, ephemeral=True)

    # on_message 監聽器已移動到 user_commands.py

async def setup(bot):
    await bot.add_cog(ManagementCommands(bot))
