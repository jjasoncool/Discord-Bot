"""
Phase 0 Step 1 of 社群 ID 查詢：
驗證 SQLite JSON1 對 ptt_posts.comments_json 做「查某使用者的留言紀錄」的效能，
決定是否需要做 ptt_comments 正規化 migration。

判準:
  - p95 < 500ms → JSON1 方案可行，直接進 Phase 0 Step 2
  - p95 ≥ 500ms → 保留 Phase X（正規化 migration）作為備案

此 script 只做讀取，不建 index、不改 schema，重跑多次安全無副作用。

怎麼跑（bot 容器內才是實際查詢環境，其他跑法的 p95 不代表 prod）：
    docker exec discord-bot python /app/scripts/bench_ptt_comment_lookup.py

輸出看最後的「判斷」區塊。若所有 p95 都通過（<500ms）即可進 Phase 0 Step 2。
"""
import sqlite3
import time
import statistics
from pathlib import Path


DB_PATH = Path(__file__).resolve().parents[1] / "scraper" / "articles.db"
BENCH_TIMES = 10
LIMIT_IN_RANGE = 1000
LIMIT_FALLBACK = 100


def row(conn, sql, params=()):
    return conn.execute(sql, params).fetchall()


def explain(conn, sql, params):
    plan = row(conn, f"EXPLAIN QUERY PLAN {sql}", params)
    for p in plan:
        print("    ", p)


def bench(conn, sql, params, times=BENCH_TIMES):
    latencies = []
    result = []
    for _ in range(times):
        t0 = time.perf_counter()
        result = row(conn, sql, params)
        latencies.append((time.perf_counter() - t0) * 1000)
    latencies.sort()
    p50 = statistics.median(latencies)
    p95 = latencies[int(len(latencies) * 0.95) - 1] if len(latencies) >= 2 else latencies[-1]
    return {
        "hits": len(result),
        "p50_ms": p50,
        "p95_ms": p95,
        "max_ms": max(latencies),
        "min_ms": min(latencies),
    }


def fmt(stats):
    return (f"hits={stats['hits']:<6} "
            f"p50={stats['p50_ms']:>7.1f}ms  "
            f"p95={stats['p95_ms']:>7.1f}ms  "
            f"max={stats['max_ms']:>7.1f}ms")


def main():
    if not DB_PATH.exists():
        print(f"❌ DB not found: {DB_PATH}")
        return

    size_mb = DB_PATH.stat().st_size / 1024 / 1024
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")

    print("=" * 70)
    print(f"DB: {DB_PATH}")
    print(f"Size: {size_mb:.1f} MB")

    total = row(conn, "SELECT COUNT(*) FROM ptt_posts")[0][0]
    total_comments = row(
        conn,
        "SELECT SUM(json_array_length(comments_json)) FROM ptt_posts WHERE comments_json IS NOT NULL",
    )[0][0] or 0
    print(f"ptt_posts rows: {total}")
    print(f"total comments (json_array_length sum): {total_comments}")

    print("\n== Existing index on ptt_posts ==")
    for i in row(conn, "PRAGMA index_list('ptt_posts')"):
        print(" ", i)

    print("\n== Top 5 留言者（全表 json_each 聚合，僅做測試用）==")
    t0 = time.perf_counter()
    top = row(
        conn,
        """
        SELECT json_extract(c.value, '$.user') AS u, COUNT(*) AS n
        FROM ptt_posts p, json_each(p.comments_json) c
        WHERE json_extract(c.value, '$.user') IS NOT NULL
          AND json_extract(c.value, '$.user') != ''
        GROUP BY u ORDER BY n DESC LIMIT 5
        """,
    )
    agg_ms = (time.perf_counter() - t0) * 1000
    print(f"  聚合耗時: {agg_ms:.0f} ms")
    for u, n in top:
        print(f"    {u}: {n} comments")

    if not top:
        print("\n⚠️ 無留言資料，結束")
        conn.close()
        return

    test_user = top[0][0]
    print(f"\n測試對象: '{test_user}'")

    # Q1: 查該 user 的留言（區間內 30 天，受 hard cap 1000 限制）
    q1 = """
        SELECT p.board, p.article_id, p.title, p.url, p.published_at,
               json_extract(c.value, '$.tag')     AS tag,
               json_extract(c.value, '$.content') AS content,
               json_extract(c.value, '$.time')    AS ptime
        FROM ptt_posts p, json_each(p.comments_json) c
        WHERE json_extract(c.value, '$.user') = ?
          AND p.published_at >= datetime('now', '-30 days')
        ORDER BY p.published_at DESC LIMIT ?
    """
    p1 = (test_user, LIMIT_IN_RANGE)

    print("\n" + "=" * 70)
    print("Q1: 區間內留言 (30 days, limit 1000)")
    print("-- EXPLAIN QUERY PLAN --")
    explain(conn, q1, p1)
    print("-- Bench --")
    print(" ", fmt(bench(conn, q1, p1)))

    # Q2: 區間外補撈（保底觸發）
    q2 = """
        SELECT p.board, p.article_id, p.title, p.url, p.published_at,
               json_extract(c.value, '$.tag')     AS tag,
               json_extract(c.value, '$.content') AS content,
               json_extract(c.value, '$.time')    AS ptime
        FROM ptt_posts p, json_each(p.comments_json) c
        WHERE json_extract(c.value, '$.user') = ?
          AND p.published_at < datetime('now', '-30 days')
        ORDER BY p.published_at DESC LIMIT ?
    """
    p2 = (test_user, LIMIT_FALLBACK)

    print("\n" + "=" * 70)
    print("Q2: 區間外補撈 (before 30 days, limit 100)")
    print("-- EXPLAIN QUERY PLAN --")
    explain(conn, q2, p2)
    print("-- Bench --")
    print(" ", fmt(bench(conn, q2, p2)))

    # Q3: 主文查詢（ptt_posts.author 格式如 "user (nickname)"，用 LIKE）
    q3 = """
        SELECT board, article_id, title, url, published_at
        FROM ptt_posts
        WHERE author LIKE ?
          AND published_at >= datetime('now', '-30 days')
        ORDER BY published_at DESC LIMIT 20
    """
    p3 = (f"{test_user}%",)

    print("\n" + "=" * 70)
    print("Q3: 主文 (author LIKE 'user%', 30 days, limit 20)")
    print("-- EXPLAIN QUERY PLAN --")
    explain(conn, q3, p3)
    print("-- Bench --")
    print(" ", fmt(bench(conn, q3, p3)))

    # Q4: 主文查詢（全程，用於保底補撈或完整歷史）
    q4 = """
        SELECT board, article_id, title, url, published_at
        FROM ptt_posts
        WHERE author LIKE ?
        ORDER BY published_at DESC LIMIT 20
    """
    p4 = (f"{test_user}%",)
    print("\n" + "=" * 70)
    print("Q4: 主文 (author LIKE, 無時間限制, limit 20)")
    print("-- EXPLAIN QUERY PLAN --")
    explain(conn, q4, p4)
    print("-- Bench --")
    print(" ", fmt(bench(conn, q4, p4)))

    # Q5: 留言查詢（無時間限制，模擬最壞情況）
    q5 = """
        SELECT p.board, p.article_id, p.title, p.published_at,
               json_extract(c.value, '$.tag')     AS tag,
               json_extract(c.value, '$.content') AS content
        FROM ptt_posts p, json_each(p.comments_json) c
        WHERE json_extract(c.value, '$.user') = ?
        ORDER BY p.published_at DESC LIMIT ?
    """
    p5 = (test_user, LIMIT_IN_RANGE)
    print("\n" + "=" * 70)
    print("Q5: 留言 (無時間限制, limit 1000) — 最壞情況")
    print("-- EXPLAIN QUERY PLAN --")
    explain(conn, q5, p5)
    print("-- Bench --")
    print(" ", fmt(bench(conn, q5, p5)))

    conn.close()

    print("\n" + "=" * 70)
    print("判斷")
    print("  - 若所有 p95 < 500ms → JSON1 方案可行，進 Phase 0 Step 2（加 idx_ptt_author / idx_ptt_published_at）")
    print("  - 若 p95 ≥ 500ms → 保留 Phase X（正規化 ptt_comments 表）")
    print("  - 注意：加 index 後效能會再提升，此次測試是最差情境的下界")


if __name__ == "__main__":
    main()
