"""Persona agent 的執行迴圈（手寫，不使用 LangChain 等框架）。

一輪的形狀：

    收集階段（thinking 關閉，最多 MAX_STEPS 步）
        每步前禮讓前景 → chat_with_tools(tools=...) → 有 tool_calls 就執行、回填
        沒有 tool_calls 或 token 預算用盡 → 跳出
    產出階段（thinking 打開）
        chat_with_tools(response_format=diff schema) → 解析成 dict

為什麼 thinking 分兩段：「下一步呼叫哪個工具」是機械決策（schema 已把選項限死，
實測關閉思考時 4.4 秒就正確產出）；「新增還是修正、證據夠不夠」才需要推理。
八步全開約 12 分／人，分段後約 3 分／人。

M2 只到「產出可解析的 diff」為止，**不寫資料庫**。evidence 反查、confidence 門檻
與版本寫入屬於 M3 的驗證層。
"""
from __future__ import annotations

import asyncio
import functools
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from llm.lemonade_gate import foreground_recently_active, stream_busy
from llm.persona_agent import tools as agent_tools
from llm.persona_agent.schema import build_response_format
from sys_settings.llm_settings import AmbientChatSettings

logger = logging.getLogger("discord_bot")

MAX_STEPS = 8
# 收集階段的累計上限。設定上 ctx_size=32768，但**實際可用的比帳面小很多**：
# llama-server 的 KV 是多個 slot 共用，被並行請求（/askai、插話）擠壓時會縮水。
# 實測單發 24,110 token 可過、但同時段的 ~17k 請求曾直接吃到
# `Context size has been exceeded` → 保守抓 12k，剩下留給 thinking、輸出與並行波動。
TOKEN_BUDGET = 12000
# 禮讓：前景（/askai、插話）在用就等；設上限避免旗標卡住時整批停擺
YIELD_POLL_SECONDS = 2.0
YIELD_MAX_WAIT_SECONDS = 600.0
# 收集步驟關閉 thinking，走預設 timeout 即可；產出步驟開 thinking，實測會吐
# 數千個推理 token（33 tok/s），300 秒的預設不夠用 → 比照人格萃取拉到 600 秒。
FINAL_TIMEOUT_SECONDS = 600

_PROMPT_PATH = "/app/settings/prompts/persona_agent_prompt.json"
_DESCRIPTION_RULES_PATH = "/app/settings/prompts/persona_description_rules.txt"


def load_prompts() -> dict[str, str]:
    """組裝 system prompt（三層疊加）。各層由 `prompt_files` 做 mtime 快取，改檔即生效。

    **刻意不自己重寫共用規則**——原本這支的 prompt 把角色設定、繁中限制、不編造、
    自訂表情規則、描述品質規則全部複製一份，13 條核心規則與 production 萃取完全重疊。
    那不只是冗餘：日後調整其中一邊，另一邊會靜默分岔。改為層疊沿用，共用的是**檔案**
    （比照 `persona_examples.txt` 被 /askai 與插話共用的做法）：

        ① personality_extraction_prompt.json 的 system_prompt
           ＝角色（社群觀察專家）／只能繁中／不要編造／自訂表情 :xxx: 規則
        ② persona_description_rules.txt
           ＝描述品質規則（嚴禁廢話、要寫出跟別人不一樣的地方、角色定位…）
        ③ persona_agent_prompt.json 的 system_layer
           ＝**只有 agent 專屬的**：工具工作流、互損文化判讀、資料不足就說不足

    ①② 的前處理（自訂表情轉語意、去 URL）由 `tools._clean_text_for_extraction`
    沿用同一份——共用規則卻不共用前處理，等於讓 prompt 對模型說謊。

    回傳 `{"system_prompt", "user_prompt_template", "final_prompt"}`。
    """
    from llm import prompt_files
    from llm.personality_extractor import _load_extract_prompts

    own = prompt_files.read_json(_PROMPT_PATH, label="persona agent prompt")
    if own is None:
        raise FileNotFoundError(f"找不到或無法解析 persona agent prompt: {_PROMPT_PATH}")

    layers = [
        _load_extract_prompts()["system_prompt"].strip(),
        prompt_files.read_text(_DESCRIPTION_RULES_PATH, label="描述品質規則"),
        own["system_layer"].strip(),
    ]
    return {
        "system_prompt": "\n\n".join(layer for layer in layers if layer),
        "user_prompt_template": own["user_prompt_template"],
        "final_prompt": own["final_prompt"],
    }


def estimate_tokens(text: str) -> int:
    """粗估 token 數：CJK 一字約一 token，其餘約四字元一 token。

    只用來守 context 預算，不需要精準——寧可略高估提早收手，也不要撐爆 32k
    讓整輪白跑。用 token 而非「則數」是因為一則可能 5 字也可能 300 字。
    """
    if not text:
        return 0
    # U+3040~U+9FFF（假名 + CJK 統一漢字）、U+FF00~U+FFEF（全形符號）算一字一 token
    wide = sum(1 for ch in text if 0x3040 <= ord(ch) <= 0x9FFF or 0xFF00 <= ord(ch) <= 0xFFEF)
    # 其餘除以 3 而非 4：工具回傳是 JSON，充滿長數字 ID 與標點，切得比一般英文散文碎
    return wide + (len(text) - wide) // 3 + 1


# 預算用盡後仍必須回覆每個 tool_call_id（協議要求），內容換成這個佔位字串
_OMITTED_PAYLOAD = '{"note": "已達本次資料上限，未執行；請就手上的資料作答"}'


class ContextExceeded(Exception):
    """可用 context 不足以完成本次執行。"""


def _is_context_error(exc: Exception) -> bool:
    """判斷是不是 context 撐爆（llama.cpp 回 500 + "Context size has been exceeded"）。"""
    detail = getattr(exc, "detail", "") or ""
    text = f"{exc} {detail}".lower()
    return "context size" in text or "context length" in text


async def _call_model(service: Any, *, messages: list[dict[str, object]],
                      trace: str, **kwargs: Any) -> Any:
    """呼叫模型；context 撐爆時直接放棄這位使用者。

    **為什麼不裁切後重試**：第一版會把較早的工具結果換成佔位字串再送一次，實測結果是
    模型手上只剩空殼，誠實回報「資料不足」——一個格式正確、理由充分、confidence 標 low
    的**假陰性**，不看 trace 根本分不出來。輸入被偷偷弄壞的執行，產出的東西不能信。

    這是每天跑一次的批次任務：今晚失敗，明晚自動重跑就好。沒有任何理由為了「有個結果」
    而接受被削過的輸入。真正的防線是收集階段的 token 預算。
    """
    try:
        return await service.chat_with_tools(messages=messages, **kwargs)
    except Exception as exc:
        if _is_context_error(exc):
            raise ContextExceeded(str(exc)) from exc
        raise


@dataclass(frozen=True)
class StepTrace:
    """單一工具呼叫的紀錄，供事後檢查 agent 的決策路徑（M3 寫進 runs 表）。"""

    step: int
    tool: str
    arguments: str
    result_preview: str
    elapsed_ms: int


@dataclass
class AgentRun:
    """一位使用者的執行結果。"""

    user_id: str
    status: str  # ok / rejected_schema / max_steps / error
    diff: Optional[dict[str, Any]] = None
    steps: int = 0
    trace: list[StepTrace] = field(default_factory=list)
    duration_ms: int = 0
    estimated_tokens: int = 0
    error: Optional[str] = None


async def _yield_to_foreground(trace_id: str) -> float:
    """前景（/askai、插話）在用模型就等，回傳實際等待秒數。

    agent 是半夜批次，慢幾分鐘無所謂；使用者在等人回話。刻意**不**呼叫
    `note_foreground_activity()`——那會把插話壓制 90 秒。
    """
    grace = AmbientChatSettings().askai_grace_seconds
    waited = 0.0
    while stream_busy() or foreground_recently_active(grace):
        if waited >= YIELD_MAX_WAIT_SECONDS:
            logger.warning(
                "persona agent trace=%s 禮讓超過 %.0f 秒，仍照常進行", trace_id, waited
            )
            break
        await asyncio.sleep(YIELD_POLL_SECONDS)
        waited += YIELD_POLL_SECONDS
    if waited:
        logger.info("persona agent trace=%s 禮讓前景 %.0f 秒", trace_id, waited)
    return waited


async def run_for_user(
    *,
    user_id: str,
    ctx: agent_tools.ToolContext,
    model: str,
    llm_service: Any = None,
    max_steps: int = MAX_STEPS,
    token_budget: int = TOKEN_BUDGET,
    final_timeout: int = FINAL_TIMEOUT_SECONDS,
    trace_id: Optional[str] = None,
) -> AgentRun:
    """對單一使用者跑完整個 agent loop，回傳結果（**不寫資料庫**）。

    任一失敗都收斂成 `AgentRun.status`，不往外拋——批次執行時單人失敗不該影響其他人。
    """
    from services.llm_service import LLMService

    service = llm_service or LLMService()
    trace = trace_id or f"pa-{user_id[-4:]}-{int(time.time())}"
    started = time.perf_counter()
    run = AgentRun(user_id=str(user_id), status="error")

    try:
        prompts = load_prompts()
        messages: list[dict[str, object]] = [
            {"role": "system", "content": prompts["system_prompt"]},
            {
                "role": "user",
                "content": prompts["user_prompt_template"].replace("{user_id}", str(user_id)),
            },
        ]
        # 固定開銷（system prompt + 每次呼叫都重送的工具宣告）必須先計入，
        # 否則預算會系統性低估約 1,500 token
        used_tokens = sum(estimate_tokens(str(m.get("content", ""))) for m in messages)
        used_tokens += estimate_tokens(json.dumps(agent_tools.TOOL_DEFINITIONS, ensure_ascii=False))
        loop = asyncio.get_running_loop()

        # ── 收集階段（thinking 關閉）─────────────────────────────────
        budget_exhausted = False
        for step in range(1, max_steps + 1):
            await _yield_to_foreground(trace)
            result = await _call_model(
                service,
                messages=messages,
                trace=trace,
                model=model,
                tools=agent_tools.TOOL_DEFINITIONS,
                think=False,
                temperature=0.3,
                trace_id=trace,
            )
            run.steps = step

            if not result.wants_tool_call:
                logger.info(
                    "persona agent trace=%s 第 %d 步不再呼叫工具，進入產出階段", trace, step
                )
                break

            messages.append({
                "role": "assistant",
                "content": result.content,
                "tool_calls": result.tool_calls,
            })

            # 模型常在同一步丟出多個 tool_calls；預算必須**逐次**檢查，
            # 否則一步塞六個 get_conversation 就會直接衝破上限。
            # 超出後仍要對每個 tool_call_id 回覆（協議要求），只是改回佔位字串。
            for call in result.tool_calls:
                fn = call.get("function") or {}
                name = str(fn.get("name") or "")
                arguments = fn.get("arguments") or "{}"
                call_started = time.perf_counter()
                if used_tokens >= token_budget:
                    budget_exhausted = True
                    payload = _OMITTED_PAYLOAD
                else:
                    payload = await loop.run_in_executor(
                        None,
                        functools.partial(
                            agent_tools.dispatch, ctx, name=name, arguments=arguments
                        ),
                    )
                elapsed_ms = int((time.perf_counter() - call_started) * 1000)
                run.trace.append(StepTrace(
                    step=step,
                    tool=name,
                    arguments=str(arguments)[:300],
                    result_preview=payload[:200],
                    elapsed_ms=elapsed_ms,
                ))
                logger.info(
                    "persona agent trace=%s step=%d tool=%s args=%s %dms → %s",
                    trace, step, name, str(arguments)[:120], elapsed_ms, payload[:120],
                )
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.get("id"),
                    "name": name,
                    "content": payload,
                })
                used_tokens += estimate_tokens(payload)

            if budget_exhausted or used_tokens >= token_budget:
                budget_exhausted = True
                logger.info(
                    "persona agent trace=%s token 預算用盡（估 %d ≥ %d），停止收集",
                    trace, used_tokens, token_budget,
                )
                break
        else:
            # 跑滿 max_steps 仍在呼叫工具：照樣進產出階段，但把狀態記下來供調參
            run.status = "max_steps"
            logger.warning("persona agent trace=%s 用滿 %d 步仍在呼叫工具", trace, max_steps)

        run.estimated_tokens = used_tokens

        # ── 產出階段（thinking 打開 + 強制 JSON schema）───────────────
        final_prompt = prompts["final_prompt"]
        if budget_exhausted:
            final_prompt = (
                "（資料量已達上限，不能再呼叫工具。請就手上的資料作答。）\n\n" + final_prompt
            )
        messages.append({"role": "user", "content": final_prompt})

        await _yield_to_foreground(trace)
        final = await _call_model(
            service,
            messages=messages,
            trace=trace,
            model=model,
            response_format=build_response_format(),
            think=True,
            temperature=0.3,
            timeout=final_timeout,
            trace_id=trace,
        )

        try:
            diff = json.loads(final.content)
        except json.JSONDecodeError as exc:
            run.status = "rejected_schema"
            run.error = f"最終輸出不是合法 JSON：{exc}"
            logger.error(
                "persona agent trace=%s 最終輸出解析失敗：%s | raw=%s",
                trace, exc, final.content[:300],
            )
            return run

        run.diff = diff
        if run.status != "max_steps":
            run.status = "ok"
        return run

    except ContextExceeded as exc:
        # 明確狀態：本次可用 context 不足（白天前景在搶共用 KV 時最常見）。
        # 不產出降級結果，明晚重跑。
        run.status = "context_exceeded"
        run.error = str(exc)
        logger.warning("persona agent trace=%s context 不足，本次放棄：%s", trace, exc)
        return run
    except Exception as exc:  # 單人失敗不影響其他人
        run.status = "error"
        run.error = f"{type(exc).__name__}: {exc}"
        logger.error("persona agent trace=%s 執行失敗：%s", trace, exc, exc_info=True)
        return run
    finally:
        run.duration_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "persona agent trace=%s 結束 status=%s steps=%d tools=%d tokens≈%d %.1fs",
            trace, run.status, run.steps, len(run.trace),
            run.estimated_tokens, run.duration_ms / 1000,
        )

