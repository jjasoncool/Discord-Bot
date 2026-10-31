"""模型後端壞掉時的自癒與通知：`llm/client/lemonade_admin.py` 的 `LemonadeAdmin.heal`／`restart`／`verify`／
`replaced_since_give_up`／`admin_for`、`http_client` 的 `is_backend_fault`、`backend_message` 與薄迴圈叫 admin 重開的規則；
通知經 `utils/owner_alerts.py` 交給介面層。

守的底線：
  - 5xx 的內容帶後端壞掉的訊號（ErrorDeviceLost、decode() failed、vk::、CUDA error）：重開那顆模型一次再重送原請求，
    sync 與 async 都一樣；看不懂的 5xx 照一般重試、不重開
  - 重開＝先 unload（帶 model_name）再 load（save_options=False、沿用原本的選項）：只送 load 對還活著的模型是空操作；
    模型已經不在（unload 404）照樣載；其他 unload 錯誤算重開失敗
  - 救回來＝行程換了而且真的算得出來：重開後 pid 沒換、或最小請求還是失敗，都算還是壞——不通知「已恢復」、不解除警報、回 False；
    驗證的類型照 health，查不到就用呼叫端交的請求種類，都不知道也不算救回
  - 只有開了自癒的行程（bot，介面層 `allow_heal(True)`）才重開；重開中別人進來不再重開，冷卻從重開結束算
  - 第 3 次重開失敗也放棄；失敗原因帶後端講的那句話；群主按重新偵測（reset_cache）時正在跑的那次做完不把放棄寫回去
  - `release` 只放指定的模型；`check` 單獨驗一顆（類型照 health、沒有就照上次自癒記下的）
  - 重開不看還剩幾次重試：不重試的呼叫端（拿著 GPU 閘門的 embedding、替 Hermes 轉送的 raw 與串流）後端壞了照樣重開，
    只是重開完不重送、照原錯誤丟出；重開等多久照客戶端的 heal_load_timeout（拿著閘門時是短的那個）
  - 每個模型 60 秒冷卻；一小時最多 3 次，第 3 次重開還是壞、或用完之後又壞，就放棄：記一次 ERROR、通知一次；
    放棄後不再自動重開（過了一小時也一樣），直到 reset_cache（群主按重新偵測）
  - 放棄中的模型行程換了（重啟 Lemonade、手動重載、被卸載）會被 `replaced_since_give_up` 找出來、同一個行程只報一次；
    沒有放棄中的模型不打 health
  - 重開失敗、還是壞、放棄經 `owner_alerts.emit` 交給介面層（私訊＋重新偵測按鈕）、救回 `inform` 一行；接的人出錯不影響原本的請求
  - 重開是後端專屬的事：只有 Lemonade 有 admin（`admin_for`），沒有 admin 的後端（Ollama）遇到同樣的 5xx 只照一般重試收尾
  - 給人看的原因是後端自己講的那句話（`backend_message` 取最裡層的 message），不是只有「HTTP 500」
  - 四種結果各一行、帶模型與原因

hermetic：假的 HTTP 回應、假的重開與 health；不碰網路。

執行：
    cd src && python -m unittest test.test_lemonade_heal -v
"""

import asyncio
import contextlib
import itertools
import os
import sys
import threading
import time
import unittest
from types import SimpleNamespace
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from llm.client import http_client, lemonade_admin  # noqa: E402
from llm.client.http_client import (  # noqa: E402
    LlmAPIError,
    LlmConnectionError,
    LlmHttpClient,
    backend_looks_broken,
    backend_message,
)
from llm.client.backend_admin import admin_for  # noqa: E402
from llm.client.lemonade_admin import LemonadeAdmin  # noqa: E402
from utils import owner_alerts  # noqa: E402

BROKEN = '{"error":{"message":"decode() failed: vk::Queue::submit: ErrorDeviceLost","type":"server_error"}}'
# Lemonade 實際的樣子：llama-server 的錯誤包在 details.response 裡
WRAPPED = ('{"error":{"code":500,"details":{"backend":"llama-server","response":{"error":{"code":500,'
           '"message":"decode() failed: vk::CommandBuffer::end: ErrorDeviceLost","type":"server_error"}}},'
           '"message":"outer","status_code":500,"type":"server_error"}}')


def resp(status, text="", payload=None):
    return SimpleNamespace(is_success=status < 400, status_code=status, text=text, json=lambda: payload or {})


def fake_admin(heal_load_timeout=120.0, kind="embedding"):
    """重開、health、驗證都換成假的：每查一次 health 行程換一個新 pid（重開有效），驗證預設通過。"""
    admin = LemonadeAdmin("http://backend.test", heal_load_timeout=heal_load_timeout)
    admin.restart = mock.Mock()
    pids = itertools.count(100)
    admin.backend = mock.Mock(side_effect=lambda model: {"pid": next(pids), "type": kind})
    admin.verify = mock.Mock()
    return admin


def enable_heal(test: unittest.TestCase) -> None:
    lemonade_admin.allow_heal(True)
    test.addCleanup(lemonade_admin.allow_heal, False)


class HealTestBase(unittest.TestCase):
    def setUp(self):
        lemonade_admin.reset_cache()
        enable_heal(self)
        owner_alerts.reset()
        self.events = []
        owner_alerts.set_listener(self.events.append)
        self.addCleanup(owner_alerts.reset)
        self.addCleanup(lemonade_admin.reset_cache)
        self.now = 1000.0
        for patcher in (mock.patch.object(http_client, "_backoff_delay", lambda attempt: 0),   # 不真的睡
                        mock.patch.object(lemonade_admin, "_clock", lambda: self.now)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def outcomes(self):
        """通知的種類：救回是一行通知、放棄要人介入、重開失敗與還是壞先警告（看文字分）。"""
        kinds = []
        for e in self.events:
            if e.severity == "info":
                kinds.append("healed")
            elif e.severity == "error":
                kinds.append("gave_up")
            else:
                kinds.append("still_broken" if "還是壞" in e.text else "failed")
        return kinds

    def client(self, *responses, heal_load_timeout=120.0, **kwargs):
        admin = fake_admin(heal_load_timeout)
        client = LlmHttpClient(base_url="http://backend.test", timeout=1.0, admin=admin, **kwargs)
        client._sync = SimpleNamespace(post=mock.Mock(side_effect=list(responses)))
        client._async = SimpleNamespace(post=mock.AsyncMock(side_effect=list(responses)))
        return client


class HealOnBackendErrorTests(HealTestBase):
    def test_signatures(self):
        self.assertTrue(backend_looks_broken(LlmAPIError("HTTP 500", status=500, detail=BROKEN)))
        self.assertTrue(backend_looks_broken(LlmAPIError("HTTP 503", status=503, detail="CUDA error: device-side assert")))
        self.assertFalse(backend_looks_broken(LlmAPIError("HTTP 500", status=500, detail="boom")))
        self.assertFalse(backend_looks_broken(LlmAPIError("HTTP 400", status=400, detail=BROKEN)))

    def test_backend_message_takes_the_innermost_message(self):
        self.assertEqual(backend_message(LlmAPIError("HTTP 500", status=500, detail=WRAPPED)),
                         "decode() failed: vk::CommandBuffer::end: ErrorDeviceLost")
        self.assertEqual(backend_message(LlmAPIError("HTTP 500", status=500, detail="plain text")), "plain text")
        self.assertEqual(backend_message(LlmAPIError("HTTP 500", status=500)), "")
        self.assertEqual(backend_message(RuntimeError("x")), "")

    def test_sync_device_error_restarts_the_model_once_and_retries(self):
        client = self.client(resp(500, WRAPPED), resp(200, payload={"data": [{"embedding": [0.1]}]}))
        self.assertEqual(client.embedding(model="emb", input="x"), [[0.1]])
        client.admin.restart.assert_called_once()
        self.assertEqual(client.admin.restart.call_args.kwargs["model"], "emb")
        client.admin.verify.assert_called_once_with(model="emb", kind="embedding")
        self.assertEqual(self.outcomes(), ["healed"])
        self.assertIn("ErrorDeviceLost", self.events[0].text)
        self.assertNotIn('{"error"', self.events[0].text, "原因是後端講的那句話，不是整包 JSON")
        self.assertIn("100→101", self.events[0].text, "救回的通知帶行程換了")
        self.assertEqual(self.events[0].key, "emb")

    def test_async_path_does_the_same(self):
        client = self.client(resp(500, BROKEN), resp(200, payload={"data": [{"embedding": [0.2]}]}))
        self.assertEqual(asyncio.run(client.aembedding(model="emb", input="x")), [[0.2]])
        client.admin.restart.assert_called_once()
        self.assertEqual(self.outcomes(), ["healed"])

    def test_unknown_5xx_is_retried_but_never_restarts(self):
        client = self.client(resp(500, "boom"), resp(500, "boom"), resp(500, "boom"))
        with self.assertRaises(LlmAPIError):
            client.embedding(model="emb", input="x")
        client.admin.restart.assert_not_called()
        self.assertEqual(self.events, [])

    def test_cooldown_allows_one_restart_per_minute(self):
        client = self.client(resp(500, BROKEN), resp(500, BROKEN), resp(500, BROKEN))
        with self.assertRaises(LlmAPIError):
            client.embedding(model="emb", input="x")
        client.admin.restart.assert_called_once()        # 第二次 5xx 在冷卻內：不再重開，照一般重試收尾

    def test_still_broken_after_restart_is_not_reported_as_recovered(self):
        """重開了、行程也換了，但真的算還是壞：不能說恢復、不能解除警報。"""
        admin = fake_admin()
        admin.verify.side_effect = LlmAPIError("HTTP 500", status=500, detail=WRAPPED)
        owner_alerts.emit(lemonade_admin.ALERT_KIND, "emb", "之前的警報")
        self.events.clear()
        self.assertFalse(admin.heal("emb", reason="r"))
        self.assertEqual(self.outcomes(), [], "同一把一小時內已經送過，還是壞（警告）不再送")
        self.assertEqual([a.key for a in owner_alerts.active()], ["emb"], "警報還掛著")
        self.assertIn("還是壞", owner_alerts.active()[0].text)
        self.assertIn("ErrorDeviceLost", owner_alerts.active()[0].text)

    def test_still_broken_is_reported_when_nothing_was_pending(self):
        admin = fake_admin()
        admin.verify.side_effect = LlmAPIError("HTTP 500", status=500, detail=BROKEN)
        with self.assertLogs("llm.client.lemonade_admin", "WARNING"):
            self.assertFalse(admin.heal("emb", reason="r"))
        self.assertEqual(self.outcomes(), ["still_broken"])
        self.assertIn("第 1／3 次", self.events[0].text)

    def test_same_pid_after_restart_counts_as_not_restarted(self):
        admin = fake_admin()
        admin.backend = mock.Mock(return_value={"pid": 7, "type": "embedding"})
        with self.assertLogs("llm.client.lemonade_admin", "WARNING"):
            self.assertFalse(admin.heal("emb", reason="r"))
        admin.verify.assert_not_called()
        self.assertEqual(self.outcomes(), ["still_broken"])
        self.assertIn("行程沒換", self.events[0].text)

    def test_unknown_pids_still_need_a_real_request(self):
        """health 查不到：比不了 pid，就靠真的算一次；類型用呼叫端交的請求種類。"""
        admin = fake_admin()
        admin.backend = mock.Mock(return_value=None)
        self.assertTrue(admin.heal("emb", reason="r", kind="embedding"))
        admin.verify.assert_called_once_with(model="emb", kind="embedding")

    def test_unknown_type_is_never_reported_as_recovered(self):
        """health 查不到、呼叫端也沒說是哪一類：沒辦法真的算，就不能說救回來。"""
        admin = LemonadeAdmin("http://backend.test")
        admin.restart = mock.Mock()
        admin.backend = mock.Mock(return_value=None)
        admin._http = SimpleNamespace(post=mock.Mock(), close=mock.Mock())
        with self.assertLogs("llm.client.lemonade_admin", "WARNING"):
            self.assertFalse(admin.heal("emb", reason="r"))
        admin._http.post.assert_not_called()
        self.assertEqual(self.outcomes(), ["still_broken"])
        self.assertNotIn("恢復", self.events[0].text)

    def test_heal_is_off_unless_this_process_turned_it_on(self):
        """只有 bot（有人收通知、有重新偵測）自癒；search-mcp、批次這些行程碰到同樣的錯只照原錯誤收尾。"""
        lemonade_admin.allow_heal(False)
        client = self.client(resp(500, BROKEN), resp(200, payload={"data": [{"embedding": [0.1]}]}))
        self.assertEqual(client.embedding(model="emb", input="x"), [[0.1]], "照一般重試收尾")
        client.admin.restart.assert_not_called()
        self.assertEqual(self.events, [])

    def test_kind_comes_from_the_failed_request(self):
        client = self.client(resp(500, BROKEN), resp(200, payload={"choices": [{}]}))
        client.admin.backend = mock.Mock(return_value=None)
        asyncio.run(client.chat_completion(model="chat", messages=[]))
        client.admin.verify.assert_called_once_with(model="chat", kind="llm")

    def test_a_restart_in_progress_is_not_started_again(self):
        """重開（卸載、載入大模型、驗證）可能比冷卻還久：重開中別的請求進來，不能再重開一次。"""
        admin = fake_admin()
        started, release = threading.Event(), threading.Event()

        def slow_restart(**kwargs):
            started.set()
            release.wait(5)
        admin.restart.side_effect = slow_restart
        first = threading.Thread(target=admin.heal, args=("emb", "r"))
        first.start()
        self.assertTrue(started.wait(2))
        self.now += 120                                    # 比冷卻還久
        self.assertFalse(admin.heal("emb", reason="r"), "重開中不再重開")
        release.set()
        first.join(5)
        self.assertEqual(admin.restart.call_count, 1)

    def test_cooldown_counts_from_the_end_of_a_restart(self):
        admin = fake_admin()
        admin.verify.side_effect = LlmAPIError("HTTP 500", status=500, detail=BROKEN)

        def slow_restart(**kwargs):
            self.now += 100                                # 這次重開花了 100 秒
        admin.restart.side_effect = slow_restart
        with self.assertLogs("llm.client.lemonade_admin", "WARNING"):
            admin.heal("emb", reason="r")
            self.now += 30
            self.assertFalse(admin.heal("emb", reason="r"), "重開結束才 30 秒，還在冷卻")
            self.now += 31
            admin.heal("emb", reason="r")
        self.assertEqual(admin.restart.call_count, 2)

    def test_third_failed_restart_attempt_gives_up_too(self):
        admin = fake_admin()
        admin.restart.side_effect = LlmAPIError("HTTP 500", status=500, detail=WRAPPED)
        with self.assertLogs("llm.client.lemonade_admin", "WARNING"):
            for _ in range(3):
                self.assertFalse(admin.heal("emb", reason="r"))
                self.now += 61
        self.assertEqual(self.outcomes(), ["failed", "gave_up"])
        self.assertIn("vk::CommandBuffer::end: ErrorDeviceLost", self.events[0].text, "失敗原因帶後端講的那句話")
        self.assertIn(("http://backend.test", "emb"), lemonade_admin._GAVE_UP)

    def test_give_up_after_a_failed_load_records_the_process_now(self):
        """第 3 次 unload 成功、load 失敗：舊行程已被 bot 自己結束，放棄要記現在的樣子（不在了），
        不然下一分鐘會被當成「有人重開過」。"""
        admin = fake_admin()
        admin.restart.side_effect = LlmAPIError("HTTP 500", status=500, detail="load failed")
        admin.backend = mock.Mock(side_effect=lambda model: None if admin.restart.call_count >= 3 else {"pid": 22672})
        with self.assertLogs("llm.client.lemonade_admin", "WARNING"):
            for _ in range(3):
                admin.heal("emb", reason="r")
                self.now += 61
        self.assertEqual(lemonade_admin._GAVE_UP[(admin._host, "emb")][1], None)

    def test_releasing_one_model_does_not_cancel_another_models_give_up(self):
        """自動重測放掉了聊天模型，向量模型剛好在跑第 3 次重開：它做完照樣放棄、通知。"""
        admin = fake_admin()
        admin.verify.side_effect = LlmAPIError("HTTP 500", status=500, detail=BROKEN)
        with self.assertLogs("llm.client.lemonade_admin", "WARNING"):
            for _ in range(2):
                admin.heal("emb", reason="r")
                self.now += 61
            lemonade_admin._HEAL_HISTORY[(admin._host, "chat")] = [self.now]     # 聊天模型也有紀錄可放
            admin.restart.side_effect = lambda **kwargs: lemonade_admin.release(["chat"])
            admin.heal("emb", reason="r")
        self.assertIn((admin._host, "emb"), lemonade_admin._GAVE_UP)
        self.assertNotIn((admin._host, "chat"), lemonade_admin._HEAL_HISTORY)
        self.assertEqual(self.outcomes()[-1], "gave_up")

    def test_releasing_a_model_mid_restart_does_not_write_back(self):
        admin = fake_admin()
        admin.verify.side_effect = LlmAPIError("HTTP 500", status=500, detail=BROKEN)
        with self.assertLogs("llm.client.lemonade_admin", "WARNING"):
            for _ in range(2):
                admin.heal("emb", reason="r")
                self.now += 61
            admin.restart.side_effect = lambda **kwargs: lemonade_admin.release(["emb"])
            admin.heal("emb", reason="r")
        self.assertNotIn((admin._host, "emb"), lemonade_admin._GAVE_UP)

    def test_retest_during_a_running_restart_is_not_undone(self):
        """群主按重新偵測（reset_cache）時剛好有一次第 3 次重開在跑：它做完不能把放棄寫回去、抵掉這次重測。"""
        admin = fake_admin()
        admin.verify.side_effect = LlmAPIError("HTTP 500", status=500, detail=BROKEN)
        with self.assertLogs("llm.client.lemonade_admin", "WARNING"):
            for _ in range(2):
                admin.heal("emb", reason="r")
                self.now += 61
            admin.restart.side_effect = lambda **kwargs: lemonade_admin.reset_cache()
            admin.heal("emb", reason="r")
        self.assertEqual(lemonade_admin._GAVE_UP, {})
        self.assertNotIn(("http://backend.test", "emb"), lemonade_admin._LAST_HEAL, "冷卻也不寫回去")

    def test_third_failed_restart_gives_up_for_good(self):
        admin = fake_admin()
        admin.verify.side_effect = LlmAPIError("HTTP 500", status=500, detail=BROKEN)
        results = []
        with self.assertLogs("llm.client.lemonade_admin", "WARNING") as logs:
            for _ in range(3):
                results.append(admin.heal("emb", reason="r"))
                self.now += 61
        self.assertEqual(results, [False, False, False])
        self.assertEqual(self.outcomes(), ["still_broken", "gave_up"], "第三次還是壞就放棄；放棄（要人介入）不被去重吃掉")
        self.assertEqual(len([l for l in logs.output if "自癒放棄" in l]), 1)
        self.now += 7200                                   # 過了兩小時
        self.assertFalse(admin.heal("emb", reason="r"), "放棄後不再自動重開")
        self.assertEqual(admin.restart.call_count, 3)
        self.assertEqual(len(self.events), 2, "放棄後不再吵")
        lemonade_admin.reset_cache()                       # 群主按了重新偵測
        admin.verify.side_effect = None
        self.assertTrue(admin.heal("emb", reason="r"), "清掉紀錄後又救得了")
        self.assertEqual(owner_alerts.active(), [], "救回來的通知解除放棄的警報")

    def test_hourly_cap_gives_up_when_it_keeps_breaking(self):
        """一小時內重開三次都救回來了，又壞第四次：一直掉就是卡或驅動的問題，放棄。"""
        admin = fake_admin()
        results = []
        for _ in range(3):
            results.append(admin.heal("emb", reason="r"))
            self.now += 61
        with self.assertLogs("llm.client.lemonade_admin", "ERROR"):
            fourth = admin.heal("emb", reason="r")
        self.now += 61
        self.assertEqual(results, [True, True, True])
        self.assertFalse(fourth)
        self.assertFalse(admin.heal("emb", reason="r"))
        self.assertEqual(admin.restart.call_count, 3)
        self.assertEqual(self.outcomes(), ["healed", "healed", "healed", "gave_up"], "放棄只通知一次")
        self.assertIn("3 次", self.events[-1].text)
        self.assertEqual([a.key for a in owner_alerts.active()], ["emb"], "放棄的那把還掛著，等人按重新偵測")

    def test_failed_restart_reports_and_returns_false(self):
        admin = fake_admin()
        admin.restart.side_effect = LlmConnectionError("admin down")
        with self.assertLogs("llm.client.lemonade_admin", "WARNING"):
            self.assertFalse(admin.heal("emb", reason="r"))
        admin.verify.assert_not_called()
        self.assertEqual(self.outcomes(), ["failed"])
        self.assertIn("admin down", self.events[0].text)

    def test_no_retry_client_restarts_then_raises_the_original_error(self):
        client = self.client(resp(500, BROKEN), resp(200, payload={"data": [{"embedding": [0.1]}]}), max_retries=0)
        with self.assertRaises(LlmAPIError):
            client.embedding(model="emb", input="x")
        client.admin.restart.assert_called_once()
        self.assertEqual(client._sync.post.call_count, 1, "沒有重試額度：重開完不重送")
        self.assertEqual(self.outcomes(), ["healed"])

    def test_raw_forwarding_restarts_on_device_error_without_resending(self):
        client = self.client(resp(500, BROKEN), resp(200, payload={"choices": []}))
        with self.assertRaises(LlmAPIError):
            asyncio.run(client.chat_completion_raw({"model": "chat", "messages": []}))
        client.admin.restart.assert_called_once()
        self.assertEqual(client.admin.restart.call_args.kwargs["model"], "chat")
        self.assertEqual(client._async.post.await_count, 1)

    def test_stream_restarts_on_device_error(self):
        broken = SimpleNamespace(is_success=False, status_code=500, text=BROKEN, aread=mock.AsyncMock())

        @contextlib.asynccontextmanager
        async def stream(*args, **kwargs):
            yield broken

        client = self.client()
        client._async = SimpleNamespace(stream=stream)

        async def run():
            async with client.chat_completion_stream({"model": "chat", "messages": []}):
                pass

        with self.assertRaises(LlmAPIError):
            asyncio.run(run())
        client.admin.restart.assert_called_once()
        self.assertEqual(client.admin.restart.call_args.kwargs["model"], "chat")

    def test_restart_reuses_the_last_load_options(self):
        admin = fake_admin()
        admin.load = mock.Mock()
        admin.ensure_loaded(model="emb", options={"ctx_size": 4096, "llamacpp_args": "-sm none -mg 1"})
        self.assertTrue(admin.heal("emb", reason="r"))
        self.assertEqual(admin.restart.call_args.kwargs["recipe"], {"ctx_size": 4096, "llamacpp_args": "-sm none -mg 1"})

    def test_gated_embedding_client_restarts_with_its_short_load_timeout(self):
        from llm.client.embedding_client import SafeLLMEmbedding

        embedding = SafeLLMEmbedding(model_name="emb", base_url="http://backend.test", backend="lemonade",
                                     max_retries=0, load_timeout=45.0)
        self.assertEqual(embedding._http_client.admin._heal_load_timeout, 45.0)
        self.assertEqual(embedding._http_client._max_retries, 0)

    def test_backend_without_admin_never_restarts(self):
        client = LlmHttpClient(base_url="http://backend.test", timeout=1.0, max_retries=0)
        client._sync = SimpleNamespace(post=mock.Mock(side_effect=[resp(500, BROKEN)]))
        with self.assertRaises(LlmAPIError):
            client.embedding(model="emb", input="x")
        self.assertEqual(self.events, [], "沒有管理 API 的後端不重開")

    def test_only_lemonade_restarts(self):
        from llm.client.embedding_client import SafeLLMEmbedding
        from llm.client.ollama_admin import OllamaAdmin

        self.assertIsInstance(admin_for("lemonade", "http://backend.test"), LemonadeAdmin)
        self.assertIsInstance(admin_for("ollama", "http://backend.test"), OllamaAdmin)
        self.assertIsNone(admin_for("vllm", "http://backend.test"))
        self.assertIsNone(SafeLLMEmbedding(model_name="emb", base_url="http://backend.test", backend="vllm")._http_client.admin)
        # Ollama 有 admin（會卸載）但沒有重開 API：同樣的 5xx 不重開、照原錯誤丟
        client = LlmHttpClient(base_url="http://backend.test", timeout=1.0, max_retries=0, admin=OllamaAdmin("http://backend.test"))
        client._sync = SimpleNamespace(post=mock.Mock(side_effect=[resp(500, BROKEN)]))
        with self.assertRaises(LlmAPIError):
            client.embedding(model="emb", input="x")
        self.assertEqual(self.events, [])

    def test_envelope_is_only_unwrapped_through_the_admin(self):
        payload = {"error": {"type": "server_error", "message": "boom"}}
        with_admin = self.client(resp(200, payload=payload))
        with self.assertRaises(LlmAPIError) as caught:
            with_admin.embedding(model="emb", input="x")
        self.assertIn("envelope", str(caught.exception), "有 admin 才認得信封，錯誤要講出 upstream 的原文")
        plain = LlmHttpClient(base_url="http://backend.test", timeout=1.0)
        plain._sync = SimpleNamespace(post=mock.Mock(side_effect=[resp(200, payload={"data": [{"embedding": [0.3]}]})]))
        self.assertEqual(plain.embedding(model="emb", input="x"), [[0.3]])

    def test_listener_errors_do_not_break_the_request(self):
        owner_alerts.set_listener(lambda alert: (_ for _ in ()).throw(RuntimeError("dm broke")))
        client = self.client(resp(500, BROKEN), resp(200, payload={"data": [{"embedding": [0.1]}]}))
        with self.assertLogs("utils.owner_alerts", "WARNING"):
            self.assertEqual(client.embedding(model="emb", input="x"), [[0.1]])


class RestartAndVerifyTests(unittest.TestCase):
    """重開與驗證打的是哪些端點（假的 HTTP，不碰網路）。"""

    def setUp(self):
        self.admin = LemonadeAdmin("http://backend.test", heal_load_timeout=33.0)
        self.posts = []
        self.replies = []

        def post(url, json=None, timeout=None):
            self.posts.append((url.removeprefix("http://backend.test"), json, timeout))
            return self.replies.pop(0) if self.replies else resp(200, payload={})
        self.admin._http = SimpleNamespace(post=post, get=mock.Mock(), close=mock.Mock())

    def test_restart_unloads_that_model_then_loads_without_saving(self):
        self.admin.restart(model="emb", recipe={"ctx_size": 4096})
        self.assertEqual([p[0] for p in self.posts], ["/api/v1/unload", "/api/v1/load"])
        self.assertEqual(self.posts[0][1], {"model_name": "emb"}, "unload 一定帶 model_name，空的會卸載全部")
        self.assertEqual(self.posts[1][1], {"model_name": "emb", "ctx_size": 4096, "save_options": False})
        self.assertEqual([p[2] for p in self.posts], [33.0, 33.0])

    def test_restart_loads_even_if_the_model_was_already_gone(self):
        self.replies = [resp(404, "Model not loaded")]
        self.admin.restart(model="emb", recipe={})
        self.assertEqual([p[0] for p in self.posts], ["/api/v1/unload", "/api/v1/load"])

    def test_restart_stops_on_other_unload_errors(self):
        self.replies = [resp(500, "boom")]
        with self.assertRaises(LlmAPIError):
            self.admin.restart(model="emb", recipe={})
        self.assertEqual([p[0] for p in self.posts], ["/api/v1/unload"])

    def test_verify_sends_the_smallest_request_for_each_type(self):
        self.replies = [resp(200, payload={"data": [{"embedding": [0.1]}]}),
                        resp(200, payload={"choices": [{"message": {"content": "p"}}]}),
                        resp(200, payload={"results": [{"index": 0, "relevance_score": 1.0}]})]
        self.admin.verify(model="emb", kind="embedding")
        self.admin.verify(model="chat", kind="llm")
        self.admin.verify(model="rr", kind="reranking")
        self.assertEqual([p[0] for p in self.posts], ["/v1/embeddings", "/v1/chat/completions", "/v1/rerank"])
        self.assertEqual(self.posts[1][1]["max_tokens"], 1)

    def test_verify_fails_on_errors_envelopes_and_empty_replies(self):
        self.replies = [resp(500, WRAPPED)]
        with self.assertRaises(LlmAPIError):
            self.admin.verify(model="emb", kind="embedding")
        self.replies = [resp(200, payload={"error": {"type": "server_error", "message": "boom"}})]
        with self.assertRaises(LlmAPIError):
            self.admin.verify(model="emb", kind="embedding")
        self.replies = [resp(200, payload={"data": []})]
        with self.assertRaises(LlmAPIError):
            self.admin.verify(model="emb", kind="embedding")

    def test_verify_refuses_types_it_does_not_know(self):
        for kind in ("tts", None):
            with self.assertRaises(LlmAPIError):
                self.admin.verify(model="x", kind=kind)
        self.assertEqual(self.posts, [], "不知道是哪一類就不送")

    def test_check_uses_the_health_type_then_the_remembered_kind(self):
        lemonade_admin.reset_cache()
        self.addCleanup(lemonade_admin.reset_cache)
        self.addCleanup(lemonade_admin._KINDS.pop, ("http://backend.test", "rr"), None)
        self.admin.backend = mock.Mock(return_value={"pid": 1, "type": "reranking"})
        self.replies = [resp(200, payload={"results": [{"index": 0}]})]
        self.admin.check("rr")
        self.assertEqual(self.posts[-1][0], "/v1/rerank")
        self.admin.backend = mock.Mock(return_value=None)       # 沒載入：照上次自癒記下的種類
        with self.assertRaises(LlmAPIError):
            self.admin.check("rr")
        lemonade_admin._KINDS[("http://backend.test", "rr")] = "reranking"
        self.replies = [resp(200, payload={"results": [{"index": 0}]})]
        self.admin.check("rr")
        self.assertEqual(self.posts[-1][0], "/v1/rerank")

    def test_backend_reads_the_health_entry(self):
        health = {"all_models_loaded": [{"model_name": "emb", "pid": 22672, "type": "embedding"}, {"pid": 1}]}
        self.admin._http.get = mock.Mock(return_value=resp(200, payload=health))
        self.assertEqual(self.admin.backend("emb")["pid"], 22672)
        self.assertIsNone(self.admin.backend("chat"))
        self.admin._http.get = mock.Mock(side_effect=lemonade_admin.httpx.ConnectError("down"))
        self.assertIsNone(self.admin.backend("emb"), "health 查不到就當不知道，不丟例外")


class ReplacedSinceGiveUpTests(HealTestBase):
    def health(self, **pids):
        return resp(200, payload={"all_models_loaded": [{"model_name": m, "pid": p, "type": "embedding"}
                                                        for m, p in pids.items()]})

    def gave_up_admin(self, pid):
        admin = fake_admin()
        admin.backend = mock.Mock(return_value={"pid": pid, "type": "embedding"})
        admin.restart = mock.Mock()
        admin.verify = mock.Mock(side_effect=LlmAPIError("HTTP 500", status=500, detail=BROKEN))
        with self.assertLogs("llm.client.lemonade_admin", "WARNING"):
            for _ in range(3):
                admin.heal("emb", reason="r")
                self.now += 61
        return admin

    def test_nothing_given_up_means_no_health_call(self):
        admin = LemonadeAdmin("http://backend.test")
        admin._http = SimpleNamespace(get=mock.Mock())
        self.assertEqual(admin.replaced_since_give_up(), [])
        admin._http.get.assert_not_called()

    def test_finds_models_whose_process_changed_or_vanished(self):
        admin = self.gave_up_admin(pid=None)       # 每次 health 都是同一個 pid 會被當成沒重開；先用 None 記放棄
        self.assertIn(("http://backend.test", "emb"), lemonade_admin._GAVE_UP)
        admin._http = SimpleNamespace(get=mock.Mock(return_value=self.health(emb=500)))
        self.assertEqual(admin.replaced_since_give_up(), [], "放棄時查不到行程：這次查到的當基準")
        self.assertEqual(admin.replaced_since_give_up(), [], "同一個行程：還是那個壞的")
        admin._http.get.return_value = self.health(emb=501)
        self.assertEqual(admin.replaced_since_give_up(), ["emb"], "行程換了（重啟 Lemonade）")
        self.assertEqual(admin.replaced_since_give_up(), [], "同一個新行程只報一次")
        admin._http.get.return_value = self.health(chat=9)
        self.assertEqual(admin.replaced_since_give_up(), ["emb"], "模型不在了也算換了")
        admin._http.get.side_effect = lemonade_admin.httpx.ConnectError("down")
        self.assertEqual(admin.replaced_since_give_up(), [], "health 查不到：下一輪再看")
        lemonade_admin.reset_cache()
        admin._http.get = mock.Mock()
        self.assertEqual(admin.replaced_since_give_up(), [])
        admin._http.get.assert_not_called()

    def test_recorded_pid_is_compared(self):
        admin = self.gave_up_admin(pid=42)
        self.assertEqual(lemonade_admin._GAVE_UP[("http://backend.test", "emb")][1], 42)
        admin._http = SimpleNamespace(get=mock.Mock(return_value=self.health(emb=42)))
        self.assertEqual(admin.replaced_since_give_up(), [])
        admin._http.get.return_value = self.health(emb=43)
        self.assertEqual(admin.replaced_since_give_up(), ["emb"])

    def test_release_only_frees_the_given_models(self):
        admin = self.gave_up_admin(pid=42)
        other = (admin._host, "chat")
        lemonade_admin._GAVE_UP[other] = (0.0, 7)
        lemonade_admin.release(["emb"])
        self.assertNotIn((admin._host, "emb"), lemonade_admin._GAVE_UP)
        self.assertNotIn((admin._host, "emb"), lemonade_admin._HEAL_HISTORY)
        self.assertIn(other, lemonade_admin._GAVE_UP, "別顆的放棄照舊")


class OwnerNoticeTests(unittest.TestCase):
    def test_each_outcome_has_its_own_line(self):
        healed = lemonade_admin.heal_notice("healed", "emb", "ErrorDeviceLost", 1, (22672, 15000))
        still = lemonade_admin.heal_notice("still_broken", "emb", "ErrorDeviceLost", 2, (15000, 15100))
        gave_up = lemonade_admin.heal_notice("gave_up", "emb", "ErrorDeviceLost", 3)
        failed = lemonade_admin.heal_notice("failed", "emb", "admin down")
        self.assertIn("已重開", healed)
        self.assertIn("能算", healed)
        self.assertIn("22672→15000", healed)
        self.assertIn("第 1 次", healed)
        self.assertIn("還是壞", still)
        self.assertIn("第 2／3 次", still)
        self.assertNotIn("恢復", still, "還是壞的不能說恢復")
        self.assertIn("放棄", gave_up)
        self.assertIn("3 次", gave_up)
        self.assertIn("不再自動重開", gave_up)
        self.assertIn("重新偵測", gave_up, "告訴群主修好之後要按哪裡")
        self.assertIn("失敗", failed)
        for text in (healed, still, gave_up, failed):
            self.assertIn("emb", text)

    def test_status_and_reset_are_not_blocked_by_a_running_load(self):
        """載入模型要 30～180 秒；群主按「機器人狀態」或「重新偵測」時不能跟著等那把鎖。"""
        lemonade_admin.reset_cache()
        self.addCleanup(lemonade_admin.reset_cache)
        admin = LemonadeAdmin("http://backend.test")
        started, release = threading.Event(), threading.Event()

        def slow_load(**kwargs):
            started.set()
            release.wait(5)
        admin.load = slow_load
        loader = threading.Thread(target=admin.ensure_loaded, kwargs=dict(model="emb", options={"ctx_size": 1}))
        loader.start()
        self.assertTrue(started.wait(2))
        t0 = time.monotonic()
        summary = lemonade_admin.heal_summary()
        lemonade_admin.reset_cache()
        elapsed = time.monotonic() - t0
        release.set()
        loader.join(5)
        self.assertLess(elapsed, 1.0, "看狀態、清紀錄被載入中的模型擋住了")
        self.assertIn("沒有重開過", summary)

    def test_summary_tells_who_gave_up_and_how_many_restarts(self):
        lemonade_admin.reset_cache()
        enable_heal(self)
        owner_alerts.reset()
        self.addCleanup(lemonade_admin.reset_cache)
        self.addCleanup(owner_alerts.reset)
        self.assertIn("沒有重開過", lemonade_admin.heal_summary())
        admin = fake_admin()
        with mock.patch.object(lemonade_admin, "_HEAL_COOLDOWN_S", 0.0):
            admin.heal("emb", reason="r")
            self.assertIn("emb 這一小時重開 1 次", lemonade_admin.heal_summary())
            with self.assertLogs("llm.client.lemonade_admin", "ERROR"):
                for _ in range(3):
                    admin.heal("emb", reason="r")
        summary = lemonade_admin.heal_summary()
        self.assertIn("emb 已放棄自動重開", summary)
        self.assertNotIn("重開 3 次", summary, "放棄中就不再另外報次數")


if __name__ == "__main__":
    unittest.main()
