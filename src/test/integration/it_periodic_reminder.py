"""週期活動提醒：手動發一則提醒到指定頻道，實測 @ 身份組與靜音（需要 live Discord）。

**為什麼放 integration/**：會真的發訊息到 Discord。`docker-compose.yaml` 的啟動 gate
只跑 `test_*.py`，`it_*.py` 自動排除。

用法（在 discord-bot 容器內，DISCORD_TOKEN 已注入）：
    python -m test.integration.it_periodic_reminder reset sea            # 發到綁定的提醒頻道
    python -m test.integration.it_periodic_reminder ending tower <頻道id>  # 發到指定頻道
    加 --no-ping：照樣發文案，但不讓 @ 生效（只看排版）

- `reset`：講「最近一次」重置（例：9/28 海墟已重置、到 10/26），**靜音 @**
- `ending`：講「下一次」重置的結束前提醒，**正常 @**（會跳通知）

文案與發送參數跟正式排程共用 `services.events.periodic_reminder`；這支不寫 StateDB、不置底面板，
所以不會影響正式排程的去重。身份組 id 取自 runtime 檔，要先在 /server_manager 綁定
「週期提醒頻道」（綁定時會自動建立身份組）。
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import aiohttp

HERE = Path(__file__).resolve().parent
SRC_DIR = HERE.parent.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from services.events.event_time_parser import SERVER_TZ  # noqa: E402
from services.events.periodic_reminder import (  # noqa: E402
    KIND_ENDING,
    KIND_RESET,
    build_reminder_text,
    last_reset,
    next_reset,
    reminders_for,
)
from sys_settings.periodic_reminder_settings import PeriodicReminderSettings  # noqa: E402

#: Discord MessageFlags.suppress_notifications（等同 discord.py 的 silent=True）
SUPPRESS_NOTIFICATIONS = 1 << 12

USAGE = "用法：python -m test.integration.it_periodic_reminder {ending|reset} {cycle key} [頻道id] [--no-ping]"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


async def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    no_ping = "--no-ping" in sys.argv
    if len(args) < 2 or args[0] not in (KIND_ENDING, KIND_RESET):
        print(USAGE)
        return 2

    settings = PeriodicReminderSettings()
    kind, cycle_key = args[0], args[1]
    cycle = next((c for c in settings.cycles if c.key == cycle_key), None)
    if cycle is None:
        print(f"沒有這個項目：{cycle_key}（可用：{', '.join(c.key for c in settings.cycles)}）")
        return 2

    role_id = _load_json(SRC_DIR / settings.runtime_path).get("role_id")
    if not role_id:
        print("runtime 檔沒有 role_id：請先在 /server_manager 綁定「週期提醒頻道」")
        return 1
    channel_id = args[2] if len(args) > 2 else _load_json(SRC_DIR / "config.json").get(settings.channel_config_key)
    if not channel_id:
        print("沒有指定頻道，config.json 也還沒綁定週期提醒頻道")
        return 1

    now = datetime.now(SERVER_TZ)
    reset_at = last_reset(cycle, now) if kind == KIND_RESET else next_reset(cycle, now)
    ending, reset = reminders_for(cycle, reset_at, settings)
    reminder = reset if kind == KIND_RESET else ending

    payload = {
        "content": build_reminder_text(reminder, f"<@&{role_id}>", now),
        "allowed_mentions": {"parse": [], "roles": [] if no_ping else [str(role_id)]},
    }
    if reminder.silent:
        payload["flags"] = SUPPRESS_NOTIFICATIONS

    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("環境變數沒有 DISCORD_TOKEN（請在 discord-bot 容器內執行）")
        return 1
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"https://discord.com/api/v10/channels/{channel_id}/messages",
            json=payload,
            headers={"Authorization": f"Bot {token}",
                     "User-Agent": "DiscordBot (integration-test, 0.1)"},
        ) as r:
            body = await r.text()
            if r.status >= 300:
                print(f"Discord 回 HTTP {r.status}：{body[:400]}")
                return 1
    print(f"已發送（{kind}，silent={reminder.silent}，ping={not no_ping}）到頻道 {channel_id}：")
    print(payload["content"])
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
