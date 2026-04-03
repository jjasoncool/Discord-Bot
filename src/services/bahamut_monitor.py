"""
巴哈姆特文章 → Discord 論壇頻道 relay 服務

架構：
- 從 Scraper API 取得巴哈討論串資料
- 格式化為 Discord embed
- 發布到 Forum Channel（1 snA = 1 thread）
- 留言使用預建格 + 溢出機制
"""
import asyncio
import aiohttp
import json
import logging
import io
import discord
from datetime import datetime
from typing import List, Dict, Optional, Tuple

from utils.logger_config import get_article_monitor_logger
from utils.discord_content import (
    IMAGE_EXTENSIONS,
    sanitize_forum_thread_title,
    linkify_image_urls,
    content_hash,
    get_forum_tags,
)
from services.base_monitor import BaseContentMonitor, get_article_runtime_config

logger = get_article_monitor_logger()

# embed 顏色
COLOR_MAIN_POST = 0x3498DB    # 藍色 — 主文
COLOR_REPLY = 0x2ECC71        # 綠色 — 回覆
COLOR_COMMENTS = 0x95A5A6     # 灰色 — 留言格

# embed description 上限
EMBED_DESC_LIMIT = 4096
# 留言格安全上限（留一些 buffer 給格式標記）
COMMENT_SLOT_LIMIT = 4000
# 第三格（最後一格預建格）額外預留導航連結空間
# "\n\n⬇️ [更多留言...](https://discord.com/channels/xxxx/xxxx/xxxx)" ≈ 80 chars
LAST_SLOT_NAV_RESERVE = 100
LAST_SLOT_LIMIT = COMMENT_SLOT_LIMIT - LAST_SLOT_NAV_RESERVE
# 每個文章 block 預建的留言格數量
COMMENT_SLOTS_COUNT = 3
# 第一則 embed 內容安全上限（embed 總大小限制 6000，留空間給 title + image + metadata）
FIRST_EMBED_CONTENT_LIMIT = 3500
# 續文 embed 內容上限（預留導航空間）
CONTINUATION_CONTENT_LIMIT = EMBED_DESC_LIMIT - LAST_SLOT_NAV_RESERVE
# 續文被清空時的佔位文字
CONTINUATION_REMOVED_PLACEHOLDER = "（此段已更新移除）"
# 巴哈論壇 tag 名稱
BAHAMUT_FORUM_TAG_NAME = "巴哈"
# 留言格佔位文字
COMMENT_SLOT_PLACEHOLDER = "💬 預留留言區（等待更新中...）"
# 每則 Discord 訊息之間的延遲（秒），避免 rate limit
SEND_DELAY = 0.8
# 巴哈小屋個人頁 URL 模板
BAHAMUT_PROFILE_URL = "https://home.gamer.com.tw/profile/index.php?owner={user_id}"



def _author_link(name: str, user_id: str) -> str:
    """將作者名稱轉為巴哈小屋連結。"""
    if user_id:
        url = BAHAMUT_PROFILE_URL.format(user_id=user_id)
        return f"[**{name}**]({url})"
    return f"**{name}**"


# 模組級 snA 鎖：同一個 snA 同時只能有一個 task 在處理（跨實例共用）
_thread_locks: Dict[str, asyncio.Lock] = {}
# 全域並行上限：同時最多處理 N 篇文章（避免 rate limit 和資源搶奪）
_concurrency_semaphore = asyncio.Semaphore(3)


def _get_thread_lock(content_key: str) -> asyncio.Lock:
    """取得或建立某個 snA 的 asyncio.Lock。"""
    if content_key not in _thread_locks:
        _thread_locks[content_key] = asyncio.Lock()
    return _thread_locks[content_key]


class BahamutMonitor(BaseContentMonitor):
    """巴哈姆特文章 → Discord Forum Channel 監控器"""

    def __init__(self, bot, scraper_api_url: str = "http://scraper:8000"):
        super().__init__(bot, scraper_api_url)

    # ── API 呼叫 ──

    async def fetch_recent_threads(self, days: int = 3, limit: int = 50, board_id: str = None) -> List[Dict]:
        """從 Scraper API 取得最近的巴哈討論串。"""
        try:
            params = {"days": days, "limit": limit, "order": "desc"}
            if board_id:
                params["board_id"] = board_id
            url = f"{self.scraper_api_url}/api/bahamut/recent"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("success"):
                            return data.get("threads", [])
                        else:
                            logger.error("巴哈 API 回應失敗: %s", data.get("message"))
                    else:
                        logger.error("巴哈 API 請求失敗，狀態碼: %s", resp.status)
        except asyncio.TimeoutError:
            logger.error("巴哈 API 請求逾時")
        except Exception as e:
            logger.error("取得巴哈討論串時發生錯誤: %s", e)
        return []

    async def fetch_single_thread(self, board_id: str, post_id: str) -> Optional[Dict]:
        """從 Scraper API 取得單一巴哈討論串。"""
        try:
            url = f"{self.scraper_api_url}/api/bahamut/{board_id}/{post_id}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("success"):
                            return data.get("thread")
                        else:
                            logger.error("巴哈 API 回應失敗: %s", data.get("message"))
                    else:
                        logger.error("巴哈 API 請求失敗，狀態碼: %s", resp.status)
        except asyncio.TimeoutError:
            logger.error("巴哈 API 請求逾時")
        except Exception as e:
            logger.error("取得巴哈討論串時發生錯誤: %s", e)
        return None

    # ── Embed 格式化 ──

    @staticmethod
    def _split_content_for_embeds(header: str, content: str, first_limit: int, cont_limit: int) -> List[str]:
        """
        將 header + content 切割成多段 embed description。
        第一段包含 header + 開頭內文，後續段只有內文。
        以換行為切割點，不切斷單行。
        """
        chunks = []

        # 第一段：header + 盡量多的內文
        first_budget = first_limit - len(header) - 1  # -1 for \n
        if first_budget <= 0:
            chunks.append(header[:first_limit])
            remaining = content
        else:
            first_content = ""
            remaining = content
            for line in content.split("\n"):
                candidate = first_content + ("\n" if first_content else "") + line
                if len(candidate) > first_budget:
                    break
                first_content = candidate
                remaining = content[len(first_content):].lstrip("\n")

            chunks.append(header + "\n" + first_content if first_content else header)

        # 後續段：每段 cont_limit
        while remaining:
            chunk = ""
            rest = remaining
            for line in remaining.split("\n"):
                candidate = chunk + ("\n" if chunk else "") + line
                if len(candidate) > cont_limit:
                    break
                chunk = candidate
                rest = remaining[len(chunk):].lstrip("\n")

            if not chunk:
                # 單行超過 cont_limit，強制切
                chunk = remaining[:cont_limit]
                rest = remaining[cont_limit:]

            chunks.append(chunk)
            remaining = rest

        return chunks

    @staticmethod
    def format_main_post_embed(main_post: Dict) -> discord.Embed:
        """格式化主文 embed（藍色）。只回傳第一則 embed（含 metadata + 開頭內文）。"""
        title = main_post.get("title") or "（無標題）"
        author = main_post.get("author_name") or "未知"
        author_id = main_post.get("author_id") or ""
        category = main_post.get("category") or ""
        gp = main_post.get("gp_count", 0)
        bp = main_post.get("bp_count", 0)
        url = main_post.get("url") or ""
        published_at = main_post.get("published_at") or ""
        content = main_post.get("content") or ""

        # 組合 header（metadata 部分）
        lines = []
        lines.append(f"👤 {_author_link(author, author_id)}")
        if category:
            lines.append(f"📁 {category}")
        lines.append(f"📅 {published_at}")

        gp_bp_parts = []
        if gp > 0:
            gp_bp_parts.append(f"👍 {gp}")
        if bp > 0:
            gp_bp_parts.append(f"👎 {bp}")
        if gp_bp_parts:
            lines.append(" / ".join(gp_bp_parts))

        if url:
            lines.append(f"🔗 [巴哈原文]({url})")

        lines.append("")
        lines.append("───────────────")
        header = "\n".join(lines)

        # 切割內文
        chunks = BahamutMonitor._split_content_for_embeds(
            header, content,
            first_limit=FIRST_EMBED_CONTENT_LIMIT,
            cont_limit=CONTINUATION_CONTENT_LIMIT,
        )

        embed = discord.Embed(
            title=title[:256],
            description=chunks[0] if chunks else header,
            color=COLOR_MAIN_POST,
        )

        images = main_post.get("content_images") or []
        if images:
            embed.set_image(url=images[0])

        return embed, chunks[1:] if len(chunks) > 1 else []

    @staticmethod
    def format_reply_embed(reply: Dict, reply_index: int) -> discord.Embed:
        """格式化回覆文章 embed（綠色）。"""
        author = reply.get("author_name") or "未知"
        author_id = reply.get("author_id") or ""
        gp = reply.get("gp_count", 0)
        bp = reply.get("bp_count", 0)
        published_at = reply.get("published_at") or ""
        content = reply.get("content") or ""

        lines = []
        lines.append(f"👤 {_author_link(author, author_id)}")
        lines.append(f"📅 {published_at}")

        gp_bp_parts = []
        if gp > 0:
            gp_bp_parts.append(f"👍 {gp}")
        if bp > 0:
            gp_bp_parts.append(f"👎 {bp}")
        if gp_bp_parts:
            lines.append(" / ".join(gp_bp_parts))

        lines.append("")
        lines.append("───────────────")
        header = "\n".join(lines)

        chunks = BahamutMonitor._split_content_for_embeds(
            header, content,
            first_limit=FIRST_EMBED_CONTENT_LIMIT,
            cont_limit=CONTINUATION_CONTENT_LIMIT,
        )

        embed = discord.Embed(
            title=f"📝 回覆 #{reply_index}",
            description=chunks[0] if chunks else header,
            color=COLOR_REPLY,
        )

        images = reply.get("content_images") or []
        if images:
            embed.set_image(url=images[0])

        return embed, chunks[1:] if len(chunks) > 1 else []

    @staticmethod
    def format_comments_embed(comments: List[Dict]) -> discord.Embed:
        """將留言列表格式化為單一 embed。"""
        if not comments:
            return discord.Embed(
                description=COMMENT_SLOT_PLACEHOLDER,
                color=COLOR_COMMENTS,
            )

        lines = []
        for c in comments:
            line = BahamutMonitor._format_single_comment(c)
            lines.append(line)

        description = "\n".join(lines)
        if len(description) > EMBED_DESC_LIMIT:
            description = description[:EMBED_DESC_LIMIT - 20] + "\n\n⋯（已截斷）"

        return discord.Embed(description=description, color=COLOR_COMMENTS)

    @staticmethod
    def _format_single_comment(comment: Dict) -> str:
        """格式化單則留言。"""
        parts = []

        # 🔥 HOT 標記
        if comment.get("is_hot"):
            parts.append("🔥")

        # 樓層
        floor = comment.get("floor") or ""
        if floor:
            parts.append(f"`{floor}`")

        # 使用者（帶巴哈小屋連結）
        user_name = comment.get("user_name") or comment.get("user_id") or "匿名"
        user_id = comment.get("user_id") or ""
        parts.append(_author_link(user_name, user_id))

        # GP / BP
        gp = comment.get("gp_count", 0)
        bp = comment.get("bp_count", 0)
        if gp > 0:
            parts.append(f"👍{gp}")
        if bp > 0:
            parts.append(f"👎{bp}")

        # 內容（圖片 URL 轉 markdown 連結）
        content = comment.get("content") or ""
        content = linkify_image_urls(content)
        parts.append(f"— {content}")

        return " ".join(parts)

    @staticmethod
    def split_comments_into_slots(comments: List[Dict], slot_limit: int = COMMENT_SLOT_LIMIT) -> List[List[Dict]]:
        """
        將留言分配到多個 slot，每個 slot 不超過 slot_limit 字元。
        以整則留言為切割單位，不切斷單則留言。
        第三格（index=2）使用較小的上限，預留導航連結空間。
        """
        slots: List[List[Dict]] = []
        current_slot: List[Dict] = []
        current_chars = 0

        def _current_limit() -> int:
            """第三格（index=2）起全部用 LAST_SLOT_LIMIT，預留導航連結空間。"""
            return LAST_SLOT_LIMIT if len(slots) >= COMMENT_SLOTS_COUNT - 1 else slot_limit

        for comment in comments:
            formatted = BahamutMonitor._format_single_comment(comment)
            line_len = len(formatted) + 1  # +1 for \n

            if current_chars + line_len > _current_limit() and current_slot:
                # 塞不下，換新 slot
                slots.append(current_slot)
                current_slot = []
                current_chars = 0

            current_slot.append(comment)
            current_chars += line_len

        if current_slot:
            slots.append(current_slot)

        return slots

    # ── Forum Thread 建立 ──

    async def send_bahamut_thread_to_forum(
        self,
        forum_channel_id: int,
        thread_data: Dict,
    ) -> Optional[Dict]:
        """
        將一個巴哈討論串發布到 Discord Forum Channel。
        回傳追蹤用的 state dict，失敗回傳 None。
        """
        try:
            channel = self.bot.get_channel(forum_channel_id)
            if not isinstance(channel, discord.ForumChannel):
                logger.error("找不到論壇頻道 ID: %s，或不是 ForumChannel", forum_channel_id)
                return None

            main_post = thread_data.get("main_post")
            if not main_post:
                logger.error("討論串缺少主文: post_id=%s", thread_data.get("post_id"))
                return None

            # 檢查 category 黑名單
            exclude = get_article_runtime_config().get("bahamut_exclude_categories", [])
            category = main_post.get("category") or ""
            if category in exclude:
                logger.debug("巴哈文章分類被排除，跳過: post_id=%s category=%s", thread_data.get("post_id"), category)
                return None

            board_id = thread_data.get("board_id", "")
            post_id = thread_data.get("post_id", "")
            content_key = f"bahamut:{board_id}:{post_id}"

            # 同一個 snA 加鎖，避免手動指令和排程同時處理同一篇
            lock = _get_thread_lock(content_key)
            if lock.locked():
                logger.info("snA 正在處理中，跳過: %s", content_key)
                return None

            # 全域並行上限（同時最多 3 篇），避免 rate limit 和資源搶奪
            async with _concurrency_semaphore:
                async with lock:
                    return await self._process_thread(channel, board_id, post_id, content_key, thread_data)

        except Exception as e:
            logger.error("發送巴哈討論串到論壇頻道失敗: %s", e, exc_info=True)
            return None

    async def _process_thread(
        self,
        channel: discord.ForumChannel,
        board_id: str,
        post_id: str,
        content_key: str,
        thread_data: Dict,
    ) -> Optional[Dict]:
        """實際處理一個討論串（已在鎖內）。"""
        try:
            main_post = thread_data.get("main_post", {})

            # 檢查是否已發送過 → 走增量更新
            if await self.is_content_sent("bahamut", content_key):
                return await self._update_existing_thread(
                    channel.id, board_id, post_id, thread_data,
                )

            # 1. 建立主文 embed + thread
            main_embed, main_cont_chunks = self.format_main_post_embed(main_post)
            thread_title = sanitize_forum_thread_title(main_post.get("title") or "")
            applied_tags = await get_forum_tags(channel, BAHAMUT_FORUM_TAG_NAME)

            created = await channel.create_thread(
                name=thread_title,
                embed=main_embed,
                applied_tags=applied_tags,
            )
            thread = created.thread if hasattr(created, "thread") else created
            if not thread:
                logger.error("建立巴哈 forum thread 失敗: %s", thread_title)
                return None

            logger.info(
                "成功建立巴哈 forum thread: board=%s post_id=%s title=%s thread_id=%s",
                board_id, post_id, thread_title, thread.id,
            )

            # 追蹤狀態
            state = {
                "thread_id": thread.id,
                "posts": {},
            }
            db = await self._get_state_db()

            # 2. 發送主文續文
            starter_message = created.message if hasattr(created, "message") else None
            main_cont_ids = await self._send_continuations(thread, main_cont_chunks, main_embed.color.value if main_embed.color else COLOR_MAIN_POST, starter_message or thread)

            # 3. 發送主文額外圖片（第 2 張起）
            await self._send_post_images(thread, main_post)

            # 4. 處理主文留言 + 預建留言格
            main_sn = main_post.get("sn", "")
            main_state = await self._send_post_comments(
                thread=thread,
                post_data=main_post,
            )
            main_state["msg_id"] = starter_message.id if starter_message else thread.id
            main_state["content_hash"] = content_hash(main_embed.description or "")
            main_state["continuation_msg_ids"] = main_cont_ids
            state["posts"][main_sn] = main_state

            # 立刻寫入 state（即使後續回覆失敗，也不會重複建 thread）
            await db.save_bahamut_thread(board_id, post_id, state)
            logger.info("巴哈 thread 已建立並存入 state: board=%s post_id=%s", board_id, post_id)

            # 3. 處理回覆文章（每 50 則回覆存一次 state）
            replies = thread_data.get("replies") or []
            state_save_interval = 50
            for idx, reply in enumerate(replies, start=2):
                try:
                    reply_embed, reply_cont_chunks = self.format_reply_embed(reply, idx)
                    reply_msg = await thread.send(embed=reply_embed)
                    await asyncio.sleep(SEND_DELAY)

                    # 回覆續文
                    reply_cont_ids = await self._send_continuations(thread, reply_cont_chunks, reply_embed.color.value if reply_embed.color else COLOR_REPLY, reply_msg)

                    # 回覆的額外圖片
                    await self._send_post_images(thread, reply)

                    reply_sn = reply.get("sn", "")
                    reply_state = await self._send_post_comments(
                        thread=thread,
                        post_data=reply,
                    )
                    reply_state["msg_id"] = reply_msg.id
                    reply_state["content_hash"] = content_hash(reply_embed.description or "")
                    reply_state["continuation_msg_ids"] = reply_cont_ids
                    state["posts"][reply_sn] = reply_state

                    # 每 N 則回覆存一次 state（斷掉時能從中間接續）
                    replies_processed = idx - 1  # idx 從 2 開始
                    if replies_processed % state_save_interval == 0:
                        await db.save_bahamut_thread(board_id, post_id, state)
                        logger.info("巴哈 state 中繼儲存: board=%s post_id=%s 已處理 %s/%s 則回覆",
                                    board_id, post_id, replies_processed, len(replies))
                except Exception as e:
                    logger.warning("處理回覆失敗，跳過繼續: sn=%s err=%s", reply.get("sn"), e)

            # 最後一次存（處理完全部或不足 N 則的尾巴）
            await db.save_bahamut_thread(board_id, post_id, state)

            logger.info(
                "巴哈討論串完整發布完成: board=%s post_id=%s replies=%s",
                board_id, post_id, len(replies),
            )
            return state

        except Exception as e:
            logger.error("發送巴哈討論串到論壇頻道失敗: %s", e, exc_info=True)
            return None

    # ── 增量更新 ──

    async def _update_existing_thread(
        self,
        forum_channel_id: int,
        board_id: str,
        post_id: str,
        thread_data: Dict,
    ) -> Optional[Dict]:
        """已存在的討論串：增量更新 GP/BP、新留言、新回覆。"""
        try:
            db = await self._get_state_db()
            old_state = await db.get_bahamut_thread(board_id, post_id)
            if not old_state:
                logger.error("增量更新失敗：找不到 state board=%s post_id=%s", board_id, post_id)
                return None

            thread_id = old_state["thread_id"]
            channel = self.bot.get_channel(forum_channel_id)
            if not channel:
                logger.error("增量更新失敗：找不到頻道 %s", forum_channel_id)
                return None

            thread = channel.get_thread(thread_id)
            if not thread:
                # thread 可能被歸檔，嘗試 fetch
                try:
                    thread = await self.bot.fetch_channel(thread_id)
                except Exception:
                    thread = None

            if not thread:
                # thread 已被刪除 → 清除舊 state，直接重建
                logger.warning("增量更新：thread %s 已不存在，清除 state 並重建", thread_id)
                content_key = f"bahamut:{board_id}:{post_id}"
                await db.db.execute("DELETE FROM sent_content WHERE source='bahamut' AND content_key=?", (content_key,))
                await db.db.execute("DELETE FROM forum_thread_state WHERE source='bahamut' AND content_key=?", (content_key,))
                await db.db.execute("DELETE FROM bahamut_post_state WHERE board_id=? AND post_id=?", (board_id, post_id))
                await db.db.execute("DELETE FROM bahamut_comment_slot WHERE board_id=? AND post_id=?", (board_id, post_id))
                await db.db.commit()
                # 直接走新建流程
                return await self._process_thread(
                    self.bot.get_channel(forum_channel_id),
                    board_id, post_id, content_key, thread_data,
                )

            main_post = thread_data.get("main_post", {})
            new_replies = thread_data.get("replies") or []
            guild_id = thread.guild.id

            # 1. 更新主文 embed（GP/BP 同步，用 DB hash 比對）
            main_sn = main_post.get("sn", "")
            main_post_state = old_state["posts"].get(main_sn)
            if main_post_state and main_post_state.get("msg_id"):
                try:
                    updated_embed, cont_chunks = self.format_main_post_embed(main_post)
                    new_hash = content_hash(updated_embed.description or "")
                    old_hash = main_post_state.get("content_hash")
                    color = updated_embed.color.value if updated_embed.color else COLOR_MAIN_POST
                    if old_hash is None:
                        main_post_state["content_hash"] = new_hash
                        await self._update_continuations(thread, cont_chunks, color, main_post_state)
                        logger.debug("增量更新：主文首次寫入 hash sn=%s", main_sn)
                    elif new_hash != old_hash:
                        main_msg = await thread.fetch_message(main_post_state["msg_id"])
                        await main_msg.edit(embed=updated_embed)
                        await asyncio.sleep(SEND_DELAY)
                        await self._update_continuations(thread, cont_chunks, color, main_post_state)
                        main_post_state["content_hash"] = new_hash
                        logger.info("增量更新：已更新主文 embed + 續文 sn=%s", main_sn)
                    else:
                        logger.debug("增量更新：主文無變化，跳過 sn=%s", main_sn)
                except Exception as e:
                    logger.warning("增量更新：更新主文 embed 失敗 sn=%s: %s", main_sn, e)

            # 2. 更新既有回覆的 embed（GP/BP 同步，用 DB hash 比對）
            for reply in new_replies:
                reply_sn = reply.get("sn", "")
                reply_state = old_state["posts"].get(reply_sn)
                if reply_state and reply_state.get("msg_id"):
                    try:
                        reply_idx = next(
                            (i for i, r in enumerate(new_replies, start=2) if r.get("sn") == reply_sn),
                            2,
                        )
                        updated_embed, cont_chunks = self.format_reply_embed(reply, reply_idx)
                        new_hash = content_hash(updated_embed.description or "")
                        old_hash = reply_state.get("content_hash")
                        color = updated_embed.color.value if updated_embed.color else COLOR_REPLY
                        if old_hash is None:
                            reply_state["content_hash"] = new_hash
                            await self._update_continuations(thread, cont_chunks, color, reply_state)
                            logger.debug("增量更新：回覆首次寫入 hash sn=%s", reply_sn)
                        elif new_hash != old_hash:
                            reply_msg = await thread.fetch_message(reply_state["msg_id"])
                            await reply_msg.edit(embed=updated_embed)
                            await asyncio.sleep(SEND_DELAY)
                            await self._update_continuations(thread, cont_chunks, color, reply_state)
                            reply_state["content_hash"] = new_hash
                            logger.info("增量更新：已更新回覆 embed + 續文 sn=%s", reply_sn)
                        else:
                            logger.debug("增量更新：回覆無變化，跳過 sn=%s", reply_sn)
                    except Exception as e:
                        logger.warning("增量更新：更新回覆 embed 失敗 sn=%s: %s", reply_sn, e)

            # 3. 更新留言（每個 sn 各自比對）
            all_posts = [("main", main_sn, main_post)]
            for reply in new_replies:
                all_posts.append(("reply", reply.get("sn", ""), reply))

            for post_type, sn, post_data in all_posts:
                post_state = old_state["posts"].get(sn)
                if not post_state:
                    # 全新回覆，走新增路徑（下面第 4 步處理）
                    continue

                new_comments = post_data.get("comments") or []
                old_comment_ids = set(post_state.get("synced_comment_ids", []))
                delta_count = len([c for c in new_comments if c.get("comment_id") not in old_comment_ids])

                logger.info(
                    "留言比對：sn=%s 留言總數=%s 新增=%s",
                    sn, len(new_comments), delta_count,
                )

                # 重組所有留言（舊 + 新）成 slots
                all_comment_slots = self.split_comments_into_slots(new_comments)

                # 更新預建格（edit）
                slots = post_state.get("comment_slots", [])
                for i, slot in enumerate(slots):
                    if i < len(all_comment_slots):
                        embed = self.format_comments_embed(all_comment_slots[i])
                        used_chars = sum(len(self._format_single_comment(c)) + 1 for c in all_comment_slots[i])
                    else:
                        embed = discord.Embed(description=COMMENT_SLOT_PLACEHOLDER, color=COLOR_COMMENTS)
                        used_chars = 0

                    # 第三格且有溢出 → 加導航連結
                    if i == COMMENT_SLOTS_COUNT - 1 and len(all_comment_slots) > COMMENT_SLOTS_COUNT:
                        overflow_slots = post_state.get("overflow_slots", [])
                        if overflow_slots:
                            nav_link = f"https://discord.com/channels/{guild_id}/{thread.id}/{overflow_slots[0]['msg_id']}"
                            lines = [self._format_single_comment(c) for c in all_comment_slots[i]]
                            lines.append("")
                            lines.append(f"⬇️ [更多留言...]({nav_link})")
                            description = "\n".join(lines)
                            if len(description) > EMBED_DESC_LIMIT:
                                description = description[:EMBED_DESC_LIMIT - 20] + "\n\n⋯（已截斷）"
                            embed = discord.Embed(description=description, color=COLOR_COMMENTS)

                    try:
                        new_hash = content_hash(embed.description or "")
                        old_hash = slot.get("content_hash")
                        if old_hash is None:
                            slot["content_hash"] = new_hash
                            logger.debug("增量更新：留言格首次寫入 hash sn=%s slot=%s", sn, i)
                        elif new_hash != old_hash:
                            msg = await thread.fetch_message(slot["msg_id"])
                            await msg.edit(embed=embed)
                            await asyncio.sleep(SEND_DELAY)
                            slot["used_chars"] = used_chars
                            slot["content_hash"] = new_hash
                            logger.info("增量更新：已更新留言格 sn=%s slot=%s", sn, i)
                        else:
                            logger.debug("增量更新：留言格無變化，跳過 sn=%s slot=%s", sn, i)
                    except Exception as e:
                        logger.warning("增量更新：edit 留言格失敗 sn=%s slot=%s: %s", sn, i, e)

                # 更新溢出格（edit 既有的，有變化才 edit）
                overflow_slots = post_state.get("overflow_slots", [])
                overflow_data_start = COMMENT_SLOTS_COUNT
                for i, overflow_slot in enumerate(overflow_slots):
                    data_idx = overflow_data_start + i
                    if data_idx < len(all_comment_slots):
                        embed = self.format_comments_embed(all_comment_slots[data_idx])
                        used_chars = sum(len(self._format_single_comment(c)) + 1 for c in all_comment_slots[data_idx])

                        # 如果還有下一格溢出，加導航連結
                        next_overflow_idx = i + 1
                        if next_overflow_idx < len(overflow_slots):
                            next_msg_id = overflow_slots[next_overflow_idx]["msg_id"]
                            lines = [self._format_single_comment(c) for c in all_comment_slots[data_idx]]
                            lines.append("")
                            lines.append(f"⬇️ [更多留言...](https://discord.com/channels/{guild_id}/{thread.id}/{next_msg_id})")
                            description = "\n".join(lines)
                            if len(description) > EMBED_DESC_LIMIT:
                                description = description[:EMBED_DESC_LIMIT - 20] + "\n\n⋯（已截斷）"
                            embed = discord.Embed(description=description, color=COLOR_COMMENTS)

                        try:
                            new_hash = content_hash(embed.description or "")
                            old_hash = overflow_slot.get("content_hash")
                            if old_hash is None:
                                overflow_slot["content_hash"] = new_hash
                                logger.debug("增量更新：溢出格首次寫入 hash sn=%s overflow=%s", sn, i)
                            elif new_hash != old_hash:
                                msg = await thread.fetch_message(overflow_slot["msg_id"])
                                await msg.edit(embed=embed)
                                await asyncio.sleep(SEND_DELAY)
                                overflow_slot["used_chars"] = used_chars
                                overflow_slot["content_hash"] = new_hash
                                logger.info("增量更新：已更新溢出格 sn=%s overflow=%s", sn, i)
                            else:
                                logger.debug("增量更新：溢出格無變化，跳過 sn=%s overflow=%s", sn, i)
                        except Exception as e:
                            logger.warning("增量更新：edit 溢出格失敗 sn=%s overflow=%s: %s", sn, i, e)

                # 需要新的溢出格？
                total_existing_slots = len(slots) + len(overflow_slots)
                if len(all_comment_slots) > total_existing_slots and (slots or overflow_slots):
                    # 找最後一個 msg 作為 reply anchor
                    if overflow_slots:
                        last_msg_id = overflow_slots[-1]["msg_id"]
                        last_comments = all_comment_slots[total_existing_slots - 1] if total_existing_slots - 1 < len(all_comment_slots) else []
                    else:
                        last_msg_id = slots[-1]["msg_id"]
                        last_comments = all_comment_slots[COMMENT_SLOTS_COUNT - 1] if COMMENT_SLOTS_COUNT - 1 < len(all_comment_slots) else []

                    prev_msg = await thread.fetch_message(last_msg_id)

                    for data_idx in range(total_existing_slots, len(all_comment_slots)):
                        overflow_comments = all_comment_slots[data_idx]
                        embed = self.format_comments_embed(overflow_comments)
                        used_chars = sum(len(self._format_single_comment(c)) + 1 for c in overflow_comments)

                        overflow_msg = await thread.send(embed=embed, reference=prev_msg)
                        await asyncio.sleep(SEND_DELAY)
                        overflow_slots.append({"msg_id": overflow_msg.id, "used_chars": used_chars})

                        # edit 前一格加導航連結
                        nav_link = f"https://discord.com/channels/{guild_id}/{thread.id}/{overflow_msg.id}"
                        lines = [self._format_single_comment(c) for c in last_comments]
                        lines.append("")
                        lines.append(f"⬇️ [更多留言...]({nav_link})")
                        description = "\n".join(lines)
                        if len(description) > EMBED_DESC_LIMIT:
                            description = description[:EMBED_DESC_LIMIT - 20] + "\n\n⋯（已截斷）"
                        await prev_msg.edit(embed=discord.Embed(description=description, color=COLOR_COMMENTS))

                        prev_msg = overflow_msg
                        last_comments = overflow_comments

                # 更新 synced_comment_ids
                post_state["synced_comment_ids"] = [c.get("comment_id") for c in new_comments]

            # 4. 新回覆（state 裡沒有的 sn）
            existing_sns = set(old_state["posts"].keys())
            new_reply_idx = len(existing_sns) + 1  # 接續原本的回覆編號
            for reply in new_replies:
                reply_sn = reply.get("sn", "")
                if reply_sn in existing_sns:
                    continue

                new_reply_idx += 1
                reply_embed, reply_cont_chunks = self.format_reply_embed(reply, new_reply_idx)
                reply_msg = await thread.send(embed=reply_embed)
                await asyncio.sleep(SEND_DELAY)

                # 回覆續文
                reply_cont_ids = await self._send_continuations(thread, reply_cont_chunks, reply_embed.color.value if reply_embed.color else COLOR_REPLY, reply_msg)

                # 回覆的額外圖片
                await self._send_post_images(thread, reply)

                reply_state = await self._send_post_comments(thread=thread, post_data=reply)
                reply_state["msg_id"] = reply_msg.id
                reply_state["continuation_msg_ids"] = reply_cont_ids
                old_state["posts"][reply_sn] = reply_state

                logger.info("增量更新：新增回覆 sn=%s reply_idx=%s", reply_sn, new_reply_idx)

            # 5. 存回 state DB
            await db.save_bahamut_thread(board_id, post_id, old_state)

            logger.info(
                "巴哈討論串增量更新完成: board=%s post_id=%s",
                board_id, post_id,
            )
            return old_state

        except Exception as e:
            logger.error("增量更新巴哈討論串失敗: %s", e, exc_info=True)
            return None

    async def _send_continuations(
        self,
        thread: discord.Thread,
        chunks: List[str],
        color: int,
        first_msg,
    ) -> List[int]:
        """
        發送續文 embeds。
        回傳續文的 msg_id 列表。
        """
        if not chunks:
            return []
        guild_id = thread.guild.id
        continuation_msg_ids = []
        prev_msg = first_msg

        for i, chunk_text in enumerate(chunks):
            cont_embed = discord.Embed(description=chunk_text, color=color)
            # 初次建立時續文緊跟在主文後面，不需要 reply
            cont_msg = await thread.send(embed=cont_embed)
            await asyncio.sleep(SEND_DELAY)
            continuation_msg_ids.append(cont_msg.id)

            # 前一則加導航連結（除了第一則續文，因為它緊跟在主 embed 後面不需要導航）
            if len(continuation_msg_ids) >= 2:
                # edit 前一則續文加導航
                prev_cont_id = continuation_msg_ids[-2]
                try:
                    prev_cont_msg = await thread.fetch_message(prev_cont_id)
                    nav_link = f"https://discord.com/channels/{guild_id}/{thread.id}/{cont_msg.id}"
                    old_desc = prev_cont_msg.embeds[0].description if prev_cont_msg.embeds else ""
                    new_desc = old_desc + f"\n\n⬇️ [更多內文...]({nav_link})"
                    if len(new_desc) <= EMBED_DESC_LIMIT:
                        await prev_cont_msg.edit(embed=discord.Embed(description=new_desc, color=color))
                        await asyncio.sleep(SEND_DELAY)
                except Exception as e:
                    logger.warning("續文導航連結添加失敗: %s", e)

            prev_msg = cont_msg

        return continuation_msg_ids

    async def _update_continuations(
        self,
        thread: discord.Thread,
        chunks: List[str],
        color: int,
        post_state: Dict,
    ) -> None:
        """
        增量更新續文：edit 既有的 / 清空多出的 / 追加新的。
        直接修改 post_state["continuation_msg_ids"]。
        """
        new_chunks = chunks
        old_cont_ids = post_state.get("continuation_msg_ids") or []
        guild_id = thread.guild.id

        updated_ids = list(old_cont_ids)

        # 1. edit 既有的續文
        for i, cont_id in enumerate(old_cont_ids):
            try:
                cont_msg = await thread.fetch_message(cont_id)
                if i < len(new_chunks):
                    # 有對應的新內容 → edit
                    new_embed = discord.Embed(description=new_chunks[i], color=color)
                    await cont_msg.edit(embed=new_embed)
                    await asyncio.sleep(SEND_DELAY)
                else:
                    # 多出來 → edit 為佔位文字
                    cleared_embed = discord.Embed(description=CONTINUATION_REMOVED_PLACEHOLDER, color=0x808080)
                    await cont_msg.edit(embed=cleared_embed)
                    await asyncio.sleep(SEND_DELAY)
            except Exception as e:
                logger.warning("增量更新：edit 續文失敗 cont_id=%s: %s", cont_id, e)

        # 2. 需要追加新的續文
        if len(new_chunks) > len(old_cont_ids):
            # 找最後一個有效的續文（或主文）作為 reply anchor
            # 先找最後一個非清空的續文
            last_valid_idx = -1
            for i in range(min(len(old_cont_ids), len(new_chunks)) - 1, -1, -1):
                last_valid_idx = i
                break

            if last_valid_idx >= 0:
                prev_msg = await thread.fetch_message(old_cont_ids[last_valid_idx])
            else:
                prev_msg = await thread.fetch_message(post_state["msg_id"])

            for i in range(len(old_cont_ids), len(new_chunks)):
                # 先檢查有沒有已清空的續文可以復用
                if i < len(updated_ids):
                    try:
                        reuse_msg = await thread.fetch_message(updated_ids[i])
                        new_embed = discord.Embed(description=new_chunks[i], color=color)
                        await reuse_msg.edit(embed=new_embed)
                        await asyncio.sleep(SEND_DELAY)
                        prev_msg = reuse_msg
                        continue
                    except Exception:
                        pass

                # 新建續文（reply to 前一則）
                new_embed = discord.Embed(description=new_chunks[i], color=color)
                new_msg = await thread.send(embed=new_embed, reference=prev_msg)
                await asyncio.sleep(SEND_DELAY)
                updated_ids.append(new_msg.id)

                # 前一則加導航連結
                try:
                    nav_link = f"https://discord.com/channels/{guild_id}/{thread.id}/{new_msg.id}"
                    prev_desc = prev_msg.embeds[0].description if prev_msg.embeds else ""
                    new_desc = prev_desc + f"\n\n⬇️ [更多內文...]({nav_link})"
                    if len(new_desc) <= EMBED_DESC_LIMIT:
                        await prev_msg.edit(embed=discord.Embed(description=new_desc, color=color))
                        await asyncio.sleep(SEND_DELAY)
                except Exception as e:
                    logger.warning("續文導航連結添加失敗: %s", e)

                prev_msg = new_msg

        post_state["continuation_msg_ids"] = updated_ids

    async def _send_post_images(
        self,
        thread: discord.Thread,
        post_data: Dict,
    ) -> None:
        """發送文章的額外圖片（第 2 張起）到 thread，每批最多 10 張。"""
        images = post_data.get("content_images") or []
        if len(images) <= 1:
            return  # 第一張已在 embed set_image，不需要額外發

        remaining = images[1:]  # 跳過第一張
        async with aiohttp.ClientSession() as session:
            for batch_start in range(0, len(remaining), 10):
                batch_urls = remaining[batch_start:batch_start + 10]
                files = []
                for idx, img_url in enumerate(batch_urls, start=batch_start + 2):
                    try:
                        async with session.get(img_url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                            if resp.status == 200 and resp.content_length and resp.content_length < 25 * 1024 * 1024:
                                data = await resp.read()
                                # 從 URL 或 content-type 推斷副檔名
                                ct = resp.headers.get("content-type", "")
                                ext = ".jpg"
                                if "png" in ct:
                                    ext = ".png"
                                elif "gif" in ct:
                                    ext = ".gif"
                                elif "webp" in ct:
                                    ext = ".webp"
                                files.append(discord.File(io.BytesIO(data), filename=f"image_{idx}{ext}"))
                    except Exception as e:
                        logger.warning("巴哈圖片下載失敗，跳過: url=%s err=%s", img_url, e)

                if files:
                    label = "**本文附圖**" if batch_start == 0 else ""
                    await thread.send(content=label, files=files)
                    await asyncio.sleep(SEND_DELAY)

    async def _send_post_comments(
        self,
        thread: discord.Thread,
        post_data: Dict,
    ) -> Dict:
        """
        為單篇文章（主文或回覆）發送預建留言格。
        回傳該 post 的追蹤 state。
        """
        comments = post_data.get("comments") or []
        comment_slots_data = self.split_comments_into_slots(comments)

        post_state = {
            "msg_id": None,
            "comment_slots": [],
            "overflow_anchor": None,
            "overflow_slots": [],
            "synced_comment_ids": [c.get("comment_id") for c in comments],
        }

        # 發送預建留言格（最多 COMMENT_SLOTS_COUNT 格）
        for i in range(COMMENT_SLOTS_COUNT):
            if i < len(comment_slots_data):
                embed = self.format_comments_embed(comment_slots_data[i])
                used_chars = sum(
                    len(self._format_single_comment(c)) + 1
                    for c in comment_slots_data[i]
                )
            else:
                embed = discord.Embed(
                    description=COMMENT_SLOT_PLACEHOLDER,
                    color=COLOR_COMMENTS,
                )
                used_chars = 0

            msg = await thread.send(embed=embed)
            await asyncio.sleep(SEND_DELAY)
            post_state["comment_slots"].append({
                "msg_id": msg.id,
                "used_chars": used_chars,
            })

        # 如果留言超過 3 格，處理溢出（鏈式 reply）
        if len(comment_slots_data) > COMMENT_SLOTS_COUNT:
            post_state["overflow_anchor"] = post_state["comment_slots"][-1]["msg_id"]
            guild_id = thread.guild.id

            # prev_msg: 上一格的訊息物件（第一輪是第三格）
            # prev_comments: 上一格的留言資料（用於 edit 加導航連結）
            prev_msg = await thread.fetch_message(post_state["comment_slots"][-1]["msg_id"])
            prev_comments = comment_slots_data[COMMENT_SLOTS_COUNT - 1] if COMMENT_SLOTS_COUNT - 1 < len(comment_slots_data) else []

            for overflow_comments in comment_slots_data[COMMENT_SLOTS_COUNT:]:
                embed = self.format_comments_embed(overflow_comments)
                used_chars = sum(
                    len(self._format_single_comment(c)) + 1
                    for c in overflow_comments
                )
                # reply to 前一格
                overflow_msg = await thread.send(
                    embed=embed,
                    reference=prev_msg,
                )
                await asyncio.sleep(SEND_DELAY)
                post_state["overflow_slots"].append({
                    "msg_id": overflow_msg.id,
                    "used_chars": used_chars,
                })

                # edit 前一格，在底部 append 導航連結
                nav_link = f"https://discord.com/channels/{guild_id}/{thread.id}/{overflow_msg.id}"
                lines = [self._format_single_comment(c) for c in prev_comments]
                lines.append("")
                lines.append(f"⬇️ [更多留言...]({nav_link})")
                description = "\n".join(lines)
                if len(description) > EMBED_DESC_LIMIT:
                    description = description[:EMBED_DESC_LIMIT - 20] + "\n\n⋯（已截斷）"
                await prev_msg.edit(embed=discord.Embed(description=description, color=COLOR_COMMENTS))

                # 推進：當前格變成下一輪的「前一格」
                prev_msg = overflow_msg
                prev_comments = overflow_comments

        return post_state

    # ── 測試用：發送單一討論串 ──

    async def test_send_single_thread(
        self,
        forum_channel_id: int,
        board_id: str,
        post_id: str,
    ) -> Optional[Dict]:
        """測試用：從 API 取得單一討論串並發送到論壇頻道。"""
        thread_data = await self.fetch_single_thread(board_id, post_id)
        if not thread_data:
            logger.error("無法取得巴哈討論串: board=%s post_id=%s", board_id, post_id)
            return None

        state = await self.send_bahamut_thread_to_forum(forum_channel_id, thread_data)
        return state
