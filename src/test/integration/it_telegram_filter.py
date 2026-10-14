"""手動抽查：用真的模型判斷 Telegram 歷史樣本，看過濾準不準（只讀資料庫、只印結果，不送任何東西）。

上線門檻：期望放行（P）的被隔離要是 0 則；期望隔離（Q）漏掉的是「漏放」，只影響效果。
E＝兩邊都算對、不計分：罵人但圖有遊戲資訊（照「任一邊有資訊就放行」該放行）、互相矛盾的一對。
10-06 使用者看過第一輪結果：「我覺得他過濾得不錯，不用太改」——模型隔離的 6 則（11557、12285、13381、13387、
13461、13481）與放行的 1474 都照模型的判斷改期望值。
**樣本原文不能放進 prompt 當例句**，否則這裡的分數會虛高、看不出新訊息準不準。
樣本與期望值見 AI_HANDOFF_AND_TODO.md 的 telegram-llm-filter-quarantine 區塊。

會佔用主模型，不要在 04:00～07:30 維護時段跑。這支腳本是另一個行程，靠 `lemonade_gate` 的跨行程鎖檔跟 bot
的插話、/askai 一起排隊；判斷本身也是排到為止、不設時限（10-08 起），這裡只量準不準，速度要在 bot 裡量。
執行（容器內）：
    docker exec -w /app discord-bot python -m test.integration.it_telegram_filter            # 全部樣本
    docker exec -w /app discord-bot python -m test.integration.it_telegram_filter 13649 14090 # 指定幾則
    docker exec -w /app discord-bot python -m test.integration.it_telegram_filter --days 7   # 最近 7 天全部
加 --save 會把送給模型的圖存到 /tmp/telegram_filter_check/ 方便對照。
`--days N`：最近 N 天的每個發送單位（相簿算一個）都判一次，列出會被隔離的；跟轉發端一樣，有圖標示但圖沒
下載到的不判（轉發端也不會判，照常送）。
"""
import asyncio
import sys
import time
from pathlib import Path

from services.relay import telegram_filter as tf
from sys_settings.time_settings import APP_TZ
from services.relay.telegram_relay_service import TelegramMessageRepository, build_telegram_pg_dsn_from_env

APP_ROOT = Path("/app")
SAVE_DIR = Path("/tmp/telegram_filter_check")

# (telegram_messages.id, 期望 Q／P／E, 類別)
SAMPLES = [
    (13371, "Q", "灌水"), (13404, "Q", "灌水+無關圖"), (13430, "Q", "灌水"), (13431, "Q", "灌水"),
    (13447, "Q", "灌水"), (13451, "Q", "灌水"), (13474, "Q", "灌水"), (13643, "Q", "灌水+別款遊戲影片"),
    (13646, "Q", "灌水"), (13649, "P", "「水」+角色設計稿"), (13478, "P", "「💦」+鳴潮劇情CG"),
    (13650, "Q", "閒聊"), (13651, "Q", "閒聊"), (13661, "Q", "閒聊"), (13681, "E", "閒聊(與13682成對)"),
    (13766, "Q", "閒聊"), (13510, "Q", "閒聊"),
    (7378, "E", "罵人+聯動資訊截圖"), (7379, "Q", "罵人"), (9028, "E", "罵人+場景美術(相簿)"),
    (9179, "E", "罵人+角色設計稿"), (9842, "Q", "罵人(相簿7張)"), (1474, "P", "罵人+圖有鳴潮介面截圖"), (1475, "Q", "罵人"),
    (6941, "Q", "罵人"), (6953, "Q", "罵人"), (13076, "E", "罵人+譯名討論(相簿)"), (13362, "Q", "罵人"),
    (13433, "Q", "罵人(相簿)"), (13449, "E", "罵人+官方公告截圖(相簿)"), (13487, "Q", "罵人"),
    (13638, "Q", "罵人"), (13678, "Q", "罵人"),
    (14090, "Q", "無關圖"), (14091, "Q", "無關圖"), (14092, "Q", "無關圖"), (14061, "Q", "無關圖"),
    (14058, "Q", "無關圖"), (13687, "Q", "無關圖"), (13448, "Q", "無關圖"), (13483, "Q", "無關圖"),
    (13459, "Q", "無關圖"), (13388, "Q", "無關圖"), (13192, "Q", "無關圖"), (13191, "Q", "無關圖"),
    (13187, "Q", "無關圖"), (13677, "Q", "無關圖"), (13671, "Q", "無關圖"), (14065, "Q", "無關圖"),
    (1, "P", "短情報"), (13025, "P", "短情報"), (9382, "P", "短情報"), (11368, "P", "短情報"),
    (12750, "P", "短情報"), (13685, "P", "短情報"), (13391, "P", "短情報"), (13392, "P", "短情報"),
    (12492, "P", "短情報+鳴潮影片"), (11584, "P", "短情報+圖"), (6937, "P", "短情報"), (13299, "P", "短情報"),
    (11205, "P", "短情報"), (11557, "Q", "看不懂的短句"), (4253, "P", "短情報"), (12190, "P", "短情報"),
    (9153, "P", "短情報"), (13189, "P", "短情報"), (13181, "P", "情報"), (13182, "P", "情報"),
    (12458, "P", "情報+圖"), (13475, "P", "情報"), (9531, "P", "髒話但有資訊"), (12285, "Q", "罵人帶一點遊戲內容"),
    (13393, "P", "情報"), (10025, "P", "頻道公告"), (13381, "Q", "頻道管理說明"), (13387, "Q", "頻道切割聲明"),
    (13461, "Q", "猜真假(前文是無關圖)"), (13480, "P", "假劇情"), (13481, "Q", "假劇情的免責聲明"),
    (13682, "E", "修正13681"), (13653, "P", "表情符號代號"), (12071, "P", "表情符號代號"),
    (13567, "P", "純圖:直播截圖"), (14051, "P", "純圖:聯名"), (14029, "P", "純圖:拿不準"),
    # 10-07 使用者看 7 天清單後補：模型認不出的角色手辦（跟同一分鐘的鳴潮手辦是同一組展場照）
    (14070, "P", "角色手辦展場照"), (14053, "P", "角色造型冰棒"),
    (14062, "Q", "「一缸石榴」"), (14064, "Q", "「二缸石榴」"),
    # 7 天清單裡明顯無關的，留著確認放寬手辦規則後仍會隔離
    (14076, "Q", "無關圖"), (14095, "Q", "無關圖"),
]


async def load_unit(repo: TelegramMessageRepository, pk: int):
    """一則訊息 → 它所在的發送單位（相簿整本，照 Telegram 訊息順序合併文字與媒體）。"""
    record = await repo.get_message_by_pk(pk)
    if record is None:
        return None, []
    members = [record]
    if record.grouped_id is not None:
        states = await repo.get_group_member_states(record.grouped_id, record.telegram_chat_id)
        members = [m for m in [await repo.get_message_by_pk(p) for p, _ in states] if m is not None]
    text = "\n".join(m.text.strip() for m in members if (m.text or "").strip())
    media = [
        tf.MediaFile(APP_ROOT / item.file_rel_path, tf.media_kind(item.media_type, item.mime_type, item.file_rel_path))
        for m in members for item in m.media_items
    ]
    return text, media


async def unit_complete(repo: TelegramMessageRepository, pk: int) -> bool:
    """這個發送單位的圖都下載到了沒（有圖標示卻沒有媒體列的，轉發端不判）。"""
    record = await repo.get_message_by_pk(pk)
    members = [record]
    if record.grouped_id is not None:
        members = [await repo.get_message_by_pk(p) for p, _ in
                   await repo.get_group_member_states(record.grouped_id, record.telegram_chat_id)]
    return all(not m.has_media or m.media_items for m in members if m is not None)


async def recent(days: int) -> None:
    """最近 N 天的每個發送單位都判一次，列出會被隔離的。"""
    repo = TelegramMessageRepository(build_telegram_pg_dsn_from_env())
    await repo.connect()
    quarantined, fallback, skipped, total, total_seconds = [], [], [], 0, 0.0
    try:
        rows = await repo.pool.fetch(
            """
            SELECT id, telegram_chat_id, grouped_id, message_date, chat_title
            FROM telegram_messages
            WHERE message_date >= NOW() - make_interval(days => $1)
            ORDER BY message_date, telegram_message_id
            """,
            days,
        )
        seen: set = set()
        for row in rows:
            key = (row["telegram_chat_id"], row["grouped_id"]) if row["grouped_id"] is not None else ("pk", row["id"])
            if key in seen:
                continue
            seen.add(key)
            pk = row["id"]
            when = row["message_date"].astimezone(APP_TZ).strftime("%m-%d %H:%M")
            source = (row["chat_title"] or "")[:8]
            if not await unit_complete(repo, pk):
                skipped.append(pk)
                print(f"  {when} {source:8} {pk:>6}  圖沒下載到，略過")
                continue
            text, media = await load_unit(repo, pk)
            if not text.strip() and not media:
                continue          # 系統通知之類的空訊息，轉發端本來就略過
            total += 1
            started = time.monotonic()
            v = await tf.judge(text, media, trace_id=f"it-tgfilter-{pk}")
            total_seconds += time.monotonic() - started
            shown = " ".join(text.split())[:40] or f"（{len(media)} 個媒體）"
            mark = "隔離" if v.quarantine else ("放行" if v.by_model else "放行*")
            print(f"  {when} {source:8} {pk:>6} {mark} {v.label or '':4}｜{v.reason}｜圖 {v.images_seen}｜"
                  f"{v.seconds:.1f}s｜{shown}")
            if v.quarantine:
                quarantined.append((pk, when, v.label, v.reason, shown))
            if not v.by_model:
                fallback.append((pk, v.reason))
    finally:
        await repo.close()
    print()
    print(f"最近 {days} 天：判了 {total} 個發送單位，平均 {total_seconds / max(total, 1):.1f} 秒；"
          f"圖沒下載到略過 {len(skipped)} 個")
    print(f"會被隔離 {len(quarantined)} 個：")
    for pk, when, label, reason, shown in quarantined:
        print(f"  {when}  db#{pk}  {label}｜{reason}｜{shown}")
    print(f"模型沒判、直接放行（放行*）{len(fallback)} 個：{fallback}")


async def main(ids: list[int], save: bool) -> None:
    samples = [s for s in SAMPLES if not ids or s[0] in ids] + [(i, "?", "指定") for i in ids
                                                                 if i not in {s[0] for s in SAMPLES}]
    repo = TelegramMessageRepository(build_telegram_pg_dsn_from_env())
    await repo.connect()
    wrong_quarantine, missed, fallback, total_seconds = [], [], [], 0.0
    try:
        for pk, expected, category in samples:
            text, media = await load_unit(repo, pk)
            if text is None:
                print(f"{pk:>6}  找不到")
                continue
            if save:
                SAVE_DIR.mkdir(parents=True, exist_ok=True)
                for n, img in enumerate(await tf.collect_images(media)):
                    (SAVE_DIR / f"{pk}_{n}.jpg").write_bytes(img)
            started = time.monotonic()
            v = await tf.judge(text, media, trace_id=f"it-tgfilter-{pk}")
            total_seconds += time.monotonic() - started
            got = "Q" if v.quarantine else "P"
            mark = "  " if expected in ("E", "?") or got == expected else "✗ "
            if expected == "P" and got == "Q":
                wrong_quarantine.append(pk)
            if expected == "Q" and got == "P":
                missed.append(pk)
            if not v.by_model:
                fallback.append(pk)
            shown = " ".join(text.split())[:30]
            print(f"{mark}{pk:>6} 期望 {expected} 判 {got} {v.label or '':4}｜{v.reason}｜圖 {v.images_seen}｜"
                  f"{v.seconds:.1f}s｜{category}｜{shown}")
            if not v.by_model or mark.strip():
                print(f"          模型回答：{' / '.join(v.answer.split(chr(10)))[:200]}")
    finally:
        await repo.close()
    n = len(samples)
    print()
    print(f"共 {n} 則，平均 {total_seconds / max(n, 1):.1f} 秒")
    print(f"期望放行卻被隔離（上線門檻要 0）：{len(wrong_quarantine)} {wrong_quarantine}")
    print(f"期望隔離卻放行（漏放）：{len(missed)} {missed}")
    print(f"模型不能用而放行：{len(fallback)} {fallback}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--days" in args:
        asyncio.run(recent(int(args[args.index("--days") + 1])))
    else:
        asyncio.run(main([int(a) for a in args if a.isdigit()], "--save" in args))
