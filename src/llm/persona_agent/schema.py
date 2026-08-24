"""Persona agent 的輸出契約：diff 的 JSON schema。

用 OpenAI dialect 的 `response_format.json_schema`（strict）強制約束，不依賴模型自律。
本後端（Lemonade 11.5.0 + llama.cpp b9747）已實測支援 strict 模式且輸出可直接
`json.loads()`，故不再另外寫 GBNF。

**LLM 輸出一律視為不可信輸入**：schema 只保證「形狀對」，內容真偽由 M3 的驗證層
（evidence 反查、confidence 門檻）負責。
"""
from __future__ import annotations

from typing import Any

# 單筆變更：type / trait / text / reason / evidence_msg_ids 缺一不可。
# additionalProperties=False 讓模型無法夾帶自創欄位（strict 模式的必要條件）。
_CHANGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "type": {
            "type": "string",
            "enum": ["add", "revise", "keep"],
            "description": "add=新增特徵；revise=修正既有描述；keep=維持不變",
        },
        "trait": {"type": "string", "description": "簡短特徵名"},
        "text": {
            "type": "string",
            "description": (
                "這個人「是」怎樣——直述句。不要解釋為什麼改、不要提到既有描述、"
                "不要寫「不只是」「而非」這種對照語氣；引用最多一個當例子。"
                "這一欄會被串成最終的人格描述給下游使用，讀者不知道舊描述長什麼樣。"
            ),
        },
        "reason": {
            "type": "string",
            "description": (
                "你憑什麼這樣說——引用、與既有描述的對照、推翻或保留的理由通通放這裡。"
                "這一欄只給人稽核，不會進入最終描述，可以寫長。"
            ),
        },
        "evidence_msg_ids": {
            "type": "array",
            "items": {"type": "string"},
            "description": "支持本項的訊息 ID；驗證層會反查是否真實存在且屬於該使用者",
        },
    },
    "required": ["type", "trait", "text", "reason", "evidence_msg_ids"],
    "additionalProperties": False,
}

PERSONA_DIFF_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "user_id": {"type": "string"},
        "changes": {"type": "array", "items": _CHANGE_SCHEMA},
        "confidence": {
            "type": "string",
            "enum": ["low", "medium", "high"],
            "description": "low 或 changes 為空 → 驗證層標記「資料不足」，不寫入新版本",
        },
        "notes": {"type": "string", "description": "資料不足或異常時的說明"},
    },
    "required": ["user_id", "changes", "confidence", "notes"],
    "additionalProperties": False,
}


def build_response_format() -> dict[str, Any]:
    """組 chat/completions 的 `response_format` 欄位（走 extra_body 送出）。"""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "persona_diff",
            "strict": True,
            "schema": PERSONA_DIFF_SCHEMA,
        },
    }
