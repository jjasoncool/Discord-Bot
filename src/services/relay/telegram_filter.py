"""Telegram 訊息轉進 Discord 前判斷該不該進主頻道：文字點名別款遊戲就隔離，其餘讓主模型看文字和圖判斷有沒有《鳴潮》的遊戲資訊。

架構定位
  層級：功能層（services.relay）。只負責判斷；判完送去哪裡由轉發端決定（`mode`、隔離 thread）。
  上層（誰呼叫）：services.relay.telegram_relay_service（新訊息、補判）、scripts/telegram_move_to_quarantine.py、
    commands.admin_status（名單檔的狀態）、手動抽查 test.integration.it_telegram_filter。
  下層（呼叫誰）：services.llm_service（模型）、llm.client（GPU 閘門、錯誤型別）、llm.preprocess.vision_image（縮圖、抽幀）、
    utils.hot_files（prompt、名單）、sys_settings（開關、細項）。

介面
  judge(text, media, trace_id=)  判斷一個發送單位；判不了回放行（`by_model=False`），不拋例外
  other_game_verdict(text)       只看文字：點名別款遊戲回隔離的判定，否則 None；不碰模型，圖沒到齊時也能用
  other_games_problem()          名單檔現在讀不讀得起來（給狀態面板）
  media_kind(…)                  媒體列 → image／video／other
  parse_verdict(answer)          模型回答 → 判定；看不懂回 None
  collect_images(media)          發送單位的媒體 → 給模型看的 JPEG
  RelayFilter                    轉發端用的介面：目前的模式與上面兩種判斷（測試換成假的，不打模型）

規則
  1. 文字點名 `settings/telegram_other_games.json` 的遊戲就隔離，不問模型，排在所有放行路徑前面；
     同一則也提到鳴潮就交回模型判，免得比較貼文被關。名單手改、下一則生效，寫壞了沿用上次的內容。
  2. 文字或任一張圖有遊戲資訊就放行；拿不準放行。
  3. 模型忙就排隊、不放行：排在插話、產圖、別的行程後面；模型逾時或連不上就等一下再問。
     轉發開著過濾時一次只處理一則，後面的訊息跟著排隊，晚一點送但不會漏判。
  4. 排了 `give_up_seconds` 還判不到才放行，並認定模型掛了：之後每則只問一次、失敗就放行，
     有一次問到就恢復排隊。
  5. 判不了的放行：看不了的檔案（語音、壓縮檔）、有圖沒看到、讀不到 prompt、模型回錯誤、回答看不懂。
  6. 每個發送單位（單則或整本相簿）判一次，最多看 `max_images` 張圖：前幾個媒體各一張，媒體不到這個數時，
     剩下的名額給動圖與影片多抽幾格（挑幀規則只有 vision_image 一份）。音訊、壓縮檔不看。

例外與決策
  - 灌水不靠關鍵字、一定要看圖：來源頻道的管理員偶爾灌水、閒聊、罵人，但含「水」的 85 則只有約 10 則是灌水，
    很短的文字多半是情報（「亚服」「V2来了」），文字只有「水」的那則圖卻是角色設計稿（13649）。
  - 別款遊戲靠名單不靠模型：模型會把「NTE 1.5 …」當成爆料放行，語音與圖沒到齊的路又根本不經模型；
    遊戲名字沒有「水」那種歧義，提到名字就是在講那款遊戲。沒寫名字的連發貼文比不到，算到放行這邊。
  - 寧可漏掉一則垃圾，不能擋掉一則情報：放行是所有判不了的情況的出口。
  - 30 分鐘是給正常排隊留的餘裕（插話一次最多 3 分鐘、/askai 5 分鐘）；模型壞了情報也不能卡好幾個小時，
    認定掛了之後不再每則等滿，否則一次一則、5 則就卡 2.5 小時。
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Iterable, Optional, Sequence

from pydantic import BaseModel, Field, StringConstraints

from llm.client import gpu_gate
from llm.client.http_client import LlmConnectionError, LlmTimeoutError
from llm.preprocess.vision_image import extract_key_frames, fit_for_vision, video_key_frames
from utils import hot_files
from llm.prompt.answer_line import answer_lines, final_line
from sys_settings import switches
from sys_settings.telegram_relay_settings import TelegramFilterSettings

logger = logging.getLogger(__name__)

_SETTINGS = TelegramFilterSettings()
_LLM = None

#: 隔離時的標籤（prompt 裡列的那幾個）；模型寫了別的就記成「其他」
LABELS = ("灌水", "閒聊", "罵人", "無關圖片")
#: 文字點名別款遊戲時的標籤：由名單判定，不列給模型選
OTHER_GAME_LABEL = "別款遊戲"
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
    #: 有沒有真的由模型判斷；False＝沒問模型：判不了而放行（`reason` 寫原因），或文字點名別款遊戲而隔離
    by_model: bool = True
    #: 沒經模型判、但之後再判可能判得出來（模型沒回應、出錯、回答看不懂）：轉發端記成待補判。
    #: 看不了的檔案、有圖沒看到再判也一樣，不補
    recheck: bool = False
    images_seen: int = 0
    seconds: float = 0.0
    answer: str = field(default="", repr=False)


#: 空字串會比中每一則訊息、整個頻道都被隔離，所以有空名字就算壞檔
_Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class _GameEntry(BaseModel):
    name: _Name
    aliases: list[_Name] = Field(min_length=1)


class _OtherGamesFile(BaseModel):
    games: list[_GameEntry]
    this_game: list[_Name] = Field(min_length=1)


@dataclass(frozen=True)
class _OtherGames:
    #: (顯示的遊戲名, 比對式)
    games: tuple[tuple[str, re.Pattern], ...]
    this_game: re.Pattern


def _names_pattern(names: Sequence[str]) -> re.Pattern:
    """英文比完整單字（`nte` 是 content、interesting 的一部分），後面可以緊接數字（「NTE1.5」）；中文有出現就算。"""
    parts = [
        rf"(?<![A-Za-z0-9]){re.escape(name)}(?![A-Za-z])" if name.isascii() else re.escape(name)
        for name in sorted(names, key=len, reverse=True)
    ]
    return re.compile("|".join(parts), re.IGNORECASE)


def _parse_other_games(raw: str) -> _OtherGames:
    parsed = _OtherGamesFile.model_validate(json.loads(raw))
    return _OtherGames(
        games=tuple((game.name, _names_pattern(game.aliases)) for game in parsed.games),
        this_game=_names_pattern(parsed.this_game),
    )


def _named_other_game(text: str) -> Optional[str]:
    """文字點名的別款遊戲；沒點名、同一則也提到鳴潮、名單讀不到都回 None（照常往下判，不能因此擋情報）。"""
    if not text:
        return None
    names = hot_files.read_parsed(_SETTINGS.other_games_path, parse=_parse_other_games, label="別款遊戲名單")
    if names is None or names.this_game.search(text):
        return None
    return next((game for game, pattern in names.games if pattern.search(text)), None)


def other_game_verdict(text: str) -> Optional[Verdict]:
    """文字點名別款遊戲 → 隔離的判定；否則 None。只看文字、不碰模型，圖沒到齊也能判。"""
    game = _named_other_game(text)
    return None if game is None else Verdict(True, label=OTHER_GAME_LABEL, reason=game, by_model=False)


def other_games_problem() -> Optional[str]:
    """名單檔現在讀不起來的原因；沒問題回 None。壞檔會沿用上次的內容、不會自己好，要讓人看得到。"""
    try:
        _parse_other_games(Path(_SETTINGS.other_games_path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return type(exc).__name__
    return None


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
    system = hot_files.read_text(_SETTINGS.prompt_path, label="Telegram 過濾 prompt")
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


def _passed(reason: str, started: float, images: int = 0, answer: str = "", *, recheck: bool = False) -> Verdict:
    return Verdict(False, reason=reason, by_model=False, images_seen=images,
                   seconds=time.monotonic() - started, answer=answer, recheck=recheck)


async def _wait_for_imagegen(trace_id: str) -> None:
    """產圖佔著 GPU 時等它做完：這時叫模型會把 LLM 載回去搶 VRAM（載入在排 GPU 之前）。"""
    if gpu_gate.imagegen_busy():
        logger.info("Telegram 過濾：產圖中，等它做完再判（%s）", trace_id)
    while gpu_gate.imagegen_busy():
        await asyncio.sleep(_SETTINGS.busy_poll_seconds)


async def _ask_until_answered(text: str, images: list[bytes], trace_id: str) -> str:
    """排隊直到模型回答：排 GPU 不設上限（`chat_raw` 裡的鎖）；模型逾時或連不上（多半是別的請求還在跑、
    或模型重新載入中）就等一下再排一次，間隔逐次加倍到上限。"""
    delay = _SETTINGS.retry_initial_seconds
    attempt = 0
    while True:
        await _wait_for_imagegen(trace_id)
        try:
            return await _ask_model(text, images, trace_id)
        except (LlmTimeoutError, LlmConnectionError) as exc:
            attempt += 1
            logger.warning("Telegram 過濾：模型沒回應（第 %s 次，%s），%g 秒後再排一次（%s）",
                           attempt, type(exc).__name__, delay, trace_id)
            await asyncio.sleep(delay)
            delay = min(delay * 2, _SETTINGS.retry_max_seconds)


#: 排滿時限還判不到之後，認定模型掛了（每則只問一次）；問到一次就恢復排隊
_model_down = False


async def _ask(text: str, images: list[bytes], trace_id: str) -> str:
    """模型正常：排隊直到回答，最多 `give_up_seconds`。認定掛了：只問一次（含等產圖、排 GPU），失敗就拋。"""
    global _model_down
    if not _model_down:
        try:
            answer = await asyncio.wait_for(_ask_until_answered(text, images, trace_id), _SETTINGS.give_up_seconds)
        except asyncio.TimeoutError:
            _model_down = True
            logger.error("Telegram 過濾：模型 %g 分鐘沒回應，這則未判就放行；之後每則只問一次，問到才恢復排隊（%s）",
                         _SETTINGS.give_up_seconds / 60, trace_id)
            raise _GaveUp(f"模型 {_SETTINGS.give_up_seconds / 60:g} 分鐘沒回應，未判") from None
        return answer

    async def once() -> str:
        await _wait_for_imagegen(trace_id)
        return await _ask_model(text, images, trace_id)
    try:
        answer = await asyncio.wait_for(once(), _SETTINGS.retry_max_seconds)
    except (asyncio.TimeoutError, LlmTimeoutError, LlmConnectionError):
        raise _GaveUp("模型還沒恢復，未判") from None
    _model_down = False
    logger.warning("Telegram 過濾：模型恢復回應，之後照常排隊（%s）", trace_id)
    return answer


class _GaveUp(Exception):
    """模型等不到，這則未判就放行（理由寫在訊息裡）。"""


async def judge(text: str, media: Iterable[MediaFile], *, trace_id: str) -> Verdict:
    """判斷一個發送單位。文字點名別款遊戲直接隔離；其餘問模型，模型忙或沒回應就排隊等（最多 `give_up_seconds`）；
    判不了的（看不了的檔案、出錯、回答看不懂、等太久）回放行（`by_model=False`），不拋例外。"""
    started = time.monotonic()
    images: list[bytes] = []
    try:
        named = other_game_verdict(text)
        if named is not None:
            return named
        media = list(media)
        if any(m.kind == "other" for m in media):
            # 語音、壓縮檔模型看不了：歷史上有好幾則語音爆料沒有文字，當成「什麼都沒有」會被錯關
            return _passed("附有看不了的檔案（語音、壓縮檔）", started)
        images, unseen = await _collect(media)
        if unseen:
            # 有圖或影片沒看到（檔案讀不到、抽幀失敗）：只憑其他部分判，會把「水」配設計稿那種錯關（13649）
            return _passed("有圖或影片沒看到", started, len(images))
        answer = await _ask(text, images, trace_id)
    except _GaveUp as exc:
        return _passed(str(exc), started, len(images), recheck=True)
    except Exception as exc:
        logger.warning("Telegram 過濾：判斷失敗，放行（%s）：%s", trace_id, exc)
        return _passed(f"判斷失敗：{type(exc).__name__}", started, len(images), recheck=True)
    parsed = parse_verdict(answer)
    if parsed is None:
        return _passed("看不懂模型的回答", started, len(images), answer, recheck=True)
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

    def other_game(self, text: str) -> Optional[Verdict]:
        return other_game_verdict(text)

