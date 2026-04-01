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
# 巴哈小屋個人頁 URL 模板
BAHAMUT_PROFILE_URL = "https://home.gamer.com.tw/profile/index.php?owner={user_id}"
# 常見圖片副檔名
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp")


def _author_link(name: str, user_id: str) -> str:
    """將作者名稱轉為巴哈小屋連結。"""
    if user_id:
        url = BAHAMUT_PROFILE_URL.format(user_id=user_id)
        return f"[**{name}**]({url})"
    return f"**{name}**"


def _linkify_image_urls(text: str) -> str:
    """將文字中的裸圖片 URL 轉為 markdown 連結。"""
    import re
    def _replace(match):
        url = match.group(0)
        # 檢查是否為圖片 URL
        lower = url.lower().split("?")[0]  # 去掉 query string 再判斷
        if any(lower.endswith(ext) for ext in IMAGE_EXTENSIONS):
            return f"[🖼 圖片]({url})"
        return url
    return re.sub(r'https?://[^\s<>"]+', _replace, text)


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
        content = _linkify_image_urls(content)
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

    async def _get_forum_tags(self, channel: discord.ForumChannel) -> List[discord.ForumTag]:
        """取得巴哈 forum tag。"""
        tags = []
        for tag in channel.available_tags:
            if tag.name == BAHAMUT_FORUM_TAG_NAME:
                tags.append(tag)
                break
        return tags

    @staticmethod
    def _sanitize_thread_title(title: str) -> str:
        """清理 thread 標題（Discord 上限 100 字元）。"""
        title = title.replace("\n", " ").strip()
        if len(title) > 100:
            title = title[:97] + "..."
        if not title:
            title = "（無標題）"
        return title

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

            # 檢查是否已發送過
            content_key = f"bahamut:{board_id}:{post_id}"
            if await self.is_content_sent("bahamut", content_key):
                logger.info("巴哈討論串已存在，跳過: %s", content_key)
                # TODO: 未來改為增量更新模式
                return None

            # 1. 建立主文 embed + thread
            main_embed = self.format_main_post_embed(main_post)
            thread_title = self._sanitize_thread_title(main_post.get("title") or "")
            applied_tags = await self._get_forum_tags(channel)

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
