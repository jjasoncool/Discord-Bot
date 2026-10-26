"""重算聊天向量：聊天向量表每一列的向量改成「只從內文算」——送給 embedding 模型的文字只有訊息內文，不再把 metadata
（message_id、作者、頻道、時間）一起送進去；算好的向量寫進指定欄位（預設影子欄 embedding_v2）。

架構定位：功能層（`llm/storage`，和 `store_chat`、`chat_index_backfill` 同層），在 discord-bot 容器另開行程跑：
`python -m llm.storage.chat_reembed`。上層：使用者手動執行。下層：`LLMServiceSettings.pgvector_connect`、
`llm.client.embedding_client.make_safe_llm_embedding`、`llm.client.lemonade_gate.gpu_exclusive_sync`、
`llm.client.http_client.is_unreachable`。

介面：
- `run(column=, batch=, limit=, pause=, dry_run=, redo_copied=)`：做一輪，回 `Report`（做了幾列、沿用舊向量幾列、為什麼停）。
- `self_check()`：拿最新一則，確認這裡送去算的字串和寫入端（`store_chat._chat_node`）會嵌的字串一字不差。
- `main(argv)`：命令列（`--dry-run` 只算還剩幾列、`--self-check`、`--limit`、`--batch`、`--pause`、`--column`、`--redo-copied`）。

規則：
- 送去算的字串就是 `text` 欄原樣：不 strip、不正規化、不加任何前綴，才和寫入端同一個向量空間。
- 每批拿跨行程 GPU 閘門（`gpu_exclusive_sync(max_wait_seconds=…)`），等不到就睡一陣再試、永遠不硬闖（閘門預設不給
  上限時等滿一段時間會照常打模型，那會和 bot 同時用顯示卡）；放鎖後讓一拍（`pause`），bot 的 /askai 與插話排在前面。
  04:00～07:30 維護時段不跑，等到結束再繼續。
- keyset 分頁（照 id 由新到舊）、每批 commit；中斷了再跑會接著做（還是 NULL 的列）。
- 後端連不上（`is_unreachable`）：整批連不上先用一則探一次，探也連不上才停（整批逾時可能只是這批太長）；
  其他錯誤整批改逐筆，仍失敗的列沿用舊向量（`embedding` 欄）並記 log，不留 NULL。算回來的向量維度不對或有
  nan／inf 也算失敗。整批逐筆都失敗、或最近 `COPY_WINDOW_BATCHES` 批沿用舊向量超過 `COPY_LIMIT_RATIO` 就停：那是後端
  整個不對，不是個別壞列。
- 影子欄不存在時自己加（先查 information_schema，欄位在就不下 ALTER——ALTER 即使 IF NOT EXISTS 也要排整張表的鎖；
  建欄的交易 `SET LOCAL lock_timeout = '3s'`，拿不到鎖就報錯、下次再跑）。讀取用完就 rollback，等鎖、睡覺時不持有交易。
- `--column embedding` 一定要配 `--redo-copied`（切換後補那幾列）：不然述詞恆假，什麼都不會做。

例外與決策：寫影子欄而不是原地覆寫，是為了切換前後不混格式、能回滾、能先用評估集比對；兩者的表膨脹一樣。
切換（RENAME 欄位）與建索引由使用者在 psql 做，不在這裡：那是一次性的 DDL，步驟記在交接檔「重算向量計畫」。
"""
from __future__ import annotations

import argparse
import logging
import math
import re
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, time as dtime
from typing import Any, Callable, Optional

from llm.client.http_client import is_unreachable
from llm.client.lemonade_gate import GpuBusy, gpu_exclusive_sync
from sys_settings.pgvector_settings import HYBRID_RETRIEVAL_SETTINGS
from sys_settings.time_settings import APP_TZ

try:
    from psycopg2.extras import execute_values
except Exception:  # pragma: no cover - 單元測試環境可能沒裝驅動
    execute_values = None

logger = logging.getLogger(__name__)

_COLUMN = re.compile(r"^[a-z_][a-z0-9_]*$")
#: 維護時段（人格萃取、persona agent 在用顯示卡）：這段不跑
MAINTENANCE_START, MAINTENANCE_END = dtime(4, 0), dtime(7, 30)
#: 等閘門的上限；等不到睡一陣再試（永遠不硬闖）
GATE_WAIT_SECONDS = 1800.0
BUSY_SLEEP_SECONDS = 30.0
#: 最近幾批裡沿用舊向量的列超過這個比例（且至少 COPY_LIMIT_MIN 列）就停：那不是個別壞列，是後端整個不對了。
#: 看最近幾批而不是全程累計：前面做得好會把尾段的壞掉稀釋掉
COPY_LIMIT_RATIO, COPY_LIMIT_MIN, COPY_WINDOW_BATCHES = 0.05, 50, 20
#: 比 bigint 最大值小一點的起點：keyset 從最新的一列開始
_ID_START = 2**62
#: 向量該有的維度（和表的 vector(N) 一致）；算回來不是這個維度就當失敗
EMBED_DIM = HYBRID_RETRIEVAL_SETTINGS.pgvector_embed_dim


@dataclass
class Report:
    scanned: int = 0
    embedded: int = 0
    copied: int = 0
    batches: int = 0
    remaining_at_start: int = 0
    failed_ids: list[int] = field(default_factory=list)
    stopped: str = ""


def _validate_column(column: str) -> str:
    if not _COLUMN.match(column or ""):
        raise ValueError(f"欄位名稱只能是小寫英數與底線：{column!r}")
    return column


def _table() -> str:
    return HYBRID_RETRIEVAL_SETTINGS.physical_table(HYBRID_RETRIEVAL_SETTINGS.get_chat_table_name())


def _vector_literal(vec) -> str:
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"


def _in_maintenance(now: datetime) -> bool:
    local = now.astimezone(APP_TZ).time()
    return MAINTENANCE_START <= local < MAINTENANCE_END


def _connect():
    from sys_settings.llm_settings import LLMServiceSettings

    return LLMServiceSettings().pgvector_connect()


def _embedder(batch: int):
    from llm.client.embedding_client import make_safe_llm_embedding
    from sys_settings.llm_settings import LLMServiceSettings, load_llm_runtime_config

    settings = LLMServiceSettings()
    runtime = load_llm_runtime_config(settings.llm_runtime_model_path)
    model = make_safe_llm_embedding(settings=settings, runtime_config=runtime, holding_gpu_gate=True)
    model.embed_batch_size = batch   # 不設的話 llama-index 一次只送 10 則，一批 64 變成 7 次 HTTP
    return model


def _predicate(column: str, redo_copied: bool) -> str:
    # 切換後補那幾列「沿用舊向量」的：它們的值和 embedding_v1 一模一樣
    return f"{column} = embedding_v1" if redo_copied else f"{column} IS NULL AND embedding IS NOT NULL"


def ensure_column(conn, column: str) -> None:
    """影子欄不存在才加（不帶 DEFAULT，拿到鎖瞬間完成）；建欄的交易 3 秒拿不到鎖就讓例外出去，下次再跑。

    先查 information_schema：`ADD COLUMN IF NOT EXISTS` 即使欄位已存在也要先拿整張表的排他鎖，續跑時沒必要去排那個隊。
    `SET LOCAL` 只活在這個交易，之後每批的 UPDATE 不受 3 秒限制。
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
            (_table(), column),
        )
        exists = cur.fetchone() is not None
        if exists:
            conn.rollback()
            return
        cur.execute("SET LOCAL lock_timeout = '3s'")
        cur.execute(f"ALTER TABLE {_table()} ADD COLUMN IF NOT EXISTS {column} vector({HYBRID_RETRIEVAL_SETTINGS.pgvector_embed_dim})")
    conn.commit()


def count_remaining(conn, column: str, redo_copied: bool = False) -> int:
    with conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {_table()} WHERE {_predicate(column, redo_copied)}")
        count = int(cur.fetchone()[0])
    conn.rollback()
    return count


def _fetch_batch(conn, column: str, before_id: int, size: int, redo_copied: bool) -> list[tuple[int, str]]:
    """讀完就 rollback 結束讀取的交易：接下來等閘門、睡覺可能很久，不能一直持著表的共享鎖（會擋住切換的 ALTER）。"""
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT id, text FROM {_table()} WHERE id < %s AND {_predicate(column, redo_copied)} ORDER BY id DESC LIMIT %s",
            (before_id, size),
        )
        rows = [(int(row[0]), row[1] or "") for row in cur.fetchall()]
    conn.rollback()
    return rows


def _valid_vector(vec) -> bool:
    try:
        return len(vec) == EMBED_DIM and all(math.isfinite(float(x)) for x in vec)
    except (TypeError, ValueError):
        return False


def _probe_backend(model, text: str, gate) -> None:
    """整批連不上時用一則探後端：連不上就往外丟（呼叫端停），那一則本身出錯（後端活著）只記 log，交給逐筆處理。"""
    try:
        with gate(max_wait_seconds=GATE_WAIT_SECONDS):
            model.get_text_embedding(text)
    except GpuBusy:
        raise
    except Exception as exc:  # 邊界：探測那一則讓後端出錯不代表後端掛了，逐筆迴圈會照既有規則處理它
        if is_unreachable(exc):
            raise
        logger.warning("探測那一則算不出來（%s），後端活著，改逐筆", exc)


def _embed_rows(model, rows: list[tuple[int, str]], gate) -> tuple[list[tuple[int, Any]], list[int]]:
    """整批算；整批失敗就逐筆，仍失敗的回在第二個 list。`GpuBusy` 與後端連不上都往外丟，由呼叫端決定睡或停。

    整批「連不上／逾時」先拿第一則探一次：64 則長文塞一個請求可能只是這批太長而逾時，探一則也連不上才是後端真的掛了。
    算回來的向量維度不對或有 nan／inf 的列當失敗；後端少回幾個向量就當整批失敗改逐筆（zip 會悄悄截斷）。
    """
    try:
        with gate(max_wait_seconds=GATE_WAIT_SECONDS):
            vectors = model.get_text_embedding_batch([text for _, text in rows])
        if len(vectors) == len(rows):
            done = [(rid, vec) for (rid, _), vec in zip(rows, vectors) if _valid_vector(vec)]
            failed = [rid for (rid, _), vec in zip(rows, vectors) if not _valid_vector(vec)]
            for rid in failed:
                logger.warning("id=%s 算回來的向量不合格（維度或 nan／inf），沿用舊向量", rid)
            return done, failed
        logger.warning("這批送 %d 則只回 %d 個向量，改逐筆", len(rows), len(vectors))
    except GpuBusy:
        raise
    except Exception as exc:  # 邊界：一批裡某一則讓後端出錯、或整批太長逾時，改逐筆；探一則也連不上才往外丟
        if is_unreachable(exc):
            _probe_backend(model, rows[0][1], gate)   # 連不上會再丟 is_unreachable 的例外，由呼叫端停
            logger.warning("這批 %d 則整批連不上或逾時（%s），但後端活著，改逐筆", len(rows), exc)
        else:
            logger.warning("這批 %d 則整批算失敗（%s），改逐筆", len(rows), exc)
    done: list[tuple[int, Any]] = []
    failed: list[int] = []
    for rid, text in rows:
        try:
            with gate(max_wait_seconds=GATE_WAIT_SECONDS):
                vec = model.get_text_embedding(text)
        except GpuBusy:
            raise
        except Exception as exc:  # 邊界：這一則算不出來就沿用舊向量，不讓一列卡住整個工作
            if is_unreachable(exc):
                raise
            logger.warning("id=%s 算不出來（%s），沿用舊向量", rid, exc)
            failed.append(rid)
            continue
        if _valid_vector(vec):
            done.append((rid, vec))
        else:
            logger.warning("id=%s 算回來的向量不合格（維度或 nan／inf），沿用舊向量", rid)
            failed.append(rid)
    if not done and failed:
        # 整批逐筆都失敗不會是「某一則讓後端出錯」，是後端整個不對；不寫、往外丟讓工作停下來
        raise RuntimeError(f"這批 {len(failed)} 則逐筆都算不出來，後端可能有問題")
    return done, failed


def _write(conn, column: str, done: list[tuple[int, Any]], failed: list[int]) -> None:
    table = _table()
    with conn.cursor() as cur:
        if done:
            execute_values(
                cur,
                f"UPDATE {table} AS t SET {column} = v.e FROM (VALUES %s) AS v(id, e) WHERE t.id = v.id",
                [(rid, _vector_literal(vec)) for rid, vec in done],
                template="(%s, %s::vector)",
            )
        if failed and column != "embedding":
            cur.execute(f"UPDATE {table} SET {column} = embedding WHERE id = ANY(%s)", (failed,))
    conn.commit()


def run(
    *,
    column: str = "embedding_v2",
    batch: int = 64,
    limit: Optional[int] = None,
    pause: float = 0.5,
    dry_run: bool = False,
    redo_copied: bool = False,
    gate: Callable[..., Any] = gpu_exclusive_sync,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], datetime] = lambda: datetime.now(APP_TZ),
    connect: Callable[[], Any] = _connect,
    embedder: Optional[Callable[[int], Any]] = None,
) -> Report:
    column = _validate_column(column)
    if column == "embedding" and not redo_copied:
        raise ValueError("--column embedding 要配 --redo-copied（切換後補沿用舊向量的那幾列）；不然述詞恆假、什麼都不會做")
    batch = max(1, int(batch))
    report = Report()
    recent: deque[tuple[int, int]] = deque(maxlen=COPY_WINDOW_BATCHES)   # 最近幾批的 (做了幾列, 沿用舊向量幾列)
    conn = connect()
    try:
        if not redo_copied and column != "embedding" and not dry_run:
            ensure_column(conn, column)
        try:
            report.remaining_at_start = count_remaining(conn, column, redo_copied)
        except Exception as exc:  # 邊界：欄位還不存在（dry-run 沒建欄）這類情況，只是少一個數字
            logger.info("算不出還剩幾列（%s）", exc)
            conn.rollback()
        logger.info("重算向量：欄位 %s，還剩 %s 列%s", column, report.remaining_at_start, "（dry-run，不算也不寫）" if dry_run else "")
        if dry_run:
            return report
        model = (embedder or _embedder)(batch)
        before = _ID_START
        started = time.monotonic()
        while limit is None or report.scanned < limit:
            while _in_maintenance(now()):
                logger.info("維護時段（%s～%s）不跑，等一分鐘再看", MAINTENANCE_START, MAINTENANCE_END)
                sleep(60)
            size = batch if limit is None else min(batch, limit - report.scanned)
            rows = _fetch_batch(conn, column, before, size, redo_copied)
            if not rows:
                break
            try:
                done, failed = _embed_rows(model, rows, gate)
            except GpuBusy:
                logger.info("GPU 忙超過 %.0f 秒，睡 %.0f 秒再試同一批", GATE_WAIT_SECONDS, BUSY_SLEEP_SECONDS)
                sleep(BUSY_SLEEP_SECONDS)
                continue
            except Exception as exc:  # 邊界：後端連不上、或整批逐筆都失敗，就停，交給下次再跑
                report.stopped = f"後端有問題，先停：{exc}（若是這批太長逾時，可用更小的 --batch 重跑）"
                logger.error(report.stopped)
                break
            _write(conn, column, done, failed)
            before = rows[-1][0]
            report.scanned += len(rows)
            report.embedded += len(done)
            report.copied += len(failed)
            report.failed_ids.extend(failed)
            report.batches += 1
            recent.append((len(rows), len(failed)))
            win_scanned, win_copied = sum(n for n, _ in recent), sum(c for _, c in recent)
            if win_copied >= COPY_LIMIT_MIN and win_copied > COPY_LIMIT_RATIO * win_scanned:
                report.stopped = f"最近 {len(recent)} 批沿用舊向量的列太多（{win_copied}/{win_scanned}），先停、請看 log"
                logger.error(report.stopped)
                break
            if report.batches % 20 == 0:
                elapsed = max(1e-6, time.monotonic() - started)
                rate = report.scanned / elapsed
                left = max(0, report.remaining_at_start - report.scanned)
                logger.info("已做 %d 列（%.0f 列/秒），還剩約 %d 列、約 %.0f 分鐘", report.scanned, rate, left, left / max(rate, 1e-6) / 60)
            sleep(pause)   # 放鎖後讓一拍：bot 的 /askai、插話先拿閘門
    finally:
        conn.close()
    logger.info("重算結束：做了 %d 列（算出 %d、沿用舊向量 %d）%s", report.scanned, report.embedded, report.copied,
                f"；{report.stopped}" if report.stopped else "")
    if report.failed_ids:
        logger.warning("沿用舊向量的列 id：%s", report.failed_ids)
    return report


def self_check(gate: Callable[..., Any] = gpu_exclusive_sync) -> tuple[bool, float]:
    """最新一則：這裡送去算的字串和寫入端會嵌的字串是不是一字不差，兩個向量的餘弦距離是多少（應為 0）。"""
    from llama_index.core.schema import MetadataMode
    from llm.storage.store_chat import _chat_node

    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT text, metadata_->>'message_id', metadata_->>'author_id', metadata_->>'channel_id', metadata_->>'timestamp' "
                f"FROM {_table()} WHERE embedding IS NOT NULL ORDER BY id DESC LIMIT 1"
            )
            text, mid, author, channel, ts = cur.fetchone()
    finally:
        conn.close()
    node = _chat_node({"message_id": mid, "text": text, "author_id": author, "channel_id": channel, "timestamp": ts})
    writer_text = node.get_content(metadata_mode=MetadataMode.EMBED)
    same = writer_text == text
    model = _embedder(2)
    with gate(max_wait_seconds=GATE_WAIT_SECONDS):
        a, b = model.get_text_embedding_batch([text, writer_text])
    dot = sum(x * y for x, y in zip(a, b))
    norm = (sum(x * x for x in a) ** 0.5) * (sum(y * y for y in b) ** 0.5) or 1.0
    distance = 1.0 - dot / norm
    logger.info("自我檢查：寫入端會嵌的字串%s text 原樣；兩個向量的餘弦距離 %.6f", "就是" if same else "不等於", distance)
    return same, distance


def main(argv: Optional[list[str]] = None) -> Report | None:
    parser = argparse.ArgumentParser(description="重算聊天向量（只嵌內文），寫進影子欄")
    parser.add_argument("--column", default="embedding_v2", help="寫進哪個欄位（預設影子欄 embedding_v2）")
    parser.add_argument("--batch", type=int, default=64, help="一批幾則（一批佔 GPU 閘門約一秒）")
    parser.add_argument("--limit", type=int, default=None, help="最多做幾列（新的先做）")
    parser.add_argument("--pause", type=float, default=0.5, help="每批放鎖後讓一拍幾秒，bot 先用")
    parser.add_argument("--dry-run", action="store_true", help="只算還剩幾列，不算也不寫")
    parser.add_argument("--redo-copied", action="store_true", help="切換後補：只做值和 embedding_v1 一樣（沿用舊向量）的列")
    parser.add_argument("--self-check", action="store_true", help="確認送去算的字串和寫入端一致（用一次 GPU）")
    args = parser.parse_args(argv)
    if args.self_check:
        self_check()
        return None
    return run(column=args.column, batch=args.batch, limit=args.limit, pause=args.pause,
               dry_run=args.dry_run, redo_copied=args.redo_copied)


if __name__ == "__main__":
    from utils.logger_config import configure_logging

    # 從 docker exec 手動執行：只印到畫面（要留紀錄就把輸出導到檔案），不寫 bot 的輪替 log
    configure_logging(force=True, root_handlers=["console"])
    main()
