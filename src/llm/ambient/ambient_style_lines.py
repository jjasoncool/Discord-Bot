"""插話的語氣參考句：每次從預設句庫與學到的句子抽幾句放進 user 段，提醒她同一種場面可以有哪些冷熱與節奏。

架構定位：功能層（`llm/ambient`）。上層：`ambient_reply` 組插話輸入時呼叫。下層：`utils.hot_files`（預設句庫）、
`llm.storage.ai_interactions_store`（學到的句子）、`llm.persona.member_names`（過濾提到群友的句子）。

介面：
- `enabled()`：開關 `ambient_seed_lines_mode` 是不是 on。
- `pick(names)`：這次要給模型看的幾行；句庫讀不到回 None。`names` 是取群友名字片段的 async 函式，有學到的句子時才呼叫。
- `NOTE`：這些句子在 prompt 裡的開頭說明。

規則：
- 放 user 段，不放 system：每次都換句子又不讓提示詞快取失效。
- 學到的句子變多，預設句跟著減少，但一直留至少一句：群友的反應分不出語氣，模型又會吸收句子的節奏，全換成
  學到的句子會一直模仿自己。
- 抽學到的句子不看和當下情境像不像：太像的範例容易被照抄，隨機抽也省一次 embedding。
- 學到的句子只來自 `learned_since` 之後（換人格前的句子是另一種聲音），過濾名字、數字、AI 自我話題與性話題，
  只存在資料庫，不寫進會公開的預設句庫。
- 讀不到學到的句子就只用預設句；其他例外往外丟，由呼叫端當成這次沒有參考句。
"""
from __future__ import annotations

import asyncio
import logging
import random
import re
import time
from collections import deque
from typing import Awaitable, Callable, Iterable, Optional

from llm.persona.member_names import query_names_member
from llm.storage.ai_interactions_store import fetch_learned_lines
from sys_settings import switches
from sys_settings.llm_settings import AmbientChatSettings
from utils import hot_files

logger = logging.getLogger(__name__)

_SETTINGS = AmbientChatSettings()
#: 看時間走這個名字，測試才換得掉
_clock = time.monotonic

TONES = ("冷", "暖", "逗")
NOTE = (
    "（以下是你可能會講的幾種話，只用來提醒你同一種場面可以有哪些冷熱和節奏，不是要你現在講這些。"
    "**只學那個味道，千萬別照抄字句、別逐字重複**；這次請用當下的話題、講你自己的新句子。"
    "看氣氛挑一種感覺，或全部不用。）"
)

NamesProvider = Callable[[], Awaitable[Iterable[str]]]

#: 學到的句子不重用的內容：數字多半是當時的事、提到 AI 的多半是在講自己是機器人、性話題當範例等於鼓勵主動開黃腔
_NOT_REUSABLE = re.compile(r"\d|#|https?://|AI|機器人|bot|胸|奶|屁股|內褲|裸|色色|做愛|上床", re.IGNORECASE)

#: 最近用過的句子，下次先避開（壓跳針）
_recent: deque[str] = deque(maxlen=_SETTINGS.seed_lines_recent_size)
#: 學到的句子快取：(過期時刻, learned_since, 句子)
_learned_cache: Optional[tuple[float, str, list[str]]] = None


def enabled() -> bool:
    return switches.current().ambient_seed_lines_mode == "on"


def _reusable(line: str) -> bool:
    return 0 < len(line) <= _SETTINGS.seed_lines_learned_max_chars and not _NOT_REUSABLE.search(line)


async def _learned_lines(since: Optional[str]) -> list[str]:
    """`since` 之後學到、內容可重用的句子；一小時重查一次（每次插話都查太浪費，句子也不會一下子變很多）。"""
    global _learned_cache
    if not since:
        return []
    now = _clock()
    if _learned_cache is not None and now < _learned_cache[0] and _learned_cache[1] == since:
        return _learned_cache[2]
    rows = await asyncio.to_thread(fetch_learned_lines, since)
    # 去重：同一句算好幾次，名額會被它撐開，那句就每次都出現
    lines = list(dict.fromkeys(text for text in (" ".join((r or "").split()) for r in rows) if _reusable(text)))
    _learned_cache = (now + _SETTINGS.seed_lines_learned_ttl_seconds, since, lines)
    return lines


def _learned_slots(count: int) -> int:
    """學到幾句時，這次要放幾句學到的；其餘名額給預設句，所以預設句不會淡到零。"""
    if count >= _SETTINGS.seed_lines_learned_more_at:
        return _SETTINGS.seed_lines_per_turn - 1
    return 1 if count >= _SETTINGS.seed_lines_learned_start_at else 0


def _choose(pool: list[str]) -> str:
    """從 pool 抽一句，先避開最近用過的；都用過了就全部一起抽。"""
    fresh = [p for p in pool if p not in _recent]
    choice = random.choice(fresh or pool)
    _recent.append(choice)
    return choice


async def pick(names: NamesProvider) -> Optional[list[str]]:
    """這次要放進 prompt 的幾行。句庫讀不到或沒有句子回 None（照沒有參考句處理）。"""
    data = hot_files.read_json(_SETTINGS.seed_lines_path, label="插話預設句庫")
    rows = [r for r in (data or {}).get("lines") or [] if isinstance(r, dict) and r.get("line")]
    if not rows:
        return None
    learned = await _learned_lines((data or {}).get("learned_since"))
    slots = _learned_slots(len(learned))
    if slots:
        parts = list(await names())
        learned = [line for line in learned if query_names_member(line, parts) is None]
        slots = _learned_slots(len(learned))    # 名額照過濾後的句數算：濾到只剩幾句時不該每次都是那幾句

    by_line = {r["line"]: r for r in rows}
    tones = [t for t in TONES if any(r.get("tone") == t for r in rows)]
    random.shuffle(tones)
    seeds = []
    for tone in tones[:_SETTINGS.seed_lines_per_turn - slots]:
        seeds.append(_choose([r["line"] for r in rows if r.get("tone") == tone]))
    lines = [f"・（{by_line[s].get('context') or '當時'}）{s}" for s in seeds]
    lines += [f"・（你之前講過）{_choose(learned)}" for _ in range(slots)]
    random.shuffle(lines)
    if _SETTINGS.style_refs_debug:
        logger.info("ambient 語氣句 預設=%d 學到=%d（可用 %d）| %s", len(seeds), slots, len(learned), " ‖ ".join(lines))
    return lines
