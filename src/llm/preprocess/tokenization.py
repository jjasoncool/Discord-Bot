"""聊天檢索用的文字正規化、分詞，與「同一句話」的折疊鍵。

架構定位：技術層（`llm/preprocess`），只依賴標準庫。上層：`llm.retrievers.context_retriever`（BM25 切詞、折疊重複）、
`llm.persona.persona_card_builder`（除錯輸出）。

介面：
- `normalize_retrieval_text(text)`：小寫、全形空白、口語（hen→很）的最小正規化。
- `tokenize_for_retrieval(text)`：英數詞＋中文 2、3 字組，給 BM25。
- `dedup_key(text)`：同一句話的身分（正規化後只留字母、數字、中日韓文字），給檢索折疊重複用。

規則：`dedup_key` 只認字面，不判斷語意相近；「笑死」「笑死！」「笑 死～」同一鍵，「笑死了」是另一句。
"""

from __future__ import annotations

import re

# 空白、標點、符號（含全形）；`\w` 在 Python 預設 Unicode 模式下含中日韓文字
_NON_WORD = re.compile(r"[\W_]+")


def normalize_retrieval_text(text: str) -> str:
    """做最小正規化，提升口語/中英混寫命中率。"""
    normalized = (text or "").lower().replace("　", " ")
    # 常見口語輸入：hen窮 / hen 帥
    normalized = re.sub(r"\bhen\b", "很", normalized)
    return " ".join(normalized.split())


def tokenize_for_retrieval(text: str) -> list[str]:
    """簡易分詞：中英數混合 + 中文 n-gram，供 BM25 使用。

    回傳 list 而非 set，保留重複 token。BM25 的 TF 分量依賴重複次數，
    若去重會讓長訊息的 term frequency 一律視為 1，排名偏弱。
    """
    normalized = normalize_retrieval_text(text)
    tokens: list[str] = []

    # 英數 token
    tokens.extend(re.findall(r"[a-z0-9_]{2,}", normalized))

    # 中文片段 token + bi/tri-gram
    zh_chunks = re.findall(r"[\u4e00-\u9fff]+", normalized)
    for chunk in zh_chunks:
        if len(chunk) >= 2:
            tokens.append(chunk)
            for i in range(len(chunk) - 1):
                tokens.append(chunk[i:i + 2])
        if len(chunk) >= 3:
            for i in range(len(chunk) - 2):
                tokens.append(chunk[i:i + 3])

    return [t for t in tokens if len(t) >= 2]


def tokens_for_debug(text: str) -> list[str]:
    """回傳去重後排序的 token，供檢索除錯輸出使用。"""
    return sorted(set(tokenize_for_retrieval(text)))


def dedup_key(text: str) -> str:
    """同一句話的身分：正規化後去掉所有空白、標點、符號，只留字母、數字與中日韓文字。

    檢索折疊重複用（同一人貼過幾千次的表情描述只留一則）。只認字面：「笑死」與「笑死！」同一鍵，不判斷語意相近。
    `:描述:` 與 `[貼圖：描述]` 的符號也被去掉，所以 `:安可瘋狂:` 與「安可瘋狂」同一鍵——折疊時兩者本來就該算同一件事。
    沒有任何字詞字元的（「????」「……」顏文字）回空字串：呼叫端遇到空鍵不折，不然不相干的純標點會被湊成一組。
    """
    return _NON_WORD.sub("", normalize_retrieval_text(text))
