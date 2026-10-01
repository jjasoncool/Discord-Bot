"""M7：把 agent 的描述挑成「精簡版」，寫進 `auto_personality` 給插話／askai 讀。

**為什麼不直接給全文**：agent 的描述幾乎只增不減（drop 很少），常常比插話那一行的上限
（`AmbientChatSettings.persona_line_max_chars`）還長。直接給全文會被切在句子中間，而且是
照位置切——越新加的條目排在越後面、越先被切掉，跟重不重要無關。精簡版改成**程式挑整條**，
不經 LLM、原文一字不改：

  1. 門檻：證據跨 ≥2 次對話（相隔 >30 分鐘算另一次）。擋掉「一次當成習慣」——
     例如「北側」在那個人全部發言裡只出現過 1 次，卻被寫成「會用…」。
  2. 基本個性：最多用一半預算，證據跨度 ≥14 天的，跨度越長越優先。
  3. 近況：剩下的預算，其餘條目（含沒排進上一段的基本個性）依對話次數由多到少，次數
     相同再依最後一次有佐證的時間（last_seen）由新到舊——所以基本個性用不完的空間自然
     讓給近況，反之亦然。
  4. 放不下的整條跳過，不切半句；文字一模一樣的只放一次。輸出時基本個性在前、近況在後。
     唯一的改動是拿掉句尾的「。」——串接後會變成「。；」。

**挑之前先擋群內流行語**（純規則，擋下的不佔預算）：同一個詞在 ≥`GROUP_SLANG_MIN_PEOPLE`
個人的描述裡都被寫成「他的口頭禪」，那是大家都在講的詞，不是誰的特色（實測「484」寫在 3 個人
身上）。群友的暱稱不算——那是在叫人，歸 ④ 的暱稱表處理；講貼圖的條目也不算。

**隱私不在這裡擋**：健康、性向、感情家庭、政治、具體行程只靠 `persona_description_rules.txt`
要 ③④ 別寫；住哪裡、宗教、財務、職業不限制。發言本來就是群裡公開講的，管理員認為舊條目留著
沒差（2026-10-01 決定），不另做關鍵字過濾。

**預算＝一行的上限扣掉標籤、自介與印象**：插話那一行是「「標籤」— 自介。印象。AI觀察」，
AI觀察排最後、最先被切。bot 讀取時撈到哪幾則印象、什麼順序都會變（SQL 撈新到舊、語意檢索
可能撈到任何一則），所以拿最長的幾則把每種排列都算一遍取最壞的。標籤也會變：有撈到自介時是
自介的別名，沒撈到時是所有別名裡排最前的那個——所以一律照「可能出現的最長別名」算。標籤算好
之後，撈得少（沒撈到自介、印象不到 3 則）只會少一段文字，不用另外列舉。
另留 `BUDGET_MARGIN` 字。這樣算出的預算，發布當下這一行不會超過上限（印象超過
`_IMPRESSION_POOL` 則時靠那份餘裕，不是嚴格保證），/askai 的卡片欄位也不會被切；白天有人新增
自介／印象時可能超過，要等下一晚重算——那時插話的截斷會切在最後一個「；」或「。」，
不切半句（`ambient_reply._rag_to_persona_lines`）。

**誰歸 ⑤、誰歸 ③**：發布開啟時，精簡版不是空的人由 ⑤ 寫，③ 與手動萃取跳過他們
（`production_skip_list`），不然會把精簡版蓋回 production 的描述。名單每次重算、跟 ⑤ 用同一套
計算（`build_plans`），不看「誰被發布過」——精簡版後來變空的人（例如自介變長、預算放不下任何
一條）才會回到 ③ 手上，不會兩邊都不更新。名單在 ③ 之前算，當晚 ④ 的新版本要下一晚才反映，
所以這種人最多多留一天舊的描述（之前的精簡版；從沒發布過的人則是前一晚 production 的描述）。

**寫入時記的萃取時間是當下**：啟動補跑看 `last_extracted_at` 的最大值
（`personality_extractor.get_last_extraction_time`）。發布開啟後 ③ 會跳過大部分的人，沿用
舊時間的話，補跑檢查會以為很久沒萃取、每次重啟都補跑。代價：③ 把 LLM 錯誤吞掉、正常回傳
空結果的那晚（④ 通常也一起失敗），⑤ 照樣記下當下時間，當天重啟就不會補跑。③ 丟例外時整個
維護會中止、⑤ 不會跑，不受影響。
"""
from __future__ import annotations

import itertools
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable, Literal, Mapping, Optional

from llm.persona.agent import tools as agent_tools
from sys_settings.time_settings import APP_TZ

logger = logging.getLogger(__name__)

#: 至少跨幾次對話才有資格被挑。1→2 是「一次當習慣」與「重複出現」的分界。
MIN_EPISODES = 2
#: 兩則證據相隔超過這麼久，算不同次對話。實測 10 分、30 分、2 小時、6 小時結果幾乎不變。
EPISODE_GAP_SECONDS = 30 * 60
#: 證據跨度達到幾天算「基本個性」。agent 預設看 7 天，14 天＝隔週以後還被佐證。
STABLE_SPAN_DAYS = 14
#: 基本個性最多佔預算的比例；用不完的讓給近況。
CORE_SHARE = 0.5
#: 模型改寫時留下的標記，不是描述（例：「…形容被煩到（近期未見）」）。
#: 「不再是…」不在此列——那種句子通常還帶著現況（「近期主玩魔獸世界…不再是主力」）。
_RESIDUE = re.compile(r"[（(](?:移除|近期未見)[）)]")
#: 串接條目用的分隔符，跟 `agent.compose_persona_text` 一致。
_SEP = "；"
#: 預算再扣掉的字數，留給列舉量不到的變動：印象超過 `_IMPRESSION_POOL` 則時沒算到的挑法
#: （標籤另外照最長的別名算，不靠這份餘裕）。
BUDGET_MARGIN = 20
#: 算最壞情況時考慮幾則印象（清理後最長的幾則）。卡片最多放 3 則，6 則取 3 則的排列是 120 種。
_IMPRESSION_POOL = 6

#: 同一個口頭禪出現在幾個人身上，就當群內流行語
GROUP_SLANG_MIN_PEOPLE = 2
_CLAIMS_CATCHPHRASE = re.compile(r"口頭禪|語尾|口癖|慣用語|固定用語|語氣詞")
_MENTIONS_STICKER = re.compile(r"貼圖|表情")
_QUOTED = re.compile(r"「([^「」]{1,12})」")
#: 自介暱稱欄、印象稱呼欄裡分隔多個暱稱的符號（「柔喵, 阿喵」）。不含空白——顯示名稱本身常有空白
_NICKNAME_SEP = re.compile(r"[,，、/／;；|｜]+")

Mode = Literal["off", "dry_run", "on"]

Section = Literal["core", "recent"]


@dataclass(frozen=True)
class LiteItem:
    """一條被挑中的條目與挑中它的依據（試算時印出來給人檢查）。"""

    n: int
    text: str
    episodes: int
    span_days: int
    last_seen: datetime
    section: Section


@dataclass
class LiteResult:
    text: str
    items: list[LiteItem] = field(default_factory=list)
    #: 過門檻的條目數，文字相同的算一條（被挑中的一定是其中一部分）
    eligible: int = 0
    #: 過門檻但被當成群內流行語擋下的條目原文
    withheld: list[str] = field(default_factory=list)


def _episodes(times: list[datetime]) -> int:
    count, last = 0, None
    for t in sorted(times):
        if last is None or (t - last).total_seconds() > EPISODE_GAP_SECONDS:
            count += 1
        last = t
    return count


def _evidence_times(change: dict[str, Any], now: datetime) -> list[datetime]:
    """證據的發送時間（從 snowflake 解，不查 DB）。解不出來或在未來的不算。"""
    ids = change.get("evidence_msg_ids")
    if not isinstance(ids, list):
        return []
    return [t for t in (agent_tools._snowflake_time(i) for i in ids) if t is not None and t <= now]


def _catchphrase_terms(text: str) -> set[str]:
    """這條把哪些詞寫成口頭禪（講貼圖的條目不算——貼圖名稱大家都用同一套）。"""
    if not _CLAIMS_CATCHPHRASE.search(text) or _MENTIONS_STICKER.search(text):
        return set()
    return {t.strip() for t in _QUOTED.findall(text) if t.strip()}


def find_group_slang(changes_by_author: Mapping[str, Any], nicknames: Iterable[str]) -> frozenset[str]:
    """被 ≥`GROUP_SLANG_MIN_PEOPLE` 個人的描述寫成口頭禪的詞。看每人最新版本的全部條目
    （不只過門檻的）——流行語判斷要看「多少人被這樣寫」，跟這條會不會被挑中無關。"""
    names = {n.strip() for n in nicknames if n and n.strip()}
    people: dict[str, set[str]] = {}
    for author_id, changes in changes_by_author.items():
        for item in agent_tools._persona_items(changes):
            for term in _catchphrase_terms(item["text"]) - names:
                people.setdefault(term, set()).add(str(author_id))
    return frozenset(t for t, who in people.items() if len(who) >= GROUP_SLANG_MIN_PEOPLE)


def select_lite(
    changes: Any,
    budget: int,
    *,
    now: Optional[datetime] = None,
    group_slang: frozenset[str] = frozenset(),
) -> LiteResult:
    """從一版 `changes` 挑出精簡版，總長不超過 `budget` 字。"""
    now = now or datetime.now(APP_TZ)
    raw = changes if isinstance(changes, list) else []
    candidates: list[LiteItem] = []
    withheld: list[str] = []
    for item in agent_tools._persona_items(raw):
        if _RESIDUE.search(item["text"]):
            continue
        times = _evidence_times(raw[item["n"] - 1], now)
        episodes = _episodes(times)
        if episodes < MIN_EPISODES:
            continue
        if _catchphrase_terms(item["text"]) & group_slang:
            withheld.append(item["text"])
            continue
        span = (max(times) - min(times)).days
        candidates.append(LiteItem(
            n=item["n"], text=item["text"].rstrip("。"), episodes=episodes, span_days=span,
            last_seen=max(times), section="core" if span >= STABLE_SPAN_DAYS else "recent",
        ))

    picked: list[LiteItem] = []
    used = 0

    def take(pool: Iterable[LiteItem], limit: int) -> None:
        nonlocal used
        for c in pool:
            # 文字一模一樣的也只放一次：舊版驗證沒擋住「兩條 keep 指到同一項」，版本裡留下了
            # 兩條相同的條目，之後編號不同、驗證也擋不到。留下的是排序在前的那一份
            if any(p.n == c.n or p.text == c.text for p in picked):
                continue
            cost = len(c.text) + (len(_SEP) if picked else 0)
            if used + cost <= limit:
                picked.append(c)
                used += cost

    def by_span(c: LiteItem) -> tuple:
        return (-c.span_days, c.n)

    def by_weight(c: LiteItem) -> tuple:
        # 對話次數多的先：門檻本身就是「重複出現才算數」，越常出現越能代表這個人。只看
        # 最後佐證時間的話，同一天差幾分鐘就決定誰進得去——實測一條 9 次對話的特徵被
        # 晚幾分鐘、字數多的條目擠掉。次數相同才比時間
        return (-c.episodes, -c.last_seen.timestamp(), c.n)

    take(sorted((c for c in candidates if c.section == "core"), key=by_span),
         int(budget * CORE_SHARE))
    take(sorted(candidates, key=by_weight), budget)

    # 近況段內也照挑選的順序：插話截斷時從尾巴切，先丟次數少的（基本個性整段排在前面，
    # 包括第二輪才挑進來的）
    ordered = (sorted((p for p in picked if p.section == "core"), key=by_span)
               + sorted((p for p in picked if p.section == "recent"), key=by_weight))
    return LiteResult(text=_SEP.join(p.text for p in ordered), items=ordered,
                      eligible=len({c.text for c in candidates}), withheld=withheld)


# ── 預算：插話那一行扣掉自介與印象，剩多少給 AI觀察 ──────────────────────────
def _auto_doc(alias: str, personality: str, metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "metadata": {**metadata, "profile_kind": "auto_personality"},
        "source": "sql_identity",
        "text": f"[Auto Personality]\nalias: {alias or '-'}\npersonality: {personality}",
    }


def line_budget(
    *,
    person_docs: list[dict[str, Any]],
    alias: str,
    auto_metadata: dict[str, Any],
    line_max_chars: int,
    card_field_chars: int,
    label_max_chars: int = 0,
) -> int:
    """這個人的 AI觀察 最多能放幾個字，才不會被插話或 /askai 截斷。

    直接用 bot 讀取時的同一套函式（`build_persona_cards`＋`format_persona_cards_for_context`）
    組一次這一行，量出 AI觀察 以外佔了多少——自己重算格式的話，兩邊一分岔就會算錯。
    `person_docs` 放自介與印象，順序就是 bot 讀到的順序；最壞情況由呼叫端列舉（`plan_for`）。
    `label_max_chars`：標籤可能的最長長度；這一行的標籤比它短時，照它算。
    """
    from llm.persona.persona_card_builder import (
        build_persona_cards,
        format_persona_cards_for_context,
        persona_card_label,
    )

    probe = "Ｘ"   # 一個字的佔位，量完扣掉
    docs = [*person_docs, _auto_doc(alias, probe, auto_metadata)]
    cards = build_persona_cards(
        docs=docs, requester_user_id=None, participant_user_ids=[],
        intent="general", alias_hints=[], max_cards=1,
    )
    lines = [c["content"] for c in format_persona_cards_for_context(cards)
             if c.get("metadata") != "persona_card_header"]
    if not lines:
        return 0
    line = " ".join(lines[0].split())      # 插話讀取時也是這樣正規化空白
    label = " ".join(persona_card_label(cards[0]).split())
    by_line = line_max_chars - (len(line) - len(probe)) - max(0, label_max_chars - len(label))
    # /askai 則是卡片欄位本身（含 "[Auto Personality] alias: … personality: " 前綴）有上限
    raw = " ".join(_auto_doc(alias, probe, auto_metadata)["text"].split())
    by_field = card_field_chars - (len(raw) - len(probe))
    return max(0, min(by_line, by_field))


# ── 讀資料（同步 DB，呼叫端丟 executor）─────────────────────────────────────
_PROFILE_KINDS = ("intro_profile", "impression", "auto_personality")


def load_guild_state(guild_id: int) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, list]]]:
    """回傳 `(每人 agent 最新版本, 每人的 profile 文件)`。

    profile 文件依人分組：自介與 auto_personality 看 `author_id`，印象看 `target_user_id`
    （跟 `build_persona_cards` 的分組規則一樣）。各類都是新到舊。
    """
    from sys_settings.llm_settings import LLMServiceSettings

    versions: dict[str, dict[str, Any]] = {}
    persons: dict[str, dict[str, list]] = {}
    with LLMServiceSettings().pgvector_cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (author_id) author_id, version, changes
            FROM persona_agent_versions
            WHERE guild_id = %s
            ORDER BY author_id, version DESC
            """,
            (str(guild_id),),
        )
        for author_id, version, changes in cur.fetchall():
            versions[str(author_id)] = {"version": version, "changes": changes or []}
        cur.execute(
            f"""
            SELECT metadata_, text FROM {agent_tools._profile_table()}
            WHERE metadata_->>'guild_id' = %s AND metadata_->>'profile_kind' = ANY(%s)
            ORDER BY id DESC
            """,
            (str(guild_id), list(_PROFILE_KINDS)),
        )
        for md, text in cur.fetchall():
            md = md or {}
            kind = str(md.get("profile_kind") or "")
            pid = str(md.get("target_user_id" if kind == "impression" else "author_id") or "")
            if not pid:
                continue
            persons.setdefault(pid, {k: [] for k in _PROFILE_KINDS})[kind].append(
                {"metadata": md, "source": "sql_identity", "text": text or ""}
            )
    return versions, persons


def member_nicknames(
    persons: Mapping[str, Mapping[str, list]],
    display_names: Optional[Mapping[str, str]] = None,
) -> dict[str, tuple[str, list[str]]]:
    """群友的暱稱：author_id → (顯示名稱, [暱稱…])，只列有暱稱的人。

    來源是成員自己填的自介「別人常常叫我什麼」，與別人寫的印象「你平常怎麼稱呼他」——群裡
    叫的「阿喵」「阿狗」不是顯示名稱，只有這兩處有。顯示名稱優先用當下的，沒有就用上次發布時
    記下的別名。純函式，`persons` 是 `load_guild_state` 的第二個回傳值。
    """
    names = display_names or {}
    out: dict[str, tuple[str, list[str]]] = {}
    for pid, docs in persons.items():
        raw = [str(d.get("metadata", {}).get("alias") or "") for d in docs.get("intro_profile", [])]
        raw += [str(d.get("metadata", {}).get("target_alias") or "") for d in docs.get("impression", [])]
        nicks: list[str] = []
        for value in raw:
            for nick in _NICKNAME_SEP.split(value):
                nick = nick.strip()
                if nick and nick not in nicks:
                    nicks.append(nick)
        autos = docs.get("auto_personality", [])
        label = str(names.get(pid) or (autos[0].get("metadata", {}).get("alias") if autos else "") or "")
        nicks = [n for n in nicks if n != label]
        if nicks:
            out[str(pid)] = (label or nicks[0], nicks)
    return out


def split_uncovered(
    results: dict[str, dict[str, Any]], covered: set[str]
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """手動萃取的結果分成「照寫」與「跳過」。回傳 `(照寫, 跳過的人的別名)`。

    `covered` 是 `production_skip_list` 的結果：手動萃取照寫的話會把精簡版蓋回 production
    的描述，直到下一晚 ⑤ 才換回來。
    """
    kept = {uid: data for uid, data in results.items() if str(uid) not in covered}
    skipped = [str(data.get("alias") or uid) for uid, data in results.items() if str(uid) in covered]
    return kept, skipped


@dataclass
class PublishPlan:
    author_id: str
    version: int
    alias: str
    budget: int
    lite: LiteResult


def plan_for(
    author_id: str,
    version_row: dict[str, Any],
    person: dict[str, list],
    *,
    line_max_chars: int,
    card_field_chars: int,
    display_name: str = "",
    now: Optional[datetime] = None,
    group_slang: frozenset[str] = frozenset(),
) -> PublishPlan:
    """一個人要發布什麼（純函式，不碰 DB）。`group_slang` 由 `build_plans` 跨人算好傳進來。"""
    from llm.persona.persona_card_builder import _clean_impression_text, persona_card_label

    person = person or {}
    autos = person.get("auto_personality", [])
    existing_md = dict(autos[0]["metadata"]) if autos else {}
    # 別名以當下的顯示名稱為準：發布開啟後 ③ 不再寫這個人，沿用文件裡的舊別名就永遠不會更新
    alias = str(display_name or existing_md.get("alias") or "")
    intros = person.get("intro_profile", [])[:1]
    # bot 讀取時撈到哪幾則（語意檢索可能撈到任何一則）、什麼順序都可能變：拿清理後最長的
    # 幾則，每種排列都算一遍取最壞的。撈得少只會少一段文字——會因此變長的只有標籤，下面另外算
    pool = sorted(
        person.get("impression", []),
        key=lambda d: len(_clean_impression_text(" ".join(str(d.get("text") or "").split()))),
        reverse=True,
    )[:_IMPRESSION_POOL]
    variants = list(itertools.permutations(pool, min(3, len(pool))))   # 沒有印象時是 [()]
    # 標籤可能是任何一個別名（沒撈到自介時取所有別名裡排最前的那個），照最長的算——含列舉
    # 範圍外的印象
    aliases = {alias.strip(), ""} | {
        str(d.get("metadata", {}).get("alias") or d.get("metadata", {}).get("target_alias") or "").strip()
        for d in [*intros, *person.get("impression", [])]
    }
    label_max = max(len(" ".join(persona_card_label({"alias": a, "person_id": author_id}).split()))
                    for a in aliases)
    auto_md = {"author_id": author_id, "alias": alias, "guild_id": existing_md.get("guild_id", "")}
    budget = min(
        line_budget(person_docs=[*intros, *v], alias=alias, auto_metadata=auto_md,
                    line_max_chars=line_max_chars, card_field_chars=card_field_chars,
                    label_max_chars=label_max)
        for v in variants
    )
    budget = max(0, budget - BUDGET_MARGIN)
    return PublishPlan(
        author_id=author_id, version=int(version_row["version"]), alias=alias, budget=budget,
        lite=select_lite(version_row["changes"], budget, now=now, group_slang=group_slang),
    )


def build_plans(
    guild_id: int,
    *,
    display_names: Optional[Mapping[str, str]] = None,
    now: Optional[datetime] = None,
) -> tuple[dict[str, PublishPlan], dict[str, Exception]]:
    """每個有 agent 版本的人要發布什麼。回傳 `(計畫, 算失敗的人與例外)`。

    同步（讀 DB），呼叫端丟 executor。⑤ 與 `production_skip_list` 共用這一份，兩邊才會一致。
    """
    from llm.persona.persona_card_builder import PERSONA_MAX_CARD_CHARS
    from sys_settings.llm_settings import AmbientChatSettings

    line_max = AmbientChatSettings().persona_line_max_chars
    versions, persons = load_guild_state(guild_id)
    names = display_names or {}
    known_names = [n for label, nicks in member_nicknames(persons, names).values() for n in (label, *nicks)]
    group_slang = find_group_slang({a: row["changes"] for a, row in versions.items()}, known_names)
    plans: dict[str, PublishPlan] = {}
    failed: dict[str, Exception] = {}
    for author_id, row in versions.items():
        try:
            plans[author_id] = plan_for(
                author_id, row, persons.get(author_id, {}),
                line_max_chars=line_max, card_field_chars=PERSONA_MAX_CARD_CHARS,
                display_name=names.get(author_id, ""), now=now, group_slang=group_slang,
            )
        except Exception as exc:
            failed[author_id] = exc
    return plans, failed


def effective_publish_mode() -> Mode:
    """實際生效的發布模式：`PersonaAgentSettings.publish_mode`，但 ④ 關掉時一律當 off。

    ④ 不跑就不會有新版本，發布只會一直寫同一份舊的精簡版，而 ③ 又跳過這些人——兩邊都不更新。
    """
    from sys_settings.llm_settings import PersonaAgentSettings

    settings = PersonaAgentSettings()
    return settings.publish_mode if settings.enabled else "off"


async def production_skip_list(
    guild_id: int, *, display_names: Optional[Mapping[str, str]] = None
) -> set[str]:
    """③ 與手動萃取寫入時要跳過的人：發布開啟時，⑤ 會寫精簡版的人；沒開啟時是空的。

    讀 DB 失敗會丟例外，由呼叫端決定怎麼處理（③ 照常全寫、手動萃取這次不寫）。
    算失敗的人不跳過——⑤ 也寫不了他們，交給 ③。
    """
    if effective_publish_mode() != "on":
        return set()
    from llm.persona.agent.agent import run_db

    plans, _ = await run_db(build_plans, guild_id, display_names=display_names)
    return {author_id for author_id, plan in plans.items() if plan.lite.text}


# ── 發布（04:00 排程的第 ⑤ 步）──────────────────────────────────────────────
async def run_publish(
    *,
    guild_id: int,
    mode: Mode,
    display_names: Optional[Mapping[str, str]] = None,
    profile_store: Any = None,
) -> dict[str, int]:
    """把每個有 agent 版本的人的精簡版寫進 `auto_personality`（或只試算）。

    - `off`：什麼都不做
    - `dry_run`：算出來、寫 log，不寫入——上線前先看挑出來的東西對不對
    - `on`：寫入；精簡版是空的人不動，③ 照常更新他們（見 `production_skip_list`）

    不依賴當晚 ④ 有沒有跑：發布的是每個人**最新的**版本，當晚沒輪到的人也照樣發布。
    `display_names` 是 author_id → 當下的顯示名稱，用來更新別名。
    """
    if mode == "off":
        return {"skipped": 1}
    from llm.persona.agent.agent import run_db

    plans, failed = await run_db(build_plans, guild_id, display_names=display_names)
    stats = {"people": len(plans) + len(failed), "written": 0, "dry_run": 0, "empty": 0,
             "failed": len(failed)}
    for author_id, exc in failed.items():
        logger.error("persona 精簡版計算失敗 author=%s：%s", author_id, exc, exc_info=exc)
    if mode == "on" and profile_store is None:
        from llm.storage.member_profile_store import get_member_profile_store
        profile_store = get_member_profile_store()

    for author_id, plan in plans.items():
        lite = plan.lite
        core = sum(1 for i in lite.items if i.section == "core")
        logger.info(
            "persona 精簡版%s author=%s v%d 預算 %d → %d 條 %d 字（基本 %d／近況 %d，過門檻 %d 條）：%s",
            "試算" if mode == "dry_run" else "", author_id, plan.version, plan.budget,
            len(lite.items), len(lite.text), core, len(lite.items) - core, lite.eligible,
            lite.text[:200] or "（空，不寫入，交給 ③）",
        )
        for text in lite.withheld:
            logger.info("persona 精簡版擋下群內流行語 author=%s：%s", author_id, text[:120])
        if not lite.text:
            stats["empty"] += 1
            continue
        if mode == "dry_run":
            stats["dry_run"] += 1
            continue
        try:
            ok = await profile_store.index_auto_personality(
                guild_id=guild_id, author_id=int(author_id), alias=plan.alias,
                personality=lite.text,
                extra_metadata={"written_by": "persona_agent", "agent_version": str(plan.version)},
            )
        except Exception as exc:
            ok = False
            logger.error("persona 精簡版寫入失敗 author=%s：%s", author_id, exc, exc_info=True)
        # 寫入函式自己會吞例外、回傳成功與否；照回傳值計，失敗才不會被算成成功
        stats["written" if ok else "failed"] += 1
    logger.info("persona 精簡版發布結束（mode=%s）：%s", mode, stats)
    return stats
