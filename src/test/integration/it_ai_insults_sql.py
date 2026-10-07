"""被罵的應對：資料庫語句實跑（`llm/storage/ai_interactions_store.py`）。

只在這次連線的暫存表上跑（TEMP TABLE，連線一關就消失），不碰正式的 ai_interactions 與 ai_insults。
驗的事：啟動建表會加 insulted 欄與 ai_insults 表；被罵的插話記成「沒人接」、之後不會被翻回「有人接」、
不當範例；名單只算 7 天內、分伺服器；罵它的人按的讚不算（開關 on 時）。

執行（容器內，pgvector 要在）：
    docker exec -w /app discord-bot python -m test.integration.it_ai_insults_sql
"""
from unittest import mock

from llm.storage import ai_interactions_store as store
from sys_settings import switches
from sys_settings.llm_settings import LLMServiceSettings


class _SameSession:
    """每次「開連線」都回同一條：暫存表只在建立它的那條連線看得到。"""

    def __init__(self, real):
        self.real = real

    def cursor(self):
        return self.real.cursor()

    def close(self):
        pass

    def __enter__(self):
        return self.real.__enter__()

    def __exit__(self, *exc):
        return self.real.__exit__(*exc)


def _check(label, ok):
    print(("通過" if ok else "失敗"), label)
    return ok


def main() -> int:
    real = LLMServiceSettings().pgvector_connect()
    try:
        with real, real.cursor() as cur:
            # 同名暫存表會蓋過正式表（暫存 schema 先被搜尋），之後的語句全落在暫存表
            cur.execute("CREATE TEMP TABLE ai_interactions (LIKE public.ai_interactions INCLUDING DEFAULTS)")
        ddl = store._DDL.replace("CREATE TABLE IF NOT EXISTS", "CREATE TEMP TABLE IF NOT EXISTS")
        assert "CREATE TABLE" not in ddl.replace("CREATE TEMP TABLE", ""), "DDL 有會建正式表的語句，停止"
        with mock.patch.object(store, "_get_conn", lambda: _SameSession(real)), \
                mock.patch.object(store, "_DDL", ddl), mock.patch.object(store, "_EMBED_DDL", "SELECT 1"), \
                mock.patch.object(switches, "current", lambda: switches.Switches(ambient_insult_mode="on")):
            store.ensure_table()
            with real, real.cursor() as cur:
                cur.execute("SELECT to_regclass('pg_temp.ai_insults') IS NOT NULL, to_regclass('public.ai_insults')")
                temp_ok, public_table = cur.fetchone()
                cur.execute("""INSERT INTO ai_interactions (guild_id, channel_id, directed, trigger_kind, reply_text,
                               reply_message_id, got_reply, positive_reactions, embedding)
                               VALUES ('1','2',false,'text','r','m1', false, 1, NULL), ('1','2',true,'text','r','m2', NULL, 0, NULL)""")
            ok = _check("ai_insults 只建在暫存表", temp_ok and public_table is None)
            store.mark_got_reply("m1", attempts=1)
            store.mark_insulted("m1", attempts=1)
            store.mark_got_reply("m1", attempts=1)          # 罵完又有人講話：不能翻回 TRUE
            store.mark_insulted("m2", attempts=1)
            for mid, author in (("x1", "99"), ("x2", "99"), ("x3", "77")):
                store.record_insult(guild_id="1", channel_id="2", author_id=author, message_id=mid,
                                    text="t", replied_to_message_id="m1")
            store.record_insult(guild_id="1", channel_id="2", author_id="99", message_id="x1",
                                text="t", replied_to_message_id="m1")   # 同一則重複記：不重複
            with real, real.cursor() as cur:
                cur.execute("UPDATE ai_insults SET ts = now() - interval '10 days' WHERE message_id = 'x3'")
            store.note_reaction("m2", "😂", None, "add", 99)   # 罵它的人：不算
            store.note_reaction("m2", "😂", None, "add", 100)  # 其他人：算
            with real, real.cursor() as cur:
                cur.execute("SELECT reply_message_id, got_reply, insulted, positive_reactions "
                            "FROM ai_interactions ORDER BY 1")
                rows = {r[0]: r[1:] for r in cur.fetchall()}
            ok &= _check("被罵的插話：got_reply FALSE、insulted、之後不被翻回", rows["m1"][:2] == (False, True))
            ok &= _check("沒納入觀測的（被點名）維持 NULL", rows["m2"][:2] == (None, True))
            ok &= _check("罵它的人按的讚不算", rows["m2"][2] == 1)
            insults = store.recent_insults("1", 7)
            ok &= _check("名單只算 7 天內、次數去重", set(insults) == {"99"} and insults["99"][1] == 2)
            ok &= _check("名單分伺服器", store.recent_insults("9", 7) == {})
            with mock.patch.object(store, "_embed_text", lambda t: [0.01] * 1024):
                ok &= _check("被罵的插話不當範例", store.fetch_similar_positive("x", min_positive=0, max_distance=2.0) == [])
    finally:
        real.close()
    print("全部通過" if ok else "有失敗")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
