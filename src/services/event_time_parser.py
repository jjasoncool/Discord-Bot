"""
官方公告活動時間解析（純函式，無 discord / db / io 依賴，可單測）。

設計來源：對 articles.db 全 490 篇 + fb_posts.json 對抗審查（2026-07-01）後定案。
- 雙詞交集硬閘門：同時含「活動時間」AND（「伺服器時間」OR「（UTC+8）」）。
- 錨點認「詞」不認「✦符號」（✦裝飾不穩定），並排除「活動時間結束/及時/期間/內」散文。
- 逐錨點抽出「所有」range（一篇可多事件，含版本內容說明匯總帖）。
- DATE：年月日時:分 / YYYY/M/D（日與時可選空白）+ 缺年分支（用貼文年份補）。
- 相對起點「X版本更新後」→ 不在這層解析成日期，回傳版本號交由上層回填（查不到則上層 SKIP）。
- 時區一律 UTC+8（伺服器時間/UTC+8 同義）；台港服無 DST，等同 fixed +8。
- 寧可漏不可錯：抓不到/缺結束/永久開放 → 不產出該筆。
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional


# 公告宣告的「伺服器時間」（由下方 _TZ_MARKER 閘門確認過是 UTC+8）。
#
# **刻意不是 APP_TZ，也不該被「收斂」掉**——兩者今天同值，語意卻完全不同：
#   APP_TZ    ＝「本機在哪個時區」，可用 APP_UTC_OFFSET_HOURS 設定
#   SERVER_TZ ＝「這份資料宣告它的時間屬於哪個時區」，由遊戲決定、固定 UTC+8
#
# 混用的話，APP_TZ 一改就會有兩種災情：
#   ① 公告「10:00（伺服器時間）」被當成新時區的 10:00 → 活動時間整批偏移
#   ② event_fingerprint 用它正規化 → 既有指紋全部失配 → 去重表失效、
#      所有舊活動被重新建立一次（而 created_events 是持久化的）
SERVER_TZ = timezone(timedelta(hours=8))

# ── 關鍵字 / 時區標記 ──
_TZ_MARKER = re.compile(r'[（(]\s*(?:伺服器時間|伺服器時區|UTC\s*[＋+]\s*8|GMT\s*[＋+]\s*8)\s*[）)]')

# 單一日期時間 token（named，僅供獨立解析用）：年份可選（缺年走補年）；
# 日與時之間允許空白；半/全形冒號
_DATE_TOKEN = (
    r'(?:(?P<y>\d{4})\s*[/年]\s*)?'      # 年（可選）
    r'(?P<mo>\d{1,2})\s*[/月]\s*'         # 月
    r'(?P<d>\d{1,2})\s*日?\s*'            # 日（日字可省）
    r'(?P<h>\d{1,2})\s*[:：]\s*'          # 時
    r'(?P<mi>\d{2})'                      # 分
)
# 非捕獲版（可重複嵌進 ANCHOR，不會撞 group 名）
_DATE_TOKEN_NC = (
    r'(?:\d{4}\s*[/年]\s*)?\d{1,2}\s*[/月]\s*\d{1,2}\s*日?\s*\d{1,2}\s*[:：]\s*\d{2}'
)
_DATE_RE = re.compile(_DATE_TOKEN)
_DATE_FULLMATCH = re.compile(r'\s*' + _DATE_TOKEN_NC + r'\s*$')

_SEP = r'[~～\-－—∼至到]'
_TZ_INLINE = r'(?:\s*[（(]\s*(?:伺服器時間|UTC\s*[＋+]\s*8)\s*[）)])?'

# 錨點：活動時間（排除散文用法）+ 不穩定裝飾；後面跟 start｜sep｜end
# start = 完整/缺年 DATE  或  ≤16 字相對描述（如「2.4版本更新後」）
_ANCHOR = re.compile(
    r'活動時間'
    r'(?!結束|及時|期間|內|前)'                       # 排除「活動時間結束後/及時參與…」散文
    r'[✦＊*：:\s　]*'                                 # 不穩定裝飾，忽略
    r'(?P<start>(?:' + _DATE_TOKEN_NC + r')|[^~～\-－—∼至到（）()\n]{1,16}?)'
    + _TZ_INLINE +
    r'\s*' + _SEP + r'\s*'
    r'(?P<end>' + _DATE_TOKEN_NC + r')'
)

# 版本號擷取（「2.4版本更新後」「3.0 版本上線後」）
_VERSION_RE = re.compile(r'(\d+\.\d+)\s*版本')


@dataclass
class ParsedEvent:
    """解析出的單一活動（時間皆為 UTC+8 aware；start 可能因相對起點而為 None）。"""
    start: Optional[datetime]                 # UTC+8 aware；相對起點未解析時為 None
    end: datetime                             # UTC+8 aware（必有）
    start_relative_version: Optional[str]     # 相對起點的版本號（如 "2.4"），否則 None
    title_hint: str                           # 錨點前文（給上層組指紋/活動名用）
    raw: str                                  # 命中的原始片段（debug）
    start_raw: Optional[str] = None           # 相對起點的原始字串（如「即日起」「2.4版本更新後」）

    @property
    def is_relative_start(self) -> bool:
        """相對起點且帶版本號（需版本日回填）。"""
        return self.start is None and self.start_relative_version is not None

    @property
    def is_immediate_start(self) -> bool:
        """『即日起 / 即時』類相對起點（用貼文日 00:00）。"""
        return (self.start is None and self.start_relative_version is None
                and bool(self.start_raw) and ('即日' in self.start_raw or '即時' in self.start_raw))


def strip_html(text: str) -> str:
    """去 HTML tag + 解 entity + 正規化空白字元（article 內文是 HTML，FB 是純文字）。"""
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', '', text)
    text = html.unescape(text)
    return text.replace('​', '').replace('\xa0', ' ')


def passes_gate(text: str) -> bool:
    """雙詞交集硬閘門：同時含『活動時間』AND（『伺服器時間』OR『（UTC+8）』）。"""
    if '活動時間' not in text:
        return False
    return ('伺服器時間' in text) or bool(_TZ_MARKER.search(text))


def _build_dt(y: int, mo: int, d: int, h: int, mi: int) -> Optional[datetime]:
    """組 UTC+8 aware datetime；非法日期回 None。"""
    try:
        return datetime(y, mo, d, h, mi, tzinfo=SERVER_TZ)
    except ValueError:
        return None


def _parse_date_token(token: str, default_year: int) -> Optional[datetime]:
    """解析單一日期 token（缺年用 default_year 補）。"""
    m = _DATE_RE.search(token)
    if not m:
        return None
    y = int(m.group('y')) if m.group('y') else default_year
    return _build_dt(y, int(m.group('mo')), int(m.group('d')),
                     int(m.group('h')), int(m.group('mi')))


def parse_events(
    text: str,
    *,
    post_time: Optional[datetime] = None,
    is_html: bool = False,
    fallback_title: str = "",
) -> List[ParsedEvent]:
    """
    從公告全文抽出所有活動時間區間。

    Args:
        text: 公告原文（article 為 HTML、FB 為純文字）。
        post_time: 貼文發布時間（缺年補年用；可為 None → 用今年無妨，跨年再修）。
        is_html: True 時先 strip HTML。
        fallback_title: 當錨點前文取不到名稱時的備援標題（如 article_title）。

    Returns:
        ParsedEvent 串列（可能多筆；不符合閘門或抓不到回 []）。
    """
    if is_html:
        text = strip_html(text)
    if not passes_gate(text):
        return []

    default_year = post_time.year if post_time else datetime.now(SERVER_TZ).year
    events: List[ParsedEvent] = []

    matches = list(_ANCHOR.finditer(text))
    # 單一活動帖：內文通常沒有章節標題行，抓不到就退用貼文標題（article_title / FB 首行），
    # 而不是退到括號名——否則會抓到敘述句裡最後一個 4 星名（「燈燈」「悖論噴流」），
    # 且 article 與 FB 兩邊退出來的名字不同 → 跨來源指紋對不上 → 重複建活動。
    # 匯總帖（多錨點）才保留括號名 fallback，否則各活動同名 → 指紋互撞被吃掉。
    multi = len(matches) > 1

    for m in matches:
        start_str = (m.group('start') or '').strip()
        end_str = (m.group('end') or '').strip()

        # 結束：必為可解析日期；缺年先用 default_year，稍後若有 start 再對齊
        end_dt = _parse_date_token(end_str, default_year)
        if end_dt is None:
            continue

        start_dt: Optional[datetime] = None
        rel_version: Optional[str] = None
        start_raw: Optional[str] = None

        if _DATE_FULLMATCH.match(start_str):
            start_dt = _parse_date_token(start_str, default_year)
            # 結束缺年 → 沿用起始年份
            if start_dt and not _DATE_RE.search(end_str).group('y'):
                end_dt = end_dt.replace(year=start_dt.year)
        else:
            # 相對起點：擷取版本號交給上層回填；保留原字串供「即日起」判斷
            start_raw = start_str
            vm = _VERSION_RE.search(start_str)
            rel_version = vm.group(1) if vm else None

        # 跨年：結束早於起始 → 結束 +1 年（缺年導致）
        if start_dt and end_dt <= start_dt:
            end_dt = end_dt.replace(year=end_dt.year + 1)

        # 錨點前文（取活動名用）：優先抓最近的「章節標題行」，退回括號活動名
        title_hint = _clean_title_hint(text, m.start(), allow_bracket_fallback=multi) or fallback_title

        events.append(ParsedEvent(
            start=start_dt,
            end=end_dt,
            start_relative_version=rel_version,
            title_hint=title_hint,
            raw=text[m.start():min(len(text), m.end() + 12)].strip(),
            start_raw=start_raw,
        ))

    return events


_BRACKET_NAME = re.compile(r'[【「『\[]([^】」』\]\n]{1,40})[】」』\]]')

# 章節標題行辨識（喚取帖的「活動時間」上方那行才是活動名；
# 緊鄰的敘述句「活動期間，5星角色「X」、4星角色「Y」…提升！」會誤取到最後一個 4 星名）
_HEAD_WINDOW = 150            # 找標題行的回看範圍（含跨行）
_HEAD_MAX_LINES = 5           # 最多回看幾個非空行，避免吃到上一段落
_HEAD_DECO = ' 　​✦＊*※・‧•-－—:：|'
_HEAD_SENTENCE = '。！？，、；'                       # 出現＝敘述句，非標題
_HEAD_OPEN_BRACKET = '[【「『<＜〈《('                  # 標題多以括號活動名開頭
_HEAD_SUFFIX = ('活動', '喚取', '說明', '公告', '挑戰')  # 或以這些詞結尾
_HEAD_NOISE = re.compile(r'時間|日期|獎勵|獲得|領取|開放|\d\s*[:：]\s*\d|\*\s*\d|[~～]')
# UP 池列舉句：「活動期間，5星角色「愛彌斯」、4星角色「白芷」…喚取機率限時提升！」
# 這行的括號名是卡池內容而非活動名，取它會得到「燈燈」「悖論噴流」這種怪活動名。
_GACHA_POOL_LINE = re.compile(r'喚取機率|\d\s*星角色|\d\s*星武器')


def _looks_like_heading(line: str) -> bool:
    """該行像「章節標題」而非敘述句／時間行／獎勵行。"""
    s = line.strip(_HEAD_DECO)
    if not (2 <= len(s) <= 40):
        return False
    if any(c in s for c in _HEAD_SENTENCE):
        return False
    if _HEAD_NOISE.search(s):
        return False
    return s[0] in _HEAD_OPEN_BRACKET or s.endswith(_HEAD_SUFFIX)


def _clean_title_hint(text: str, anchor: int, *, allow_bracket_fallback: bool = True) -> str:
    """從錨點前文擷取活動名。

    優先：往回找最近的「章節標題行」（匯總帖/多期喚取帖唯一能區分各活動的位置）。
    次選（僅匯總帖）：最近一個括號名，再次：最後一段句子。
    單一活動帖找不到標題行時回 ""，由呼叫端退用貼文標題。
    """
    start = max(0, anchor - _HEAD_WINDOW)
    lines = text[start:anchor].split('\n')
    # 視窗把首行切成半句時丟掉它（殘句如「3:59（伺服器時間）」不算標題）
    if start > 0 and text[start - 1] != '\n' and len(lines) > 1:
        lines = lines[1:]

    seen = 0
    for line in reversed(lines):
        if not line.strip(_HEAD_DECO):
            continue
        seen += 1
        if seen > _HEAD_MAX_LINES:
            break
        if _looks_like_heading(line):
            return line.strip(_HEAD_DECO)[:40]

    if not allow_bracket_fallback:
        return ""

    pre = text[max(0, anchor - 90):anchor]
    if not pre:
        return ""
    # 次選：最近一個括號活動名（跨來源/匯總帖↔獨立貼文最穩定的識別）。
    # 跳過 UP 池列舉句與說明條列——那裡的括號名是 4 星角色/武器與內建名詞，不是活動名。
    for line in reversed(pre.split('\n')):
        if _GACHA_POOL_LINE.search(line) or line.strip()[:1] in ('※', '-', '－'):
            continue
        names = _BRACKET_NAME.findall(line)
        if names:
            return names[-1].strip()[:40]
    # 再次：切到最後一個句末/條列/裝飾之後的片段
    for boundary in ['✦', '※', '\n', '。', '！']:
        idx = pre.rfind(boundary)
        if idx != -1:
            pre = pre[idx + 1:]
    return pre.strip(' 　・-—:：')[:40]


# ── 指紋（跨來源去重；對抗審查確認必含 start/end，title 為輔） ──

_NORM_STRIP = re.compile(r'[\s　【】\[\]「」『』（）()✦＊*※・,，。!！~～\-—:：|/\\]+')


def normalize_title(title: str) -> str:
    """活動名正規化：剝裝飾/標點/空白，保留核心字。供跨來源指紋比對。

    跨來源穩定度：Article 標題常多一個 `[詩意標籤]`、FB 沒有，但兩者通常都帶
    `「角色/武器名」`。故優先取「」『』內的核心名，沒有才退用【】[] tag，再退全文。
    """
    if not title:
        return ""
    quoted = re.findall(r'[「『]([^」』\n]{1,30})[」』]', title)
    if quoted:
        base = ''.join(quoted)
    else:
        tags = re.findall(r'[【\[]([^】\]\n]{1,40})[】\]]', title)
        base = ''.join(tags) if tags else title
    return _NORM_STRIP.sub('', base).lower()


def event_fingerprint(title: str, start: datetime, end: datetime) -> str:
    """跨來源活動指紋 = normalize(title) | start | end（正規化到整分，避免 1 分鐘差漏命中）。"""
    s = start.astimezone(SERVER_TZ).strftime('%Y%m%d%H%M')
    e = end.astimezone(SERVER_TZ).strftime('%Y%m%d%H%M')
    return f"{normalize_title(title)}|{s}|{e}"
