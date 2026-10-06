"""模型回答的「最後一行結論」：prompt 要模型先寫一行看到什麼、最後一行才寫結論時，程式只取最後一行。

**為什麼先寫理由再寫結論**：直接要結論時，看圖補字典十張有五張回「不知道」，其實圖都看得清楚；
先寫一行看到什麼，就一題都沒有。

**為什麼要去前綴**：模型常照 prompt 的格式說明，在結論前面多寫「第二行：」「看到什麼：」。
不去掉的話，看圖補字典會把「第二行：」當描述寫進字典，過濾也會因為開頭不是「放行」「隔離」而判讀失敗。
"""
from __future__ import annotations

import re

_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.S)
# 沒收尾的思考區塊（回答被截斷、或模型沒寫完）：從 <think> 到結尾都是思考，不是結論
_OPEN_THINK = re.compile(r"<think>.*\Z", re.S)
# 「第二行：」「第2行:」「看到什麼：」「描述：」「結論：」……這類照抄格式說明的前綴（可能連續好幾個）
_LABEL_PREFIX = re.compile(r"^(?:(?:第\s*[一二三四五六七八九十\d]+\s*行|看到什麼|描述|結論|判斷|判定|回答|答案|結果)\s*[：:]\s*)+")


def answer_lines(text: str) -> list[str]:
    """去掉思考區塊（含沒收尾的）後的每個非空行，去掉反引號與照抄格式的前綴。"""
    text = _OPEN_THINK.sub("", _THINK_BLOCK.sub("", text or ""))
    lines = []
    for raw in text.splitlines():
        line = raw.strip().strip("`").strip()
        if line:
            lines.append(_LABEL_PREFIX.sub("", line).strip())
    return lines


def final_line(text: str) -> str:
    """去掉思考區塊後的最後一個非空行（去掉反引號與照抄格式的前綴）；沒有內容回空字串。"""
    lines = answer_lines(text)
    return lines[-1] if lines else ""
