"""prompt 裡分辨人的錨點：「名字#user_id 尾碼」。

**對照靠錨點，不靠名字**：同一個人在聊天行、人物卡、名字對照裡都掛同一個尾碼；群友會改名、也有
同名的人，模型認人靠的是尾碼。完整 user_id 不進 prompt（降敏、省 token，長串數字也容易被模型抄錯）。

**預設 4 碼，撞號的人自動加長**：128 人用 4 碼約 56% 會出現至少一組撞號，撞了模型會把兩個人當成
同一個。`refresh()` 用成員名單找出誰跟誰撞，只有撞號的人改用分得開的最短長度；沒撞號的人永遠是
4 碼，名單更新不會讓其他人的錨點變動。錨點每次組 prompt 時現算、不存檔（2026-10-01 查證：人物
資料與 agent 版本 0 筆含錨點；只有插話紀錄的情境快照有，那裡只當背景引用、不拿來對人），所以
加長不會讓舊資料對不上。

加長過的人不縮回（見 `refresh`）。重啟前就離開伺服器的人不在名單裡，一律 4 碼；他跟現有成員
撞號時，`chat_line` 組 prompt 時會警告。
"""
from __future__ import annotations

import logging
from typing import Any, Iterable

logger = logging.getLogger(__name__)

MIN_DIGITS = 4

#: 撞號的人 → 要用幾碼。只放撞號的人：沒撞號的一律 MIN_DIGITS。整份換掉（不原地改），
#: executor 執行緒讀到的永遠是完整的一份
_extended: dict[str, int] = {}


def refresh(member_ids: Iterable[Any]) -> None:
    """用目前的成員名單重算撞號名單。啟動與成員加入／離開時呼叫。

    **加長過的人不縮回**：撞號的兩人有一人離開，他的舊訊息還在聊天歷史裡；留下的人縮回 4 碼的話，
    兩人又變成同一個錨點。所以上一份名單裡加長過的人照樣算進來（重啟後這份記憶就沒了，那時
    由 `chat_line` 的撞號警告兜底）。
    """
    global _extended
    groups: dict[str, list[str]] = {}
    for uid in {str(i) for i in member_ids} | set(_extended):
        if len(uid) >= MIN_DIGITS:
            groups.setdefault(uid[-MIN_DIGITS:], []).append(uid)
    extended: dict[str, int] = {}
    for same in groups.values():
        if len(same) < 2:
            continue
        digits = MIN_DIGITS
        while len({u[-digits:] for u in same}) < len(same) and digits < max(map(len, same)):
            digits += 1
        extended.update(dict.fromkeys(same, digits))
    if extended != _extended:
        logger.info("人名錨點撞號名單更新：%s",
                    {u: u[-n:] for u, n in sorted(extended.items())} or "（無撞號）")
    _extended = extended


def suffix(user_id: Any) -> str:
    """錨點的數字部分（不含 #）；user_id 太短時回空字串。"""
    uid = str(user_id or "")
    if len(uid) < MIN_DIGITS:
        return ""
    return uid[-_extended.get(uid, MIN_DIGITS):]


def label(name: str, user_id: Any) -> str:
    """「名字#尾碼」；沒有可用的尾碼時只回名字。"""
    tail = suffix(user_id)
    return f"{name}#{tail}" if tail else name
