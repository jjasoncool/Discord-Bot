"""切段：把一份文件切成幾百字一段，每段前面帶標題，送去算向量。

為什麼要切：一篇四千字的公告壓成一個向量，裡面某一句的意思會被其他內容平均掉；切成幾百字一段，
問句才對得上講那件事的那一段。為什麼帶標題：巴哈的回覆樓層、公告的中後段常常沒提到主題，
標題（巴哈樓層的標題＝討論串標題＋樓數）補上「這段在講什麼」（contextual chunk header）。

規則（2026-10-08 定案）：
  - 照段落累積，超過上限就切到下一段；相鄰兩段重疊一小截，答案剛好跨在切點上也有一段是完整的
  - 一個段落本身就超過上限（巴哈常整樓不換行）才用固定長度的滑動視窗切
  - 巴哈一樓多半很短，自然就是一段；聊天紀錄（`/askai` 那邊）一則訊息就是天然的最小單位，不切
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    chunk_id: str        # 「文件 id#段落序號」
    doc_id: str
    position: int
    text: str            # 標題＋這一段，就是送去算向量的文字
    text_hash: str       # 內容沒變就不重算向量


def split_text(title: str, body: str, *, max_chars: int, overlap: int) -> list[str]:
    """回傳每段的文字（已帶標題）。只有標題、沒有內文時回一段只有標題的。"""
    paragraphs = [line.strip() for line in (body or "").splitlines() if line.strip()]
    pieces: list[str] = []
    current = ""
    for para in paragraphs:
        if len(para) > max_chars:
            if current:
                pieces.append(current)
                current = ""
            step = max(1, max_chars - overlap)
            for start in range(0, len(para), step):
                pieces.append(para[start:start + max_chars])
                if start + max_chars >= len(para):
                    break
            continue
        if current and len(current) + 1 + len(para) > max_chars:
            pieces.append(current)
            tail = current[-overlap:] if overlap else ""
            current = f"{tail}\n{para}" if tail else para
        else:
            current = f"{current}\n{para}" if current else para
    if current or not pieces:
        pieces.append(current)
    header = (title or "").strip()
    return [f"{header}\n{piece}".strip() for piece in pieces]


def chunk_document(doc_id: str, title: str, body: str, *, max_chars: int, overlap: int) -> list[Chunk]:
    return [
        Chunk(chunk_id=f"{doc_id}#{i}", doc_id=doc_id, position=i, text=text,
              text_hash=hashlib.sha1(text.encode("utf-8")).hexdigest())
        for i, text in enumerate(split_text(title, body, max_chars=max_chars, overlap=overlap))
    ]
