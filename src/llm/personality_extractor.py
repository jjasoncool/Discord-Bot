"""自動人格萃取 Pipeline。

從 pgvector 聊天記錄中萃取每位成員的人格特徵，
寫入 auto_personality profile，供 persona card 使用。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Awaitable, Callable, Protocol

import psycopg2

from llm.emoji_text_utils import (
    reload_descriptions as _reload_emoji_descriptions,
    replace_custom_emoji_with_description,
)
from sys_settings.llm_settings import LLMServiceSettings, load_llm_runtime_config
from sys_settings.pgvector_settings import HYBRID_RETRIEVAL_SETTINGS

logger = logging.getLogger("discord_bot")


class PersonalityExtractionInProgressError(RuntimeError):
    """已有其他人格萃取流程正在執行。"""


class PersonalityExtractionProgressCallback(Protocol):
    """人格萃取進度回報 callback。"""

    def __call__(
        self,
        *,
        stage: str,
        model: str,
        total_users: int,
        completed_users: int,
        current_batch: int,
        total_batches: int,
    ) -> None: ...

# 萃取設定
EXTRACT_DAYS = 14  # 取最近幾天的聊天
MIN_MESSAGES_PER_USER = 10  # 低於此數的使用者不分析
BATCH_SIZE = 3  # 每批送幾個人給 LLM
MAX_PERSONALITY_CHARS = 200  # 每人描述上限（提升至 200：新 prompt 讓 LLM 能寫出更具體描述，100 會截斷完整句子）

_EXTRACT_PROMPT_PATH = "/app/settings/prompts/personality_extraction_prompt.json"
_extract_prompts: dict[str, str] | None = None
_extraction_running = False  # 防止同時跑多個人格萃取（僅限單一 process）


def _load_extract_prompts() -> dict[str, str]:
    """載入萃取 prompt（快取）。"""
    global _extract_prompts
    if _extract_prompts is not None:
        return _extract_prompts

    from pathlib import Path
    path = Path(_EXTRACT_PROMPT_PATH)
    if not path.exists():
        raise FileNotFoundError(f"找不到萃取 prompt 檔案: {path}")
    _extract_prompts = json.loads(path.read_text(encoding="utf-8"))
    return _extract_prompts


def _get_db_conn():
    """建立 pgvector 連線。"""
    settings = LLMServiceSettings()
    return psycopg2.connect(
        host=settings.pgvector_host,
        port=settings.pgvector_port,
        dbname=settings.pgvector_db,
        user=settings.pgvector_user,
        password=settings.pgvector_password,
    )


def get_last_extraction_time(guild_id: int | None = None) -> datetime | None:
    """查詢 auto_personality 最後一次萃取的時間（來自 metadata_.last_extracted_at）。

    回傳 UTC datetime；若資料庫沒有任何 auto_personality 記錄或未帶時間戳，回傳 None。
    給排程啟動時判斷「上次排程是否錯過」用。
    """
    profile_table = f"data_{HYBRID_RETRIEVAL_SETTINGS.get_source('member_profile').table_name}"
    sql = f"""
        SELECT MAX((metadata_->>'last_extracted_at')::TIMESTAMPTZ)
        FROM {profile_table}
        WHERE metadata_->>'profile_kind' = 'auto_personality'
          AND metadata_->>'last_extracted_at' IS NOT NULL
    """
    params: list = []
    if guild_id is not None:
        sql += " AND metadata_->>'guild_id' = %s"
        params.append(str(guild_id))

    try:
        with _get_db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                row = cur.fetchone()
                return row[0] if row and row[0] else None
    except Exception as exc:
        logger.warning("查詢 last_extracted_at 失敗: %s", exc)
        return None


def _fetch_aliases_from_db() -> dict[str, str]:
    """從 member_profile 表撈取 author_id → alias 對照。"""
    profile_table = f"data_{HYBRID_RETRIEVAL_SETTINGS.get_source('member_profile').table_name}"
    try:
        with _get_db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT metadata_->>'author_id', metadata_->>'alias'
                    FROM {profile_table}
                    WHERE metadata_->>'profile_kind' = 'intro_profile'
                      AND metadata_->>'alias' IS NOT NULL
                      AND metadata_->>'alias' != ''
                """)
                return {row[0]: row[1] for row in cur.fetchall() if row[0] and row[1]}
    except Exception as exc:
        logger.warning("撈取 DB alias 失敗: %s", exc)
        return {}


def fetch_recent_messages(
    *,
    days: int = EXTRACT_DAYS,
    channel_ids: list[str] | None = None,
) -> list[dict[str, str]]:
    """從 pgvector 撈最近 N 天的聊天記錄。"""
    chat_table = f"data_{HYBRID_RETRIEVAL_SETTINGS.get_chat_table_name()}"
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    query = f"""
        SELECT text, metadata_->>'author_id' AS author_id,
               metadata_->>'timestamp' AS ts
        FROM {chat_table}
        WHERE metadata_->>'doc_type' = 'discord_chat'
          AND metadata_->>'timestamp' >= %s
    """
    params: list[Any] = [since]

    if channel_ids:
        placeholders = ",".join(["%s"] * len(channel_ids))
        query += f" AND metadata_->>'channel_id' IN ({placeholders})"
        params.extend(channel_ids)

    query += " ORDER BY metadata_->>'timestamp'"

    try:
        with _get_db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                rows = cur.fetchall()
        return [
            {"text": row[0] or "", "author_id": row[1] or "", "timestamp": row[2] or ""}
            for row in rows
        ]
    except Exception as exc:
        logger.error("撈取聊天記錄失敗: %s", exc)
        return []


def group_by_user(
    messages: list[dict[str, str]],
    *,
    min_messages: int = MIN_MESSAGES_PER_USER,
) -> dict[str, list[dict[str, str]]]:
    """按 author_id 分組，過濾發言量不足的使用者。"""
    groups: dict[str, list[dict[str, str]]] = {}
    for msg in messages:
        aid = msg.get("author_id", "").strip()
        if not aid:
            continue
        groups.setdefault(aid, []).append(msg)

    return {
        uid: msgs
        for uid, msgs in groups.items()
        if len(msgs) >= min_messages
    }


_EMOJI_DICT_PATH = "/app/settings/emoji_dictionary.txt"


def _load_all_emoji_names_from_file() -> set[str]:
    """讀檔，回傳所有已登記的 emoji name（含空值佔位），用於判斷是否需要新增。"""
    from pathlib import Path
    names: set[str] = set()
    path = Path(_EMOJI_DICT_PATH)
    if not path.exists():
        return names
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name = line.split("=", 1)[0].strip()
            if name:
                names.add(name)
    except Exception as exc:
        logger.warning("讀取 emoji 字典失敗: %s", exc)
    return names


def refresh_emoji_dictionary(guild) -> int:
    """掃描 guild.emojis，把字典沒有的 emoji name 以空值 append 到檔案尾端。

    只處理本 guild 擁有的 emoji（guild.emojis 自然只列本伺服器自訂 emoji；
    其他伺服器的引用不會出現在這裡）。新項目以空值佔位寫入，萃取邏輯會自動
    忽略無描述的 emoji，等管理員手動填寫語意後才真正生效。

    回傳新增的項目數。
    """
    from datetime import datetime
    from pathlib import Path

    existing_names = _load_all_emoji_names_from_file()
    guild_emoji_names = {e.name for e in guild.emojis}
    new_names = sorted(guild_emoji_names - existing_names)
    if not new_names:
        logger.info(
            "emoji 字典無新項目（本 guild 共 %d 個自訂 emoji，全部已記錄）",
            len(guild_emoji_names),
        )
        return 0

    path = Path(_EMOJI_DICT_PATH)
    today = datetime.now().strftime("%Y-%m-%d")
    block = [
        "",
        f"# === 自動偵測 {today}（待填寫） ===",
        *[f"{name} =" for name in new_names],
        "",
    ]
    try:
        with path.open("a", encoding="utf-8") as f:
            f.write("\n".join(block))
    except Exception as exc:
        logger.warning("寫入 emoji 字典失敗: %s", exc)
        return 0

    # 清所有共用 emoji 快取（字典檔剛被改過）
    _reload_emoji_descriptions()
    try:
        from llm.reaction_classifier import reload_custom_emoji_categories
        reload_custom_emoji_categories()
    except Exception as exc:
        logger.warning("重載 reaction_classifier 快取失敗: %s", exc)

    logger.info(
        "emoji 字典新增 %d 個待填項目（前 10：%s）",
        len(new_names),
        new_names[:10],
    )
    return len(new_names)


def _clean_text_for_extraction(text: str) -> str:
    """清理聊天文字，移除對人格分析無用的噪音。"""
    import re
    # Discord 自訂 emoji：<:name:id> → :描述:（與 chat_persistence 共用同一替換函式）
    text = replace_custom_emoji_with_description(text)
    # 移除所有 URL（對人格分析無用，且模型容易誤判為「分享音樂/資訊」）
    text = re.sub(r"https?://\S+", "", text)
    # 移除 Discord mention <@id> 保留可讀形式
    text = re.sub(r"<@!?(\d+)>", "@某人", text)
    # 壓縮空白
    text = " ".join(text.split()).strip()
    return text


def build_chat_log_for_extraction(
    messages: list[dict[str, str]],
    user_aliases: dict[str, str],
) -> str:
    """將訊息組裝成萃取用的聊天記錄文字（含噪音過濾）。"""
    lines: list[str] = []
    for msg in messages:
        author_id = msg.get("author_id", "")
        alias = user_aliases.get(author_id, author_id)
        text = _clean_text_for_extraction(msg.get("text", ""))
        # 過濾掉清理後為空或太短的訊息
        if len(text) < 2:
            continue
        lines.append(f"{alias}: {text}")
    return "\n".join(lines)


async def extract_personalities(
    *,
    messages: list[dict[str, str]],
    user_groups: dict[str, list[dict[str, str]]],
    user_aliases: dict[str, str],
    model: str,
    progress_callback: PersonalityExtractionProgressCallback | None = None,
) -> dict[str, dict[str, str]]:
    """呼叫 LLM 萃取人格特徵。

    回傳 {author_id: {"alias": str, "personality": str}}
    """
    # 走共用 LLMService.chat_raw（不重複一套 aiohttp 實作）
    # 本函式自組 messages list，走底層 chat_raw 而非 generate_reply 比較語意乾淨
    # （generate_reply 是 /askai 專用的 prompt bundle 組裝流程）。
    from services.llm_service import LLMAPIError, LLMService
    service = LLMService()

    user_ids = list(user_groups.keys())
    results: dict[str, dict[str, str]] = {}
    total_batches = (len(user_ids) + BATCH_SIZE - 1) // BATCH_SIZE if user_ids else 0

    if progress_callback:
        progress_callback(
            stage="preparing",
            model=model,
            total_users=len(user_ids),
            completed_users=0,
            current_batch=0,
            total_batches=total_batches,
        )

    for batch_start in range(0, len(user_ids), BATCH_SIZE):
        batch_ids = user_ids[batch_start:batch_start + BATCH_SIZE]
        batch_id_set = set(batch_ids)
        current_batch = batch_start // BATCH_SIZE + 1

        if progress_callback:
            progress_callback(
                stage="calling_llm",
                model=model,
                total_users=len(user_ids),
                completed_users=len(results),
                current_batch=current_batch,
                total_batches=total_batches,
            )

        # 收集這批人的所有訊息（保持時序）
        batch_messages = [
            msg for msg in messages
            if msg.get("author_id", "") in batch_id_set
        ]

        if not batch_messages:
            continue

        # 組裝參與者清單
        user_list = "\n".join(
            f"- ID: {uid}, 暱稱: {user_aliases.get(uid, uid)}"
            for uid in batch_ids
        )

        chat_log = build_chat_log_for_extraction(batch_messages, user_aliases)

        # 截斷過長的聊天記錄（粗估 token，每字約 1.5 token）
        max_chat_chars = 20000
        if len(chat_log) > max_chat_chars:
            chat_log = chat_log[-max_chat_chars:]

        prompts = _load_extract_prompts()
        user_prompt = (
            prompts["user_prompt_template"]
            .replace("{max_chars}", str(MAX_PERSONALITY_CHARS))
            .replace("{user_list}", user_list)
            .replace("{chat_log}", chat_log)
        )

        try:
            content = await service.chat_raw(
                model=model,
                messages=[
                    {"role": "system", "content": prompts["system_prompt"]},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                top_p=0.8,
                num_ctx=32768,
                timeout=600,  # 人格萃取單批可能跑很久，覆蓋預設 300s
                # 排程在 4am 一次跑完所有 batch，結束後不需再駐留；30 分鐘緩衝後釋放 VRAM
                keep_alive="30m",
            )

            # 解析 JSON 結果
            parsed = _extract_json_from_response(content)
            if parsed:
                for item in parsed:
                    uid = str(item.get("user_id", "")).strip()
                    if uid and uid in batch_id_set:
                        personality = str(item.get("personality", "")).strip()
                        alias = str(item.get("alias", "")).strip()
                        if personality:
                            results[uid] = {
                                "alias": alias or user_aliases.get(uid, ""),
                                "personality": personality[:MAX_PERSONALITY_CHARS],
                            }

            logger.info(
                "人格萃取批次完成: batch=%d/%d, extracted=%d",
                current_batch,
                total_batches,
                len([uid for uid in batch_ids if uid in results]),
            )
            if progress_callback:
                progress_callback(
                    stage="batch_done",
                    model=model,
                    total_users=len(user_ids),
                    completed_users=len(results),
                    current_batch=current_batch,
                    total_batches=total_batches,
                )
        except LLMAPIError as exc:
            if exc.status is not None:
                logger.error("人格萃取 LLM 回應失敗: %s - %s", exc.status, exc.detail)
            else:
                logger.error("人格萃取 LLM 回應格式異常: %s", exc.detail)
        except Exception as exc:
            logger.error(
                "人格萃取呼叫失敗: %s: %s",
                type(exc).__name__, exc, exc_info=True,
            )

    if progress_callback:
        progress_callback(
            stage="finished",
            model=model,
            total_users=len(user_ids),
            completed_users=len(results),
            current_batch=total_batches,
            total_batches=total_batches,
        )

    return results


def _extract_json_from_response(text: str) -> list[dict[str, str]] | None:
    """從 LLM 回應中提取 JSON results array。

    策略：優先直接解析 → code fence 提取 → 逐行掃描找第一個 JSON object。
    """
    import re

    # 策略 1：直接解析整段
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            results = parsed.get("results", [])
            if isinstance(results, list):
                return results
        if isinstance(parsed, list):
            return parsed
    except json.JSONDecodeError:
        pass

    # 策略 2：提取 code fence 內的 JSON
    fence_match = re.search(r"```(?:json)?\s*\n?([\s\S]*?)\n?```", text)
    if fence_match:
        try:
            parsed = json.loads(fence_match.group(1))
            if isinstance(parsed, dict):
                results = parsed.get("results", [])
                if isinstance(results, list):
                    return results
        except json.JSONDecodeError:
            pass

    # 策略 3：找第一個完整的 JSON object（平衡大括號）
    start = text.find("{")
    if start >= 0:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        parsed = json.loads(text[start:i + 1])
                        if isinstance(parsed, dict):
                            results = parsed.get("results", [])
                            if isinstance(results, list):
                                return results
                    except json.JSONDecodeError:
                        pass
                    break

    logger.warning("無法從 LLM 回應解析人格萃取結果: %s", text[:200])
    return None


async def run_personality_extraction(
    *,
    guild: Any,
    days: int = EXTRACT_DAYS,
    channel_ids: list[str] | None = None,
    model: str | None = None,
    write_rag: bool = True,
    progress_callback: PersonalityExtractionProgressCallback | None = None,
) -> dict[str, dict[str, str]]:
    """完整的人格萃取流程：撈資料 → 分組 → 萃取 → 寫入 RAG。

    guild: discord.Guild 物件，用於反查 display_name
    回傳 {author_id: {"alias": str, "personality": str}}
    """
    global _extraction_running
    if _extraction_running:
        logger.warning("人格萃取：已有萃取正在執行，拒絕重複啟動")
        raise PersonalityExtractionInProgressError("人格萃取正在執行中")
    _extraction_running = True

    try:
        return await _run_personality_extraction_impl(
            guild=guild, days=days, channel_ids=channel_ids,
            model=model, write_rag=write_rag, progress_callback=progress_callback,
        )
    finally:
        _extraction_running = False


async def _run_personality_extraction_impl(
    *,
    guild: Any,
    days: int = EXTRACT_DAYS,
    channel_ids: list[str] | None = None,
    model: str | None = None,
    write_rag: bool = True,
    progress_callback: PersonalityExtractionProgressCallback | None = None,
) -> dict[str, dict[str, str]]:
    # 解析模型：呼叫端指定 > config personality_model > config 主 model
    if not model:
        settings = LLMServiceSettings()
        runtime_config = load_llm_runtime_config(settings.llm_runtime_model_path)
        model = runtime_config.personality_model or runtime_config.model
    logger.info("人格萃取：使用模型 %s", model)
    if progress_callback:
        progress_callback(
            stage="initializing",
            model=model,
            total_users=0,
            completed_users=0,
            current_batch=0,
            total_batches=0,
        )

    # 1. 撈聊天記錄
    messages = fetch_recent_messages(days=days, channel_ids=channel_ids)
    if not messages:
        logger.info("人格萃取：無聊天記錄可分析")
        return {}
    logger.info("人格萃取：撈到 %d 則聊天記錄（最近 %d 天）", len(messages), days)

    # 2. 按使用者分組
    user_groups = group_by_user(messages)
    if not user_groups:
        logger.info("人格萃取：無符合門檻的使用者（最少 %d 則）", MIN_MESSAGES_PER_USER)
        return {}
    logger.info("人格萃取：%d 位使用者符合分析門檻", len(user_groups))
    if progress_callback:
        total_batches = (len(user_groups) + BATCH_SIZE - 1) // BATCH_SIZE if user_groups else 0
        progress_callback(
            stage="grouped",
            model=model,
            total_users=len(user_groups),
            completed_users=0,
            current_batch=0,
            total_batches=total_batches,
        )

    # 3. 反查 display_name（cache 優先，miss 再並行打 API，最後 fallback DB alias）
    user_aliases: dict[str, str] = {}
    db_aliases = _fetch_aliases_from_db()
    missing_uids: list[str] = []
    for uid in user_groups:
        member = guild.get_member(int(uid)) if guild else None
        if member:
            user_aliases[uid] = getattr(member, "display_name", member.name)
        else:
            missing_uids.append(uid)

    if guild and missing_uids:
        import asyncio as _aio
        sem = _aio.Semaphore(5)

        async def _fetch_one(uid: str):
            async with sem:
                try:
                    return uid, await guild.fetch_member(int(uid))
                except Exception:
                    return uid, None

        fetched = await _aio.gather(*[_fetch_one(uid) for uid in missing_uids])
        for uid, member in fetched:
            if member:
                user_aliases[uid] = getattr(member, "display_name", member.name)

    for uid in user_groups:
        if uid not in user_aliases:
            user_aliases[uid] = db_aliases.get(uid, f"user_{uid[-4:]}")

    # 4. 呼叫 LLM 萃取
    results = await extract_personalities(
        messages=messages,
        user_groups=user_groups,
        user_aliases=user_aliases,
        model=model,
        progress_callback=progress_callback,
    )
    logger.info("人格萃取：成功萃取 %d / %d 位使用者", len(results), len(user_groups))

    # 5. 寫入 RAG（可透過 write_rag=False 跳過，供預覽用）
    if write_rag and results and guild:
        written = await save_personality_results(guild_id=guild.id, results=results)
        logger.info("人格萃取：寫入 RAG %d 筆", written)

    return results


async def save_personality_results(
    *,
    guild_id: int,
    results: dict[str, dict[str, str]],
    progress_callback: Callable[[int, int], Awaitable[None]] | None = None,
) -> int:
    """將萃取結果寫入 RAG，回傳寫入數量。

    progress_callback: 每寫完一筆（不論成功/失敗）呼叫一次，收到 (written_success, total)。
    callback 內的例外會被吞掉，避免拖累寫入主流程。
    """
    from llm.intro_rag_port import get_pgvector_intro_rag_port
    rag_port = get_pgvector_intro_rag_port()
    written = 0
    total = len(results)
    for uid, data in results.items():
        try:
            await rag_port.index_auto_personality(
                guild_id=guild_id,
                author_id=int(uid),
                alias=data["alias"],
                personality=data["personality"],
            )
            written += 1
        except Exception as exc:
            logger.error("寫入 auto_personality 失敗: uid=%s err=%s", uid, exc)
        if progress_callback:
            try:
                await progress_callback(written, total)
            except Exception as exc:
                logger.warning("save_personality_results progress_callback 失敗: %s", exc)
    return written
