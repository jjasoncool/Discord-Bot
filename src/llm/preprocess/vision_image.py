"""給 vision 模型的圖：抓網路上的圖、動圖拆關鍵幀、縮圖，以及格式降級備援。

架構定位：LLM 技術層（`llm.preprocess`）。依賴 Pillow、aiohttp、`utils.media_probe`（ffmpeg）；不 import discord，
Discord 的附件、預覽物件由呼叫端交進來、這裡只讀屬性。上層：插話（附件、連結預覽）、/askai 的附件、
看圖補字典、別的伺服器的表情、X 貼文、Telegram 過濾。

介面：
- `remote_image(media)`：Discord 的附件或預覽上的圖 → `RemoteImage`（代理網址、原檔網址、寬高、會不會動）。
- `fetch_for_vision(session, image, max_frames=)`：先抓代理的縮小版、不行才抓原檔 → `VisionFetch`（給模型的圖、是不是太大）。
- `proxy_variant(image)`：向 Discord 媒體代理要的縮小版網址。
- `vision_frames(data, max_frames)`：下載到的圖 → 動圖的關鍵幀（PNG）或一張靜態圖（JPEG）。
- `download_images(session, urls, limit=)`：幾個網址各抓一張（動圖只取第一幀）。
- `extract_key_frames`／`select_key_frames`／`video_key_frames`：動圖、影片挑關鍵幀；`fit_for_vision`：縮圖轉 JPEG。
- `is_vision_image`、`VISION_IMAGE_EXTS`、`DEFAULT_MAX_FRAMES`、`MAX_FETCH_BYTES`：全專案唯一一份的格式、幀數、大小上限。

規則：
- 抓網路上的圖一律只在記憶體裡：下載、轉檔、交給模型，用完即丟，不寫硬碟。
- 解碼、拆幀是 CPU 工作：`fetch_for_vision` 自己丟到執行緒；直接叫 `vision_frames`、`extract_key_frames` 的 async 呼叫端要自己丟。
- 一張抓不到只是少一張，不往外丟例外；`fetch_for_vision` 記一行 INFO 說兩邊各是什麼原因。

例外與決策：
- 自己拆幀：實測當時的模型直接吃 gif 只讀得到第一幀（[全白, 紅圓, 藍方, 綠三角] 的動圖它答「空白」，追問幀數
  還會編）。拆成幾張 PNG 一起送：PNG 沒有 vision 後端不吃，拆幾張、拆哪幾張由我們決定。
- 挑「變化大」的幀、不等距抽樣：反應 gif 常常幾十幀都在原地抖，等距抽樣會拿到一疊幾乎一樣的圖、白吃 context。
- 挑幀用 Pillow 不用 OpenCV：灰階縮圖算差值用不到 OpenCV；缺 Pillow 時退回原圖照送。影片由 ffmpeg 先解畫格，
  再交給同一套挑幀規則——挑幀規則全專案只有一份。
- 縮圖：動圖 4 幀一起送、每幀長邊 512；靜態圖只送一張、長邊 1280，截圖上的字要看得清楚。輸出只有 JPEG、PNG：
  `llm_service` 一律標成 JPEG 送出，代理給的 webp 不是每個後端都吃。
- 先抓 Discord 媒體代理的縮小版：原檔有多大就得抓多大，一支 13 MB 的 GIF 原檔超過上限、代理縮成 512 只要 2.7 MB；
  別的網站的圖也都經過同一個代理。代理的參數是 Discord 用戶端自己在用、沒有正式文件，失效時靠退回原檔。
  原檔要用附件或預覽裡簽過名的網址：訊息裡貼的光網址，Discord 的 CDN 回 404。
"""
from __future__ import annotations

import asyncio
import base64
import logging
import shutil
import tempfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Iterable
from urllib.parse import urlencode, urlsplit

from utils.media_probe import probe_duration, run_media_tool

logger = logging.getLogger(__name__)

# 送得進 vision 的副檔名——**全專案唯一一份**。ambient 插話、/askai、chat_history 的
# `(圖)` 標記都讀這裡：三邊各留一份的話，哪天加格式就會有人漏改，變成「標了看得到、
# 實際沒送進去」那種對不起來的狀態。
VISION_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")

# 單一動圖最多拆幾幀。也是唯一一份：兩邊各設一個常數遲早會漂移。
DEFAULT_MAX_FRAMES = 4

# 抓網路上的圖給模型：代理的縮小版、原檔都用這一個上限
MAX_FETCH_BYTES = 10 * 1024 * 1024
# 送給模型的圖的長邊：動圖一次送好幾幀，每幀要小；靜態圖只送一張，字要看得清楚
ANIMATED_MAX_SIDE = 512
STATIC_MAX_SIDE = 1280

_JPEG_MAGIC = b"\xff\xd8\xff"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def is_vision_image(filename: str) -> bool:
    """這個檔名送不送得進 vision。"""
    return (filename or "").lower().endswith(VISION_IMAGE_EXTS)

# 比較用的縮圖尺寸：算平均差值不需要原解析度，縮小快很多且結果幾乎一樣
_COMPARE_SIZE = (128, 128)
# 平均像素差門檻（0~255）。8~12 敏感、15~20 中等、25+ 只抓大幅變動。
_DIFF_THRESHOLD = 12.0
# 至少隔幾幀才考慮下一張，避免過渡期連續存進一堆相似幀
_MIN_FRAME_GAP = 2


def is_universal_image(data: bytes) -> bool:
    """是不是所有 vision 後端都吃的格式（jpeg / png）。用 magic bytes 判，不看副檔名。"""
    return bool(data) and (data.startswith(_JPEG_MAGIC) or data.startswith(_PNG_MAGIC))


def _flatten(im):
    """轉 RGB；有透明度的先鋪白底。直接 convert 會把透明的地方變成黑色，透明背景上的深色線稿就整張黑掉。"""
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        from PIL import Image

        rgba = im.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background
    return im.convert("RGB")


def _to_png(im) -> bytes:
    buf = BytesIO()
    _flatten(im).save(buf, format="PNG")
    return buf.getvalue()


def _mean_abs_diff(a, b) -> float:
    """兩張灰階縮圖的平均像素差（0~255）。用直方圖算，不必動用 numpy。"""
    from PIL import ImageChops

    hist = ImageChops.difference(a, b).histogram()
    total = sum(hist)
    if not total:
        return 0.0
    return sum(value * count for value, count in enumerate(hist)) / total


def select_key_frames(frames: Iterable, max_frames: int = DEFAULT_MAX_FRAMES) -> tuple[list, list[int]]:
    """一串依時間排好的幀（PIL Image）→ 變化夠大的關鍵幀（RGB）與它們的位置。挑幀規則全專案只有這一份。

    一定會收第一幀；末幀在還有名額時補進來，讓「最後長什麼樣」不會漏掉——很多梗圖的笑點就在最後一幀。
    `frames` 可以是邊解邊給的 iterator：名額滿了就不再往下讀。
    """
    kept: list = []
    kept_indices: list[int] = []
    if max_frames < 1:
        return kept, kept_indices
    prev_small = None
    last = None
    for idx, frame in enumerate(frames):
        # convert 一次拿到合成後的完整幀（partial frame 的 gif 直接取會破圖）
        full = _flatten(frame)
        small = full.convert("L").resize(_COMPARE_SIZE)
        last = (idx, full, small)
        if prev_small is not None and (
            idx - kept_indices[-1] < _MIN_FRAME_GAP
            or _mean_abs_diff(small, prev_small) <= _DIFF_THRESHOLD
        ):
            continue
        kept.append(full)
        kept_indices.append(idx)
        prev_small = small
        # 收完就檢查：名額只有 1 張時只收第一幀
        if len(kept) >= max_frames:
            break

    # 末幀補課：還有名額、它本來沒被選中、而且跟最後收的那張不一樣 → 補上（梗圖的結果常在最後）。
    # 一樣的不補：影片只有一個關鍵畫格時，解出來的每格都是同一張，補了只是讓模型看兩次
    if (last is not None and len(kept) < max_frames and kept_indices[-1] != last[0]
            and _mean_abs_diff(last[2], prev_small) > _DIFF_THRESHOLD):
        kept.append(last[1])
        kept_indices.append(last[0])
    return kept, kept_indices


def extract_key_frames(data: bytes, max_frames: int = 4, *, max_side: int | None = None) -> list[bytes]:
    """動圖 → 變化夠大的關鍵幀（PNG，給了 `max_side` 就縮到長邊不超過它）；靜圖、非動圖、或拆不動時回 `[原圖]`。
    挑法見 `select_key_frames`。"""
    if not data or max_frames <= 1:
        return [data]
    try:
        from PIL import Image, ImageSequence

        with Image.open(BytesIO(data)) as im:
            n_frames = getattr(im, "n_frames", 1)
            if n_frames <= 1:
                return [data]
            kept, kept_indices = select_key_frames(ImageSequence.Iterator(im), max_frames)
            if max_side:
                for frame in kept:
                    frame.thumbnail((max_side, max_side))
            out = [_to_png(f) for f in kept]
    except Exception as exc:
        logger.debug("動圖拆幀失敗，原圖照送：%s", exc)
        return [data]

    logger.info("動圖拆幀：%d 幀 → 取 %s", n_frames, kept_indices)
    return out


def fit_for_vision(data: bytes, *, max_side: int = STATIC_MAX_SIDE, quality: int = 85) -> bytes | None:
    """縮到長邊不超過 `max_side`、轉成 JPEG（動圖取第一幀）。打不開回 None，由呼叫端決定要不要跳過這張。

    JPEG 是所有 vision 後端都吃的格式（`llm_service` 也一律標成 `image/jpeg` 送出），體積比 PNG 小 5～10 倍。
    """
    if not data:
        return None
    try:
        from PIL import Image

        with Image.open(BytesIO(data)) as im:
            im.seek(0)
            rgb = _flatten(im)
        rgb.thumbnail((max_side, max_side))
        buf = BytesIO()
        rgb.save(buf, format="JPEG", quality=quality)
        return buf.getvalue()
    except Exception as exc:
        logger.debug("vision 縮圖失敗：%s", exc)
        return None


async def video_key_frames(path: str | Path, max_frames: int = DEFAULT_MAX_FRAMES, *, max_side: int = 1280,
                           sample_frames: int = 12, timeout: float = 60) -> list[bytes]:
    """影片 → 關鍵幀（PNG，長邊不超過 `max_side`）；解不開、逾時回空清單。

    ffmpeg 只解關鍵畫格（`-skip_frame nokey`）、在整支影片平均取 `sample_frames` 格再交給 `select_key_frames`：
    完整解碼 4K 影片要 40 秒，只解關鍵畫格 2 秒。ffmpeg 直接輸出動態 PNG 到管線會產生壞檔（被當成單張），
    所以先輸出成一張張 PNG 再讀回來。CPU 工作（讀檔、挑幀）與暫存資料夾的建立、刪除丟到執行緒，不卡 event loop。

    fps 濾鏡要 `eof_action=pass`：預設會在結尾丟掉最後一個輸入幀，只有一個關鍵畫格的短片（Telegram 的 GIF 轉
    mp4 多半如此，約一成影片）會一張都抽不出來，多個關鍵畫格的也可能漏掉最後一段。
    """
    if max_frames < 1:
        return []
    duration = await probe_duration(str(path))
    if duration <= 0:
        return []
    tmp = Path(await asyncio.to_thread(tempfile.mkdtemp, prefix="vision_video_"))
    try:
        cmd = [
            "ffmpeg", "-v", "error", "-nostdin", "-skip_frame", "nokey", "-i", str(path),
            "-vf", f"fps={sample_frames}/{duration:.3f}:eof_action=pass,scale='min({max_side},iw)':-2",
            "-frames:v", str(sample_frames), str(tmp / "frame_%03d.png"),
        ]
        result = await run_media_tool(cmd, timeout=timeout)
        if result.timed_out:
            return []
        if result.returncode != 0:
            logger.warning("影片抽幀失敗（rc=%s）：%s %s", result.returncode, path, result.stderr.decode(errors="replace")[-300:])
            return []
        return await asyncio.to_thread(_pick_from_dir, tmp, max_frames)
    finally:
        await asyncio.to_thread(shutil.rmtree, tmp, True)


def _pick_from_dir(folder: Path, max_frames: int) -> list[bytes]:
    from PIL import Image

    def frames():
        for file in sorted(folder.glob("frame_*.png")):
            with Image.open(file) as im:
                yield im.convert("RGB")

    kept, kept_indices = select_key_frames(frames(), max_frames)
    logger.info("影片抽幀：取 %s", kept_indices)
    return [_to_png(f) for f in kept]


def to_png_first_frame(data: bytes) -> bytes:
    """把圖轉成 PNG（動畫取第一幀）；轉不動就原樣返回。

    給「後端連原格式都吃不下」的降級備援用——拆幀已經處理掉 gif，這裡剩下的是
    animated webp 之類的少數情況。
    """
    if not data:
        return data
    try:
        from PIL import Image

        with Image.open(BytesIO(data)) as im:
            im.seek(0)
            converted = _to_png(im)
    except Exception as exc:
        logger.debug("vision 圖片轉 PNG 失敗，原樣送出：%s", exc)
        return data
    logger.info("vision 圖片已退成 PNG 第一幀（%d → %d bytes）", len(data), len(converted))
    return converted


async def download_images(session, urls, *, limit: int, max_bytes: int = 5 * 1024 * 1024,
                          timeout: float = 8) -> list[str]:
    """下載網址上的圖 → base64（給 vision 模型），最多 `limit` 張；動圖只取第一幀。

    任何一張失敗（逾時、非 200、太大、空檔）就跳過那張，不拋例外——圖只是補充，少一張不該擋住回覆。
    X 貼文縮圖（`tweet_context`）與別的伺服器的表情／貼圖（`external_emoji`）共用。
    """
    out: list[str] = []
    for url in urls:
        if len(out) >= limit:
            break
        data, why = await _fetch_bytes(session, url, max_bytes=max_bytes, timeout=timeout)
        if data is None:
            logger.debug("下載圖片失敗 %s：%s", url, why)
            continue
        out.extend(base64.b64encode(f).decode("utf-8") for f in extract_key_frames(data, max_frames=1)[:1])
    return out


@dataclass(frozen=True)
class RemoteImage:
    """網路上的一張圖：Discord 媒體代理的網址（能要縮小版）、原檔網址、原圖寬高（不知道是 None）、會不會動。"""

    proxy_url: str | None
    url: str | None
    width: int | None = None
    height: int | None = None
    animated: bool = False


@dataclass(frozen=True)
class VisionFetch:
    """`fetch_for_vision` 的結果：給模型的圖（base64；抓不到是空清單），以及抓不到時是不是有一邊太大。"""

    frames: list[str]
    too_big: bool = False


def remote_image(media) -> RemoteImage | None:
    """Discord 的附件或預覽上的圖（`Attachment`、`embed.thumbnail`／`embed.image`）→ `RemoteImage`；兩個網址都沒有回 None。

    只讀屬性、不認 discord 的型別（這層不 import discord）。旗標沒標「會動」的 GIF 也當動圖：
    舊的附件、別的網站的預覽不一定有旗標。
    """
    if media is None:
        return None
    proxy_url = getattr(media, "proxy_url", None) or None
    url = getattr(media, "url", None) or None
    if not (proxy_url or url):
        return None
    names = (getattr(media, "filename", None) or "", urlsplit(url or proxy_url).path)
    animated = (bool(getattr(getattr(media, "flags", None), "animated", False))
                or (getattr(media, "content_type", None) or "").lower() == "image/gif"
                or any(name.lower().endswith(".gif") for name in names))
    width = getattr(media, "width", None) or None
    height = getattr(media, "height", None) or None
    return RemoteImage(proxy_url, url, int(width) if width else None, int(height) if height else None, animated)


def proxy_variant(image: RemoteImage) -> str | None:
    """向 Discord 媒體代理要的縮小版網址；沒有代理網址回 None。

    動圖要會動的 webp、長邊 `ANIMATED_MAX_SIDE`；靜態圖長邊 `STATIC_MAX_SIDE`、格式不換；比上限小的不放大。
    寬高照原圖比例自己算：兩個都給、比例不對，代理會把圖拉變形；不知道原圖寬高就不要尺寸。參數接在原本的
    簽章參數後面，簽章要原樣留著代理才認。
    """
    if not image.proxy_url:
        return None
    params: dict[str, str | int] = {}
    if image.animated:
        params.update(format="webp", animated="true")
    if image.width and image.height:
        side = ANIMATED_MAX_SIDE if image.animated else STATIC_MAX_SIDE
        scale = min(1.0, side / max(image.width, image.height))
        params.update(width=max(1, round(image.width * scale)), height=max(1, round(image.height * scale)))
    if not params:
        return image.proxy_url
    joiner = "" if image.proxy_url.endswith(("?", "&")) else ("&" if "?" in image.proxy_url else "?")
    return image.proxy_url + joiner + urlencode(params)


def vision_frames(data: bytes, max_frames: int = DEFAULT_MAX_FRAMES) -> list[bytes]:
    """下載到的圖 → 送給模型的圖：動圖拆最多 `max_frames` 張關鍵幀（PNG、長邊 `ANIMATED_MAX_SIDE`），靜態圖一張
    （JPEG、長邊 `STATIC_MAX_SIDE`）；打不開回空清單。CPU 工作，async 裡要丟到執行緒。"""
    if max_frames > 1:
        frames = extract_key_frames(data, max_frames, max_side=ANIMATED_MAX_SIDE)
        if frames != [data]:  # 回原檔＝靜態圖或拆不動，照靜態圖處理（動圖取第一幀）
            return frames
    single = fit_for_vision(data, max_side=STATIC_MAX_SIDE)
    return [single] if single else []


def _encoded_frames(data: bytes, max_frames: int) -> list[str]:
    return [base64.b64encode(f).decode("ascii") for f in vision_frames(data, max_frames)]


_TOO_BIG = "太大"


async def _fetch_bytes(session, url: str, *, max_bytes: int, timeout: float) -> tuple[bytes | None, str]:
    """GET 一個網址 → (內容, "")；抓不到回 (None, 原因)。對方先講了大小、而且超過上限，就不下載。"""
    import aiohttp

    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            if resp.status != 200:
                return None, f"HTTP {resp.status}"
            declared = getattr(resp, "content_length", None)
            if declared and declared > max_bytes:
                return None, f"{_TOO_BIG}（{declared / 1024 / 1024:.1f} MB）"
            data = await resp.read()
    except Exception as exc:  # 邊界：一張圖抓不到只是少一張，不擋住回覆
        return None, type(exc).__name__
    if not data:
        return None, "空檔"
    if len(data) > max_bytes:
        return None, f"{_TOO_BIG}（{len(data) / 1024 / 1024:.1f} MB）"
    return data, ""


def _without_query(url: str | None) -> str:
    return urlsplit(url)._replace(query="").geturl() if url else "-"


async def fetch_for_vision(session, image: RemoteImage, *, max_frames: int = DEFAULT_MAX_FRAMES,
                           max_bytes: int = MAX_FETCH_BYTES, timeout: float = 20) -> VisionFetch:
    """網路上的一張圖 → 給模型的圖（見 `vision_frames`）。

    先抓代理的縮小版（`proxy_variant`），代理抓不到、太大或解不開才抓原檔，兩邊上限都是 `max_bytes`。
    兩邊都不行回空的 `frames`、記一行 INFO 寫兩邊各是什麼原因，`too_big` 說是不是有一邊太大。
    拆幀、轉檔丟到執行緒，不卡 event loop（音樂、Discord 連線都在上面）。
    """
    tried: list[str] = []
    too_big = False
    for label, url in (("代理", proxy_variant(image)), ("原檔", image.url)):
        if not url:
            continue
        data, why = await _fetch_bytes(session, url, max_bytes=max_bytes, timeout=timeout)
        if data is None:
            too_big = too_big or why.startswith(_TOO_BIG)
            tried.append(f"{label} {why}")
            continue
        frames = await asyncio.to_thread(_encoded_frames, data, max_frames)
        if frames:
            return VisionFetch(frames)
        tried.append(f"{label} 解不開")
    logger.info("圖片沒抓到（%s）：%s", "；".join(tried) or "沒有網址", _without_query(image.url or image.proxy_url))
    return VisionFetch([], too_big=too_big)

