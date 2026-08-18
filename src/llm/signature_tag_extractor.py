"""功能二記憶：招牌梗 signature_tag 抽取與寫入（持久印象層）。

把一批插話頻道訊息餵 12B → 抽出「某成員的招牌梗／口頭禪／自嘲外號」→ 經多層安全守門
（歸屬硬驗證、evidence 校驗、敏感過濾、spicy 非對稱門檻、每日去重 corroboration）寫入
共享 pgvector 記憶層的 profile_kind='signature_tag'。

與 preference_extractor 平行（同骨架，治理更硬）。掛在 ambient flush 的 observe（每則訊息
只消費一次），不掛 04:00 滑動窗。
"""
from __future__ import annotations

import asyncio
import functools
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from llm.member_profile_store import get_member_profile_store
from services.llm_service import LLMService
from sys_settings.llm_settings import AmbientChatSettings

logger = logging.getLogger("discord_bot")

_SETTINGS = AmbientChatSettings()
_LLM_SERVICE: Optional[LLMService] = None
_PROMPT_CACHE: dict = {"text": None, "mtime_ns": None}

# 敏感關鍵詞硬過濾（backstop；prompt 已要求丟，這層再兜一次）。寧可誤殺邊緣梗。
# 只收「多字、低誤判」的中文詞——刻意不放 T/P/GAY 這類短字/單字，避免把正常英文/字母誤殺。
_SENSITIVE_KEYWORDS = (
    # 心理/疾病
    "憂鬱症", "躁鬱", "思覺失調", "精神病", "癌", "腫瘤", "愛滋", "HIV", "確診",
    "自殺", "自殘", "洗腎", "化療", "重病",
    # 性向
    "出櫃", "同性戀", "雙性戀", "跨性別", "性傾向", "性別認同",
    # 感情/家庭
    "離婚", "外遇", "劈腿", "小三", "家暴", "婆媳", "單親", "墮胎", "流產",
    # 財務
    "破產", "負債", "失業", "卡債", "欠錢", "貸款", "賭債",
    # 宗教
    "信仰", "基督教", "天主教", "佛教", "伊斯蘭", "穆斯林", "信教",
    # 政治
    "政黨", "民進黨", "國民黨", "統獨", "總統", "罷免",
)


def _get_llm() -> LLMService:
    global _LLM_SERVICE
    if _LLM_SERVICE is None:
        _LLM_SERVICE = LLMService()
    return _LLM_SERVICE


def _has_sensitive(text: str) -> bool:
    return any(k in (text or "") for k in _SENSITIVE_KEYWORDS)


def _load_tag_extractor_prompt() -> str:
    path = Path(_SETTINGS.tag_extractor_prompt_path)
    try:
        if path.exists():
            mtime_ns = path.stat().st_mtime_ns
            if _PROMPT_CACHE["mtime_ns"] == mtime_ns and _PROMPT_CACHE["text"]:
                return _PROMPT_CACHE["text"]
            text = path.read_text(encoding="utf-8").strip()
            if text:
                _PROMPT_CACHE["text"] = text
                _PROMPT_CACHE["mtime_ns"] = mtime_ns
                return text
    except Exception as exc:
        logger.warning("載入 signature_tag extractor prompt 失敗（%s）：%s", path, exc)
    return ""


def _parse_tags(raw: str) -> list[dict]:
    """穩健解析 12B 輸出的 tag JSON 陣列。"""
    if not raw:
        return []
    s = raw.strip()
    start, end = s.find("["), s.rfind("]")
    if start == -1 or end == -1 or end < start:
        return []
    try:
        data = json.loads(s[start : end + 1])
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    out: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        author_id = str(item.get("author_id", "")).strip()
        tag = str(item.get("tag", "")).strip()
        tag_key = str(item.get("tag_key", "")).strip()
        if not author_id.isdigit() or not tag or not tag_key:
            continue
        try:
            confidence = float(item.get("confidence", 0))
        except (TypeError, ValueError):
            confidence = 0.0
        sensitivity = str(item.get("sensitivity", "low")).strip().lower()
        if sensitivity not in ("low", "spicy"):
            sensitivity = "low"
        out.append({
            "author_id": author_id,
            "tag": tag[:40],
            "tag_key": tag_key[:120],
            "tag_kind": str(item.get("tag_kind", "")).strip()[:20],
            "sensitivity": sensitivity,
            "self_claimed": bool(item.get("self_claimed", False)),
            "evidence_quote": str(item.get("evidence_quote", "")).strip()[:300],
            "evidence_author_id": str(item.get("evidence_author_id", "")).strip(),
            "confidence": max(0.0, min(1.0, confidence)),
        })
    return out


async def extract_signature_tags(*, messages: list[dict], model: str) -> list[dict]:
    """messages: [{author_id, alias, text}, …] → 候選 tags（含 alias）。走 chat_raw、低溫。"""
    system_prompt = _load_tag_extractor_prompt()
    if not system_prompt or not messages:
        return []
    alias_map: dict[str, str] = {}
    lines: list[str] = []
    for m in messages:
        author_id = str(m.get("author_id", "")).strip()
        text = (m.get("text", "") or "").strip()
        if not author_id.isdigit() or not text:
            continue
        alias_map.setdefault(author_id, (m.get("alias", "") or ""))
        lines.append(f"author_id={author_id} ({m.get('alias', '') or '-'}): {text[:300]}")
    if not lines:
        return []
    chat_messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "以下是群聊訊息：\n" + "\n".join(lines)},
    ]
    try:
        raw = await _get_llm().chat_raw(model=model, messages=chat_messages, temperature=0.2)
    except Exception as exc:
        logger.warning("signature_tag 抽取 LLM 失敗：%s", exc)
        return []
    tags = _parse_tags(raw)
    for t in tags:
        t["alias"] = alias_map.get(t["author_id"], "")
    return tags


async def ingest_signature_tags(
    *,
    guild_id: int,
    candidates: list[dict],
    valid_author_ids: set[str],
    author_texts: dict[str, str],
) -> dict:
    """多層守門 + corroboration 寫入。

    valid_author_ids: 本批「真實 sender」集合（來自 Discord 訊息物件，非 LLM 文字）——歸屬白名單。
    author_texts: author_id → 該人本批文字（給 evidence_quote 機械校驗用）。
    """
    stats = {
        "written": 0, "new": 0, "promoted": 0,
        "rejected_attr": 0, "rejected_sensitive": 0, "rejected_spicy": 0,
        "rejected_blacklist": 0, "skipped_conf": 0,
    }
    if not candidates:
        return stats
    port = get_member_profile_store()
    loop = asyncio.get_running_loop()
    now_iso = datetime.now(timezone.utc).isoformat()
    today = datetime.now(timezone.utc).date().isoformat()

    # 過濾 + 批內去重
    deduped: dict[tuple[str, str], dict] = {}
    for c in candidates:
        aid = c["author_id"]
        if aid not in valid_author_ids:               # 歸屬硬驗證：必是本批真實 sender
            stats["rejected_attr"] += 1
            continue
        # 敏感過濾掃所有人臉可見/證據欄位（不只 tag/tag_key）
        if any(_has_sensitive(c.get(f, "")) for f in
               ("tag", "tag_key", "tag_kind", "evidence_quote", "alias")):
            stats["rejected_sensitive"] += 1
            continue
        if c.get("confidence", 0.0) < _SETTINGS.tag_min_confidence:
            stats["skipped_conf"] += 1
            continue
        # evidence 機械校驗（self_claimed / spicy 才需要）
        self_claimed = bool(c.get("self_claimed"))
        if self_claimed or c.get("sensitivity") == "spicy":
            ev_aid = str(c.get("evidence_author_id", "")).strip()
            ev_q = (c.get("evidence_quote", "") or "").strip()
            own_text = author_texts.get(aid, "") or ""
            # evidence 前綴需為本人原文子串；前綴拉到 16 字、且至少 4 字，壓低用無關片段湊驗證的空間
            ev_len = min(len(ev_q), 16)
            ok = bool(ev_aid == aid and ev_len >= 4 and ev_q[:ev_len] in own_text)
            if c.get("sensitivity") == "spicy":
                # spicy 正文本身必須真出自本人原文（防 LLM 捏造黃色梗硬掛到本人頭上）
                norm_tag = port._normalize_tag_text(c.get("tag", ""))
                ok = ok and bool(norm_tag and norm_tag in own_text)
            self_claimed = self_claimed and ok
        c["_self_claimed_verified"] = self_claimed
        if c.get("sensitivity") == "spicy" and not self_claimed:   # spicy 必須本人認領
            stats["rejected_spicy"] += 1
            continue
        deduped.setdefault((aid, c["tag_key"]), c)

    by_author: dict[str, list[dict]] = {}
    for (aid, _k), c in deduped.items():
        by_author.setdefault(aid, []).append(c)

    for aid, cands in by_author.items():
        existing_rows = await loop.run_in_executor(
            None,
            functools.partial(port.list_signature_tags, guild_id=guild_id, author_id=int(aid)),
        )
        existing = {r.get("tag_key", ""): r for r in existing_rows}
        # blacklist 禁學不綁在 LLM 自由產生的 tag_key 上：另用 normalize(tag) 對所有已封鎖列做
        # 子字串包含比對，攔截「近義改寫換個 tag_key 重新學」的繞過（SEC-1）。
        blacklisted_norms = [
            n for n in (
                port._normalize_tag_text(r.get("tag", ""))
                for r in existing_rows if r.get("blacklisted") == "1"
            ) if n
        ]

        for c in cands:
            spicy = c.get("sensitivity") == "spicy"
            promote_at = _SETTINGS.tag_promote_at_spicy if spicy else _SETTINGS.tag_promote_at_low
            norm_tag = port._normalize_tag_text(c.get("tag", ""))
            if norm_tag and any(
                norm_tag in bn or bn in norm_tag for bn in blacklisted_norms
            ):
                stats["rejected_blacklist"] += 1
                continue  # 命中已封鎖梗的近義改寫 → 禁學
            prev = existing.get(c["tag_key"])
            suppressed, blacklisted = "0", "0"
            if prev:
                if prev.get("blacklisted") == "1":     # 申訴後永不再處理
                    continue
                suppressed = prev.get("suppressed", "0")
                blacklisted = prev.get("blacklisted", "0")
                try:
                    prev_count = int(prev.get("mention_count", "1") or "1")
                except ValueError:
                    prev_count = 1
                first_seen = prev.get("first_seen") or now_iso
                was_trusted = prev.get("status") == "trusted"
                # 每日去重：今天已計過 → count 不動（只刷 last_seen）
                if prev.get("last_corroborated_day") == today:
                    count = prev_count
                else:
                    count = min(prev_count + 1, _SETTINGS.tag_count_cap)
            else:
                count, first_seen, was_trusted = 1, now_iso, False

            can_promote = (suppressed != "1" and blacklisted != "1")
            new_trusted = can_promote and count >= promote_at
            status = "trusted" if (new_trusted or (was_trusted and suppressed != "1")) else "tentative"

            doc_id = await port.index_signature_tag(
                guild_id=guild_id,
                author_id=int(aid),
                alias=c.get("alias", ""),
                tag=c["tag"],
                tag_key=c["tag_key"],
                tag_kind=c.get("tag_kind", ""),
                sensitivity=c.get("sensitivity", "low"),
                self_claimed="1" if c.get("_self_claimed_verified") else "0",
                confidence=float(c.get("confidence", 0.0)),
                status=status,
                mention_count=count,
                first_seen=first_seen,
                last_seen=now_iso,
                last_corroborated_day=today,
                suppressed=suppressed,
                blacklisted=blacklisted,
            )
            if doc_id:
                stats["written"] += 1
                if not prev:
                    stats["new"] += 1
                if new_trusted and not was_trusted:
                    stats["promoted"] += 1
    return stats


async def run_signature_tag_sweep(guild) -> dict[str, int]:
    """招牌梗衰減 sweep（每日維護步驟；純 metadata UPDATE/DELETE，不碰 LLM、不重嵌入）。

    2026-08-18 從 `personality_extractor._run_personality_extraction_impl` 的步驟 0 移出。
    兩者無資料相依（sweep 只動 profile_kind='signature_tag'，萃取只動 'auto_personality'），
    當初共用 `_extraction_running` 鎖只是為了不另開排程。拆開的好處：
      - 人格萃取日後換成 agent 實作時，招牌梗 GC 不受影響（換工具＝只換萃取那一步）
      - 手動預覽指令（`write_rag=False`）不再誤觸真實的刪梗／降級

    純 SQL、不佔 GPU，所以不需要 `stream_exclusive()` 或萃取鎖。
    失敗只 log 不 raise —— 維護工作不該拖垮排程的其他步驟。

    回傳 `{scanned, demoted, archived}`；guild 為 None 或失敗時回傳全 0。
    """
    zero = {"scanned": 0, "demoted": 0, "archived": 0}
    if guild is None:
        logger.warning("招牌梗 sweep：無可用 guild，略過")
        return zero
    try:
        port = get_member_profile_store()
        stats = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: port.sweep_signature_tags(
                guild_id=guild.id,
                halflife_low_days=_SETTINGS.tag_halflife_low_days,
                halflife_spicy_days=_SETTINGS.tag_halflife_spicy_days,
                demote_floor=_SETTINGS.tag_demote_floor,
                archive_floor=_SETTINGS.tag_archive_floor,
            ),
        )
        logger.info("招牌梗 sweep（guild=%s）：%s", guild.id, stats)
        return stats
    except Exception as exc:
        logger.warning("招牌梗 sweep 失敗（不影響其他維護步驟）：%s", exc, exc_info=True)
        return zero


async def process_tag_batch(*, guild_id: int, messages: list[dict], model: str) -> dict:
    """便利接口：一批訊息 → 抽取 → 守門 ingest。供 MemoryService.observe 並排呼叫。

    messages 必須帶**真實 author_id**（來自 enqueue_for_memory 的 Discord 訊息物件）。
    """
    candidates = await extract_signature_tags(messages=messages, model=model)
    if not candidates:
        return {"written": 0}
    # 真實 sender 白名單 + 每人本批文字（evidence 校驗）——皆來自可信的訊息來源，非 LLM 輸出
    valid_author_ids: set[str] = set()
    author_texts: dict[str, str] = {}
    for m in messages:
        aid = str(m.get("author_id", "")).strip()
        if not aid.isdigit():
            continue
        valid_author_ids.add(aid)
        author_texts[aid] = (author_texts.get(aid, "") + " " + (m.get("text", "") or "")).strip()
    stats = await ingest_signature_tags(
        guild_id=guild_id,
        candidates=candidates,
        valid_author_ids=valid_author_ids,
        author_texts=author_texts,
    )
    logger.info("signature_tag 批次寫入：guild=%s %s", guild_id, stats)
    return stats
