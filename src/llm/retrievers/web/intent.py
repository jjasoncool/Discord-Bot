"""意圖偵測 + 查詢整理 + 類別路由：純 regex、零外部依賴。

三個獨立責任：
1. `should_search`：判斷要不要搜（yes/no + 觸發原因）
2. `clean_query`：剝除指令性贅字，得到真正要送 SearXNG 的字串
3. `classify_route`：依關鍵字決定 categories / time_range / language

合併為 `IntentResult`，方便 caller 一次拿到所有所需資訊。
"""

from __future__ import annotations

import re
from dataclasses import dataclass


# === 主題 token 群（HARD 觸發 + 對應 route 共用）===
# 新增主題：在這裡加一個常數、再到 _ROUTE_RULES 加一條規則即可，
# HARD 端會自動透過下方 _alt(...) 收進去，不會再有單邊忘改的 drift。
#
# tuple 元素是 regex fragment（允許 \s+ \s* 等控制字元）；要塞含 + * ? | ( )
# 等 regex 特殊符號的 token 需自行 escape。
_TOPIC_FINANCE_INTL = (
    "美股", "nasdaq", "nyse", "s&p", r"dow\s+jones", "道瓊",
    "比特幣", "以太幣", "加密貨幣", "crypto", "bitcoin", "ethereum",
)
_TOPIC_FINANCE_ZH = (
    "股價", "漲跌", "盤中", "收盤", "大盤",
    "台股", "港股", "陸股", "日股", "加權",
    "行情", "匯率", "幣價",
)
_TOPIC_WEATHER = ("天氣", "氣溫", "降雨", "颱風", "氣象")
_TOPIC_GAME_PATCH = (
    "版本", "更新", "改版", "patch", "release", "前瞻",
    "上線", "發布", "發佈", "推出", "公布",
)
_TOPIC_NEWS_PURE = ("公告", "開服", "維護")
_TOPIC_REDDIT = ("reddit", "鄉民", "網友怎麼說", "討論度")
# 體育賽事「報導 / 花絮」類問句（時效性中等，走 news + 一週）。
# 刻意不收 bare「比賽」「賽」——太泛會誤觸（「遊戲的比賽機制」「比賽看法」）；
# 用「世界盃 / 足球 / 球賽」這種帶體育語意的錨字。
# 注意：賽程 / 賽果 / 比分 / 場次 這類「即時數據」字已拆到下方 _TOPIC_SPORTS_LIVE，
# 改走 general + 當日——news engines 撈不到比分站 / 賽程頁，對這類查詢只會回花絮
# 特稿（隊醫最忙、最幸福的球迷⋯），答非所問。
# 「戰績」刻意留在這裡（news + 一週）：中文多指「生涯 / 累計戰績」(選舉/業績/電競)，
# 而非當日比分；壓成單日視窗會把歷史型查詢答壞，故不收進 live。
_TOPIC_SPORTS = (
    "世界盃", "世足", "足球", "籃球", "棒球", "排球",
    "賽事", "球賽", "體育",
    "季後賽", "總冠軍", "戰績",
    "nba", "mlb", "英超", "西甲", "歐冠", "歐國盃", "中職",
)
# 體育即時數據（賽程 / 賽果 / 比分 / 場次）：時效性高，資料活在比分站 / 賽程頁 /
# 官網（皆非 news 分類），故與上面「報導群」拆開，單獨走 general + 當日。
#   • 賽程 / 賽果 / 比分：domain-specific，誤觸風險低 → 同時 HARD 觸發（見 *_HARD）。
#   • 場次：與「現場 / 賣場 / 停車場 / 工作場 + 次X」等詞相連會誤觸（中文無詞界），
#     故只進路由、不進 HARD；真實場次查詢通常另帶「今天 / 查 / 世足」等 HARD 字，
#     仍會先觸發、再由本路由接走，不影響回報的「今天世足賽場次」案例。
_TOPIC_SPORTS_LIVE_HARD = (
    "賽程", "賽果", "比分",
)
_TOPIC_SPORTS_LIVE = _TOPIC_SPORTS_LIVE_HARD + ("場次",)

# === 純觸發 token（HARD 用；不對應特定 route）===
# 新聞時序錨字：HARD + 純新聞 route 共用。拆「今日」與「其餘」兩組：
#   • _TRIGGER_NEWS_TODAY（今天 / 今日 / 本日）→ 明確指當天，走 news + day。
#   • _TRIGGER_NEWS_TIME（新聞 / 最新 / 昨天 / 昨日）→ 時序較寬或不確定，走 news + week。
# 「昨天 / 昨日」刻意留 week 不放 day：SearXNG 的 day≈過去 24h，會切掉昨天上半天，
# 寧可用 week 完整涵蓋（超集），也不要漏掉昨天主新聞。
_TRIGGER_NEWS_TODAY = ("今天", "今日", "本日")
_TRIGGER_NEWS_TIME = ("新聞", "最新", "昨天", "昨日")
# HARD-only：觸發但無特定 route，落入 default（categories/time_range/language 皆 None）
_TRIGGER_HARD_ONLY = (
    # 即時狀態詞
    "目前", "現在", "即時", "此刻", "近況",
    # 主題不夠特定的單字（沿用既有行為，未掛 route）
    "股票", "下雨", "活動", "上市", "發售",
    # 搜尋動詞 / 禮貌請求
    "查詢", "查一下", "搜尋", "搜一下", "找一下", "看一下",
    "幫我查", "幫我找", "幫我搜", "幫我看",
    r"google\s*一下", "goolge一下",
    # 釋出時程提問
    "幾點開", "何時上線", "什麼時候出", "發布日", "發佈日",
)


def _alt(*groups: tuple[str, ...]) -> str:
    """把多個 token tuple 攤平串成 regex alternation。"""
    return "|".join(token for group in groups for token in group)


# 強觸發：明確指涉需要即時 / 外部資訊
# 注意：剛剛/剛才 刻意不放 HARD（太泛、會誤觸「剛才那段翻成英文」），改進 SOFT 時間詞。
_SEARCH_HARD = re.compile(
    _alt(
        _TRIGGER_NEWS_TODAY, _TRIGGER_NEWS_TIME, _TRIGGER_HARD_ONLY,
        _TOPIC_FINANCE_ZH, _TOPIC_FINANCE_INTL,
        _TOPIC_WEATHER, _TOPIC_GAME_PATCH, _TOPIC_NEWS_PURE, _TOPIC_REDDIT,
        _TOPIC_SPORTS, _TOPIC_SPORTS_LIVE_HARD,  # 場次 不進 HARD（見上方註解）
    ),
    re.IGNORECASE,
)

# 強排除：明顯閒聊 / 情緒 / 對 bot 本身的問話
_SEARCH_NEVER = re.compile(
    r"^(早安|晚安|你好|嗨|哈囉|幹嘛|在嗎|愛你|喜歡你|想你|抱抱)"
    r"|^(你是誰|你叫什麼|你幾歲|你喜歡|幫我tag|標記|tag一下)"
    r"|^(想吐槽|好累|煩死|無聊|笑死|真的假的|傻眼)"
)

# 軟觸發：時間詞 + 實體動詞組合（剛剛/剛才 需在此處配動詞才會觸發，避免誤判）
_SEARCH_SOFT = re.compile(
    r"(最近|這[週周]|這個月|前幾天|這兩天|這幾天|上[週周]|最近一[週周]|剛剛|剛才)"
    r".{0,30}"
    r"(發生|新|出|改|更|上線|推出|發布|開放|變化|漲|跌)"
)

# 指令性贅字（剝除用）：開頭禮貌詞、「幫我+動詞」、「動詞+一下」、末尾「一下」
_STRIP_PATTERNS: tuple[re.Pattern[str], ...] = (
    # 開頭禮貌 / 疑問詞
    re.compile(r"^(請問|請|麻煩|拜託|可不可以|可以嗎|可以|能不能|能)\s*"),
    # 「幫我」+動詞(+一下)：最具體、最長；google\s*一下 容許空格
    re.compile(
        r"幫我\s*"
        r"(查詢|查看|查一下|查|搜尋|搜一下|搜|找一下|找|看一下|看|"
        r"google\s*一下|google)\s*",
        re.IGNORECASE,
    ),
    # 獨立的「動詞+一下」或「查詢」開頭
    re.compile(
        r"^(查詢|查一下|搜尋|搜一下|找一下|看一下|google\s*一下|google一下)\s*",
        re.IGNORECASE,
    ),
    # 殘留的 bare「幫我」（當動詞沒命中時，例如「幫我 tag」）
    re.compile(r"^幫我\s*"),
    # 末尾「一下」
    re.compile(r"[，,\s]*一下\s*$"),
    # 多空白合成單空白（最後跑）
    re.compile(r"\s+"),
)

# 路由規則（順序敏感：愈特定愈前）
#
# 為什麼遊戲改版類走通用 engines 而不是 news：
# 實測 Google News / Bing News 在 zh-TW 對遊戲垂直站（巴哈、4Gamers、遊戲角落）
# 覆蓋極差，news engines 查「鳴潮」會拿到買房/政治新聞。通用 engines + time_range
# 才能抓到真正的遊戲新聞，同時用日期過濾擋掉舊版。
#
# 為什麼國際金融題材要切 language=en：
# zh-TW news engines 對美股/加密幣當日新聞命中差，題材源頭幾乎都是英文
# (reuters/bloomberg/cnbc)，中文媒體常落後 6~24 小時。切到 en locale 才能撈到
# 原始英文頭條；chat model（gemma 27B）自帶英→繁中能力，配 system prompt
# 「只能使用繁體中文」規則，最終輸出仍是繁中。
#
# 「網友說」歷史上只在 Reddit route 出現、未在 HARD 裡，因此維持 inline
# 不收進 _TOPIC_REDDIT，避免擴張 HARD 觸發行為。
_ROUTE_RULES: tuple[tuple[re.Pattern[str], str | None, str | None, str | None], ...] = (
    # 國際金融題材：news + 當日 + 英文 locale（最特定，需排在股價類之前）
    (re.compile(_alt(_TOPIC_FINANCE_INTL), re.IGNORECASE), "news", "day", "en"),
    # 股價類：news + 當日（中文圈題材：台股、港股、日股、陸股、匯率等）
    (re.compile(_alt(_TOPIC_FINANCE_ZH)), "news", "day", None),
    # 天氣類：通用 + 當日
    (re.compile(_alt(_TOPIC_WEATHER)), None, "day", None),
    # 遊戲改版 / 軟體版本：通用 + 一週（news engines 對這類覆蓋太差）
    (re.compile(_alt(_TOPIC_GAME_PATCH), re.IGNORECASE), None, "week", None),
    # 體育即時數據（賽程 / 賽果 / 比分 / 場次）：general + 當日。
    # 必須排在下面的「體育報導」規則之前——這類字常與「世足 / NBA」等主題字同時出現
    # （例：「今天世足賽最新場次」），先比中這條才能避開 news 路由。原因：賽程 / 比分
    # 活在比分站 / 賽程頁 / 官網（非 news 分類），走 news engines 只會回花絮特稿；
    # 改 general 引擎讓比分站浮上來，time_range=day 收斂到當日資料。
    (re.compile(_alt(_TOPIC_SPORTS_LIVE), re.IGNORECASE), None, "day", None),
    # 體育報導 / 花絮：news + 一週（news engines 對足球 / NBA 等「報導類」覆蓋良好；
    # 但對賽程 / 比分這種即時數據覆蓋差，那類已由上一條 general 規則接走）
    (re.compile(_alt(_TOPIC_SPORTS), re.IGNORECASE), "news", "week", None),
    # 今日新聞：news + 當日（「今天 / 今日 / 本日」明確指當天，time_range 收到 day；
    # 排在下面 week 規則之前，「今天新聞」這種同時帶兩組的 query 才會落在 day）
    (re.compile(_alt(_TRIGGER_NEWS_TODAY)), "news", "day", None),
    # 純新聞 / 政治時事 / 最新 / 昨日：news + 一週
    (re.compile(_alt(_TRIGGER_NEWS_TIME, _TOPIC_NEWS_PURE)), "news", "week", None),
    # Reddit / 鄉民 / 網友討論（網友說 inline，原因見上方說明）
    (re.compile(_alt(_TOPIC_REDDIT) + r"|網友說", re.IGNORECASE), "social media", None, None),
)


@dataclass(frozen=True)
class IntentResult:
    """意圖偵測 + 查詢整理 + 類別路由的一次性結果。"""

    triggered: bool
    reason: str  # "hard" | "soft" | "never" | "default"
    trigger_keyword: str | None
    cleaned_query: str
    categories: str | None  # "news" | "social media" | None
    time_range: str | None  # "day" | "week" | "month" | None
    language: str | None  # 強制 SearXNG locale；None 沿用 settings.language（zh-TW）


def clean_query(text: str) -> str:
    """剝除指令性贅字，保留真正要搜尋的主題字串。

    全部被剝空時退回原文（保底不丟出空字串）。
    """
    cleaned = text.strip()
    # 多次迭代，處理「請幫我查一下...」這種疊加結構
    for _ in range(4):
        previous = cleaned
        for pattern in _STRIP_PATTERNS:
            cleaned = pattern.sub(" ", cleaned).strip()
        if cleaned == previous:
            break
    return cleaned or text.strip()


def classify_route(text: str) -> tuple[str | None, str | None, str | None]:
    """依關鍵字決定 SearXNG 的 categories、time_range 與 language。"""
    for pattern, cat, tr, lang in _ROUTE_RULES:
        if pattern.search(text):
            return cat, tr, lang
    return None, None, None


def should_search(question: str) -> IntentResult:
    """綜合判斷：是否搜、要怎麼搜、搜什麼字串。

    判斷順序：
    1. 空字串 → 不搜（default）
    2. 很短（< 6 字）且無 HARD 關鍵字 → 不搜（never）
    3. 命中 NEVER → 不搜（never）
    4. 命中 HARD → 搜（hard）
    5. 命中 SOFT → 搜（soft）
    6. 其他 → 不搜（default）
    """
    if not question or not question.strip():
        return IntentResult(
            triggered=False,
            reason="default",
            trigger_keyword=None,
            cleaned_query="",
            categories=None,
            time_range=None,
            language=None,
        )

    text = question.strip()
    cleaned = clean_query(text)
    cat, tr, lang = classify_route(text)

    if len(text) < 6:
        hard = _SEARCH_HARD.search(text)
        if hard:
            return IntentResult(
                triggered=True,
                reason="hard",
                trigger_keyword=hard.group(0),
                cleaned_query=cleaned,
                categories=cat,
                time_range=tr,
                language=lang,
            )
        return IntentResult(
            triggered=False,
            reason="never",
            trigger_keyword=None,
            cleaned_query=cleaned,
            categories=None,
            time_range=None,
            language=None,
        )

    never = _SEARCH_NEVER.search(text)
    if never:
        return IntentResult(
            triggered=False,
            reason="never",
            trigger_keyword=never.group(0),
            cleaned_query=cleaned,
            categories=None,
            time_range=None,
            language=None,
        )

    hard = _SEARCH_HARD.search(text)
    if hard:
        return IntentResult(
            triggered=True,
            reason="hard",
            trigger_keyword=hard.group(0),
            cleaned_query=cleaned,
            categories=cat,
            time_range=tr,
            language=lang,
        )

    soft = _SEARCH_SOFT.search(text)
    if soft:
        return IntentResult(
            triggered=True,
            reason="soft",
            trigger_keyword=soft.group(0),
            cleaned_query=cleaned,
            categories=cat,
            time_range=tr,
            language=lang,
        )

    return IntentResult(
        triggered=False,
        reason="default",
        trigger_keyword=None,
        cleaned_query=cleaned,
        categories=None,
        time_range=None,
        language=None,
    )
