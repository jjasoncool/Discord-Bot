"""Discord 的共用工具：發文、切長文、換畫面、論壇標籤、上傳上限這類各功能都要用、跟功能本身無關的寫法。

架構定位：基礎層（`utils/`），列在分層守衛的 `DISCORD_HELPERS_IN_BASE`，可以 import discord，不依賴其他層。
  - 上層（誰呼叫）：轉發來源（官網、巴哈、PTT、FB、Telegram）、交易與商品市集、AI 插話與日記、
    主控台與各種面板（`commands/`）、面板置底（`utils.panel_bump`）。
  - 下層（呼叫誰）：discord.py。

介面：
  - 發文：`post_to_channel`（論壇／文字頻道自動分流、附件分批、失敗退純文字）、`send_model_text`（模型寫的文字：切段、不 @ 任何人，要 @ 的人由呼叫端指定）。
  - 長文：`split_message`、`DISCORD_MESSAGE_LIMIT`。
  - 畫面：`edit_screen`、`guarded_screen`、`layout_text`、`message_custom_ids`。
  - 論壇標籤：`find_forum_tags`（照快取找）、`ensure_forum_tags`（沒有就建）、`get_forum_tags`（找一個，舊介面）。
  - 其他：`upload_limit`、`chunk_discord_files`、`sanitize_forum_thread_title`、`linkify_image_urls`、`content_hash`。

規則：
  - 這裡只放機制，訊息長什麼樣子由呼叫端決定。
  - 建論壇標籤只走 `ensure_forum_tags`（守衛擋直接 `create_tag`）。

例外與決策：
  - 論壇標籤不用 `ForumChannel.create_tag`：它拿快取的標籤清單整份覆寫，建完又不更新快取（要等 Discord 推送頻道更新），
    連著建兩個，後一個會把前一個蓋掉。`ensure_forum_tags` 在快取缺標籤時先向 Discord 讀一次最新的清單，缺的一次送出；
    快取齊全時不多打 API。
"""
import asyncio
import hashlib
import logging
import re
from typing import Any, Awaitable, Callable, Iterable, List, Optional, Sequence

import discord

logger = logging.getLogger(__name__)

# 常見圖片副檔名（各 monitor 共用）
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp")

#: Discord 一則訊息的字數上限
DISCORD_MESSAGE_LIMIT = 2000


def sanitize_forum_thread_title(title: str, content: str = "", fallback: str = "（無標題）") -> str:
    """清理 forum thread 標題（Discord 上限 100 字元）。
    若 title 為空，嘗試從 content 取前 20 字作為替代。
    """
    sanitized = (title or "").replace("\n", " ").replace("\r", " ").strip()
    sanitized = re.sub(r"\s+", " ", sanitized)
    if not sanitized:
        content_preview = (content or "").replace("\n", " ").replace("\r", " ").strip()
        content_preview = re.sub(r"\s+", " ", content_preview)
        sanitized = content_preview[:20] if content_preview else fallback
    return sanitized[:100]


def linkify_image_urls(text: str) -> str:
    """將文字中的裸圖片 URL 轉為 markdown 連結 [🖼 圖片](url)。"""
    def _replace(match):
        url = match.group(0)
        lower = url.lower().split("?")[0]  # 去掉 query string 再判斷
        if any(lower.endswith(ext) for ext in IMAGE_EXTENSIONS):
            return f"[🖼 圖片]({url})"
        return url
    return re.sub(r'https?://[^\s<>"]+', _replace, text)


def layout_text(view: "discord.ui.LayoutView") -> str:
    """新版版面（LayoutView）上所有文字接成一段（log、測試比對用；Discord 端怎麼排不管）。"""
    return "\n".join(item.content for item in view.walk_children() if isinstance(item, discord.ui.TextDisplay))


async def edit_screen(interaction: discord.Interaction, *, view, embed: Optional[discord.Embed] = None,
                      content: Optional[str] = None) -> None:
    """換畫面一律改互動所在的那一則訊息：還沒回應就用回應改；回應過（已切成「處理中」、或 defer 了）就改原訊息。

    新版版面（LayoutView）的畫面只給 view：content／embed 明確清成 None，舊的 embed 版訊息按下去才換得過去，
    本來就是新版版面的多帶無害。embed 版面板給 embed＋view。表單送出的互動（從按鈕或選單開的表單）也能這樣改。"""
    kwargs = dict(content=content, embed=embed, view=view)
    if interaction.response.is_done():
        await interaction.edit_original_response(**kwargs)
    else:
        await interaction.response.edit_message(**kwargs)


async def guarded_screen(interaction: discord.Interaction, label: str, run: Callable[[], Awaitable[None]], *,
                         rescue: Callable[[str], Awaitable[None]], log: logging.Logger = logger) -> None:
    """面板上一次操作的外殼：做壞了把畫面換回 `rescue(notice)` 給的那個並記 ERROR（不能停在「處理中」全灰、沒按鈕）；
    救援畫面也改不了（訊息在做的途中被刪）只記一行 WARNING，不讓例外再往外丟。log 給呼叫端自己的 logger，才看得出是哪個面板。"""
    try:
        await run()
    except Exception as exc:  # 邊界：面板按鈕的一次互動；要把畫面從「處理中」救回來，細節進 log
        log.error("%s 失敗：%s", label, exc, exc_info=True)
        try:
            await rescue(f"❌ 操作失敗（{type(exc).__name__}），請再試一次；細節在 log。")
        except discord.HTTPException as rescue_exc:
            log.warning("%s：救援畫面也改不了（面板可能已被刪）：%s", label, rescue_exc)


def message_custom_ids(message) -> set[str]:
    """一則訊息上所有按鈕與選單的 custom_id（新版版面的容器、區段與區段右邊的按鈕都走進去；最多三層）。"""
    found: set[str] = set()

    def walk(node, depth: int) -> None:
        custom_id = getattr(node, "custom_id", None)
        if isinstance(custom_id, str):
            found.add(custom_id)
        if depth >= 3:
            return
        children = getattr(node, "children", None)
        for child in children if isinstance(children, (list, tuple)) else ():
            walk(child, depth + 1)
        accessory = getattr(node, "accessory", None)
        if accessory is not None and isinstance(getattr(accessory, "custom_id", None), str):
            found.add(accessory.custom_id)

    components = getattr(message, "components", None)
    for component in components if isinstance(components, (list, tuple)) else ():
        walk(component, 0)
    return found


def split_message(text: str, limit: int = DISCORD_MESSAGE_LIMIT) -> list[str]:
    """把長文切成多段，每段長度 <= limit（Telegram 轉發的長貼文、/askai 的長回答共用）。

    盡量在換行邊界切（其次空白），避免把句子或段落切斷；
    都太靠前（不到半段）才硬切，以免切出過短的碎段。保留全文不丟內容。

    暴雷標記安全：切點不會落在一對 `||` 中間；切完再平衡每段的 `||`，
    若暴雷段跨越切點，前段補 `||` 收尾、下段補 `||` 開頭，避免標記破掉、暴雷外洩——這時一段最多會比
    limit 多 4 個字（前後各補一組），呼叫端要留餘裕。
    """
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        window = remaining[:limit]
        cut = window.rfind("\n")
        if cut < limit // 2:
            space_cut = window.rfind(" ")
            cut = space_cut if space_cut >= limit // 2 else limit
        # 避免把暴雷標記 || 從兩個 pipe 中間切開（讓整組 || 落到下一段）
        if 0 < cut < len(remaining) and remaining[cut - 1] == "|" and remaining[cut] == "|":
            cut -= 1
        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    if remaining:
        chunks.append(remaining)

    # 平衡暴雷標記：每段 || 數須成對；落單代表暴雷段跨越切點，補成對並接到下一段
    balanced: list[str] = []
    carry_open = False
    for chunk in chunks:
        if carry_open:
            chunk = "||" + chunk
        if chunk.count("||") % 2 == 1:
            chunk = chunk + "||"
            carry_open = True
        else:
            carry_open = False
        balanced.append(chunk)
    return balanced


async def send_model_text(
    send: Callable[..., Awaitable[Any]],
    text: str,
    *,
    mention_users: Sequence[discord.abc.Snowflake] = (),
    limit: int = DISCORD_MESSAGE_LIMIT - 10,
) -> list[Any]:
    """把模型寫的文字送到 Discord：切成放得下的幾段，預設不提及任何人。

    模型的輸出不可信：被聊天內容誘導寫出 @everyone、身分組或 <@某人> 時，送出去也不能真的通知到；
    要 @ 的人（例：/askai 的發問者）由呼叫端用 mention_users 指定，只放在第一段。reply 也不 @ 被回的人。
    send 是呼叫端的送出函式（channel.send、message.reply、interaction.followup.send），回到哪裡由它決定；
    切段預設留 10 字餘裕，給暴雷標記跨切點時補 ||。回傳各段送出的訊息（照 send 的回傳值）。
    /askai、插話、日記都走這裡，新的送出路徑也一樣，擋提及的規則只有這一份。
    """
    sent: list[Any] = []
    for index, part in enumerate(split_message(text, limit)):
        users: Any = list(mention_users) if index == 0 and mention_users else False
        mentions = discord.AllowedMentions(everyone=False, roles=False, users=users, replied_user=False)
        sent.append(await send(part, allowed_mentions=mentions))
    return sent


def content_hash(text: str) -> str:
    """快速 hash，用來比對 embed 內容是否有變化。"""
    return hashlib.md5(text.encode("utf-8")).hexdigest()


#: 離上傳上限留一點餘裕：Discord 算的是整個請求，不只檔案本身
_UPLOAD_MARGIN = 512 * 1024
#: 拿不到伺服器資訊時的上限（沿用 Telegram 轉發原本的值；實際發文都有伺服器資訊，走不到這裡）
_FALLBACK_UPLOAD_LIMIT = 25 * 1024 * 1024 - _UPLOAD_MARGIN


def upload_limit(target) -> int:
    """這個頻道（或伺服器）能傳的單檔上限。每次從伺服器讀，加成等級變了就跟著變。"""
    guild = getattr(target, "guild", target)
    limit = getattr(guild, "filesize_limit", None)
    return limit - _UPLOAD_MARGIN if limit else _FALLBACK_UPLOAD_LIMIT


def chunk_discord_files(files: List[discord.File], chunk_size: int = 10) -> List[List[discord.File]]:
    """將 Discord 附件依 Discord 限制切成多批。"""
    if not files:
        return []
    return [files[i:i + chunk_size] for i in range(0, len(files), chunk_size)]


async def get_forum_tags(channel: discord.ForumChannel, tag_name: str) -> List[discord.ForumTag]:
    """從 forum channel 取得指定名稱的 tag（找不到回空的，不建）。"""
    return list(find_forum_tags(channel, [tag_name]).values())


def find_forum_tags(forum: discord.ForumChannel, names: Iterable[str]) -> dict[str, discord.ForumTag]:
    """論壇上這幾個名字的標籤（照 discord.py 的快取）；沒有的不在結果裡。"""
    wanted = set(names)
    return {tag.name: tag for tag in forum.available_tags if tag.name in wanted}


#: 每個論壇一把：建標籤是整份清單覆寫，同時建的兩次要排隊
_TAG_LOCKS: dict[int, asyncio.Lock] = {}


async def ensure_forum_tags(forum: discord.ForumChannel, names: Iterable[str]) -> dict[str, discord.ForumTag]:
    """論壇上這幾個名字的標籤，還沒有的先建；建不了（多半缺「管理頻道」權限）的不在結果裡、記 WARNING。

    快取裡都有就直接回；缺的話先向 Discord 讀一次最新的標籤清單（剛建好的快取可能還沒有），再把缺的一次送出。"""
    names = list(dict.fromkeys(names))
    found = find_forum_tags(forum, names)
    if len(found) == len(names):
        return found
    async with _TAG_LOCKS.setdefault(forum.id, asyncio.Lock()):
        try:
            fresh = await forum.guild.fetch_channel(forum.id)
        except discord.HTTPException:
            logger.warning("論壇標籤：讀不到論壇 %s 最新的標籤清單", forum.id, exc_info=True)
            return found
        found = find_forum_tags(fresh, names)
        missing = [name for name in names if name not in found]
        if not missing:
            return found
        try:
            edited = await fresh.edit(available_tags=[*fresh.available_tags,
                                                      *(discord.ForumTag(name=name) for name in missing)])
        except discord.HTTPException:
            logger.warning("論壇標籤：在論壇 %s 建 %s 失敗（缺「管理頻道」權限？）", forum.id, missing, exc_info=True)
            return found
        logger.info("論壇標籤：在論壇 %s 建了 %s", forum.id, missing)
        return find_forum_tags(edited, names) if edited is not None else found


async def post_to_channel(
    channel: discord.abc.GuildChannel,
    *,
    content: Optional[str] = None,
    embed: Optional[discord.Embed] = None,
    embeds: Optional[List[discord.Embed]] = None,
    files: Optional[List[discord.File]] = None,
    thread_title: Optional[str] = None,
    tags: Optional[List[discord.ForumTag]] = None,
    follow_up_label: Optional[str] = None,
    files_per_message: int = 10,
    view: Optional[discord.ui.View] = None,
    allowed_mentions: Optional[discord.AllowedMentions] = None,
) -> Optional[discord.Message]:
    """依「綁定的頻道型別」自動決定發文方式，並穩健處理附件：

      - ForumChannel          → create_thread()，每則開一個新 thread
        （thread_title 當標題，空時自動從 content 取前 20 字；tags 會帶成 applied_tags）。
      - TextChannel / Thread  → send()，直接發一則訊息。

    附件處理（兩種型別一致）：
      - 第一則最多帶 files_per_message 張附件，其餘自動分批以後續訊息補送。
      - 若「帶附件的第一則」因 HTTPException 失敗（多半是檔案太大/上傳失敗），
        自動退成純文字重發，並把所有附件改走後續批次補送。
      - follow_up_label 當第一個補送批次的說明文字（例：「本文附圖（後續補送）」）。
      - view（按鈕、選單）只掛在第一則；退成純文字重發時也會帶著。
      - allowed_mentions 給轉貼別人訊息的呼叫端用（例：封存對話），免得內容裡的 @ 又通知一次。

    回傳首則 discord.Message（forum 為 thread 首則）；呼叫端可用 msg.channel
    取得 thread / 文字頻道繼續發後續內容（留言等），forum / text 寫法一致。

    這是給「要同時支援論壇或文字頻道」的功能用的共用入口；
    現有只發單一型別的程式可逐步改用它，但不是必須。
    """
    files = list(files or [])
    initial_files = files[:files_per_message]
    remaining_files = files[files_per_message:]

    async def _post_initial(attachments: List[discord.File]) -> Optional[discord.Message]:
        kwargs = {}
        if content is not None:
            kwargs["content"] = content
        if embed is not None:
            kwargs["embed"] = embed
        if embeds is not None:
            kwargs["embeds"] = embeds
        if attachments:
            kwargs["files"] = attachments
        if view is not None:
            kwargs["view"] = view
        if allowed_mentions is not None:
            kwargs["allowed_mentions"] = allowed_mentions
        if isinstance(channel, discord.ForumChannel):
            if tags:
                kwargs["applied_tags"] = tags
            title = sanitize_forum_thread_title(thread_title or "", content or "")
            created = await channel.create_thread(name=title, **kwargs)
            # discord.py 2.x 的 create_thread 回傳 ThreadWithMessage(.thread/.message)
            return getattr(created, "message", None)
        return await channel.send(**kwargs)

    try:
        starter = await _post_initial(initial_files)
    except discord.HTTPException:
        if not initial_files:
            raise  # 不是附件造成的失敗，往上拋給呼叫端處理
        logger.error(
            "post_to_channel 帶附件發文失敗，改用純文字 fallback，附件改走後續批次補送",
            exc_info=True,
        )
        starter = await _post_initial([])
        remaining_files = files  # 全部附件都改後送

    target = getattr(starter, "channel", None)
    if target is not None and remaining_files:
        for idx, chunk in enumerate(chunk_discord_files(remaining_files, files_per_message)):
            if idx == 0 and follow_up_label:
                await target.send(follow_up_label, files=chunk)
            else:
                await target.send(files=chunk)
            await asyncio.sleep(0.5)

    return starter
