"""解析使用者在 Discord 視窗裡打的日期與時間。

Discord 沒有日期選擇器，日期一律靠文字輸入（社群稽查的起訖日、商品的預購截止）。
這裡只管「把人打的字讀成日期」，而且讀得寬鬆：全形字自動轉半形、`2026/10/20`、`2026-10-20`、
`2026.10.20`、`2026年10月20日`、`20261020` 都收，月、日、時可以只寫一位數。
年份一定要寫四位數（跨年時才不會猜錯）。

讀不懂回 None，錯誤訊息由呼叫端寫（各功能的範例不同）；「不能是未來」「最多幾天」這類規則也留給呼叫端。
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, time
from typing import Optional

_DATE = (r"(?:(?P<y>\d{4})\s*[-/.年]\s*(?P<m>\d{1,2})\s*[-/.月]\s*(?P<d>\d{1,2})\s*日?"
         r"|(?P<cy>\d{4})(?P<cm>\d{2})(?P<cd>\d{2}))")
_TIME = r"(?P<H>\d{1,2})\s*:\s*(?P<M>\d{2})"
_PATTERN = re.compile(rf"{_DATE}(?:\s+{_TIME})?")


def _match(text: str) -> Optional[re.Match]:
    # NFKC：全形數字與符號（２０２６／１０／２０　２３：５９）轉成半形
    return _PATTERN.fullmatch(unicodedata.normalize("NFKC", text or "").strip())


def _date_of(match: re.Match) -> Optional[date]:
    y, m, d = (match["y"], match["m"], match["d"]) if match["y"] else (match["cy"], match["cm"], match["cd"])
    try:
        return date(int(y), int(m), int(d))
    except ValueError:  # 2/30 這類不存在的日期
        return None


def parse_user_date(text: str) -> Optional[date]:
    """只要日期的欄位。多寫了時間也算讀不懂（免得使用者以為時間有作用）。"""
    match = _match(text)
    if match is None or match["H"] is not None:
        return None
    return _date_of(match)


def parse_user_datetime(text: str, *, default_time: Optional[time] = None) -> Optional[datetime]:
    """日期＋時間的欄位，回傳不帶時區的 datetime（時區由呼叫端決定）。
    只寫日期時用 default_time；沒給 default_time 就一定要寫時間。"""
    match = _match(text)
    if match is None:
        return None
    day = _date_of(match)
    if day is None:
        return None
    if match["H"] is None:
        return None if default_time is None else datetime.combine(day, default_time)
    try:
        return datetime.combine(day, time(int(match["H"]), int(match["M"])))
    except ValueError:  # 25:00、23:60
        return None
