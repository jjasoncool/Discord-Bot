"""
幽靈點名 Cog — 管理面板 + 回覆按鈕（persistent views）
"""
import json
import logging
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

from utils.utils import ChannelConfig, ITEMS_PER_PAGE
from services.rollcall_service import (
    RollCallService,
    RESPONSE_DEADLINE_DAYS,
    IMMUNITY_DAYS,
    _now_utc8,
)

logger = logging.getLogger('discord_bot')

CONFIG_FILE = "config.json"


# ────────────────────────────────────────────
#  Persistent Views
# ────────────────────────────────────────────

class RollCallResponseView(discord.ui.View):
    """點名回覆按鈕（每則點名訊息附帶，persistent）"""

    def __init__(self, service: RollCallService = None, target_user_id: int = None):
        super().__init__(timeout=None)
        self._service = service
        self._target_user_id = target_user_id

    @discord.ui.button(
        label="✋ 我是活人",
        style=discord.ButtonStyle.success,
        custom_id="rollcall_response",
    )
    async def respond(self, interaction: discord.Interaction, button: discord.ui.Button):
        service = self._service
        if service is None:
            cog = interaction.client.get_cog("RollCallCommands")
            if cog:
                service = cog.service

        if service is None:
            await interaction.response.send_message(
                "系統尚未就緒，請稍後再試。", ephemeral=True
            )
            return

        user_id = interaction.user.id

        # 以 message_id 反查這則點名訊息真正對應的目標使用者，
        # 避免重啟後 persistent view 的 _target_user_id 為 None 而失去綁定。
        target_user_id = self._target_user_id
        msg = interaction.message
        if msg is not None:
            for uid_str, info in service.runtime.pending.items():
                if info.get("message_id") == msg.id:
                    target_user_id = int(uid_str)
                    break

        # 只有被點名本人能回覆「自己的」點名訊息，
        # 防止 A 透過 B 的按鈕解掉自己（或誤動）的點名。
        if target_user_id is not None and user_id != target_user_id:
            await interaction.response.send_message(
                "這不是你的點名訊息，只有被點名本人可以回覆。", ephemeral=True
            )
            return

        if not service.runtime.is_pending(user_id):
            await interaction.response.send_message(
                "你目前沒有待回覆的點名，可能已經回覆過了。", ephemeral=True
            )
            return

        await service.handle_response(user_id, interaction)


class RollCallAdminView(discord.ui.View):
    """管理員控制面板（persistent）"""

    def __init__(self, service: RollCallService = None):
        super().__init__(timeout=None)
        self._service = service

    def _get_service(self, interaction: discord.Interaction) -> RollCallService:
        if self._service:
            return self._service
        cog = interaction.client.get_cog("RollCallCommands")
        return cog.service if cog else None

    async def _check_admin(self, interaction: discord.Interaction) -> bool:
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "只有管理員可以操作。", ephemeral=True
            )
            return False
        return True

    # ── Row 0: 開關 + 手動點名 ──

    @discord.ui.button(
        label="✅ 開啟",
        style=discord.ButtonStyle.success,
        custom_id="rollcall_admin_enable",
        row=0,
    )
    async def enable(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_admin(interaction):
            return
        service = self._get_service(interaction)
        if not service:
            await interaction.response.send_message("系統尚未就緒。", ephemeral=True)
            return

        service.runtime.enabled = True
        service.runtime.save()
        embed = service.get_status_embed()
        await interaction.response.edit_message(embed=embed)
        logger.info(f"幽靈點名：{interaction.user} 已開啟自動點名")

    @discord.ui.button(
        label="❌ 關閉",
        style=discord.ButtonStyle.danger,
        custom_id="rollcall_admin_disable",
        row=0,
    )
    async def disable(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_admin(interaction):
            return
        service = self._get_service(interaction)
        if not service:
            await interaction.response.send_message("系統尚未就緒。", ephemeral=True)
            return

        service.runtime.enabled = False
        service.runtime.save()
        embed = service.get_status_embed()
        await interaction.response.edit_message(embed=embed)
        logger.info(f"幽靈點名：{interaction.user} 已關閉自動點名")

    @discord.ui.button(
        label="🎲 手動點名",
        style=discord.ButtonStyle.primary,
        custom_id="rollcall_admin_manual",
        row=0,
    )
    async def manual_pick(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_admin(interaction):
            return
        service = self._get_service(interaction)
        if not service:
            await interaction.response.send_message("系統尚未就緒。", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        picked = await service.do_roll_call(manual=True)
        if picked:
            names = ", ".join(m.display_name for m in picked)
            await interaction.followup.send(
                f"已手動點名 {len(picked)} 人：{names}", ephemeral=True
            )
        else:
            await interaction.followup.send(
                "沒有符合資格的成員可抽選（可能全部在豁免期或 pending 中）。",
                ephemeral=True,
            )
        embed = service.get_status_embed()
        try:
            await interaction.message.edit(embed=embed)
        except Exception:
            pass

    # ── Row 1: 查看 + 刷新 ──

    @discord.ui.button(
        label="📋 待回覆清單",
        style=discord.ButtonStyle.secondary,
        custom_id="rollcall_admin_pending",
        row=1,
    )
    async def show_pending(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_admin(interaction):
            return
        service = self._get_service(interaction)
        if not service:
            await interaction.response.send_message("系統尚未就緒。", ephemeral=True)
            return

        pending = service.runtime.get_pending_list()
        if not pending:
            await interaction.response.send_message(
                "目前沒有待回覆的點名。", ephemeral=True
            )
            return

        lines = []
        now = _now_utc8()
        for item in pending:
            deadline = datetime.fromisoformat(item["deadline"])
            remaining = deadline - now
            days_left = max(0, remaining.days)
            lines.append(
                f"• <@{item['user_id']}> — 剩餘 {days_left} 天"
                f"（截止 {deadline.strftime('%m/%d %H:%M')}）"
            )

        embed = discord.Embed(
            title="📋 待回覆點名清單",
            description="\n".join(lines),
            color=discord.Color.orange(),
        )
        embed.set_footer(text=f"共 {len(pending)} 人待回覆")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(
        label="🔄 刷新狀態",
        style=discord.ButtonStyle.secondary,
        custom_id="rollcall_admin_refresh",
        row=1,
    )
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_admin(interaction):
            return
        service = self._get_service(interaction)
        if not service:
            await interaction.response.send_message("系統尚未就緒。", ephemeral=True)
            return

        embed = service.get_status_embed()
        await interaction.response.edit_message(embed=embed)

    # ── Row 2: 身份組設定 ──

    @discord.ui.button(
        label="🎯 設定目標身份組",
        style=discord.ButtonStyle.secondary,
        custom_id="rollcall_admin_set_target",
        row=2,
    )
    async def set_target_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_admin(interaction):
            return
        await _show_role_config_menu(
            interaction,
            config_key="rollcall_target_role_ids",
            title="🎯 設定目標身份組",
            description="選擇要點名的身份組（新增或移除）：",
        )

    @discord.ui.button(
        label="🛡️ 設定排除身份組",
        style=discord.ButtonStyle.secondary,
        custom_id="rollcall_admin_set_exclude",
        row=2,
    )
    async def set_exclude_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_admin(interaction):
            return
        await _show_role_config_menu(
            interaction,
            config_key="rollcall_exclude_role_ids",
            title="🛡️ 設定排除身份組",
            description="擁有這些身份組的成員不會被點名（新增或移除）：",
        )

    @discord.ui.button(
        label="👥 點名範圍",
        style=discord.ButtonStyle.secondary,
        custom_id="rollcall_admin_preview",
        row=2,
    )
    async def preview_scope(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_admin(interaction):
            return
        service = self._get_service(interaction)
        if not service:
            await interaction.response.send_message("系統尚未就緒。", ephemeral=True)
            return

        target_ids = set(service._get_target_role_ids())
        exclude_ids = set(service._get_exclude_role_ids())

        if not target_ids:
            await interaction.response.send_message(
                "尚未設定目標身份組。", ephemeral=True
            )
            return

        guild = interaction.guild

        # 用 service 同一套邏輯篩選
        members = [m async for m in guild.fetch_members(limit=None)]
        candidates = service._collect_candidates_from_list(
            members, list(target_ids), list(exclude_ids),
        )

        if not candidates:
            await interaction.response.send_message(
                "目前沒有成員會被點名（可能全部被排除、豁免中、或待回覆中）。",
                ephemeral=True,
            )
            return

        # 機器人管理的身份組不列入組合顯示
        managed_role_ids = {r.id for r in guild.roles if r.managed or r.is_default()}

        # 從篩選結果統計身份組組合
        combo_counts: dict[frozenset[int], int] = {}
        for member in candidates:
            display_roles = frozenset(
                r.id for r in member.roles
                if r.id not in managed_role_ids
            )
            combo_counts[display_roles] = combo_counts.get(display_roles, 0) + 1

        lines = []
        for combo, count in sorted(combo_counts.items(), key=lambda x: -x[1]):
            role_names = []
            for rid in combo:
                role = guild.get_role(rid)
                role_names.append(role.name if role else str(rid))
            role_names.sort()
            lines.append(f"• {' + '.join(role_names)}（{count} 人）")

        total = sum(combo_counts.values())

        embed = discord.Embed(
            title="👥 點名範圍（身份組組合）",
            description="\n".join(lines),
            color=discord.Color.blue(),
        )
        embed.set_footer(text=f"共 {total} 人可被點名\n已排除 Bot、管理員、排除身份組、豁免中、待回覆中")
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ────────────────────────────────────────────
#  身份組設定共用邏輯
# ────────────────────────────────────────────

async def _show_role_config_menu(
    interaction: discord.Interaction,
    *,
    config_key: str,
    title: str,
    description: str,
):
    """顯示身份組設定選單（StringSelect 多選，新增只列未加入的，移除只列已加入的）"""
    config = ChannelConfig.load_config(CONFIG_FILE, caller="RollCallCommands")
    current_ids: list = config.get(config_key, [])
    current_set = set(current_ids)

    # 目前已設定的身份組
    if current_ids:
        lines = []
        for rid in current_ids:
            role = interaction.guild.get_role(rid)
            lines.append(f"• {role.name}" if role else f"• 未知 (ID: {rid})")
        current_text = "\n".join(lines)
    else:
        current_text = "（無）"

    # 建立操作選單
    action_select = discord.ui.Select(
        placeholder="選擇操作...",
        custom_id=f"rollcall_{config_key}_action",
        options=[
            discord.SelectOption(label="新增身份組", value="add", emoji="➕"),
            discord.SelectOption(label="移除身份組", value="remove", emoji="➖"),
        ],
    )

    async def action_callback(action_interaction: discord.Interaction):
        action = action_select.values[0]

        if action == "add":
            # 只列出尚未加入的身份組
            available_roles = [
                r for r in interaction.guild.roles
                if not r.is_default() and r.id not in current_set
            ]
            if not available_roles:
                await action_interaction.response.send_message(
                    "所有身份組都已設定，沒有可新增的。", ephemeral=True
                )
                return

            options = [
                discord.SelectOption(
                    label=r.name, value=str(r.id),
                    description=f"ID: {r.id}", emoji="🎭"
                )
                for r in available_roles
            ]

            # Discord Select 上限 25 個選項，需要分頁
            if len(options) <= ITEMS_PER_PAGE:
                role_select = discord.ui.Select(
                    placeholder="選擇要新增的身份組（可多選）...",
                    min_values=1,
                    max_values=len(options),
                    options=options,
                )

                async def on_add(sel_interaction: discord.Interaction):
                    fresh = ChannelConfig.load_config(CONFIG_FILE, caller="RollCallCommands")
                    id_list = fresh.get(config_key, [])
                    if not isinstance(id_list, list):
                        id_list = []

                    added = []
                    for val in role_select.values:
                        role_id = int(val)
                        if role_id not in id_list:
                            id_list.append(role_id)
                            role = sel_interaction.guild.get_role(role_id)
                            added.append(role.name if role else str(role_id))

                    fresh[config_key] = id_list
                    ChannelConfig.save_config(fresh, CONFIG_FILE, caller="RollCallCommands")

                    names = ", ".join(f"**{n}**" for n in added)
                    await sel_interaction.response.edit_message(
                        content=f"✅ 已新增 {len(added)} 個身份組：{names}",
                        embed=None, view=None,
                    )
                    logger.info(f"幽靈點名：{sel_interaction.user} 新增 {config_key} → {', '.join(added)}")
                    await _try_refresh_admin_panel(sel_interaction)

                role_select.callback = on_add
                add_view = discord.ui.View()
                add_view.add_item(role_select)
                embed = discord.Embed(
                    title="新增身份組",
                    description="請選擇要新增的身份組（可一次多選）。",
                    color=discord.Color.green(),
                )
                await action_interaction.response.edit_message(embed=embed, view=add_view)
            else:
                # 超過 25 個，使用 RoleSelect 讓使用者從全伺服器選
                role_select = discord.ui.RoleSelect(
                    placeholder="選擇要新增的身份組（可多選）...",
                    min_values=1,
                    max_values=25,
                )

                async def on_add_fallback(sel_interaction: discord.Interaction):
                    fresh = ChannelConfig.load_config(CONFIG_FILE, caller="RollCallCommands")
                    id_list = fresh.get(config_key, [])
                    if not isinstance(id_list, list):
                        id_list = []

                    added = []
                    skipped = []
                    for role in role_select.values:
                        if role.id not in id_list:
                            id_list.append(role.id)
                            added.append(role.name)
                        else:
                            skipped.append(role.name)

                    if added:
                        fresh[config_key] = id_list
                        ChannelConfig.save_config(fresh, CONFIG_FILE, caller="RollCallCommands")
                        names = ", ".join(f"**{n}**" for n in added)
                        msg = f"✅ 已新增 {len(added)} 個身份組：{names}"
                        if skipped:
                            msg += f"\n⚠️ 已跳過（重複）：{', '.join(skipped)}"
                        await sel_interaction.response.edit_message(
                            content=msg, embed=None, view=None,
                        )
                        logger.info(f"幽靈點名：{sel_interaction.user} 新增 {config_key} → {', '.join(added)}")
                    else:
                        await sel_interaction.response.edit_message(
                            content="⚠️ 選擇的身份組皆已存在。", embed=None, view=None,
                        )
                    await _try_refresh_admin_panel(sel_interaction)

                role_select.callback = on_add_fallback
                add_view = discord.ui.View()
                add_view.add_item(role_select)
                embed = discord.Embed(
                    title="新增身份組",
                    description="身份組數量較多，請從下方選擇要新增的身份組（可多選）。\n已設定的身份組會自動跳過。",
                    color=discord.Color.green(),
                )
                await action_interaction.response.edit_message(embed=embed, view=add_view)

        elif action == "remove":
            if not current_ids:
                await action_interaction.response.send_message(
                    "目前沒有已設定的身份組可移除。", ephemeral=True
                )
                return

            # 列出所有已設定的身份組，全部預設勾選
            # 使用者取消勾選的 = 要移除的，保留勾選的 = 要留下的
            options = []
            for rid in current_ids:
                role = interaction.guild.get_role(rid)
                options.append(discord.SelectOption(
                    label=role.name if role else f"未知 (ID: {rid})",
                    value=str(rid),
                    description=f"ID: {rid}", emoji="🎭",
                    default=True,  # 全部預選
                ))

            role_select = discord.ui.Select(
                placeholder="取消勾選要移除的身份組...",
                min_values=0,  # 允許全部取消
                max_values=len(options),
                options=options,
            )

            async def on_remove(sel_interaction: discord.Interaction):
                # 勾選的 = 要保留的
                kept_ids = {int(val) for val in role_select.values}
                original_set = set(current_ids)
                removed_ids = original_set - kept_ids

                if not removed_ids:
                    await sel_interaction.response.edit_message(
                        content="未變更任何身份組。", embed=None, view=None,
                    )
                    return

                fresh = ChannelConfig.load_config(CONFIG_FILE, caller="RollCallCommands")
                # 直接用保留的清單覆寫
                fresh[config_key] = [rid for rid in fresh.get(config_key, []) if rid not in removed_ids]
                ChannelConfig.save_config(fresh, CONFIG_FILE, caller="RollCallCommands")

                removed_names = []
                for rid in removed_ids:
                    role = sel_interaction.guild.get_role(rid)
                    removed_names.append(role.name if role else str(rid))

                names = ", ".join(f"**{n}**" for n in removed_names)
                await sel_interaction.response.edit_message(
                    content=f"✅ 已移除 {len(removed_names)} 個身份組：{names}",
                    embed=None, view=None,
                )
                logger.info(f"幽靈點名：{sel_interaction.user} 移除 {config_key} → {', '.join(removed_names)}")
                await _try_refresh_admin_panel(sel_interaction)

            role_select.callback = on_remove
            remove_view = discord.ui.View()
            remove_view.add_item(role_select)
            embed = discord.Embed(
                title="移除身份組",
                description="以下為目前已設定的身份組（全部預選）。\n**取消勾選**要移除的，然後送出。",
                color=discord.Color.red(),
            )
            await action_interaction.response.edit_message(embed=embed, view=remove_view)

    action_select.callback = action_callback
    action_view = discord.ui.View()
    action_view.add_item(action_select)

    embed = discord.Embed(
        title=title,
        description=f"{description}\n\n**目前設定：**\n{current_text}",
        color=discord.Color.dark_orange(),
    )
    await interaction.response.send_message(embed=embed, view=action_view, ephemeral=True)


async def _try_refresh_admin_panel(interaction: discord.Interaction):
    """嘗試更新管理面板的 embed"""
    cog = interaction.client.get_cog("RollCallCommands")
    if not cog:
        return
    service = cog.service
    msg_id = service.runtime.admin_panel_message_id
    if not msg_id:
        return
    try:
        channel = interaction.client.get_channel(interaction.channel_id)
        if channel:
            msg = await channel.fetch_message(msg_id)
            embed = service.get_status_embed()
            await msg.edit(embed=embed)
    except Exception:
        pass


# ────────────────────────────────────────────
#  Cog
# ────────────────────────────────────────────

class RollCallCommands(commands.Cog):
    """幽靈點名管理"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.service = RollCallService(bot)

    async def cog_load(self):
        # 註冊 persistent views
        self.bot.add_view(RollCallResponseView())
        self.bot.add_view(RollCallAdminView())
        logger.info("已註冊 RollCall persistent views")

        # 啟動背景排程
        await self.service.start()

    async def cog_unload(self):
        await self.service.stop()

    @app_commands.command(
        name="rollcall_panel",
        description="發送幽靈點名管理面板（管理員限定）",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def send_admin_panel(self, interaction: discord.Interaction):
        """在當前頻道發送管理面板"""
        # 刪除舊面板
        old_msg_id = self.service.runtime.admin_panel_message_id
        if old_msg_id:
            try:
                old_msg = await interaction.channel.fetch_message(old_msg_id)
                await old_msg.delete()
            except Exception:
                pass

        embed = self.service.get_status_embed()
        view = RollCallAdminView(self.service)

        await interaction.response.send_message(
            embed=embed, view=view
        )
        msg = await interaction.original_response()
        self.service.runtime.admin_panel_message_id = msg.id
        self.service.runtime.channel_id = interaction.channel_id
        self.service.runtime.save()


async def setup(bot: commands.Bot):
    await bot.add_cog(RollCallCommands(bot))
