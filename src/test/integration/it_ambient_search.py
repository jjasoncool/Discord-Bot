"""手動驗收：用真的模型跑插話的查詢工具（記錄模式），看模型遇到新梗會不會叫工具、閒聊會不會亂查、
帶圖加工具後端接不接受、查完還守不守 [PASS]／#N 的格式、回覆有沒有網址。只印結果，不送任何東西到 Discord。

記錄模式本來就不出網：工具回給模型的是固定說明，這裡量的是「想不想查、查什麼、多花幾秒」。
會佔用主模型，不要在 04:00～07:30 維護時段跑；這支腳本是另一個行程，靠 `gpu_gate` 的跨行程鎖檔跟 bot 排隊。
執行（容器內）：
    docker exec -w /app discord-bot python -m test.integration.it_ambient_search            # 全部情境
    docker exec -w /app discord-bot python -m test.integration.it_ambient_search 新梗 帶圖   # 指定情境
"""
import asyncio
import base64
import io
import re
import sys
import time
from datetime import datetime

from llm.ambient import ambient_reply, ambient_search
from llm.ambient.ambient_reply import _load_ambient_prompt
from sys_settings.llm_settings import AskAIIntelSettings, load_llm_runtime_config, LLMServiceSettings
from sys_settings.time_settings import APP_TZ

SPONTANEOUS_PROMPT = (
    "（以上是你在群裡旁觀到的最新對話。最新一則是群友彼此在講話、不一定是對你說的——"
    "先判斷適不適合插話；要插就接整段對話裡的具體一點，否則只輸出 [PASS]。）"
)
BOT = "琇紫#0001"
URL = re.compile(r"https?://")

SCENARIOS = {
    "新梗": dict(
        directed=False,
        chat=["#1 [21:02] 阿凱#1023: 剛那場排位被秒殺", "#2 [21:03] 小魚#7788: 對面整隊都在玩這波",
              "#3 [21:03] 阿凱#1023: 這波是標準的何意味 笑死", "#4 [21:04] 小魚#7788: 何意味 XD"],
        latest="#4 [21:04] 小魚#7788: 何意味 XD",
        expect_tool=True,
    ),
    "閒聊": dict(
        directed=False,
        chat=["#1 [22:10] 阿凱#1023: 今天好累", "#2 [22:11] 小魚#7788: 抽卡又歪了啦",
              "#3 [22:11] 阿凱#1023: 保底前不衝活該", "#4 [22:12] 小魚#7788: 嗚嗚"],
        latest="#4 [22:12] 小魚#7788: 嗚嗚",
        expect_tool=False,
    ),
    "被@問新東西": dict(
        directed=True,
        chat=["#1 [20:00] 阿凱#1023: 3.7 要出新角色了", "#2 [20:01] 小魚#7788: 誰啊"],
        latest="琇紫 你知道 3.7 版本的新角色是誰嗎",
        expect_tool=True,
    ),
    "帶圖": dict(
        directed=True,
        chat=["#1 [20:00] 阿凱#1023: 看這張"],
        latest="琇紫 這張圖你覺得怎樣",
        expect_tool=None,          # 只看後端接不接受「圖＋工具」
        image=True,
    ),
}


def _png() -> str:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (120, 80, 200)).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


async def _names():
    return ["阿凱", "小魚"]


async def run_one(name: str, spec: dict, model: str) -> dict:
    tools = await ambient_search.prepare(spec["latest"], now=lambda: datetime.now(APP_TZ), names=_names,
                                         trace_id=f"it-{name}", intel_settings=AskAIIntelSettings())
    if tools is None:
        return {"name": name, "error": "開關是 off 或今天額度用完，prepare 回 None"}
    tools.mode = "dry_run"       # 這支腳本只量行為，永遠不出網
    llm = ambient_reply._get_llm()
    started = time.perf_counter()
    result = await llm.generate_reply(
        prompt=spec["latest"] if spec["directed"] else SPONTANEOUS_PROMPT,
        system=_load_ambient_prompt(),
        chat_context=spec["chat"],
        images=[_png()] if spec.get("image") else None,
        model=model,
        bot_display_name=BOT,
        asker_display_name="小魚#7788" if spec["directed"] else None,
        timeout=int(ambient_reply._SETTINGS.pass_timeout_seconds),
        trace_id=f"it-{name}",
        today=ambient_reply._today_line(datetime.now(APP_TZ)),
        tool_runner=tools,
        max_tool_rounds=ambient_search.max_tool_rounds(),
        tool_nudge=ambient_search.NUDGE,
        tools_plain_fallback=False,
        max_tokens=ambient_reply._SETTINGS.directed_max_tokens if spec["directed"] else None,
    )
    elapsed = time.perf_counter() - started
    raw = (result.reply or "").strip()
    line_choice, reply = ambient_reply._parse_line_choice(raw)
    verdicts = []
    if spec["expect_tool"] is True and not tools.records:
        verdicts.append("預期會叫工具，沒叫")
    if spec["expect_tool"] is False and tools.records:
        verdicts.append("預期不查，卻叫了工具")
    if result.error_kind:
        verdicts.append(f"模型呼叫失敗 kind={result.error_kind}")
    if URL.search(raw):
        verdicts.append("回覆裡有網址")
    if "<tool_call>" in raw:
        verdicts.append("工具呼叫漏成文字")
    if not spec["directed"] and raw and not ambient_reply._is_silence(reply, "[PASS]") and line_choice is None:
        verdicts.append("自發插話開口卻沒寫 #N")
    return {
        "name": name, "seconds": round(elapsed, 1), "error_kind": result.error_kind,
        "tool_calls": [(r["tool"], r["query"], r["verdict"]) for r in tools.records],
        "line": line_choice, "reply": reply[:120], "problems": verdicts,
    }


async def main(names: list[str]) -> int:
    settings = LLMServiceSettings()
    model = load_llm_runtime_config(settings.llm_runtime_model_path).ambient_model
    if not model:
        print("llm_runtime_config.json 沒設 ambient_model")
        return 2
    picked = [n for n in SCENARIOS if not names or n in names]
    failures = 0
    for name in picked:
        outcome = await run_one(name, SCENARIOS[name], model)
        print(f"=== {name} ===")
        for key, value in outcome.items():
            if key != "name":
                print(f"  {key}: {value}")
        failures += bool(outcome.get("problems")) or bool(outcome.get("error"))
    print(f"{len(picked)} 個情境，{failures} 個有問題")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
