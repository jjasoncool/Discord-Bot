"""
PTT 貼文 → Discord 論壇頻道 relay 服務

從 Scraper API 取得 PTT 貼文，格式化並發布到 Forum Channel。
"""
import asyncio
import aiohttp
import json
import logging
import discord
from pathlib import Path
from typing import List, Dict, Optional
from urllib.parse import urlparse
from bs4 import BeautifulSoup

from utils.logger_config import get_discord_bot_logger, get_article_monitor_logger
from utils.discord_content import (
    sanitize_forum_thread_title,
    get_forum_tags,
    post_to_channel,
)
from .base_monitor import BaseContentMonitor

logger = get_discord_bot_logger()
article_logger = get_article_monitor_logger()


class PTTMonitor(BaseContentMonitor):
    """PTT 貼文 → Discord Forum Channel 監控器"""

    PTT_FORUM_TAG_NAME = "PTT"
    ARTICLE_RUNTIME_CONFIG_PATH = Path("/app/settings/article_runtime.json")

    def __init__(self, bot, scraper_api_url: str = "http://scraper:8000"):
        super().__init__(bot, scraper_api_url)
        self.article_runtime_config = self._load_article_runtime_config()

    def _load_article_runtime_config(self) -> Dict:
        """載入文章相關 runtime 設定。"""
        with open(self.ARTICLE_RUNTIME_CONFIG_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)

        if not isinstance(raw, dict):
            raise ValueError("article_runtime.json 格式錯誤，根節點必須是 JSON object")

        if "ptt_spoiler_keywords" not in raw:
            raise ValueError("article_runtime.json 缺少必要欄位: ptt_spoiler_keywords")

        if "ptt_comment_chunk_limit" not in raw:
            raise ValueError("article_runtime.json 缺少必要欄位: ptt_comment_chunk_limit")

        return raw

    # ── API 呼叫 ──

    async def fetch_recent_ptt_posts(self, days: int = 3) -> List[Dict]:
        """從 scraper API 取得最近的 PTT 貼文（新到舊，發送前再反轉）"""
        return await self.fetch_content_from_api(
            "/api/ptt_posts/recent",
            {"days": days, "limit": 50, "order": "desc"},
        )

    # ── 工具方法 ──

    @staticmethod
    def _build_ptt_article_key(post: Dict) -> str:
        board = str(post.get('board') or '').strip()
        article_id = str(post.get('article_id') or '').strip()
        return f"ptt:{board}:{article_id}"

    @staticmethod
    def _normalize_comment(comment: Dict) -> Dict:
        return {
            "tag": (comment.get("tag") or "").strip(),
            "user": (comment.get("user") or "").strip(),
            "content": (comment.get("content") or "").strip(),
            "time": (comment.get("time") or "").strip(),
        }

    def _format_ptt_comments_messages(self, comments: List[Dict], chunk_limit: int = 1800) -> List[str]:
        """將 PTT 留言分段成多則 Discord 訊息，避免超過長度限制。"""
        chunk_limit = int(self.article_runtime_config.get("ptt_comment_chunk_limit", chunk_limit) or chunk_limit)
        if not comments:
            return ["目前沒有留言。"]

        chunks: List[str] = []
        current_lines: List[str] = ["**留言更新**"]
        current_length = len(current_lines[0])

        for comment in comments:
            tag = (comment.get("tag") or "").strip() or "留言"
            user = (comment.get("user") or "").strip() or "未知使用者"
            content = (comment.get("content") or "").strip()
            time_text = (comment.get("time") or "").strip()
            identity_text = f"{user} ({time_text})" if time_text else user
            line = f"`{tag}` __{identity_text}__: {content}"

            projected_length = current_length + 1 + len(line)
            if projected_length > chunk_limit and len(current_lines) > 1:
                chunks.append("\n".join(current_lines))
                current_lines = ["**留言更新（續）**", line]
                current_length = len(current_lines[0]) + 1 + len(line)
            else:
                current_lines.append(line)
                current_length = projected_length

        if current_lines:
            chunks.append("\n".join(current_lines))

        return chunks

    async def _resolve_ptt_image_targets(self, text: str) -> List[str]:
        """從文字中解析可下載圖片，包含無副檔名連結（如 imgur 頁面）。"""
        if not text:
            return []

        import re
        candidates = re.findall(r'https?://[^\s<>"]+', text)
        resolved: List[str] = []
        seen: set[str] = set()

        async with aiohttp.ClientSession() as session:
            for raw_url in candidates:
                cleaned = raw_url.rstrip('.,);]\">')
                if cleaned in seen:
                    continue

                parsed = urlparse(cleaned)
                path = (parsed.path or '').lower()

                # 只接受 http/https 連結
                if parsed.scheme not in ("http", "https"):
                    logger.debug("略過非 http/https 的 PTT 圖片候選 URL: %s", cleaned)
                    continue

                # 明確排除 favicon / ico 類資源
                if path.endswith(self.DISALLOWED_IMAGE_EXTENSIONS):
                    logger.debug("略過不應抓取的 PTT 圖片候選 URL: %s", cleaned)
                    continue

                seen.add(cleaned)

                if path.endswith(self.IMAGE_EXTENSIONS):
                    resolved.append(cleaned)
                    continue

                try:
                    async with session.get(cleaned, timeout=10, allow_redirects=True, headers=self._build_request_headers()) as response:
                        if response.status != 200:
                            continue

                        content_type = (response.headers.get('content-type') or '').lower()
                        final_url = str(response.url)

                        if content_type.startswith('image/'):
                            resolved.append(final_url)
                            continue

                        if 'text/html' in content_type:
                            html = await response.text()
                            soup = BeautifulSoup(html, 'html.parser')
                            og_image = soup.find('meta', attrs={'property': 'og:image'})
                            if og_image and og_image.get('content'):
                                og_image_url = og_image['content'].strip()
                                og_parsed = urlparse(og_image_url)
                                og_path = (og_parsed.path or '').lower()
                                if og_parsed.scheme in ("http", "https") and not og_path.endswith(self.DISALLOWED_IMAGE_EXTENSIONS):
                                    resolved.append(og_image_url)
                                else:
                                    logger.debug("略過 og:image 候選 URL: %s", og_image_url)
                except Exception:
                    continue

        deduped: List[str] = []
        dedupe_seen: set[str] = set()
        for url in resolved:
            if url in dedupe_seen:
                continue
            dedupe_seen.add(url)
            deduped.append(url)
        return deduped

    def _format_ptt_post_content(self, post: Dict) -> str:
        board = post.get('board') or 'unknown'
        author = post.get('author') or '未知作者'
        url = post.get('url') or ''
        published_at = post.get('published_at') or '未知時間'
        matched_keywords = post.get('matched_keywords') or '無'
        raw_content = (post.get('content') or '').strip()
        preview = raw_content[:1500] + ('\n...（內容已截斷）' if len(raw_content) > 1500 else '')

        parts = [
            f"**作者**：{author}",
            f"**看板**：{board}",
            f"**發文時間**：{published_at}",
            f"**關鍵字**：{matched_keywords}",
        ]
        if url:
            parts.append(f"**連結**：{url}")
        if preview:
            parts.extend(["", "**內文預覽**", preview])
        return "\n".join(parts)

    # ── 發送 ──

    async def send_ptt_post_to_forum_channel(self, forum_channel_id: int, post: Dict) -> Dict:
        """將 PTT 貼文發表到指定論壇頻道。"""
        try:
            channel = self.bot.get_channel(forum_channel_id)
            if not isinstance(channel, discord.ForumChannel):
                logger.error(f"找不到論壇頻道 ID: {forum_channel_id}，或該頻道不是 ForumChannel")
                return False

            thread_title = sanitize_forum_thread_title(
                post.get('title') or '',
                post.get('content') or '',
            )
            thread_content = self._format_ptt_post_content(post)
            applied_tags = await get_forum_tags(channel, self.PTT_FORUM_TAG_NAME)

            files: List[discord.File] = []
            image_urls = await self._resolve_ptt_image_targets(post.get('content') or '')
            logger.info(
                "PTT 貼文圖片解析完成: board=%s article_id=%s title=%s image_urls=%s",
                post.get('board'),
                post.get('article_id'),
                thread_title,
                len(image_urls),
            )
            logger.debug("PTT 圖片 URL 列表: %s", image_urls)
            spoiler_keywords = self.article_runtime_config.get("ptt_spoiler_keywords") or []
            spoiler_first_image = any(keyword in (post.get('title') or '') for keyword in spoiler_keywords)
            if image_urls:
                logger.info(
                    "PTT 貼文偵測到 %s 張圖片，準備和首貼一起上傳: board=%s article_id=%s",
                    len(image_urls),
                    post.get('board'),
                    post.get('article_id'),
                )
                async with aiohttp.ClientSession() as session:
                    for index, image_url in enumerate(image_urls, start=1):
                        download_result = await self._download_image_as_file(image_url, session, max_retries=2)
                        if not download_result:
                            logger.warning("PTT 圖片下載失敗，略過: %s", image_url)
                            continue

                        image_data, detected_ext = download_result
                        filename = self._get_image_filename_with_ext(image_url, index, detected_ext)
                        if spoiler_first_image and index == 1 and not filename.startswith("SPOILER_"):
                            filename = f"SPOILER_{filename}"
                        files.append(discord.File(image_data, filename=filename))

            logger.info(
                "PTT 附件準備完成: board=%s article_id=%s files=%s",
                post.get('board'),
                post.get('article_id'),
                len(files),
            )

            if len(files) > 10:
                logger.warning(
                    "PTT 附件超過 Discord 單則上限，將分批發送: board=%s article_id=%s total=%s",
                    post.get('board'),
                    post.get('article_id'),
                    len(files),
                )

            # 改走共用 post_to_channel：建立 forum thread + 首則最多 10 張附件 +
            # 其餘自動分批補送 + 帶附件失敗自動退純文字 fallback（原本手寫的這幾段都收進接口）
            sent_message = await post_to_channel(
                channel,
                content=thread_content,
                files=files,
                thread_title=thread_title,
                tags=applied_tags,
                follow_up_label="**本文附圖（超過 10 張後續補送）**",
            )
            thread = sent_message.channel if sent_message else None

            comments = post.get('comments') or []
            if thread and comments:
                logger.info(
                    "PTT 圖片補送完成，開始發送留言: board=%s article_id=%s comments=%s",
                    post.get('board'),
                    post.get('article_id'),
                    len(comments),
                )
                comment_chunks = self._format_ptt_comments_messages(comments)
                comments_message_obj = None
                for idx, comments_message in enumerate(comment_chunks):
                    sent_msg = await thread.send(comments_message)
                    if idx == 0:
                        comments_message_obj = sent_msg
            else:
                comments_message_obj = None

            logger.info(
                "成功將 PTT 貼文發布到論壇頻道: forum_channel_id=%s board=%s article_id=%s title=%s tags=%s",
                forum_channel_id,
                post.get('board'),
                post.get('article_id'),
                thread_title,
                [tag.name for tag in applied_tags] if applied_tags else [],
            )
            return {
                "ok": True,
                "thread_id": thread.id if thread else None,
                "thread_name": thread_title,
                "comment_message_id": comments_message_obj.id if comments_message_obj else None,
                "comments_count": len(comments),
            }
        except Exception as e:
            logger.error(f"發送 PTT 貼文到論壇頻道失敗: {e}", exc_info=True)
            return {"ok": False}

    # ── 排程 ──

    async def check_and_send_new_ptt_posts(self, forum_channel_ids: List[int]):
        """檢查並發送新的 PTT 貼文到指定論壇頻道。"""
        try:
            posts = await self.fetch_recent_ptt_posts(days=3)
            if not posts:
                article_logger.debug("[PTT] 沒有找到新 PTT 貼文")
                return

            valid_posts: List[Dict] = []
            for post in posts:
                article_key = self._build_ptt_article_key(post)
                if article_key != 'ptt::':
                    valid_posts.append(post)

            if not valid_posts:
                article_logger.debug("[PTT] 沒有可處理的 PTT 貼文")
                return

            # 先從 API 以新到舊抓資料，實際發送前再反轉成舊到新
            valid_posts = list(reversed(valid_posts))

            article_logger.debug(f"[PTT] 本輪檢查 {len(valid_posts)} 篇 PTT 貼文")
            for post in valid_posts:
                article_key = self._build_ptt_article_key(post)
                state = await self.get_ptt_state(article_key)
                new_comments = [self._normalize_comment(item) for item in (post.get('comments') or [])]
                synced_comments_count = int(state.get('synced_comments_count', 0) or 0)
                delta_comments = new_comments[synced_comments_count:] if len(new_comments) > synced_comments_count else []

                if not await self.is_content_sent('ptt', article_key):
                    sent_any = False
                    for channel_id in forum_channel_ids:
                        result = await self.send_ptt_post_to_forum_channel(channel_id, post)
                        if result.get('ok'):
                            sent_any = True
                            await self.update_ptt_state(article_key, {
                                "thread_id": result.get('thread_id'),
                                "synced_comments_count": len(new_comments),
                            })
                            await asyncio.sleep(1)

                    if sent_any:
                        await self.mark_content_as_sent('ptt', article_key)
                    continue

                if not delta_comments:
                    continue

                for channel_id in forum_channel_ids:
                    thread_id = state.get('thread_id')
                    if not thread_id:
                        continue

                    thread = self.bot.get_channel(thread_id)
                    if not isinstance(thread, discord.Thread):
                        continue

                    delta_messages = self._format_ptt_comments_messages(delta_comments)
                    for delta_message in delta_messages:
                        await thread.send(delta_message)
                        await asyncio.sleep(1)

                await self.update_ptt_state(article_key, {
                    "thread_id": state.get('thread_id'),
                    "synced_comments_count": len(new_comments),
                })
        except Exception as e:
            logger.error(f"[PTT] 檢查新 PTT 貼文時發生錯誤: {e}", exc_info=True)

    async def start_ptt_monitoring(self, forum_channel_ids: List[int], check_interval: int = 600):
        """開始監控 PTT 貼文並發送到論壇頻道。"""
        article_logger.info(f"[PTT] 開始監控 PTT 貼文，檢查間隔: {check_interval} 秒")

        while True:
            try:
                await self.check_and_send_new_ptt_posts(forum_channel_ids)
                await asyncio.sleep(check_interval)
            except Exception as e:
                article_logger.error(f"[PTT] 監控循環發生錯誤: {e}")
                await asyncio.sleep(300)
