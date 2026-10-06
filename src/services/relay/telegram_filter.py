"""Telegram 訊息轉進 Discord 前，讓主模型判斷有沒有《鳴潮》的遊戲資訊。

**為什麼**：來源是兩個內鬼爆料頻道，偶爾混進頻道管理員自己的灌水、閒聊、罵人，或跟遊戲無關的梗圖
（使用者 09-28 提出、10-05 定案）。關鍵字做不到：含「水」的 85 則只有約 10 則是灌水，很短的文字多半是
情報（「亚服」「V2来了」），文字只有「水」的那則圖卻是角色設計稿（13649）——所以**一定要看圖**。

判斷標準（使用者 10-05 定案）：
- 文字或任一張圖有遊戲資訊就放行；拿不準放行。
- 模型不能用就放行：產圖佔著 GPU、排隊或回答超過 `wait_seconds`、出錯、回答看不懂。寧可漏掉一則垃圾，
  不能擋掉一則情報。
- 每個發送單位（單則或整本相簿）判一次，最多看 `max_images` 張圖：前幾個媒體各一張，媒體不到這個數時，
  剩下的名額給動圖與影片多抽幾格（GIF、動態 WebP 用 `extract_key_frames`，影片用 `video_key_frames`，
  挑幀規則只有一份）。音訊、壓縮檔不看。

這裡只負責判斷；判完送去哪裡由轉發端決定（`mode`、隔離 thread）。
"""
from __future__ import annotations

import asyncio
import base64
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional, Sequence

from llm.client import lemonade_gate
from llm.preprocess.vision_image import extract_key_frames, fit_for_vision, video_key_frames
from llm.prompt import prompt_files
from llm.prompt.answer_line import answer_lines, final_line
from sys_settings import switches
from sys_settings.telegram_relay_settings import TelegramFilterSettings

logger = logging.getLogger(__name__)

_SETTINGS = TelegramFilterSettings()
_LLM = None

#: 隔離時的標籤（prompt 裡列的那幾個）；模型寫了別的就記成「其他」
LABELS = ("灌水", "閒聊", "罵人", "無關圖片")
_VERDICT = re.compile(r"^(放行|隔離)\s*(?:[｜|]\s*(.*))?$")
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
_VIDEO_EXTS = {".mp4", ".webm", ".mov", ".mkv", ".m4v"}


@dataclass(frozen=True)
class MediaFile:
    path: Path
    #: image／video／other（other 不給模型看：音訊、壓縮檔、Lottie 貼圖）
    kind: str


@dataclass(frozen=True)
class Verdict:
    quarantine: bool
    #: 隔離時是 LABELS 之一（或「其他」）；放行時空字串
    label: str = ""
    reason: str = ""
    #: 有沒有真的由模型判斷；False＝模型不能用而放行（`reason` 寫原因）
    by_model: bool = True
    images_seen: int = 0
    seconds: float = 0.0
    answer: str = field(default="", repr=False)


def media_kind(media_type: Optional[str], mime_type: Optional[str], path: str) -> str:
    """媒體列 → image／video／other。爬蟲的 media_type、mime 不完全可信（有 mime 是空的 .jpg），副檔名當後備。"""
    mime = (mime_type or "").lower()
    kind = (media_type or "").lower()
    ext = Path(path).suffix.lower()
    if kind == "photo" or mime.startswith("image/") or (kind in ("image", "unknown", "") and ext in _IMAGE_EXTS):
        return "image"
    if mime.startswith("video/") or kind == "video" or ext in _VIDEO_EXTS:
        return "video"
    return "other"


def parse_verdict(answer: str) -> Optional[tuple[bool, str, str]]:
    """模型回答 →（要不要隔離, 標籤, 理由）；看不懂回 None（呼叫端當放行）。

    不合格式的一律看不懂：最後一行不是結論、好幾行結論互相矛盾（例如答完又照抄範例）、思考區塊沒收尾、
    只寫「隔離」沒有標籤。
    """
    m = _VERDICT.match(final_line(answer))
    if not m:
        return None
    verdicts = {v.group(1) for v in (_VERDICT.match(line) for line in answer_lines(answer)) if v}
    if len(verdicts) > 1:
        return None
    parts = [p.strip() for p in re.split(r"[｜|]", m.group(2) or "") if p.strip()]
    if m.group(1) == "放行":
        return False, "", "｜".join(parts)[:40]
    if not parts:
        return None
    if parts[0] in LABELS:
        return True, parts[0], "｜".join(parts[1:])[:40]
    return True, "其他", "｜".join(parts)[:40]


def _image_frames(path: Path, allowance: int) -> list[bytes]:
    """圖檔 → 給模型看的 JPEG（動圖拆幀）。讀不到、太大、打不開回空清單。在執行緒裡跑。"""
    try:
        if path.stat().st_size > _SETTINGS.image_max_bytes:
            logger.info("Telegram 過濾：圖檔太大不看 %s", path)
            return []
        data = path.read_bytes()
    except OSError as exc:
        logger.info("Telegram 過濾：讀不到圖檔 %s（%s）", path, exc)
        return []
    return _fit_all(extract_key_frames(data, max_frames=allowance))


def _fit_all(frames: list[bytes]) -> list[bytes]:
    return [f for f in (fit_for_vision(x, max_side=_SETTINGS.image_max_side) for x in frames) if f]


async def collect_images(media: Sequence[MediaFile]) -> list[bytes]:
    """一個發送單位的媒體 → 給模型看的圖（JPEG），最多 `max_images` 張。"""
    images, _ = await _collect(media)
    return images


async def _collect(media: Sequence[MediaFile]) -> tuple[list[bytes], int]:
    """→（給模型看的圖, 該看卻一張都沒看到的媒體數）。相簿超過 `max_images` 個媒體時，後面的本來就不看，不算沒看到。"""
    visual = [m for m in media if m.kind in ("image", "video")][: _SETTINGS.max_images]
    extra = _SETTINGS.max_images - len(visual)
    out: list[bytes] = []
    unseen = 0
    for m in visual:
        allowance = 1 + extra
        if m.kind == "image":
            got = await asyncio.to_thread(_image_frames, m.path, allowance)
        else:
            raw = await video_key_frames(m.path, allowance, max_side=_SETTINGS.image_max_side,
                                         sample_frames=_SETTINGS.video_sample_frames,
                                         timeout=_SETTINGS.video_timeout_seconds)
            got = await asyncio.to_thread(_fit_all, raw)
        # 每個媒體至少一張、多抽的從剩下的名額扣，總數不會超過 max_images
        extra -= max(0, len(got) - 1)
        out.extend(got)
        if not got:
            unseen += 1
    return out, unseen


def _get_llm():
    global _LLM
    if _LLM is None:
        from services.llm_service import LLMService
        _LLM = LLMService()
    return _LLM


def _user_message(text: str, image_count: int) -> str:
    text = (text or "").strip()
    if len(text) > _SETTINGS.max_text_chars:
        text = text[: _SETTINGS.max_text_chars] + "……（後面省略）"
    head = f"文字：「{text}」" if text else "文字：（沒有文字）"
    tail = f"（附圖 {image_count} 張）" if image_count else "（沒有圖）"
    return f"{head}\n{tail}"


async def _ask_model(text: str, images: list[bytes], trace_id: str) -> str:
    system = prompt_files.read_text(_SETTINGS.prompt_path, label="Telegram 過濾 prompt")
    if not system:
        raise RuntimeError("讀不到 prompt")
    llm = _get_llm()
    user: dict = {"role": "user", "content": _user_message(text, len(images))}
    if images:
        user["images"] = [base64.b64encode(img).decode("ascii") for img in images]
    return await llm.chat_raw(
        model=llm.resolve_request_model(),
        messages=[{"role": "system", "content": system}, user],
        think=False,
        temperature=0.2,
        timeout=_SETTINGS.request_timeout_seconds,
        trace_id=trace_id,
    )


def _passed(reason: str, started: float, images: int = 0, answer: str = "") -> Verdict:
    return Verdict(False, reason=reason, by_model=False, images_seen=images,
                   seconds=time.monotonic() - started, answer=answer)


async def judge(text: str, media: Iterable[MediaFile], *, trace_id: str) -> Verdict:
    """判斷一個發送單位。任何失敗都回放行（`by_model=False`），不拋例外。"""
    started = time.monotonic()
    images: list[bytes] = []
    try:
        if lemonade_gate.imagegen_busy():
            return _passed("產圖中，模型不能用", started)
        media = list(media)
        if any(m.kind == "other" for m in media):
            # 語音、壓縮檔模型看不了：歷史上有好幾則語音爆料沒有文字，當成「什麼都沒有」會被錯關
            return _passed("附有看不了的檔案（語音、壓縮檔）", started)
        images, unseen = await _collect(media)
        if unseen:
            # 有圖或影片沒看到（檔案讀不到、抽幀失敗）：只憑其他部分判，會把「水」配設計稿那種錯關（13649）
            return _passed("有圖或影片沒看到", started, len(images))
        answer = await asyncio.wait_for(_ask_model(text, images, trace_id), _SETTINGS.wait_seconds)
    except asyncio.TimeoutError:
        return _passed(f"等模型超過 {_SETTINGS.wait_seconds:g} 秒", started, len(images))
    except Exception as exc:
        logger.warning("Telegram 過濾：判斷失敗，放行（%s）：%s", trace_id, exc)
        return _passed(f"判斷失敗：{type(exc).__name__}", started, len(images))
    parsed = parse_verdict(answer)
    if parsed is None:
        return _passed("看不懂模型的回答", started, len(images), answer)
    quarantine, label, reason = parsed
    return Verdict(quarantine, label=label, reason=reason, images_seen=len(images),
                   seconds=time.monotonic() - started, answer=answer)


class RelayFilter:
    """轉發端用的過濾：目前的模式與判斷（測試換成假的，不打模型）。"""

    @property
    def mode(self) -> str:
        """`settings/switches.json` 的 `telegram_filter_mode`；每則重讀（檔案改了才重新解析），改了就生效。"""
        return switches.current().telegram_filter_mode

    async def judge(self, text: str, media: Iterable[MediaFile], *, trace_id: str) -> Verdict:
        return await judge(text, media, trace_id=trace_id)

