"""Discord 的人與權限：取伺服器成員（快取沒有再問 API）、找能收訊息的對象、誰是群主、指令與按鈕的權限檢查。

架構定位：基礎層（utils）裡的 Discord 工具（登記在 `test_layering.DISCORD_HELPERS_IN_BASE`），只依賴 discord.py 與
  `utils.utils`（安全回覆、config.json 的位置）。
  上層：各指令模組（權限檢查）、交易與商品（身分組、顯示暱稱）、關鍵字清單、賣家清單、論壇貼文擁有者、私訊通知、插話的被罵應對（群主 id）。
  下層：discord.py 的快取與 REST；`config.json` 的 `role_mapping`。

介面：
- `resolve_member(guild, user_id)`：先查成員快取、沒有再 `fetch_member`；不在伺服器（已離開）、沒權限、其他 HTTP 錯誤都回 None。
- `resolve_user(bot, user_id, guild=)`：先當成員找（上面那支），不是成員再查 bot 的使用者快取、最後 `fetch_user`；都沒有回 None。
- `bot_owner_id()`：群主的使用者 id（環境變數 `OWNER_ID`；沒設是 0，誰都不是）。
- `check_role(user, required_role)`：使用者有沒有 `config.json` `role_mapping` 裡那個身分組；群主自動通過。
- `check_guild(interaction, owner_only=, admin_only=, required_role=, permission=)`：指令與按鈕的權限檢查，不通過時自己回
  只有本人看得到的訊息。全專案的管理員限制都走它（守衛擋 `has_permissions`：它擋下時回英文錯誤還記一筆 ERROR）。

規則：
- 全專案取成員只走這裡（守衛擋自己 `guild.fetch_member`）：快取偶爾拿不到人（接單曾因此失敗），快取沒有不等於不在伺服器，
  一定要再問一次 API。點名刻意只用 API（快取漏人會把還在的人誤判成離開而踢掉），是合理例外。

例外與決策：
- 快取優先而不是 API 優先：bot 開著 members intent，成員改暱稱、離開都會經 gateway 事件更新快取，資料不會舊；
  快取命中就省兩次 API，沒命中走的 API 和 API 優先一樣。
"""
from __future__ import annotations

import json
import logging
import os

import discord

from utils.utils import CONFIG_FILE, safe_send_interaction_message

logger = logging.getLogger(__name__)


async def resolve_member(guild, user_id) -> discord.Member | None:
    """伺服器成員：先查快取、沒有再向 API 查；不在、沒權限、出錯都回 None。"""
    if guild is None or not user_id:
        return None
    member = guild.get_member(int(user_id))
    if member is not None:
        return member
    try:
        return await guild.fetch_member(int(user_id))
    except discord.NotFound:
        logger.warning("成員 %s 不在伺服器（可能已離開）", user_id)
    except discord.Forbidden:
        logger.warning("沒有權限查成員 %s", user_id)
    except discord.HTTPException as exc:
        logger.warning("向 API 查成員 %s 失敗：%s", user_id, exc)
    return None


async def resolve_user(bot, user_id: int, *, guild: discord.Guild = None):
    """任何能收訊息的對象（Member 或 User）：先當伺服器成員找，不是成員才退到 bot 的使用者快取與 API。"""
    user = await resolve_member(guild, user_id)
    if user is None:
        user = bot.get_user(user_id)
    if user is None:
        try:
            user = await bot.fetch_user(user_id)
        except (discord.NotFound, discord.Forbidden):
            pass
        except discord.HTTPException as exc:
            logger.warning("fetch_user 錯誤，ID: %s：%s", user_id, exc)

    if user is None:
        logger.warning("所有方法均無法取得使用者，ID: %s", user_id)
    return user


def bot_owner_id() -> int:
    """擁有者（群主）的 Discord 使用者 ID：環境變數 `OWNER_ID`；沒設是 0，誰都不是擁有者。"""
    return int(os.getenv('OWNER_ID', '0'))


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
        owner_id = bot_owner_id()
        if user.id == owner_id:
            logger.info(f'使用者 {user.name} 是 owner，自動通過角色權限檢查')
            return True
        config_file = CONFIG_FILE
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
        owner_id = bot_owner_id()
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
        owner_id = bot_owner_id()
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
