"""prompt 除錯 log：檔案 logger 的建立（寫到哪、怎麼輪替），以及 /askai 除錯 log 的內容組裝。"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from pathlib import Path
from typing import Literal

from utils.logger_config import redirected_log_name

def get_or_create_file_logger(
    *,
    name: str,
    log_path: Path,
    mode: Literal["size", "time"],
    level: int = logging.INFO,
    max_bytes: int = 0,
    backup_count: int = 0,
    when: str = "midnight",
    interval: int = 1,
) -> logging.Logger:
    """依 rotation 模式建立/回傳 file logger（避免重複 handler）。"""
    override = redirected_log_name()
    if override:
        # 測試模式：prompt 除錯檔也改寫到測試 log，不動正式的除錯檔
        log_path = log_path.with_name(override)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False

    if not logger.handlers:
        if mode == "time":
            file_handler = TimedRotatingFileHandler(
                log_path,
                when=when,
                interval=interval,
                backupCount=backup_count,
                encoding="utf-8",
            )
        else:
            file_handler = RotatingFileHandler(
                log_path,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )

        file_handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(file_handler)

    return logger


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
