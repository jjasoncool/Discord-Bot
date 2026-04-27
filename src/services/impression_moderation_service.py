"""他人印象內容審核服務（防禦 RAG 資料中毒 + 迷因灌水）。"""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import re
from typing import Any

from services.llm_service import LLMService
from sys_settings.llm_settings import (
    LLMServiceSettings,
    load_context_safety_rules,
    load_llm_runtime_config,
)

logger = logging.getLogger("discord_bot")


def _clamp_score(value: Any, default: float = 1.0) -> float:
    try:
        numeric = float(value)
    except Exception:
        return default
    if numeric < 0.0:
        return 0.0
    if numeric > 1.0:
        return 1.0
    return numeric


def _extract_json_object(raw_text: str) -> dict[str, Any] | None:
    text = (raw_text or "").strip()
    if not text:
        return None

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None

    try:
        parsed = json.loads(match.group(0))
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        return None
    return None


def _rule_prefilter(text: str) -> tuple[bool, str]:
    normalized = " ".join((text or "").split())

    if len(normalized) < 6:
        return False, "內容太短，請描述你對對方的具體印象。"

    digits = sum(ch.isdigit() for ch in normalized)
    if digits / max(len(normalized), 1) >= 0.7:
        return False, "內容數字比例過高，請改成可理解的社群印象描述。"

    if re.search(r"(.)\1{6,}", normalized):
        return False, "內容重複字元過多，請改寫成具體敘述。"

    return True, "ok"


@dataclass(frozen=True)
class ImpressionModerationResult:
    approved: bool
    decision: str
    reason: str
    score_prompt_injection: float
    score_meme_spam: float
    score_fake_story: float
    score_real_interaction: float
    score_meaningfulness: float

    def to_metadata(self) -> dict[str, str]:
        return {
            "mod_schema_ver": "impression_moderation_v1",
            "mod_decision": self.decision,
            "mod_reason": self.reason,
            "mod_score_prompt_injection": f"{self.score_prompt_injection:.4f}",
            "mod_score_meme_spam": f"{self.score_meme_spam:.4f}",
            "mod_score_fake_story": f"{self.score_fake_story:.4f}",
            "mod_score_real_interaction": f"{self.score_real_interaction:.4f}",
            "mod_score_meaningfulness": f"{self.score_meaningfulness:.4f}",
            "mod_approved": "true" if self.approved else "false",
        }


class ImpressionModerationService:
    """以 LLM + 規則做提交前審核，並輸出可入庫的安全 metadata。"""

    def __init__(self, llm_service: LLMService | None = None) -> None:
        self.settings = LLMServiceSettings()
        self.safety_rules = load_context_safety_rules(self.settings.llm_context_safety_rules_path)
        self.runtime_config = load_llm_runtime_config(self.settings.llm_runtime_model_path)
        self.llm = llm_service or LLMService()

    async def moderate(self, *, target_display: str, text: str) -> ImpressionModerationResult:
        pre_ok, pre_reason = _rule_prefilter(text)
        if not pre_ok:
            return ImpressionModerationResult(
                approved=False,
                decision="reject",
                reason=pre_reason,
                score_prompt_injection=0.0,
                score_meme_spam=1.0,
                score_fake_story=0.0,
                score_real_interaction=0.0,
                score_meaningfulness=0.0,
            )

        schema_hint = self.safety_rules.impression_moderation_schema_hint
        system_prompt = self.safety_rules.impression_moderation_system_prompt
        user_prompt = self.safety_rules.impression_moderation_user_prompt_template.format(
            target_display=target_display,
            text=text,
            schema_hint_json=json.dumps(schema_hint, ensure_ascii=False),
        )

        moderation_model = self.runtime_config.moderation_model or None

        reply_text, _ = await self.llm.generate_reply(
            prompt=user_prompt,
            system=system_prompt,
            model=moderation_model,
            temperature=0.1,
            top_p=0.2,
            repeat_penalty=1.05,
            num_ctx=2048,
            # moderation 是 /impression 觸發的間歇性任務：最後一次後 30 分鐘 unload，
            # 節省 VRAM 但不會太短導致頻繁 reload
            keep_alive="30m",
        )

        parsed = _extract_json_object(reply_text)
        if not parsed:
            logger.warning("Impression moderation 無法解析 JSON，reply=%s", reply_text)
            return ImpressionModerationResult(
                approved=False,
                decision="rewrite",
                reason="審核結果不穩定，請補充更具體的對象印象。",
                score_prompt_injection=0.0,
                score_meme_spam=0.5,
                score_fake_story=0.5,
                score_real_interaction=0.0,
                score_meaningfulness=0.0,
            )

        decision = str(parsed.get("decision", "rewrite")).strip().lower()
        if decision not in {"pass", "reject", "rewrite"}:
            decision = "rewrite"

        reason = str(parsed.get("reason", "內容需要補充與目標對象的具體互動印象")).strip()
        if not reason:
            reason = "內容需要補充與目標對象的具體互動印象"

        score_prompt_injection = _clamp_score(parsed.get("score_prompt_injection"), default=1.0)
        score_meme_spam = _clamp_score(parsed.get("score_meme_spam"), default=1.0)
        score_fake_story = _clamp_score(parsed.get("score_fake_story"), default=1.0)
        score_real_interaction = _clamp_score(parsed.get("score_real_interaction"), default=0.0)
        score_meaningfulness = _clamp_score(parsed.get("score_meaningfulness"), default=0.0)

        # 安全閘道：程式硬判斷優先於 LLM 的最終 decision。
        if score_prompt_injection > 0.1:
            return ImpressionModerationResult(
                approved=False,
                decision="reject",
                reason="偵測到疑似系統操控指令內容，請改寫。",
                score_prompt_injection=score_prompt_injection,
                score_meme_spam=score_meme_spam,
                score_fake_story=score_fake_story,
                score_real_interaction=score_real_interaction,
                score_meaningfulness=score_meaningfulness,
            )

        if score_meme_spam > 0.6:
            return ImpressionModerationResult(
                approved=False,
                decision="reject",
                reason="請勿使用迷因/定型文灌水，請填寫真實社群印象。",
                score_prompt_injection=score_prompt_injection,
                score_meme_spam=score_meme_spam,
                score_fake_story=score_fake_story,
                score_real_interaction=score_real_interaction,
                score_meaningfulness=score_meaningfulness,
            )

        if score_fake_story > 0.6:
            return ImpressionModerationResult(
                approved=False,
                decision="reject",
                reason="內容偏向虛構或離題，請改為真實互動印象。",
                score_prompt_injection=score_prompt_injection,
                score_meme_spam=score_meme_spam,
                score_fake_story=score_fake_story,
                score_real_interaction=score_real_interaction,
                score_meaningfulness=score_meaningfulness,
            )

        if score_real_interaction < 0.4:
            return ImpressionModerationResult(
                approved=False,
                decision="rewrite",
                reason="內容缺乏真實互動感，請補充具體觀察。",
                score_prompt_injection=score_prompt_injection,
                score_meme_spam=score_meme_spam,
                score_fake_story=score_fake_story,
                score_real_interaction=score_real_interaction,
                score_meaningfulness=score_meaningfulness,
            )

        approved = decision == "pass" and score_meaningfulness >= 0.35
        if not approved and decision == "reject":
            final_decision = "reject"
        elif approved:
            final_decision = "pass"
        else:
            final_decision = "rewrite"

        return ImpressionModerationResult(
            approved=approved,
            decision=final_decision,
            reason=reason if reason else "請補充更具體且與對象相關的印象",
            score_prompt_injection=score_prompt_injection,
            score_meme_spam=score_meme_spam,
            score_fake_story=score_fake_story,
            score_real_interaction=score_real_interaction,
            score_meaningfulness=score_meaningfulness,
        )
