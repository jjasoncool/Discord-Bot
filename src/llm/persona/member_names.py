"""群友的名字：Discord 上的名字、自介與印象裡的暱稱，以及 prompt 裡的「名字對照」。

**為什麼要合起來看**：同一個人在群裡有好幾個叫法——Discord 顯示名稱（就是伺服器暱稱，沒設才是
全域名稱）、另一個 Discord 名稱、自介「別人常常叫我什麼」、印象「你平常怎麼稱呼他」。實測糯糯的
伺服器暱稱是「糯糯 弗糯糯」、全域名稱是「一野shout死你」，群裡叫他一野；柔柔喵的「阿喵」只在
自介與印象裡有。只看其中一處，模型就會把叫人的名字當成口頭禪，或對不到是誰。

**主名字一律用 Discord 顯示名稱**，其他名字放「名字對照」（`name_map_lines`），用同一個
`#尾碼`（`llm.preprocess.person_anchor`）掛在一起。Discord 名字每次從 bot 的成員快取讀——改名時
Discord 會推送、快取自動更新，不另存資料庫。帳號名在聊天畫面上看不到，不收。
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Mapping, Optional

from llm.preprocess import person_anchor

#: 自介暱稱欄、印象稱呼欄裡分隔多個暱稱的符號（「柔喵, 阿喵」）。不含空白——顯示名稱本身常有空白
_NICKNAME_SEP = re.compile(r"[,，、/／;；|｜]+")
#: 名字頭尾的符號與表情（「❤️柔柔喵❤️-時渺」的開頭）
_EDGE = re.compile(r"^\W+|\W+$")
NAME_MAP_HEADER = "【名字對照】（同一個 #尾碼 就是同一個人；左邊是 Discord 顯示名稱）"


def member_names_from_guild(guild: Any) -> dict[str, list[str]]:
    """Discord 上每個成員的名字：author_id → [顯示名稱, 伺服器暱稱, 全域名稱]（去重、去空）。
    第一個一定是顯示名稱。bot 不收。"""
    out: dict[str, list[str]] = {}
    for m in getattr(guild, "members", None) or []:
        if getattr(m, "bot", False):   # bot 不是被聊的群友；不收，找人時才不會對到 bot 自己
            continue
        names = [n for n in (m.display_name, m.nick, m.global_name) if n]
        out[str(m.id)] = list(dict.fromkeys(names))
    return out


def merge_names(discord_names: Iterable[str], listed: Iterable[str] = ()) -> list[str]:
    """合併名字：Discord 名字整個保留，自介、印象欄位拆開（「柔喵, 阿喵」）；去空、去重，保留順序。

    Discord 名字不能拆：顯示名稱本身常帶「/」（實測「Biboolater-只剩我沒6命愛彌斯/緋雪/心了」），
    拆了會多出「緋雪」「心了」這種不是名字的東西。
    """
    names: list[str] = []
    pieces = [*discord_names, *(p for value in listed for p in _NICKNAME_SEP.split(value or ""))]
    for name in pieces:
        name = (name or "").strip()
        if name and name not in names:
            names.append(name)
    return names


def name_parts(names: Iterable[str]) -> frozenset[str]:
    """名字整個與用空白分開的每一段（去掉頭尾符號、至少 2 字），拿來比對「這個詞是不是在叫某個群友」。

    **只用空白分段**：顯示名稱常用符號裝飾，照符號拆會拆出不是名字的詞——實測
    「Biboolater-只剩我沒6命愛彌斯/緋雪/心了」會拆出「緋雪」（遊戲角色），問「緋雪什麼時候復刻」就被
    當成在講他。頭尾符號去掉，「❤️柔柔喵❤️-時渺」的開頭才比得到「柔柔喵」。單字不收——「喵」這種字
    到處都是。
    """
    parts: set[str] = set()
    for name in names:
        for piece in [name or "", *(name or "").split()]:
            piece = _EDGE.sub("", piece)
            if len(piece) >= 2:
                parts.add(piece)
    return frozenset(parts)


def _script(ch: str) -> str:
    """字元屬於哪一類：漢字／假名／韓文、其他文字與數字、符號（含空白、表情）。"""
    code = ord(ch)
    if (0x3040 <= code <= 0x30FF or 0x3400 <= code <= 0x9FFF or 0xAC00 <= code <= 0xD7AF
            or 0xF900 <= code <= 0xFAFF):
        return "cjk"
    return "word" if ch.isalnum() else "other"


def _boundary(text: str, i: int) -> bool:
    """`text[i-1]` 與 `text[i]` 之間是不是詞的邊界：頭尾、旁邊是符號，或換了一類文字。"""
    if i <= 0 or i >= len(text):
        return True
    left, right = _script(text[i - 1]), _script(text[i])
    return "other" in (left, right) or left != right


def names_member(word: str, parts: Iterable[str], *, allow_longer: bool = False) -> bool:
    """這個詞是不是在叫某個群友。名字的一段等於這個詞，或以這個詞開頭、而且開頭到此是一個詞
    （「一野shout死你」的「一野」後面換成英文；「沒有傘的孩子」的「沒有」後面還是中文，不算）。

    `allow_longer`：詞比名字長也算——中文名字在詞裡任何位置都算（「肥糯糯」含「糯糯」），英文名字
    要整個字（「or」不算出現在「sorry」裡）。描述裡引號括起來的詞短而明確，可以開；問句切出來的詞
    很雜（整句也是候選），開了常見詞會對到名字剛好是它的人。單字一律不算。

    為什麼要看邊界：獨立複查拿 3,408 則真實訊息試，沒看邊界時 54 則對到人、大多是誤中——
    「沒有」→「阿夢 - 沒有傘的孩子」、「丹瑾」（遊戲角色）→「丹瑾偶遇全息…」、「su」→ super。
    """
    word = word.lower()
    if len(word) < 2:
        return False
    for p in (p.lower() for p in parts):
        if p == word or (p.startswith(word) and _boundary(p, len(word))):
            return True
        if allow_longer and len(p) >= 2:
            start = word.find(p)
            while start >= 0:
                if all(_script(c) == "cjk" for c in p) or (
                        _boundary(word, start) and _boundary(word, start + len(p))):
                    return True
                start = word.find(p, start + 1)
    return False


def match_members(member_names: Mapping[str, list[str]], candidates: Iterable[str]) -> list[str]:
    """問句裡的詞對得到哪些成員的 Discord 名字（「一野最近在幹嘛」→ 糯糯）。規則見 `names_member`。"""
    # 問句的候選詞已轉小寫（`persona_card_builder.normalize_alias_text`），`names_member` 比小寫
    words = list(dict.fromkeys(candidates))
    hits: list[str] = []
    for uid, names in member_names.items():
        parts = name_parts(names)
        if any(names_member(w, parts) for w in words):
            hits.append(uid)
    return hits


def name_map_lines(
    guild_id: int,
    person_ids: Iterable[Any],
    member_names: Mapping[str, list[str]],
    *,
    profile_store: Any = None,
) -> list[str]:
    """這次 prompt 裡出現的人的「名字對照」：只列有其他名字的人；沒有就回空串列。

    自介與印象的暱稱查一次資料庫（同步，呼叫端丟 executor）；查不到時只用 Discord 名字。
    """
    ids = list(dict.fromkeys(str(p) for p in person_ids if p))
    if not ids:
        return []
    if profile_store is None:
        from llm.storage.member_profile_store import get_member_profile_store
        profile_store = get_member_profile_store()
    try:
        aliases = profile_store.aliases_for_users(guild_id=guild_id, user_ids=ids)
    except Exception:
        aliases = {}
    lines: list[str] = []
    for uid in ids:
        discord_names = member_names.get(uid, [])
        names = merge_names(discord_names, aliases.get(uid, []))
        if not names:
            continue
        label = discord_names[0] if discord_names else names[0]
        others = [n for n in names if n != label]
        if others:
            lines.append(f"- {person_anchor.label(label, uid)} 也叫：{'、'.join(others)}")
    return [NAME_MAP_HEADER, *lines] if lines else []


def display_names(member_names: Optional[Mapping[str, list[str]]]) -> dict[str, str]:
    """`member_names_from_guild` 的結果 → author_id → 顯示名稱。"""
    return {uid: names[0] for uid, names in (member_names or {}).items() if names}
