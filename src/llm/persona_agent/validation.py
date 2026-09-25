"""驗證層：**把 LLM 輸出當成不可信輸入**。

schema 只保證形狀對，內容真偽要靠這裡。三道關卡各自對應一次真實觀察到的失敗：

  ① **evidence 反查**——實測一次 26 個證據裡有 1 個是編的，而且夾在兩個真的中間、
     格式完全合理、前 10 位數字都對，**肉眼百分之百看不出來**。這是最有效的過濾器。
  ② **語意空殼**——strict schema 完全放行 `text=""` + `evidence=[]` 的 add 項
     （空字串也是字串、空陣列也是陣列）。不擋的話版本表會被塞進一堆合法但無意義的紀錄。
  ③ **confidence 不能當放行條件**——那次編造 ID 的執行自己標的是 `high`。
     confidence 只用來判斷「資料不足、整筆不寫版本」，不用來判斷單項可信度。

**逐項處理而非整筆丟棄**：原規格寫「整筆丟棄」，但實測那筆 7 項裡有 6 項完全正確，
只有 1 項引用了假 ID。整筆丟掉等於為了一顆老鼠屎倒掉一鍋粥，而且會讓「資料不足」
與「有幻覺」兩種完全不同的狀況在統計上混為一談。
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional, Sequence

from llm.persona_agent import tools
from sys_settings.pgvector_settings import HYBRID_RETRIEVAL_SETTINGS

logger = logging.getLogger("discord_bot")

VALID_TYPES = {"add", "revise", "keep", "drop"}
VALID_CONFIDENCE = {"low", "medium", "high"}

#: 沿用 tools 的型別，不另外定義一份（同一個東西兩個名字就是分岔的起點）
FetchFn = tools.FetchFn


@dataclass
class ValidationResult:
    """驗證結果。`accepted` 才進版本表，其餘都是要記進 runs 表的統計。"""

    accepted: list[dict[str, Any]] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    #: 宣稱的證據數（drop 附的不算）／其中查無此筆或不屬於本人的數量
    evidence_claimed: int = 0
    evidence_bogus: int = 0
    #: 整筆不寫版本的原因（None 代表可以寫）
    skip_reason: Optional[str] = None
    #: 描述裡「」引號內的字串，在自己列的證據訊息裡找不到的個數。
    #: **只記錄不擋**——見 `_unmatched_quotes` 的說明。
    #: `None` 代表本次沒算（證據反查失敗，語料拿不到），與 0 意義不同。
    quote_unmatched: Optional[int] = 0
    quote_misses: list[str] = field(default_factory=list)
    #: 上一版每個編號有沒有被交代（keep／revise／drop 擇一、恰好一次），以及有交代
    #: 卻被退件而實際消失的編號（`lost`，不寫新版本時為空）。沒交代、指錯編號都**只記錄
    #: 不擋**——先跑幾晚看遵守率再決定要不要強制；重複交代則會處理成只採一筆（見
    #: `_one_change_per_ref`），編號照樣記在 `duplicated`，被取代的那幾筆連同原因記在
    #: `superseded`。`None`＝本次沒有可對照的上一版：第一次跑（基準
    #: 是 production 的散文，沒有編號）、讀上一版失敗、或 diff 在逐項驗證前就被拒絕
    #: （結構不合法、user_id 不符）。
    ref_accounting: Optional[dict[str, list[Any]]] = None

    @property
    def hallucination_rate(self) -> float:
        """幻覺率＝假證據 / 宣稱證據。runs 表記這個數字才調得動 prompt。"""
        if not self.evidence_claimed:
            return 0.0
        return round(self.evidence_bogus / self.evidence_claimed, 4)


def _real_evidence(
    fetch: FetchFn, *, user_id: str, ids: Sequence[str]
) -> Optional[dict[str, str]]:
    """回傳這批 msg_id 中**真實存在且屬於該使用者**的那些 → 訊息原文。

    兩個條件缺一不可：ID 存在但屬於別人，等於拿別人的話當這個人的證據。

    **順便把 text 撈回來**：引號比對（`_unmatched_quotes`）需要原文，而它要的正是
    這批 id。分兩次查等於同樣的 WHERE 跑兩遍。
    """
    if not ids:
        return {}
    table = HYBRID_RETRIEVAL_SETTINGS.chat_table()
    sql = f"""
        SELECT metadata_->>'message_id', text
        FROM {table}
        WHERE metadata_->>'doc_type' = 'discord_chat'
          AND metadata_->>'author_id' = %s
          AND metadata_->>'message_id' = ANY(%s)
    """
    try:
        rows = fetch(sql, (str(user_id), list(dict.fromkeys(ids))))
    except Exception as exc:
        # 查不了就不能宣稱「證據是假的」——寧可放行也不要冤枉，但要留 log
        logger.error("evidence 反查失敗（本次不做證據過濾）：%s", exc, exc_info=True)
        # None 代表「這次沒查成」，與「查成了但原文是空的」必須分得開：
        # 前者要連引號比對一起跳過，否則語料全空會讓每個引號都算沒命中，
        # 把 quote_unmatched 灌到最大值，而 evidence_bogus 又因為放行而是 0——
        # 資料上看起來就是「證據乾淨但引文全是編的」，剛好相反。
        return None
    return {r[0]: (r[1] or "") for r in rows if r and r[0]}


#: 引號內容拆分用：模型常用「／」「/」合併兩種說法、用「…」省略中段。
_QUOTE_SPLIT = re.compile(r"[／/…]|\.\.\.")
#: 全形／半形標點差異會讓字面比對失準，比對前一律抹掉。
_PUNCT = re.compile(r"[，,。．、；;：:！!？?~～\s]+")
#: 串接多則證據原文時的分隔符。**不能用空白**——`_norm` 會把空白抹掉，
#: 「前一則結尾＋後一則開頭」就會拼出原本不存在的字串，變成假命中。
#: 也不能用 `\x1f` 這類控制字元：Python 的 `\s` 連 `\x1c`~`\x1f` 一起吃。
#: 用私有使用區的碼位，聊天內容不可能出現，也不會被 `_PUNCT` 掃掉。
_JOIN = "\ue000"


def _norm(text: str) -> str:
    return _PUNCT.sub("", text)


def _unmatched_quotes(change_text: str, corpus: str) -> list[str]:
    """回傳描述裡「」內、在證據原文中找不到的片段。

    **這是警示不是過濾器**——實測兩晚 118 個引號片段，裸比對有 27 個對不上，
    其中約半數是冤枉的：`「第一件事」「第二件事」` 是模型在分段不是引用、
    `「拒絕/不要」` 對應的是 `:不要、拒絕:` 只是順序不同。拿來退件會砍掉正確的
    描述，比放行錯誤的更糟，所以只計數、進 runs 表當人工複查的排序鍵。

    降低冤枉的三條規則（都是實測看出來的，不是預想的）：
      - 「／」「/」「…」拆開，任一段命中就算數（模型愛用它們合併多種說法）
      - 標點與全半形差異抹掉再比
      - 2 字以下跳過——「肥」這種必然命中，沒有鑑別力

    表情與貼圖不需要特別處理：DB 的 text 欄位存的是渲染後的 `:生氣:`／
    `[貼圖：jinhsi_cry]`，模型寫「生氣」直接就是子字串。
    """
    hay = _norm(corpus)
    misses: list[str] = []
    for raw in re.findall(r"「([^」]{1,40})」", change_text or ""):
        parts = [_norm(p) for p in _QUOTE_SPLIT.split(raw)]
        parts = [p for p in parts if len(p) > 2]
        if not parts:
            continue  # 全是短詞，沒有鑑別力
        if not any(p in hay for p in parts):
            misses.append(raw)
    return misses


def _ref(change: dict[str, Any]) -> int:
    try:
        return int(change.get("ref") or 0)
    except (TypeError, ValueError):
        return 0


def _is_anchored_keep(change: dict[str, Any], base: Optional[set[int]]) -> bool:
    """指到上一版真實項目的 keep：文字、trait、證據都由程式沿用，不是模型今晚寫的。"""
    return (
        base is not None
        and str(change.get("type") or "") == "keep"
        and _ref(change) in base
    )


def _shape_problem(change: dict[str, Any], *, anchored: bool = False) -> Optional[str]:
    """形狀與語意檢查。回傳問題描述，沒問題回 None。

    `anchored`＝這是指到上一版真實項目的 keep。它的文字、trait、證據都由程式沿用
    （`agent.resolve_keeps`／`agent.inherit_keep_evidence`），模型只需要說「這項不動」。
    """
    ctype = str(change.get("type") or "").strip()
    if ctype not in VALID_TYPES:
        return f"type 不合法：{ctype!r}"
    if ctype == "drop":
        # 刪除不描述任何人、也無法用訊息證明「某件事不再發生」——
        # 所以 text 與證據都可空，但**一定要說為什麼刪**，否則又回到無聲消失
        if not str(change.get("reason") or "").strip():
            return "drop 必須附 reason（為什麼刪）"
        return None
    if anchored:
        # **不再要求 keep 附本週的證據**。那條規則逼模型二選一，兩條路都是錯的：
        #   - 老實留空 → 被退件、項目無聲消失。09-24 有人 5 項這樣沒了，reason 寫的是
        #     「本週發言未出現…無反證亦無正證，保守保留」——模型的意思明明是保留。
        #     這類退件四晚從 0 → 3 → 6 → 15 在增加。
        #   - 從本週訊息湊幾則沾邊的 → 過關，但證據撐不住描述。「糯糯」那項的
        #     「糾正別人」原本有證據（09-01「這個糯糯不是 此糯糯」），每晚換證據後
        #     就只剩「我是肥糯糯」這種，評審判成「部分成立」算進幻覺，其實是真的。
        # 文字是 resolve_keeps 沿用的原文，所以只剩「空的」這一種壞法要擋。
        if not str(change.get("text") or "").strip():
            return "text 為空（keep 的原文沒有沿用成功）"
        return None
    if not str(change.get("trait") or "").strip():
        return "trait 為空"
    if not str(change.get("text") or "").strip():
        return "text 為空（strict schema 放行空字串，但空描述沒有意義）"
    if not str(change.get("reason") or "").strip():
        return "reason 為空"
    if not isinstance(change.get("evidence_msg_ids"), list):
        return "evidence_msg_ids 不是陣列"
    if not change["evidence_msg_ids"]:
        return "evidence_msg_ids 為空（無法稽核的描述等同無法採信）"
    return None


def _account_refs(changes: Any, base_refs: Iterable[int]) -> dict[str, list[int]]:
    """上一版的每個編號，有沒有被恰好交代一次。

    **為什麼要查**：模型不必用 drop 也能刪——只要不提那一項，那一項就消失了。
    實測米拉 v7→v8 從 51 項帶過來 31 項，20 項無聲消失，沒有任何紀錄說刪了什麼、
    為什麼刪；同時那 7 項「會用 X 形容 Y」的廢話卻被留下來。可稽核的 diff 唯獨
    「刪除」沒有紀錄，所以要求每一項都明確 keep／revise／drop。

    也順帶抓重複引用：09-22 那晚有一版「帶過來 28 項、上一版只有 27 項」，是兩個
    keep 指到同一項，那一項被複製了一次（這裡只記錄；只留一筆由 `_one_change_per_ref` 處理）。

    回傳 `unaccounted`（沒被提到＝無聲消失）、`duplicated`（被提到兩次以上）、
    `unknown`（指到上一版不存在的編號）。計的是模型的**意圖**：被驗證層退掉的
    keep 也算有交代，因為這裡量的是「模型有沒有照規則逐項處理」。**結果**另外算
    （`_lost_refs`）——只看這三項會以為沒有東西消失：09-24 帳面 25/26 人完整交代，
    實際卻有 20 項因為 keep 被退件而不見。
    """
    base = set(base_refs)
    seen: dict[int, int] = {}
    unknown: list[int] = []
    for c in changes if isinstance(changes, list) else []:
        if not isinstance(c, dict):
            continue
        if str(c.get("type") or "") not in {"keep", "revise", "drop"}:
            continue
        r = _ref(c)
        if r not in base:
            unknown.append(r)
            continue
        seen[r] = seen.get(r, 0) + 1
    return {
        "unaccounted": sorted(base - set(seen)),
        "duplicated": sorted(r for r, k in seen.items() if k > 1),
        "unknown": sorted(set(unknown)),
    }


_REF_TYPES = {"keep", "revise", "drop"}


#: 同一項被交代多次時採用哪一筆：revise 改了內容、keep 維持原樣、drop 刪除。
#: 衝突時寧可保留內容（revise > keep > drop）；同類型取第一筆。
_REF_PRIORITY = {"revise": 0, "keep": 1, "drop": 2}


def _one_change_per_ref(
    accepted: list[dict[str, Any]], base: set[int]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """上一版的每一項只採用一筆變更。回傳 `(採用, 被取代)`。

    `_account_refs` 只記錄重複、不處理，於是兩筆都會寫進新版本。09-25 的真實案例：
    同一人對第 6 項同時下了 keep 和 revise，新版本出現兩條幾乎一樣的描述——
    「會把 AI 工具往荒謬/低俗方向接梗自嘲」與「會把 AI 工具或遊戲角色商品往荒謬/
    低俗方向接梗自嘲」。bot 讀到的會是重複的內容。

    **落選的是 keep 時，它今晚附的證據併進勝出那筆**（keep 或 revise）：
      - 兩筆 keep 說的是同一句話，後面那筆常是模型在補證據。真實案例：有人對第 9 項下了
        兩次 keep，第二筆附了 09-20 的新發言、reason 寫「作為第9項的補充證據」——
        直接丟掉的話 `last_seen` 會停在 09-02。
      - revise 勝出時也要併：同一晚對同一項又 keep 又 revise，代表模型認為原句還成立，
        revise 是在補充。真實案例（米拉 v10 第 25 項）：revise 的新句引用「黑料一堆低能
        台V」，但 revise 自己附的證據撐不住；撐它的那則附在同一晚的 keep 上。
      - 只併**今晚已驗證**的 id，不併歷史；revise 為何不沿用歷史見 `agent.inherit_keep_evidence`。
        若哪天模型同一晚 keep 又推翻同一項，今晚 keep 附的幾則會併到推翻的新句底下——
        資料庫裡的 2 例都是補充，至今沒出現過，影響也只限今晚附的那幾則。

    被取代的每一筆（含併掉的 keep）連同原因一起回傳，呼叫端記在
    `ref_accounting["superseded"]`：它的 reason、`stripped_msg_ids` 才查得到。
    """
    winner: dict[int, int] = {}
    for idx, c in enumerate(accepted):
        ctype, r = str(c.get("type") or ""), _ref(c)
        if ctype in _REF_PRIORITY and r in base:
            cur = winner.get(r)
            if cur is None or _REF_PRIORITY[ctype] < _REF_PRIORITY[str(accepted[cur].get("type"))]:
                winner[r] = idx
    extra: dict[int, list[str]] = {}
    superseded: list[dict[str, Any]] = []
    losers: set[int] = set()
    for idx, c in enumerate(accepted):
        ctype, r = str(c.get("type") or ""), _ref(c)
        if ctype in _REF_PRIORITY and r in base and winner[r] != idx:
            losers.add(idx)
            chosen = str(accepted[winner[r]].get("type"))
            if ctype == "keep" and chosen in ("keep", "revise"):
                ids = c.get("evidence_msg_ids")
                moved = [str(i) for i in (ids if isinstance(ids, list) else [])]
                extra.setdefault(winner[r], []).extend(moved)
                superseded.append({
                    "change": c,
                    "why": (f"第 {r} 項重複交代，採用 {chosen}，這筆 keep 今晚附的 "
                            f"{len(moved)} 則證據併入" if moved else
                            f"第 {r} 項重複交代，採用 {chosen}，這筆 keep 沒有附證據"),
                })
            else:
                superseded.append({"change": c, "why": f"第 {r} 項重複交代，採用 {chosen}，這筆不寫入"})
    kept: list[dict[str, Any]] = []
    for idx, c in enumerate(accepted):
        if idx in losers:
            continue
        if idx in extra:
            ids = c.get("evidence_msg_ids")
            own = [str(i) for i in ids] if isinstance(ids, list) else []
            c = {**c, "evidence_msg_ids": list(dict.fromkeys(own + extra[idx]))}
        kept.append(c)
    return kept, superseded


def _lost_refs(result: ValidationResult, base_refs: Iterable[int]) -> list[int]:
    """有交代、卻因為驗證退件而實際消失的上一版編號。

    被退掉的 keep／revise 不會進版本表，舊的那一項也不會被帶過來——結果跟模型
    根本沒提到它一樣。被退掉的 drop 也算：項目一樣消失了，而且沒有留下刪除理由。
    """
    def refs(changes: Iterable[Any]) -> set[int]:
        return {
            _ref(c) for c in changes
            if isinstance(c, dict) and str(c.get("type") or "") in _REF_TYPES
        }

    rejected = refs(r.get("change") for r in result.rejected if isinstance(r, dict))
    return sorted((rejected & set(base_refs)) - refs(result.accepted))


def validate_diff(
    diff: dict[str, Any],
    *,
    user_id: str,
    fetch: FetchFn,
    base_refs: Optional[Iterable[int]] = None,
) -> ValidationResult:
    """逐項驗證 agent 產出的 diff。

    `fetch` 可注入，單元測試不必碰 DB。
    """
    result = ValidationResult()

    if not isinstance(diff, dict) or not isinstance(diff.get("changes"), list):
        result.skip_reason = "diff 結構不合法"
        return result

    if str(diff.get("user_id") or "") != str(user_id):
        # 拿 A 的資料寫成 B 的人格，比幻覺更嚴重
        result.skip_reason = (
            f"user_id 不符：diff 說 {diff.get('user_id')!r}、實際查的是 {user_id!r}"
        )
        return result

    claimed: list[str] = []
    for change in diff["changes"]:
        # drop 不需要證據，它附的 id 從來不會被判真假，所以不算進「宣稱的證據」——
        # 算進去的話，幻覺率的分母會多出一批不可能被算成假的 id
        if (isinstance(change, dict) and str(change.get("type") or "") != "drop"
                and isinstance(change.get("evidence_msg_ids"), list)):
            claimed.extend(str(i) for i in change["evidence_msg_ids"])
    result.evidence_claimed = len(claimed)
    found = _real_evidence(fetch, user_id=user_id, ids=claimed)
    # None＝反查失敗（fail-open）。id 檢查照舊全放行，但引號比對整個跳過，
    # 並讓 quote_unmatched 留 None，人工複查時才分得出「沒算」與「算了是 0」。
    lookup_failed = found is None
    real = {str(i): "" for i in claimed} if lookup_failed else found
    # 轉成 set：下面判斷 anchored 和最後的帳目都要用，傳進來的若是 generator 只能讀一次
    base = set(base_refs) if base_refs is not None else None

    for change in diff["changes"]:
        if not isinstance(change, dict):
            result.rejected.append({"change": change, "why": "不是物件"})
            continue
        anchored = _is_anchored_keep(change, base)
        problem = _shape_problem(change, anchored=anchored)
        if problem:
            result.rejected.append({"change": change, "why": problem})
            continue
        if str(change.get("type") or "") == "drop":
            # 刪除沒有描述要驗、也沒有證據要反查，形狀對就收
            result.accepted.append(change)
            continue
        raw_ids = change.get("evidence_msg_ids")
        ids = [str(i) for i in raw_ids] if isinstance(raw_ids, list) else []
        if anchored and lookup_failed:
            # 反查失敗時其他項目 fail-open，但 keep 不需要證據，沒驗過的 id 就不收：
            # 沿用的證據會經由歷史一直留下去，沒驗過的 id 一旦進來就再也清不掉
            change = {**change, "evidence_msg_ids": []}
            ids = []
        bogus = [i for i in ids if i not in real]
        if bogus:
            result.evidence_bogus += len(bogus)
            if not anchored:
                result.rejected.append({
                    "change": change,
                    "why": f"引用了不存在或不屬於本人的 msg_id：{bogus}",
                })
                continue
            # keep 只剔掉假的那幾個 id、項目留著：文字是上一版驗證過的原文，
            # 今晚多附的假 id 污染不到它。整項退掉的話，一個抄錯的 id
            # 就讓一項沒問題的描述無聲消失（09-24 有 5 項這樣沒了）。
            # 假 id 照樣算進 evidence_bogus；剔掉的是哪幾個記在該項的
            # `stripped_msg_ids`，稽核時查得到。不放進 `rejected`：那裡的每一筆
            # 都會被算成退件數，除錯指令也會把它顯示成「✗ 拒絕」。
            logger.info("keep 第 %s 項的新證據有假 id，已剔除、項目保留：%s",
                        _ref(change), bogus)
            change = {
                **change,
                "evidence_msg_ids": [i for i in ids if i in real],
                "stripped_msg_ids": bogus,
            }
        result.accepted.append(change)

    # 同一項被交代多次只採一筆。落選的不算退件（它沒有驗證失敗），記在
    # ref_accounting 的 superseded——退件數才維持「驗證失敗」這一個意思。
    superseded: list[dict[str, Any]] = []
    if base is not None:
        result.accepted, superseded = _one_change_per_ref(result.accepted, base)

    # 引號比對放在最後：被退掉、被取代的項目不會寫入，不必算、也不該算進統計。
    # 沿用上一版的 keep 不算：文字是原文、不是今晚寫的，而它的證據多半沒有重附，
    # 拿空的證據比對會把每個引號都算成沒命中。ref 對不上的 keep 文字是模型寫的，照算。
    if lookup_failed:
        result.quote_unmatched = None
    else:
        for change in result.accepted:
            if str(change.get("type") or "") == "drop" or _is_anchored_keep(change, base):
                continue
            misses = _unmatched_quotes(
                str(change.get("text") or ""),
                # **比對基準要跟模型看到的一致**：工具回給模型的是
                # `_clean_text_for_extraction` 的結果（去 URL、mention 轉 @某人、
                # `<:x:123>` 轉 `:x:`）。拿 DB 原文比，模型忠實照抄也會對不上。
                _JOIN.join(
                    tools._clean_text_for_extraction(real.get(str(i), ""))
                    for i in change.get("evidence_msg_ids") or []
                ),
            )
            result.quote_unmatched += len(misses)
            result.quote_misses.extend(misses)

    if not result.accepted:
        result.skip_reason = "沒有任何一項通過驗證"
    elif str(diff.get("confidence") or "").lower() == "low":
        # confidence 只用在這裡：模型自認資料不足時不覆寫既有描述。
        # **不用它判斷單項可信度**——編造 ID 那次自己標的就是 high。
        result.skip_reason = "confidence=low（模型自認資料不足，不寫入新版本）"

    if base is not None:
        result.ref_accounting = _account_refs(diff["changes"], base)
        # 不寫新版本時上一版原封不動，沒有任何項目消失——照算的話 confidence=low
        # 那幾晚每次都會多出幾個假的 lost，加總「消失了幾項」就會高估
        result.ref_accounting["lost"] = (
            [] if result.skip_reason else _lost_refs(result, base)
        )
        result.ref_accounting["superseded"] = superseded

    return result
