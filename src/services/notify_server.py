"""
輕量 HTTP 通知伺服器

接收 Scraper 的 webhook 通知，觸發 Discord Bot 的對應處理；同一個 port 也掛 Hermes 用的模型端點。
用 aiohttp.web 在背景執行，預設 port 5000。

endpoint：
- GET  /health             — 健康檢查
- POST /notify/{source}    — 通用通知入口（bahamut / ptt / fb / ...）
  有設共用密鑰（環境變數 NOTIFY_SHARED_SECRET）時，要帶 header X-Notify-Secret，不符回 401；沒設就不驗、啟動時警告一次。
- GET  /v1/models、POST /v1/chat/completions — Hermes 的模型端點（`services.llm_proxy`），只認 Bearer HERMES_API_KEY；
  沒設金鑰就不掛。兩組端點各驗各的鑰匙，互不通用。
"""
import asyncio
import hmac
import logging
from functools import partial
from aiohttp import web
from typing import Callable, Coroutine, Dict, Optional

from utils.logger_config import get_article_monitor_logger
from utils.utils import ChannelConfig
from utils.background_tasks import spawn
from services.llm_proxy import LlmProxy
from sys_settings.hermes_settings import HermesSettings
from sys_settings.notify_settings import NotifyServerSettings

logger = get_article_monitor_logger()

NOTIFY_SERVER_PORT = 5000

# 共用「拉最近並發送」來源註冊表（宣告式；同形狀來源收斂成單一 _process_relay）。
# 巴哈刻意不在此表（單篇/批次＋forum slot/edit 是真特例，維持自有 _process_bahamut）。
_RELAY_SOURCES: Dict[str, dict] = {
    "fb": {
        "config_key": "article_monitor_channel_id",
        "module": "services.relay.fb_monitor", "cls": "FBMonitor",
        "method": "check_and_send_fb_posts",
    },
    "article": {
        "config_key": "article_monitor_channel_id",
        "module": "services.relay.article_monitor", "cls": "ArticleMonitor",
        "method": "check_and_send_new_articles",
    },
    "it_article": {
        "config_key": "hardware_news_channel_id",
        "module": "services.relay.it_article_monitor", "cls": "ItArticleMonitor",
        "method": "check_and_send_new", "seed": "ensure_seeded",
    },
}


#: 爬蟲打通知時帶密鑰的 header
SECRET_HEADER = "X-Notify-Secret"


class NotifyServer:
    """輕量 HTTP 通知伺服器。"""

    def __init__(self, bot, settings: Optional[NotifyServerSettings] = None, hermes_settings: Optional[HermesSettings] = None):
        self.bot = bot
        self.settings = settings or NotifyServerSettings()
        self.hermes_settings = hermes_settings or HermesSettings()
        self._runner: Optional[web.AppRunner] = None
        # 本文上限照模型端點的需要放大（aiohttp 預設 1 MiB，長 context 的對話會超過）；通知的本文本來就很小
        self._app = web.Application(client_max_size=self.hermes_settings.proxy_max_body_bytes)
        # 來源 → 處理函式 的分派表
        self._handlers: Dict[str, Callable[..., Coroutine]] = {
            "bahamut": self._process_bahamut,
            # fb / article / it_article 共用 _process_relay（宣告式註冊表）
            **{src: partial(self._process_relay, src) for src in _RELAY_SOURCES},
        }
        # 來源 → 是否正在處理中（防止重複執行）
        self._processing: Dict[str, bool] = {}
        self._setup_routes()

    def _setup_routes(self):
        self._app.router.add_get("/health", self._handle_health)
        self._app.router.add_post("/notify/{source}", self._handle_notify)
        # 模型端點只在有金鑰時掛：它會占用顯示卡，不能沒驗證就開
        self.model_endpoint_enabled = bool(self.hermes_settings.api_key)
        if self.model_endpoint_enabled:
            LlmProxy(self.hermes_settings).add_routes(self._app)

    async def start(self, port: int = NOTIFY_SERVER_PORT) -> None:
        """啟動 HTTP 伺服器。"""
        # handler_cancellation：對方斷線就取消處理函式。模型端點的請求會拿著 GPU 閘門等後端寫完，
        # 不取消的話，斷線後那一整段生成還是會跑完、鎖也一直拿著；通知的處理本來就 spawn 到背景，不受影響
        self._runner = web.AppRunner(self._app, handler_cancellation=True)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "0.0.0.0", port)
        await site.start()
        logger.info("Notify server 已啟動: port=%s, 支援來源=%s, 模型端點=%s",
                    port, list(self._handlers.keys()), "開" if self.model_endpoint_enabled else "關（沒設 HERMES_API_KEY）")
        self._warn_if_unprotected()

    def _warn_if_unprotected(self) -> None:
        if not self.settings.shared_secret:
            logger.warning("Notify server 沒設共用密鑰（NOTIFY_SHARED_SECRET）：內網裡任何程式都能觸發通知")

    def _authorized(self, request: web.Request) -> bool:
        """有設密鑰才驗；比對用常數時間，不讓比對時間洩漏前幾個字元對不對。"""
        secret = self.settings.shared_secret
        if not secret:
            return True
        return hmac.compare_digest(request.headers.get(SECRET_HEADER, ""), secret)

    async def stop(self) -> None:
        if self._runner:
            await self._runner.cleanup()
            logger.info("Notify server 已停止")

    # ── Endpoints ──

    async def _handle_health(self, request: web.Request) -> web.Response:
        return web.json_response({"status": "ok", "sources": list(self._handlers.keys())})

    async def _handle_notify(self, request: web.Request) -> web.Response:
        """通用通知入口：依 path parameter {source} 分派到對應處理函式。"""
        source = request.match_info.get("source", "")

        if not self._authorized(request):
            logger.warning("拒絕通知：密鑰不符 source=%s remote=%s", source, request.remote)
            return web.json_response({"status": "error", "message": "密鑰不符"}, status=401)

        if source not in self._handlers:
            return web.json_response(
                {"status": "error", "message": f"未知的通知來源: {source}"},
                status=404,
            )

        try:
            try:
                payload = await request.json()
            except Exception:
                payload = {}

            logger.info("收到通知: source=%s payload=%s", source, payload)

            # 檢查是否已在處理中
            if self._processing.get(source):
                logger.info("通知跳過：source=%s 已在處理中", source)
                return web.json_response({"status": "skipped", "source": source, "reason": "already processing"})

            # 在背景排程處理，不阻塞 HTTP 回應
            spawn(self._guarded_process(source, payload), name=f"通知處理 {source}")

            return web.json_response({"status": "accepted", "source": source})

        except Exception as e:
            logger.error("處理通知失敗: source=%s err=%s", source, e, exc_info=True)
            return web.json_response({"status": "error", "message": str(e)}, status=500)

    async def _guarded_process(self, source: str, payload: Dict) -> None:
        """加鎖的背景處理：同一來源同時只能有一個在跑。"""
        self._processing[source] = True
        try:
            await self._handlers[source](payload)
        finally:
            self._processing[source] = False

    # ── 來源處理函式 ──

    async def _process_bahamut(self, payload: Dict) -> None:
        """巴哈通知：從 Scraper API 拉最新資料，逐一發文/更新。
        payload 帶 post_id 時只處理單篇，不帶則批次處理最近 3 天。
        """
        try:
            from services.relay.bahamut_monitor import BahamutMonitor

            board_id = payload.get("board_id", "74934")
            post_id = payload.get("post_id")
            config = ChannelConfig.load_config(caller="notify_server")
            forum_channel_id = config.get("forum_article_channel_id")
            if not forum_channel_id:
                logger.error("巴哈通知處理失敗：config.json 未設定 forum_article_channel_id")
                return

            monitor = BahamutMonitor(self.bot)

            if post_id:
                # 單篇模式
                thread_data = await monitor.fetch_single_thread(board_id, post_id)
                if not thread_data:
                    logger.info("巴哈單篇通知：找不到 post_id=%s", post_id)
                    return
                result = await monitor.send_bahamut_thread_to_forum(forum_channel_id, thread_data)
                logger.info("巴哈單篇通知處理完成: post_id=%s result=%s", post_id, "ok" if result else "skip/fail")
                return

            # 批次模式：每篇文章各自背景處理，不互相阻塞
            threads = await monitor.fetch_recent_threads(days=3, limit=50, board_id=board_id)

            if not threads:
                logger.info("巴哈通知處理：沒有新的討論串")
                return

            logger.info("巴哈通知：開始背景處理 %s 個討論串", len(threads))
            for thread_data in threads:
                spawn(self._process_single_bahamut(
                    monitor, forum_channel_id, thread_data, board_id,
                ), name=f"巴哈通知處理 {board_id}")

        except Exception as e:
            logger.error("巴哈通知背景處理失敗: %s", e, exc_info=True)

    async def _process_relay(self, source: str, payload: Dict) -> None:
        """共用「拉最近並發送」處理：fb / article / it_article（依 _RELAY_SOURCES 註冊表）。

        同形狀＝讀 config 某 channel key → 建 monitor → 呼叫其「拉最近並發送」方法。
        it_article 多一個首次 seed 步驟（spec['seed']）；其餘來源無此步。
        """
        try:
            spec = _RELAY_SOURCES[source]
            config = ChannelConfig.load_config(caller="notify_server")
            channel_id = config.get(spec["config_key"])
            if not channel_id:
                logger.error("%s 通知處理失敗：config.json 未設定 %s", source, spec["config_key"])
                return

            module = __import__(spec["module"], fromlist=[spec["cls"]])
            monitor = getattr(module, spec["cls"])(self.bot)

            # 選配首次 seed（it_article：>3 天舊文標記已發、3 天內保留）
            seed_method = spec.get("seed")
            if seed_method:
                try:
                    seeded = await getattr(monitor, seed_method)()
                    if seeded is not None and seeded >= 0:
                        logger.info("%s 首次 seed：%s 篇舊文標記已發", source, seeded)
                except Exception as e:
                    logger.warning("%s seed 失敗（續發新文）: %s", source, e)

            await getattr(monitor, spec["method"])(channel_ids=[channel_id])
            logger.info("%s 通知處理完成", source)

        except Exception as e:
            logger.error("%s 通知背景處理失敗: %s", source, e, exc_info=True)

    async def _process_single_bahamut(self, monitor, forum_channel_id: int, thread_data: Dict, board_id: str) -> None:
        """背景處理單篇巴哈討論串。每篇獨立 task，由 snA 鎖保護不重複。"""
        post_id = thread_data.get("post_id", "?")
        try:
            result = await monitor.send_bahamut_thread_to_forum(forum_channel_id, thread_data)
            if result:
                logger.info("巴哈背景處理完成: post_id=%s", post_id)
        except Exception as e:
            logger.error("巴哈背景處理失敗: post_id=%s err=%s", post_id, e)
