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
from services.base_monitor import BaseContentMonitor

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
# 主文內文截斷上限
CONTENT_TRUNCATE_LIMIT = 3500
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
    def format_main_post_embed(main_post: Dict) -> discord.Embed:
        """格式化主文 embed（藍色）。"""
        title = main_post.get("title") or "（無標題）"
        author = main_post.get("author_name") or "未知"
        author_id = main_post.get("author_id") or ""
        category = main_post.get("category") or ""
        gp = main_post.get("gp_count", 0)
        bp = main_post.get("bp_count", 0)
        url = main_post.get("url") or ""
        published_at = main_post.get("published_at") or ""
        content = main_post.get("content") or ""

        # 組合 description
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

        lines.append("")  # 空行分隔
        lines.append("───────────────")

        if content:
            if len(content) > CONTENT_TRUNCATE_LIMIT:
                content = content[:CONTENT_TRUNCATE_LIMIT] + "\n\n⋯（內文過長，已截斷）"
            lines.append(content)

        description = "\n".join(lines)
        # 確保不超過 embed 上限
        if len(description) > EMBED_DESC_LIMIT:
            description = description[:EMBED_DESC_LIMIT - 20] + "\n\n⋯（已截斷）"

        embed = discord.Embed(
            title=title[:256],  # embed title 上限 256
            description=description,
            color=COLOR_MAIN_POST,
        )

        # 附圖：取第一張作為 thumbnail
        images = main_post.get("content_images") or []
        if images:
            embed.set_image(url=images[0])

        return embed

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

        if content:
            if len(content) > CONTENT_TRUNCATE_LIMIT:
                content = content[:CONTENT_TRUNCATE_LIMIT] + "\n\n⋯（內文過長，已截斷）"
            lines.append(content)

        description = "\n".join(lines)
        if len(description) > EMBED_DESC_LIMIT:
            description = description[:EMBED_DESC_LIMIT - 20] + "\n\n⋯（已截斷）"

        embed = discord.Embed(
            title=f"📝 回覆 #{reply_index}",
            description=description,
            color=COLOR_REPLY,
        )

        images = reply.get("content_images") or []
        if images:
            embed.set_image(url=images[0])

        return embed

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

            board_id = thread_data.get("board_id", "")
            post_id = thread_data.get("post_id", "")

            # 檢查是否已發送過 → 走增量更新
            content_key = f"bahamut:{board_id}:{post_id}"
            if await self.is_content_sent("bahamut", content_key):
                return await self._update_existing_thread(
                    forum_channel_id, board_id, post_id, thread_data,
                )

            # 1. 建立主文 embed + thread
            main_embed = self.format_main_post_embed(main_post)
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

            # 2. 處理主文留言 + 預建留言格
            main_sn = main_post.get("sn", "")
            main_state = await self._send_post_comments(
                thread=thread,
                post_data=main_post,
            )
            # 主文 msg_id = thread 首則訊息（create_thread 回傳的 message）
            starter_message = created.message if hasattr(created, "message") else None
            main_state["msg_id"] = starter_message.id if starter_message else thread.id
            state["posts"][main_sn] = main_state

            # 3. 處理回覆文章
            replies = thread_data.get("replies") or []
            for idx, reply in enumerate(replies, start=2):
                reply_embed = self.format_reply_embed(reply, idx)
                reply_msg = await thread.send(embed=reply_embed)
                await asyncio.sleep(SEND_DELAY)

                reply_sn = reply.get("sn", "")
                reply_state = await self._send_post_comments(
                    thread=thread,
                    post_data=reply,
                )
                reply_state["msg_id"] = reply_msg.id
                state["posts"][reply_sn] = reply_state

            # 4. 寫入 state DB（含 sent_content 去重 + forum_thread_state）
            db = await self._get_state_db()
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
                    logger.error("增量更新失敗：找不到 thread %s", thread_id)
                    return None

            main_post = thread_data.get("main_post", {})
            new_replies = thread_data.get("replies") or []
            guild_id = thread.guild.id

            # 1. 更新主文 embed（GP/BP 同步，有變化才 edit）
            main_sn = main_post.get("sn", "")
            main_post_state = old_state["posts"].get(main_sn)
            if main_post_state and main_post_state.get("msg_id"):
                try:
                    updated_embed = self.format_main_post_embed(main_post)
                    new_hash = content_hash(updated_embed.description or "")
                    main_msg = await thread.fetch_message(main_post_state["msg_id"])
                    old_hash = content_hash(main_msg.embeds[0].description or "") if main_msg.embeds else ""
                    if new_hash != old_hash:
                        await main_msg.edit(embed=updated_embed)
                        logger.info("增量更新：已更新主文 embed sn=%s", main_sn)
                    else:
                        logger.debug("增量更新：主文無變化，跳過 sn=%s", main_sn)
                except Exception as e:
                    logger.warning("增量更新：更新主文 embed 失敗 sn=%s: %s", main_sn, e)

            # 2. 更新既有回覆的 embed（GP/BP 同步，有變化才 edit）
            for reply in new_replies:
                reply_sn = reply.get("sn", "")
                reply_state = old_state["posts"].get(reply_sn)
                if reply_state and reply_state.get("msg_id"):
                    try:
                        reply_idx = next(
                            (i for i, r in enumerate(new_replies, start=2) if r.get("sn") == reply_sn),
                            2,
                        )
                        updated_embed = self.format_reply_embed(reply, reply_idx)
                        new_hash = content_hash(updated_embed.description or "")
                        reply_msg = await thread.fetch_message(reply_state["msg_id"])
                        old_hash = content_hash(reply_msg.embeds[0].description or "") if reply_msg.embeds else ""
                        if new_hash != old_hash:
                            await reply_msg.edit(embed=updated_embed)
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
                        msg = await thread.fetch_message(slot["msg_id"])
                        old_hash = content_hash(msg.embeds[0].description or "") if msg.embeds else ""
                        if new_hash != old_hash:
                            await msg.edit(embed=embed)
                            slot["used_chars"] = used_chars
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
                            msg = await thread.fetch_message(overflow_slot["msg_id"])
                            old_hash = content_hash(msg.embeds[0].description or "") if msg.embeds else ""
                            if new_hash != old_hash:
                                await msg.edit(embed=embed)
                                overflow_slot["used_chars"] = used_chars
                                logger.info("增量更新：已更新溢出格 sn=%s overflow=%s", sn, i)
                            else:
                                logger.debug("增量更新：溢出格無變化，跳過 sn=%s overflow=%s", sn, i)
                        except Exception as e:
                            logger.warning("增量更新：edit 溢出格失敗 sn=%s overflow=%s: %s", sn, i, e)

                # 需要新的溢出格？
                total_existing_slots = len(slots) + len(overflow_slots)
                if len(all_comment_slots) > total_existing_slots:
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
                reply_embed = self.format_reply_embed(reply, new_reply_idx)
                reply_msg = await thread.send(embed=reply_embed)
                await asyncio.sleep(SEND_DELAY)

                reply_state = await self._send_post_comments(thread=thread, post_data=reply)
                reply_state["msg_id"] = reply_msg.id
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
