"""Persona card 聚合與格式化工具。"""

from __future__ import annotations

import re
from typing import Any

from llm.tokenization import tokens_for_debug

# Persona RAG 預算與關聯控制（避免 token 爆量）
PERSONA_MAX_PARTICIPANTS = 5
PERSONA_MAX_CARDS = 3
PERSONA_MAX_CARD_CHARS = 220
PERSONA_MAX_IMPRESSIONS_PER_CARD = 2

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
    intent: str,
    alias_hints: list[str],
    max_cards: int,
) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}

    for doc in docs:
        md = doc.get("metadata") or {}
        profile_kind = str(md.get("profile_kind", ""))
        person_id = ""
        if profile_kind == "intro_profile":
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
                "aliases": set(),
                "intro_texts": [],
                "impression_texts": [],
                "sources": set(),
                "evidence_count": 0,
            },
        )
        if alias:
            card["aliases"].add(alias)
        card["sources"].add(source)
        card["evidence_count"] += 1
        if profile_kind == "intro_profile" and text:
            card["intro_texts"].append(text)
        elif profile_kind == "impression" and text:
            card["impression_texts"].append(text)

    cards: list[dict[str, Any]] = []
    requester = str(requester_user_id) if requester_user_id is not None else ""

    for person_id, card in grouped.items():
        intro_summary = "；".join(card["intro_texts"][:1])
        impression_summary = "；".join(card["impression_texts"][:PERSONA_MAX_IMPRESSIONS_PER_CARD])
        alias_list = sorted(card["aliases"])
        primary_alias = alias_list[0] if alias_list else ""

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
        if primary_alias and any(h in normalize_alias_text(primary_alias) for h in alias_hints):
            score += 20

        cards.append(
            {
                "person_id": person_id,
                "alias": primary_alias,
                "intro_summary": intro_summary[:PERSONA_MAX_CARD_CHARS],
                "impression_summary": impression_summary[:PERSONA_MAX_CARD_CHARS],
                "evidence_count": card["evidence_count"],
                "score": score,
            }
        )

    cards.sort(key=lambda x: (x["score"], x["evidence_count"]), reverse=True)
    return cards[:max_cards]


def format_persona_cards_for_context(cards: list[dict[str, Any]]) -> list[dict[str, str]]:
    context_items: list[dict[str, str]] = []
    if not cards:
        return context_items
    context_items.append(
        {
            "role": "system",
            "content": "--- 以下為 Persona Cards（同 guild 範圍，僅供語意參考）---",
            "metadata": "persona_card_header",
        }
    )
    for card in cards:
        intro = card.get("intro_summary") or "-"
        impression = card.get("impression_summary") or "-"
        context_items.append(
            {
                "role": "user",
                "content": (
                    f"[persona_card] person_id={card['person_id']} alias={card.get('alias') or '-'} "
                    f"evidence={card.get('evidence_count', 0)}\n"
                    f"intro={intro}\n"
                    f"impression={impression}"
                ),
            }
        )
    return context_items
