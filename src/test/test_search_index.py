"""情報搜尋（官網公告、官方 FB、PTT、巴哈）的索引、搜尋與讀全文。

守的底線：
  - 四種來源都搜得到，每筆結果的 id 與連結固定（巴哈以「樓層」為單位，用 sn；串號＋樓層會重複）
  - 公告存的是 HTML，要當純文字搜；兩個字的角色名也要搜得到；回覆樓層靠討論串標題也找得到
  - 每種來源有筆數上限，論壇的量不能把官方公告擠掉；含全部關鍵字的排前面
  - 新文章、改過的、刪掉的，下一次搜尋前都會跟上；只被「看過」（時間戳變了、內容沒變）的不重建
  - **絕不寫 scraper 的資料庫**（articles.db 是使用者資料，只能唯讀開）
  - 讀全文時帶上 PTT 推文、巴哈留言，並分頁

執行：
    cd src && python -m unittest test.test_search_index -v
"""

import hashlib
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from services.search import DocumentNotFound, SearchIndex  # noqa: E402
from services.search import text as search_text  # noqa: E402

SCHEMA = """
CREATE TABLE article_details (id INTEGER PRIMARY KEY, article_id INTEGER, article_title TEXT,
    article_content TEXT, start_time DATETIME, created_at DATETIME, updated_at DATETIME);
CREATE TABLE fb_posts (id INTEGER PRIMARY KEY, post_id TEXT, url TEXT, pfbid_url TEXT, text TEXT,
    timestamp DATETIME, created_at DATETIME, updated_at DATETIME);
CREATE TABLE ptt_posts (id INTEGER PRIMARY KEY, board TEXT, article_id TEXT, title TEXT, url TEXT,
    content TEXT, published_at DATETIME, comments_json TEXT, created_at DATETIME, updated_at DATETIME);
CREATE TABLE bahamut_posts (id INTEGER PRIMARY KEY, board_id TEXT, post_id TEXT, sn TEXT,
    position INTEGER, title TEXT, url TEXT, published_at DATETIME, content TEXT, is_deleted BOOLEAN,
    created_at DATETIME, updated_at DATETIME);
CREATE TABLE bahamut_post_comments (id INTEGER PRIMARY KEY, bahamut_post_id INTEGER, parent_sn TEXT,
    comment_id TEXT, user_name TEXT, content TEXT, published_at DATETIME);
"""

T0 = "2026-01-01 00:00:00.000000"


class ScraperDb:
    """照 scraper 的欄位建一份小資料庫；測試裡用它模擬 scraper 新增、修改、刪除。"""

    def __init__(self, path: Path):
        self.path = path
        self.con = sqlite3.connect(path)
        self.con.executescript(SCHEMA)
        self._clock = 0

    def tick(self) -> str:
        """單調遞增的 updated_at，模擬 scraper 每次寫入的時間。"""
        self._clock += 1
        return f"2026-02-01 00:00:{self._clock:02d}.000000"

    def article(self, article_id, title, html, start="2026-01-10 10:00:00.000000"):
        self.con.execute(
            "INSERT INTO article_details (article_id, article_title, article_content, start_time,"
            " created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (article_id, title, html, start, T0, self.tick()))
        self.con.commit()

    def fb(self, text, ts="2026-01-11 10:00:00.000000", url=None, pfbid_url="https://fb.example/p/1"):
        cur = self.con.execute(
            "INSERT INTO fb_posts (post_id, url, pfbid_url, text, timestamp, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?)", ("fb_x", url, pfbid_url, text, ts, T0, self.tick()))
        self.con.commit()
        return cur.lastrowid

    def ptt(self, article_id, title, content, published="2026-01-12 10:00:00.000000", comments=()):
        self.con.execute(
            "INSERT INTO ptt_posts (board, article_id, title, url, content, published_at, comments_json,"
            " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            ("C_Chat", article_id, title, f"https://www.ptt.cc/bbs/C_Chat/{article_id}.html", content,
             published, json.dumps(list(comments), ensure_ascii=False), T0, self.tick()))
        self.con.commit()

    def floor(self, post_id, position, sn, content, title="", published="2026-01-13 10:00:00.000000"):
        cur = self.con.execute(
            "INSERT INTO bahamut_posts (board_id, post_id, sn, position, title, url, published_at, content,"
            " is_deleted, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,0,?,?)",
            ("74934", post_id, sn, position, title,
             f"https://forum.gamer.com.tw/C.php?bsn=74934&snA={post_id}", published, content, T0, self.tick()))
        self.con.commit()
        return cur.lastrowid

    def comment(self, floor_row_id, parent_sn, user, content):
        self.con.execute(
            "INSERT INTO bahamut_post_comments (bahamut_post_id, parent_sn, comment_id, user_name, content,"
            " published_at) VALUES (?,?,?,?,?,?)", (floor_row_id, parent_sn, "c1", user, content, T0))
        self.con.commit()

    def update(self, sql, *args):
        self.con.execute(sql, args)
        self.con.commit()


class SearchIndexTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        self.db = ScraperDb(tmp / "articles.db")
        self.index_path = tmp / "index" / "search_index.db"

    def tearDown(self):
        self.db.con.close()
        self._tmp.cleanup()

    def make_index(self, **overrides) -> SearchIndex:
        options = dict(per_source_limit=5, max_limit=20, fetch_page_chars=4000, sync_min_interval_seconds=0)
        options.update(overrides)
        return SearchIndex(index_path=self.index_path, articles_db_path=self.db.path, **options)

    def ids(self, hits) -> list[str]:
        return [h.doc_id for h in hits]


class EverySourceTests(SearchIndexTestBase):
    def test_every_source_is_searchable_with_stable_ids_and_links(self):
        self.db.article(4930, "巡迴演唱會台北站", "<p>演出場館在桃園會展中心</p>")
        fb_id = self.db.fb("悠遊卡預購開始，獨家商品甲")
        self.db.ptt("M.1.A.AAA", "[鳴潮] 西西點位", "每天下午病房出現獨家商品乙")
        self.db.floor("8166", 1, "136900", "兌換碼分享串的主文", title="【情報】兌換碼分享串")
        self.db.floor("8166", 465, "136939", "科考摩托塗裝兌換碼獨家商品丙")
        index = self.make_index()

        found = {h.doc_id: h for h in index.search("獨家商品") + index.search("桃園會展中心")}

        self.assertIn("article:4930", found)
        self.assertIn(f"fb:{fb_id}", found)
        self.assertIn("ptt:M.1.A.AAA", found)
        self.assertIn("bahamut:136939", found)  # 樓層用 sn，不是 8166#465
        self.assertEqual(found["article:4930"].url,
                         "https://wutheringwaves.kurogames.com/zh-tw/main/news/detail/4930")
        self.assertEqual(found[f"fb:{fb_id}"].url, "https://fb.example/p/1")
        self.assertEqual(found["ptt:M.1.A.AAA"].url, "https://www.ptt.cc/bbs/C_Chat/M.1.A.AAA.html")
        self.assertEqual(found["bahamut:136939"].url, "https://forum.gamer.com.tw/Co.php?bsn=74934&sn=136939")
        self.assertTrue(found["article:4930"].official)
        self.assertFalse(found["ptt:M.1.A.AAA"].official)

    def test_announcement_html_is_searched_as_plain_text(self):
        self.db.article(1, "深塔公告", '<div><p>深塔<b>海墟</b>每兩週重置</p><span class="x">注意</span></div>')
        index = self.make_index()

        self.assertEqual(self.ids(index.search("深塔海墟")), ["article:1"])  # 標籤拆開的字也接得起來
        self.assertEqual(index.search("span"), [])  # 標籤本身不算內容
        self.assertEqual(index.search("class"), [])

    def test_two_character_term_is_found(self):
        self.db.floor("5499", 1, "200", "分身會繼承秋水的生命值，持續8秒", title="【攻略】嘲諷坦輔")
        self.db.floor("5500", 1, "201", "完全無關的內容", title="【閒聊】別的話題")
        index = self.make_index()

        self.assertEqual(self.ids(index.search("秋水")), ["bahamut:200"])

    def test_reply_floor_is_found_through_its_thread_title(self):
        self.db.floor("7635", 1, "300", "總共有3次寶箱可以拿", title="【攻略】槲生半島深囚者攻略")
        self.db.floor("7635", 2, "301", "第一次打贏後一個寶箱，後面可以再打兩次")
        index = self.make_index()

        self.assertIn("bahamut:301", self.ids(index.search("深囚者")))
        self.assertIn("深囚者", index.search("深囚者 再打兩次")[0].title)  # 樓層的標題用討論串標題

    def test_question_sentence_is_ranked_by_its_rare_words(self):
        # 中文句子沒有空格：整句丟進來時，「卜靈」這種少見的兩字詞要比「是什麼」「身分」這種常見詞重要
        self.db.article(1, "檔案公開 | 妙算神聽", "<p>卜靈：瑝瓏夢州方士，黑海岸客卿</p>")
        for i in range(5):
            self.db.floor(str(10 + i), 1, str(900 + i), "這段劇情是什麼意思？主角的身分是什麼？大家覺得是什麼",
                          title=f"【討論】劇情討論串{i}")
        index = self.make_index()

        self.assertEqual(self.ids(index.search("卜靈是什麼身分？"))[:1], ["article:1"])

    def test_one_character_keyword_is_found(self):
        self.db.floor("1", 1, "700", "椿的普攻傷害占比83%", title="【攻略】角色數據")
        self.db.floor("2", 1, "701", "普攻教學：其他角色", title="【攻略】普攻")
        index = self.make_index()

        self.assertEqual(self.ids(index.search("椿 普攻"))[:1], ["bahamut:700"])
        self.assertEqual(self.ids(index.search("椿")), ["bahamut:700"])  # 只有一個字也要找得到

    def test_sentence_query_still_finds_paraphrased_text(self):
        self.db.article(1, "深塔公告", "<p>深塔海墟每兩週重置一次</p>")
        self.db.article(2, "其他公告", "<p>今天天氣很好</p>")
        index = self.make_index()

        self.assertEqual(self.ids(index.search("深塔海墟多久會重置"))[:1], ["article:1"])


class RankingTests(SearchIndexTestBase):
    def test_documents_with_every_term_rank_first(self):
        # 只看 BM25 的話，短文裡重複很多次的「兌換碼」會贏過長文裡各出現一次的兩個詞
        self.db.ptt("M.1.A.001", "兌換碼", "兌換碼兌換碼兌換碼兌換碼")
        self.db.ptt("M.1.A.002", "直播整理", "很長的閒聊。" * 50 + "前瞻直播送的兌換碼如下")
        index = self.make_index()

        self.assertEqual(self.ids(index.search("兌換碼 前瞻"))[:2], ["ptt:M.1.A.002", "ptt:M.1.A.001"])

    def test_each_source_is_capped_so_forums_cannot_crowd_out_official_posts(self):
        for i in range(8):
            self.db.ptt(f"M.1.A.{i:03d}", f"心得{i}", "鳴潮演唱會心得分享")
        self.db.article(4930, "演唱會公告", "<p>鳴潮演唱會台北站</p>")
        index = self.make_index(per_source_limit=3)

        hits = index.search("鳴潮演唱會")
        self.assertEqual(sum(h.source == "ptt" for h in hits), 3)
        self.assertIn("article:4930", self.ids(hits))

    def test_limit_caps_the_total(self):
        for i in range(8):
            self.db.ptt(f"M.1.A.{i:03d}", f"心得{i}", "鳴潮演唱會心得分享")
        index = self.make_index(per_source_limit=10)

        self.assertEqual(len(index.search("鳴潮演唱會", limit=4)), 4)


class FilterTests(SearchIndexTestBase):
    def setUp(self):
        super().setUp()
        self.db.article(1, "舊公告", "<p>版本更新說明</p>", start="2025-06-01 10:00:00.000000")
        self.db.article(2, "新公告", "<p>版本更新說明</p>", start="2026-03-01 10:00:00.000000")
        self.db.ptt("M.1.A.001", "版本", "版本更新說明的心得", published="2026-03-02 10:00:00.000000")
        self.index = self.make_index()

    def test_since_and_until_are_inclusive_days(self):
        self.assertEqual(set(self.ids(self.index.search("版本更新", since="2026-03-01"))),
                         {"article:2", "ptt:M.1.A.001"})
        self.assertEqual(self.ids(self.index.search("版本更新", until="2025-06-01")), ["article:1"])

    def test_sources_filter(self):
        self.assertEqual(set(self.ids(self.index.search("版本更新", sources=["article"]))),
                         {"article:1", "article:2"})

    def test_far_future_until_means_no_upper_bound(self):
        # 模型想表達「不設上限」時可能傳 9999-12-31：不能因為日期溢位而整個搜尋失敗
        self.assertEqual(set(self.ids(self.index.search("版本更新", until="9999-12-31"))),
                         {"article:1", "article:2", "ptt:M.1.A.001"})

    def test_unknown_source_and_bad_date_are_rejected_with_the_valid_choices(self):
        with self.assertRaises(ValueError) as ctx:
            self.index.search("版本", sources=["telegram"])
        self.assertIn("article", str(ctx.exception))
        with self.assertRaises(ValueError):
            self.index.search("版本", since="上個月")


class SyncTests(SearchIndexTestBase):
    def test_new_changed_and_deleted_rows_are_picked_up_before_the_next_search(self):
        self.db.ptt("M.1.A.001", "舊文", "原本的內容甲")
        keep_row = self.db.floor("1", 1, "500", "不會變的樓層內容", title="【閒聊】串")
        self.db.floor("1", 2, "501", "會被修改的樓層")
        self.db.floor("1", 3, "502", "會被刪掉的樓層")
        index = self.make_index()
        index.search("內容")

        self.db.ptt("M.1.A.002", "新文", "新增的情報乙")
        self.db.update("UPDATE bahamut_posts SET content=?, updated_at=? WHERE sn='501'", "改過的情報丙", self.db.tick())
        self.db.update("UPDATE bahamut_posts SET is_deleted=1, updated_at=? WHERE sn='502'", self.db.tick())
        # scraper 每輪都會更新「最後看到時間」，連帶改到 updated_at，但內容沒變
        self.db.update("UPDATE bahamut_posts SET updated_at=? WHERE id=?", self.db.tick(), keep_row)

        report = index.sync()

        self.assertEqual((report.added, report.updated, report.removed), (1, 1, 1))
        self.assertEqual(self.ids(index.search("新增的情報"))[:1], ["ptt:M.1.A.002"])
        self.assertEqual(self.ids(index.search("改過的情報"))[:1], ["bahamut:501"])
        self.assertNotIn("bahamut:502", self.ids(index.search("會被刪掉的樓層")))

    def test_old_words_do_not_stick_after_update_or_delete(self):
        self.db.floor("1", 1, "800", "原本寫的是第一版說明", title="【攻略】改過的文")
        index = self.make_index()
        index.sync()
        self.db.update("UPDATE bahamut_posts SET content=?, updated_at=? WHERE sn='800'", "後來全部改寫", self.db.tick())
        index.sync()
        self.assertEqual(index.search("第一版說明"), [])  # 改掉的字不能還找得到

        # 刪掉最後一筆後，新文章可能沿用同一個列編號；被刪文章的字不能黏到新文章上
        self.db.floor("2", 1, "801", "獨一無二的舊段落", title="【閒聊】會被刪")
        index.sync()
        self.db.update("UPDATE bahamut_posts SET is_deleted=1, updated_at=? WHERE sn='801'", self.db.tick())
        index.sync()
        self.db.ptt("M.1.A.009", "新文章", "完全不同的新內容")
        index.sync()
        self.assertEqual(index.search("獨一無二的舊段落"), [])

    def test_rows_sharing_the_cursor_timestamp_are_not_skipped(self):
        """scraper 同一輪寫入的列 updated_at 相同；游標停在其中一列時，同時間、編號較大的列下次還要撈到。"""
        stamp = self.db.tick()
        first = self.db.floor("1", 1, "700", "同一輪寫入的甲", title="【閒聊】甲")
        self.db.update("UPDATE bahamut_posts SET updated_at=? WHERE id=?", stamp, first)
        index = self.make_index()
        index.sync()
        second = self.db.floor("2", 1, "701", "同一輪寫入的乙", title="【閒聊】乙")
        self.db.update("UPDATE bahamut_posts SET updated_at=? WHERE id=?", stamp, second)

        index.sync()

        self.assertIn("bahamut:701", self.ids(index.search("同一輪寫入的乙")))

    def test_sync_seeks_through_the_scrapers_updated_at_index(self):
        """有 scraper 的 (updated_at, id) 索引時，增量同步直接跳到游標之後、不整張表掃：
        巴哈十萬多列整張掃，沒有變動也要讀 120 MB，冷快取時一次同步 20 秒以上。"""
        tables = ("article_details", "fb_posts", "ptt_posts", "bahamut_posts")
        for table in tables:
            self.db.con.execute(f"CREATE INDEX ix_{table}_updated_at_id ON {table} (updated_at, id)")
        self.db.con.commit()
        self.db.ptt("M.1.A.001", "標題", "內容")
        index = self.make_index()
        index.sync()
        queries = []
        open_source = index._open_source

        def traced():
            con = open_source()
            con.set_trace_callback(queries.append)
            return con

        index._open_source = traced
        index.sync(force=True)

        scans = [q for q in queries if q.lstrip().upper().startswith("SELECT") and "updated_at" in q]
        self.assertEqual(len(scans), len(tables))
        for sql in scans:
            plan = " ".join(row[3] for row in self.db.con.execute(
                "EXPLAIN QUERY PLAN " + sql, ("", 0) if "?" in sql else ()))
            self.assertTrue(plan.startswith("SEARCH") and "updated_at_id" in plan, plan)

    def test_search_syncs_by_itself(self):
        index = self.make_index()
        self.assertEqual(index.search("突發情報"), [])
        self.db.fb("突發情報：維護延長")

        self.assertEqual(len(index.search("突發情報")), 1)

    def test_never_writes_the_scraper_database(self):
        self.db.ptt("M.1.A.001", "標題", "內容", comments=[{"tag": "推", "user": "a", "content": "b", "time": "1"}])
        self.db.con.close()
        before = hashlib.sha256(self.db.path.read_bytes()).hexdigest()

        index = self.make_index()
        index.search("內容")
        index.fetch("ptt:M.1.A.001")

        self.assertEqual(hashlib.sha256(self.db.path.read_bytes()).hexdigest(), before)
        self.assertFalse(Path(str(self.db.path) + "-wal").exists())
        self.assertTrue(self.index_path.exists())
        self.db.con = sqlite3.connect(self.db.path)  # 給 tearDown 關

    def test_newer_index_is_never_downgraded(self):
        """舊程式的行程（例如開著的 MCP）遇到新版索引：停下並說明，不能把索引砍回舊版。"""
        self.db.article(1, "公告", "<p>內容</p>")
        index = self.make_index()
        index.sync()
        with sqlite3.connect(self.index_path) as con:
            con.execute("UPDATE meta SET value='99' WHERE key='schema'")

        from services.search import IndexTooNew
        with self.assertRaises(IndexTooNew):
            index.sync(force=True)
        with sqlite3.connect(self.index_path) as con:
            self.assertEqual(con.execute("SELECT value FROM meta WHERE key='schema'").fetchone()[0], "99")
            self.assertEqual(con.execute("SELECT count(*) FROM docs").fetchone()[0], 1)   # 沒被清掉

    def test_older_index_is_rebuilt(self):
        self.db.article(1, "公告", "<p>內容</p>")
        index = self.make_index()
        index.sync()
        with sqlite3.connect(self.index_path) as con:
            con.execute("UPDATE meta SET value='1' WHERE key='schema'")

        self.assertTrue(index.sync(force=True).rebuilt)
        self.assertEqual(self.ids(index.search("內容")), ["article:1"])

    def test_changing_the_text_normalizer_rebuilds_the_index(self):
        self.db.article(1, "公告", "<p>內容</p>")
        index = self.make_index()
        index.sync()
        with sqlite3.connect(self.index_path) as con:
            con.execute("UPDATE meta SET value='舊版' WHERE key='normalizer'")

        report = index.sync()

        self.assertTrue(report.rebuilt)
        self.assertEqual(self.ids(index.search("內容")), ["article:1"])


class FetchTests(SearchIndexTestBase):
    def test_ptt_full_text_includes_pushes_and_is_paged(self):
        self.db.ptt("M.1.A.001", "[鳴潮] 長文", "很長的內文。" * 300,
                    comments=[{"tag": "推", "user": "alice", "content": "推文在最後", "time": "10/08 00:59"}])
        index = self.make_index(fetch_page_chars=500)

        first = index.fetch("ptt:M.1.A.001")
        last = index.fetch("ptt:M.1.A.001", page=first.total_pages)

        self.assertGreater(first.total_pages, 1)
        self.assertEqual(first.title, "[鳴潮] 長文")
        self.assertIn("alice", last.text)
        self.assertIn("推文在最後", last.text)
        self.assertEqual(first.url, "https://www.ptt.cc/bbs/C_Chat/M.1.A.001.html")

    def test_bahamut_floor_includes_thread_title_and_its_comments(self):
        self.db.floor("7635", 1, "300", "主文", title="【攻略】槲生半島深囚者攻略")
        row = self.db.floor("7635", 2, "301", "後面可以再打兩次")
        self.db.comment(row, "301", "bob", "感謝整理")

        doc = self.make_index().fetch("bahamut:301")

        self.assertIn("深囚者", doc.title)
        self.assertIn("2 樓", doc.title)
        self.assertIn("後面可以再打兩次", doc.text)
        self.assertIn("感謝整理", doc.text)

    def test_announcement_is_returned_as_plain_text(self):
        self.db.article(1, "公告", "<div><p>第一段</p><p>第二段</p></div>")

        doc = self.make_index().fetch("article:1")

        self.assertNotIn("<p>", doc.text)
        self.assertIn("第一段", doc.text)

    def test_unknown_or_malformed_id_raises(self):
        index = self.make_index()
        for bad in ("ptt:M.9.A.999", "article:abc", "telegram:1", "沒有冒號"):
            with self.subTest(bad=bad), self.assertRaises(DocumentNotFound):
                index.fetch(bad)


class StubVectorStore:
    """假的向量那一路：照預先排好的名單回傳，記下收到的篩選條件；`error` 給了就丟出來。"""

    def __init__(self, ranked=(), error=None):
        self.ranked, self.error, self.calls = list(ranked), error, []

    def search(self, query, *, sources, start, end, k, max_distance=None):
        self.calls.append({"query": query, "sources": list(sources), "start": start, "end": end, "k": k,
                           "max_distance": max_distance})
        if self.error:
            raise self.error
        return self.ranked[:k]


class HybridSearchTests(SearchIndexTestBase):
    """P3：關鍵字的名次和向量的名次用 RRF 合併。"""

    def test_document_only_found_by_meaning_is_returned(self):
        # 問「冰棒口味」，文章只寫「阿奇儂合作」：關鍵字找不到，向量找得到
        self.db.fb("《鳴潮》× 阿奇儂 合作預告：香草朱古力、咖啡核果、花生脆粒")
        index = self.make_index(vector_store=StubVectorStore(["fb:1"]))

        self.assertEqual(self.ids(index.search("聯名冰棒有哪幾種口味")), ["fb:1"])

    def test_documents_found_by_both_rank_first(self):
        self.db.ptt("M.1.A.001", "[鳴潮] 深塔", "深塔海墟重置時間，深塔海墟")   # 關鍵字第一
        self.db.ptt("M.1.A.002", "[鳴潮] 整理", "深塔海墟每兩週重置")           # 關鍵字第二、向量第一
        index = self.make_index(vector_store=StubVectorStore(["ptt:M.1.A.002"]))

        self.assertEqual(self.ids(index.search("深塔海墟"))[:2], ["ptt:M.1.A.002", "ptt:M.1.A.001"])

    def test_vector_failure_falls_back_to_keywords(self):
        self.db.ptt("M.1.A.001", "[鳴潮] 深塔", "深塔海墟每兩週重置")
        plain = self.ids(self.make_index().search("深塔海墟"))
        broken = self.make_index(vector_store=StubVectorStore(error=ConnectionError("pgvector 連不上")))

        with self.assertLogs("services.search.index", level="WARNING"):
            self.assertEqual(self.ids(broken.search("深塔海墟")), plain)

    def test_weight_and_threshold_reach_the_vector_side(self):
        self.db.ptt("M.1.A.001", "[鳴潮] 深塔", "深塔海墟重置時間，深塔海墟")
        self.db.ptt("M.1.A.002", "[鳴潮] 整理", "深塔海墟每兩週重置")
        self.db.ptt("M.1.A.003", "[鳴潮] 換句話說", "逆境高塔每十四天刷新一次")   # 只有向量找得到
        store = StubVectorStore(["ptt:M.1.A.003"])
        light = self.make_index(vector_store=store, vector_weight=0.1, vector_max_distance=0.45)
        heavy = self.make_index(vector_store=StubVectorStore(["ptt:M.1.A.003"]), vector_weight=2.0)

        # RRF 的 k=60 時，第 1、2 名分數只差 1/61 與 1/62：權重決定「只有向量找到的」排在哪
        self.assertEqual(self.ids(light.search("深塔海墟")), ["ptt:M.1.A.001", "ptt:M.1.A.002", "ptt:M.1.A.003"])
        self.assertEqual(self.ids(heavy.search("深塔海墟"))[0], "ptt:M.1.A.003")
        self.assertEqual(store.calls[0]["max_distance"], 0.45)

    def test_switch_off_means_keywords_only(self):
        self.db.fb("《鳴潮》× 阿奇儂 合作預告")
        store = StubVectorStore(["fb:1"])
        index = self.make_index(vector_store=store, vector_enabled=lambda: False)

        self.assertEqual(index.search("聯名冰棒有哪幾種口味"), [])
        self.assertEqual(store.calls, [])   # 關著時連 embedding 都不打

    def test_vector_side_gets_the_same_filters(self):
        self.db.ptt("M.1.A.001", "[鳴潮] 深塔", "深塔海墟每兩週重置", published="2026-03-02 10:00:00.000000")
        store = StubVectorStore(["ptt:M.1.A.001"])
        index = self.make_index(vector_store=store)

        index.search("深塔海墟", sources=["ptt"], since="2026-03-01", until="2026-03-31")

        self.assertEqual(store.calls[0]["sources"], ["ptt"])
        self.assertEqual((store.calls[0]["start"], store.calls[0]["end"]), ("2026-03-01", "2026-04-01"))

    def test_vector_results_outside_the_filters_are_dropped(self):
        self.db.ptt("M.1.A.001", "[鳴潮] 新文", "今年的內容", published="2026-02-02 10:00:00.000000")
        self.db.ptt("M.1.A.002", "[鳴潮] 舊文", "去年的內容", published="2025-01-02 10:00:00.000000")
        # 假的向量那一路不守篩選：塞一篇範圍外的、一篇不存在的，搜尋都不能放進結果
        index = self.make_index(vector_store=StubVectorStore(["ptt:M.1.A.002", "ptt:M.9.A.999", "ptt:M.1.A.001"]))

        ids = self.ids(index.search("內容", since="2026-01-01"))

        self.assertIn("ptt:M.1.A.001", ids)
        self.assertNotIn("ptt:M.1.A.002", ids)
        self.assertNotIn("ptt:M.9.A.999", ids)


@unittest.skipUnless(search_text.has_chinese_converter(), "容器還沒裝 opencc（requirements 已加，重建 image 後會跑）")
class SimplifiedChineseTests(SearchIndexTestBase):
    def test_simplified_and_traditional_match_each_other(self):
        self.db.floor("1", 1, "600", "紅名怪打完三天才會重生", title="【情報】紅怪")
        self.db.floor("2", 1, "601", "红名怪大概三天刷新一次", title="【问题】刷新")
        index = self.make_index()

        self.assertEqual(set(self.ids(index.search("红名怪"))), {"bahamut:600", "bahamut:601"})
        self.assertEqual(set(self.ids(index.search("紅名怪"))), {"bahamut:600", "bahamut:601"})


if __name__ == "__main__":
    unittest.main()
