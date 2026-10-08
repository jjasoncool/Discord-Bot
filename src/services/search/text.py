"""搜尋用的文字處理：公告 HTML 轉純文字，以及建索引與查詢**共用**的正規化。

正規化一定要兩邊用同一套：文件存進索引前做、查詢字也做，比對才會一致。
"""
from __future__ import annotations

import logging
import re
import unicodedata
from functools import lru_cache

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


_BLOCK_TAGS = ["p", "div", "li", "br", "tr", "table", "ul", "ol", "section",
               "h1", "h2", "h3", "h4", "h5", "h6"]


def html_to_text(html: str | None) -> str:
    """官網公告存的是 HTML：去掉標籤，每個區塊一行，去空行。"""
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    # 只在區塊標籤後面換行；行內標籤（<b>、<span>）若也斷行，「深塔<b>海墟</b>」會被拆開而搜不到
    for block in soup.find_all(_BLOCK_TAGS):
        block.insert_after("\n")
    lines = (line.strip() for line in soup.get_text("").splitlines())
    return "\n".join(line for line in lines if line)


@lru_cache(maxsize=1)
def _converter():
    """簡轉繁的轉換器；沒裝 opencc 時回 None，搜尋照常可用，只是簡體內容會漏。"""
    try:
        import opencc
    except ImportError:
        logger.warning("沒有安裝 opencc：簡體字不會轉成繁體，搜尋簡體寫的內容會漏")
        return None
    return opencc.OpenCC("s2t.json")


def has_chinese_converter() -> bool:
    return _converter() is not None


def normalizer_id() -> str:
    """正規化方式的代號。索引記著建立時用的代號，代號變了（例如裝上 opencc）就整份重建。"""
    return "nfkc+s2t" if has_chinese_converter() else "nfkc"


def normalize(text: str | None) -> str:
    """全形轉半形（NFKC）＋簡轉繁。不轉大小寫：全文索引與 LIKE 本來就不分英文大小寫。"""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    converter = _converter()
    return converter.convert(text) if converter else text


# 中日韓文字（含假名、諺文）連成一串的部分；其餘取英數字
_CJK_RUN = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uac00-\ud7af]+")
_TOKEN = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uac00-\ud7af]+|[0-9a-z]+")


def bigram_tokens(text: str | None) -> list[str]:
    """中文切成「兩個字一組」（相鄰重疊），英數字整串當一個詞。

    為什麼是兩個字：中文沒有空格，又不想為了斷詞引進詞典（角色名、暱稱一直在增加）。兩字一組是
    傳統中文全文搜尋的做法——「卜靈是什麼身分」切成 卜靈／靈是／是什／什麼／麼身／身分，交給 BM25
    之後，到處都有的「什麼」權重很低、少見的「卜靈」權重很高，不必斷詞也排得對。
    只有一個字、前後都不是中文的（例如單獨出現的「椿」）保留那一個字。輸入要先 `normalize`。
    """
    tokens = []
    for run in _TOKEN.findall((text or "").lower()):
        if _CJK_RUN.fullmatch(run):
            tokens += [run] if len(run) == 1 else [run[i:i + 2] for i in range(len(run) - 1)]
        else:
            tokens.append(run)
    return tokens
