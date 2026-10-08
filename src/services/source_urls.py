"""來源文章的原文網址（**唯一來源**）。

官方公告原本由轉發（article_monitor）與自動建活動（event_scheduler）共用一份，巴哈「精確樓層」
網址原本只有社群稽查在組；情報搜尋也要給這兩種連結，所以抽到這裡。刻意不依賴 discord 套件：
搜尋程式跑在獨立的 MCP 行程裡，不該為了組一個網址把整個 bot 拖進來。
"""
from __future__ import annotations

from typing import Optional

OFFICIAL_ARTICLE_URL = "https://wutheringwaves.kurogames.com/zh-tw/main/news/detail/{article_id}"

# Co.php?bsn=…&sn=… 直接跳到那一樓；scraper 存的 C.php?snA=… 只到討論串
BAHAMUT_FLOOR_URL = "https://forum.gamer.com.tw/Co.php?bsn={board_id}&sn={sn}"


def official_article_url(article_id) -> Optional[str]:
    """官方公告原文網址；article_id 缺失時回 None（embed url 傳 None 等同不設）。"""
    if article_id in (None, "", "unknown"):
        return None
    return OFFICIAL_ARTICLE_URL.format(article_id=article_id)


def bahamut_floor_url(board_id, sn) -> Optional[str]:
    """巴哈某一樓的網址；缺 board_id 或 sn 時回 None，由呼叫端退回討論串網址。"""
    if not board_id or not sn:
        return None
    return BAHAMUT_FLOOR_URL.format(board_id=board_id, sn=sn)
