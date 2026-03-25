"""
管理命令的模組 (可搭配服務介面與 Cogs 使用)
"""
import logging
import json
import os
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional

# 注意：需確保 utils 資料夾下的 utils.py 包含 create_paginated_view, ITEMS_PER_PAGE, safe_send_interaction_message, ChannelConfig 等定義
from utils.utils import create_paginated_view, ITEMS_PER_PAGE, safe_send_interaction_message, ChannelConfig
# 注意：需確保 services 資料夾下的 intro_profile_service.py 包含 IntroProfilePayload, ImpressionPayload, IntroProfileServiceProtocol, IntroProfileService 等定義
from services.intro_profile_service import (
    IntroProfilePayload,
    ImpressionPayload,
    IntroProfileServiceProtocol,
    IntroProfileService,
)
from services.impression_moderation_service import ImpressionModerationService
from llm.intro_rag_port import PgVectorIntroRAGPort
from telegram_scraper.tg_config import normalize_channel_identifier

# 獲取 logger
logger = logging.getLogger('discord_bot')
INTRO_PANEL_RUNTIME_FILE = "settings/intro_panel_runtime.json"


def _load_intro_panel_runtime_config() -> dict:
    """只讀取 message_id（不進版控）"""
    if not os.path.exists(INTRO_PANEL_RUNTIME_FILE):
        return {}
    try:
        with open(INTRO_PANEL_RUNTIME_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # 強制只保留 message_id
            return {"intro_panel_message_id": data.get("intro_panel_message_id")}
    except Exception as e:
        logger.error(f"讀取 {INTRO_PANEL_RUNTIME_FILE} 失敗: {e}", exc_info=True)
        return {}


def _save_intro_panel_runtime_config(message_id: int) -> None:
    """只寫入 message_id（不存其他東西）"""
    try:
        os.makedirs(os.path.dirname(INTRO_PANEL_RUNTIME_FILE), exist_ok=True)
        data = {"intro_panel_message_id": message_id}
        with open(INTRO_PANEL_RUNTIME_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"已更新 runtime.json → message_id={message_id}")
    except Exception as e:
        logger.error(f"寫入 {INTRO_PANEL_RUNTIME_FILE} 失敗: {e}", exc_info=True)
        raise


class ServerInfoView(discord.ui.View):
    """/server_info 主入口 persistent view"""

    def __init__(self, cog: "ManagementCommands"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="列出頻道", style=discord.ButtonStyle.primary, custom_id="list_channels")
    async def list_channels_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.cog._check_guild_and_owner(interaction, owner_only=True):
            return
        await self.cog._list_channels(interaction)

    @discord.ui.button(label="列出身份組", style=discord.ButtonStyle.secondary, custom_id="list_roles")
    async def list_roles_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.cog._check_guild_and_owner(interaction, owner_only=True):
            return
        await self.cog._list_roles(interaction)


class RoleManagerView(discord.ui.View):
    """/role_manager 主入口 persistent view"""

    def __init__(self, cog: "ManagementCommands"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="設定角色權限", style=discord.ButtonStyle.primary, custom_id="set_role_permissions")
    async def set_role_permissions_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.set_role_permissions_cmd(interaction)

    @discord.ui.button(label="列出角色權限", style=discord.ButtonStyle.secondary, custom_id="list_role_permissions")
    async def list_role_permissions_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.list_role_permissions_cmd(interaction)

    @discord.ui.button(label="移除角色權限", style=discord.ButtonStyle.danger, custom_id="remove_role_permissions")
    async def remove_role_permissions_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.remove_role_permissions_cmd(interaction)


class ServerManagerView(discord.ui.View):
    """/server_manager 主入口 persistent view"""

    def __init__(self, cog: "ManagementCommands"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="角色管理", style=discord.ButtonStyle.primary, custom_id="role_manager")
    async def role_manager_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.role_manager_cmd(interaction)

    @discord.ui.button(label="頻道設定", style=discord.ButtonStyle.secondary, custom_id="set_channel")
    async def set_channel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.set_channel_cmd(interaction)

class IntroProfileModal(discord.ui.Modal):
    """自我介紹 Modal - 已修正初始化與 defer"""
    def __init__(self, intro_service: IntroProfileServiceProtocol, management_cog: "ManagementCommands"):
        super().__init__(title="自我介紹", timeout=600)  # 必須明確傳 title + timeout

        self.intro_service = intro_service
        self.management_cog = management_cog

        # 統一用 list + for 迴圈減少重複 add_item
        self.alias = discord.ui.TextInput(
            label="別人常常叫我什麼（暱稱/綽號）",
            placeholder="例如：阿狗、紅狐...",
            max_length=50,
            required=True,
        )
        self.wuwa_uid = discord.ui.TextInput(
            label="鳴潮 UID（選填）",
            placeholder="例如：123456789",
            max_length=50,
            required=False,
        )
        self.bio = discord.ui.TextInput(
            label="自我介紹",
            placeholder="簡單介紹你自己、喜歡玩的遊戲、個性...",
            style=discord.TextStyle.paragraph,
            max_length=600,
            required=True,
        )
        self.message_to_all = discord.ui.TextInput(
            label="想跟群裡的大家說什麼（選填）",
            placeholder="例如：很高興認識大家！之後請多指教～",
            style=discord.TextStyle.paragraph,
            max_length=300,
            required=False,
        )

        # 依序加入 Modal (注意：Modal 最多支援 5 個項目)
        self.add_item(self.alias)
        self.add_item(self.wuwa_uid)
        self.add_item(self.bio)
        self.add_item(self.message_to_all)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)  # 防止超時（最重要！）

        # 以下你原本的程式碼完全保留不變（從 embed 開始）
        embed = discord.Embed(
            title="🙋 新的自我介紹",
            color=discord.Color.blurple(),
            timestamp=interaction.created_at,
        )
        embed.add_field(name="暱稱 / 綽號", value=self.alias.value, inline=False)

        if self.wuwa_uid.value:
            embed.add_field(name="鳴潮 UID", value=self.wuwa_uid.value, inline=False)

        embed.add_field(name="自我介紹", value=self.bio.value, inline=False)

        if self.message_to_all.value:
            embed.add_field(name="想對大家說", value=self.message_to_all.value, inline=False)

        embed.set_footer(text=f"提交者：{interaction.user.display_name}")

        # 將 Embed 傳送到觸發指令的頻道
        await interaction.channel.send(content=f"{interaction.user.mention}", embed=embed)

        # 呼叫後端服務寫入資料 (將資料提供給 RAG 使用)
        try:
            # ⚠️ 這裡的 Payload 必須對應你實際的服務實作
            await self.intro_service.on_intro_submitted(
                IntroProfilePayload(
                    guild_id=interaction.guild.id if interaction.guild else 0,
                    channel_id=interaction.channel.id if interaction.channel else 0,
                    author_id=interaction.user.id,
                    alias=self.alias.value,                  # 新增的暱稱欄位
                    wuwa_uid=self.wuwa_uid.value,            # 新增的鳴潮 UID 欄位
                    bio=self.bio.value,                      # 原本的自我介紹
                    message_to_all=self.message_to_all.value # 新增的想說的話
                )
            )
        except Exception as e:
            logger.error(f"自我介紹 RAG 介面呼叫失敗: {e}", exc_info=True)

        # 直接發送成功訊息（不使用 interaction 回覆）
        await interaction.channel.send(content=f"{interaction.user.mention} ✅ 已送出你的自我介紹！")

        try:
            await self.management_cog._auto_bump_intro_panel_after_submission(interaction)
        except Exception as e:
            logger.error(f"自我介紹送出後自動 bump 面板失敗: {e}", exc_info=True)

class IntroImpressionModal(discord.ui.Modal):
    """對他人印象 Modal - 2026 年 2.6.4 官方正確寫法（使用 Label 包裝）"""
    def __init__(
        self,
        intro_service: IntroProfileServiceProtocol,
        management_cog: "ManagementCommands",
    ):
        super().__init__(title="填寫對他人印象", timeout=600)

        self.intro_service = intro_service
        self.management_cog = management_cog
        self.moderation_service = ImpressionModerationService()

        logger.info("intro_impression_modal_init: timeout=600, using Label-wrapped UserSelect (2.6.4 supported)")

        # UserSelect 本體（不要給 custom_id，讓 library 自動產生）
        self.target_select: discord.ui.UserSelect = discord.ui.UserSelect(
            placeholder="請選擇你要填寫印象的對象...",
            min_values=1,
            max_values=1,
            required=True,   # 2.6+ 在 Modal 內生效
            row=0,
        )

        # 關鍵：一定要用 Label 包裝（官方唯一合法寫法）
        select_label = discord.ui.Label(
            text="👤 選擇目標使用者",   # 顯示在 Select 上方的文字
            component=self.target_select,
        )

        # 其他欄位保持 TextInput（可省略 row，library 會自動排）
        self.alias_text = discord.ui.TextInput(
            label="你平常怎麼稱呼他？（綽號/梗名）",
            placeholder="例如：阿狗、一野...（若無可留白）",
            max_length=50,
            required=False,
        )
        self.habit_text = discord.ui.TextInput(
            label="他常常在群裡面做什麼？(請簡答)",
            placeholder="例如：有錢人、常常搬石、死臭歐...",
            style=discord.TextStyle.short,
            max_length=100,
            required=False,
        )
        self.impression = discord.ui.TextInput(
            label="你對他的整體印象",
            placeholder="請寫下你對他的印象（帥潮、男娘、手法帝...）",
            style=discord.TextStyle.paragraph,
            max_length=600,
            required=True,
        )

        # 統一加入（減少重複 add_item）
        for item in (select_label, self.alias_text, self.habit_text, self.impression):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        if not self.target_select.values:
            await safe_send_interaction_message(interaction, "請務必選擇一個對象！", ephemeral=True)
            return

        # 以下你原本的 on_submit 程式碼完全保留（從 selected_user 開始）
        selected_user = self.target_select.values[0]
        alias = self.alias_text.value.strip()
        habit = self.habit_text.value.strip()
        impression_text = self.impression.value.strip()

        moderation = await self.moderation_service.moderate(
            target_display=f"{selected_user.display_name}({selected_user.id})",
            text=impression_text,
        )
        if not moderation.approved:
            logger.info(
                (
                    "intro_impression_moderation_blocked "
                    "author_id=%s target_user_id=%s decision=%s reason=%s "
                    "score_prompt_injection=%.4f score_meme_spam=%.4f "
                    "score_fake_story=%.4f score_real_interaction=%.4f "
                    "score_meaningfulness=%.4f"
                ),
                interaction.user.id if interaction.user else None,
                selected_user.id,
                moderation.decision,
                moderation.reason,
                moderation.score_prompt_injection,
                moderation.score_meme_spam,
                moderation.score_fake_story,
                moderation.score_real_interaction,
                moderation.score_meaningfulness,
            )
            await safe_send_interaction_message(
                interaction,
                (
                    "⚠️ 這則他人印象暫時無法提交。\n"
                    "請改寫為與對象相關、可理解且具體的社群印象後再送出。"
                ),
                ephemeral=True,
                prefer_followup=True,
            )
            return

        display_target = f"{selected_user.mention}"
        if alias:
            display_target += f" (大家都叫：**{alias}**)"

        embed = discord.Embed(
            title="💬 收到對他人的新印象",
            color=discord.Color.teal(),
            timestamp=interaction.created_at,
        )
        embed.add_field(name="對象", value=display_target, inline=False)
        if habit:
            embed.add_field(name="常做的事", value=habit, inline=False)
        embed.add_field(name="整體印象", value=impression_text, inline=False)
        embed.set_footer(text=f"填寫者：{interaction.user.display_name}")

        await interaction.channel.send(content=f"{interaction.user.mention}", embed=embed)

        try:
            await self.intro_service.on_impression_submitted(
                ImpressionPayload(
                    guild_id=interaction.guild.id if interaction.guild else 0,
                    channel_id=interaction.channel.id if interaction.channel else 0,
                    author_id=interaction.user.id,
                    target_user_id=selected_user.id,
                    target_alias=alias,
                    target_habit=habit,
                    impression=impression_text,
                    moderation_metadata=moderation.to_metadata(),
                )
            )
        except Exception as e:
            logger.error(f"他人印象 RAG 介面呼叫失敗: {e}", exc_info=True)

        # 直接發送成功訊息（不使用 interaction 回覆）
        await interaction.channel.send(
            content=f"✅ 已成功送出你對 {selected_user.mention} 的印象，謝謝分享！"
        )

        try:
            await self.management_cog._auto_bump_intro_panel_after_submission(interaction)
        except Exception as e:
            logger.error(f"他人印象送出後自動 bump 面板失敗: {e}", exc_info=True)
class IntroPanelView(discord.ui.View):
    """自我介紹面板 persistent view"""

    def __init__(self, intro_service: IntroProfileServiceProtocol, management_cog: "ManagementCommands"):
        super().__init__(timeout=None)
        self.intro_service = intro_service
        self.management_cog = management_cog

    @discord.ui.button(label="✍️ 填寫自我介紹", style=discord.ButtonStyle.primary, custom_id="intro_open_modal")
    async def intro_open_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(IntroProfileModal(self.intro_service, self.management_cog))

    @discord.ui.button(label="🗣️ 填寫對他人印象", style=discord.ButtonStyle.secondary, custom_id="intro_open_impression_modal")
    async def intro_open_impression_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        logger.info(
            "intro_impression_button_clicked user_id=%s guild_id=%s channel_id=%s custom_id=%s",
            interaction.user.id if interaction.user else None,
            interaction.guild.id if interaction.guild else None,
            interaction.channel.id if interaction.channel else None,
            button.custom_id,
        )
        await interaction.response.send_modal(IntroImpressionModal(self.intro_service, self.management_cog))


class ManagementCommands(commands.Cog):
    def __init__(self, bot, intro_profile_service: Optional[IntroProfileServiceProtocol] = None):
        self.bot = bot
        self.intro_profile_service: IntroProfileServiceProtocol = (
            intro_profile_service or IntroProfileService(rag_port=PgVectorIntroRAGPort())
        )

    async def cog_load(self):
        # 註冊 persistent views，避免機器人重啟後主入口按鈕失效
        self.bot.add_view(ServerInfoView(self))
        self.bot.add_view(RoleManagerView(self))
        self.bot.add_view(ServerManagerView(self))
        self.bot.add_view(IntroPanelView(self.intro_profile_service, self))
        logger.info("已註冊 ManagementCommands persistent views")

    async def _auto_bump_intro_panel_after_submission(self, interaction: discord.Interaction):
        """提交表單後，自動刪除舊面板並重發置底。"""
        if not interaction.guild:
            return

        config_file = "config.json"
        config = ChannelConfig.load_config(config_file, caller="ManagementCommands")
        intro_channel_id = config.get("intro_channel_id", ChannelConfig.DEFAULT_ID)
        if intro_channel_id == ChannelConfig.DEFAULT_ID:
            logger.info("自動 bump 跳過：intro_channel_id 未設定。")
            return

        intro_channel = interaction.guild.get_channel(int(intro_channel_id))
        if not isinstance(intro_channel, discord.TextChannel):
            logger.warning("自動 bump 跳過：intro_channel_id 非有效文字頻道。id=%s", intro_channel_id)
            return

        message, deleted_old = await self._publish_intro_panel(
            guild=interaction.guild,
            intro_channel=intro_channel,
            config=config,
            config_file=config_file,
        )
        logger.info(
            "自動 bump 完成：new_message_id=%s deleted_old=%s channel_id=%s",
            message.id,
            deleted_old,
            intro_channel.id,
        )

    async def _check_guild_and_owner(self, interaction: discord.Interaction, owner_only: bool = True, admin_only: bool = False) -> bool:
        """檢查命令是否在伺服器中使用且使用者是否有相應權限"""
        from utils.utils import check_guild
        return await check_guild(interaction, owner_only=owner_only, admin_only=admin_only)

    async def _send_error_message(self, interaction: discord.Interaction, message: str):
        """發送錯誤訊息"""
        await safe_send_interaction_message(interaction, message, ephemeral=True)

    async def _list_channels(self, interaction: discord.Interaction):
        """列出伺服器中所有可見的頻道"""
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

        await safe_send_interaction_message(interaction, embed=embed, ephemeral=True)

    async def _list_roles(self, interaction: discord.Interaction):
        """列出伺服器中所有身份組及其ID"""
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

        await safe_send_interaction_message(interaction, embed=embed, ephemeral=True)

    @app_commands.command(name="server_info", description="檢視伺服器相關資訊")
    async def server_info_cmd(self, interaction: discord.Interaction):
        """斜線命令：檢視伺服器相關資訊"""
        logger.info(f'收到來自 {interaction.user} 的 /server_info 斜線命令')

        if not await self._check_guild_and_owner(interaction, owner_only=True):
            return

        action_view = ServerInfoView(self)

        embed = discord.Embed(
            title="檢視伺服器資訊",
            description="請選擇您要檢視的伺服器資訊。",
            color=discord.Color.greyple()
        )
        await safe_send_interaction_message(interaction, embed=embed, view=action_view, ephemeral=True)

    async def set_channel_cmd(self, interaction: discord.Interaction):
        """設定特定功能的頻道"""
        logger.info(f'收到來自 {interaction.user} 的 set_channel 請求')

        if not await self._check_guild_and_owner(interaction, owner_only=True):
            return

        telegram_route_option_label = "Telegram 路由設定"

        channel_types = {
            "交易頻道": {"type": discord.ChannelType.forum, "key": "trade_forum_channel_id", "color": discord.Color.blue(), "desc": "交易記錄頻道"},
            "交易紀錄封存": {"type": discord.ChannelType.forum, "key": "archive_channel_id", "color": discord.Color.dark_grey(), "desc": "交易紀錄封存頻道"},
            "論壇文章頻道": {"type": discord.ChannelType.forum, "key": "forum_article_channel_id", "color": discord.Color.gold(), "desc": "自動發布論壇文章的論壇頻道"},
            "購物車交付": {"type": discord.ChannelType.text, "key": "cart_delivery_channel_id", "color": discord.Color.green(), "desc": "購物車交付通知頻道"},
            "官方文章更新": {"type": discord.ChannelType.text, "key": "article_monitor_channel_id", "color": discord.Color.orange(), "desc": "自動發送官方最新文章的頻道"},
            telegram_route_option_label: {"type": discord.ChannelType.text, "key": "telegram_channel_routes", "color": discord.Color.teal(), "desc": "先輸入 Telegram 來源（名稱/chat_id），再綁定 Discord 文字頻道"},
            "自我介紹頻道": {"type": discord.ChannelType.text, "key": "intro_channel_id", "color": discord.Color.purple(), "desc": "使用者填寫自我介紹的頻道"}
        }

        # 創建頻道類型選單
        type_select = discord.ui.Select(
            placeholder="選擇要設定的頻道類型...",
            custom_id="management_set_channel_type_select",
            options=[
                discord.SelectOption(label=channel_type, value=channel_type, description=info["desc"])
                for channel_type, info in channel_types.items()
            ]
        )

        async def type_select_callback(interaction: discord.Interaction):
            selected_type = type_select.values[0]
            if selected_type not in channel_types:
                await safe_send_interaction_message(interaction, f"無效的頻道類型：{selected_type}。請重試。", ephemeral=True)
                return

            if selected_type == telegram_route_option_label:
                class TelegramRouteInputModal(discord.ui.Modal):
                    def __init__(self):
                        super().__init__(title="設定 Telegram 路由", timeout=300)
                        self.telegram_source = discord.ui.TextInput(
                            label="Telegram 來源（名稱或 chat_id）",
                            placeholder="例如：Seele_WW_leak、@Seele_WW_leak、-1001234567890",
                            required=True,
                            max_length=128,
                        )
                        self.target_channel = discord.ui.ChannelSelect(
                            placeholder="選擇要轉發的 Discord 文字頻道...",
                            min_values=1,
                            max_values=1,
                            channel_types=[discord.ChannelType.text],
                            required=True,
                        )
                        self.add_item(self.telegram_source)
                        self.add_item(discord.ui.Label(text="Discord 目標頻道", component=self.target_channel))

                    async def on_submit(self, modal_interaction: discord.Interaction):
                        source_raw = self.telegram_source.value.strip()
                        source_key = normalize_channel_identifier(source_raw).lower()

                        if not source_key:
                            await safe_send_interaction_message(modal_interaction, "來源值不可為空，請重新設定。", ephemeral=True)
                            return

                        if not self.target_channel.values:
                            await safe_send_interaction_message(modal_interaction, "請選擇 Discord 目標頻道。", ephemeral=True)
                            return

                        selected_channel = self.target_channel.values[0]
                        selected_channel_id = int(getattr(selected_channel, "id", 0) or 0)
                        if selected_channel_id <= 0:
                            await safe_send_interaction_message(modal_interaction, "選擇的頻道無效，請重試。", ephemeral=True)
                            return

                        config_file = "config.json"
                        config = ChannelConfig.load_config(config_file, caller="ManagementCommands")
                        routes = config.get("telegram_channel_routes")
                        if not isinstance(routes, dict):
                            routes = {}

                        raw_existing = routes.get(source_key, [])
                        if isinstance(raw_existing, list):
                            existing_ids = raw_existing
                        elif raw_existing in (None, ""):
                            existing_ids = []
                        else:
                            existing_ids = [raw_existing]

                        normalized_ids: list[int] = []
                        for rid in existing_ids:
                            try:
                                rid_int = int(rid)
                            except (TypeError, ValueError):
                                continue
                            if rid_int > 0 and rid_int not in normalized_ids:
                                normalized_ids.append(rid_int)

                        if selected_channel_id not in normalized_ids:
                            normalized_ids.append(selected_channel_id)

                        routes[source_key] = normalized_ids
                        config["telegram_channel_routes"] = routes
                        ChannelConfig.save_config(config, config_file, caller="ManagementCommands")

                        await safe_send_interaction_message(
                            modal_interaction,
                            (
                                f"✅ 已新增 Telegram 路由：`{source_key}` -> <#{selected_channel_id}>\n"
                                f"目前目標頻道數：{len(normalized_ids)}"
                            ),
                            ephemeral=True,
                        )

                await interaction.response.send_modal(TelegramRouteInputModal())
                return

            channel_info = channel_types[selected_type]
            channels = [channel for channel in interaction.guild.channels if channel.type == channel_info["type"]]
            if not channels:
                await safe_send_interaction_message(interaction, f"此伺服器中沒有找到{selected_type}頻道！", ephemeral=True)
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
                await safe_send_interaction_message(interaction, f"沒有可供選擇的{selected_type}頻道！", ephemeral=True)
                return

            async def on_select_callback(interaction, selected_value):
                selected_channel_id = int(selected_value)
                channel = interaction.guild.get_channel(selected_channel_id)
                if channel and channel.type == channel_info["type"]:
                    # 儲存設定到 JSON 檔案
                    config_file = "config.json"
                    config = ChannelConfig.load_config(config_file, caller="ManagementCommands")

                    config[channel_info["key"]] = selected_channel_id

                    auto_panel_note = ""
                    if channel_info["key"] == "intro_channel_id" and isinstance(channel, discord.TextChannel):
                        try:
                            panel_message, deleted_old = await self._replace_intro_panel_message(
                                interaction.guild,
                                channel,
                                config,
                            )
                            auto_panel_note = f"\n🤖 已自動發送填寫面板：{panel_message.jump_url}"
                            if deleted_old:
                                auto_panel_note += "\n🧹 舊頻道面板已刪除。"
                        except Exception as e:
                            logger.error(f"設定自我介紹頻道後自動發送面板失敗: {e}", exc_info=True)
                            runtime_cfg = _load_intro_panel_runtime_config()
                            runtime_cfg.pop("intro_panel_message_id", None)
                            _save_intro_panel_runtime_config(ChannelConfig.DEFAULT_ID)
                            auto_panel_note = "\n⚠️ 自動發送面板失敗，系統會在下一次有人送出表單時自動重新 bump。"

                    ChannelConfig.save_config(config, config_file, caller="ManagementCommands")

                    await interaction.response.edit_message(view=None)
                    await safe_send_interaction_message(
                        interaction,
                        f"✅ 已將{selected_type}頻道設定為 **{channel.name}** (ID: {selected_channel_id})！{auto_panel_note}",
                        ephemeral=True
                    )
                    logger.info(f"{selected_type}頻道已設定為 {channel.name} (ID: {selected_channel_id})")
                else:
                    await safe_send_interaction_message(interaction, f"選擇的頻道無效或不是{selected_type}頻道，請重試。", ephemeral=True)

            current_page, channel_view = create_paginated_view(
                channel_options,
                lambda page: f"選擇一個{selected_type}頻道... (第 {page + 1} 頁)" if len(channel_options) > ITEMS_PER_PAGE else f"選擇一個{selected_type}頻道...",
                f"選擇{selected_type}頻道",
                lambda page: f"請從以下選項中選擇一個{selected_type}頻道作為{channel_info['desc']}。(第 {page + 1} 頁)" if len(channel_options) > ITEMS_PER_PAGE else f"請從以下選項中選擇一個{selected_type}頻道作為{channel_info['desc']}",
                channel_info["color"],
                on_select_callback,
                custom_id_prefix=f"management_set_channel_{channel_info['key']}"
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
        await safe_send_interaction_message(interaction, embed=embed, view=type_view, ephemeral=True)

    async def set_role_permissions_cmd(self, interaction: discord.Interaction):
        """設定角色的命令執行權限"""
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
            custom_id="management_set_role_permissions_type_select",
            options=[
                discord.SelectOption(label=role_type, value=role_type, description=info["desc"])
                for role_type, info in role_types.items()
            ]
        )

        async def type_select_callback(interaction: discord.Interaction):
            selected_type = type_select.values[0]
            if selected_type not in role_types:
                await safe_send_interaction_message(interaction, f"無效的角色類型：{selected_type}。請重試。", ephemeral=True)
                return

            role_info = role_types[selected_type]
            roles = [role for role in interaction.guild.roles if not role.is_default()]
            if not roles:
                await safe_send_interaction_message(interaction, f"此伺服器中沒有找到自定義身份組！", ephemeral=True)
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
                await safe_send_interaction_message(interaction, f"沒有可供選擇的身份組！", ephemeral=True)
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
                        await safe_send_interaction_message(
                            interaction,
                            f"✅ 已將 {selected_type} 角色權限設定為 **{role.name}** (ID: {selected_role_id})！",
                            ephemeral=True
                        )
                        logger.info(f"{selected_type} 角色權限已設定為 {role.name} (ID: {selected_role_id})")
                    else:
                        await interaction.response.edit_message(view=None)
                        await safe_send_interaction_message(
                            interaction,
                            f"⚠️ {selected_type} 角色權限已經包含 **{role.name}** (ID: {selected_role_id})！",
                            ephemeral=True
                        )
                else:
                    await safe_send_interaction_message(interaction, f"選擇的身份組無效，請重試。", ephemeral=True)

            current_page, role_view = create_paginated_view(
                role_options,
                lambda page: f"選擇一個身份組... (第 {page + 1} 頁)" if len(role_options) > ITEMS_PER_PAGE else f"選擇一個身份組...",
                f"選擇身份組",
                lambda page: f"請從以下選項中選擇一個身份組作為 {selected_type} 角色。(第 {page + 1} 頁)" if len(role_options) > ITEMS_PER_PAGE else f"請從以下選項中選擇一個身份組作為 {selected_type} 角色。",
                role_info["color"],
                on_select_callback,
                custom_id_prefix=f"management_set_role_permissions_{selected_type.lower()}"
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
        await safe_send_interaction_message(interaction, embed=embed, view=type_view, ephemeral=True)

    async def list_role_permissions_cmd(self, interaction: discord.Interaction):
        """列出角色的命令執行權限設定"""
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
                await safe_send_interaction_message(interaction, "無法讀取配置文件，請重試。", ephemeral=True)
                return

        role_mapping = config.get("role_mapping", {})
        if not role_mapping:
            await safe_send_interaction_message(interaction, "目前沒有設定任何角色權限。", ephemeral=True)
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

        await safe_send_interaction_message(interaction, embed=embed, ephemeral=True)

    async def remove_role_permissions_cmd(self, interaction: discord.Interaction):
        """移除角色的命令執行權限"""
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
                await safe_send_interaction_message(interaction, "無法讀取配置文件，請重試。", ephemeral=True)
                return

        role_mapping = config.get("role_mapping", {})
        if not role_mapping:
            await safe_send_interaction_message(interaction, "目前沒有設定任何角色權限。", ephemeral=True)
            return

        # 創建角色類型選單
        type_select = discord.ui.Select(
            placeholder="選擇要移除的角色類型...",
            custom_id="management_remove_role_permissions_type_select",
            options=[
                discord.SelectOption(label=role_type, value=role_type, description=f"移除 {role_type} 角色權限")
                for role_type in role_mapping.keys()
            ]
        )

        async def type_select_callback(interaction: discord.Interaction):
            selected_type = type_select.values[0]
            if selected_type not in role_mapping:
                await safe_send_interaction_message(interaction, f"無效的角色類型：{selected_type}。請重試。", ephemeral=True)
                return

            role_ids = role_mapping[selected_type]
            if not role_ids or role_ids == [0]:
                await safe_send_interaction_message(interaction, f"目前沒有設定 {selected_type} 角色權限。", ephemeral=True)
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
                    await safe_send_interaction_message(
                        interaction,
                        f"✅ 已移除 {selected_type} 角色權限中的 **{role_name}**！",
                        ephemeral=True
                    )
                    logger.info(f"已移除 {selected_type} 角色權限中的 {role_name}")
                else:
                    await safe_send_interaction_message(interaction, f"選擇的身份組不在 {selected_type} 角色權限中，請重試。", ephemeral=True)

            current_page, role_view = create_paginated_view(
                role_options,
                lambda page: f"選擇要移除的身份組... (第 {page + 1} 頁)" if len(role_options) > ITEMS_PER_PAGE else f"選擇要移除的身份組...",
                f"選擇要移除的身份組",
                lambda page: f"請從以下選項中選擇一個要從 {selected_type} 角色權限中移除的身份組。(第 {page + 1} 頁)" if len(role_options) > ITEMS_PER_PAGE else f"請從以下選項中選擇一個要從 {selected_type} 角色權限中移除的身份組。",
                discord.Color.red(),
                on_select_callback,
                custom_id_prefix=f"management_remove_role_permissions_{selected_type.lower()}"
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
        await safe_send_interaction_message(interaction, embed=embed, view=type_view, ephemeral=True)

    async def role_manager_cmd(self, interaction: discord.Interaction):
        """管理角色的命令執行權限"""
        logger.info(f'收到來自 {interaction.user} 的 role_manager 請求')

        if not await self._check_guild_and_owner(interaction, owner_only=True):
            return

        action_view = RoleManagerView(self)

        embed = discord.Embed(
            title="管理角色權限",
            description="請選擇您要執行的操作。",
            color=discord.Color.greyple()
        )
        await safe_send_interaction_message(interaction, embed=embed, view=action_view, ephemeral=True)

    @app_commands.command(name="server_manager", description="管理伺服器設定")
    async def server_manager_cmd(self, interaction: discord.Interaction):
        """斜線命令：管理伺服器設定"""
        logger.info(f'收到來自 {interaction.user} 的 /server_manager 斜線命令')

        if not await self._check_guild_and_owner(interaction, owner_only=True):
            return

        action_view = ServerManagerView(self)

        embed = discord.Embed(
            title="伺服器管理",
            description="請選擇您要管理的項目。",
            color=discord.Color.greyple()
        )
        await safe_send_interaction_message(interaction, embed=embed, view=action_view, ephemeral=True)

    async def send_intro_panel_cmd(self, interaction: discord.Interaction):
        """在設定好的自我介紹頻道發送/更新填寫面板（非斜線指令入口）。"""
        logger.info(f'收到來自 {interaction.user} 的 intro_panel 請求')

        if not await self._check_guild_and_owner(interaction, owner_only=True):
            return

        from utils.utils import get_intro_channel_id
        intro_channel_id = await get_intro_channel_id(config_file="config.json", caller="ManagementCommands")

        if intro_channel_id == ChannelConfig.DEFAULT_ID:
            await safe_send_interaction_message(
                interaction,
                "❌ 尚未設定自我介紹頻道，請先到 `/server_manager` -> `頻道設定` 完成設定。",
                ephemeral=True,
            )
            return

        intro_channel = interaction.guild.get_channel(intro_channel_id)
        if not isinstance(intro_channel, discord.TextChannel):
            await safe_send_interaction_message(
                interaction,
                f"❌ 找不到有效的自我介紹文字頻道（ID: {intro_channel_id}）。",
                ephemeral=True,
            )
            return

        config_file = "config.json"
        config = ChannelConfig.load_config(config_file, caller="ManagementCommands")

        message, deleted_old = await self._publish_intro_panel(
            guild=interaction.guild,
            intro_channel=intro_channel,
            config=config,
            config_file=config_file,
        )

        deleted_note = "\n🧹 舊頻道面板已刪除。" if deleted_old else ""
        await safe_send_interaction_message(
            interaction,
            f"✅ 已在 {intro_channel.mention} 發送填寫自我介紹面板。\n🔗 {message.jump_url}{deleted_note}",
            ephemeral=True,
        )

    def _build_intro_panel_embed(self) -> discord.Embed:
        """建立自我介紹面板的統一 Embed。"""
        embed = discord.Embed(
            title="👋 自我介紹區",
            description="歡迎！請點擊下方按鈕填寫自我介紹，或填寫對他人的印象。",
            color=discord.Color.purple(),
        )
        embed.add_field(
            name="操作方式",
            value="1)【✍️ 填寫自我介紹】\n2)【🗣️ 填寫對他人印象】\n點擊後會跳出表單",
            inline=False,
        )
        return embed

    async def _send_intro_panel_to_channel(self, intro_channel: discord.TextChannel) -> discord.Message:
        """在指定頻道發送自我介紹面板。"""
        embed = self._build_intro_panel_embed()
        return await intro_channel.send(embed=embed, view=IntroPanelView(self.intro_profile_service, self))

    async def _publish_intro_panel(
        self,
        guild: discord.Guild,
        intro_channel: discord.TextChannel,
        config: dict,
        config_file: str = "config.json",
    ) -> tuple[discord.Message, bool]:
        """統一發布流程：刪除舊面板、發送新面板、更新設定檔。"""
        message, deleted_old = await self._replace_intro_panel_message(
            guild,
            intro_channel,
            config,
        )
        # 其他設定仍維持寫回 config.json；面板訊息 ID 改由 runtime 檔管理
        ChannelConfig.save_config(config, config_file, caller="ManagementCommands")
        return message, deleted_old

    async def _replace_intro_panel_message(
        self,
        guild: discord.Guild,
        intro_channel: discord.TextChannel,
        config: dict,
    ) -> tuple[discord.Message, bool]:
        """刪除舊面板並發新面板（runtime 只存 message_id）"""
        deleted_old = False

        runtime_cfg = _load_intro_panel_runtime_config()
        old_channel_id = config.get("intro_panel_channel_id", ChannelConfig.DEFAULT_ID)
        old_message_id = runtime_cfg.get("intro_panel_message_id", ChannelConfig.DEFAULT_ID)

        if old_channel_id != ChannelConfig.DEFAULT_ID and old_message_id != ChannelConfig.DEFAULT_ID:
            old_channel = guild.get_channel(int(old_channel_id))
            if isinstance(old_channel, discord.TextChannel):
                try:
                    old_message = await old_channel.fetch_message(int(old_message_id))
                    await old_message.delete()
                    deleted_old = True
                    logger.info(f"已刪除舊面板 message_id={old_message_id}")
                except discord.NotFound:
                    logger.info("舊面板不存在，略過刪除")
                except discord.Forbidden:
                    logger.warning("無權限刪除舊面板")

        # 發送新面板
        message = await self._send_intro_panel_to_channel(intro_channel)

        # 更新 config.json（channel_id）
        config["intro_panel_channel_id"] = intro_channel.id
        # 更新 runtime.json（只存 message_id）
        _save_intro_panel_runtime_config(message.id)

        return message, deleted_old

async def setup(bot):
    await bot.add_cog(ManagementCommands(bot))
