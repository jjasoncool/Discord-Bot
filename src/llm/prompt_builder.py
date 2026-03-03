"""LLM prompt 與 log 組裝工具。"""

from __future__ import annotations


def build_askai_prompt_log(
    *,
    system_prompt: str,
    question: str,
    discord_context: list[dict[str, str]],
    rag_context: list[dict[str, str]],
    discord_meta: dict[str, int],
    rag_meta: dict[str, int | bool | str],
    retrieval_debug: dict[str, object] | None,
    image_meta: dict[str, str | int | bool] | None,
    max_context_messages: int,
    discord_context_begin: str,
    discord_context_end: str,
    rag_context_begin: str,
    rag_context_end: str,
) -> str:
    """組裝 askai prompt log 內容。"""
    prompt_parts: list[str] = ["<system>", system_prompt]

    def _safe_extract_content(item: object) -> str:
        """安全提取 context 內容，避免格式異常導致 log 寫入失敗。"""
        if isinstance(item, dict):
            return str(item.get("content", ""))
        return str(item)

    if discord_context:
        prompt_parts.extend([
            "<context_meta:discord>",
            f"fetch_limit={max_context_messages}",
            f"fetched_count={discord_meta.get('fetched_count', 0)}",
            f"recent_selected={discord_meta.get('recent_selected_count', 0)}",
            f"relevant_selected={discord_meta.get('relevant_selected_count', 0)}",
            f"selected_count_before_trim={discord_meta.get('selected_count_before_trim', 0)}",
            f"trimmed_count={discord_meta.get('trimmed_count', 0)}",
            f"sent_count={discord_meta.get('sent_count', 0)}",
            discord_context_begin,
        ])
        for item in discord_context:
            prompt_parts.append(_safe_extract_content(item))
        prompt_parts.append(discord_context_end)

    prompt_parts.extend([
        "<context_meta:rag>",
        f"enabled={rag_meta.get('enabled', False)}",
        f"sent_count={rag_meta.get('sent_count', 0)}",
    ])
    if rag_context:
        prompt_parts.append(rag_context_begin)
        for item in rag_context:
            prompt_parts.append(_safe_extract_content(item))
        prompt_parts.append(rag_context_end)

    prompt_parts.append("<retrieval_debug>")
    if retrieval_debug:
        question_tokens = retrieval_debug.get("question_tokens", [])
        prompt_parts.append(f"question_tokens={question_tokens}")

        prompt_parts.append("<retrieval_debug:bm25_ranked>")
        for item in retrieval_debug.get("bm25_ranked", []):
            prompt_parts.append(str(item))

        prompt_parts.append("<retrieval_debug:vector_ranked>")
        for item in retrieval_debug.get("vector_ranked", []):
            prompt_parts.append(str(item))

        prompt_parts.append("<retrieval_debug:fused_ranked>")
        for item in retrieval_debug.get("fused_ranked", []):
            prompt_parts.append(str(item))
    else:
        prompt_parts.append("enabled=False")

    prompt_parts.append("<image_meta>")
    if image_meta:
        prompt_parts.append(f"attached={bool(image_meta.get('attached', False))}")
        prompt_parts.append(f"count={int(image_meta.get('count', 0))}")
        prompt_parts.append(f"filename={image_meta.get('filename', '')}")
        prompt_parts.append(f"size_bytes={int(image_meta.get('size_bytes', 0))}")
    else:
        prompt_parts.append("attached=False")
        prompt_parts.append("count=0")

    prompt_parts.extend(["<question>", question])
    return "\n".join(prompt_parts)
