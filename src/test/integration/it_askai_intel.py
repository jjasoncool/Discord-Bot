"""/askai 查遊戲情報與網路：用真的模型、真的 search-mcp 與 SearXNG，跑幾題完整的回答流程，只印結果、不送 Discord。

用途：上線前、改了 askai_intel_rules.txt／askai_web_rules.txt 或工具輪的參數後，抽查「該查的有沒有查、查對邊
（遊戲問題查情報、時事查網路）、不該查的有沒有亂查、回答有沒有分開講官方與玩家說法、有沒有附對的網址」。
走的是 /askai 工具模式同一條路（`run_with_intel(also=[WebSearchTools])` → `generate_reply` 的工具輪），
沒有聊天紀錄與人物卡（那些和查不查無關）。
會呼叫主模型（每題幾十秒，排同一把 GPU 鎖），不要在 04:00～07:30 維護時段跑。

執行（容器內）：
    docker exec -w /app discord-bot python -m test.integration.it_askai_intel            # 預設題目
    docker exec -w /app discord-bot python -m test.integration.it_askai_intel "卜靈是什麼身分？"
"""
import asyncio
import sys
import time

from commands.llm_commands import INTEL_SETTINGS, WEB_SETTINGS, load_system_prompt
from llm.retrievers.intel import run_with_intel
from llm.retrievers.web import WebSearchTools
from services.llm_service import LLMService

#: 情報題、攻略題各一，一題該查網路的時事，加一題不該查的閒聊
DEFAULT_QUESTIONS = [
    "3.2 版本前瞻直播的兌換碼是什麼？",
    "今汐要怎麼配隊？",
    "明天台北會下雨嗎？",
    "今天好累喔，你今天過得怎樣？",
]


async def answer(service: LLMService, question: str, *, trace_id: str):
    """走 /askai 工具模式同一條路回答一題。回傳（回答結果、查情報的經過、網路搜尋工具）。
    Agent 評估（`it_askai_agent_eval`）也用這個，兩邊量的才是同一條路。"""
    meta: dict = {"mode": "on"}

    async def generate(tool_runner):
        return await service.generate_reply(
            prompt=question, system=load_system_prompt(), tool_runner=tool_runner,
            max_tool_rounds=INTEL_SETTINGS.max_tool_rounds,
            trace_id=trace_id,
        )

    web = WebSearchTools(settings=WEB_SETTINGS)
    result = await run_with_intel(generate, question=question, enabled=True, meta=meta, settings=INTEL_SETTINGS,
                                  also=[web])
    return result, meta, web


async def ask(service: LLMService, question: str) -> None:
    started = time.monotonic()
    result, meta, web = await answer(service, question, trace_id=f"it-intel-{int(started)}")
    print("=" * 70)
    print(f"問：{question}（{time.monotonic() - started:.1f} 秒，連上 search-mcp：{meta.get('connected')}）")
    for call in meta.get("calls") or []:
        outcome = call.get("error") or f"{len(call.get('result_ids') or [])} 筆 {call.get('result_ids')}"
        print(f"  查：{call['tool']} {call['arguments']}（{call['elapsed_ms']} ms）→ {outcome}")
    for call in web.calls:
        outcome = call.get("error") or f"{call.get('result_count')} 筆 {call.get('result_urls')}"
        print(f"  網路：[{call.get('kind')}] {call.get('query')} {call.get('route')}（{call['elapsed_ms']} ms）→ {outcome}"
              f"，直接答案 {call.get('answer_count', 0)} 則")
    if not meta.get("calls") and not web.calls:
        print("  （沒有查）")
    print(f"答：{result.reply}")
    if result.error_kind:
        print(f"  錯誤類型：{result.error_kind}")


async def main(questions: list[str]) -> None:
    service = LLMService()
    for question in questions:
        await ask(service, question)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:] or DEFAULT_QUESTIONS))
