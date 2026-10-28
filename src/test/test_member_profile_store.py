"""成員資料的寫入（llm/storage/member_profile_store：先算向量、同一個交易刪舊寫新）。

守的底線：
  1. 先算向量再碰資料庫：embedding 後端出錯（5xx、連不上）時連交易都不開、舊列不刪；index_* 回失敗、ERROR 寫明舊資料保留。
  2. 刪舊與寫新在同一個交易、同一個 cursor，順序是 算向量 → 開交易 → DELETE → INSERT → commit；
     INSERT 帶的向量就是算出來的那個，DELETE 用的就是這份資料的 doc_id。
  3. INSERT 失敗時整段 rollback、不 commit，index_* 回失敗。
  4. 一份資料一列：表單上限的長自介（600＋300 字）也只寫一列、只算一次向量（切成兩段會撞唯一索引、整筆寫不進去）。
  5. 列的格式和 LlamaIndex 自己寫的一樣：寫進成員資料那張表的 text、metadata_、node_id、embedding 四欄，metadata 的
     ref_doc_id／doc_id／document_id 都是 doc_id、_node_content 裡不重複存內文，用 LlamaIndex 還原得回來；
     DELETE 也只刪成員資料那張表裡這份資料的列；向量輸入是 metadata 加內文（和既有的列同一種算法）。
  6. 第一次寫入前先建表（空的 add）並補索引，之後的寫入不再重來。
  7. 招牌梗的 suppressed／blacklisted 寫回時沿用資料庫裡現在的值：本人在算向量的期間用 /forget_tag 封鎖，
     寫回不能把它蓋回 0；讀的那句鎖住舊列（FOR UPDATE），在 DELETE 之前、同一個交易裡；其他種類不鎖不讀。

不連資料庫、不打 embedding：向量庫、embedding 模型、pgvector 交易都是假物件。
"""
import asyncio
import json
import os
import sys
import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from llm.client.http_client import LlmAPIError, LlmConnectionError  # noqa: E402
from llm.storage import member_profile_store as mps  # noqa: E402

try:
    from llama_index.core.vector_stores.utils import metadata_dict_to_node
except ImportError:  # pragma: no cover - 沒裝 llama_index 的環境整檔跳過
    metadata_dict_to_node = None

VECTOR = [0.25, -0.5, 0.125]


class FakeEmbed:
    def __init__(self, events, fail=None):
        self.events, self.fail, self.inputs = events, fail, []

    def get_text_embedding_batch(self, texts):
        self.events.append("embed")
        self.inputs.extend(texts)
        if self.fail is not None:
            raise self.fail
        return [list(VECTOR) for _ in texts]


class FakeCursor:
    """記下每句 SQL；SELECT（鎖舊列）回 stored 裡這份資料現在的 metadata。"""

    def __init__(self, events, stored, fail_insert=None):
        self.events, self.stored, self.fail_insert, self.calls = events, stored, fail_insert, []
        self._row = None

    def execute(self, sql, params=None):
        words = " ".join(sql.split())
        verb = words.split()[0].upper()
        self.events.append(verb)
        self.calls.append((verb, words, params))
        if verb == "SELECT":
            current = self.stored.get(params[0])
            self._row = (json.dumps(current),) if current is not None else None
        if verb == "INSERT" and self.fail_insert is not None:
            raise self.fail_insert

    def fetchone(self):
        return self._row


class FakeVectorStore:
    flat_metadata = False

    def __init__(self, events):
        self.events = events

    def add(self, nodes):
        self.events.append(f"create_table({len(list(nodes))})")
        return []


@unittest.skipIf(mps.TextNode is None or metadata_dict_to_node is None, "需要 llama_index")
class MemberProfileWriteTests(unittest.TestCase):
    def store(self, *, embed_fail=None, insert_fail=None, stored=None):
        # 設定整個換成假的：不讀環境變數、不碰資料庫
        with mock.patch.object(mps, "LLMServiceSettings", SimpleNamespace):
            store = mps.PgVectorMemberProfileStore()
        self.events, self.cursors = [], []
        self.stored = stored if stored is not None else {}   # doc_id → 資料庫裡現在的 metadata
        self.embed = FakeEmbed(self.events, embed_fail)
        vector_store = FakeVectorStore(self.events)

        @contextmanager
        def pgvector_cursor(*, commit=False):
            self.events.append(f"begin(commit={commit})")
            cur = FakeCursor(self.events, self.stored, insert_fail)
            self.cursors.append(cur)
            try:
                yield cur
            except BaseException:
                self.events.append("rollback")
                raise
            self.events.append("commit")

        store.settings = SimpleNamespace(pgvector_cursor=pgvector_cursor,
                                         pgvector_vector_store=lambda **_kw: vector_store)
        store._get_embed_model = lambda: self.embed
        store._ensure_schema_constraints = lambda: self.events.append("schema")
        return store

    def write_preference(self, store):
        return asyncio.run(store.index_preference_fact(
            guild_id=9, author_id=1, alias="米拉", fact="喜歡今汐", fact_key="like:今汐", category="like",
            confidence=0.9, status="trusted", mention_count=3, first_seen="2026-10-01", last_seen="2026-10-28"))

    def write_tag(self, store, *, suppressed="0", blacklisted="0"):
        return asyncio.run(store.index_signature_tag(
            guild_id=9, author_id=1, alias="阿狗", tag="狗王", tag_key="dog_king", tag_kind="nickname",
            sensitivity="low", self_claimed="0", confidence=0.9, status="trusted", mention_count=4,
            first_seen="2026-10-01", last_seen="2026-10-28", last_corroborated_day="2026-10-28",
            suppressed=suppressed, blacklisted=blacklisted))

    def statements(self, verb):
        return [(words, params) for cur in self.cursors for v, words, params in cur.calls if v == verb]

    def insert_params(self):
        inserts = self.statements("INSERT")
        self.assertEqual(1, len(inserts))
        return inserts[0][1]

    def test_embedding_failure_leaves_the_old_row_untouched(self):
        for fail in (LlmAPIError("HTTP 500", status=500, detail="vk::Queue::submit: ErrorDeviceLost"),
                     LlmConnectionError("POST /embeddings 連線錯誤")):
            with self.subTest(fail=type(fail).__name__):
                store = self.store(embed_fail=fail)
                with self.assertLogs(mps.logger, "ERROR") as logs:
                    self.assertIsNone(self.write_preference(store))
                self.assertEqual([], self.cursors, "還沒算出向量就不能開交易")
                self.assertNotIn("DELETE", self.events)
                self.assertIn("舊資料保留", "\n".join(logs.output))

        store = self.store(embed_fail=LlmAPIError("HTTP 500", status=500))
        with self.assertLogs(mps.logger, "ERROR"):
            ok = asyncio.run(store.index_auto_personality(guild_id=9, author_id=1, alias="米拉", personality="愛吐槽"))
        self.assertFalse(ok)
        self.assertNotIn("DELETE", self.events)

    def test_delete_and_insert_share_one_transaction_after_the_embedding(self):
        store = self.store()
        doc_id = self.write_preference(store)

        self.assertEqual(["embed", "begin(commit=True)", "DELETE", "INSERT", "commit"],
                         self.events[self.events.index("embed"):])
        self.assertEqual(1, len(self.cursors), "刪與寫要用同一個 cursor、同一個交易")
        [(delete_sql, delete_params)] = self.statements("DELETE")
        self.assertEqual((doc_id, doc_id, doc_id), delete_params)
        self.assertEqual("DELETE FROM data_discord_member_profiles_index WHERE metadata_->>'ref_doc_id' = %s "
                         "OR metadata_->>'doc_id' = %s OR metadata_->>'document_id' = %s", delete_sql,
                         "只刪成員資料那張表裡、這份資料的列")
        self.assertEqual([], self.statements("SELECT"), "偏好不需要鎖舊列")
        text, _metadata, node_id, embedding = self.insert_params()
        self.assertEqual(VECTOR, embedding, "寫進去的就是先算好的向量")
        self.assertTrue(node_id)
        self.assertIn("fact: 喜歡今汐", text)

    def test_insert_failure_rolls_back_and_reports(self):
        store = self.store(insert_fail=RuntimeError("expected 1024 dimensions, not 3"))
        with self.assertLogs(mps.logger, "ERROR"):
            self.assertIsNone(self.write_preference(store))
        self.assertEqual("rollback", self.events[-1])
        self.assertNotIn("commit", self.events)

    def test_long_intro_is_one_row_and_one_embedding(self):
        store = self.store()
        bio, message = "我" * 600, "嗨" * 300
        asyncio.run(store.index_intro_profile(guild_id=9, channel_id=5, author_id=1, alias="米拉",
                                              wuwa_uid="800000001", bio=bio, message_to_all=message))
        text, _metadata, _node_id, _embedding = self.insert_params()
        self.assertEqual(1, len(self.embed.inputs), "整份一個向量")
        self.assertIn(bio, text)
        self.assertIn(message, text)

    def test_row_format_matches_llama_index(self):
        store = self.store()
        doc_id = self.write_preference(store)
        text, metadata_json, node_id, _embedding = self.insert_params()
        metadata = json.loads(metadata_json)

        [(insert_sql, _params)] = self.statements("INSERT")
        self.assertEqual("INSERT INTO data_discord_member_profiles_index (text, metadata_, node_id, embedding) "
                         "VALUES (%s, %s::json, %s, %s::vector)", insert_sql)
        self.assertEqual("", json.loads(metadata["_node_content"])["text"], "內文只存在 text 欄，和 LlamaIndex 寫的一樣")
        for key in ("ref_doc_id", "doc_id", "document_id"):
            self.assertEqual(doc_id, metadata[key], key)
        self.assertEqual("preference_fact", metadata["profile_kind"])
        self.assertEqual("3", metadata["mention_count"])
        node = metadata_dict_to_node(metadata, text=text)
        self.assertEqual((doc_id, node_id), (node.ref_doc_id, node.node_id))
        embedded = self.embed.inputs[0]
        self.assertIn("profile_kind: preference_fact", embedded, "向量輸入含 metadata，和既有的列同一種算法")
        self.assertIn("fact: 喜歡今汐", embedded)

    def test_owner_flags_set_while_embedding_survive_the_rewrite(self):
        """插話記憶讀到 suppressed／blacklisted＝0，算向量的期間本人按了「永久封鎖」：寫回要沿用封鎖，不能蓋回 0。"""
        doc_id = mps.PgVectorMemberProfileStore._signature_tag_doc_id(9, 1, "dog_king")
        store = self.store(stored={doc_id: {"doc_id": doc_id, "suppressed": "0", "blacklisted": "0"}})

        def block_during_embedding(texts, _original=self.embed.get_text_embedding_batch):
            self.stored[doc_id].update(suppressed="1", blacklisted="1")   # /forget_tag 的 UPDATE 在這時提交
            return _original(texts)

        self.embed.get_text_embedding_batch = block_during_embedding
        self.assertEqual(doc_id, self.write_tag(store, suppressed="0", blacklisted="0"))

        metadata = json.loads(self.insert_params()[1])
        self.assertEqual(("1", "1"), (metadata["suppressed"], metadata["blacklisted"]))
        self.assertEqual(("1", "1"), (json.loads(metadata["_node_content"])["metadata"]["suppressed"],
                                      json.loads(metadata["_node_content"])["metadata"]["blacklisted"]))
        self.assertEqual(["embed", "begin(commit=True)", "SELECT", "DELETE", "INSERT", "commit"],
                         self.events[self.events.index("embed"):])
        [(lock_sql, lock_params)] = self.statements("SELECT")
        self.assertTrue(lock_sql.endswith("FOR UPDATE"), "讀旗標那句要鎖住舊列，改旗標的 UPDATE 才不會插在中間")
        self.assertIn("FROM data_discord_member_profiles_index WHERE", lock_sql)
        self.assertEqual((doc_id, doc_id, doc_id), lock_params)

    def test_new_tag_keeps_the_given_flags(self):
        store = self.store()
        self.write_tag(store, suppressed="0", blacklisted="0")
        metadata = json.loads(self.insert_params()[1])
        self.assertEqual(("0", "0"), (metadata["suppressed"], metadata["blacklisted"]))

    def test_table_is_created_once_before_the_first_write(self):
        store = self.store()
        self.write_preference(store)
        self.write_preference(store)
        self.assertEqual(1, self.events.count("create_table(0)"))
        self.assertEqual(1, self.events.count("schema"))
        self.assertLess(self.events.index("schema"), self.events.index("embed"))


if __name__ == "__main__":
    unittest.main()
