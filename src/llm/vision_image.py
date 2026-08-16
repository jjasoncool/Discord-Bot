"""vision 圖片前處理：動圖拆成關鍵幀，以及格式降級備援。

**為什麼要自己拆幀**：把「看不看得懂動畫」從後端的實作細節變成我們控制的事。
實測 Qwen3.8-27B 直接吃 gif 時**只讀得到第一幀**——一張 [全白, 紅圓, 藍方, 綠三角] 的
四幀動圖，它回答「空白」；再追問幀數還會憑空編出不存在的幀。與其賭後端怎麼解，不如自己
拆成幾張 PNG 一起送：PNG 沒有任何 vision 後端不吃，而且拆幾張、拆哪幾張由我們決定。

**為什麼挑「變化大」的幀而不是等距抽樣**：反應 gif 常常幾十幀都在原地抖，等距抽樣會拿到
一疊幾乎一樣的圖，白白吃掉 context。改成比較相鄰幀的平均像素差，只留變化超過門檻的。

**為什麼用 PIL 不用 ffmpeg/OpenCV**：Pillow 已經在 image 裡（相依帶進來的），ffmpeg 要另外
裝、OpenCV 更肥。灰階縮圖算差值這種程度用不到那些。缺 Pillow 時整條路退回「原圖照送」，
不會因此丟掉圖。
"""
from __future__ import annotations

import logging
from io import BytesIO

logger = logging.getLogger("discord_bot")

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


def _to_png(im) -> bytes:
    buf = BytesIO()
    im.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()


def _mean_abs_diff(a, b) -> float:
    """兩張灰階縮圖的平均像素差（0~255）。用直方圖算，不必動用 numpy。"""
    from PIL import ImageChops

    hist = ImageChops.difference(a, b).histogram()
    total = sum(hist)
    if not total:
        return 0.0
    return sum(value * count for value, count in enumerate(hist)) / total


def extract_key_frames(data: bytes, max_frames: int = 4) -> list[bytes]:
    """動圖 → 變化夠大的關鍵幀（PNG）；靜圖、非動圖、或拆不動時回 `[原圖]`。

    一定會收第一幀；末幀在還有名額時補進來，讓「最後長什麼樣」不會漏掉——
    很多梗圖的笑點就在最後一幀。
    """
    if not data or max_frames <= 1:
        return [data]
    try:
        from PIL import Image

        with Image.open(BytesIO(data)) as im:
            n_frames = getattr(im, "n_frames", 1)
            if n_frames <= 1:
                return [data]

            kept: list[bytes] = []
            kept_indices: list[int] = []
            prev_small = None
            for idx in range(n_frames):
                im.seek(idx)
                # convert 一次拿到合成後的完整幀（partial frame 的 gif 直接取會破圖）
                full = im.convert("RGB")
                small = full.convert("L").resize(_COMPARE_SIZE)
                if prev_small is None:
                    kept.append(_to_png(full))
                    kept_indices.append(idx)
                elif (
                    idx - kept_indices[-1] >= _MIN_FRAME_GAP
                    and _mean_abs_diff(small, prev_small) > _DIFF_THRESHOLD
                ):
                    kept.append(_to_png(full))
                    kept_indices.append(idx)
                    if len(kept) >= max_frames:
                        break
                else:
                    continue
                prev_small = small

            # 末幀補課：還有名額、且它本來沒被選中 → 補上（梗圖的結果常在最後）
            if len(kept) < max_frames and kept_indices[-1] != n_frames - 1:
                im.seek(n_frames - 1)
                kept.append(_to_png(im.convert("RGB")))
                kept_indices.append(n_frames - 1)
    except Exception as exc:
        logger.debug("動圖拆幀失敗，原圖照送：%s", exc)
        return [data]

    logger.info("動圖拆幀：%d 幀 → 取 %s", n_frames, kept_indices)
    return kept


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
