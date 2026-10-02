"""看到沒描述的表情或貼圖時，背景讓模型看圖、把描述寫進字典。

**為什麼**：別的伺服器的表情與貼圖不可控，名稱常常沒意義（`252`、`FR16`、`1A`），模型只看得到名稱就
不知道對方在回什麼；本伺服器的新表情則多半只填了類別字（`let_me_see_see = think`）。使用者 10-02：
「當下看到就回填，沒看到的沒關係」。

- 對象：表情字典沒登錄（別的伺服器）或描述空白／只有類別字的表情；不在本伺服器、也還沒記進
  `sticker_dictionary` 的貼圖（Lottie 沒圖檔，跳過）。使用者寫過的描述一律不動。
- 每個只看一次：寫進字典就查得到，之後文字直接換成描述、回覆時也不再下載圖（`external_emoji`）。
- 當下那次回覆不等這裡——回覆照 `external_emoji` 直接看圖；這裡在背景跑，補的是之後的每一次。
- 節流：一次只看一張（`_lock`）、每天上限、看不出來或失敗的隔 `retry_hours` 才再看、04:00 維護時段不跑。
- `mode`：dry_run 只寫 log 不寫檔（上線先抽查），on 才寫入。
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from llm.preprocess import emoji_dictionary, sticker_cache, sticker_dictionary
from llm.preprocess.external_emoji import custom_emojis, sticker_image_url
from llm.preprocess.vision_image import download_images
from llm.prompt import prompt_files
from sys_settings.llm_settings import EmojiAutofillSettings
from sys_settings.time_settings import APP_TZ

logger = logging.getLogger(__name__)

_SETTINGS = EmojiAutofillSettings()

_lock = asyncio.Lock()
#: 正在排隊或處理中的對象，同一個表情連發好幾則時只看一次
_in_flight: set[str] = set()
#: 對象 → 這個時間之前不再看（看不出來、失敗、試跑看過）
_retry_after: dict[str, float] = {}
#: (日期, 今天已看幾張)
_quota: list = ["", 0]
_LLM = None

_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.S)


@dataclass(frozen=True)
class Target:
    #: emoji／sticker
    kind: str
    #: 去重與節流用的鍵：`emoji:名稱`、`sticker:ID`
    key: str
    name: str
    url: str
    sticker_id: Optional[int] = None


def targets(message: Any) -> list[Target]:
    """這則訊息裡需要補描述的表情與貼圖。只查字典，不連網。"""
    known = emoji_dictionary.entries()
    out: dict[str, Target] = {}
    for name, _emoji_id, url in custom_emojis(getattr(message, "content", "") or ""):
        entry = known.get(name)
        if entry is None or entry.needs_description:
            out.setdefault(f"emoji:{name}", Target("emoji", f"emoji:{name}", name, url))
    for st in getattr(message, "stickers", None) or ():
        sticker_id = getattr(st, "id", 0)
        if sticker_cache.is_known(sticker_id) or sticker_dictionary.lookup(sticker_id):
            continue
        url = sticker_image_url(st)
        if url:
            key = f"sticker:{sticker_id}"
            out.setdefault(key, Target("sticker", key, str(getattr(st, "name", "")), url, int(sticker_id)))
    return list(out.values())


def parse_answer(text: str, *, max_chars: int) -> Optional[tuple[str, Optional[str]]]:
    """模型回答 →（描述, 類別）。看不出來、格式不對、太長、只有類別字都回 None——寧可不寫。

    prompt 要模型先寫一行「看到什麼」再寫字典那行（直接要字典那行時，十張有五張回「不知道」，
    其實圖都看得清楚），所以取**最後一行**。
    """
    text = _THINK_BLOCK.sub("", text or "")
    lines = [ln.strip().strip("`").strip() for ln in text.splitlines()]
    line = next((ln for ln in reversed(lines) if ln), "")
    if not line or "不知道" in line:
        return None
    entry = emoji_dictionary.parse_line(f"_ = {line}")
    if entry is None:
        return None
    desc = entry.description.strip().strip("「」『』\"'").strip()
    if (not desc or len(desc) > max_chars or any(c in desc for c in "=|#")
            or desc.lower() in emoji_dictionary.VALID_CATEGORIES):
        return None
    return desc, entry.category


def _minutes(hhmm: str) -> int:
    hour, _, minute = hhmm.partition(":")
    return int(hour) * 60 + int(minute or 0)


def _in_quiet_hours(now: datetime) -> bool:
    start, end, t = _minutes(_SETTINGS.quiet_start), _minutes(_SETTINGS.quiet_end), now.hour * 60 + now.minute
    return start <= t < end if start <= end else (t >= start or t < end)


def _take_quota(now: datetime) -> bool:
    today = now.strftime("%Y-%m-%d")
    if _quota[0] != today:
        _quota[0], _quota[1] = today, 0
    if _quota[1] >= _SETTINGS.daily_limit:
        return False
    _quota[1] += 1
    return True


def _still_needed(t: Target) -> bool:
    """排隊時字典可能已經被補了（使用者手改、或前一則剛寫入）。"""
    if t.kind == "emoji":
        entry = emoji_dictionary.entries().get(t.name)
        return entry is None or entry.needs_description
    return not sticker_dictionary.lookup(t.sticker_id)


def _context_lines(message: Any) -> list[str]:
    """出現的那則訊息（有回覆對象就加上被回覆的那則），給模型猜用途。"""
    from llm.preprocess.chat_line import semantic_message_text

    limit = _SETTINGS.max_context_chars
    lines: list[str] = []
    replied = getattr(getattr(message, "reference", None), "resolved", None)
    if replied is not None and hasattr(replied, "content"):
        text = " ".join(semantic_message_text(replied).split())
        if text:
            lines.append(f"（被回覆的訊息）{text[:limit]}")
    text = " ".join(semantic_message_text(message).split())
    lines.append(text[:limit] if text else "（只有這個表情或貼圖）")
    return lines


def _now() -> datetime:
    return datetime.now(APP_TZ)


def _session():
    import aiohttp
    return aiohttp.ClientSession()


def _get_llm():
    global _LLM
    if _LLM is None:
        from services.llm_service import LLMService
        _LLM = LLMService()
    return _LLM


async def _ask_model(t: Target, image: str, context: list[str]) -> str:
    system = prompt_files.read_text(_SETTINGS.prompt_path, label="看圖補字典 prompt")
    if not system:
        return ""
    kind = "表情" if t.kind == "emoji" else "貼圖"
    user = f"種類：{kind}\n名稱：{t.name}\n出現的訊息：\n" + "\n".join(context)
    llm = _get_llm()
    return await llm.chat_raw(
        model=llm.resolve_request_model(),
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user, "images": [image]}],
        think=False,
        temperature=0.2,
        timeout=_SETTINGS.timeout_seconds,
        trace_id=f"autofill-{t.key}",
    )


def _write(t: Target, desc: str, category: Optional[str]) -> bool:
    if t.kind == "emoji":
        return emoji_dictionary.fill(t.name, desc, category, backup_dir=_SETTINGS.backup_dir,
                                     backup_keep=_SETTINGS.backup_keep)
    return sticker_dictionary.add(t.sticker_id, t.name, desc, backup_dir=_SETTINGS.backup_dir,
                                  backup_keep=_SETTINGS.backup_keep)


async def _handle(t: Target, context: list[str], session) -> None:
    now = _now()
    if _in_quiet_hours(now) or not _still_needed(t):
        return
    if not _take_quota(now):
        logger.info("看圖補字典：今天已達上限 %d 張，%s 等下次被看到再補", _SETTINGS.daily_limit, t.key)
        return
    # 先記下次可再看的時間：看不出來、失敗都要等；寫入成功的本來就不會再被挑中
    _retry_after[t.key] = time.time() + _SETTINGS.retry_hours * 3600
    images = await download_images(session, [t.url], limit=1)
    if not images:
        logger.info("看圖補字典：下載不到圖 %s（%s）", t.key, t.url)
        return
    answer = await _ask_model(t, images[0], context)
    parsed = parse_answer(answer, max_chars=_SETTINGS.max_description_chars)
    if parsed is None:
        logger.info("看圖補字典：看不出來或格式不對，%s → %r（%s）", t.key, answer, t.url)
        return
    desc, category = parsed
    if _SETTINGS.mode != "on":
        logger.info("看圖補字典（試跑，未寫入）：%s → %s | %s（%s）", t.key, desc, category, t.url)
        return
    written = await asyncio.to_thread(_write, t, desc, category)
    if written:
        logger.info("看圖補字典：已寫入 %s → %s | %s（%s）", t.key, desc, category, t.url)
    else:
        logger.info("看圖補字典：%s 已經有描述，不覆寫", t.key)


async def observe(message: Any) -> None:
    """`on_message` 用背景 task 呼叫。沒有對象時只查幾次字典就返回；任何錯誤都只記 log。"""
    try:
        if _SETTINGS.mode == "off" or getattr(getattr(message, "author", None), "bot", False):
            return
        now = time.time()
        pending = [t for t in targets(message)
                   if t.key not in _in_flight and _retry_after.get(t.key, 0) <= now]
        if not pending:
            return
        context = _context_lines(message)
        _in_flight.update(t.key for t in pending)
        try:
            async with _lock:
                async with _session() as session:
                    for t in pending:
                        try:
                            await _handle(t, context, session)
                        except Exception as exc:
                            logger.warning("看圖補字典失敗 %s：%s", t.key, exc)
        finally:
            _in_flight.difference_update(t.key for t in pending)
    except Exception as exc:
        logger.warning("看圖補字典失敗：%s", exc)
