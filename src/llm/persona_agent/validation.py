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
from typing import Any, Optional, Sequence

from llm.persona_agent import tools
from sys_settings.pgvector_settings import HYBRID_RETRIEVAL_SETTINGS

logger = logging.getLogger("discord_bot")

VALID_TYPES = {"add", "revise", "keep"}
VALID_CONFIDENCE = {"low", "medium", "high"}

#: 沿用 tools 的型別，不另外定義一份（同一個東西兩個名字就是分岔的起點）
FetchFn = tools.FetchFn


@dataclass
class ValidationResult:
    """驗證結果。`accepted` 才進版本表，其餘都是要記進 runs 表的統計。"""

    accepted: list[dict[str, Any]] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    #: 宣稱的證據總數 / 其中查無此筆或不屬於本人的數量
    evidence_claimed: int = 0
    evidence_bogus: int = 0
    #: 整筆不寫版本的原因（None 代表可以寫）
    skip_reason: Optional[str] = None
    #: 描述裡「」引號內的字串，在自己列的證據訊息裡找不到的個數。
    #: **只記錄不擋**——見 `_unmatched_quotes` 的說明。
    #: `None` 代表本次沒算（證據反查失敗，語料拿不到），與 0 意義不同。
    quote_unmatched: Optional[int] = 0
    quote_misses: list[str] = field(default_factory=list)

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


def _shape_problem(change: dict[str, Any]) -> Optional[str]:
    """形狀與語意檢查。回傳問題描述，沒問題回 None。"""
    ctype = str(change.get("type") or "").strip()
    if ctype not in VALID_TYPES:
        return f"type 不合法：{ctype!r}"
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


def validate_diff(
    diff: dict[str, Any],
    *,
    user_id: str,
    fetch: FetchFn,
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
        if isinstance(change, dict) and isinstance(change.get("evidence_msg_ids"), list):
            claimed.extend(str(i) for i in change["evidence_msg_ids"])
    result.evidence_claimed = len(claimed)
    found = _real_evidence(fetch, user_id=user_id, ids=claimed)
    # None＝反查失敗（fail-open）。id 檢查照舊全放行，但引號比對整個跳過，
    # 並讓 quote_unmatched 留 None，人工複查時才分得出「沒算」與「算了是 0」。
    lookup_failed = found is None
    real = {str(i): "" for i in claimed} if lookup_failed else found

    for change in diff["changes"]:
        if not isinstance(change, dict):
            result.rejected.append({"change": change, "why": "不是物件"})
            continue
        problem = _shape_problem(change)
        if problem:
            result.rejected.append({"change": change, "why": problem})
            continue
        ids = [str(i) for i in change["evidence_msg_ids"]]
        bogus = [i for i in ids if i not in real]
        if bogus:
            result.evidence_bogus += len(bogus)
            result.rejected.append({
                "change": change,
                "why": f"引用了不存在或不屬於本人的 msg_id：{bogus}",
            })
            continue
        # 通過驗證後才算引號——被退掉的項目不必再花這個力氣
        if not lookup_failed:
            misses = _unmatched_quotes(
                str(change.get("text") or ""),
                # **比對基準要跟模型看到的一致**：工具回給模型的是
                # `_clean_text_for_extraction` 的結果（去 URL、mention 轉 @某人、
                # `<:x:123>` 轉 `:x:`）。拿 DB 原文比，模型忠實照抄也會對不上。
                _JOIN.join(
                    tools._clean_text_for_extraction(real.get(i, "")) for i in ids
                ),
            )
            result.quote_unmatched += len(misses)
            result.quote_misses.extend(misses)
        result.accepted.append(change)

    if lookup_failed:
        result.quote_unmatched = None

    if not result.accepted:
        result.skip_reason = "沒有任何一項通過驗證"
    elif str(diff.get("confidence") or "").lower() == "low":
        # confidence 只用在這裡：模型自認資料不足時不覆寫既有描述。
        # **不用它判斷單項可信度**——編造 ID 那次自己標的就是 high。
        result.skip_reason = "confidence=low（模型自認資料不足，不寫入新版本）"

    return result
