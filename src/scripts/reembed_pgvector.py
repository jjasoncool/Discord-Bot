"""Re-embed pgvector 既有資料（在 discord-bot container 內執行）。

用途：embed model 切換後（例如 bge-m3 → qwen3-embedding:0.6b），
      只需要重建 `embedding` 欄位，不動 `text` / `metadata_` / `node_id`。

執行方式（必須在 container 內，因為 pgvector 只在 docker network 可達）：
    docker exec discord-bot python /app/scripts/reembed_pgvector.py \
        --table data_discord_member_profiles_index
    docker exec discord-bot python /app/scripts/reembed_pgvector.py \
        --table data_discord_messages_index

前置步驟（必做）：
    1. 改 src/sys_settings/llm_runtime_config.json 的 embed_model
       （runtime hot reload，不用重啟 bot）
    2. 用 SQL 把舊向量清成 NULL，讓 script 能辨識未處理的 row：
         docker exec pgvector psql -U llm_vector -d discord_data -c \
           "UPDATE data_discord_messages_index SET embedding = NULL;"
         docker exec pgvector psql -U llm_vector -d discord_data -c \
           "UPDATE data_discord_member_profiles_index SET embedding = NULL;"

參數：
    --batch-size N   每批送 Ollama 的筆數（預設 16）
    --model NAME     embed model（預設從 llm_runtime_config.json 讀）
    --dry-run        只 embed 不寫 DB

DB 連線與 Ollama URL 皆從專案 `LLMServiceSettings` 取得（同 bot 環境變數），
不寫死任何連線字串。

Script 只處理 `embedding IS NULL` 的 row，所以可中斷續跑。

容錯邏輯：
- batch embed 失敗 → fallback 改逐筆 embed，batch 內只把 poison 那一筆標為失敗
- 單筆 embed 也失敗 → 該 row 保持 embedding = NULL，加入 poison 清單繼續跑
- 結束時列出所有 poison row id 與文字預覽，方便之後 Ollama 修好再單獨處理
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

# container 裡 /app 沒在 sys.path，手動加入以便 import sys_settings / llm 等模組
sys.path.insert(0, "/app")

import psycopg2
import requests

from llm.safe_llm_embedding import embed_with_perturbation_retry
from sys_settings.llm_settings import LLMServiceSettings, load_llm_runtime_config

logger = logging.getLogger("reembed")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


def embed_batch(
    session: requests.Session,
    base_url: str,
    model: str,
    texts: list[str],
    timeout: float,
    keep_alive: str = "30m",
) -> list[list[float]]:
    """用共用 Session 發 embed 請求，透過 Connection: keep-alive 避免每次新開 TCP socket
    （Windows 上 Ollama 主 process 連內部 runner subprocess 走 localhost HTTP，
     過多短連線會塞滿 Windows ephemeral port 池，造成莫名 runner 崩潰 / 400）。

    keep_alive：強制 model 常駐 VRAM，避免 Ollama 在其他 model 請求進來時把 embed model
    swap 出去（swap 過程在 Windows 有 runner lifecycle bug，造成大量 wsarecv / connection refused）。
    """
    url = f"{base_url.rstrip('/')}/api/embed"
    resp = session.post(
        url,
        json={"model": model, "input": texts, "keep_alive": keep_alive},
        timeout=timeout,
    )
    if not resp.ok:
        # 把 Ollama 實際回傳的 error body 帶出來，方便診斷真因
        # （原本 resp.raise_for_status() 只給 HTTP status，沒給 body）
        body = resp.text[:500] if resp.text else "<empty body>"
        raise RuntimeError(f"HTTP {resp.status_code} body={body!r}")
    data = resp.json()
    embeddings = data.get("embeddings")
    if not embeddings or len(embeddings) != len(texts):
        raise RuntimeError(
            f"Ollama 回傳 embedding 數量不符: 期望 {len(texts)}, 實得 "
            f"{len(embeddings) if embeddings else 0}"
        )
    return embeddings


def vector_literal(embedding: list[float]) -> str:
    """pgvector 可接受的字串格式：'[0.1,0.2,...]'，配 ::vector cast。"""
    return "[" + ",".join(f"{x:.8f}" for x in embedding) + "]"


ALLOWED_TABLES = {
    "data_discord_messages_index",
    "data_discord_member_profiles_index",
    "data_discord_knowledge_base_index",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Re-embed pgvector 既有資料")
    parser.add_argument(
        "--table",
        required=True,
        choices=sorted(ALLOWED_TABLES),
        help="pgvector 資料表名稱",
    )
    parser.add_argument("--batch-size", type=int, default=16, help="每批送 Ollama 的筆數")
    parser.add_argument("--model", default=None, help="embed model 名稱（預設從 runtime config 讀）")
    parser.add_argument("--dry-run", action="store_true", help="只 embed 不寫 DB")
    args = parser.parse_args()

    # 統一使用 bot 的設定載入流程，所有連線參數從 env / runtime config 來
    settings = LLMServiceSettings()
    runtime_config = load_llm_runtime_config(settings.llm_runtime_model_path)

    model = args.model or runtime_config.embed_model
    if not model:
        logger.error("embed_model 未設定（runtime config 或 --model）")
        return 2

    table = args.table

    logger.info(
        "table=%s model=%s ollama=%s batch=%d dry_run=%s",
        table, model, settings.llm_base_url, args.batch_size, args.dry_run,
    )
    logger.info(
        "pgvector=%s@%s:%s/%s",
        settings.pgvector_user, settings.pgvector_host,
        settings.pgvector_port, settings.pgvector_db,
    )

    conn = psycopg2.connect(
        host=settings.pgvector_host,
        port=settings.pgvector_port,
        dbname=settings.pgvector_db,
        user=settings.pgvector_user,
        password=settings.pgvector_password,
    )
    conn.autocommit = False

    # 全程共用一個 Session，讓所有 embed 請求走同一條 HTTP keep-alive 連線
    session = requests.Session()

    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {table} WHERE embedding IS NULL")
            pending = cur.fetchone()[0]
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            total = cur.fetchone()[0]
        logger.info("總 %d 筆，待處理（embedding IS NULL） %d 筆", total, pending)

        if pending == 0:
            logger.info("沒有待處理 row，結束")
            return 0

        processed = 0
        empty_skipped = 0
        poison_rows: list[tuple[int, str]] = []
        poison_ids: set[int] = set()
        t_start = time.time()

        while True:
            with conn.cursor() as cur:
                if poison_ids:
                    cur.execute(
                        f"SELECT id, text FROM {table} "
                        f"WHERE embedding IS NULL AND id <> ALL(%s) "
                        f"ORDER BY id LIMIT %s",
                        (list(poison_ids), args.batch_size),
                    )
                else:
                    cur.execute(
                        f"SELECT id, text FROM {table} WHERE embedding IS NULL "
                        f"ORDER BY id LIMIT %s",
                        (args.batch_size,),
                    )
                rows = cur.fetchall()
            if not rows:
                break

            ids: list[int] = []
            texts: list[str] = []
            empty_ids: list[int] = []
            for rid, text in rows:
                if text and text.strip():
                    ids.append(rid)
                    texts.append(text)
                else:
                    empty_ids.append(rid)

            # text 為空的 row 無法 embed，直接刪掉（實務上不該出現，保險處理）
            if empty_ids and not args.dry_run:
                with conn.cursor() as cur:
                    cur.execute(
                        f"DELETE FROM {table} WHERE id = ANY(%s)",
                        (empty_ids,),
                    )
                conn.commit()
                empty_skipped += len(empty_ids)
                logger.warning("刪除 %d 筆 text 為空的 row: %s",
                               len(empty_ids), empty_ids[:5])

            if not ids:
                continue

            # 先試 batch；batch 失敗 fallback 逐筆，單筆還失敗就標為 poison 跳過
            embeds: list[list[float] | None]
            try:
                embeds = list(embed_batch(
                    session, settings.llm_base_url, model, texts, settings.llm_timeout,
                ))
            except Exception as exc:
                logger.warning(
                    "batch embed 失敗（size=%d, 首 id=%s）: %s — 改成逐筆重試",
                    len(ids), ids[0], exc,
                )
                # 單筆 + 空格 perturbation retry（跟 bot 端共用 helper，邏輯一致）
                def _embed_single(t: str) -> list[float]:
                    return embed_batch(
                        session, settings.llm_base_url, model, [t],
                        settings.llm_timeout,
                    )[0]

                embeds = []
                for rid, text in zip(ids, texts):
                    try:
                        vec = embed_with_perturbation_retry(
                            _embed_single, text,
                            context_label=f"reembed.id={rid}",
                            log=logger,
                        )
                        embeds.append(vec)
                    except Exception as single_exc:
                        logger.error(
                            "單筆 embed 失敗（含空格 perturbation）id=%d text=%r err=%s",
                            rid, text[:40], single_exc,
                        )
                        poison_rows.append((rid, text[:60]))
                        poison_ids.add(rid)
                        embeds.append(None)

            if not args.dry_run:
                with conn.cursor() as cur:
                    for rid, emb in zip(ids, embeds):
                        if emb is None:
                            continue
                        cur.execute(
                            f"UPDATE {table} SET embedding = %s::vector WHERE id = %s",
                            (vector_literal(emb), rid),
                        )
                conn.commit()

            success_count = sum(1 for e in embeds if e is not None)
            processed += success_count
            elapsed = time.time() - t_start
            rate = processed / elapsed if elapsed > 0 else 0
            remaining = pending - processed - empty_skipped - len(poison_rows)
            eta = remaining / rate if rate > 0 else 0
            logger.info(
                "進度 %d/%d (%.1f 筆/秒, ETA %.0fs, 空=%d, poison=%d)",
                processed, pending, rate, eta, empty_skipped, len(poison_rows),
            )

        logger.info("完成：處理 %d、空刪 %d、poison=%d",
                    processed, empty_skipped, len(poison_rows))
        if poison_rows:
            logger.warning("以下 %d 筆 row 無法 embed（單筆測試亦失敗，embedding 保持 NULL）:",
                           len(poison_rows))
            for rid, preview in poison_rows:
                logger.warning("  id=%d text=%r", rid, preview)
        return 0
    finally:
        session.close()
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
