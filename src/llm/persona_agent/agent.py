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
from services.llm_service import LLMAPIError
from llm.persona_agent import tools as agent_tools
from llm.persona_agent.schema import build_response_format
from sys_settings.llm_settings import AmbientChatSettings

logger = logging.getLogger("discord_bot")

MAX_STEPS = 8

#: 最終產出要不要開 thinking。**預設關閉**——mock benchmark（四個判斷陷阱、各跑兩次）
#: 顯示開關對品質沒有可測差異：兩邊都正確推翻過時描述、判對互損文化、誠實標註無證據的
#: 項目、零幻覺；開啟的那組反而出現一次自相矛盾（同一份 diff 既 keep 又 revise
#: 「安靜寡言」）。代價卻是**慢 4.5 倍**（平均 233s vs 51s）。
#:
#: 真實資料上更慘：thinking 三戰三敗，每次都在推理階段把 32k context 用光
#: （prompt 17k~22k + 推理 10k~12k），`finish_reason=length`、content 全空。
#:
#: 開關保留（`chat_template_kwargs.enable_thinking` 的轉接已打通），日後想再比較隨時能開。
FINAL_STEP_THINKING = False

# 收集階段的 prompt 上限（**以伺服器回報的 usage.prompt_tokens 為準，不是估的**）。
#
# ctx_size=32768 是 prompt + 生成**共用**的。關掉 thinking 後生成只剩答案本身
# （實測 1,200~4,800 token），不必再為推理預留 20k → 預算從 12,000 拉到 24,000，
# **省下來的空間拿去裝證據**。這個任務的判斷靠證據而非推理，多一倍資料比多想一輪值。
#
# 仍要留餘裕：估算會低估（曾估 14,501 而實際 22,379，差 1.54 倍），因為估算漏了
# assistant 訊息的 tool_calls 結構、最終指示、以及 chat template 本身的標記。
TOKEN_BUDGET = 20000

#: 估算的自我校正上下限。估算一定低估（漏算 assistant 訊息的 tool_calls 結構、最終指示、
#: chat template 標記），實測 12,000 的預算讓 prompt 衝到 17,191——**超標 43%**。
#: 每輪用伺服器回報的實際值反推「上一輪估得多準」，之後的估算乘上這個係數：
#: **用實測校正，不用猜倍數**。夾在範圍內避免單次異常把係數帶歪。
ESTIMATE_SCALE_RANGE = (1.0, 4.0)
# 預算用盡後，仍保留給 `search_messages` 的額外額度。
#
# 實測一次：模型在最後一步搜「PY」「米拉」「機械」——**問題問得完全正確**，卻正好撞上
# 預算用盡，三個都回佔位字串。它只好在 notes 寫「無法確認」，但那些詞在 14 天內都還在
# （PY 出現 14 次）。search 的回傳上限只有 50 則短訊息，砍它省不到多少 context，
# 損失的卻是**查證能力**——那是 revise / keep 判斷的依據。
SEARCH_RESERVE_TOKENS = 2500
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
    #: True 代表最終步的 thinking 把 context 想光（finish_reason=length、content 全空），
    #: 改以關閉 thinking 重跑產出。輸入沒被動過，只是少了深思——評測時要分開看。
    thinking_exhausted: bool = False
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
        # 第一次呼叫前沒有實際值可用，先粗估；第一次呼叫後就換成伺服器回報的數字
        used_tokens = sum(estimate_tokens(str(m.get("content", ""))) for m in messages)
        used_tokens += estimate_tokens(json.dumps(agent_tools.TOOL_DEFINITIONS, ensure_ascii=False))
        pending_tokens = 0
        # 估算低估多少倍。第一輪沒有實際值可比，先假設準確；拿到實際值後就開始校正。
        estimate_scale = 1.0
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
            # 伺服器算的精確值，取代上一輪的估算（含 chat template 標記等我們看不到的部分）
            actual = (result.usage or {}).get("prompt_tokens")
            if isinstance(actual, int) and actual > 0:
                if pending_tokens > 0 and actual > used_tokens:
                    # 上一輪估了 pending_tokens，實際長了 (actual - used_tokens)。
                    # 兩者比值＝估算的低估倍數 → 校正之後的估算。用實測，不猜倍數。
                    lo, hi = ESTIMATE_SCALE_RANGE
                    estimate_scale = max(lo, min(hi, (actual - used_tokens) / pending_tokens))
                    logger.info(
                        "persona agent trace=%s 估算校正：估 %d、實際長 %d → 係數 %.2f",
                        trace, pending_tokens, actual - used_tokens, estimate_scale,
                    )
                used_tokens = actual
                pending_tokens = 0

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

            # 這一步有沒有真的執行到工具。全部被擋（只回佔位字串）就沒有繼續的理由——
            # 否則批量被擋之後 pending 不再成長，迴圈會一路空轉到 max_steps。
            executed_this_step = False

            # 模型常在同一步丟出多個 tool_calls；預算必須**逐次**檢查，
            # 否則一步塞六個 get_conversation 就會直接衝破上限。
            # 超出後仍要對每個 tool_call_id 回覆（協議要求），只是改回佔位字串。
            for call in result.tool_calls:
                fn = call.get("function") or {}
                name = str(fn.get("name") or "")
                arguments = fn.get("arguments") or "{}"
                call_started = time.perf_counter()
                # search_messages 走保留額度：預算用盡後仍可再查幾次（回傳小、價值高）
                projected = used_tokens + pending_tokens * estimate_scale
                over = projected >= token_budget
                ceiling = token_budget + (
                    SEARCH_RESERVE_TOKENS if name == "search_messages" else 0
                )
                if projected >= ceiling:
                    budget_exhausted = True
                    payload = _OMITTED_PAYLOAD
                elif over:
                    logger.info(
                        "persona agent trace=%s 預算已滿，但放行 search_messages（保留額度）",
                        trace,
                    )
                    payload = await loop.run_in_executor(
                        None,
                        functools.partial(
                            agent_tools.dispatch, ctx, name=name, arguments=arguments
                        ),
                    )
                    executed_this_step = True
                else:
                    payload = await loop.run_in_executor(
                        None,
                        functools.partial(
                            agent_tools.dispatch, ctx, name=name, arguments=arguments
                        ),
                    )
                    executed_this_step = True
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
                # 這一步新增的工具結果還沒被伺服器算過，先估；下一輪呼叫後會被實際值取代
                pending_tokens += estimate_tokens(payload)

            if used_tokens + pending_tokens * estimate_scale >= (
                token_budget + SEARCH_RESERVE_TOKENS
            ):
                budget_exhausted = True
            if budget_exhausted and not executed_this_step:
                logger.info(
                    "persona agent trace=%s prompt 預算用盡（實際 %d + 增量估 %d×%.2f ≥ %d）"
                    "且本步無工具執行成功，停止收集",
                    trace, used_tokens, pending_tokens, estimate_scale, token_budget,
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
        final_kwargs = dict(
            model=model,
            response_format=build_response_format(),
            temperature=0.3,
            timeout=final_timeout,
            trace_id=trace,
        )
        try:
            final = await _call_model(
                service, messages=messages, trace=trace,
                think=FINAL_STEP_THINKING, **final_kwargs
            )
        except LLMAPIError as exc:
            # thinking 把 context 想光：finish_reason=length、content 全空、推理塞滿 32k。
            # 關掉 thinking 重跑一次——**輸入完全沒動**，只是少了深思，這跟「裁掉資料再問」
            # 是兩回事：那個會產出假陰性，這個只是品質降一級，而且有旗標標記得出來。
            if getattr(exc, "kind", None) != "empty_content" or not FINAL_STEP_THINKING:
                # thinking 本來就關著還空 content → 是真的異常，不該吞掉當成「想太久」
                raise
            run.thinking_exhausted = True
            logger.warning(
                "persona agent trace=%s thinking 用光 context，改以關閉 thinking 重試", trace
            )
            await _yield_to_foreground(trace)
            final = await _call_model(
                service, messages=messages, trace=trace, think=False, **final_kwargs
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
        if run.thinking_exhausted:
            logger.warning(
                "persona agent trace=%s 本次未經 thinking 產出（推理把 context 用光），"
                "評測時需與正常結果分開看", trace,
            )



# ── 驗證 + 寫入（M3）────────────────────────────────────────────────────
#: 連續失敗時的預算降級。**重點不是省 GPU（一人一晚約 3 分鐘），是避免沉默失敗**——
#: 確定性失敗（例如某人的資料量就是撐爆 context）每晚重跑都一樣爆，而沒人會發現。
#: 降到第 3 次仍失敗就隔離，讓它浮出來變成維運報告上的一行。
DEGRADE_BY_FAILURES = {0: 1.0, 1: 0.7, 2: 0.5}
QUARANTINE_AFTER_FAILURES = 3


def resolve_keeps(
    changes: list[dict[str, Any]], base_changes: Any
) -> list[dict[str, Any]]:
    """把 `keep` 的文字換成上一版 `ref` 指到的原文。

    **`keep` 原本是個謊言**：schema 要求每一項都寫 `text`，所以模型標成「維持不變」
    的項目還是得自己重寫一遍——實測 43.7% 的 keep 文字其實變了。真實案例：

        v1  「何意味」是固定口頭禪，用來表達困惑，常搭配疑惑類表情一起發。
        v2  「何意味」是固定口頭禪，用來表達困惑或無言，常搭配疑惑類表情一起發。
                                              ↑ 標 keep 卻多了「或無言」

        v1  貼圖使用極少，僅在看戲/吃瓜情境下偶爾用（吃瓜、疑惑類），情緒表達幾乎全靠打字
        v2  貼圖使用極少，情緒表達幾乎全靠打字
              ↑ 標 keep 卻遺失了一半資訊

    沿用原文之後，想改就**必須**標成 revise——偽裝成 keep 的偷偷改寫不再可能。

    trait 也沿用：09-22 有 17 個 keep 因為模型把 trait 留空而被退件，項目跟著消失。
    上一版的 trait 是空的才用模型寫的。

    `ref` 對不上（0、超出範圍、上一版沒有 changes）時保留模型寫的 text：
    第一次跑是以 production 的散文為基準，那時根本沒有可指涉的項目。
    """
    by_n = {i["n"]: i for i in agent_tools._persona_items(base_changes)}
    out: list[dict[str, Any]] = []
    for c in changes:
        if not isinstance(c, dict):
            out.append(c)
            continue
        if str(c.get("type") or "") == "keep":
            original = by_n.get(_as_int(c.get("ref")))
            if original:
                c = {**c, "text": original["text"],
                     "trait": original["trait"] or c.get("trait", "")}
        out.append(c)
    return out


#: keep 沿用證據的上限：最早的 8 則（寫下這句話時的證據）＋最新的 4 則（最近的佐證）。
#: 不設上限的話，每晚多附一兩則就會一路長下去。只留最新的也不行——最早那幾則正是
#: 這句話的依據，「糯糯」那項就是證據被換到只剩近期的，才看起來像幻覺。
KEEP_EVIDENCE_HEAD = 8
KEEP_EVIDENCE_TAIL = 4


def inherit_keep_evidence(
    accepted: list[dict[str, Any]],
    base_changes: Any,
    history: Optional[dict[str, list[str]]] = None,
) -> list[dict[str, Any]]:
    """keep 沿用這段文字引用過的證據，再接上今晚新附的。

    **要在驗證之後做**：驗證層只該反查模型今晚宣稱的 id。沿用的 id 寫進版本表時
    就驗過了，混進去重驗會讓 `evidence_claimed` 灌水、幻覺率的分母變成另一個東西。

    文字沿用（`resolve_keeps`）之後，證據也必須跟著沿用，這句話和它的依據才會
    一直綁在一起。`ref` 對不上的 keep 不動（沒有上一版可以沿用）。

    `history`（`store.evidence_history`）是同一段文字在**所有**版本引用過的證據。
    只看上一版的話，以前被換掉的正確證據就永遠回不來——排序是歷史在前、上一版
    其次、今晚新附的最後，所以寫下這句話時的依據會落在保留的前 8 則裡。
    """
    raw = base_changes if isinstance(base_changes, list) else []
    # 編號規則必須跟模型看到的清單一致，所以同樣從 `_persona_items` 取
    by_n = {i["n"]: raw[i["n"] - 1] for i in agent_tools._persona_items(raw)}
    out: list[dict[str, Any]] = []
    for c in accepted:
        if isinstance(c, dict) and str(c.get("type") or "") == "keep":
            original = by_n.get(_as_int(c.get("ref")))
            if original is not None:
                past = (history or {}).get(str(original.get("text") or "").strip(), [])
                old = original.get("evidence_msg_ids")
                new = c.get("evidence_msg_ids")
                ids = list(dict.fromkeys(
                    [str(i) for i in past]
                    + [str(i) for i in (old if isinstance(old, list) else [])]
                    + [str(i) for i in (new if isinstance(new, list) else [])]
                ))
                if len(ids) > KEEP_EVIDENCE_HEAD + KEEP_EVIDENCE_TAIL:
                    ids = ids[:KEEP_EVIDENCE_HEAD] + ids[-KEEP_EVIDENCE_TAIL:]
                c = {**c, "evidence_msg_ids": ids}
        out.append(c)
    return out


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def compose_persona_text(changes: list[dict[str, Any]]) -> str:
    """把通過驗證的變更組成完整人格描述。

    `add` / `revise` / `keep` 三種都是在描述「這個人現在的樣子」，所以直接串起來就是
    當前人格。**存完整文字而不只存 diff**：消費端（persona card / askai / 插話）要的是
    「他現在什麼樣子」，只存 diff 的話每次讀都得重播全部歷史。diff 是給人稽核用的，
    完整文字是給機器讀的，兩個都要存。
    """
    return "；".join(
        str(c.get("text") or "").strip()
        for c in changes
        # drop 是「刪掉這一項」，不是描述——就算模型在它的 text 裡寫了東西也不能串進去
        if str(c.get("type") or "") != "drop" and str(c.get("text") or "").strip()
    )


async def run_db(fn, *args, **kwargs):
    """同步 DB 呼叫一律丟 executor。

    `store`、`validation`、`batch.select_targets` 走的是同步 psycopg2；直接在 async 裡
    呼叫會**卡住整個 event loop**（音樂、Discord 心跳、插話全部停住）。批次跑 10 人
    就是 60 次阻塞，而 `select_targets` 那句實測就要 1 秒。

    **放在模組層而不是 `run_and_persist` 內的 closure**：M4 的 `run_batch` 是第二個
    async 進入點，closure 借不到就會各寫一份 `run_in_executor`。
    `test_persona_agent_loop.BlockingCallTests` 會掃這兩支的原始碼把關。
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, functools.partial(fn, *args, **kwargs))


async def run_and_persist(
    *,
    user_id: str,
    guild_id: int,
    ctx: agent_tools.ToolContext,
    model: str,
    run_id: str,
    llm_service: Any = None,
    save: bool = True,
) -> tuple[AgentRun, Any]:
    """跑一位使用者 → 驗證 → 寫入兩張表。回傳 `(AgentRun, ValidationResult|None)`。

    `run_for_user` 保持純粹（只產出 diff、不碰 DB），寫入集中在這裡，M4 的批次直接
    呼叫這支即可。`save=False` 時只驗證不寫，給除錯指令用。

    **執行前先看連續失敗次數**：失敗越多次預算調得越保守，超過門檻就跳過並記
    `quarantined`——不然某個人可能每晚都失敗、而沒有任何地方看得出來。
    """
    from llm.persona_agent import store, validation

    failures = await run_db(store.consecutive_failures, guild_id, user_id) if save else 0
    if failures >= QUARANTINE_AFTER_FAILURES:
        run = AgentRun(user_id=str(user_id), status="quarantined")
        run.error = f"連續失敗 {failures} 次，本次跳過（需人工檢視）"
        logger.warning("persona agent %s 已隔離：%s", user_id, run.error)
        if save:
            await run_db(
                store.record_run,
                run_id=run_id, guild_id=guild_id, author_id=user_id,
                status=run.status, steps=0, tool_calls=0, prompt_tokens=None,
                thinking_exhausted=False, evidence_claimed=0, evidence_bogus=0,
                accepted_changes=0, rejected_changes=0, skip_reason=run.error,
                trace=[], rejected=None, quote_unmatched=None,
                quote_misses=None, skipped_changes=None, ref_accounting=None,
                duration_ms=0, error=run.error,
            )
        return run, None

    budget = int(TOKEN_BUDGET * DEGRADE_BY_FAILURES.get(failures, 0.5))
    if failures:
        logger.info(
            "persona agent %s 連續失敗 %d 次 → 預算降到 %d", user_id, failures, budget
        )

    run = await run_for_user(
        user_id=user_id, ctx=ctx, model=model,
        llm_service=llm_service, token_budget=budget, trace_id=run_id,
    )

    result = None
    version = None
    if run.diff is not None:
        # **先解析 keep 再驗證**：keep 的文字沿用上一版原文，而驗證層會把空 text
        # 當成「語意空殼」退掉。順序顛倒的話每個 keep 都會被誤殺。
        latest = None
        try:
            latest = await run_db(store.latest_version, guild_id, user_id)
        except Exception:
            pass
        if isinstance(run.diff.get("changes"), list):
            run.diff["changes"] = resolve_keeps(
                run.diff["changes"], latest.get("changes") if latest else None
            )

        # 上一版的編號清單：拿來查「每一項有沒有被交代」。沒有上一版（第一次跑、
        # 基準是 production 的散文）就傳 None，不做這項檢查。
        base_refs = (
            [i["n"] for i in agent_tools._persona_items(latest.get("changes"))]
            if latest else None
        )
        result = await run_db(
            validation.validate_diff, run.diff, user_id=user_id, fetch=ctx.fetch,
            base_refs=base_refs,
        )
        # 有上一版才有 keep 可沿用，沒有就不必讀歷史（第一次跑省一次查詢）
        history = (
            await run_db(store.evidence_history, guild_id, user_id) if latest else None
        )
        result.accepted = inherit_keep_evidence(
            result.accepted, latest.get("changes") if latest else None, history
        )
        if save and result.skip_reason is None:
            base = f"v{latest['version']}" if latest else "production"
            version = await run_db(
                store.write_version,
                guild_id=guild_id, author_id=user_id,
                persona_text=compose_persona_text(result.accepted),
                changes=result.accepted,
                confidence=str(run.diff.get("confidence") or ""),
                notes=str(run.diff.get("notes") or ""),
                model=model, based_on=base,
            )

    if save:
        await run_db(
            store.record_run,
            run_id=run_id, guild_id=guild_id, author_id=user_id,
            status=run.status, steps=run.steps, tool_calls=len(run.trace),
            prompt_tokens=run.estimated_tokens,
            thinking_exhausted=run.thinking_exhausted,
            evidence_claimed=result.evidence_claimed if result else 0,
            evidence_bogus=result.evidence_bogus if result else 0,
            accepted_changes=len(result.accepted) if result else 0,
            rejected_changes=len(result.rejected) if result else 0,
            skip_reason=result.skip_reason if result else None,
            # 被退掉的完整內容：只記數字的話，「為什麼會幻覺」永遠查不下去
            rejected=result.rejected if result else None,
            quote_unmatched=result.quote_unmatched if result else None,
            quote_misses=result.quote_misses if result else None,
            # 通過驗證卻沒寫成版本時（`skip_reason` 有值），內容只存在記憶體裡。
            # 只記 `accepted_changes=5` 這個數字，「那五項寫了什麼」就永遠查不到——
            # 而低量使用者能不能寫出東西，正是 M6 要判斷的。寫成版本的那條路不必存，
            # 內容在 `persona_agent_versions` 裡。
            skipped_changes=(
                result.accepted if result and result.skip_reason is not None else None
            ),
            ref_accounting=result.ref_accounting if result else None,
            trace=[{
                "step": t.step, "tool": t.tool, "args": t.arguments,
                "result": t.result_preview, "ms": t.elapsed_ms,
            } for t in run.trace],
            duration_ms=run.duration_ms, error=run.error,
        )
    if version:
        logger.info("persona agent %s 寫入 v%d", user_id, version)
    return run, result
