"""
社群 ID 查詢 Cog — Panel / Modal / Thread section 管理。

設計重點：
- 永續面板（兩顆按鈕：🔍 查 PTT / 🎮 查巴哈），persistent View via custom_id
- 每 (guild, source, lookup_id) 唯一 public thread，命名 `[PTT] xxx` / `[巴哈] name (id)`
- 「日期 hybrid」:
    同日重查 → 刪除今日 section 所有訊息重發（delete-then-append，等同 edit 效果）
    跨日查 → append 新日期 section
- Embed slot 切割（≤ 4000 字）+ Discord reply 串接
- 色條分區：🟦 標頭 / 🟪 主文 / 🟩 留言 / ⬜ 控制訊息
- 查詢完 → 父頻道發公告通知 + bump panel
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, NamedTuple, Optional, Tuple

import discord
from discord import app_commands
from discord.ext import commands

from services.community_lookup_service import (
    BahamutCandidate,
    CommunityActivity,
    CommunityLookupService,
    HARD_CAP,
    LookupResult,
    PTT_COMMENT_MIN,
    PTT_POST_MIN,
    BAHAMUT_COMMENT_MIN,
    BAHAMUT_POST_MIN,
)
from services.state_db import StateDB
from utils.utils import ChannelConfig, safe_send_interaction_message


logger = logging.getLogger('discord_bot')

# ═══════════════════════════════════════════════════
# 常數
# ═══════════════════════════════════════════════════

COMMUNITY_PANEL_RUNTIME_FILE = "settings/community_panel_runtime.json"

EMBED_DESC_MAX = 4000          # 留 96 字 buffer
SEND_DELAY = 0.3                # slot 連發間隔
TAIPEI_TZ = timezone(timedelta(hours=8))

COLOR_HEADER = 0x3498DB         # 🟦 藍
COLOR_POSTS = 0x9B59B6          # 🟪 紫
COLOR_COMMENTS = 0x2ECC71       # 🟩 綠
COLOR_CONTROL = 0x95A5A6        # ⬜ 灰

DEFAULT_DAYS = 30
MAX_RANGE_DAYS = 180  # 6 個月上限

THREAD_AUTO_ARCHIVE_MIN = 10080  # 7 days

# Custom IDs（persistent View 需要穩定 ID）
CUSTOM_ID_PANEL_PTT = "community_lookup:panel:ptt"
CUSTOM_ID_PANEL_BAHAMUT = "community_lookup:panel:bahamut"
CUSTOM_ID_CONTROL_REFRESH = "community_lookup:control:refresh"


# ═══════════════════════════════════════════════════
# Runtime 檔（panel message_id）
# ═══════════════════════════════════════════════════

def _load_panel_runtime() -> dict:
    if not os.path.exists(COMMUNITY_PANEL_RUNTIME_FILE):
        return {}
    try:
        with open(COMMUNITY_PANEL_RUNTIME_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {
            "panel_channel_id": data.get("panel_channel_id"),
            "panel_message_id": data.get("panel_message_id"),
        }
    except Exception as e:
        logger.error(f"讀取 {COMMUNITY_PANEL_RUNTIME_FILE} 失敗: {e}", exc_info=True)
        return {}


def _save_panel_runtime(channel_id: int, message_id: int) -> None:
    try:
        os.makedirs(os.path.dirname(COMMUNITY_PANEL_RUNTIME_FILE), exist_ok=True)
        with open(COMMUNITY_PANEL_RUNTIME_FILE, "w", encoding="utf-8") as f:
            json.dump(
                {"panel_channel_id": channel_id, "panel_message_id": message_id},
                f,
                ensure_ascii=False,
                indent=2,
            )
    except Exception as e:
        logger.error(f"寫入 {COMMUNITY_PANEL_RUNTIME_FILE} 失敗: {e}", exc_info=True)
        raise


# ═══════════════════════════════════════════════════
# Embed 格式化 helpers
# ═══════════════════════════════════════════════════

def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


# 巴哈留言內部引用格式 `#B57:3966974#` → 「回 B57」
_BAHAMUT_REF_RE = re.compile(r"#B(\d+):\d+#")


def _clean_content(text: str, source: str) -> str:
    """移除 raw markup 並正規化空白。"""
    if not text:
        return ""
    cleaned = text.replace("\n", " ").strip()
    if source == "bahamut":
        cleaned = _BAHAMUT_REF_RE.sub(r"[回 B\1] ", cleaned)
    # 壓縮連續空白
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned


def _format_post_line(idx: int, a: CommunityActivity) -> str:
    content_limit = 150 if a.source == "bahamut" else 100
    content = _truncate(_clean_content(a.content, a.source), content_limit)
    time_part = (a.time or "")[:16]

    extras: List[str] = []
    is_reply = False
    if a.source == "bahamut":
        gp = a.extra.get("gp") or 0
        if gp:
            extras.append(f"GP{gp}")
        bp = a.extra.get("bp") or 0
        if bp:
            extras.append(f"BP{bp}")
        is_reply = (a.extra.get("position", 1) != 1)

    # 第一行：編號 + 動作（主文 / 回覆 XXX）
    if a.source == "bahamut" and is_reply:
        parent_title = _truncate((a.extra.get("parent_title") or a.title or "(原串)").replace("\n", " "), 50)
        head = f"**#{idx}** 🗨️ 回「{parent_title}」"
    else:
        title = _truncate((a.title or "(無標題)").replace("\n", " "), 60)
        head = f"**#{idx}** 📝 「{title}」"

    meta = f"📅 {time_part}" + (f" · {' · '.join(extras)}" if extras else "")

    # 連結
    if a.discord_jump_url:
        link_part = f"→ [🗨️ Discord 討論]({a.discord_jump_url})"
    elif a.url:
        link_part = f"→ [🌐 原文]({a.url})"
    else:
        link_part = ""

    return (
        f"{head}\n"
        f"{meta}\n"
        f"　「{content}」\n"
        + (f"{link_part}\n\n" if link_part else "\n")
    )


def _merge_ptt_comments(comments: List[CommunityActivity]) -> List[CommunityActivity]:
    """合併連續同作者 + 同 tag + 同分鐘 + 同父文的 PTT 推文。

    PTT 每則推文限約 40 中文字，一個意思常被切成多則連續推文，合併回去才符合語意。
    合併 key：(tag, time, parent_article_id)。content 直接 concat 不加空格（推文是強制字元切割，相鄰推文可能中途斷詞）。
    """
    if not comments:
        return comments
    from dataclasses import replace
    merged: List[CommunityActivity] = []
    for c in comments:
        if c.source != "ptt" or not merged:
            merged.append(c)
            continue
        prev = merged[-1]
        same = (
            prev.source == "ptt"
            and prev.extra.get("tag") == c.extra.get("tag")
            and prev.time == c.time
            and prev.extra.get("parent_article_id") == c.extra.get("parent_article_id")
        )
        if same:
            merged[-1] = replace(prev, content=(prev.content or "") + (c.content or ""))
        else:
            merged.append(c)
    return merged


def _format_comment_line(a: CommunityActivity) -> str:
    """單則留言（不含 parent title，title 由分組 header 提供）。

    不做縮排 — Discord markdown 自動折行不繼承縮排，強迫縮排反而醜。
    層級感交由 sub-header（`↪️ 回文 #N`）的單行縮排提供。
    """
    content_limit = 200 if a.source == "ptt" else 150
    content = _truncate(_clean_content(a.content, a.source), content_limit)
    time_part = (a.time or "")[:16]

    prefix_parts: List[str] = []
    if a.source == "ptt":
        tag = a.extra.get("tag")
        if tag:
            prefix_parts.append(tag)
    else:  # bahamut
        floor = a.extra.get("floor")
        if floor:
            prefix_parts.append(floor)
        gp = a.extra.get("gp") or 0
        if gp:
            prefix_parts.append(f"GP{gp}")
        bp = a.extra.get("bp") or 0
        if bp:
            prefix_parts.append(f"BP{bp}")

    prefix = " · ".join(prefix_parts)
    head = f"**{prefix}**  {time_part}" if prefix else time_part
    return f"・{head}\n　「{content}」\n"


def _group_comments_by_parent(comments: List[CommunityActivity]) -> List[Tuple[str, List[CommunityActivity]]]:
    """以 (討論串, parent_sn) 徹底分組 + 排序。

    排序規則：
    - 討論串之間：依該討論串「最新留言時間」desc（活躍的先）
    - 同討論串內多個 parent_sn 分組：依 parent_position asc（主文 #1 → 回文 #N）
    - 同 group 內留言：依時間 asc（樓層順序 B1 → B2 → B3）
    """
    if not comments:
        return []
    buckets: Dict[Tuple[str, object], List[CommunityActivity]] = {}
    for c in comments:
        title = (c.title or "(未知討論串)").replace("\n", " ")
        psn = c.extra.get("parent_sn")
        buckets.setdefault((title, psn), []).append(c)

    # 每個 bucket 內按時間 asc（樓層順序）
    for bucket in buckets.values():
        bucket.sort(key=lambda x: x.time or "")

    # 每個討論串的最新留言時間（用於討論串間排序）
    thread_latest: Dict[str, str] = {}
    for (title, _psn), bucket in buckets.items():
        latest = bucket[-1].time or ""  # bucket 已 asc，最新在最後
        if thread_latest.get(title, "") < latest:
            thread_latest[title] = latest

    items = [(title, psn, bucket) for (title, psn), bucket in buckets.items()]
    # 穩定排序：先排 secondary（同討論串內 position asc），再排 primary（討論串最新時間 desc）
    items.sort(key=lambda x: x[2][0].extra.get("parent_position") or 0)
    items.sort(key=lambda x: thread_latest.get(x[0], ""), reverse=True)
    return [(title, bucket) for title, _psn, bucket in items]


def _escape_md_link_text(text: str) -> str:
    """Markdown link 文字中的 `[` `]` 會破壞語法，簡單 escape。"""
    return text.replace("[", "⦋").replace("]", "⦌")


def _build_header_embed(
    *,
    source: str,
    lookup_id: str,
    start_date: str,
    end_date: str,
    querier: discord.abc.User,
    result: LookupResult,
    fuzzy: bool = False,
    first_query_time: Optional[datetime] = None,
    latest_query_time: Optional[datetime] = None,
) -> discord.Embed:
    source_label = "PTT" if source == "ptt" else "巴哈"
    today = datetime.now(TAIPEI_TZ).date().isoformat()

    # 巴哈對象 ID 做成搜尋超連結；PTT 維持純文字
    if source == "bahamut":
        target_str = f"[`{lookup_id}`](<https://search.gamer.com.tw/?q={lookup_id}>)"
    else:
        target_str = f"`{lookup_id}`"

    desc_parts = [
        f"📅 **{today}** 查詢紀錄",
        f"🎯 對象：{target_str} ({source_label})" + (" · 模糊" if fuzzy else ""),
        f"⏱️ 查詢區間：{start_date} ~ {end_date}",
    ]

    total_p_in = len(result.posts_in_range)
    total_p_fb = len(result.posts_fallback)
    total_c_in = len(result.comments_in_range)
    total_c_fb = len(result.comments_fallback)

    stats = [f"主文 {total_p_in}"]
    if total_p_fb:
        stats.append(f"+ 區間外補 {total_p_fb}")
    stats.append(f"/ 留言 {total_c_in}")
    if total_c_fb:
        stats.append(f"+ 區間外補 {total_c_fb}")
    desc_parts.append("📊 " + " ".join(stats))

    notes = []
    if total_p_in < PTT_POST_MIN and total_p_fb > 0:
        notes.append(f"ℹ️ 區間內主文不足 {PTT_POST_MIN}，已補撈區間外")
    if total_c_in < PTT_COMMENT_MIN and total_c_fb > 0:
        notes.append(f"ℹ️ 區間內留言不足 {PTT_COMMENT_MIN}，已補撈區間外")
    if result.hit_hard_cap:
        # PTT 因合併後數量會對不上 raw 1000，不帶數字；巴哈帶數字
        if source == "ptt":
            notes.append("⚠️ 查詢結果過多，請縮短查詢區間")
        else:
            notes.append(f"⚠️ 結果過多已截斷至 {HARD_CAP}，建議縮短查詢區間")
    if notes:
        desc_parts.append("\n" + "\n".join(notes))

    # 最初 / 最新更新
    time_lines = []
    if first_query_time:
        time_lines.append(f"最初查詢：{first_query_time.strftime('%H:%M')} @{querier.display_name}")
    if latest_query_time and first_query_time and latest_query_time != first_query_time:
        time_lines.append(f"最新更新：{latest_query_time.strftime('%H:%M')} @{querier.display_name}")
    elif latest_query_time:
        time_lines.append(f"查詢時間：{latest_query_time.strftime('%H:%M')} @{querier.display_name}")
    if time_lines:
        desc_parts.append("\n" + "\n".join(time_lines))

    embed = discord.Embed(
        description="\n".join(desc_parts),
        color=COLOR_HEADER,
    )
    return embed


class _CommentBlock(NamedTuple):
    """一個不可切開的留言區塊：sub-header + 其下所有 comments。"""
    thread_title: str                # 用於判斷 thread 是否切換（`__sep__` 為保底分隔符）
    thread_header_line: str          # "📌 **[title](url)**\n"
    sub_header_line: str             # "　↪️ *[回文 #N](url)*\n" 或 ""
    comment_lines: List[str]         # 留言 lines


def _mark_continued(thread_header_line: str) -> str:
    """把 `📌 **...**\\n` 改成 `📌 **...** *(續)*\\n`；空字串不變。"""
    if not thread_header_line:
        return ""
    if thread_header_line.endswith("**\n"):
        return thread_header_line[:-3] + "** *(續)*\n"
    return thread_header_line


def _build_comment_blocks(comments: List[CommunityActivity]) -> List[_CommentBlock]:
    """由 comments 產生不可切的 blocks。排序/分組由 _group_comments_by_parent 處理。"""
    if not comments:
        return []
    blocks: List[_CommentBlock] = []
    groups = _group_comments_by_parent(comments)
    last_thread_title: Optional[str] = None
    last_parent_sn: Optional[object] = None
    for title, bucket in groups:
        title_str = _truncate(title.replace("\n", " "), 60)
        first = bucket[0]
        parent_url = next((c.url for c in bucket if c.url), None)
        is_reply = bool(first.extra.get("parent_is_reply"))
        parent_sn = first.extra.get("parent_sn")

        if parent_url:
            thread_header = f"📌 **[{_escape_md_link_text(title_str)}]({parent_url})**\n"
        else:
            thread_header = f"📌 **{title_str}**\n"

        thread_changed = title_str != last_thread_title
        need_subheader = False
        if thread_changed:
            if is_reply:
                need_subheader = True
        else:
            if parent_sn != last_parent_sn:
                need_subheader = True

        sub_header = ""
        if need_subheader:
            if is_reply:
                pos = first.extra.get("parent_position")
                label_text = f"回文 #{pos}" if pos else "回文"
            else:
                label_text = "主文"
            if parent_sn and first.source == "bahamut":
                sub_url = f"https://forum.gamer.com.tw/Co.php?bsn={first.board}&sn={parent_sn}"
                sub_header = f"　↪️ *[{label_text}]({sub_url})*\n"
            else:
                sub_header = f"　↪️ *{label_text}*\n"

        comment_lines = [_format_comment_line(c) for c in bucket]
        blocks.append(_CommentBlock(
            thread_title=title_str,
            thread_header_line=thread_header,
            sub_header_line=sub_header,
            comment_lines=comment_lines,
        ))
        last_thread_title = title_str
        last_parent_sn = parent_sn
    return blocks


_SEPARATOR_BLOCK = _CommentBlock(
    thread_title="__sep__",
    thread_header_line="",
    sub_header_line="━━━ 以下為區間外補撈 ━━━\n\n",
    comment_lines=[],
)


def _pack_comment_blocks(
    blocks_in: List[_CommentBlock],
    blocks_fb: List[_CommentBlock],
    color: int,
) -> List[discord.Embed]:
    """Block-aware 打包：block 不會被切開；跨 embed 時重印 `📌 (續)` 保留 context。"""
    section_header = "### 💬 留言\n"
    all_blocks: List[_CommentBlock] = list(blocks_in)
    if blocks_fb:
        all_blocks.append(_SEPARATOR_BLOCK)
        all_blocks.extend(blocks_fb)
    if not all_blocks:
        return [discord.Embed(description=section_header + "（無資料）", color=color)]

    embeds: List[discord.Embed] = []
    buf: List[str] = [section_header]
    buf_len = len(section_header)
    last_thread_in_buf: Optional[str] = None

    def flush():
        nonlocal buf, buf_len, last_thread_in_buf
        if buf_len > len(section_header):
            embeds.append(discord.Embed(description="".join(buf), color=color))
        buf = [section_header]
        buf_len = len(section_header)
        last_thread_in_buf = None

    for b in all_blocks:
        # 分隔 block：不帶 thread context
        if b.thread_title == "__sep__":
            effective = b.sub_header_line
            if buf_len + len(effective) > EMBED_DESC_MAX and buf_len > len(section_header):
                flush()
            buf.append(effective)
            buf_len += len(effective)
            last_thread_in_buf = None
            continue

        # 同 thread 繼續 → 不重印 thread_header
        if b.thread_title == last_thread_in_buf:
            effective = b.sub_header_line + "".join(b.comment_lines)
        else:
            prefix = "\n" if last_thread_in_buf is not None else ""
            effective = prefix + b.thread_header_line + b.sub_header_line + "".join(b.comment_lines)

        # 超過上限 → flush 到新 embed；新 embed 重印 thread_header（加 「(續)」）
        if buf_len + len(effective) > EMBED_DESC_MAX and buf_len > len(section_header):
            flush()
            effective = _mark_continued(b.thread_header_line) + b.sub_header_line + "".join(b.comment_lines)

        # 單個 block 仍超過上限 → fallback 逐 line 切，每次切 embed 都重印 header
        if len(effective) > EMBED_DESC_MAX:
            if buf_len > len(section_header):
                flush()
            parts: List[str] = [section_header, b.thread_header_line, b.sub_header_line]
            parts_len = sum(len(x) for x in parts)
            header_baseline = parts_len  # 基線：只有 section+thread+sub header
            for line in b.comment_lines:
                if parts_len + len(line) > EMBED_DESC_MAX and parts_len > header_baseline:
                    embeds.append(discord.Embed(description="".join(parts), color=color))
                    parts = [section_header, _mark_continued(b.thread_header_line), b.sub_header_line]
                    parts_len = sum(len(x) for x in parts)
                parts.append(line)
                parts_len += len(line)
            buf = parts
            buf_len = parts_len
            last_thread_in_buf = b.thread_title
            continue

        buf.append(effective)
        buf_len += len(effective)
        last_thread_in_buf = b.thread_title

    if buf_len > len(section_header):
        embeds.append(discord.Embed(description="".join(buf), color=color))

    if not embeds:
        embeds.append(discord.Embed(description=section_header + "（無資料）", color=color))
    return embeds


def _build_comment_embeds(
    comments_in: List[CommunityActivity], comments_fb: List[CommunityActivity]
) -> List[discord.Embed]:
    blocks_in = _build_comment_blocks(comments_in)
    blocks_fb = _build_comment_blocks(comments_fb)
    return _pack_comment_blocks(blocks_in, blocks_fb, COLOR_COMMENTS)


def _build_post_embeds(
    posts_in: List[CommunityActivity], posts_fb: List[CommunityActivity]
) -> List[discord.Embed]:
    """每則 post 視為一個不可切 block；切到新 embed 時 post 完整搬走，不會被腰斬。"""
    section_header = "### 📄 主文 / 回文\n"
    post_strs_in = [_format_post_line(i + 1, a) for i, a in enumerate(posts_in)]
    post_strs_fb = [_format_post_line(len(posts_in) + i + 1, a) for i, a in enumerate(posts_fb)]

    embeds: List[discord.Embed] = []
    buf: List[str] = [section_header]
    buf_len = len(section_header)

    def _pack_one(item: str) -> None:
        nonlocal buf, buf_len
        content = item
        if len(content) > EMBED_DESC_MAX:
            # 單則 post 極長 → truncate（罕見）
            content = content[: EMBED_DESC_MAX - 30] + "\n…(過長已截斷)\n"
        if buf_len + len(content) > EMBED_DESC_MAX and buf_len > len(section_header):
            embeds.append(discord.Embed(description="".join(buf), color=COLOR_POSTS))
            buf = [section_header]
            buf_len = len(section_header)
        buf.append(content)
        buf_len += len(content)

    for s in post_strs_in:
        _pack_one(s)
    if post_strs_fb:
        _pack_one("\n━━━ 以下為區間外補撈 ━━━\n\n")
        for s in post_strs_fb:
            _pack_one(s)

    if buf_len > len(section_header):
        embeds.append(discord.Embed(description="".join(buf), color=COLOR_POSTS))
    if not embeds:
        embeds.append(discord.Embed(description=section_header + "（無資料）", color=COLOR_POSTS))
    return embeds


def _build_control_embed(*, source: str, lookup_id: str, last_updated: datetime) -> discord.Embed:
    source_label = "PTT" if source == "ptt" else "巴哈"
    embed = discord.Embed(
        description=(
            f"📚 **[{source_label}] `{lookup_id}` 的查詢紀錄**\n"
            f"最後更新：{last_updated.strftime('%Y-%m-%d %H:%M')}\n\n"
            "點擊下方按鈕重新查詢，結果會以新的日期 section 接在下方。"
        ),
        color=COLOR_CONTROL,
    )
    return embed


def _build_community_panel_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🔎 社群 ID 查詢",
        description=(
            "查詢某個 PTT 帳號 / 巴哈 ID 在兩站的發文與留言紀錄。\n"
            "每個 ID 會建立一個討論串作為長期追蹤紀錄。\n\n"
            "**使用方式**\n"
            "1️⃣【🔍 查 PTT】輸入 PTT 帳號\n"
            "2️⃣【🎮 查巴哈】輸入巴哈 user_id（或切模糊模式查名稱）\n\n"
            "查詢完成後會在下方建立/更新 thread，並公告誰查了誰。"
        ),
        color=COLOR_HEADER,
    )
    return embed


def _build_thread_name(
    source: str,
    lookup_id: str,
    display_name: Optional[str] = None,
    query_date: Optional[str] = None,
) -> str:
    date_suffix = f" ({query_date})" if query_date else ""
    if source == "ptt":
        return f"[PTT] {lookup_id}{date_suffix}"
    name_part = f" ({display_name})" if display_name else ""
    return f"[巴哈] {lookup_id}{name_part}{date_suffix}"


# ═══════════════════════════════════════════════════
# Modal / View
# ═══════════════════════════════════════════════════

def _default_date_range() -> Tuple[str, str]:
    """預設區間：今天-30 ~ 今天（台灣時區）。"""
    today = datetime.now(TAIPEI_TZ).date()
    start = (today - timedelta(days=DEFAULT_DAYS)).isoformat()
    return start, today.isoformat()


def _validate_date_range(start_raw: str, end_raw: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """L2 驗證 + 自動修正。

    規則：
    - 格式必須 `YYYY-MM-DD`（date.fromisoformat），失敗 → 錯誤
    - 起始 > 今天 → 錯誤
    - 結束 > 今天 → 自動改為今天
    - 起始 > 結束 → 自動互換
    - 區間 > 180 天 → 錯誤

    回傳 (start_iso, end_iso, error_msg)；error 非 None 時 start/end 為 None。
    """
    from datetime import date as _date
    def _parse(s: str):
        try:
            return _date.fromisoformat(s.strip())
        except (ValueError, AttributeError):
            return None

    s = _parse(start_raw or "")
    e = _parse(end_raw or "")
    if s is None:
        return None, None, "起始日格式錯誤，請使用 `YYYY-MM-DD`（例 `2026-04-20`）"
    if e is None:
        return None, None, "結束日格式錯誤，請使用 `YYYY-MM-DD`（例 `2026-04-20`）"

    today = datetime.now(TAIPEI_TZ).date()
    if s > today:
        return None, None, "起始日不能是未來日期"
    if e > today:
        e = today  # 靜默修正
    if s > e:
        s, e = e, s  # 顛倒互換
    span = (e - s).days + 1
    if span > MAX_RANGE_DAYS:
        return None, None, f"查詢區間最多 6 個月（{MAX_RANGE_DAYS} 天），目前 {span} 天，請縮短"
    return s.isoformat(), e.isoformat(), None


def _make_match_mode_select() -> discord.ui.Select:
    return discord.ui.Select(
        placeholder="比對模式",
        min_values=1,
        max_values=1,
        options=[
            discord.SelectOption(label="精確（只查 ID）", value="exact", default=True),
            discord.SelectOption(label="模糊（ID 或名稱）", value="fuzzy"),
        ],
    )


class PttLookupModal(discord.ui.Modal):
    """PTT 查詢 Modal：帳號 + 起始日 + 結束日。"""

    def __init__(
        self,
        cog: "CommunityLookupCommands",
        default_start: Optional[str] = None,
        default_end: Optional[str] = None,
    ):
        super().__init__(title="查 PTT 使用者紀錄", timeout=600)
        self.cog = cog
        ds, de = _default_date_range()
        self.account = discord.ui.TextInput(
            label="PTT 帳號",
            placeholder="例如：JohnDoe（僅帳號，不含括號暱稱）",
            max_length=50,
            required=True,
        )
        self.start_input = discord.ui.TextInput(
            label="🗓️ 起始日（預設 30 天前）",
            placeholder="YYYY-MM-DD，例 2026-03-21",
            default=default_start or ds,
            max_length=10,
            required=True,
        )
        self.end_input = discord.ui.TextInput(
            label="🗓️ 結束日（最多 6 個月區間）",
            placeholder="YYYY-MM-DD，例 2026-04-20",
            default=default_end or de,
            max_length=10,
            required=True,
        )
        self.add_item(self.account)
        self.add_item(self.start_input)
        self.add_item(self.end_input)

    async def on_submit(self, interaction: discord.Interaction):
        account = self.account.value.strip()
        start_iso, end_iso, err = _validate_date_range(self.start_input.value, self.end_input.value)
        if err:
            await interaction.response.send_message(f"⚠️ {err}", ephemeral=True)
            return
        await self.cog.flow.run(
            interaction=interaction,
            source="ptt",
            lookup_id=account,
            start_date=start_iso,
            end_date=end_iso,
        )


class BahamutLookupModal(discord.ui.Modal):
    """巴哈查詢 Modal：ID/名稱 + 起始日 + 結束日 + 比對模式。"""

    def __init__(
        self,
        cog: "CommunityLookupCommands",
        default_start: Optional[str] = None,
        default_end: Optional[str] = None,
    ):
        super().__init__(title="查巴哈使用者紀錄", timeout=600)
        self.cog = cog
        ds, de = _default_date_range()
        self.account = discord.ui.TextInput(
            label="巴哈 user_id 或名稱",
            placeholder="精確模式請輸入 ID；切模糊模式才能用名稱",
            max_length=50,
            required=True,
        )
        self.start_input = discord.ui.TextInput(
            label="🗓️ 起始日（預設 30 天前）",
            placeholder="YYYY-MM-DD,例 2026-03-21",
            default=default_start or ds,
            max_length=10,
            required=True,
        )
        self.end_input = discord.ui.TextInput(
            label="🗓️ 結束日（最多 6 個月區間）",
            placeholder="YYYY-MM-DD,例 2026-04-20",
            default=default_end or de,
            max_length=10,
            required=True,
        )
        self.mode_select = _make_match_mode_select()
        self.add_item(self.account)
        self.add_item(self.start_input)
        self.add_item(self.end_input)
        self.add_item(discord.ui.Label(text="🎯 比對模式", component=self.mode_select))

    async def on_submit(self, interaction: discord.Interaction):
        keyword = self.account.value.strip()
        start_iso, end_iso, err = _validate_date_range(self.start_input.value, self.end_input.value)
        if err:
            await interaction.response.send_message(f"⚠️ {err}", ephemeral=True)
            return
        mode = self.mode_select.values[0] if self.mode_select.values else "exact"
        fuzzy = (mode == "fuzzy")
        await self.cog.flow.run(
            interaction=interaction,
            source="bahamut",
            lookup_id=keyword,
            start_date=start_iso,
            end_date=end_iso,
            fuzzy=fuzzy,
        )


class RefreshLookupModal(discord.ui.Modal):
    """Thread 內 🔄 更新按鈕（經警告確認後）彈出的 Modal — 只問起迄日期。"""

    def __init__(
        self,
        cog: "CommunityLookupCommands",
        source: str,
        lookup_id: str,
        existing_thread: discord.Thread,
    ):
        source_label = "PTT" if source == "ptt" else "巴哈"
        title = _truncate(f"重新查詢 [{source_label}] {lookup_id}", 45)
        super().__init__(title=title, timeout=600)
        self.cog = cog
        self.source = source
        self.lookup_id = lookup_id
        self.existing_thread = existing_thread
        ds, de = _default_date_range()
        self.start_input = discord.ui.TextInput(
            label="🗓️ 起始日",
            placeholder="YYYY-MM-DD",
            default=ds,
            max_length=10,
            required=True,
        )
        self.end_input = discord.ui.TextInput(
            label="🗓️ 結束日",
            placeholder="YYYY-MM-DD",
            default=de,
            max_length=10,
            required=True,
        )
        self.add_item(self.start_input)
        self.add_item(self.end_input)

    async def on_submit(self, interaction: discord.Interaction):
        start_iso, end_iso, err = _validate_date_range(self.start_input.value, self.end_input.value)
        if err:
            await interaction.response.send_message(f"⚠️ {err}", ephemeral=True)
            return
        await self.cog.flow.run(
            interaction=interaction,
            source=self.source,
            lookup_id=self.lookup_id,
            start_date=start_iso,
            end_date=end_iso,
            existing_thread=self.existing_thread,
        )


class ConfirmRefreshView(discord.ui.View):
    """兩段式 refresh 流程的第一段：警告 + 確認/取消按鈕。"""

    def __init__(
        self,
        cog: "CommunityLookupCommands",
        source: str,
        lookup_id: str,
        existing_thread: discord.Thread,
    ):
        super().__init__(timeout=120)
        self.cog = cog
        self.source = source
        self.lookup_id = lookup_id
        self.existing_thread = existing_thread

    @discord.ui.button(label="✅ 確認繼續", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.send_modal(
            RefreshLookupModal(
                self.cog,
                source=self.source,
                lookup_id=self.lookup_id,
                existing_thread=self.existing_thread,
            )
        )

    @discord.ui.button(label="❌ 取消", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.edit_message(
            content="🚫 已取消重新查詢",
            embed=None,
            view=None,
        )


def _build_refresh_warning_embed() -> discord.Embed:
    return discord.Embed(
        title="⚠️ 重新查詢前請確認",
        description=(
            "若您此次選的區間與之前查詢的區間**重疊**，重疊部分的留言會在本 thread 內"
            "**重複出現**（前次 section 有一次、這次 section 又有一次），不容易閱讀。\n\n"
            "**建議選不重疊的新區間，例如：**\n"
            "・先前若查 `2026-03-01 ~ 2026-04-20`\n"
            "・這次改查 `2026-01-01 ~ 2026-02-28`（接續在前）"
        ),
        color=0xE67E22,  # 橘色警示
    )


CANDIDATES_PER_PAGE = 25  # Discord Select 上限


class BahamutCandidateView(discord.ui.View):
    """模糊查詢候選下拉（ephemeral）；候選數 > 25 自動分頁。"""

    def __init__(
        self,
        cog: "CommunityLookupCommands",
        candidates: List[BahamutCandidate],
        start_date: str,
        end_date: str,
        page: int = 0,
    ):
        super().__init__(timeout=180)
        self.cog = cog
        # 過濾無效 ID（雙保險：service 已過濾，這裡再擋 Discord SelectOption.value 1~100 限制）
        self.all_candidates: List[BahamutCandidate] = [
            c for c in candidates
            if c.author_id and 1 <= len((c.author_id or "").strip()) <= 100
        ]
        self.start_date = start_date
        self.end_date = end_date
        total = len(self.all_candidates)
        self.total_pages = max(1, (total + CANDIDATES_PER_PAGE - 1) // CANDIDATES_PER_PAGE)
        self.page = max(0, min(page, self.total_pages - 1))

        self.select = self._build_select()
        self.add_item(self.select)

        if self.total_pages > 1:
            prev_btn = discord.ui.Button(
                label="⬅️ 上一頁", style=discord.ButtonStyle.secondary, row=1,
                disabled=(self.page == 0),
            )
            prev_btn.callback = self._on_prev
            self.add_item(prev_btn)

            page_label = discord.ui.Button(
                label=f"{self.page + 1} / {self.total_pages}",
                style=discord.ButtonStyle.secondary, row=1, disabled=True,
            )
            self.add_item(page_label)

            next_btn = discord.ui.Button(
                label="下一頁 ➡️", style=discord.ButtonStyle.secondary, row=1,
                disabled=(self.page == self.total_pages - 1),
            )
            next_btn.callback = self._on_next
            self.add_item(next_btn)

        cancel_btn = discord.ui.Button(label="❌ 取消", style=discord.ButtonStyle.secondary, row=1)
        cancel_btn.callback = self._on_cancel
        self.add_item(cancel_btn)

    def _build_select(self) -> discord.ui.Select:
        start = self.page * CANDIDATES_PER_PAGE
        end = start + CANDIDATES_PER_PAGE
        page_candidates = self.all_candidates[start:end]
        options: List[discord.SelectOption] = [
            discord.SelectOption(
                label=_truncate(f"{c.author_name or '(無名稱)'}  [{c.author_id.strip()}]", 100),
                value=c.author_id.strip(),
                description=_truncate(f"主文 {c.post_count} · 留言 {c.comment_count}", 100),
            )
            for c in page_candidates
        ]
        if not options:
            options = [discord.SelectOption(label="(無有效候選)", value="__empty__")]
        select = discord.ui.Select(
            placeholder=f"選擇巴哈使用者（第 {self.page + 1}/{self.total_pages} 頁）",
            options=options, min_values=1, max_values=1, row=0,
        )
        select.callback = self._on_select
        return select

    async def _on_select(self, interaction: discord.Interaction):
        chosen_id = self.select.values[0]
        if chosen_id == "__empty__":
            await interaction.response.edit_message(content="🚫 無有效候選", view=None)
            return
        self.stop()
        await self.cog.flow.run(
            interaction=interaction,
            source="bahamut",
            lookup_id=chosen_id,
            start_date=self.start_date,
            end_date=self.end_date,
            fuzzy=False,
            already_deferred=False,
        )

    async def _on_prev(self, interaction: discord.Interaction):
        new_view = BahamutCandidateView(
            self.cog, self.all_candidates, self.start_date, self.end_date,
            page=self.page - 1,
        )
        await interaction.response.edit_message(view=new_view)
        self.stop()

    async def _on_next(self, interaction: discord.Interaction):
        new_view = BahamutCandidateView(
            self.cog, self.all_candidates, self.start_date, self.end_date,
            page=self.page + 1,
        )
        await interaction.response.edit_message(view=new_view)
        self.stop()

    async def _on_cancel(self, interaction: discord.Interaction):
        self.stop()
        await interaction.response.edit_message(content="🚫 已取消查詢", view=None)


class CommunityPanelView(discord.ui.View):
    """父頻道常駐面板 — 兩顆按鈕。"""

    def __init__(self, cog: Optional["CommunityLookupCommands"] = None):
        super().__init__(timeout=None)
        self._cog_ref = cog

    def _cog(self, interaction: discord.Interaction) -> "CommunityLookupCommands":
        if self._cog_ref:
            return self._cog_ref
        return interaction.client.get_cog("CommunityLookupCommands")

    @discord.ui.button(
        label="🔍 查 PTT",
        style=discord.ButtonStyle.primary,
        custom_id=CUSTOM_ID_PANEL_PTT,
    )
    async def ptt_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog = self._cog(interaction)
        if cog is None:
            await interaction.response.send_message("⚠️ 服務尚未載入", ephemeral=True)
            return
        await interaction.response.send_modal(PttLookupModal(cog))

    @discord.ui.button(
        label="🎮 查巴哈",
        style=discord.ButtonStyle.primary,
        custom_id=CUSTOM_ID_PANEL_BAHAMUT,
    )
    async def bahamut_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog = self._cog(interaction)
        if cog is None:
            await interaction.response.send_message("⚠️ 服務尚未載入", ephemeral=True)
            return
        await interaction.response.send_modal(BahamutLookupModal(cog))


class ControlMessageView(discord.ui.View):
    """Thread 底部控制訊息 — [🔄 更新] 按鈕（persistent）。

    按鈕本身依賴 thread 的 parent metadata（從 state_db 反查）才能重跑查詢，
    因此 custom_id 是固定的，flow 會從 thread_id 反查 (source, lookup_id)。
    """

    def __init__(self, cog: Optional["CommunityLookupCommands"] = None):
        super().__init__(timeout=None)
        self._cog_ref = cog

    def _cog(self, interaction: discord.Interaction) -> "CommunityLookupCommands":
        if self._cog_ref:
            return self._cog_ref
        return interaction.client.get_cog("CommunityLookupCommands")

    @discord.ui.button(
        label="🔄 更新查詢結果",
        style=discord.ButtonStyle.success,
        custom_id=CUSTOM_ID_CONTROL_REFRESH,
    )
    async def refresh_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog = self._cog(interaction)
        if cog is None:
            await interaction.response.send_message("⚠️ 服務尚未載入", ephemeral=True)
            return

        thread = interaction.channel
        if not isinstance(thread, discord.Thread):
            await interaction.response.send_message("⚠️ 此按鈕只能在查詢 thread 內使用", ephemeral=True)
            return

        # 反查 state_db 取 source / lookup_id
        meta = await cog.find_thread_meta(thread.id, guild_id=interaction.guild_id or 0)
        if meta is None:
            await interaction.response.send_message(
                "⚠️ 找不到此 thread 的查詢紀錄（可能 DB 失效）",
                ephemeral=True,
            )
            return
        source, lookup_id = meta

        # 同日 refresh → 覆蓋今日 section，不會產生重複資料，直接彈 Modal 不需警告
        # 跨日 refresh → append 新 section，可能與歷史 section 區間重疊，顯示警告
        state = await cog.state_db.get_community_lookup_thread(
            interaction.guild_id or 0, source, lookup_id,
        )
        today = datetime.now(TAIPEI_TZ).date().isoformat()
        is_same_day = bool(state and state.get("last_section_date") == today)

        if is_same_day:
            await interaction.response.send_modal(
                RefreshLookupModal(cog, source=source, lookup_id=lookup_id, existing_thread=thread)
            )
        else:
            await interaction.response.send_message(
                embed=_build_refresh_warning_embed(),
                view=ConfirmRefreshView(cog, source=source, lookup_id=lookup_id, existing_thread=thread),
                ephemeral=True,
            )


# ═══════════════════════════════════════════════════
# Flow — 主查詢流程
# ═══════════════════════════════════════════════════

class CommunityLookupFlow:
    """協調一次完整查詢流程。"""

    def __init__(self, cog: "CommunityLookupCommands"):
        self.cog = cog
        self._locks: Dict[int, asyncio.Lock] = {}

    def _lock_for(self, key: int) -> asyncio.Lock:
        lock = self._locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[key] = lock
        return lock

    async def run(
        self,
        *,
        interaction: discord.Interaction,
        source: str,
        lookup_id: str,
        start_date: str,
        end_date: str,
        fuzzy: bool = False,
        existing_thread: Optional[discord.Thread] = None,
        already_deferred: bool = False,
    ) -> None:
        """主入口。start_date / end_date 皆為 `YYYY-MM-DD`。"""
        if not interaction.guild:
            await interaction.response.send_message("⚠️ 僅限伺服器中使用", ephemeral=True)
            return

        if not already_deferred and not interaction.response.is_done():
            try:
                await interaction.response.defer(ephemeral=True, thinking=True)
            except discord.HTTPException:
                pass

        guild_id = interaction.guild.id

        # 巴哈模糊 → 候選清單
        if source == "bahamut" and fuzzy:
            candidates = await self.cog.service.search_bahamut_candidates(lookup_id)
            if not candidates:
                await interaction.followup.send(
                    f"⚠️ 模糊查詢 `{lookup_id}` 找不到任何巴哈使用者。",
                    ephemeral=True,
                )
                return
            # 只有一筆且 author_id 精確 match → 直接走
            if len(candidates) == 1 and candidates[0].author_id == lookup_id:
                lookup_id = candidates[0].author_id
                fuzzy = False
                # 繼續往下跑
            else:
                view = BahamutCandidateView(self.cog, candidates, start_date=start_date, end_date=end_date)
                await interaction.followup.send(
                    f"🔎 模糊查詢 `{lookup_id}` 找到 {len(candidates)} 位巴哈使用者，請選擇：",
                    view=view,
                    ephemeral=True,
                )
                return

        # 執行查詢
        if source == "ptt":
            result = await self.cog.service.query_ptt(
                author=lookup_id, start_date=start_date, end_date=end_date, guild_id=guild_id,
            )
            # PTT 推文斷句合併（同作者 + 同 tag + 同分鐘 + 同父文）
            result.comments_in_range = _merge_ptt_comments(result.comments_in_range)
            result.comments_fallback = _merge_ptt_comments(result.comments_fallback)
        else:
            result = await self.cog.service.query_bahamut(
                lookup_id=lookup_id, start_date=start_date, end_date=end_date, fuzzy=False, guild_id=guild_id,
            )

        if result.total_posts == 0 and result.total_comments == 0:
            await interaction.followup.send(
                f"⚠️ 查無 `{lookup_id}` 的任何活動紀錄（區間內外皆無）。",
                ephemeral=True,
            )
            return

        # 取/建 thread
        parent_channel = await self.cog.get_panel_channel(interaction.guild)
        if parent_channel is None:
            await interaction.followup.send(
                "⚠️ 尚未設定社群查詢頻道（請先用 `/server_manager` 設定）",
                ephemeral=True,
            )
            return

        thread = existing_thread
        state = await self.cog.state_db.get_community_lookup_thread(guild_id, source, lookup_id)

        created_thread = False
        if thread is None:
            if state and state.get("thread_id"):
                try:
                    ch = interaction.client.get_channel(state["thread_id"]) or await interaction.client.fetch_channel(state["thread_id"])
                    if isinstance(ch, discord.Thread):
                        thread = ch
                except discord.NotFound:
                    # 舊 thread 被刪了，清狀態
                    await self.cog.state_db.delete_community_lookup_thread(guild_id, source, lookup_id)
                    state = None

        # Thread 名稱：帶今天日期，每次查詢都會嘗試更新為最新日期
        today_iso = datetime.now(TAIPEI_TZ).date().isoformat()
        display_name = None
        if source == "bahamut" and result.posts_in_range:
            display_name = result.posts_in_range[0].extra.get("author_name")
        elif source == "bahamut" and result.comments_in_range:
            display_name = result.comments_in_range[0].extra.get("user_name")
        desired_thread_name = _truncate(
            _build_thread_name(source, lookup_id, display_name, query_date=today_iso),
            100,
        )

        if thread is None:
            # 建新 thread
            thread = await parent_channel.create_thread(
                name=desired_thread_name,
                auto_archive_duration=THREAD_AUTO_ARCHIVE_MIN,
                type=discord.ChannelType.public_thread,
            )
            created_thread = True
        elif thread.name != desired_thread_name:
            # 既有 thread，title 落後於最新查詢日期 → 改名
            # Rate limit: 每 thread 10 分鐘 2 次改名；撞到就略過（下次查會再試）
            try:
                await thread.edit(name=desired_thread_name)
            except discord.HTTPException as e:
                logger.warning(
                    "更新 community lookup thread 名稱失敗（可能 rate limit）: thread_id=%s err=%s",
                    thread.id, e,
                )

        # Thread 若封存，send 時會自動解封（或先 unarchive 較穩）
        if thread.archived:
            try:
                await thread.edit(archived=False)
            except discord.HTTPException:
                pass

        # 同 thread 並發 lock
        async with self._lock_for(thread.id):
            today = datetime.now(TAIPEI_TZ).date().isoformat()
            now_tw = datetime.now(TAIPEI_TZ)
            is_same_day = state and state.get("last_section_date") == today

            # 同日 → 刪除今日 section 後重新 append
            if is_same_day:
                await self._delete_section(thread, state.get("last_section_slots") or {})

            # 刪除舊控制訊息（不管同日跨日都要移到最底）
            if state and state.get("control_msg_id"):
                try:
                    old_ctrl = await thread.fetch_message(state["control_msg_id"])
                    await old_ctrl.delete()
                except (discord.NotFound, discord.Forbidden):
                    pass

            # 組新 section 的 embeds
            header_embed = _build_header_embed(
                source=source, lookup_id=lookup_id,
                start_date=start_date, end_date=end_date,
                querier=interaction.user, result=result,
                fuzzy=fuzzy,
                first_query_time=now_tw if not is_same_day else None,
                latest_query_time=now_tw,
            )
            post_embeds = _build_post_embeds(result.posts_in_range, result.posts_fallback)
            comment_embeds = _build_comment_embeds(result.comments_in_range, result.comments_fallback)

            # Append section messages
            slot_ids = await self._append_section(thread, header_embed, post_embeds, comment_embeds)

            # Append 新控制訊息
            ctrl_msg = await thread.send(
                embed=_build_control_embed(source=source, lookup_id=lookup_id, last_updated=now_tw),
                view=ControlMessageView(self.cog),
            )

            # 更新 state_db
            await self.cog.state_db.upsert_community_lookup_thread(
                guild_id,
                source,
                lookup_id,
                thread_id=thread.id,
                control_msg_id=ctrl_msg.id,
                last_section_date=today,
                last_section_slots=slot_ids,
            )

        # 父頻道通知 + bump panel
        await self._notify_parent(
            parent_channel=parent_channel,
            querier=interaction.user,
            source=source, lookup_id=lookup_id,
            start_date=start_date, end_date=end_date,
            result=result,
            thread_url=thread.jump_url,
        )
        # ephemeral 回查詢者
        try:
            await interaction.followup.send(
                f"✅ 已{'建立' if created_thread else '更新'}查詢紀錄 → {thread.jump_url}",
                ephemeral=True,
            )
        except discord.HTTPException:
            pass

        # bump panel（背景 task，避免阻塞）
        asyncio.create_task(self.cog.bump_panel_safe(interaction.guild, parent_channel))

    async def _append_section(
        self,
        thread: discord.Thread,
        header_embed: discord.Embed,
        post_embeds: List[discord.Embed],
        comment_embeds: List[discord.Embed],
    ) -> Dict[str, object]:
        """Append 一整組 section embeds，回傳 msg_ids 讓後續 edit / 追蹤。"""
        header_msg = await thread.send(embed=header_embed)
        await asyncio.sleep(SEND_DELAY)

        post_msg_ids: List[int] = []
        prev_msg = header_msg
        for emb in post_embeds:
            m = await thread.send(embed=emb, reference=prev_msg)
            post_msg_ids.append(m.id)
            prev_msg = m
            await asyncio.sleep(SEND_DELAY)

        comment_msg_ids: List[int] = []
        for emb in comment_embeds:
            m = await thread.send(embed=emb, reference=prev_msg)
            comment_msg_ids.append(m.id)
            prev_msg = m
            await asyncio.sleep(SEND_DELAY)

        return {
            "header_msg_id": header_msg.id,
            "post_slot_msg_ids": post_msg_ids,
            "comment_slot_msg_ids": comment_msg_ids,
        }

    async def _delete_section(self, thread: discord.Thread, slots: Dict) -> None:
        """刪除前次 section 的所有訊息（同日重查用）。"""
        msg_ids: List[int] = []
        if slots.get("header_msg_id"):
            msg_ids.append(slots["header_msg_id"])
        msg_ids.extend(slots.get("post_slot_msg_ids") or [])
        msg_ids.extend(slots.get("comment_slot_msg_ids") or [])
        for mid in msg_ids:
            try:
                m = await thread.fetch_message(mid)
                await m.delete()
            except (discord.NotFound, discord.Forbidden):
                continue
            except discord.HTTPException as e:
                logger.warning("刪除舊 section msg 失敗 mid=%s: %s", mid, e)

    async def _notify_parent(
        self,
        *,
        parent_channel: discord.TextChannel,
        querier: discord.abc.User,
        source: str,
        lookup_id: str,
        start_date: str,
        end_date: str,
        result: LookupResult,
        thread_url: str,
    ) -> None:
        source_label = "PTT" if source == "ptt" else "巴哈"
        total_p = result.total_posts
        total_c = result.total_comments
        # 巴哈的對象 ID 做成搜尋超連結；PTT 維持純文字
        if source == "bahamut":
            target_str = f"[`{lookup_id}`](<https://search.gamer.com.tw/?q={lookup_id}>)"
        else:
            target_str = f"`{lookup_id}`"
        text = (
            f"🔔 {querier.mention} 更新了 **[{source_label}] {target_str}** 的查詢紀錄\n"
            f"　📅 {start_date} ~ {end_date} · 📊 主文 {total_p} / 留言 {total_c}\n"
            f"　→ {thread_url}"
        )
        try:
            await parent_channel.send(text, allowed_mentions=discord.AllowedMentions(users=True))
        except discord.HTTPException as e:
            logger.warning("父頻道通知發送失敗: %s", e)


# ═══════════════════════════════════════════════════
# Cog
# ═══════════════════════════════════════════════════

class CommunityLookupCommands(commands.Cog):
    """社群 ID 查詢。"""

    def __init__(
        self,
        bot: commands.Bot,
        state_db: Optional[StateDB] = None,
        service: Optional[CommunityLookupService] = None,
    ):
        self.bot = bot
        self.state_db = state_db
        self.service = service
        self.flow = CommunityLookupFlow(self)
        self._panel_lock = asyncio.Lock()

    async def cog_load(self):
        # Lazy init：沿用 base_monitor 的全域 StateDB，避免多實例
        if self.state_db is None:
            from services.base_monitor import get_shared_state_db
            self.state_db = await get_shared_state_db()
        if self.service is None:
            self.service = CommunityLookupService(state_db=self.state_db)
        # 註冊 persistent views
        self.bot.add_view(CommunityPanelView(self))
        self.bot.add_view(ControlMessageView(self))
        logger.info("CommunityLookupCommands cog loaded；persistent views registered")

    # ── Panel 部署 ──

    async def get_panel_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        config = ChannelConfig.load_config("config.json", caller="CommunityLookup")
        ch_id = config.get("community_lookup_channel_id", ChannelConfig.DEFAULT_ID)
        if ch_id == ChannelConfig.DEFAULT_ID:
            return None
        ch = guild.get_channel(int(ch_id))
        return ch if isinstance(ch, discord.TextChannel) else None

    async def _send_community_panel_to_channel(self, channel: discord.TextChannel) -> discord.Message:
        return await channel.send(embed=_build_community_panel_embed(), view=CommunityPanelView(self))

    async def replace_community_panel_message(
        self, guild: discord.Guild, panel_channel: discord.TextChannel,
    ) -> tuple[discord.Message, bool]:
        """刪舊發新。"""
        runtime = _load_panel_runtime()
        deleted = False
        old_ch_id = runtime.get("panel_channel_id")
        old_msg_id = runtime.get("panel_message_id")
        if old_ch_id and old_msg_id:
            old_ch = guild.get_channel(int(old_ch_id))
            if isinstance(old_ch, discord.TextChannel):
                try:
                    old_msg = await old_ch.fetch_message(int(old_msg_id))
                    await old_msg.delete()
                    deleted = True
                except discord.NotFound:
                    pass
                except discord.Forbidden:
                    logger.warning("無權刪除舊社群查詢面板")
        new_msg = await self._send_community_panel_to_channel(panel_channel)
        _save_panel_runtime(panel_channel.id, new_msg.id)
        return new_msg, deleted

    async def bump_panel_safe(self, guild: discord.Guild, panel_channel: discord.TextChannel) -> None:
        """每次查詢完呼叫（背景）。"""
        try:
            async with self._panel_lock:
                await self.replace_community_panel_message(guild, panel_channel)
        except Exception as e:
            logger.error("bump_panel_safe 失敗: %s", e, exc_info=True)

    # ── Thread meta 反查（control button 用）──

    async def find_thread_meta(
        self, thread_id: int, guild_id: int
    ) -> Optional[tuple[str, str]]:
        """從 thread_id 反查 (source, lookup_id)。"""
        async with self.state_db.db.execute(
            """SELECT source, lookup_id
               FROM community_lookup_threads
               WHERE guild_id=? AND thread_id=?""",
            (guild_id, thread_id),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return row[0], row[1]

    # ── （可選）手動重發面板入口 ──

    async def send_community_panel_cmd(self, interaction: discord.Interaction):
        """手動重發面板（可由 /server_manager 某按鈕呼叫）。"""
        if not interaction.guild:
            return
        panel_channel = await self.get_panel_channel(interaction.guild)
        if panel_channel is None:
            await safe_send_interaction_message(
                interaction,
                "❌ 尚未設定社群查詢頻道，請先用 `/server_manager` → 頻道設定。",
                ephemeral=True,
            )
            return
        msg, deleted = await self.replace_community_panel_message(interaction.guild, panel_channel)
        extra = "\n🧹 舊面板已刪除。" if deleted else ""
        await safe_send_interaction_message(
            interaction,
            f"✅ 已在 {panel_channel.mention} 發送社群 ID 查詢面板。\n🔗 {msg.jump_url}{extra}",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    """標準 load_extension 入口；cog 會在 cog_load 自行 lazy init state_db/service。"""
    await bot.add_cog(CommunityLookupCommands(bot))
