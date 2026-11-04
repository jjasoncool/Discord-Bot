"""Facebook 貼文轉發到 Discord：取貼文、發主文與圖片、傳影片。

架構定位：功能層（`services.relay`）。
  - 上層：`services.notify_server`（爬蟲通知後發新貼文）、`commands.article_commands`（`/resend_article`）。
  - 下層：爬蟲 API、`utils.discord_content`、`services.events.event_scheduler`（公告建活動）。

介面：
- `check_and_send_fb_posts(channel_ids)`：發最近 7 天還沒送過的貼文。
- `send_fb_post_to_channel(channel_id, post, force_event_rebuild=, notes=)`：發一篇。
- `fetch_fb_post_for_resend(id, notes=)`：重發用，先請爬蟲重開貼文拿新網址。

規則：
- 主文一送出就記已送，之後的圖片或影片失敗只記 log，不再重來：重來會讓主文每小時多發一次。
- 影片貼文一律傳影片，不放封面：高畫質超過上限就改標準畫質，都傳不上去才給文章連結。

例外與決策：
- bot 開不了 FB（沒有瀏覽器，走 IPv4 又會被導去登入頁），圖片與影片的檔案網址約 4.4 天過期，
  要新網址只能請爬蟲重開文章（文章網址不會過期），所以影片與新網址都不存。
- 影片不沿用 `_download_image_as_file`：那邊總時限 10 秒、上限 25 MB、副檔名預設 .jpg，影片都不合用。
- 「主文一送出就記已送」有一個缺口：帶附件的主文被退回、退純文字送出後，`post_to_channel` 補送附件又失敗時會
  丟例外，這篇記不到已送，下一輪會再發一次。那段在共用元件裡，其他轉發來源也走它，所以沒有在這裡繞過。
"""
import asyncio
import aiohttp
import io
import logging
import re
import discord
from datetime import datetime
from typing import List, Dict, Optional
from urllib.parse import urlparse, urlunparse

from utils.discord_content import post_to_channel, upload_limit
from .base_monitor import BaseContentMonitor, content_send_lock

logger = logging.getLogger(__name__)

#: 請爬蟲重開一篇的總時限（秒）：可能要先排隊等每小時那一輪（最多 4 分鐘），再開頁、翻照片
_REFRESH_TIMEOUT_SECONDS = 480
#: 影片下載的時限：總時限，以及多久沒收到資料就放棄
_VIDEO_DOWNLOAD_TIMEOUT = aiohttp.ClientTimeout(total=180, sock_read=30)
_VIDEO_CHUNK_BYTES = 1024 * 1024
#: 一篇最多傳幾支影片，其餘給連結
_MAX_VIDEOS = 3
#: 送到 Discord 可能碰到的錯誤：Discord 回錯誤，或連線中斷、逾時（這些 discord.py 不會包成 HTTPException）
_SEND_ERRORS = (discord.HTTPException, aiohttp.ClientError, asyncio.TimeoutError, OSError)


class FBMonitor(BaseContentMonitor):
    """Facebook 貼文監控類別"""

    def __init__(self, bot, scraper_api_url: str = "http://scraper:8000"):
        super().__init__(bot, scraper_api_url)

    # ── FB URL 清洗 ──

    @staticmethod
    def _sanitize_fb_hashtag_url(url: str) -> str:
        """僅在 Discord 顯示前清洗 Facebook hashtag URL，保留原始資料不變。"""
        if not url:
            return ""
        try:
            parsed = urlparse(url.strip())
        except Exception:
            return url

        if "facebook.com" not in parsed.netloc or "/hashtag/" not in parsed.path:
            return url

        clean_path = parsed.path.rstrip("/")
        return urlunparse((parsed.scheme or "https", "www.facebook.com", clean_path, "", "", ""))

    def _sanitize_fb_text_md_for_discord(self, text_md: str) -> str:
        """清洗 Discord 顯示用的 FB markdown，不改動資料來源。
        1. hashtag URL 去追蹤參數
        2. 純文字 URL → [連結](URL)
        """
        if not text_md:
            return ""

        # 1) 清洗 hashtag markdown link
        def _replace_hashtag(match: re.Match) -> str:
            label = match.group(1)
            url = match.group(2)
            sanitized_url = self._sanitize_fb_hashtag_url(url)
            return f"[{label}]({sanitized_url})"

        hashtag_pattern = re.compile(r"\[(#[^\]]+)\]\((https?://[^)]+)\)")
        result = hashtag_pattern.sub(_replace_hashtag, text_md)

        # 2) 純文字 URL → [連結](URL)（不處理已在 markdown 中的 URL）
        result = re.sub(r"(?<!\()(https?://[^\s\n\)]+)", r"[連結](\1)", result)

        return result

    # ── API 呼叫 ──

    async def fetch_recent_fb_posts(self, days: int = 7) -> List[Dict]:
        """從 scraper API 取得最近的 FB 貼文"""
        return await self.fetch_content_from_api("/api/fb_posts/recent", {"days": days, "limit": 20})

    async def fetch_fb_post_by_id(self, fb_post_id: int) -> Optional[Dict]:
        """從 scraper API 根據資料庫 ID 取得單篇 FB 貼文。"""
        try:
            url = f"{self.scraper_api_url}/api/fb_posts/{fb_post_id}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=15) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get('success') and data.get('post'):
                            logger.info(f"成功根據資料庫 ID {fb_post_id} 取得 FB 貼文")
                            return data['post']

                        logger.warning(
                            "FB API 回應成功但內容無效（id=%s）: success=%s has_post=%s",
                            fb_post_id,
                            data.get('success'),
                            bool(data.get('post')),
                        )
                        return None

                    try:
                        error_data = await response.json()
                    except Exception:
                        error_data = {}

                    logger.error(
                        "FB API 請求失敗（id=%s），狀態碼: %s, 細節: %s",
                        fb_post_id,
                        response.status,
                        error_data.get('detail') or error_data.get('message')
                    )
                    return None
        except asyncio.TimeoutError:
            logger.error(f"根據資料庫 ID {fb_post_id} 取得 FB 貼文逾時")
            return None
        except Exception as e:
            logger.error(f"根據資料庫 ID {fb_post_id} 取得 FB 貼文時發生錯誤: {e}")
            return None

    async def refresh_media(self, fb_post_id: int) -> Optional[Dict]:
        """請爬蟲重開這篇貼文，回傳新的 images 與 videos；失敗回 None。"""
        url = f"{self.scraper_api_url}/api/fb_posts/{fb_post_id}/refresh"
        try:
            timeout = aiohttp.ClientTimeout(total=_REFRESH_TIMEOUT_SECONDS)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url) as response:
                    if response.status != 200:
                        logger.warning("重開 FB 貼文 %s 失敗，狀態碼 %s", fb_post_id, response.status)
                        return None
                    data = await response.json()
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
            logger.warning("重開 FB 貼文 %s 失敗：%s", fb_post_id, exc)
            return None
        if not data.get("success"):
            logger.warning("重開 FB 貼文 %s 失敗：%s", fb_post_id, data.get("message"))
            return None
        return data

    async def _attach_fresh_media(self, fb_post: Dict, notes: Optional[List[str]] = None) -> None:
        """把新的圖片與影片網址填進這篇。拿不到就沿用已存的圖片，影片留空（之後給連結）。"""
        fresh = await self.refresh_media(fb_post["id"])
        if fresh is None:
            fb_post["videos"] = []
            if notes is not None:
                notes.append("沒能重開原貼文，圖片用已存的網址，可能已過期" if fb_post.get("images") else "沒能重開原貼文")
            return
        fb_post["images"] = fresh.get("images") or fb_post.get("images") or []
        fb_post["videos"] = fresh.get("videos") or []
        if fb_post["videos"]:
            fb_post["has_video"] = True
        # 「+N」數的是格子，影片也佔一格，要一起算才不會全部拿到還說少
        got = len(fresh.get("images") or []) + len(fb_post["videos"])
        expected = fresh.get("expected_images")
        if expected and got < expected:
            logger.warning("重開 FB 貼文 %s 少了 %d 張（頁面表示 %d 張）", fb_post["id"], expected - got, expected)
            if notes is not None:
                notes.append(f"重開少了 {expected - got} 張（頁面表示 {expected} 張）")

    async def fetch_fb_post_for_resend(self, fb_post_id: int, notes: Optional[List[str]] = None) -> Optional[Dict]:
        """重發用：除了資料庫的內容，再請爬蟲重開貼文拿新網址（已存的網址可能過期了）。"""
        fb_post = await self.fetch_fb_post_by_id(fb_post_id)
        if fb_post:
            await self._attach_fresh_media(fb_post, notes)
        return fb_post

    # ── 格式化 ──

    def format_fb_embed(self, fb_post: Dict):
        """格式化 FB 貼文為 Discord Embed"""
        # 優先使用 text_md（Discord Markdown 格式），如果沒有則使用 text
        description_text = fb_post.get('text_md') or fb_post.get('text', '')
        if fb_post.get('text_md'):
            description_text = self._sanitize_fb_text_md_for_discord(description_text)
        description = description_text[:4000] if description_text else ''

        # 優先使用 url 欄位，如果 url 是空的則使用 pfbid_url
        embed_url = fb_post.get('url') or fb_post.get('pfbid_url')

        # 優先使用 timestamp（貼文發佈時間），如果沒有則使用 created_at（資料庫記錄時間）
        timestamp_str = fb_post.get('timestamp') or fb_post.get('created_at')
        timestamp = None
        if timestamp_str:
            try:
                if timestamp_str.endswith('Z'):
                    timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                else:
                    timestamp = datetime.fromisoformat(timestamp_str)
            except ValueError as e:
                logger.warning(f"無法解析 FB 貼文時間戳 '{timestamp_str}': {e}")
                timestamp = None

        embed = discord.Embed(
            title="Facebook 貼文",
            description=description,
            color=0x1877F2,  # FB 藍色
            timestamp=timestamp,
            url=embed_url
        )

        embed.add_field(name="📘 來源", value="Facebook", inline=True)

        images = fb_post.get('images', [])
        if images:
            logger.info(f"FB 貼文 {fb_post.get('id', 'unknown')} 設定圖片: {images[0]}")
            embed.set_image(url=images[0])
        else:
            logger.info(f"FB 貼文 {fb_post.get('id', 'unknown')} 沒有圖片")

        fb_id = fb_post.get('id', '?')
        embed.set_footer(text=f"#{fb_id} 鳴潮官方 Facebook")
        return embed

    # ── 發送 ──

    @staticmethod
    async def _download_video(url: str, session: aiohttp.ClientSession, limit: int) -> Optional[io.BytesIO]:
        """下載影片到記憶體；失敗或超過 limit 回 None。邊收邊算，超過就中止，不必整支讀完才知道。"""
        try:
            async with session.get(url, timeout=_VIDEO_DOWNLOAD_TIMEOUT) as response:
                if response.status != 200:
                    logger.warning("影片下載失敗，狀態碼 %s", response.status)
                    return None
                if (response.content_length or 0) > limit:
                    logger.info("影片 %s bytes，超過上傳上限 %s", response.content_length, limit)
                    return None
                data = io.BytesIO()
                async for chunk in response.content.iter_chunked(_VIDEO_CHUNK_BYTES):
                    data.write(chunk)
                    if data.tell() > limit:
                        logger.info("影片超過上傳上限 %s，中止下載", limit)
                        return None
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            logger.warning("影片下載失敗：%s", exc)
            return None
        data.seek(0)
        return data

    async def _upload_video(self, target, reply: Dict, video: Dict) -> bool:
        """傳一支影片：高畫質超過上限或被 Discord 退回就改標準畫質。回傳有沒有傳上去。"""
        limit = upload_limit(target)
        async with aiohttp.ClientSession() as session:
            for url in (video.get("hd_url"), video.get("sd_url")):
                if not url:
                    continue
                data = await self._download_video(url, session, limit)
                if data is None:
                    continue
                try:
                    await target.send(file=discord.File(data, filename=f"fb_{video['id']}.mp4"), **reply)
                    logger.info("影片 %s 已傳上 Discord", video.get("id"))
                    return True
                except _SEND_ERRORS as exc:
                    # 連線中斷時 Discord 可能其實收到了，改傳標準畫質偶爾會多一支，總比沒有影片好
                    logger.warning("影片 %s 上傳失敗：%s", video.get("id"), exc)
        return False

    async def _send_videos(self, target, sent_message, fb_post: Dict, notes: Optional[List[str]]) -> None:
        """影片貼文：回覆主文傳影片，傳不上去的給文章連結。"""
        videos = fb_post.get("videos") or []
        if not videos and not fb_post.get("has_video"):
            return
        reply = {"reference": sent_message, "mention_author": False} if sent_message else {}
        missing = not videos or len(videos) > _MAX_VIDEOS
        for video in videos[:_MAX_VIDEOS]:
            try:
                uploaded = await self._upload_video(target, reply, video)
            except Exception as exc:  # 邊界：一支影片出錯不能擋後面的影片，也不能少了連結
                logger.error("影片 %s 傳送失敗：%s", video.get("id"), exc, exc_info=True)
                uploaded = False
            if not uploaded:
                missing = True
        if missing:
            link = fb_post.get("pfbid_url") or fb_post.get("url") or (videos[0].get("permalink_url") if videos else None)
            if link:
                await target.send(f"🎬 這篇有影片，到 Facebook 看：{link}", **reply)
            if notes is not None:
                notes.append("影片沒傳成，改放連結")

    async def _send_rest_images(self, target, images: List[str]) -> int:
        """送第 2 張起的圖片（正序、每批最多 10 張），回傳沒送成幾張。"""
        missing = 0
        chunk_size = 10
        image_chunks = [images[i:i + chunk_size] for i in range(0, len(images), chunk_size)]
        for i, chunk in enumerate(image_chunks):
            logger.info(f"[FB_FLOW] 準備發送第 {i+1} 批其餘圖片，共 {len(chunk)} 張")
            files = []
            async with aiohttp.ClientSession() as session:
                for j, image_url in enumerate(chunk):
                    original_index = sum(len(c) for c in image_chunks[:i]) + j + 2
                    logger.info(f"[FB_FLOW] 開始下載第 {original_index} 張圖片: {image_url}")

                    download_result = await self._download_image_as_file(image_url, session, max_retries=2)
                    if not download_result:
                        logger.warning(f"[FB_FLOW] ❌ 跳過無法下載圖片: {image_url}")
                        missing += 1
                        continue

                    image_data, detected_ext = download_result
                    filename = self._get_image_filename_with_ext(image_url, original_index, detected_ext)
                    files.append(discord.File(image_data, filename=filename))

            if files:
                await asyncio.sleep(0.5)
                try:
                    await target.send(files=files)
                    logger.info(f"[FB_FLOW] ✅ 第 {i+1} 批已發送 {len(files)} 張")
                except _SEND_ERRORS as exc:
                    logger.warning(f"[FB_FLOW] 第 {i+1} 批發送失敗: {exc}")
                    missing += len(files)
            else:
                logger.warning(f"[FB_FLOW] 第 {i+1} 批沒有可發送圖片")
        return missing

    async def send_fb_post_to_channel(self, channel_id: int, fb_post: Dict,
                                      *, force_event_rebuild: bool = False,
                                      notes: Optional[List[str]] = None) -> bool:
        """發送 FB 貼文到指定頻道。notes：有缺的部分（少了圖、影片沒傳成）記在這裡給操作者看。"""
        try:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                logger.error(f"找不到頻道 ID: {channel_id}")
                return False

            logger.info(f"[RESEND_ROUTE] 進入 send_fb_post_to_channel: fb_id={fb_post.get('id')}, channel_id={channel_id}")

            # 影片網址沒有存，第一次發影片貼文時才請爬蟲重開拿；多頻道時共用這次的結果
            if fb_post.get("has_video") and "videos" not in fb_post:
                await self._attach_fresh_media(fb_post, notes)

            embed = self.format_fb_embed(fb_post)

            # FB 分支：主文 + 第1張圖片（附件）同次發送，再發其餘圖片（正序）
            images = fb_post.get('images', [])

            # 1) 先送主文 + 第1張圖片（附件）
            # 改走共用 post_to_channel：文字頻道→發訊息、論壇頻道→自動開 thread
            embed.set_image(url=None)  # 禁止以 URL 連結方式顯示圖片
            sent_message = None
            missing_images = 0
            if images:
                first_image_url = images[0]
                async with aiohttp.ClientSession() as session:
                    logger.info(f"[FB_FLOW] 開始下載第 1 張圖片（主圖）: {first_image_url}")
                    main_result = await self._download_image_as_file(first_image_url, session, max_retries=2)
                    if main_result:
                        image_data, detected_ext = main_result
                        main_filename = self._get_image_filename_with_ext(first_image_url, 1, detected_ext)
                        main_file = discord.File(image_data, filename=main_filename)
                        embed.set_image(url=f"attachment://{main_filename}")
                        sent_message = await post_to_channel(channel, embed=embed, files=[main_file], thread_title=embed.title)
                        logger.info(f"[FB_FLOW] 📤 主文+第1張圖片發送完成: {main_filename}")
                    else:
                        sent_message = await post_to_channel(channel, embed=embed, thread_title=embed.title)
                        missing_images += 1
                        logger.warning(f"[FB_FLOW] ❌ 第 1 張主圖下載失敗，僅發送主文: {first_image_url}")
            else:
                sent_message = await post_to_channel(channel, embed=embed, thread_title=embed.title)
                logger.info("[FB_FLOW] 📤 發送 FB 主文完成（無圖片）")

            # 主文一送出就記已送：後面的圖或影片失敗時重來，主文會每小時多發一次
            await self.mark_content_as_sent('fbpost', fb_post['id'])

            # 後續補圖的目標：論壇→剛建立的 thread、文字→原頻道
            followup_target = sent_message.channel if sent_message else channel

            if images:
                logger.info(f"[FB_FLOW] 總共有 {len(images)} 張圖片，將以正序分段發送")
            else:
                logger.info("[FB_FLOW] 無圖片可發送")
            try:
                # 2) 再送其餘圖片（第 2 張起，正序；每批最多 10）
                missing_images += await self._send_rest_images(followup_target, images[1:])
            except Exception as exc:  # 邊界：主文已送出也記了已送，圖片壞掉不能讓這篇被當成沒送，也不能擋影片
                logger.error(f"[FB_FLOW] 貼文 {fb_post.get('id')} 的圖片送到一半失敗: {exc}", exc_info=True)
                if notes is not None:
                    notes.append("圖片送到一半失敗，請看 log")
            try:
                await self._send_videos(followup_target, sent_message, fb_post, notes)
            except Exception as exc:  # 邊界：主文已送出也記了已送，影片或連結送不出去不能讓這篇被當成沒送
                logger.error(f"[FB_FLOW] 貼文 {fb_post.get('id')} 的影片送到一半失敗: {exc}", exc_info=True)
                if notes is not None:
                    notes.append("影片送到一半失敗，請看 log")
            if missing_images and notes is not None:
                notes.append(f"少了 {missing_images} 張圖")

            # 偵測活動公告 → 自動建 Discord 伺服器活動（欄位對應/best-effort 收在 event_scheduler）
            from services.events.event_scheduler import schedule_from_fb
            await schedule_from_fb(
                self.bot, fb_post, channel_id,
                message_url=getattr(sent_message, "jump_url", None),
                force=force_event_rebuild,
            )

            logger.info(f"成功發送 FB 貼文 {fb_post['id']} 到頻道 {channel_id}")
            return True

        except Exception as e:
            logger.error(f"發送 FB 貼文到頻道失敗: {e}")
            return False

    # ── 排程 ──

    async def check_and_send_fb_posts(self, channel_ids: List[int]):
        """檢查並發送新的 FB 貼文"""
        try:
            fb_posts = await self.fetch_recent_fb_posts(days=7)

            if not fb_posts:
                logger.debug("[FB] 沒有找到新 FB 貼文")
                return

            new_posts = []
            for post in fb_posts:
                if not await self.is_content_sent('fbpost', post['id']):
                    new_posts.append(post)

            if not new_posts:
                logger.debug("[FB] 沒有新的未發送 FB 貼文")
                return

            logger.info(f"[FB] 找到 {len(new_posts)} 篇新 FB 貼文")

            # 同一篇可能同時被兩條路找到：拿到鎖後再查一次，另一條路已經送完的就不再送
            for post in new_posts:
                async with content_send_lock('fbpost', post['id']):
                    if await self.is_content_sent('fbpost', post['id']):
                        continue
                    for channel_id in channel_ids:
                        success = await self.send_fb_post_to_channel(channel_id, post)
                        if success:
                            logger.info(f"[FB] 成功發送 FB 貼文 {post['id']} 到頻道 {channel_id}")
                            await asyncio.sleep(2)

        except Exception as e:
            logger.error(f"[FB] 檢查 FB 貼文時發生錯誤: {e}")
