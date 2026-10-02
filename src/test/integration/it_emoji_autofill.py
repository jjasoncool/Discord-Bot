"""看圖補字典：拿真實聊天紀錄裡最常用、還沒描述的表情，實際問模型，只印結果、不寫字典。

用途：上線前或改 prompt 後抽查描述品質（`settings/prompts/emoji_autofill_prompt.txt`）。
會呼叫模型（佔 GPU 幾十秒），不要在 04:00～07:30 維護時段跑。

執行（容器內）：
    docker exec -w /app discord-bot python -m test.integration.it_emoji_autofill [張數，預設 8]
圖片另存到 /tmp/emoji_autofill_check/，方便對照。
"""
import asyncio
import base64
import collections
import re
import sys
from pathlib import Path
from types import SimpleNamespace

from llm.preprocess import emoji_autofill as af
from llm.preprocess import emoji_dictionary
from sys_settings.llm_settings import LLMServiceSettings

OUT = Path("/tmp/emoji_autofill_check")


def recent_targets(limit: int):
    """近 30 天最常用、需要補描述的表情：(名稱, 網址, 一則用到它的訊息)。"""
    conn = LLMServiceSettings().pgvector_connect()
    try:
        cur = conn.cursor()
        cur.execute("select content from discord_messages_raw where created_at > now() - interval '30 days' "
                    "and content ~ '<a?:\\w+:\\d+>' order by created_at desc")
        rows = [r[0] for r in cur.fetchall()]
    finally:
        conn.close()
    known = emoji_dictionary.entries()
    counts = collections.Counter()
    sample = {}
    for content in rows:
        for animated, name, emoji_id in re.findall(r"<(a?):(\w+):(\d+)>", content or ""):
            entry = known.get(name)
            if entry is None or entry.needs_description:
                counts[name] += 1
                url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{'gif' if animated else 'png'}"
                sample.setdefault(name, (url, content))
    return [(name, *sample[name]) for name, _ in counts.most_common(limit)]


async def main(limit: int):
    OUT.mkdir(exist_ok=True)
    async with af._session() as session:
        for name, url, content in recent_targets(limit):
            target = af.Target("emoji", f"emoji:{name}", name, url)
            context = af._context_lines(SimpleNamespace(content=content, stickers=[], mentions=[], guild=None,
                                                        reference=None))
            images = await af.download_images(session, [url], limit=1)
            if not images:
                print(f"{name}: 下載不到圖 {url}")
                continue
            (OUT / f"{name}.png").write_bytes(base64.b64decode(images[0]))
            answer = await af._ask_model(target, images[0], context)
            parsed = af.parse_answer(answer, max_chars=af._SETTINGS.max_description_chars)
            print(f"{name}: {parsed}  ← 模型原文 {answer!r}｜訊息 {context[-1][:60]!r}")


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 8))
