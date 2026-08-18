"""
幽靈點名服務
定期抽選指定身份組成員進行活躍確認，逾期未回覆則踢除。
"""
import asyncio
from sys_settings.time_settings import APP_TZ
import json
import logging
import os
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set

import discord

from utils.dm_notifier import send_dm

logger = logging.getLogger('discord_bot')

RUNTIME_FILE = Path(__file__).parent.parent / "settings" / "rollcall_runtime.json"
# 點名回覆期限（天）
RESPONSE_DEADLINE_DAYS = 7
# 通過點名後的豁免期（天）
IMMUNITY_DAYS = 30
# 每次抽選人數
PICK_COUNT = 10
# 抽選時間（UTC+8 14:00）
PICK_HOUR_UTC8 = 14
# 抽選間隔（天）
PICK_INTERVAL_DAYS = 7
# 過期掃描間隔（秒）
EXPIRE_CHECK_INTERVAL = 6 * 3600  # 6 小時
# 踢除後重新加入的邀請連結
REJOIN_INVITE_URL = "https://discord.gg/wuwachatroom"



def _now_utc8() -> datetime:
    return datetime.now(APP_TZ)


class RollCallRuntime:
    """Runtime 狀態管理（JSON 持久化）"""

    def __init__(self):
        self.enabled: bool = False
        self.admin_panel_message_id: Optional[int] = None
        self.channel_id: Optional[int] = None
        # pending: {user_id_str: {message_id, roll_call_at, deadline}}
        self.pending: Dict[str, dict] = {}
        # immunity: {user_id_str: expire_iso}
        self.immunity: Dict[str, str] = {}
        self.stats: Dict[str, int] = {"total_kicked": 0, "total_passed": 0}
        # 上次自動點名日期（YYYY-MM-DD），防止重啟後同日重複點名
        self.last_rollcall_date: Optional[str] = None
        # 上次手動點名日期（YYYY-MM-DD），防止自動排程與手動同日重複
        self.last_manual_rollcall_date: Optional[str] = None
        self._load()

    # ── 持久化 ──

    def _load(self):
        if not RUNTIME_FILE.exists():
            return
        try:
            data = json.loads(RUNTIME_FILE.read_text(encoding="utf-8"))
            self.enabled = data.get("enabled", False)
            self.admin_panel_message_id = data.get("admin_panel_message_id")
            self.channel_id = data.get("channel_id")
            self.pending = data.get("pending", {})
            self.immunity = data.get("immunity", {})
            self.stats = data.get("stats", {"total_kicked": 0, "total_passed": 0})
            self.last_rollcall_date = data.get("last_rollcall_date")
            self.last_manual_rollcall_date = data.get("last_manual_rollcall_date")
        except Exception as e:
            logger.error(f"讀取 rollcall_runtime.json 失敗: {e}", exc_info=True)

    def save(self):
        try:
            os.makedirs(RUNTIME_FILE.parent, exist_ok=True)
            data = {
                "enabled": self.enabled,
                "admin_panel_message_id": self.admin_panel_message_id,
                "channel_id": self.channel_id,
                "pending": self.pending,
                "immunity": self.immunity,
                "stats": self.stats,
                "last_rollcall_date": self.last_rollcall_date,
                "last_manual_rollcall_date": self.last_manual_rollcall_date,
            }
            RUNTIME_FILE.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error(f"寫入 rollcall_runtime.json 失敗: {e}", exc_info=True)

    # ── 查詢 ──

    def is_pending(self, user_id: int) -> bool:
        return str(user_id) in self.pending

    def is_immune(self, user_id: int) -> bool:
        uid = str(user_id)
        expire_str = self.immunity.get(uid)
        if not expire_str:
            return False
        expire = datetime.fromisoformat(expire_str)
        if _now_utc8() >= expire:
            # 豁免已過期，清除
            del self.immunity[uid]
            self.save()
            return False
        return True

    def get_pending_list(self) -> List[dict]:
        """回傳 pending 清單，附帶 user_id int"""
        result = []
        for uid_str, info in self.pending.items():
            result.append({**info, "user_id": int(uid_str)})
        return result


class RollCallService:
    """幽靈點名核心邏輯"""

    def __init__(self, bot: discord.Client):
        self.bot = bot
        self.runtime = RollCallRuntime()
        self._tasks: List[asyncio.Task] = []

    # ── 生命周期 ──

    async def start(self):
        """啟動背景排程（每日抽選 + 過期掃描）"""
        if self._tasks:
            return
        self._tasks = [
            asyncio.create_task(self._weekly_pick_loop(), name="rollcall_weekly_pick"),
            asyncio.create_task(self._expire_check_loop(), name="rollcall_expire_check"),
        ]
        logger.info("幽靈點名服務已啟動背景排程")

    async def stop(self):
        for t in self._tasks:
            t.cancel()
        self._tasks.clear()

    # ── 背景排程 ──

    async def _weekly_pick_loop(self):
        """每週 UTC+8 14:00 自動抽選"""
        while True:
            try:
                now = _now_utc8()
                # 計算到下一次 14:00 的秒數
                target = now.replace(
                    hour=PICK_HOUR_UTC8, minute=0, second=0, microsecond=0
                )
                if now >= target:
                    target += timedelta(days=1)
                wait_seconds = (target - now).total_seconds()
                logger.info(
                    f"幽靈點名：下次檢查在 {target.isoformat()}（{wait_seconds:.0f} 秒後）"
                )
                await asyncio.sleep(wait_seconds)

                if self.runtime.enabled:
                    from datetime import date
                    today_str = _now_utc8().strftime("%Y-%m-%d")
                    today = date.fromisoformat(today_str)

                    # 今天已有手動點名，跳過自動排程
                    if self.runtime.last_manual_rollcall_date == today_str:
                        continue

                    # 檢查距離上次自動點名是否已過指定天數
                    last_date = self.runtime.last_rollcall_date
                    if last_date:
                        last = date.fromisoformat(last_date)
                        if (today - last).days < PICK_INTERVAL_DAYS:
                            continue
                    await self.do_roll_call()
                    self.runtime.last_rollcall_date = today_str
                    self.runtime.save()
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.error(f"幽靈點名每日排程錯誤: {e}", exc_info=True)
                await asyncio.sleep(300)

    async def _expire_check_loop(self):
        """定期掃描逾期未回覆的成員（啟動時等 bot ready 後立即掃一次）"""
        try:
            await self.bot.wait_until_ready()
            if self.runtime.enabled:
                await self.check_expired()
        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.error(f"幽靈點名啟動掃描錯誤: {e}", exc_info=True)

        while True:
            try:
                await asyncio.sleep(EXPIRE_CHECK_INTERVAL)
                if self.runtime.enabled:
                    await self.check_expired()
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.error(f"幽靈點名過期掃描錯誤: {e}", exc_info=True)
                await asyncio.sleep(300)

    # ── 核心邏輯 ──

    def _get_config(self) -> dict:
        """讀取 config.json 取得 rollcall 設定"""
        try:
            with open("config.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _get_target_role_ids(self) -> List[int]:
        config = self._get_config()
        return config.get("rollcall_target_role_ids", [])

    def _get_exclude_role_ids(self) -> List[int]:
        config = self._get_config()
        return config.get("rollcall_exclude_role_ids", [])

    def _get_channel_id(self) -> Optional[int]:
        config = self._get_config()
        return config.get("rollcall_channel_id")

    async def do_roll_call(self, count: int = PICK_COUNT, *, manual: bool = False) -> List[discord.Member]:
        """執行一次點名抽選，回傳被抽中的成員列表"""
        # 抽選新成員前，先清理上一輪逾期未回覆者，避免他們因仍在 pending 而被排除
        try:
            await self.check_expired()
        except Exception as e:
            logger.error(f"幽靈點名：抽選前過期掃描失敗: {e}", exc_info=True)

        channel_id = self._get_channel_id()
        if not channel_id:
            logger.warning("幽靈點名：未設定 rollcall_channel_id，跳過")
            return []

        channel = self.bot.get_channel(channel_id)
        if not channel:
            logger.warning(f"幽靈點名：找不到頻道 {channel_id}")
            return []

        guild = channel.guild
        target_role_ids = self._get_target_role_ids()
        if not target_role_ids:
            logger.warning("幽靈點名：未設定 rollcall_target_role_ids，跳過")
            return []

        exclude_role_ids = self._get_exclude_role_ids()

        # 收集符合資格的成員（從 API 拉取完整成員資料）
        members = [m async for m in guild.fetch_members(limit=None)]
        candidates = self._collect_candidates_from_list(members, target_role_ids, exclude_role_ids)
        if not candidates:
            logger.info("幽靈點名：沒有符合資格的成員可抽選")
            return []

        # 隨機抽選
        picked = random.sample(candidates, min(count, len(candidates)))
        now = _now_utc8()
        deadline = now + timedelta(days=RESPONSE_DEADLINE_DAYS)

        # 逐一發送點名訊息
        sent_members = []
        for member in picked:
            try:
                msg = await self._send_rollcall_message(channel, member, deadline)
                self.runtime.pending[str(member.id)] = {
                    "message_id": msg.id,
                    "roll_call_at": now.isoformat(),
                    "deadline": deadline.isoformat(),
                }
                sent_members.append(member)
            except Exception as e:
                logger.error(
                    f"幽靈點名：發送點名訊息給 {member} 失敗: {e}", exc_info=True
                )

        if manual:
            self.runtime.last_manual_rollcall_date = _now_utc8().strftime("%Y-%m-%d")
        self.runtime.save()
        logger.info(f"幽靈點名：已抽選 {len(sent_members)} 人（{'手動' if manual else '自動'}）")
        return sent_members

    def _collect_candidates_from_list(
        self, members: List[discord.Member], target_role_ids: List[int],
        exclude_role_ids: Optional[List[int]] = None,
    ) -> List[discord.Member]:
        """收集符合抽選資格的成員"""
        target_roles: Set[int] = set(target_role_ids)
        exclude_roles: Set[int] = set(exclude_role_ids or [])
        candidates = []
        for member in members:
            # 排除 Bot
            if member.bot:
                continue
            # 排除管理員
            if member.guild_permissions.administrator:
                continue
            # 必須擁有至少一個目標身份組
            if not any(r.id in target_roles for r in member.roles):
                continue
            # 排除擁有排除身份組的成員
            if exclude_roles and any(r.id in exclude_roles for r in member.roles):
                continue
            # 排除已在 pending 中的
            if self.runtime.is_pending(member.id):
                continue
            # 排除豁免期內的
            if self.runtime.is_immune(member.id):
                continue
            candidates.append(member)
        return candidates

    async def _send_rollcall_message(
        self, channel: discord.abc.Messageable, member: discord.Member, deadline: datetime
    ) -> discord.Message:
        """發送點名訊息（embed + 按鈕）"""
        # 這裡只建立 embed，View 由 Cog 層提供
        embed = discord.Embed(
            title="📋 點名確認",
            description=(
                f"{member.mention} 你好！這是定期活躍確認。\n"
                f"請在 **7 天內**點擊下方按鈕回覆。\n\n"
                f"截止時間：{deadline.strftime('%Y-%m-%d %H:%M')} (UTC+8)"
            ),
            color=discord.Color.orange(),
            timestamp=deadline,
        )
        embed.set_footer(text="逾期未回覆將被移出伺服器")

        from commands.rollcall_commands import RollCallResponseView
        view = RollCallResponseView(self, member.id)
        msg = await channel.send(
            content=member.mention,
            embed=embed,
            view=view,
        )
        return msg

    async def handle_response(self, user_id: int, interaction: discord.Interaction):
        """處理使用者按下「我是活人」按鈕"""
        uid = str(user_id)
        if uid not in self.runtime.pending:
            await interaction.response.send_message(
                "你目前沒有待回覆的點名。", ephemeral=True
            )
            return

        # 移除 pending，加入豁免
        del self.runtime.pending[uid]
        immunity_expire = _now_utc8() + timedelta(days=IMMUNITY_DAYS)
        self.runtime.immunity[uid] = immunity_expire.isoformat()
        self.runtime.stats["total_passed"] = self.runtime.stats.get("total_passed", 0) + 1
        self.runtime.save()

        await interaction.response.send_message(
            f"✅ 確認完成！你已通過點名，下次點名豁免至 {immunity_expire.strftime('%Y-%m-%d')}。",
            ephemeral=True,
        )

        # 更新原始訊息
        try:
            embed = interaction.message.embeds[0] if interaction.message.embeds else None
            if embed:
                embed.color = discord.Color.green()
                embed.description = f"{interaction.user.mention} 已確認活躍 ✅"
                embed.set_footer(text=f"回覆於 {_now_utc8().strftime('%Y-%m-%d %H:%M')}")
            await interaction.message.edit(embed=embed, view=None)
        except Exception as e:
            logger.error(f"幽靈點名：更新點名訊息失敗: {e}", exc_info=True)

        logger.info(f"幽靈點名：{interaction.user}（{user_id}）已回覆點名")

    async def check_expired(self):
        """掃描逾期未回覆的成員，執行踢除"""
        now = _now_utc8()
        expired_uids = []

        for uid_str, info in list(self.runtime.pending.items()):
            deadline = datetime.fromisoformat(info["deadline"])
            if now >= deadline:
                expired_uids.append(uid_str)

        if not expired_uids:
            return

        channel_id = self._get_channel_id()
        channel = self.bot.get_channel(channel_id) if channel_id else None
        guild = channel.guild if channel else None

        # guild 不可用時保留 pending，下次掃描重試（避免靜默丟失資料）
        if not guild:
            logger.warning(
                f"幽靈點名：{len(expired_uids)} 人逾期但 guild 不可用，保留 pending 等下次重試"
            )
            return

        for uid_str in expired_uids:
            info = self.runtime.pending.get(uid_str, {})
            user_id = int(uid_str)

            # 用 fetch_member 確認成員是否真的不在伺服器（避免 cache miss 誤刪）
            try:
                member = await guild.fetch_member(user_id)
            except discord.NotFound:
                self.runtime.pending.pop(uid_str, None)
                logger.info(f"幽靈點名：成員 {user_id} 已不在伺服器，移除 pending")
                continue
            except Exception as e:
                logger.error(
                    f"幽靈點名：取得成員 {user_id} 失敗，保留 pending：{e}", exc_info=True
                )
                continue

            # 踢出前先 DM 通知（踢後 bot 就 DM 不到了），失敗不影響 kick
            dm_text = (
                "👻 幽靈點名通知\n\n"
                f"由於連續 {RESPONSE_DEADLINE_DAYS} 天未回覆活躍確認點名，我們已將您移出伺服器。\n\n"
                "若您仍希望加入我們的社群，歡迎透過以下邀請連結重新申請：\n"
                f"{REJOIN_INVITE_URL}\n\n"
                "我們會再次進行審核，也誠摯希望您回來後能多與大家交流互動，謝謝！"
            )
            await send_dm(member, content=dm_text)

            try:
                await guild.kick(
                    member,
                    reason=f"幽靈點名：逾期 {RESPONSE_DEADLINE_DAYS} 天未回覆",
                )
                self.runtime.pending.pop(uid_str, None)
                self.runtime.stats["total_kicked"] = (
                    self.runtime.stats.get("total_kicked", 0) + 1
                )
                logger.info(f"幽靈點名：已踢除 {member}（{user_id}），逾期未回覆")

                # 更新原始點名訊息
                if channel and info.get("message_id"):
                    try:
                        msg = await channel.fetch_message(info["message_id"])
                        embed = msg.embeds[0] if msg.embeds else None
                        if embed:
                            embed.color = discord.Color.red()
                            embed.description = (
                                f"~~{member.mention}~~ 逾期未回覆，已被移出伺服器 ❌"
                            )
                            embed.set_footer(
                                text=f"踢除於 {now.strftime('%Y-%m-%d %H:%M')}"
                            )
                        await msg.edit(embed=embed, view=None)
                    except Exception:
                        pass

                # 發送踢除通知
                if channel:
                    await channel.send(
                        embed=discord.Embed(
                            description=(
                                f"👻 **{member.display_name}**（{member}）"
                                f"逾期 {RESPONSE_DEADLINE_DAYS} 天未回覆點名，已被移出伺服器。"
                            ),
                            color=discord.Color.red(),
                        )
                    )
            except discord.Forbidden:
                logger.error(f"幽靈點名：權限不足，無法踢除 {member}（{user_id}）")
            except Exception as e:
                logger.error(f"幽靈點名：踢除 {member}（{user_id}）失敗: {e}", exc_info=True)

        self.runtime.save()

    # ── 管理面板用 ──

    def get_status_embed(self) -> discord.Embed:
        """產生管理面板的狀態 embed"""
        status_icon = "🟢 已啟用" if self.runtime.enabled else "🔴 已停用"

        # 取得目標身份組名稱
        role_ids = self._get_target_role_ids()
        role_text = ", ".join(f"<@&{rid}>" for rid in role_ids) if role_ids else "未設定"

        # 取得排除身份組名稱
        exclude_ids = self._get_exclude_role_ids()
        exclude_text = ", ".join(f"<@&{rid}>" for rid in exclude_ids) if exclude_ids else "無"

        pending_count = len(self.runtime.pending)
        immune_count = sum(
            1 for exp in self.runtime.immunity.values()
            if _now_utc8() < datetime.fromisoformat(exp)
        )

        embed = discord.Embed(
            title="👻 幽靈點名系統",
            color=discord.Color.green() if self.runtime.enabled else discord.Color.greyple(),
        )
        embed.add_field(name="狀態", value=status_icon, inline=True)
        embed.add_field(name="目標身份組", value=role_text, inline=True)
        embed.add_field(name="排除身份組", value=exclude_text, inline=True)
        embed.add_field(name="每週抽選", value=f"{PICK_COUNT} 人", inline=True)
        embed.add_field(name="待回覆", value=f"{pending_count} 人", inline=True)
        embed.add_field(name="豁免中", value=f"{immune_count} 人", inline=True)
        embed.add_field(
            name="累計踢除",
            value=f"{self.runtime.stats.get('total_kicked', 0)} 人",
            inline=True,
        )
        embed.add_field(
            name="累計通過",
            value=f"{self.runtime.stats.get('total_passed', 0)} 人",
            inline=True,
        )
        embed.set_footer(
            text=f"回覆期限 {RESPONSE_DEADLINE_DAYS} 天 ｜ 豁免期 {IMMUNITY_DAYS} 天 ｜ 每 {PICK_INTERVAL_DAYS} 天抽選一次 {PICK_HOUR_UTC8}:00 (UTC+8)"
        )
        return embed
