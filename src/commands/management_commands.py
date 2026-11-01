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

from utils.discord_members import NO_HOME_GUILD, home_guild, require_access
from utils.discord_content import edit_screen, guarded_screen
from utils.discord_members import (
    addable_role_ids, role_ids_after, role_ids_changed, role_name, role_select_options, roles_by_position,
)
from utils.utils import ITEMS_PER_PAGE, paginate, safe_send_interaction_message, ChannelConfig, ConfigWriteError
from utils.panel_bump import PanelBumper
from utils import runtime_file
from sys_settings.paths import runtime_path
# 注意：需確保 services 資料夾下的 intro_profile_service.py 包含 IntroProfilePayload, ImpressionPayload, IntroProfileServiceProtocol, IntroProfileService 等定義
from services.community.intro_profile_service import (
    IntroProfilePayload,
    ImpressionPayload,
    IntroProfileServiceProtocol,
    IntroProfileService,
)
from services.community.impression_moderation_service import ImpressionModerationService
from llm.storage.member_profile_store import get_member_profile_store
from commands import admin_console, channel_panel

# 獲取 logger
logger = logging.getLogger(__name__)
INTRO_PANEL_RUNTIME_FILE = runtime_path("intro_panel.json")
# 面板按鈕 custom_id：persistent view 與置底翻找殘留面板共用
INTRO_CUSTOM_ID_OPEN = "intro_open_modal"
INTRO_CUSTOM_ID_IMPRESSION = "intro_open_impression_modal"
INTRO_SUBMISSION_RUNTIME_FILE = runtime_path("intro_submissions.json")


def _load_intro_submission_runtime_config() -> dict:
    """讀取自我介紹提交訊息 runtime 資料。"""
    data = runtime_file.load(INTRO_SUBMISSION_RUNTIME_FILE)
    intro_submissions = data.get("intro_submissions")
    impression_submissions = data.get("impression_submissions")
    return {
        "intro_submissions": intro_submissions if isinstance(intro_submissions, dict) else {},
        "impression_submissions": impression_submissions if isinstance(impression_submissions, dict) else {},
    }


def _save_intro_submission_runtime_config(data: dict) -> None:
    """寫入自我介紹提交訊息 runtime 資料。"""
    try:
        runtime_file.save(INTRO_SUBMISSION_RUNTIME_FILE, data)
    except Exception as e:
        logger.error(f"寫入 {INTRO_SUBMISSION_RUNTIME_FILE} 失敗: {e}", exc_info=True)
        raise


def _build_intro_submission_key(*, guild_id: int, author_id: int) -> str:
    """自我介紹提交訊息的 runtime key。"""
    return f"{guild_id}:{author_id}"


def _build_impression_submission_key(*, guild_id: int, author_id: int, target_user_id: int) -> str:
    """他人印象提交訊息的 runtime key。"""
    return f"{guild_id}:{author_id}:{target_user_id}"


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

        await self.management_cog._delete_previous_submission_messages(
            interaction,
            category="intro_submissions",
            record_key=_build_intro_submission_key(
                guild_id=interaction.guild.id,
                author_id=interaction.user.id,
            ),
            message_id_fields=("intro_message_id", "success_message_id"),
        )

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
        intro_message = await interaction.channel.send(content=f"{interaction.user.mention}", embed=embed)

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
        success_message = await interaction.channel.send(content=f"{interaction.user.mention} ✅ 已送出你的自我介紹！")

        try:
            await self.management_cog._record_submission_messages(
                interaction,
                category="intro_submissions",
                record_key=_build_intro_submission_key(
                    guild_id=interaction.guild.id,
                    author_id=interaction.user.id,
                ),
                extra_fields={
                    "intro_message_id": intro_message.id,
                    "success_message_id": success_message.id,
                },
            )
        except Exception as e:
            logger.error(f"紀錄自我介紹訊息 ID 失敗: {e}", exc_info=True)

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
        *,
        prefill_target: Optional[discord.abc.Snowflake] = None,
        prefill_alias: str = "",
        prefill_habit: str = "",
        prefill_impression: str = "",
    ):
        super().__init__(title="填寫對他人印象", timeout=600)

        self.intro_service = intro_service
        self.management_cog = management_cog
        self.moderation_service = ImpressionModerationService()

        logger.info(
            "intro_impression_modal_init: timeout=600, using Label-wrapped UserSelect (2.6.4 supported), prefill=%s",
            bool(prefill_impression or prefill_alias or prefill_habit or prefill_target),
        )

        # UserSelect 本體（不要給 custom_id，讓 library 自動產生）
        # 有帶入上次對象時預選（default_values 需 discord.py 2.4+）
        user_select_kwargs = dict(
            placeholder="請選擇你要填寫印象的對象...",
            min_values=1,
            max_values=1,
            required=True,   # 2.6+ 在 Modal 內生效
            row=0,
        )
        if prefill_target is not None:
            user_select_kwargs["default_values"] = [prefill_target]
        self.target_select: discord.ui.UserSelect = discord.ui.UserSelect(**user_select_kwargs)

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
            default=(prefill_alias or None),
        )
        self.habit_text = discord.ui.TextInput(
            label="他常常在群裡面做什麼？(請簡答)",
            placeholder="例如：有錢人、常常搬石、死臭歐...",
            style=discord.TextStyle.short,
            max_length=100,
            required=False,
            default=(prefill_habit or None),
        )
        self.impression = discord.ui.TextInput(
            label="你對他的整體印象",
            placeholder="請寫下你對他的印象（帥潮、男娘、手法帝...）",
            style=discord.TextStyle.paragraph,
            max_length=600,
            required=True,
            default=(prefill_impression or None),
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

        await self.management_cog._delete_previous_submission_messages(
            interaction,
            category="impression_submissions",
            record_key=_build_impression_submission_key(
                guild_id=interaction.guild.id,
                author_id=interaction.user.id,
                target_user_id=selected_user.id,
            ),
            message_id_fields=("impression_message_id", "success_message_id"),
        )

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
            # 帶入上次內容的重填按鈕，讓被擋的使用者不必整篇重打
            retry_view = ImpressionRetryView(
                self.intro_service,
                self.management_cog,
                target=selected_user,
                alias=alias,
                habit=habit,
                impression=impression_text,
            )
            await safe_send_interaction_message(
                interaction,
                (
                    "⚠️ 這則他人印象暫時無法提交。\n"
                    f"審核原因：{moderation.reason}\n\n"
                    "你剛剛填的內容如下（可直接複製修改）：\n"
                    f"```\n{impression_text}\n```\n"
                    "點下方按鈕可帶入剛剛的內容重新編修後再送出。"
                ),
                ephemeral=True,
                prefer_followup=True,
                view=retry_view,
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

        impression_message = await interaction.channel.send(content=f"{interaction.user.mention}", embed=embed)

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
        success_message = await interaction.channel.send(
            content=f"✅ 已成功送出你對 {selected_user.mention} 的印象，謝謝分享！"
        )

        try:
            await self.management_cog._record_submission_messages(
                interaction,
                category="impression_submissions",
                record_key=_build_impression_submission_key(
                    guild_id=interaction.guild.id,
                    author_id=interaction.user.id,
                    target_user_id=selected_user.id,
                ),
                extra_fields={
                    "target_user_id": selected_user.id,
                    "impression_message_id": impression_message.id,
                    "success_message_id": success_message.id,
                },
            )
        except Exception as e:
            logger.error(f"紀錄他人印象訊息 ID 失敗: {e}", exc_info=True)

        try:
            await self.management_cog._auto_bump_intro_panel_after_submission(interaction)
        except Exception as e:
            logger.error(f"他人印象送出後自動 bump 面板失敗: {e}", exc_info=True)


class ImpressionRetryView(discord.ui.View):
    """他人印象被審核擋下後，讓使用者一鍵帶入上次內容重新編修再送出。

    非持久化 view：只在 timeout 期間有效，逾時後按鈕失效，但訊息中已附原文可手動複製。
    """

    def __init__(
        self,
        intro_service: IntroProfileServiceProtocol,
        management_cog: "ManagementCommands",
        *,
        target: discord.abc.Snowflake,
        alias: str,
        habit: str,
        impression: str,
        timeout: float = 600,
    ):
        super().__init__(timeout=timeout)
        self.intro_service = intro_service
        self.management_cog = management_cog
        self._target = target
        self._alias = alias
        self._habit = habit
        self._impression = impression

    @discord.ui.button(label="✏️ 重新填寫（帶入剛剛內容）", style=discord.ButtonStyle.primary)
    async def retry_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            IntroImpressionModal(
                self.intro_service,
                self.management_cog,
                prefill_target=self._target,
                prefill_alias=self._alias,
                prefill_habit=self._habit,
                prefill_impression=self._impression,
            )
        )


class IntroPanelView(discord.ui.View):
    """自我介紹面板 persistent view"""

    def __init__(self, intro_service: IntroProfileServiceProtocol, management_cog: "ManagementCommands"):
        super().__init__(timeout=None)
        self.intro_service = intro_service
        self.management_cog = management_cog

    @discord.ui.button(label="✍️ 填寫自我介紹", style=discord.ButtonStyle.primary, custom_id=INTRO_CUSTOM_ID_OPEN)
    async def intro_open_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(IntroProfileModal(self.intro_service, self.management_cog))

    @discord.ui.button(label="🗣️ 填寫對他人印象", style=discord.ButtonStyle.secondary, custom_id=INTRO_CUSTOM_ID_IMPRESSION)
    async def intro_open_impression_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        logger.info(
            "intro_impression_button_clicked user_id=%s guild_id=%s channel_id=%s custom_id=%s",
            interaction.user.id if interaction.user else None,
            interaction.guild.id if interaction.guild else None,
            interaction.channel.id if interaction.channel else None,
            button.custom_id,
        )
        await interaction.response.send_modal(IntroImpressionModal(self.intro_service, self.management_cog))


# ────────────────────────────────────────────
#  角色管理：Trader、Moderator 各對應哪些身份組（主控台的一個畫面：主畫面列現況、勾選畫面分頁多選）
# ────────────────────────────────────────────

#: 動作、哪種角色、新增或移除、頁碼；選單另一個樣板（同一則訊息裡 custom_id 不能撞）
ROLE_TEMPLATE = r"roles:(?P<action>home|pick)(?::(?P<kind>trader|moderator))?(?::(?P<mode>add|remove))?(?::(?P<page>\d+))?"
ROLE_SELECT_TEMPLATE = r"roles:sel:(?P<kind>trader|moderator):(?P<mode>add|remove):(?P<page>\d+)"
#: 代號 →（config.json `role_mapping` 的 key、說明）
ROLE_KINDS: dict[str, tuple[str, str]] = {
    "trader": ("Trader", "交易員：自由市場、商品與購物車的交易身份"),
    "moderator": ("Moderator", "版主：社群管理類指令"),
}
_ROLE_ACCESS = dict(owner_only=True, allow_dm=True)
_CONFIG_BROKEN = "❌ 設定檔讀取失敗，這次沒有寫入，請檢查 config.json。"


def _mapped_role_ids(kind: str) -> list[int]:
    """這種角色目前對應的身份組 id（舊設定用 [0] 當「沒設」，略過）。"""
    mapping = ChannelConfig.load_config(caller="ManagementCommands").get("role_mapping", {})
    ids = mapping.get(ROLE_KINDS[kind][0], []) if isinstance(mapping, dict) else []
    return [int(rid) for rid in ids if isinstance(rid, int) and rid > 0] if isinstance(ids, list) else []


def render_roles_home(guild: discord.Guild, *, notice: Optional[str] = None) -> discord.ui.LayoutView:
    """主畫面：每種角色一行現況、一排「新增」「移除」；沒得加、沒得減的那顆灰掉。"""
    box = admin_console.screen_box("## 🎭 角色管理\n-# Trader、Moderator 各對應哪些身份組；新增、移除都在這裡設，改了馬上生效",
                                   notice=notice, colour=discord.Color.purple())
    rows: list[list[discord.ui.Item]] = []
    for kind, (key, desc) in ROLE_KINDS.items():
        current = roles_by_position(guild, _mapped_role_ids(kind))
        names = "、".join(role_name(guild, rid) for rid in current) or "未設定"
        box.add_item(discord.ui.TextDisplay(f"**{key}**　{names[:900]}\n-# {desc}"))
        rows.append([
            RoleButton("pick", kind, "add", 0, label=f"➕ {key} 新增", style=discord.ButtonStyle.success,
                       disabled=not addable_role_ids(guild, current)),
            RoleButton("pick", kind, "remove", 0, label=f"➖ {key} 移除", style=discord.ButtonStyle.danger, disabled=not current),
        ])
    return admin_console.screen_view(box, *rows, [admin_console.back_button()])


def render_role_pick(guild: discord.Guild, kind: str, mode: str, page: int) -> discord.ui.LayoutView:
    """勾選畫面：這一頁的身份組一個選單（可多選、一次送出一頁），超過 25 個才有上一頁／下一頁；頁碼夾回合法範圍。
    沒東西可選就退回主畫面並說原因。"""
    key, _ = ROLE_KINDS[kind]
    current = _mapped_role_ids(kind)
    adding = mode == "add"
    role_ids = addable_role_ids(guild, current) if adding else roles_by_position(guild, current)
    if not role_ids:
        return render_roles_home(guild, notice=(f"⚠️ 所有身份組都已經在 {key} 的設定裡，沒有可新增的。" if adding
                                                else f"⚠️ {key} 目前沒有已設定的身份組可移除。"))
    shown, page, pages = paginate(role_ids, page, ITEMS_PER_PAGE)
    verb = "新增" if adding else "移除"
    title = f"## {'➕' if adding else '➖'} {key} {verb}身份組\n-# 勾選要{verb}的身份組（可多選；一次送出一頁）。"
    if pages > 1:
        title += f"\n-# 第 {page + 1}／{pages} 頁，共 {len(role_ids)} 個。"
    box = admin_console.screen_box(title, colour=discord.Color.green() if adding else discord.Color.red())
    buttons: list[discord.ui.Item] = []
    if pages > 1:
        buttons.append(RoleButton("pick", kind, mode, max(page - 1, 0), label="◀ 上一頁", disabled=page <= 0))
        buttons.append(RoleButton("pick", kind, mode, min(page + 1, pages - 1), label="下一頁 ▶", disabled=page >= pages - 1))
    buttons.append(RoleButton("home", label="↩️ 回上一層"))
    return admin_console.screen_view(box, [RoleSelect(kind, mode, page, options=role_select_options(guild, shown))], buttons)


async def _apply_role_change(interaction: discord.Interaction, guild: discord.Guild, kind: str, mode: str,
                             picked: list[int]) -> None:
    """勾好送出：寫 config.json 的 role_mapping，回主畫面並在最上面講結果。"""
    key, _ = ROLE_KINDS[kind]
    changed = role_ids_changed(_mapped_role_ids(kind), picked, mode)
    verb = "新增" if mode == "add" else "移除"
    if not changed:
        notice = "⚠️ 勾的身份組都已經在設定裡了。" if mode == "add" else "⚠️ 勾的身份組都不在設定裡。"
    else:
        # 名字在寫檔前就算好：寫完才查，查不到會變成「寫進去了但畫面說失敗」
        names = [role_name(guild, rid) for rid in changed]

        def change(c: dict) -> None:
            mapping = c.setdefault("role_mapping", {})
            mapping[key] = [rid for rid in role_ids_after(mapping.get(key), mode, changed) if rid > 0]

        try:
            await ChannelConfig.update_config(change, caller="ManagementCommands")
        except ConfigWriteError as exc:
            logger.error("角色管理：%s %s 寫入設定檔失敗: %s", key, verb, exc)
            notice = _CONFIG_BROKEN
        else:
            logger.info("角色管理：%s %s %s → %s", interaction.user, key, verb, ", ".join(names))
            notice = f"✅ {key} 已{verb} {len(names)} 個身份組：{', '.join(f'**{n}**' for n in names)}"
    await edit_screen(interaction, view=render_roles_home(guild, notice=notice))


async def _guarded_roles(interaction: discord.Interaction, label: str, run) -> None:
    """角色管理一次操作的外殼：先驗群主與伺服器，做壞了換回主畫面並標錯誤。"""
    if not await require_access(interaction, **_ROLE_ACCESS):
        return
    guild = home_guild(interaction)
    if guild is None:
        await safe_send_interaction_message(interaction, NO_HOME_GUILD, ephemeral=True)
        return
    await guarded_screen(interaction, f"角色管理：{label}", lambda: run(guild), log=logger,
                         rescue=lambda notice: edit_screen(interaction, view=render_roles_home(guild, notice=notice)))


class RoleButton(discord.ui.DynamicItem[discord.ui.Button], template=ROLE_TEMPLATE):
    """角色管理的按鈕：回主畫面、進勾選畫面（哪種角色、新增或移除、頁碼都在 custom_id）。"""

    def __init__(self, action: str, kind: Optional[str] = None, mode: Optional[str] = None, page: Optional[int] = None, *,
                 label: str, style: discord.ButtonStyle = discord.ButtonStyle.secondary, disabled: bool = False):
        parts = ["roles", action] + [p for p in (kind, mode) if p] + ([str(int(page))] if page is not None else [])
        super().__init__(discord.ui.Button(label=label, style=style, custom_id=":".join(parts), disabled=disabled))
        self.action, self.kind, self.mode = action, kind, mode
        self.page = int(page) if page is not None else 0

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match, /):
        return cls(match["action"], match["kind"], match["mode"], match["page"], label=item.label or "…",
                   style=item.style, disabled=item.disabled)

    async def callback(self, interaction: discord.Interaction):
        async def run(guild: discord.Guild) -> None:
            if self.action == "pick" and self.kind in ROLE_KINDS and self.mode in ("add", "remove"):
                await edit_screen(interaction, view=render_role_pick(guild, self.kind, self.mode, self.page))
            else:
                await edit_screen(interaction, view=render_roles_home(guild))

        await _guarded_roles(interaction, self.custom_id, run)


class RoleSelect(discord.ui.DynamicItem[discord.ui.Select], template=ROLE_SELECT_TEMPLATE):
    """勾選畫面的選單：選項是這一頁的身份組，可多選；送出就寫設定檔。"""

    def __init__(self, kind: str, mode: str, page: int, *, options=()):
        opts = list(options) or [discord.SelectOption(label="（沒有項目）", value="-")]
        super().__init__(discord.ui.Select(
            custom_id=f"roles:sel:{kind}:{mode}:{int(page)}",
            placeholder=f"勾選要{'新增' if mode == 'add' else '移除'}的身份組…",
            min_values=1, max_values=len(opts), options=opts, disabled=not options,
        ))
        self.kind, self.mode, self.page = kind, mode, int(page)

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Select, match, /):
        return cls(match["kind"], match["mode"], int(match["page"]), options=item.options)

    async def callback(self, interaction: discord.Interaction):
        picked = [int(v) for v in self.item.values if v.isdigit()]
        await _guarded_roles(interaction, self.custom_id,
                             lambda guild: _apply_role_change(interaction, guild, self.kind, self.mode, picked))


ROLE_DYNAMIC_ITEMS = (RoleButton, RoleSelect)


class ManagementCommands(commands.Cog):
    def __init__(self, bot, intro_profile_service: Optional[IntroProfileServiceProtocol] = None):
        self.bot = bot
        self.intro_profile_service: IntroProfileServiceProtocol = (
            intro_profile_service or IntroProfileService(rag_port=get_member_profile_store())
        )
        # 面板位置記在 runtime 檔的 intro_panel_channel_id / intro_panel_message_id（不寫 config.json）
        self.intro_panel = PanelBumper(
            INTRO_PANEL_RUNTIME_FILE, self._send_intro_panel_to_channel,
            custom_ids=(INTRO_CUSTOM_ID_OPEN, INTRO_CUSTOM_ID_IMPRESSION), key_prefix="intro_panel_",
        )

    async def cog_load(self):
        # 註冊 persistent views，避免機器人重啟後主入口按鈕失效
        self.bot.add_view(IntroPanelView(self.intro_profile_service, self))
        # 主控台、頻道綁定、角色管理的按鈕狀態都在 custom_id 裡，走 DynamicItem；舊的伺服器資訊、角色管理選單按了由主控台接手
        self.bot.add_dynamic_items(*channel_panel.DYNAMIC_ITEMS, *admin_console.DYNAMIC_ITEMS, *ROLE_DYNAMIC_ITEMS)
        logger.info("已註冊 ManagementCommands persistent views")

    async def _delete_previous_submission_messages(
        self,
        interaction: discord.Interaction,
        *,
        category: str,
        record_key: str,
        message_id_fields: tuple[str, ...],
    ) -> None:
        """刪除舊的提交訊息（自我介紹或他人印象皆適用）。"""
        if not interaction.guild or not interaction.channel:
            return

        runtime_data = _load_intro_submission_runtime_config()
        submissions = runtime_data.get(category, {})
        record = submissions.get(record_key)
        if not isinstance(record, dict):
            return

        channel_id = int(record.get("channel_id") or interaction.channel.id)
        target_channel = interaction.guild.get_channel(channel_id)
        if not isinstance(target_channel, discord.TextChannel):
            submissions.pop(record_key, None)
            _save_intro_submission_runtime_config(runtime_data)
            return

        deleted_any = False
        for field_name in message_id_fields:
            message_id = record.get(field_name)
            if not message_id:
                continue
            try:
                old_message = await target_channel.fetch_message(int(message_id))
                await old_message.delete()
                deleted_any = True
            except discord.NotFound:
                logger.info("舊訊息不存在，略過刪除: category=%s field=%s message_id=%s", category, field_name, message_id)
            except discord.Forbidden:
                logger.warning("無權限刪除舊訊息: category=%s field=%s message_id=%s", category, field_name, message_id)
            except Exception as e:
                logger.error("刪除舊訊息失敗: category=%s field=%s message_id=%s err=%s", category, field_name, message_id, e, exc_info=True)

        submissions.pop(record_key, None)
        _save_intro_submission_runtime_config(runtime_data)

        if deleted_any:
            logger.info("已刪除舊提交訊息: category=%s key=%s", category, record_key)

    async def _record_submission_messages(
        self,
        interaction: discord.Interaction,
        *,
        category: str,
        record_key: str,
        extra_fields: dict,
    ) -> None:
        """紀錄最新提交訊息的 message id（自我介紹或他人印象皆適用）。"""
        if not interaction.guild or not interaction.channel:
            return

        runtime_data = _load_intro_submission_runtime_config()
        submissions = runtime_data.setdefault(category, {})
        submissions[record_key] = {
            "guild_id": interaction.guild.id,
            "channel_id": interaction.channel.id,
            "author_id": interaction.user.id,
            **extra_fields,
        }
        _save_intro_submission_runtime_config(runtime_data)

    async def _auto_bump_intro_panel_after_submission(self, interaction: discord.Interaction):
        """提交表單後，自動刪除舊面板並重發置底。"""
        if not interaction.guild:
            return

        config = ChannelConfig.load_config(caller="ManagementCommands")
        intro_channel_id = config.get("intro_channel_id", ChannelConfig.DEFAULT_ID)
        if intro_channel_id == ChannelConfig.DEFAULT_ID:
            logger.info("自動 bump 跳過：intro_channel_id 未設定。")
            return

        intro_channel = interaction.guild.get_channel(int(intro_channel_id))
        if not isinstance(intro_channel, discord.TextChannel):
            logger.warning("自動 bump 跳過：intro_channel_id 非有效文字頻道。id=%s", intro_channel_id)
            return

        message, deleted_old = await self.intro_panel.bump(intro_channel)
        logger.info(
            "自動 bump 完成：new_message_id=%s deleted_old=%s channel_id=%s",
            message.id,
            deleted_old,
            intro_channel.id,
        )

    async def _send_error_message(self, interaction: discord.Interaction, message: str):
        """發送錯誤訊息"""
        await safe_send_interaction_message(interaction, message, ephemeral=True)

    @app_commands.command(name="server_info", description="伺服器資訊：列出頻道與身份組的 ID（只有群主；私訊裡也能用）")
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=False)
    async def server_info_cmd(self, interaction: discord.Interaction):
        """斜線命令：直接開在主控台的「伺服器資訊」那一頁（清單一頁一頁翻）"""
        logger.info(f'收到來自 {interaction.user} 的 /server_info 斜線命令')
        await admin_console.send_console(interaction, screen="info")

    async def open_roles(self, interaction: discord.Interaction, guild: discord.Guild) -> None:
        """主控台的「角色管理」：把角色管理畫在主控台那一則上（權限由主控台先驗）。"""
        await edit_screen(interaction, view=render_roles_home(guild))

    @app_commands.command(name="server_manager", description="管理主控台：狀態、頻道、角色、文章、點名、AI（只有群主；私訊裡也能用）")
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=False)
    async def server_manager_cmd(self, interaction: discord.Interaction):
        """斜線命令：管理主控台（私訊裡也能用，只有群主；私訊裡只有這個指令會叫出選單）"""
        logger.info(f'收到來自 {interaction.user} 的 /server_manager 斜線命令')
        await admin_console.send_console(interaction)

    async def send_intro_panel_cmd(self, interaction: discord.Interaction):
        """在設定好的自我介紹頻道發送/更新填寫面板（非斜線指令入口）。"""
        logger.info(f'收到來自 {interaction.user} 的 intro_panel 請求')

        if not await require_access(interaction, owner_only=True):
            return

        from utils.utils import get_intro_channel_id
        intro_channel_id = await get_intro_channel_id(caller="ManagementCommands")

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

        message, deleted_old = await self.intro_panel.bump(intro_channel)

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


async def setup(bot):
    await bot.add_cog(ManagementCommands(bot))
