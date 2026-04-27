"""意圖偵測 + 查詢整理 + 類別路由：純 regex、零外部依賴。

三個獨立責任：
1. `should_search`：判斷要不要搜（yes/no + 觸發原因）
2. `clean_query`：剝除指令性贅字，得到真正要送 SearXNG 的字串
3. `classify_route`：依關鍵字決定 categories / time_range

合併為 `IntentResult`，方便 caller 一次拿到所有所需資訊。
"""

from __future__ import annotations

import re
from dataclasses import dataclass


# 強觸發：明確指涉需要即時 / 外部資訊
# 注意：剛剛/剛才 刻意不放 HARD（太泛、會誤觸「剛才那段翻成英文」），改進 SOFT 時間詞。
_SEARCH_HARD = re.compile(
    r"新聞|最新|今天|今日|本日|昨天|昨日|目前|現在|即時|此刻|近況|"
    r"股價|股票|台股|美股|港股|陸股|日股|加權|大盤|盤中|收盤|漲跌|行情|匯率|幣價|"
    r"天氣|氣溫|下雨|颱風|氣象|降雨|"
    r"版本|更新|patch|release|開服|維護|公告|活動|改版|前瞻|"
    r"發布|發佈|上市|上線|推出|公布|發售|"
    r"查詢|查一下|搜尋|搜一下|找一下|看一下|"
    r"幫我查|幫我找|幫我搜|幫我看|"
    r"google\s*一下|goolge一下|"
    r"幾點開|何時上線|什麼時候出|發布日|發佈日|"
    r"reddit|鄉民|網友怎麼說|討論度",
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
    r"(最近|這週|這個月|前幾天|這兩天|這幾天|上週|最近一週|剛剛|剛才)"
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
_ROUTE_RULES: tuple[tuple[re.Pattern[str], str | None, str | None], ...] = (
    # 股價類：news + 當日（股市真的是時事類，news engines 覆蓋 OK）
    (re.compile(r"股價|漲跌|盤中|收盤|大盤|台股|美股|港股|陸股|日股|加權|行情|匯率|幣價"), "news", "day"),
    # 天氣類：通用 + 當日
    (re.compile(r"天氣|氣溫|降雨|颱風|氣象"), None, "day"),
    # 遊戲改版 / 軟體版本：通用 + 一週（news engines 對這類覆蓋太差）
    (
        re.compile(
            r"版本|更新|改版|patch|release|前瞻|上線|發布|發佈|推出|公布",
            re.IGNORECASE,
        ),
        None,
        "week",
    ),
    # 純新聞 / 政治時事：news + 一週
    (re.compile(r"新聞|今天|今日|本日|昨天|昨日|最新|公告|開服|維護"), "news", "week"),
    # Reddit / 鄉民 / 網友討論
    (re.compile(r"reddit|鄉民|網友怎麼說|網友說|討論度", re.IGNORECASE), "social media", None),
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


def classify_route(text: str) -> tuple[str | None, str | None]:
    """依關鍵字決定 SearXNG 的 categories 與 time_range。"""
    for pattern, cat, tr in _ROUTE_RULES:
        if pattern.search(text):
            return cat, tr
    return None, None


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
        )

    text = question.strip()
    cleaned = clean_query(text)
    cat, tr = classify_route(text)

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
            )
        return IntentResult(
            triggered=False,
            reason="never",
            trigger_keyword=None,
            cleaned_query=cleaned,
            categories=None,
            time_range=None,
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
        )

    return IntentResult(
        triggered=False,
        reason="default",
        trigger_keyword=None,
        cleaned_query=cleaned,
        categories=None,
        time_range=None,
    )
