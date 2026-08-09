"""插話鉤子閘（L1）：決定「這一刻值不值得花那 ~120 秒去想」。

**不用 LLM。** 鉤子的存在意義就是決定要不要動用生成（實測中位 120s、單流排隊），
如果它自己要跑模型就失去意義了。方法是三層，由硬到軟：

    結構演算法（主，零 I/O）→ 少量 regex → k-NN 檢索（軟，一次 embedding）

**結構優於關鍵詞**：只看 `author_id` / `created_at` / `reference`，不理解內容——不會誤判語言、
規則數量不會膨脹，而且「人為什麼插話」本來就是時機問題多過內容問題。regex 只用在
「這則是不是問句」這種很窄的判定上，不拿來判「有沒有梗」。

計分：特徵加權後過 sigmoid，比對 `hook_threshold`。**權重全是正的、沒有負鉤子**——
鉤子只回答「這一刻值不值得想」，「該不該插進這段對話」是語意問題（判準是話題封不封閉，
不是有幾個人在聊），完整留給模型的第一關。唯一的否決是「連一則可讀的訊息都沒有」。
權重目前是手設的合理起點，之後用 `ai_interactions` 的 (特徵, got_reply) 跑 logistic
regression 取代——係數可讀，看得出它為什麼開口。

**ε-greedy 探索**：保留 `hook_explore_rate` 比例無視分數強制放行。沒有它，只有鉤子放行的
時機才會產生新樣本，偏好會自我強化、開口方式窄化成單一種（exposure bias）；探索樣本
同時也是迴歸訓練缺的反例。

鉤子只管「要不要喚醒模型」——**開不開口仍然是模型 [PASS] 說了算**，所以門檻可以設寬鬆。
"""
from __future__ import annotations

import logging
import math
import random
import re
import time
from typing import Optional

from sys_settings.llm_settings import AmbientChatSettings

logger = logging.getLogger("discord_bot")

_SETTINGS = AmbientChatSettings()

# 疑問句判定：句尾問號，或含疑問詞。窄用途——只判「這則是不是在問東西」。
_QUESTION_WORDS = (
    "嗎", "呢", "怎麼", "為什麼", "為何", "哪", "誰", "什麼", "幾點", "多少",
    "要不要", "有沒有", "是不是", "能不能", "可不可以", "會不會", "該不該",
)
# 明確對全場徵詢（最高把握的少數幾條；刻意克制，不擴充成關鍵詞地獄）
_SOLICIT_RE = re.compile(r"有沒有人|有人知道|大家覺得|求推薦|推薦一下|怎麼辦|求救|幫我看")
# 沒有 @ 但直接叫名字＝在對它說話
_NAME_RE = re.compile(r"琇紫|小紫")


def _is_question(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if t.endswith("?") or t.endswith("？"):
        return True
    return any(w in t for w in _QUESTION_WORDS)


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-60.0, min(60.0, x))))


class HookDecision:
    """鉤子判定結果（帶可讀細項，供 log 與之後的離線訓練）。"""

    __slots__ = ("passed", "score", "prob", "features", "veto", "explore", "signals")

    def __init__(self, *, passed: bool, score: float, prob: float,
                 features: dict, veto: Optional[str], explore: bool,
                 signals: Optional[list] = None):
        self.passed = passed
        self.score = score
        self.prob = prob
        self.features = features
        self.veto = veto
        self.explore = explore
        # 量到的事實，寫成中性描述後注入 prompt 的 <situation_signals>（見 describe_signals）
        self.signals = signals or []

    def __repr__(self) -> str:  # debug log 用
        hit = ",".join(k for k, v in self.features.items() if v) or "-"
        tag = "VETO:" + self.veto if self.veto else ("EXPLORE" if self.explore else
                                                    ("PASS" if self.passed else "SKIP"))
        # 同時印 raw score 與 sigmoid 後的機率：調權重時看 s= 比 p= 直觀（權重是加在 score 上的）
        return f"<hook {tag} s={self.score:+.2f} p={self.prob:.2f} [{hit}]>"


# ── 特徵權重（手設起點；之後由 logistic regression 取代）───────────────────────────
# 直覺來源：真人最常在「有人問了沒人回」「有人自言自語」「話題剛起頭／剛告一段落」時插話。
_W = {
    "bias": -1.2,            # 預設偏向不開口（開口是例外，不是預設）
    "dangling_question": 2.2,  # 懸空問句：有人問、沒人回 → 最強的正鉤子
    "monologue": 1.2,          # 獨白：同一人連講沒人接 → 插進去不打斷誰
    "active_chat": 1.2,        # 對話正熱 → 熱聊時插一句最自然（真人也是這時候插）
    "lull_after_burst": 1.0,   # 聊了一陣後停下來 → 話題告一段落
    "named": 2.5,              # 沒 @ 但叫名字
    "solicit": 1.3,            # 明確徵詢全場
    "knn_reply_rate": 1.8,     # k-NN：語意相近情境過去被接話的比率（置中後 ±0.5）
}
# 全部是正權重、沒有負鉤子：鉤子只回答「這一刻值不值得花 ~120s 去想」，
# 「該不該插進這段對話」是語意問題，留給模型的第一關。


def _structural_features(
    recent: list, now_ts: float, obs: Optional[dict] = None
) -> tuple[dict, Optional[str]]:
    """只看 metadata 的結構特徵。回 (特徵字典, 否決原因或 None)。

    recent：時序（舊→新）的 discord.Message，已排除 bot。now_ts＝現在的 epoch 秒。
    obs：傳一個 dict 進來，會被填入「量到了什麼」的細節（誰、多久前、幾則），
        供 `describe_signals()` 寫成給模型看的中性事實。out-param 而非改回傳簽章＝
        既有 caller（含測試）不受影響。
    """
    obs = obs if obs is not None else {}
    feats: dict = {
        "dangling_question": 0.0,
        "monologue": 0.0,
        "lull_after_burst": 0.0,
        "active_chat": 0.0,
    }
    # （曾有 `cold_start`＝「冷場超過 10 分鐘後有人開口就接」。語意上正是「沒人聊天時硬回」，
    #   使用者明確不要；實測 132 次評估裡也只命中 1 次，移除無痛。沒人在聊的時候，只有
    #   「有人問了沒人回」「有人叫它/徵詢」這類明確訊號才值得開口。）
    if not recent:
        return feats, "no_messages"

    def _ts(m) -> float:
        return m.created_at.timestamp()

    # 下面兩個「等一下再說」的門檻必須跟靜默期對齊：debounce 已經確保「最後一則之後
    # quiet_seconds 內沒有新訊息、而且沒人在打字」，鉤子再自己要求 30/60 秒就等於永遠
    # 不會命中——評估時通常才過 ~15 秒。（把鉤子接到 debounce 後面時漏掉的疊加效應，
    # 實測 log 全是 feats={}。等待「別人可能正在打字」這件事本來就已經由 typing 偵測負責。）
    quiet = max(5.0, _SETTINGS.quiet_seconds)

    # 這裡**刻意不用「幾個人在聊」當判準**。曾經有一條 A↔B 對線的負鉤子（兩人 + 間隔短 →
    # 直接否決），實測小頻道常態就是兩三人在聊，12 分鐘內 6/7 次判定全被擋掉、幾乎全時間靜音。
    # 根本問題是：prompt 第一關 gate #3 的判準是「**話題封不封閉**，不是有沒有兩個人」——那是
    # 語意問題，結構規則模仿不來，硬擋只會把「兩人在聊一件全場都看得到的事」一起殺掉。
    # 人數的事交給模型判斷；鉤子只管「時機」，不管「對象」。
    # ——但「誰跟誰在來回」這個**事實**仍然量測下來（存進 obs、不計分），寫成中性描述給模型，
    #   省下它自己數作者、算間隔的力氣（那正是它最容易算錯的地方）。判斷仍然是它的。
    tail = recent[-6:]
    if len(tail) >= 4:
        authors = {m.author.id for m in tail}
        gaps = [_ts(tail[i + 1]) - _ts(tail[i]) for i in range(len(tail) - 1)]
        if len(authors) == 2 and (sum(gaps) / len(gaps)) < 45.0:
            obs["two_person"] = [tail[-1].author, next(
                m.author for m in reversed(tail) if m.author.id != tail[-1].author.id
            )]

    # ── 懸空問句：最近 10 則裡有人問了問題，之後沒有別人回，且已過靜默期 ──
    for m in reversed(recent[-10:]):
        if not _is_question(getattr(m, "content", "") or ""):
            continue
        answered = any(
            x.author.id != m.author.id and _ts(x) > _ts(m) for x in recent
        )
        if not answered and (now_ts - _ts(m)) > quiet:
            feats["dangling_question"] = 1.0
            obs["question"] = (m.author, now_ts - _ts(m))
        break  # 只看最近那一個問句

    # ── 獨白：最近 3 則同一個人 ──
    if len(recent) >= 3 and len({m.author.id for m in recent[-3:]}) == 1:
        feats["monologue"] = 1.0
        streak = 0
        for m in reversed(recent):
            if m.author.id != recent[-1].author.id:
                break
            streak += 1
        obs["monologue"] = (recent[-1].author, streak, now_ts - _ts(recent[-1]))

    # ── 對話正熱：近 8 則擠在 3 分鐘內 → 場子熱絡，這時插一句最自然（真人也是這樣插話的）──
    # 其他鉤子全是「找空檔」導向（懸空問句/獨白/冷場/停頓），快節奏熱聊時一個都不命中；
    # 加上 debounce 在熱聊時等不到靜默、只能靠 max_wait 兜底放行，那時「已停下來」也不成立
    # → 熱聊必然靜音。這條就是補這個洞。
    # 與 lull_after_burst 不衝突：那條看「已經停下來」、這條看「節奏快」，同時成立＝剛熱聊完
    # 的空檔，本來就是最好的時機，疊加加分是對的。
    hot = recent[-8:]
    if len(hot) >= 5 and (_ts(hot[-1]) - _ts(hot[0])) < 180.0:
        feats["active_chat"] = 1.0

    # ── 聊了一陣後停頓：近 10 則跨度 < 10 分鐘（有在聊），且已經停下來（停＝靜默期已滿）──
    # 跨度原本設 5 分鐘，但那是「連珠炮式熱聊」的節奏；小頻道常態是每分鐘一兩則，10 則就
    # 超過 5 分鐘 → 這個鉤子等於只服務最吵的頻道。放寬到 10 分鐘涵蓋「正常聊了一段然後停」。
    window = recent[-10:]
    if len(window) >= 5:
        span = _ts(window[-1]) - _ts(window[0])
        if span < 600.0 and (now_ts - _ts(recent[-1])) > quiet:
            feats["lull_after_burst"] = 1.0

    return feats, None


def _ago(seconds: float) -> str:
    """秒數 → 口語的「多久前」（給模型看的，不需要精確到秒）。"""
    if seconds < 90:
        return "剛剛"
    mins = int(seconds // 60)
    return f"{mins} 分鐘前" if mins < 60 else f"{mins // 60} 小時前"


def describe_signals(obs: dict) -> list[str]:
    """把鉤子量到的事實寫成中性的自然語言，給模型當判斷材料。

    **只陳述事實、不下結論、不給分數。** 例如寫「A 問了一句、到現在沒人回應」，
    不寫「A 想要有人回答，建議你接話」——後者會把模型變成橡皮圖章，它的判斷力就廢了。
    分數/權重更是絕對不給：那是內部實作細節，模型看到只會誤以為「分數高就該講」。

    這樣分工才乾淨：**容易算錯的事實推導（誰回了誰、隔多久、連講幾則）交給 code，
    需要理解的判斷（他是想要回應還是不想被打擾、這時候插話得不得體）留給模型。**
    """
    from llm.chat_line import name_with_anchor  # leaf 模組，避免頂層循環 import

    lines: list[str] = []
    if "question" in obs:
        author, ago = obs["question"]
        lines.append(
            f"・{name_with_anchor(author)} 問了一句（{_ago(ago)}），到現在沒有人回應。"
        )
    if "monologue" in obs:
        author, streak, ago = obs["monologue"]
        lines.append(
            f"・{name_with_anchor(author)} 連續講了 {streak} 則都沒有人接話"
            f"（最後一則：{_ago(ago)}）。"
        )
    if "two_person" in obs:
        a, b = obs["two_person"]
        lines.append(
            f"・最近幾則是 {name_with_anchor(a)} 和 {name_with_anchor(b)} 兩個人在來回，"
            "節奏很快。"
        )
    return lines


def _channel_has_life(recent: list, now_ts: float) -> bool:
    """頻道最近到底有沒有人在——**ε-greedy 探索的前提**。

    探索是「無視分數硬放行」，原本不管有沒有人在。但沒人聊天時探索既學不到東西
    （沒人在，標籤必然是「沒人接」），又會在死寂的頻道突然冒一句——實測「無任何特徵卻被
    探索放行」正是使用者回報「沒人聊天也硬回」的來源。

    判準刻意寬鬆（只要求「有一小群訊息落在近期」），因為真正該不該講已經由分數決定，
    這裡只是把「連人都不在」的情況擋掉。
    """
    n = _SETTINGS.explore_min_messages
    if len(recent) < n:
        return False
    return (now_ts - recent[-n].created_at.timestamp()) < _SETTINGS.explore_activity_window_seconds


def _text_features(recent: list) -> dict:
    """極少量的內容 regex（只放最高把握的幾條）。看最近 3 則的合併文字。"""
    blob = " ".join((getattr(m, "content", "") or "") for m in recent[-3:])
    return {
        "named": 1.0 if _NAME_RE.search(blob) else 0.0,
        "solicit": 1.0 if _SOLICIT_RE.search(blob) else 0.0,
    }


async def _knn_feature(situation: str) -> tuple[float, int]:
    """k-NN 軟特徵：過去語意相近情境下，自發插話被接話的比率。回 (置中後的值, 樣本數)。

    值域置中到 [-0.5, +0.5]（比率 0.5 ＝中性 0）；樣本不足 5 筆視為沒訊號回 (0.0, n)——
    功能剛上線時 got_reply 幾乎全是 NULL，這個特徵會自動休眠，等資料長出來才生效。
    """
    if not _SETTINGS.hook_knn_enabled or not situation.strip():
        return (0.0, 0)
    try:
        import asyncio

        from llm.ai_interactions_store import fetch_reply_rate_stats

        n, rate = await asyncio.to_thread(
            fetch_reply_rate_stats,
            situation,
            k=_SETTINGS.hook_knn_top_k,
            max_distance=_SETTINGS.hook_knn_max_distance,
        )
    except Exception as exc:
        logger.debug("鉤子 k-NN 特徵取得失敗：%s", exc)
        return (0.0, 0)
    if n < 5:
        return (0.0, n)
    return (rate - 0.5, n)


async def evaluate(recent: list, *, situation: str = "") -> HookDecision:
    """算這一刻該不該喚醒模型。recent＝時序（舊→新）的真人訊息（呼叫端已濾掉 bot）。

    整段 best-effort：任何一層失敗都不該擋住插話——例外時回「放行」，讓後面的模型 [PASS]
    去把關，寧可多想一次也不要因為鉤子壞掉而整個功能啞掉。
    """
    if not _SETTINGS.hook_enabled:
        return HookDecision(passed=True, score=0.0, prob=1.0, features={},
                            veto=None, explore=False)
    try:
        now_ts = time.time()
        obs: dict = {}
        feats, veto = _structural_features(recent, now_ts, obs)
        feats.update(_text_features(recent))
        knn_val, knn_n = await _knn_feature(situation)
        feats["knn_reply_rate"] = knn_val

        score = _W["bias"] + sum(_W.get(k, 0.0) * v for k, v in feats.items())
        prob = _sigmoid(score)

        explore = False
        if veto is not None:
            passed = False
        else:
            passed = prob >= _SETTINGS.hook_threshold
            # ε-greedy：專收「鉤子不看好」的樣本——但只在頻道真的有人在的時候探索
            if (not passed and _channel_has_life(recent, now_ts)
                    and random.random() < _SETTINGS.hook_explore_rate):
                passed, explore = True, True

        decision = HookDecision(passed=passed, score=score, prob=prob,
                                features=feats, veto=veto, explore=explore,
                                signals=describe_signals(obs))
        if _SETTINGS.hook_debug:
            logger.info(
                "ambient 鉤子 %s | thr=%.2f knn(n=%d,v=%+.2f) feats=%s",
                decision, _SETTINGS.hook_threshold, knn_n, knn_val,
                {k: round(v, 2) for k, v in feats.items() if v},
            )
        return decision
    except Exception as exc:
        logger.warning("鉤子評估例外（放行交給模型判斷）：%s", exc, exc_info=True)
        return HookDecision(passed=True, score=0.0, prob=1.0, features={},
                            veto=None, explore=False)
