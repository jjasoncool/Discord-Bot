"""一次性：已經貼在主頻道的 Telegram 轉發，用 LLM 判斷，判成垃圾的移進「垃圾訊息」thread（使用者 2026-10-07）。

每個 pk（相簿給哪一張都行，整本一起判、一起搬）：
1. 判斷：清單檔有寫判定的照清單（使用者看過的，不重判：模型每次判的不一定一樣）；沒寫的用跟轉發同一套的判斷
   （`MessageRelayWorker.judge_existing`；不看 switches.json，開關是給新訊息的；圖沒到齊的不判）
2. 判成垃圾才搬（`MessageRelayWorker.move_to_quarantine`）：在 thread 照正常流程重貼（最上面「判定：…」）
   → 刪主頻道原貼文 → 發送紀錄的頻道欄位改成 thread（送出時間不動）
3. 搬完在 thread 貼放回面板；判錯的用面板放回

不搬的（會印出原因）：認不出本文那則（2026-07-25 以前的舊格式 footer 沒有 db#）、第一次送出未滿 12 小時的相簿、
已經在隔離區或放回過的、主頻道找不到原貼文。

用 bot 的身分只走 HTTP、不連 gateway：線上的 bot 照常跑、不用重啟。模型跟 bot 排同一個隊。

使用方式（容器內）：
    # 預覽：只判斷、列出會刪主頻道哪幾則，不貼、不刪、不改資料庫
    docker exec -w /app discord-bot python scripts/telegram_move_to_quarantine.py 14095
    # 實際搬
    docker exec -w /app discord-bot python scripts/telegram_move_to_quarantine.py 14095 --apply
    # 很多則：清單檔一行一則「pk 標籤 理由」（只寫 pk 的用模型判；# 之後是註解）
    docker exec -w /app discord-bot python scripts/telegram_move_to_quarantine.py --file /tmp/move.txt --apply

復原：log 記了每則改了哪幾列（列 id, pk）；要整批改回，照列 id 把 discord_channel_id 改回主頻道。
放回單則用面板（重新貼回主頻道）。刪了一部分才失敗的，重跑同一則會補完；全刪了才寫不進資料庫的，
log 會留要手動執行的 SQL。
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import timedelta
from pathlib import Path
from typing import Optional

SRC_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SRC_DIR))
os.chdir(SRC_DIR)   # config.json 等相對路徑跟 bot 一樣以 src 為準

from utils.logger_config import configure_logging  # noqa: E402,F401  import 即套用 settings/logging.json

import discord  # noqa: E402

from commands.telegram_quarantine_commands import TelegramQuarantineCommands  # noqa: E402
from services.relay.telegram_filter import RelayFilter, Verdict  # noqa: E402
from services.relay.telegram_quarantine import RUNTIME_PATH, QuarantineThreads  # noqa: E402
from services.relay.telegram_relay_service import (  # noqa: E402
    DiscordMessagePublisher,
    MessageRelayWorker,
    MessageRouteResolver,
    TelegramMessageRepository,
    TelegramRenderAdapter,
    build_telegram_pg_dsn_from_env,
)


class _Publisher(DiscordMessagePublisher):
    """只走 HTTP 時頻道帶的伺服器資料不完整（加成等級不明，上限會被當成最低的 10 MB、大影片被壓縮）：
    用另外查到的伺服器上限。"""

    def __init__(self, file_limit: int) -> None:
        super().__init__()
        self._file_limit = file_limit

    def _get_file_limit(self, channel) -> int:
        return self._file_limit


def _read_targets(args) -> dict[int, Optional[Verdict]]:
    """pk → 清單給的判定（None＝用模型判）。清單檔一行「pk 標籤 理由」，只寫 pk 也行。"""
    targets: dict[int, Optional[Verdict]] = {pk: None for pk in args.pks}
    if args.file:
        for line in Path(args.file).read_text(encoding="utf-8").splitlines():
            fields = line.split("#", 1)[0].split()
            if fields:
                label, reason = (fields[1], " ".join(fields[2:])) if len(fields) > 1 else (None, "")
                targets[int(fields[0])] = Verdict(True, label=label, reason=reason) if label else None
    return targets


async def run(targets: dict[int, Optional[Verdict]], apply: bool) -> None:
    client = discord.Client(intents=discord.Intents.none())
    await client.login(os.environ["DISCORD_TOKEN"])
    repo = TelegramMessageRepository(build_telegram_pg_dsn_from_env())
    await repo.connect()
    try:
        resolver = MessageRouteResolver(config_path="config.json")
        records = {}
        for pk in targets:
            record = await repo.get_message_by_pk(pk)
            if record is None:
                print(f"db#{pk}：找不到，略過")
            else:
                records[pk] = record
        route_ids = sorted({r for rec in records.values() for r in resolver.resolve_telegram_routes(rec.telegram_chat_id)})
        if not route_ids:
            print("沒有要處理的主頻道")
            return

        channels = {route_id: await client.fetch_channel(route_id) for route_id in route_ids}
        guild = await client.fetch_guild(next(iter(channels.values())).guild.id)
        quarantine = QuarantineThreads(client, RUNTIME_PATH)
        worker = MessageRelayWorker(
            bot=client, repository=repo, route_resolver=resolver,
            render_adapter=TelegramRenderAdapter(app_root=str(SRC_DIR)),
            publisher=_Publisher(guild.filesize_limit - 512 * 1024),
            dsn="", content_filter=RelayFilter(), quarantine=quarantine,
        )

        # 主頻道掃一次（從最早那則發文的前一天起），每則用同一份
        since = min(rec.message_date for rec in records.values()) - timedelta(days=1)
        posts: dict[int, list[discord.Message]] = {}
        for channel in channels.values():
            for pk, messages in (await worker.relay_posts(channel, after=since)).items():
                posts.setdefault(pk, []).extend(messages)

        moved_routes: set[int] = set()
        for pk, record in records.items():
            given = targets[pk]
            verdict = given or await worker.judge_existing(pk)
            if verdict is None or not verdict.quarantine:
                why = "判斷失敗" if verdict is None else ("放行" if verdict.by_model else "沒判（放行）")
                print(f"db#{pk}：{why}｜{getattr(verdict, 'reason', '')}，不搬")
                continue
            head = f"db#{pk}：隔離｜{verdict.label}｜{verdict.reason}（{'清單' if given else '模型'}）"
            ok, note = await worker.move_to_quarantine(pk, verdict, posts, apply=apply)
            print(f"{head}；{note}")
            if ok and apply:
                moved_routes.update(resolver.resolve_telegram_routes(record.telegram_chat_id))

        # 搬完貼放回面板（bot 之後置底時會照 runtime 檔刪掉這則再發）
        panel = TelegramQuarantineCommands(client)
        panel.worker = worker
        for route_id in sorted(moved_routes):
            thread = await quarantine.current_thread(route_id)
            if thread is not None:
                await panel.post_panel(route_id, thread)
                print(f"已在 thread {thread.id} 貼放回面板")
    finally:
        await repo.close()
        await client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="判斷已在主頻道的 Telegram 轉發，垃圾移進隔離 thread")
    parser.add_argument("pks", nargs="*", type=int, help="Telegram 訊息的 db# 編號")
    parser.add_argument("--file", help="清單檔，一行「pk 標籤 理由」（只寫 pk 的用模型判）")
    parser.add_argument("--apply", action="store_true", help="實際搬（沒加只預覽）")
    args = parser.parse_args()
    targets = _read_targets(args)
    if not targets:
        parser.error("要給 pk 或 --file")
    asyncio.run(run(targets, args.apply))


if __name__ == "__main__":
    main()
