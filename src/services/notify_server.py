"""
輕量 HTTP 通知伺服器

接收 Scraper 的 webhook 通知，觸發 Discord Bot 的對應處理。
用 aiohttp.web 在背景執行，預設 port 5000。

endpoint：
- GET  /health             — 健康檢查
- POST /notify/{source}    — 通用通知入口（bahamut / ptt / fb / ...）
"""
import asyncio
import logging
from aiohttp import web
from typing import Callable, Coroutine, Dict, Optional

from utils.logger_config import get_article_monitor_logger
from utils.utils import ChannelConfig

logger = get_article_monitor_logger()

NOTIFY_SERVER_PORT = 5000


class NotifyServer:
    """輕量 HTTP 通知伺服器。"""

    def __init__(self, bot):
        self.bot = bot
        self._runner: Optional[web.AppRunner] = None
        self._app = web.Application()
        # 來源 → 處理函式 的分派表
        self._handlers: Dict[str, Callable[..., Coroutine]] = {
            "bahamut": self._process_bahamut,
        }
        # 來源 → 是否正在處理中（防止重複執行）
        self._processing: Dict[str, bool] = {}
        self._setup_routes()

    def _setup_routes(self):
        self._app.router.add_get("/health", self._handle_health)
        self._app.router.add_post("/notify/{source}", self._handle_notify)

    async def start(self, port: int = NOTIFY_SERVER_PORT) -> None:
        """啟動 HTTP 伺服器。"""
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "0.0.0.0", port)
        await site.start()
        logger.info("Notify server 已啟動: port=%s, 支援來源=%s", port, list(self._handlers.keys()))

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
            asyncio.create_task(self._guarded_process(source, payload))

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
            from services.bahamut_monitor import BahamutMonitor

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

            # 批次模式
            threads = await monitor.fetch_recent_threads(days=3, limit=50, board_id=board_id)

            if not threads:
                logger.info("巴哈通知處理：沒有新的討論串")
                return

            processed = 0
            for thread_data in threads:
                result = await monitor.send_bahamut_thread_to_forum(forum_channel_id, thread_data)
                if result:
                    processed += 1

            logger.info(
                "巴哈通知處理完成: board_id=%s threads=%s processed=%s",
                board_id, len(threads), processed,
            )

        except Exception as e:
            logger.error("巴哈通知背景處理失敗: %s", e, exc_info=True)
