"""被點名惡意辱罵時的應對：不回文字、按一個嘲諷表情，之後幾天不主動接這個人的話。

是不是在罵它由模型判斷（關鍵字分不出敵意和玩笑）：被點名本來就要跑一次模型，在那次生成多給它
一個選項——真的在惡意辱罵它就整則輸出 `[INSULT]`（規則寫在 `ambient_reply_prompt.txt` 的「被 @ 或被回覆時」）。
看得到前後文，分得出真的有敵意和朋友間的虧。這是保護機制（開玩笑不要太容易觸發，明顯敵意才算）：單純叫它閉嘴、嫌吵、帶笑的虧都照常回；「閉嘴啦 腦殘AI」這種帶著敵意的羞辱才算。

為什麼不回：罵人的人要的是反應。原本被點名一定回，每罵一次就換到一則回覆、一筆互動紀錄；
回嗆的話，嗆人的回覆一被按笑就會被當成範例。
為什麼記住這個人：2026-10-03～10-07 的五次都是「它先主動接了對方的話 → 對方兩分鐘內回覆罵它」，
罵完它回「好，不說了」、隔天照接。記仇期間對方點名，照樣回、但帶著心情（冷淡一點）。
群主不記仇（群主和它的關係不一樣）：表情照按，但不進名單、不標被罵的那則。

開關：`settings/switches.json` 的 `ambient_insult_mode`。off 時標記照樣不送出去（等於不回），
只是不按表情、不記名單——prompt 裡的規則不跟著開關，要整個拿掉就改 prompt。
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import discord

from llm.storage.ai_interactions_store import mark_insulted, recent_insults, record_insult
from sys_settings import switches
from sys_settings.llm_settings import AmbientChatSettings
from sys_settings.time_settings import APP_TZ
from utils.discord_members import bot_owner_id

logger = logging.getLogger(__name__)

_SETTINGS = AmbientChatSettings()

#: 模型判定「被惡意辱罵」時輸出的標記 `[INSULT]`。用英文跟 `[PASS]` 一樣，不會漂成簡體；大小寫與全形、各種括號
#: 都寬鬆比對（`[PASS]` 漂成 `[Pass]` 外洩過，理由同 `_is_silence`）。
_MARKER_RE = re.compile(r"[\[［(（【〔「]\s*insult\s*[\]］)）】〕」]", re.IGNORECASE)
#: 去掉這些之後只剩「insult」＝整則就是標記（含忘了打括號的裸寫法）
_MARKER_NOISE_RE = re.compile(r"[\s\[\]［］()（）【】〔〕「」`。．.!！]")
_FALLBACK_EMOJI = "🙄"


def enabled() -> bool:
    return switches.current().ambient_insult_mode == "on"


def is_marker(reply: str) -> bool:
    """模型的回答整則就是「被惡意辱罵」的標記——只有這樣才按表情、記仇。"""
    return _MARKER_NOISE_RE.sub("", reply or "").lower() == "insult"


def mentions_marker(reply: str) -> bool:
    """回答裡夾著標記（例：「[INSULT] 你自己查」）：模型拿不定主意。不送出（標記不能外洩），
    但也不按表情、不記仇——保護機制門檻要高，拿不準就不算。"""
    return bool(_MARKER_RE.search(reply or ""))


@dataclass(frozen=True)
class Grudge:
    """它對某人還沒消的氣：`insult_cold_days` 天內最後一次被他點名罵的時間、一共幾次。"""
    last_at: datetime
    times: int


async def grudges(guild_id: int) -> dict[int, Grudge]:
    """最近罵過它的人（`insult_cold_days` 天內，再罵就從那天重算）。開關沒開時是空的。

    名單上的人它不主動接話；他點名時照回，但 prompt 帶上心情（`mood_note`）。
    """
    if not enabled():
        return {}
    rows = await asyncio.to_thread(recent_insults, str(guild_id), _SETTINGS.insult_cold_days)
    owner = bot_owner_id()   # 群主不記仇；寫入端已擋，這裡再擋一次，手動回補的資料也不會讓群主被冷落
    return {int(author): Grudge(last_at=ts, times=n) for author, (ts, n) in rows.items() if int(author) != owner}


def mood_note(grudge: Grudge, now: datetime) -> str:
    """記仇中的人點名它時，疊在 system prompt 最後的事實；怎麼回由插話 prompt 的規則決定。

    只放時間與次數，不放對方罵的原話也不放名字：這段在 system prompt（可信區），原話和名字都是
    群友打的字，放進來等於讓人寫 7 天份的系統指令。只在點名的就是這個人時才帶，所以不需要名字。
    """
    days = (now.astimezone(APP_TZ).date() - grudge.last_at.astimezone(APP_TZ).date()).days
    when = "今天" if days <= 0 else ("昨天" if days == 1 else f"{days} 天前")
    times = f"，這 {_SETTINGS.insult_cold_days} 天內一共 {grudge.times} 次" if grudge.times > 1 else ""
    return f"【你的心情】這次點名你的人，{when}罵過你{times}。你還沒消氣。"


def _pick_emoji(guild: Optional[discord.Guild]):
    """設定的本伺服器自訂表情；找不到或不能用（伺服器掉等級）時用 🙄。"""
    if guild is not None:
        emoji = discord.utils.get(guild.emojis, name=_SETTINGS.insult_reaction_emoji)
        if emoji is not None and getattr(emoji, "available", True):
            return emoji
    return _FALLBACK_EMOJI


async def respond(message: discord.Message, *, insulted_reply_id: Optional[str]) -> None:
    """按嘲諷表情、記下是誰罵的；被罵的那則插話記成「不受歡迎」（不算有人接、不當範例）。

    不寫互動紀錄。best-effort：任何一步失敗都只記 log。
    """
    try:
        await message.add_reaction(_pick_emoji(message.guild))
    except discord.HTTPException as exc:
        logger.info("ambient 被罵：按表情失敗 message=%s：%s", message.id, exc)
    if message.author.id == bot_owner_id():
        logger.info("ambient 被群主罵 channel=%s：按表情，不記仇", message.channel.id)
        return
    await asyncio.to_thread(
        record_insult,
        guild_id=str(message.guild.id),
        channel_id=str(message.channel.id),
        author_id=str(message.author.id),
        message_id=str(message.id),
        text=(message.content or "")[:300],
        replied_to_message_id=insulted_reply_id,
    )
    if insulted_reply_id:
        await asyncio.to_thread(mark_insulted, insulted_reply_id)
    logger.info(
        "ambient 被罵 channel=%s author=%s：按表情、不回；被罵的那則=%s，%d 天內不主動接他的話",
        message.channel.id, message.author.id, insulted_reply_id or "無", _SETTINGS.insult_cold_days,
    )
