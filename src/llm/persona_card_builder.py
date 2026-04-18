"""Persona card 聚合與格式化工具。"""

from __future__ import annotations

import re
from typing import Any

from llm.tokenization import tokens_for_debug

# Persona RAG 預算與關聯控制（避免 token 爆量）
PERSONA_MAX_PARTICIPANTS = 5
PERSONA_MAX_CARDS = 3
PERSONA_MAX_CARD_CHARS = 400
PERSONA_MAX_IMPRESSIONS_PER_CARD = 3

# Alias 正規化映射（可持續擴充）
ALIAS_SYNONYM_MAP: dict[str, tuple[str, ...]] = {
    "我": ("自己", "本人"),
    "自己": ("我", "本人"),
    "本人": ("我", "自己"),
}


def normalize_alias_text(text: str) -> str:
    normalized = text.strip().lower()
    normalized = re.sub(r"<@!?\d+>", "", normalized)
    normalized = re.sub(r"[^\w\u4e00-\u9fff]+", "", normalized)
    return normalized


def expand_alias_candidates(question: str) -> list[str]:
    raw_tokens = tokens_for_debug(question)
    candidates: list[str] = []
    for token in raw_tokens:
        norm = normalize_alias_text(token)
        if len(norm) < 2 or norm.isdigit():
            continue
        candidates.append(norm)
        for alias in ALIAS_SYNONYM_MAP.get(norm, ()):  # alias map
            alias_norm = normalize_alias_text(alias)
            if alias_norm:
                candidates.append(alias_norm)
    return list(dict.fromkeys(candidates))[:8]


def classify_persona_intent(question: str) -> str:
    q = question.strip()
    if not q:
        return "general"
    if re.search(r"我給人的印象|我.*是誰|我是什麼樣的人|我這個人", q):
        return "self"
    if re.search(r"誰是|他是|她是|他這個人|她這個人|<@!?\d+>", q):
        return "other"
    if "我" in q or "自己" in q:
        return "self"
    return "general"


def extract_mentioned_user_ids(question: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"<@!?(\d+)>", question)))


def build_persona_cards(
    *,
    docs: list[dict[str, Any]],
    requester_user_id: int | None,
    participant_user_ids: list[str],
    mentioned_user_ids: list[str] | None = None,
    intent: str,
    alias_hints: list[str],
    max_cards: int,
) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}

    for doc in docs:
        md = doc.get("metadata") or {}
        profile_kind = str(md.get("profile_kind", ""))
        person_id = ""
        if profile_kind in ("intro_profile", "auto_personality"):
            person_id = str(md.get("author_id", "")).strip()
        elif profile_kind == "impression":
            person_id = str(md.get("target_user_id", "")).strip()
        if not person_id:
            continue

        alias = str(md.get("alias", "") or md.get("target_alias", "")).strip()
        source = str(doc.get("source", "vector"))
        text = " ".join(str(doc.get("text", "")).split())

        card = grouped.setdefault(
            person_id,
            {
                "person_id": person_id,
                "intro_alias": "",
                "other_aliases": set(),
                "intro_texts": [],
                "impression_texts": [],
                "auto_personality_texts": [],
                "sources": set(),
                "evidence_count": 0,
            },
        )
        if alias:
            if profile_kind == "intro_profile" and not card["intro_alias"]:
                card["intro_alias"] = alias
            else:
                card["other_aliases"].add(alias)
        card["sources"].add(source)
        card["evidence_count"] += 1
        if profile_kind == "intro_profile" and text:
            card["intro_texts"].append(text)
        elif profile_kind == "impression" and text:
            card["impression_texts"].append(text)
        elif profile_kind == "auto_personality" and text:
            card["auto_personality_texts"].append(text)

    cards: list[dict[str, Any]] = []
    requester = str(requester_user_id) if requester_user_id is not None else ""

    for person_id, card in grouped.items():
        intro_summary = "；".join(card["intro_texts"][:1])
        impression_summary = "；".join(card["impression_texts"][:PERSONA_MAX_IMPRESSIONS_PER_CARD])
        auto_personality_summary = "；".join(card["auto_personality_texts"][:1])
        # 優先用自我介紹的 alias，其次才用 impression 的
        primary_alias = card["intro_alias"]
        if not primary_alias:
            other = sorted(card["other_aliases"])
            primary_alias = other[0] if other else ""

        score = int(card["evidence_count"])
        source_bonus = {
            "sql_identity": 30,
            "sql_participant": 24,
            "sql_alias": 20,
            "vector": 10,
        }
        for src in card["sources"]:
            score += source_bonus.get(src, 0)
        if person_id == requester and intent == "self":
            score += 50
        if person_id in participant_user_ids:
            score += 25
        if mentioned_user_ids and person_id in mentioned_user_ids:
            score += 35
        if primary_alias and any(h in normalize_alias_text(primary_alias) for h in alias_hints):
            score += 20

        cards.append(
            {
                "person_id": person_id,
                "alias": primary_alias,
                "intro_summary": intro_summary[:PERSONA_MAX_CARD_CHARS],
                "impression_summary": impression_summary[:PERSONA_MAX_CARD_CHARS],
                "auto_personality_summary": auto_personality_summary[:PERSONA_MAX_CARD_CHARS],
                "evidence_count": card["evidence_count"],
                "score": score,
            }
        )

    cards.sort(key=lambda x: (x["score"], x["evidence_count"]), reverse=True)
    return cards[:max_cards]


def _clean_intro_text(raw: str) -> str:
    """從 intro_profile 的 DB 原始 text 中提取有用資訊。

    DB 格式：
        [Intro Profile]
        alias: 柔喵, 阿喵
        wuwa_uid: 800680956
        bio: 普通人，曾經當過巴哈鳴潮板主...
        message_to_all: 不要再80我了...
    """
    # 移除標題行
    text = re.sub(r"\[Intro Profile\]\s*", "", raw)
    # 提取 alias（別名，供 LLM 對照聊天記錄中的 display_name）
    alias_str = ""
    alias_match = re.search(r"alias:\s*(.+?)(?=\n|wuwa_uid:|bio:|message_to_all:|$)", text, re.DOTALL)
    if alias_match:
        alias_val = alias_match.group(1).strip()
        if alias_val and alias_val != "-":
            alias_str = f"別名：{alias_val}"
    # 提取各欄位
    uid = ""
    uid_match = re.search(r"wuwa_uid:\s*(.+?)(?=\n|bio:|message_to_all:|$)", text, re.DOTALL)
    if uid_match:
        uid_val = uid_match.group(1).strip()
        if uid_val and uid_val != "-":
            uid = f"鳴潮UID:{uid_val}"
    bio = ""
    bio_match = re.search(r"bio:\s*(.+?)(?=message_to_all:|$)", text, re.DOTALL)
    if bio_match:
        bio = bio_match.group(1).strip()
    msg = ""
    msg_match = re.search(r"message_to_all:\s*(.+?)$", text, re.DOTALL)
    if msg_match:
        msg = msg_match.group(1).strip()
    # 合併
    parts = [p for p in [alias_str, uid, bio, msg] if p and p != "-"]
    result = "；".join(parts) if parts else ""
    return " ".join(result.split()).strip()


def _clean_impression_text(raw: str) -> str:
    """從 impression 的 DB 原始 text 中提取有用資訊。

    DB 格式：
        [Member Impression]
        target_user_id: 468158509297434635
        target_alias: 阿喵
        target_habit: 最純淨的色慾化身
        impression: 本群最富不容質疑...
    """
    # 移除標題行與 metadata 欄位
    text = re.sub(r"\[Member Impression\]\s*", "", raw)
    text = re.sub(r"target_user_id:\s*\d+\s*", "", text)
    text = re.sub(r"target_alias:.*?(?=\n|target_habit:|impression:|$)", "", text, flags=re.DOTALL)
    # 提取 habit 和 impression 的值
    habit = ""
    imp = ""
    habit_match = re.search(r"target_habit:\s*(.+?)(?=impression:|$)", text, re.DOTALL)
    if habit_match:
        habit = habit_match.group(1).strip()
    imp_match = re.search(r"impression:\s*(.+?)$", text, re.DOTALL)
    if imp_match:
        imp = imp_match.group(1).strip()
    # 合併
    parts = [p for p in [habit, imp] if p and p != "-"]
    result = "；".join(parts) if parts else ""
    return " ".join(result.split()).strip()


def _clean_auto_personality_text(raw: str) -> str:
    """從 auto_personality 的 DB 原始 text 中提取人格描述。

    DB 格式：
        [Auto Personality]
        alias: 柔喵
        personality: 說話幽默自嘲...
    """
    text = re.sub(r"\[Auto Personality\]\s*", "", raw)
    text = re.sub(r"alias:.*?(?=\n|personality:|$)", "", text, flags=re.DOTALL)
    result = ""
    p_match = re.search(r"personality:\s*(.+?)$", text, re.DOTALL)
    if p_match:
        result = p_match.group(1).strip()
    if not result:
        result = " ".join(text.split()).strip()
    return result


def format_persona_cards_for_context(cards: list[dict[str, Any]]) -> list[dict[str, str]]:
    """將 persona cards 格式化為自然語言描述，供 LLM 理解群友人物背景。

    回傳格式不變（list[dict[str, str]]），但 content 改為自然語言。
    header 保留 metadata="persona_card_header" 供呼叫端過濾。
    """
    context_items: list[dict[str, str]] = []
    if not cards:
        return context_items
    context_items.append(
        {
            "role": "system",
            "content": "",
            "metadata": "persona_card_header",
        }
    )
    for card in cards:
        alias = card.get("alias") or "未知"

        # 清理 intro（自我介紹）
        intro = _clean_intro_text(card.get("intro_summary") or "")

        # 清理 impression（群友印象）
        impression = _clean_impression_text(card.get("impression_summary") or "")

        # 清理 auto_personality（AI 觀察）
        auto_personality = _clean_auto_personality_text(card.get("auto_personality_summary") or "")

        # 合併：impression > auto_personality > intro
        parts: list[str] = []
        if intro:
            parts.append(f"自介：{intro}")
        if impression:
            parts.append(f"印象：{impression}")
        if auto_personality:
            parts.append(f"AI觀察：{auto_personality}")

        if parts:
            description = "。".join(parts)
            context_items.append(
                {
                    "role": "user",
                    "content": f"「{alias}」— {description}",
                    "person_id": card.get("person_id", ""),
                }
            )
    return context_items
