"""LLM prompt 與 log 組裝工具。"""

from __future__ import annotations


def build_askai_prompt_log(
    *,
    system_prompt: str,
    question: str,
    discord_context: list[dict[str, str]],
    rag_context: list[dict[str, str]],
    discord_meta: dict[str, int],
    rag_meta: dict[str, int | bool],
    max_context_messages: int,
    discord_context_begin: str,
    discord_context_end: str,
    rag_context_begin: str,
    rag_context_end: str,
) -> str:
    """組裝 askai prompt log 內容。"""
    prompt_parts: list[str] = ["[system]", system_prompt]

    if discord_context:
        prompt_parts.extend([
            "[context_meta:discord]",
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
            prompt_parts.append(item.get("content", ""))
        prompt_parts.append(discord_context_end)

    prompt_parts.extend([
        "[context_meta:rag]",
        f"enabled={rag_meta.get('enabled', False)}",
        f"sent_count={rag_meta.get('sent_count', 0)}",
    ])
    if rag_context:
        prompt_parts.append(rag_context_begin)
        for item in rag_context:
            prompt_parts.append(item.get("content", ""))
        prompt_parts.append(rag_context_end)

    prompt_parts.extend(["[question]", question])
    return "\n".join(prompt_parts)
