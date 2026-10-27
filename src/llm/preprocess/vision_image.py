"""vision 圖片前處理：動圖拆成關鍵幀，以及格式降級備援。

**為什麼要自己拆幀**：把「看不看得懂動畫」從後端的實作細節變成我們控制的事。
實測當時的模型直接吃 gif 時**只讀得到第一幀**——一張 [全白, 紅圓, 藍方, 綠三角] 的
四幀動圖，它回答「空白」；再追問幀數還會憑空編出不存在的幀。與其賭後端怎麼解，不如自己
拆成幾張 PNG 一起送：PNG 沒有任何 vision 後端不吃，而且拆幾張、拆哪幾張由我們決定。

**為什麼挑「變化大」的幀而不是等距抽樣**：反應 gif 常常幾十幀都在原地抖，等距抽樣會拿到
一疊幾乎一樣的圖，白白吃掉 context。改成比較相鄰幀的平均像素差，只留變化超過門檻的。

**為什麼挑幀用 PIL 不用 OpenCV**：Pillow 已經在 image 裡（相依帶進來的），OpenCV 更肥，灰階縮圖
算差值這種程度用不到。缺 Pillow 時整條路退回「原圖照送」，不會因此丟掉圖。影片（mp4、webm）PIL
解不開，由 ffmpeg 先解出一些畫格（`video_key_frames`），再交給同一套挑幀規則（`select_key_frames`）——
挑幀規則全專案只有一份。

**為什麼要縮圖（`fit_for_vision`）**：靜圖原本原樣送出，Telegram 有 4100×4080、13.8 MB 的 PNG，動圖拆出來
也是原解析度；縮到長邊上限、轉 JPEG，模型看得一樣清楚，請求小很多，也不會撞到後端不吃的格式。
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Iterable

from utils.media_probe import probe_duration, run_media_tool

logger = logging.getLogger(__name__)

# 送得進 vision 的副檔名——**全專案唯一一份**。ambient 插話、/askai、chat_history 的
# `(圖)` 標記都讀這裡：三邊各留一份的話，哪天加格式就會有人漏改，變成「標了看得到、
# 實際沒送進去」那種對不起來的狀態。
VISION_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")

# 單一動圖最多拆幾幀。也是唯一一份：兩邊各設一個常數遲早會漂移。
DEFAULT_MAX_FRAMES = 4

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


def extract_key_frames(data: bytes, max_frames: int = 4) -> list[bytes]:
    """動圖 → 變化夠大的關鍵幀（PNG）；靜圖、非動圖、或拆不動時回 `[原圖]`。挑法見 `select_key_frames`。"""
    if not data or max_frames <= 1:
        return [data]
    try:
        from PIL import Image, ImageSequence

        with Image.open(BytesIO(data)) as im:
            n_frames = getattr(im, "n_frames", 1)
            if n_frames <= 1:
                return [data]
            kept, kept_indices = select_key_frames(ImageSequence.Iterator(im), max_frames)
            out = [_to_png(f) for f in kept]
    except Exception as exc:
        logger.debug("動圖拆幀失敗，原圖照送：%s", exc)
        return [data]

    logger.info("動圖拆幀：%d 幀 → 取 %s", n_frames, kept_indices)
    return out


def fit_for_vision(data: bytes, *, max_side: int = 1280, quality: int = 85) -> bytes | None:
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
    import base64

    import aiohttp

    out: list[str] = []
    for url in urls:
        if len(out) >= limit:
            break
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                if resp.status != 200:
                    continue
                data = await resp.read()
        except Exception as exc:
            logger.debug("下載圖片失敗 %s：%s", url, exc)
            continue
        if not data or len(data) > max_bytes:
            continue
        out.extend(base64.b64encode(f).decode("utf-8") for f in extract_key_frames(data, max_frames=1)[:1])
    return out

