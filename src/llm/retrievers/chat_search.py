"""搜尋這個伺服器的聊天紀錄，做成給模型用的工具：/askai 問「誰說過／誰常說某句話」「之前有人提過…嗎」時，
由模型自己決定要不要查、查什麼（開關 `askai_chat_search_mode`）。

架構定位：服務層（`llm/retrievers`）。上層：介面層 `commands.llm_commands`（和情報、網路搜尋一起交給
`run_with_intel(also=…)`，模型在同一個工具輪裡挑）。下層：`context_retriever.search_chat`（語意路）、pgvector
（字面路，`LLMServiceSettings.pgvector_connect`）、`llm.preprocess.person_anchor`（名字#尾碼）、`emoji_text_utils`（品質閘）。
不 import discord：成員名字、頻道名稱、bot 自己的 id 由指令層查好交進來。

介面：
- `ChatSearchTools(settings=, member_names=, channel_names=, self_id=, instructions=)`：`ToolRunner`——
  `tools`（宣告一個 chat_search）、`instructions`（規則檔 `askai_chat_search_rules.txt`，改檔即生效）、`execute`；
  `calls` 記這次請求查了什麼（寫進 /askai 的回應紀錄）。`phrase_search`／`topic_search` 是兩種模式的後端（同步、碰 DB）。
- `CHAT_SEARCH_TOOL`：宣告（名稱與說明是模型決定要不要查的依據）。

規則：
- 兩種模式由模型選：phrase＝照字面找（ILIKE 子字串）、按人與頻道計數＋每人最近幾則原文，給「誰常說、誰說過」這類要數
  的問題；topic＝照意思找（`search_chat` 全庫、同一人同一句折成一則），回最近幾則含誰、哪個頻道、何時，給印象與話題。
  phrase 一筆都沒有時自動改走 topic，回傳裡註明「不是一字不差」。
- 結果一律標「頻道、名字#尾碼、時間」：/askai 本來只看一個頻道的視窗，全庫搜回來的東西不標出處會混在一起。
- 聊天表沒存 guild_id（只有 channel_id），bot 目前只在一個伺服器，所以不分伺服器；之後多伺服器要用指令層交進來的頻道
  名單當白名單。bot 自己的訊息不算（`self_id`）。
- 任何失敗（參數錯、名字對不到、DB 壞）都回 `{"error": ...}` 給模型，不往外丟。DB 是同步的，`execute` 丟到執行緒。

例外與決策：字面比對用 ILIKE 子字串而不是 `dedup_key` 的正規化——資料庫端沒有同一份正規化；句子中間夾標點或空白
（「好 了 啦」）會漏，模型可以換寫法再查。字面模式一次掃描就把計數與最近幾則一起算出來（CTE 引用兩次會物化一次），
熱快取約 0.3 秒、冷快取讀整個 heap（約 660 MB）要幾秒到十幾秒，所以設 statement_timeout 讓它逾時就回錯誤給模型；
要再快得建 pg_trgm 的 GIN 索引（三個字以上的句子走索引，兩個字的照樣掃描），建不建記在交接檔。
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from llm.client.tool_calls import ToolArgumentError, parse_arguments
from llm.preprocess import person_anchor
from llm.preprocess.emoji_text_utils import is_emoji_or_symbol_only, is_link_only
from llm.retrievers import context_retriever
from sys_settings.llm_settings import AskAIChatSearchSettings, LLMServiceSettings
from sys_settings.pgvector_settings import HYBRID_RETRIEVAL_SETTINGS
from sys_settings.time_settings import APP_TZ
from utils import hot_files

logger = logging.getLogger(__name__)

_LLM_SETTINGS = LLMServiceSettings()
MODES = ("phrase", "topic")

#: 宣告給模型的工具（名稱與說明是模型決定要不要查的依據）
CHAT_SEARCH_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "chat_search",
        "description": (
            "搜尋這個伺服器的聊天紀錄（全部頻道、所有時間）。問「誰說過／誰常說某句話」「之前有人提過某件事嗎」"
            "「某人講過什麼」時用。phrase＝照字面找那句話、按人與頻道計數，附每人最近幾則原文（口頭禪、名言、要數次數的問題）；"
            "topic＝照意思找（印象、話題），回最近幾則含誰、哪個頻道、何時。結果裡的 name 是「名字#尾碼」。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string",
                          "description": "要找的那句話（phrase）或主題（topic）；不要把「誰常說」這類問法寫進去"},
                "mode": {"type": "string", "enum": list(MODES),
                         "description": "phrase＝字面、計數；topic＝語意。沒給就是 topic"},
                "author": {"type": "string", "description": "只找這個人說的：用對話或名字對照裡看到的名字，可含 #尾碼"},
                "channel": {"type": "string", "description": "只找這個頻道（頻道名稱）"},
            },
            "required": ["query"],
        },
    },
}


def _connect():
    return _LLM_SETTINGS.pgvector_connect()


def _when(ts: Any) -> str:
    """向量庫的 timestamp（isoformat，帶 +00:00）→ 本地時間「YYYY-MM-DD HH:MM」；讀不懂回空字串。"""
    try:
        dt = datetime.fromisoformat(str(ts))
    except (TypeError, ValueError):
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(APP_TZ).strftime("%Y-%m-%d %H:%M")


def _clip(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", (text or "")).strip()
    return text if len(text) <= limit else text[: max(1, limit - 1)] + "…"


class ChatSearchTools:
    """一次 /askai 請求的聊天紀錄搜尋工具（`llm.client.tool_calls.ToolRunner`）。"""

    def __init__(self, *, member_names: Mapping[Any, list[str]], channel_names: Mapping[Any, str],
                 self_id: Any = None, settings: Optional[AskAIChatSearchSettings] = None,
                 instructions: Optional[str] = None):
        self.settings = settings or AskAIChatSearchSettings()
        #: author_id → [顯示名稱, …]（`member_names_from_guild`；第一個是顯示名稱，bot 不在裡面）
        self.member_names = {str(uid): list(names) for uid, names in member_names.items() if names}
        #: channel_id → 頻道或 thread 名稱（只有指令層查得到的；封存的 thread 標成未知頻道）
        self.channel_names = {str(cid): str(name) for cid, name in channel_names.items() if name}
        self.self_id = str(self_id) if self_id else None
        #: 怎麼用這個工具（接在系統提示詞後面，見 `LLMService.generate_reply`）
        self.instructions = (
            instructions if instructions is not None
            else hot_files.read_text(self.settings.rules_path, label="聊天紀錄搜尋規則")
        )
        #: 這次請求呼叫過的工具與結果摘要（寫進 /askai 的回應紀錄）
        self.calls: list[dict[str, Any]] = []

    @property
    def tools(self) -> list[dict[str, Any]]:
        return [CHAT_SEARCH_TOOL]

    # ── 名字、頻道 ────────────────────────────────────────────────────────
    def label(self, user_id: Any) -> str:
        names = self.member_names.get(str(user_id or ""))
        if names:
            return person_anchor.label(names[0], user_id)
        tail = person_anchor.suffix(user_id)
        return f"已離開的成員#{tail}" if tail else "已離開的成員"

    def channel_label(self, channel_id: Any) -> str:
        return self.channel_names.get(str(channel_id or "")) or "未知頻道"

    def resolve_author(self, raw: Any) -> tuple[Optional[str], Optional[str]]:
        """模型給的名字 → author_id。對到一個人回 (id, None)；對不到或對到好幾個回 (None, 給模型的錯誤)。"""
        text = str(raw or "").strip().lstrip("@")
        if not text:
            return None, None
        mention = re.fullmatch(r"<@!?(\d+)>|(\d{15,})", text)
        if mention:
            return (mention.group(1) or mention.group(2)), None
        anchored = re.fullmatch(r"(.*?)\s*#(\d{2,})", text)
        name, tail = (anchored.group(1).strip(), anchored.group(2)) if anchored else (text, "")
        key = name.casefold()
        exact: list[str] = []
        partial: list[str] = []
        for uid, names in self.member_names.items():
            if tail and not uid.endswith(tail):
                continue
            folded = [n.casefold() for n in names]
            if key and key in folded:
                exact.append(uid)
            elif key and any(key in n for n in folded):
                partial.append(uid)
            elif not key and tail:
                exact.append(uid)
        hits = exact or partial
        if len(hits) == 1:
            return hits[0], None
        if not hits:
            return None, f"找不到叫「{text}」的人：用對話或名字對照裡看到的名字（可含 #尾碼）"
        shown = "、".join(self.label(uid) for uid in hits[:6])
        return None, f"有好幾個人對得上「{text}」：{shown}；請用帶 #尾碼的名字"

    def resolve_channel(self, raw: Any) -> tuple[Optional[str], Optional[str]]:
        text = str(raw or "").strip().lstrip("#")
        if not text:
            return None, None
        if text.isdigit() and text in self.channel_names:
            return text, None
        key = text.casefold()
        exact = [cid for cid, name in self.channel_names.items() if name.casefold() == key]
        partial = [cid for cid, name in self.channel_names.items() if key in name.casefold()]
        hits = exact or partial
        if len(hits) == 1:
            return hits[0], None
        if not hits:
            return None, f"沒有叫「{text}」的頻道"
        return None, f"有好幾個頻道對得上「{text}」：{'、'.join(self.channel_names[c] for c in hits[:6])}"

    # ── 執行 ──────────────────────────────────────────────────────────────
    async def execute(self, name: str, arguments: Any) -> str:
        """執行一個工具呼叫，回傳給模型的 JSON 字串；失敗也回 `{"error": ...}`，不往外丟。"""
        started = time.perf_counter()
        record: dict[str, Any] = {"tool": name, "arguments": str(arguments)[:300]}
        try:
            payload = await self._execute(name, arguments, record)
        except Exception as exc:   # 邊界：每個工具呼叫；失敗轉成錯誤回給模型，不中斷回答
            logger.warning("聊天搜尋工具失敗 tool=%s：%s: %s", name, type(exc).__name__, exc)
            payload = {"error": f"這次查不到（{type(exc).__name__}），請就手上的資料回答"}
        record["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
        if "error" in payload:
            record["error"] = str(payload["error"])[:200]
        self.calls.append(record)
        return json.dumps(payload, ensure_ascii=False)

    async def _execute(self, name: str, arguments: Any, record: dict[str, Any]) -> dict[str, Any]:
        if name != CHAT_SEARCH_TOOL["function"]["name"]:
            return {"error": f"沒有名為 {name} 的工具；可用的是：chat_search"}
        try:
            args = parse_arguments(arguments)
        except ToolArgumentError as exc:
            return {"error": str(exc)}
        query = str(args.get("query") or "").strip()
        if not query:
            return {"error": "query 不能是空的：寫要找的那句話或主題"}
        mode = str(args.get("mode") or "topic").strip().lower()
        if mode not in MODES:
            return {"error": f"mode 只能是 {'／'.join(MODES)}"}
        author_id, error = self.resolve_author(args.get("author"))
        if error:
            return {"error": error}
        channel_id, error = self.resolve_channel(args.get("channel"))
        if error:
            return {"error": error}
        record.update(query=query, mode=mode, author_id=author_id, channel_id=channel_id)

        if mode == "phrase":
            payload = await asyncio.to_thread(self.phrase_search, query, author_id=author_id, channel_id=channel_id)
            if payload["total"]:
                record["result_count"] = payload["total"]
                return payload
            record["fallback"] = "topic"
            payload = await asyncio.to_thread(self.topic_search, query, author_id=author_id, channel_id=channel_id)
            payload["note"] = f"照字面找不到「{query}」，改照意思找：下面是意思相近的句子，不是一字不差"
        else:
            payload = await asyncio.to_thread(self.topic_search, query, author_id=author_id, channel_id=channel_id)
        record["result_count"] = len(payload["results"])
        return payload

    # ── 兩種模式的後端（同步、碰 DB） ─────────────────────────────────────
    def phrase_search(self, query: str, *, author_id: Optional[str] = None,
                      channel_id: Optional[str] = None) -> dict[str, Any]:
        """照字面找：按人與頻道計數，每人附最近幾則原文。一次掃描：計數與最近幾則都從同一個 CTE 來。"""
        s = self.settings
        pattern = "%" + re.sub(r"([\\%_])", r"\\\1", query) + "%"
        where = ["text ILIKE %s ESCAPE '\\'"]
        params: list[Any] = [pattern]
        if author_id:
            where.append("metadata_->>'author_id' = %s")
            params.append(author_id)
        if channel_id:
            where.append("metadata_->>'channel_id' = %s")
            params.append(channel_id)
        table = HYBRID_RETRIEVAL_SETTINGS.physical_table(HYBRID_RETRIEVAL_SETTINGS.get_chat_table_name())
        sql = f"""
            WITH hits AS (
                SELECT metadata_->>'author_id' AS author, metadata_->>'channel_id' AS channel,
                       metadata_->>'timestamp' AS ts, text
                FROM {table} WHERE {' AND '.join(where)}
            )
            SELECT 'count', author, channel, count(*)::text, max(ts) FROM hits GROUP BY author, channel
            UNION ALL
            SELECT 'recent', author, channel, ts, text
            FROM (SELECT author, channel, ts, text FROM hits ORDER BY ts DESC LIMIT %s) AS recent
        """
        with _connect() as conn:
            with conn.cursor() as cur:
                # 沒有 trigram 索引時是全表掃描，冷快取可能十幾秒；超過就放棄、回錯誤給模型（SET LOCAL 只活在這個交易）
                cur.execute("SET LOCAL statement_timeout = %s", (int(s.statement_timeout_seconds * 1000),))
                cur.execute(sql, tuple([*params, s.phrase_scan_rows]))
                rows = cur.fetchall()
        groups = [(author, channel, int(n), last) for kind, author, channel, n, last in rows if kind == "count"]
        recent = [(author, channel, ts, text) for kind, author, channel, ts, text in rows if kind == "recent"]

        counts: dict[str, int] = defaultdict(int)
        per_channel: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        latest: dict[str, str] = {}
        for author, channel, n, last in groups:
            author = str(author or "")
            if not author or author == self.self_id:
                continue
            counts[author] += int(n)
            per_channel[author][str(channel or "")] += int(n)
            latest[author] = max(latest.get(author, ""), str(last or ""))
        examples: dict[str, list[str]] = defaultdict(list)
        for author, channel, ts, text in recent:
            author = str(author or "")
            if author in counts and len(examples[author]) < s.phrase_examples:
                examples[author].append(f"[{_when(ts)} #{self.channel_label(channel)}] {_clip(text, s.text_max_chars)}")
        speakers = []
        for author in sorted(counts, key=lambda a: (-counts[a], a))[: s.phrase_speakers]:
            channels = sorted(per_channel[author].items(), key=lambda kv: -kv[1])[: s.phrase_channels]
            speakers.append({
                "name": self.label(author), "count": counts[author],
                "channels": [f"{self.channel_label(cid)} {n}" for cid, n in channels],
                "latest": _when(latest[author])[:10], "examples": examples.get(author, []),
            })
        payload: dict[str, Any] = {"mode": "phrase", "query": query, "total": sum(counts.values()), "speakers": speakers}
        if len(counts) > len(speakers):
            payload["note"] = f"還有 {len(counts) - len(speakers)} 個人說過，只列說最多次的 {len(speakers)} 個"
        return payload

    def topic_search(self, query: str, *, author_id: Optional[str] = None,
                     channel_id: Optional[str] = None) -> dict[str, Any]:
        """照意思找：全庫語意搜尋，回最近幾則含誰、哪個頻道、何時。"""
        s = self.settings
        rows = context_retriever.search_chat(
            question=query, limit=s.topic_limit * 2, logger=logger, candidate_ids=None,
            channel_id=channel_id, author_id=author_id, return_meta=True, min_chars=s.topic_min_chars, collapse=True,
        )
        results = []
        for row in rows:
            text = (row.get("text") or "").strip()
            if str(row.get("author_id") or "") == self.self_id or is_emoji_or_symbol_only(text) or is_link_only(text):
                continue
            item = {"when": _when(row.get("timestamp")), "channel": self.channel_label(row.get("channel_id")),
                    "name": self.label(row.get("author_id")), "text": _clip(text, s.text_max_chars)}
            if (row.get("repeat_count") or 1) > 1:
                item["repeats"] = row["repeat_count"]
            results.append(item)
            if len(results) >= s.topic_limit:
                break
        return {"mode": "topic", "query": query, "results": results}
