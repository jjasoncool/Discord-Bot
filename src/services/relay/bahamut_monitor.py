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
import time
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
from services.relay.base_monitor import BaseContentMonitor, get_article_runtime_config

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
# 續文底部的導航連結：Discord ID 最長 20 位數時連結共 107 字。
# 舊值借用留言格的 100，續文切到滿時連結塞不下、被略過（實際 ID 19 位數時是 104 字）
CONTINUATION_NAV_RESERVE = 110
# 續文 embed 內容上限（預留導航空間）
CONTINUATION_CONTENT_LIMIT = EMBED_DESC_LIMIT - CONTINUATION_NAV_RESERVE
# 續文被清空時的佔位文字
CONTINUATION_REMOVED_PLACEHOLDER = "（此段已更新移除）"
# 巴哈論壇 tag 名稱
BAHAMUT_FORUM_TAG_NAME = "巴哈"
# 留言格佔位文字
COMMENT_SLOT_PLACEHOLDER = "💬 預留留言區（等待更新中...）"
# 每則 Discord 訊息之間的延遲（秒），避免 rate limit
SEND_DELAY = 0.8
# 同一個討論串裡兩次 edit 之間的最小間隔（秒）
# Discord 對編輯舊訊息有未公開的較嚴限速：實測同一串約 5 秒只能編一則（429 要求等待最長 5.04 秒），
# 只按「同一則訊息」冷卻擋不住同串的其他訊息，熱門串每則都會先吃 429 再等
THREAD_EDIT_INTERVAL = 6.0
# 巴哈小屋個人頁 URL 模板
BAHAMUT_PROFILE_URL = "https://home.gamer.com.tw/profile/index.php?owner={user_id}"



def _continuation_nav(guild_id: int, thread_id: int, next_msg_id: int) -> str:
    """接在續文底部、連到下一則續文的導航連結。"""
    return f"\n\n⬇️ [更多內文...](https://discord.com/channels/{guild_id}/{thread_id}/{next_msg_id})"


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
# 每個討論串下一次可以 edit 的 monotonic 時戳
_next_edit_at: Dict[int, float] = {}


async def _edit_with_cooldown(msg: discord.Message, **kwargs) -> None:
    """同一個討論串的 edit 排隊，主動避開 Discord 對編輯舊訊息的限速。"""
    channel_id = msg.channel.id
    now = time.monotonic()
    previous = _next_edit_at.get(channel_id, 0.0)
    start = max(now, previous)
    # 先登記再等：同串有兩個 edit 同時進來時也會依序錯開
    reserved = start + THREAD_EDIT_INTERVAL
    _next_edit_at[channel_id] = reserved
    if start > now:
        await asyncio.sleep(start - now)
    try:
        await msg.edit(**kwargs)
    except Exception:
        # 被拒絕的 edit（例如討論串已封存）不佔名額，否則每則失敗都白等一個間隔
        if _next_edit_at.get(channel_id) == reserved:
            _next_edit_at[channel_id] = previous
        raise
    # discord.py 吃到 429 會自己等完重試：間隔從真正編完的時間起算
    _next_edit_at[channel_id] = max(_next_edit_at[channel_id], time.monotonic() + THREAD_EDIT_INTERVAL)


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
            main_desc = await self._link_post_to_continuations(thread, starter_message, main_embed, main_cont_chunks, main_cont_ids)

            # 3. 發送主文額外圖片（第 2 張起）
            await self._send_post_images(thread, main_post)

            # 4. 處理主文留言 + 預建留言格
            main_sn = main_post.get("sn", "")
            main_state = await self._send_post_comments(
                thread=thread,
                post_data=main_post,
            )
            main_state["msg_id"] = starter_message.id if starter_message else thread.id
            main_state["content_hash"] = content_hash(main_desc)
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
                    reply_desc = await self._link_post_to_continuations(thread, reply_msg, reply_embed, reply_cont_chunks, reply_cont_ids)

                    # 回覆的額外圖片
                    await self._send_post_images(thread, reply)

                    reply_sn = reply.get("sn", "")
                    reply_state = await self._send_post_comments(
                        thread=thread,
                        post_data=reply,
                    )
                    reply_state["msg_id"] = reply_msg.id
                    reply_state["content_hash"] = content_hash(reply_desc)
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

            # 封存的串編輯一定被拒（50083），hash 不會更新、每輪白試。
            # 只有推數／留言變動時不為此把舊貼文頂回活躍列表；變動留著，等有新回覆時一起補上
            if getattr(thread, "archived", False):
                if all(r.get("sn", "") in old_state["posts"] for r in new_replies):
                    logger.debug("增量更新：討論串已封存，等有新回覆再更新 board=%s post_id=%s", board_id, post_id)
                    return old_state
                # 有新回覆時發文本來就會解除封存；先解除，前面的編輯才不會被拒
                try:
                    await thread.edit(archived=False)
                except Exception as e:
                    logger.warning("增量更新：解除封存失敗 board=%s post_id=%s: %s", board_id, post_id, e)

            # 1. 更新主文 embed（GP/BP 同步，用 DB hash 比對）
            main_sn = main_post.get("sn", "")
            main_post_state = old_state["posts"].get(main_sn)
            if main_post_state and main_post_state.get("msg_id"):
                try:
                    updated_embed, cont_chunks = self.format_main_post_embed(main_post)
                    color = updated_embed.color.value if updated_embed.color else COLOR_MAIN_POST
                    # 續文先同步（後段改了、導航連結掉了都要補）：第一則續文確定後，本文底部的連結才指得對
                    await self._update_continuations(thread, cont_chunks, color, main_post_state)
                    self._add_continuation_link(updated_embed, guild_id, thread.id, cont_chunks, main_post_state)
                    new_hash = content_hash(updated_embed.description or "")
                    old_hash = main_post_state.get("content_hash")
                    if old_hash is None:
                        main_post_state["content_hash"] = new_hash
                        logger.debug("增量更新：主文首次寫入 hash sn=%s", main_sn)
                    elif new_hash != old_hash:
                        main_msg = await thread.fetch_message(main_post_state["msg_id"])
                        await _edit_with_cooldown(main_msg, embed=updated_embed)
                        await asyncio.sleep(SEND_DELAY)
                        main_post_state["content_hash"] = new_hash
                        logger.info("增量更新：已更新主文 embed sn=%s", main_sn)
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
                        color = updated_embed.color.value if updated_embed.color else COLOR_REPLY
                        await self._update_continuations(thread, cont_chunks, color, reply_state)
                        self._add_continuation_link(updated_embed, guild_id, thread.id, cont_chunks, reply_state)
                        new_hash = content_hash(updated_embed.description or "")
                        old_hash = reply_state.get("content_hash")
                        if old_hash is None:
                            reply_state["content_hash"] = new_hash
                            logger.debug("增量更新：回覆首次寫入 hash sn=%s", reply_sn)
                        elif new_hash != old_hash:
                            reply_msg = await thread.fetch_message(reply_state["msg_id"])
                            await _edit_with_cooldown(reply_msg, embed=updated_embed)
                            await asyncio.sleep(SEND_DELAY)
                            reply_state["content_hash"] = new_hash
                            logger.info("增量更新：已更新回覆 embed sn=%s", reply_sn)
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

                if delta_count > 0:
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
                            await _edit_with_cooldown(msg, embed=embed)
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
                                await _edit_with_cooldown(msg, embed=embed)
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
                        prev_slot = overflow_slots[-1]
                        last_comments = all_comment_slots[total_existing_slots - 1] if total_existing_slots - 1 < len(all_comment_slots) else []
                    else:
                        prev_slot = slots[-1]
                        last_comments = all_comment_slots[COMMENT_SLOTS_COUNT - 1] if COMMENT_SLOTS_COUNT - 1 < len(all_comment_slots) else []

                    prev_msg = await thread.fetch_message(prev_slot["msg_id"])

                    for data_idx in range(total_existing_slots, len(all_comment_slots)):
                        overflow_comments = all_comment_slots[data_idx]
                        embed = self.format_comments_embed(overflow_comments)
                        used_chars = sum(len(self._format_single_comment(c)) + 1 for c in overflow_comments)

                        overflow_msg = await thread.send(embed=embed, reference=prev_msg)
                        await asyncio.sleep(SEND_DELAY)
                        overflow_slot = {
                            "msg_id": overflow_msg.id,
                            "used_chars": used_chars,
                            "content_hash": content_hash(embed.description or ""),
                        }
                        overflow_slots.append(overflow_slot)

                        # edit 前一格加導航連結
                        nav_link = f"https://discord.com/channels/{guild_id}/{thread.id}/{overflow_msg.id}"
                        lines = [self._format_single_comment(c) for c in last_comments]
                        lines.append("")
                        lines.append(f"⬇️ [更多留言...]({nav_link})")
                        description = "\n".join(lines)
                        if len(description) > EMBED_DESC_LIMIT:
                            description = description[:EMBED_DESC_LIMIT - 20] + "\n\n⋯（已截斷）"
                        await _edit_with_cooldown(prev_msg, embed=discord.Embed(description=description, color=COLOR_COMMENTS))
                        prev_slot["content_hash"] = content_hash(description)

                        prev_msg = overflow_msg
                        prev_slot = overflow_slot
                        last_comments = overflow_comments

                # 更新 synced_comment_ids
                post_state["synced_comment_ids"] = [c.get("comment_id") for c in new_comments]

            # 4. 新回覆（state 裡沒有的 sn）
            existing_sns = set(old_state["posts"].keys())
            # 接續原本的回覆編號：主文是 #1，existing_sns 已含主文，迴圈裡先 +1 就是下一則
            new_reply_idx = len(existing_sns)
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
                reply_desc = await self._link_post_to_continuations(thread, reply_msg, reply_embed, reply_cont_chunks, reply_cont_ids)

                # 回覆的額外圖片
                await self._send_post_images(thread, reply)

                reply_state = await self._send_post_comments(thread=thread, post_data=reply)
                reply_state["msg_id"] = reply_msg.id
                reply_state["content_hash"] = content_hash(reply_desc)
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

    @staticmethod
    def _add_continuation_link(embed: discord.Embed, guild_id: int, thread_id: int, chunks: List[str], post_state: Dict) -> None:
        """本文被切斷時，底部加「更多內文」連到第一則續文（改文變長時新續文在串尾，從本文要找得到）。
        連結目標是存在 state 的第一則續文 id，建立後就不變，所以算進 hash 也不會每輪判定有變。"""
        cont_ids = post_state.get("continuation_msg_ids") or []
        if chunks and cont_ids:
            embed.description = (embed.description or "") + _continuation_nav(guild_id, thread_id, cont_ids[0])

    async def _link_post_to_continuations(
        self,
        thread: discord.Thread,
        msg,
        embed: discord.Embed,
        chunks: List[str],
        cont_ids: List[int],
    ) -> str:
        """新發的本文補上往下的連結（續文要先發出去才有 id）。
        回傳 Discord 上實際的描述給呼叫端記 hash：補失敗就記沒連結的版本，下一輪會再補。"""
        plain = embed.description or ""
        if msg is None or not (chunks and cont_ids):
            return plain
        linked = embed.copy()
        self._add_continuation_link(linked, thread.guild.id, thread.id, chunks, {"continuation_msg_ids": cont_ids})
        try:
            await _edit_with_cooldown(msg, embed=linked)
            await asyncio.sleep(SEND_DELAY)
            return linked.description
        except Exception as e:
            logger.warning("本文續文連結添加失敗: %s", e)
            return plain

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
        prev_cont_msg = None

        for i, chunk_text in enumerate(chunks):
            cont_embed = discord.Embed(description=chunk_text, color=color)
            # 初次建立時續文緊跟在主文後面，不需要 reply
            cont_msg = await thread.send(embed=cont_embed)
            await asyncio.sleep(SEND_DELAY)
            continuation_msg_ids.append(cont_msg.id)

            # 前一則續文加導航連結（第一則續文緊跟在主 embed 後面，主 embed 不需要導航）
            if prev_cont_msg is not None:
                try:
                    new_desc = chunks[i - 1] + _continuation_nav(guild_id, thread.id, cont_msg.id)
                    await _edit_with_cooldown(prev_cont_msg, embed=discord.Embed(description=new_desc, color=color))
                    await asyncio.sleep(SEND_DELAY)
                except Exception as e:
                    logger.warning("續文導航連結添加失敗: %s", e)

            prev_cont_msg = cont_msg

        return continuation_msg_ids

    async def _update_continuations(
        self,
        thread: discord.Thread,
        chunks: List[str],
        color: int,
        post_state: Dict,
    ) -> None:
        """
        增量更新續文：不夠的追加、多出的改成佔位，再逐則比對應有內容（含導航連結），
        跟訊息上的一樣就不編。直接修改 post_state["continuation_msg_ids"]。
        """
        cont_ids = list(post_state.get("continuation_msg_ids") or [])
        if not cont_ids and not chunks:
            return
        guild_id = thread.guild.id
        sent = {}

        # 1. 不夠的先追加（排在討論串最後，reply 前一則方便往回找）；導航連結等全部 id 確定後一起補
        if len(chunks) > len(cont_ids):
            try:
                prev_msg = await thread.fetch_message(cont_ids[-1] if cont_ids else post_state["msg_id"])
                for i in range(len(cont_ids), len(chunks)):
                    prev_msg = await thread.send(embed=discord.Embed(description=chunks[i], color=color), reference=prev_msg)
                    await asyncio.sleep(SEND_DELAY)
                    cont_ids.append(prev_msg.id)
                    sent[prev_msg.id] = prev_msg
            except Exception as e:
                logger.warning("增量更新：追加續文失敗: %s", e)

        # 2. 逐則比對；Discord 會修掉內容頭尾的空白，比對時一起忽略
        for i, cont_id in enumerate(cont_ids):
            if i < len(chunks):
                expected = chunks[i]
                if i + 1 < len(chunks) and i + 1 < len(cont_ids):
                    expected += _continuation_nav(guild_id, thread.id, cont_ids[i + 1])
                expected_color = color
            else:
                expected, expected_color = CONTINUATION_REMOVED_PLACEHOLDER, 0x808080
            try:
                cont_msg = sent.get(cont_id) or await thread.fetch_message(cont_id)
                current = (cont_msg.embeds[0].description if cont_msg.embeds else None) or ""
                if current.strip() == expected.strip():
                    continue
                await _edit_with_cooldown(cont_msg, embed=discord.Embed(description=expected, color=expected_color))
                await asyncio.sleep(SEND_DELAY)
                logger.info("增量更新：已更新續文 msg=%s", cont_id)
            except Exception as e:
                logger.warning("增量更新：edit 續文失敗 cont_id=%s: %s", cont_id, e)

        post_state["continuation_msg_ids"] = cont_ids

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
            # 建立當下就記 hash：沒記的話下一輪只會補記、不會編，這期間的新留言就不會出現
            post_state["comment_slots"].append({
                "msg_id": msg.id,
                "used_chars": used_chars,
                "content_hash": content_hash(embed.description or ""),
            })

        # 如果留言超過 3 格，處理溢出（鏈式 reply）
        if len(comment_slots_data) > COMMENT_SLOTS_COUNT:
            post_state["overflow_anchor"] = post_state["comment_slots"][-1]["msg_id"]
            guild_id = thread.guild.id

            # prev_msg: 上一格的訊息物件（第一輪是第三格）
            # prev_comments: 上一格的留言資料（用於 edit 加導航連結）
            prev_msg = await thread.fetch_message(post_state["comment_slots"][-1]["msg_id"])
            prev_slot = post_state["comment_slots"][-1]
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
                overflow_slot = {
                    "msg_id": overflow_msg.id,
                    "used_chars": used_chars,
                    "content_hash": content_hash(embed.description or ""),
                }
                post_state["overflow_slots"].append(overflow_slot)

                # edit 前一格，在底部 append 導航連結
                nav_link = f"https://discord.com/channels/{guild_id}/{thread.id}/{overflow_msg.id}"
                lines = [self._format_single_comment(c) for c in prev_comments]
                lines.append("")
                lines.append(f"⬇️ [更多留言...]({nav_link})")
                description = "\n".join(lines)
                if len(description) > EMBED_DESC_LIMIT:
                    description = description[:EMBED_DESC_LIMIT - 20] + "\n\n⋯（已截斷）"
                await _edit_with_cooldown(prev_msg, embed=discord.Embed(description=description, color=COLOR_COMMENTS))
                prev_slot["content_hash"] = content_hash(description)

                # 推進：當前格變成下一輪的「前一格」
                prev_msg = overflow_msg
                prev_slot = overflow_slot
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
