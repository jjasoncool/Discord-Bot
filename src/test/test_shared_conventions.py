"""跨模組共用慣例的守衛（收斂後防止再度分岔）。

守的不是某個功能，而是「**同一件事只有一個來源**」這個結構性約定。

為什麼用測試而不是寫在文件裡：這個專案大部分由 AI 協作，而文件會被略讀、慣例會被
遺忘，但**紅掉的測試不會**。每條規則都是一次真實分岔的紀錄：

  - 實體表名：四處各自拼 `f"data_{...}"`，其中兩處**沒有消毒**（SQL identifier 注入）
  - 全站時區：八處各自寫死 UTC+8，四種命名；唯一可設定的來源只有一處在用
    （2026-09-02 追加：regex 版守衛被 `timezone as _tz` 的 import 別名繞過，改走 AST）
  - pgvector 連線：六處抄同樣的五個參數；要加 timeout 或換驅動得改六個地方
  - 向量庫建立：三處各自 `PGVectorStore.from_params`，都沒有借出前檢查，資料庫關掉閒置連線後
    第一次寫入必失敗，成員偏好因此丟過
  - prompt 載入：三份一字不差的 mtime 快取實作

**新增共用元件時，順手在 `RULES` 加一條**，下一個人（或下一輪的 AI）就不會重造。

執行：
    cd src && python -m unittest test.test_shared_conventions -v
"""

import ast
import textwrap
import tempfile
import builtins
import functools
import os
import re
import sys
import tokenize
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from sys_settings.pgvector_settings import HYBRID_RETRIEVAL_SETTINGS as H  # noqa: E402


class Rule:
    """一條「這件事只能有一個來源」的規則。

    偵測方式二選一：
      - `pattern`：逐行 regex（遮掉註解與字串後比對）。形狀單純的用這個就夠。
      - `finder`：吃檔案路徑、回傳行號 list。**會被 import 別名或寫法變形繞過的
        用這個走 AST**——見 `_find_hardcoded_utc_offsets`。
    """

    def __init__(
        self,
        name: str,
        canonical: str,
        allowed: set[str],
        *,
        pattern: str | None = None,
        finder=None,
    ):
        assert (pattern is None) != (finder is None), (
            f"規則「{name}」只能有一種偵測方式（pattern 或 finder）"
        )
        self.name = name
        self.pattern = pattern
        self.finder = finder
        self.canonical = canonical
        #: 合法的例外。scraper 是獨立容器（掛載 ./src/scraper → /app），
        #: 根目錄看不到 sys_settings，只能自己保留一份。以 `/` 結尾的是整個資料夾。
        self.allowed = allowed

    def allows(self, rel: str) -> bool:
        return rel in self.allowed or any(
            a.endswith("/") and rel.startswith(a) for a in self.allowed
        )


def _find_discarded_create_task(path: Path) -> list[int]:
    """`asyncio.create_task(...)`／`loop.create_task(...)`／`ensure_future(...)` 的回傳值直接丟掉的語句。

    丟掉就沒人留參照（event loop 只留弱參照，任務可能被回收），任務裡的例外也只會在被回收時印一行
    「Task exception was never retrieved」——哪個功能停了沒人知道。要 fire-and-forget 走
    `utils.background_tasks.spawn`；有留參照（`task = ...`、放進 list、`await`）的不在此限。
    """
    hits = []
    for node in ast.walk(_parse(path)):
        if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)):
            continue
        func = node.value.func
        name = func.attr if isinstance(func, ast.Attribute) else (func.id if isinstance(func, ast.Name) else "")
        if name in ("create_task", "ensure_future"):
            hits.append(node.lineno)
    return hits


@functools.cache
def _parse(path: Path) -> ast.Module:
    """解析一個原始碼檔成 AST；**同一個檔只解析一次**。

    為什麼要快取：掃描的巢狀順序是「外層規則、內層檔案」，而 AST 的消費者又不只
    一個（時區規則在 `NoReinventedWheelsTests`、未定義常數檢查在
    `UndefinedConstantTests`，是兩個獨立的 test method）。**跨 test method 的重複
    只有快取搆得到**——把迴圈順序倒過來只能省下同一個 method 內的重複。

    這個檔的規則會持續長（docstring 明說「新增共用元件時順手加一條」），沒有快取
    的話每加一條 AST 規則就多一趟全檔解析，成本線性成長。

    前提：測試進程是短命的，跑的期間原始碼不會被改。若日後有測試需要「改檔案再
    重掃」，那條測試得自己繞開這個快取（或呼叫 `_parse.cache_clear()`）。
    """
    return ast.parse(path.read_text(encoding="utf-8"))


def _find_hardcoded_utc_offsets_in_source(src: str) -> list[int]:
    r"""在原始碼字串裡找 `timezone(timedelta(hours=...))`，**連 import 別名一起抓**。

    為什麼這條規則不用 regex：`discord_bot.py` 的日記排程曾經寫成

        from datetime import timezone as _tz, timedelta as _td
        DIARY_TZ = _tz(_td(hours=8))

    形狀一模一樣，卻整整溜過 ``timezone\(timedelta\(hours=`` 這條 pattern。
    **一個換個 import 別名就能繞過的守衛，可靠度等同寫在文件裡**——而本檔存在的
    前提正是「文件會被略讀、紅掉的測試不會」。AST 看的是「這個名字綁到 datetime
    的哪個東西」，改叫什麼都躲不掉。

    只認「直接把 timedelta 呼叫塞進 timezone」這個慣用寫法（含 `datetime.timezone(...)`
    的模組屬性形式）。先把 offset 存成變數再傳進去的繞法不擋——那已經是 linter
    的作用域分析範圍，而本檔的取捨一貫是「判定明確、誤判率低」，因為**誤判會讓
    容器啟動 gate 紅掉，比漏判更難收拾**。
    """
    return _scan_tz_calls(ast.parse(src))


def _scan_tz_calls(tree: ast.Module) -> list[int]:
    """`_find_hardcoded_utc_offsets_in_source` 的核心，抽出來讓檔案入口能共用快取的 AST。"""
    # 本檔裡 timezone / timedelta 的所有叫法
    tz_names: set[str] = set()
    td_names: set[str] = set()
    dt_modules: set[str] = set()  # import datetime as X → X.timezone(...)

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "datetime":
            for a in node.names:
                if a.name == "timezone":
                    tz_names.add(a.asname or a.name)
                elif a.name == "timedelta":
                    td_names.add(a.asname or a.name)
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name == "datetime":
                    dt_modules.add(a.asname or a.name)

    def _is_call_to(node, simple_names: set[str], attr: str) -> bool:
        if not isinstance(node, ast.Call):
            return False
        func = node.func
        if isinstance(func, ast.Name):
            return func.id in simple_names
        return (
            isinstance(func, ast.Attribute)
            and func.attr == attr
            and isinstance(func.value, ast.Name)
            and func.value.id in dt_modules
        )

    hits: set[int] = set()
    for node in ast.walk(tree):
        if not _is_call_to(node, tz_names, "timezone"):
            continue
        for arg in node.args:
            if _is_call_to(arg, td_names, "timedelta") and any(
                kw.arg == "hours" for kw in arg.keywords
            ):
                hits.add(node.lineno)
    return sorted(hits)


def _find_hardcoded_utc_offsets(path: Path) -> list[int]:
    """檔案版：語法壞掉的檔案回空 list（交給 py_compile / 其他測試去抱怨）。"""
    try:
        return _scan_tz_calls(_parse(path))
    except (SyntaxError, UnicodeDecodeError):
        return []


def _find_hardcoded_app_root(path: Path) -> list[int]:
    """找寫死的容器掛載點 `"/app"`、`"/app/..."`、`"/logs"`、`"/logs/..."`（字串裡的東西 regex 看不到，走 AST）。

    容器裡這兩個路徑永遠對，但主機上的腳本、未來的 CI 找不到；掛載一改就要翻幾十處。
    根目錄與 log 目錄只有 `sys_settings.paths` 一處知道，其他地方問它。
    """
    hits = []
    for node in ast.walk(_parse(path)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            v = node.value
            if v in ("/app", "/logs") or v.startswith("/app/") or v.startswith("/logs/"):
                hits.append(node.lineno)
    return hits


def _find_raw_runtime_json_io(path: Path) -> list[int]:
    """自己 `open()`／`read_text()`／`write_text()` 一個 bot 寫的檔（`settings/runtime/` 底下、舊名 `*_runtime.json`、價格表）的那幾行。

    看的是開檔那一行的參數文字：直接寫檔名、或變數名帶 RUNTIME／runtime／PRICES。這些是程式自己寫的
    狀態檔；各寫一套讀寫，就會有的直接覆寫、有的自己快取、有的相對路徑。機制只有 `utils.runtime_file`
    一份（面板置底的 `load_runtime`／`update_runtime` 轉呼叫它；價格表的 `item_prices` 也建在它上面）。
    人手改的 `settings/article_relay.json` 走熱讀檔（`hot_files`），不在這條規則的對象裡。
    """
    hits = []
    for node in ast.walk(_parse(path)):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if isinstance(f, ast.Attribute) and f.attr in ("read_text", "write_text"):
            target = ast.unparse(f.value)          # `X.read_text(encoding=...)` 沒有位置參數，看的是 X
        elif isinstance(f, ast.Name) and f.id == "open" and node.args:
            target = ast.unparse(node.args[0])
        else:
            continue
        if any(k in target for k in ("_runtime.json", "RUNTIME", "runtime", "PRICES", "prices_file", "STATE", "monitored_channels")):
            hits.append(node.lineno)
    return hits


def _find_hardcoded_article_urls(path: Path) -> list[int]:
    """找寫死的官方公告網址。

    為什麼這條要走 AST 而不是 regex：`_code_lines` 會把**字串內容整段遮掉**
    （否則 docstring 裡提到被禁的寫法就會誤判），而網址正好只活在字串裡，
    regex 規則對它是全盲的。f-string 也吃得到——JoinedStr 底下的常數片段
    `"…/news/detail/"` 一樣是 ast.Constant。

    起因：官方原文網址原本 article_monitor（轉發 embed）與 event_scheduler
    （活動描述）各寫一份，改網址時只會改到其中一邊。
    """
    hits = []
    for node in ast.walk(_parse(path)):
        if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and "kurogames.com" in node.value and "news/detail" in node.value):
            hits.append(node.lineno)
    return hits


def _find_hardcoded_bahamut_floor_urls(path: Path) -> list[int]:
    """找寫死的巴哈「單一樓層」網址（`Co.php`）。走 AST 的理由同 `_find_hardcoded_article_urls`。

    起因：社群稽查的兩處各自用 f-string 組，情報搜尋也要給樓層連結（2026-10-08 收成一份）。
    """
    hits = []
    for node in ast.walk(_parse(path)):
        if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and "forum.gamer.com.tw/Co.php" in node.value):
            hits.append(node.lineno)
    return hits


_CONTENT_LIKE = re.compile(r"\b(?:article_content|article_title|content|title|text)\s+LIKE\b", re.IGNORECASE)


def _find_content_keyword_search(path: Path) -> list[int]:
    """找直接對文章內容或標題下 `LIKE` 的 SQL（自己做一份關鍵字搜尋）。走 AST 的理由同上：SQL 只活在字串裡。

    起因：公告、FB、論壇原本完全沒有搜尋，2026-10-08 做了 `services.search`（全文索引、短詞退路、
    來源上限、簡轉繁）。再各自 `LIKE '%…%'` 會少掉這些處理，也會在十萬列的表上全表掃描。
    """
    hits = []
    for node in ast.walk(_parse(path)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and _CONTENT_LIKE.search(node.value):
            hits.append(node.lineno)
    return hits


def _find_named_module_loggers(path: Path) -> list[int]:
    """找 `getLogger("寫死的名稱")`；設定檔裡定義的類別 logger 除外。

    模組 logger 一律 `getLogger(__name__)`：名稱＝模組路徑，`settings/logging.json` 才能依前綴
    分類。寫死名稱會讓所有紀錄叫同一個名字，分不出來源，也沒辦法用設定檔拆分。
    走 AST：`_code_lines` 會把字串內容遮掉，regex 看不到括號裡寫了什麼名稱。
    """
    from utils.logger_config import ARTICLE_MONITOR_LOGGER, LLM_ANOMALY_LOGGER
    category_loggers = {ARTICLE_MONITOR_LOGGER, LLM_ANOMALY_LOGGER}
    hits = []
    for node in ast.walk(_parse(path)):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        func_name = getattr(node.func, "attr", getattr(node.func, "id", None))
        arg = node.args[0]
        if (func_name == "getLogger" and isinstance(arg, ast.Constant)
                and isinstance(arg.value, str) and arg.value not in category_loggers):
            hits.append(node.lineno)
    return hits


def _is_tail_slice(node: ast.AST) -> bool:
    """`x[-4:]` 這種取尾巴的切片。"""
    return (isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Slice)
            and node.slice.upper is None and isinstance(node.slice.lower, ast.UnaryOp)
            and isinstance(node.slice.lower.op, ast.USub))


def _find_handwritten_person_anchors(path: Path) -> list[int]:
    """找自己拼的「名字#user_id 尾碼」：`f"#{uid[-4:]}"`，或先 `short = uid[-4:]` 再 `f"{name}#{short}"`。

    錨點是 prompt 裡認人的鍵（聊天行、人物卡、名字對照要同一個），撞號時還要自動加長——散在
    7 處各寫一份時，改長度得改 7 個地方，漏一處兩邊就對不上。只抓這兩種形狀：`#{...}` 在本專案
    很常見（行號、訊息編號），也有不少 `[-4:]` 只是給 log 看的 trace id，誤判會擋住啟動 gate。
    """
    hits: list[int] = []
    for func in ast.walk(_parse(path)):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Module)):
            continue
        sliced = {
            t.id
            for n in ast.walk(func) if isinstance(n, ast.Assign)
            if any(_is_tail_slice(x) for x in ast.walk(n.value))
            for t in n.targets if isinstance(t, ast.Name)
        }
        for node in ast.walk(func):
            if not isinstance(node, ast.JoinedStr):
                continue
            for prev, cur in zip(node.values, node.values[1:]):
                if not (isinstance(prev, ast.Constant) and str(prev.value).endswith("#")
                        and isinstance(cur, ast.FormattedValue)):
                    continue
                expr = cur.value
                if _is_tail_slice(expr) or (isinstance(expr, ast.Name) and expr.id in sliced):
                    hits.append(node.lineno)
    return sorted(set(hits))


def _find_syndication_urls(path: Path) -> list[int]:
    """找自己寫的 Twitter syndication CDN 網址。查貼文（類型、內文、縮圖）一律走 `utils.link_fix.fetch_tweet`，
    token 演算法與失敗時的 fail-open 規則只有一份。網址寫在字串裡，regex 規則看不到（字串會被遮掉），所以走 AST。"""
    return sorted({
        node.lineno for node in ast.walk(_parse(path))
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and "syndication.twimg.com" in node.value
    })


def _find_think_block_parsing(path: Path) -> list[int]:
    """找自己去掉 `<think>` 區塊、取模型最後一行的寫法。一律走 `llm.prompt.answer_line.final_line`：
    模型會在結論前多寫「第二行：」這類前綴，各寫一份就會有一份沒處理（看圖補字典曾把前綴寫進字典）。
    `<think>` 寫在字串裡，regex 規則看不到，所以走 AST。"""
    return sorted({
        node.lineno for node in ast.walk(_parse(path))
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and "<think>" in node.value
    })


def _find_thread_unarchive(path: Path) -> list[int]:
    """自己呼叫 `edit(archived=False)` 解封 thread。一律走 `utils.discord_threads.reopen_thread`：封存的 thread
    改不了也刪不了訊息，失敗怎麼處理只留一份。"""
    return sorted({
        node.lineno for node in ast.walk(_parse(path))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "edit"
        and any(k.arg == "archived" and isinstance(k.value, ast.Constant) and k.value.value is False
                for k in node.keywords)
    })


def _find_config_json_writes(path: Path) -> list[int]:
    """自己寫 config.json：`open(...config.json..., "w")` 或舊的整份覆寫 `save_config`。一律走
    `ChannelConfig.update_config`：寫入前重讀最新內容、只改這次的 key、安全寫入加備份（
    以前整份寫回快取，手改的內容會被蓋掉，檔案壞掉時會被寫成只剩一個 key）。"""
    hits = set()
    for node in ast.walk(_parse(path)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if name == "save_config":
            hits.add(node.lineno)
        if name == "open" and node.args:
            target = node.args[0]
            mode = node.args[1] if len(node.args) > 1 else next((k.value for k in node.keywords if k.arg == "mode"), None)
            if (isinstance(target, ast.Constant) and isinstance(target.value, str) and "config.json" in target.value
                    and isinstance(mode, ast.Constant) and isinstance(mode.value, str) and set(mode.value) & set("wax+")):
                hits.add(node.lineno)
    return sorted(hits)


# 2026-10-06 開關集中到 settings/switches.json 時已有的開關欄位：之後改到哪個功能就搬過去、從這裡移除（
# 有改到才搬）。改了要重啟或重建容器才生效，是它們該搬的原因。
_LEGACY_SWITCH_FIELDS = {
    "sys_settings/llm_settings.py:AmbientChatSettings.enabled",
    "sys_settings/llm_settings.py:AmbientChatSettings.use_shared_identity",
    "sys_settings/llm_settings.py:AmbientChatSettings.use_examples",
    "sys_settings/llm_settings.py:AmbientChatSettings.style_refs_enabled",
    "sys_settings/llm_settings.py:AmbientChatSettings.style_refs_debug",
    "sys_settings/llm_settings.py:AmbientChatSettings.callback_enabled",
    "sys_settings/llm_settings.py:AmbientChatSettings.callback_debug",
    "sys_settings/llm_settings.py:AmbientChatSettings.followup_enabled",
    "sys_settings/llm_settings.py:AmbientChatSettings.hook_enabled",
    "sys_settings/llm_settings.py:AmbientChatSettings.hook_knn_enabled",
    "sys_settings/llm_settings.py:AmbientChatSettings.hook_debug",
    "sys_settings/llm_settings.py:AmbientChatSettings.tag_spicy_dark_launch",
    "sys_settings/llm_settings.py:PersonaAgentSettings.enabled",
    "sys_settings/llm_settings.py:PersonaAgentSettings.mode",
    "sys_settings/llm_settings.py:PersonaAgentSettings.publish_mode",
    "sys_settings/llm_settings.py:DiaryReflectionSettings.enabled",
    "sys_settings/llm_settings.py:DiaryReflectionSettings.use_shared_identity",
    "sys_settings/llm_settings.py:EmojiAutofillSettings.mode",
    "sys_settings/periodic_reminder_settings.py:PeriodicReminderSettings.enabled",
    "sys_settings/pgvector_settings.py:RetrievalSourceConfig.enabled",
    "sys_settings/pgvector_settings.py:RetrievalSourceConfig.persist_mode",
}
# 名稱看得出是開關的：開／關、模式、試跑、灰度（dark_launch）、除錯輸出、use_／enable_ 開頭
_SWITCH_FIELD = re.compile(r"^(enabled|mode|dry_run|use_.*|enable_.*|.*_enabled|.*_mode|.*_dry_run|.*_debug|.*_dark_launch)$")


def _find_switch_fields(path: Path) -> list[int]:
    """sys_settings 裡新加的開關欄位（enabled、mode、dry_run…）。功能開關一律放 `settings/switches.json`
    （名稱、預設、允許的值寫在 `sys_settings.switches.Switches`）：改了就生效、不用重啟，也只有一個地方找。
    細項參數（逾時、張數）不算開關，照舊放各自的 sys_settings 類別。"""
    rel = Path(path).relative_to(SRC_DIR).as_posix()
    if not rel.startswith("sys_settings/"):
        return []
    hits = []
    for cls in (n for n in _parse(path).body if isinstance(n, ast.ClassDef)):
        for st in cls.body:
            if (isinstance(st, ast.AnnAssign) and isinstance(st.target, ast.Name) and _SWITCH_FIELD.match(st.target.id)
                    and f"{rel}:{cls.name}.{st.target.id}" not in _LEGACY_SWITCH_FIELDS):
                hits.append(st.lineno)
    return hits


def _find_hand_rolled_daily_quotas(path: Path) -> list[int]:
    """`_quota = ["", 0]` 這種自己用（日期, 次數）記每天額度的寫法。每天幾次的計數一律用 `utils.daily_quota.DailyQuota`
    （看圖補字典原本自己寫一份，插話查詢要第二份時抽出來）。寫法是個 list 字面值，所以走 AST。"""
    hits: list[int] = []
    for node in ast.walk(_parse(path)):
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        value = node.value
        if not (isinstance(value, ast.List) and len(value.elts) == 2
                and all(isinstance(e, ast.Constant) for e in value.elts)
                and isinstance(value.elts[0].value, str) and isinstance(value.elts[1].value, int)):
            continue
        if any(isinstance(t, ast.Name) and "quota" in t.id.lower() for t in targets):
            hits.append(node.lineno)
    return hits


def _is_http_startswith(node: ast.AST) -> bool:
    """`x.startswith("http://")`、`x.startswith(("http://", "https://"))` 這兩種寫法。"""
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "startswith"
            and node.args):
        return False
    arg = node.args[0]
    consts = arg.elts if isinstance(arg, ast.Tuple) else [arg]
    return any(isinstance(c, ast.Constant) and isinstance(c.value, str) and c.value.startswith(("http://", "https://"))
               for c in consts)


def _find_link_only_checks_in_tree(tree: ast.AST) -> list[int]:
    hits = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("all", "any")
                and node.args and isinstance(node.args[0], ast.GeneratorExp)
                and any(_is_http_startswith(inner) for inner in ast.walk(node.args[0].elt))):
            hits.append(node.lineno)
    return sorted(set(hits))


def _find_hand_rolled_link_only_checks(path: Path) -> list[int]:
    """`all(t.startswith("http://") or t.startswith("https://") for t in text.split())` 這種自己判斷「整則只有連結」
    的寫法（單一字串或 tuple 都抓）。一律用 `llm.preprocess.emoji_text_utils.is_link_only`（純表情、純貼圖是同模組的
    `is_emoji_or_symbol_only`），插話的內容閘、插話回憶、/askai 的相關名額才會用同一套標準。
    只抓「每個片段都是網址」這個形狀：單獨的 `url.startswith("https://")` 是在驗網址，不是在判斷整則，不抓。
    網址寫在字串裡，regex 規則看不到（字串會被遮掉），所以走 AST。"""
    return _find_link_only_checks_in_tree(_parse(path))


def _find_ffprobe_calls(path: Path) -> list[int]:
    """找自己組 ffprobe 指令的地方。讀影片長度一律走 `utils.media_probe.probe_duration`（逾時、失敗回 0、
    收掉子行程只有一份）。指令寫在字串裡，所以走 AST。"""
    return sorted({
        node.lineno for node in ast.walk(_parse(path))
        if isinstance(node, ast.Constant) and node.value == "ffprobe"
    })


def _find_sqlite_openers(path: Path) -> list[int]:
    """自己拼 articles.db 的路徑，或自己寫 SQLite 的唯讀／immutable 連線參數的字串。

    articles.db 是 WAL 模式、爬蟲一直在寫：要用 `mode=ro`、不能用 `immutable=1`（會看不到還在 WAL 裡的新公告，
    活動排程出過這個錯）。規則寫在註解守不住：改用 immutable 或漏掉 mode=ro 都不會紅。路徑與連線字串只有
    `sys_settings.paths` 一份。只看程式裡的字串常數，docstring 與 log 文案提到檔名不算。"""
    tree = _parse(path)
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                docstrings.add(id(first.value))
    hits = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)) or id(node) in docstrings:
            continue
        text = node.value
        if (text.endswith("articles.db") and not text.endswith("sent_articles.db")) or "mode=ro" in text or "immutable=" in text:
            hits.add(node.lineno)
    return sorted(hits)


def _find_user_date_parsing(path: Path) -> list[int]:
    """指令層（接使用者輸入的地方）自己用 strptime／fromisoformat 解析日期。使用者在視窗打的日期一律走
    `utils.user_dates`，全形、各種分隔符號、只寫日期這些寬鬆規則才只有一份（2026-10-04 社群稽查與預購截止合併）。
    只看 commands/：別處的 fromisoformat 多半是讀自己存的 ISO 字串，不是人打的字。"""
    if Path(path).relative_to(SRC_DIR).parts[0] != "commands":
        return []
    return sorted({
        node.lineno for node in ast.walk(_parse(path))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr in ("strptime", "fromisoformat")
    })


# 每種送出／寫紀錄各自只准哪些函式呼叫（審查 10-07：共用一份白名單時，搬移那段直接送出或寫主頻道紀錄也擋不到）
_RELAY_SENDERS = {
    "publish_to_channel": {"_send_unit", "resend_telegram_by_id"},
    "mark_message_published": {"_send_unit"},
    "moving_deliveries": {"_move_unit", "_record_after_deleted"},
}


def _find_relay_sends_outside_helper(path: Path) -> list[int]:
    """Telegram 轉發端在共用的 `_send_unit` 以外送出或寫發送紀錄。送出前要過濾、紀錄要記實際送到的頻道
    （主頻道或隔離 thread），各寫一份就會有一條路繞過過濾，或把隔離的記成主頻道（2026-10-06 接上 LLM 過濾）。
    - `resend_telegram_by_id` 是 /resend_article：使用者定案不過濾、也不寫紀錄，所以只准它送、不准寫紀錄。
    - 搬移（把已在主頻道的移進隔離區）經 `_send_unit` 送；改紀錄（`moving_deliveries`）只准 `_move_unit` 與
      原貼文全刪後重試的 `_record_after_deleted`。"""
    if Path(path).relative_to(SRC_DIR).as_posix() != "services/relay/telegram_relay_service.py":
        return []
    found = []

    def visit(node, owner):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                visit(child, child.name)
                continue
            if (isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute)
                    and child.func.attr in _RELAY_SENDERS
                    and owner not in _RELAY_SENDERS[child.func.attr]):
                found.append(child.lineno)
            visit(child, owner)

    visit(_parse(path), None)
    return sorted(found)


_TRADE_THREAD_READERS = {"read_trade_thread", "transcript"}


def _find_trade_thread_reads(path: Path) -> list[int]:
    """交易與商品模組自己翻交易 thread 的歷史。讀交易 thread 一律走 `TradeService.read`（`TradeThreadLog`）：
    讀多少則、哪些訊息算通知或按鈕只在一處（2026-10-04 架構檢視 B，以前七處各讀各的、讀太少就漏）。
    `transcript` 讀的是自由市場的需求貼文，不是交易 thread。"""
    if Path(path).relative_to(SRC_DIR).as_posix() not in (
            "services/community/trade_service.py", "services/community/shop_service.py"):
        return []
    found = []

    def visit(node, owner):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                visit(child, child.name)
                continue
            if (isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute)
                    and child.func.attr == "history" and owner not in _TRADE_THREAD_READERS):
                found.append(child.lineno)
            visit(child, owner)

    visit(_parse(path), None)
    return sorted(found)


def _string_mentions(filename: str):
    """找自己指到某個資料檔的字串（說明文字 docstring 提到檔名不算）。網址或路徑寫在字串裡，
    regex 規則看不到（字串會被遮掉），所以走 AST。"""
    def finder(path: Path) -> list[int]:
        tree = _parse(path)
        docstrings = {
            id(node.body[0].value) for node in ast.walk(tree)
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            and node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant)
        }
        return sorted({
            node.lineno for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings
            and filename in node.value
        })
    return finder


#: 字典一律走各自的讀寫模組：以前三個讀取者各自解析、各自快取，使用者手改字典要等 04:00
#: 偵測到新表情才會全部生效；AI 補描述也只能經過「不覆寫人寫的描述」那一關。
_find_emoji_dictionary_paths = _string_mentions("emoji_dictionary.txt")
_find_sticker_dictionary_paths = _string_mentions("sticker_dictionary.txt")


def _find_sleep_until_in_tree(tree: ast.Module) -> list[int]:
    """`asyncio.sleep(...)` 的秒數是從某個時刻算出來的（`.total_seconds()`，直接寫或先存進變數）。

    這是手寫定時排程的特徵：「算出離下一次還有幾秒、睡到那時」。固定間隔的 sleep
    （輪詢、重試、限速）不算，那些不是排程。
    """
    def calls_total_seconds(node: ast.AST) -> bool:
        return any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                   and n.func.attr == "total_seconds" for n in ast.walk(node))

    hits: set[int] = set()
    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        timed: set[str] = set()
        for node in ast.walk(func):
            if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)) and node.value is not None \
                    and calls_total_seconds(node.value):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                timed.update(t.id for t in targets if isinstance(t, ast.Name))
        for node in ast.walk(func):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "sleep" and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "asyncio" and node.args):
                continue
            arg = node.args[0]
            if calls_total_seconds(arg) or any(isinstance(n, ast.Name) and n.id in timed for n in ast.walk(arg)):
                hits.add(node.lineno)
    return sorted(hits)


def _find_tool_call_messages(path: Path) -> list[int]:
    """自己組工具呼叫訊息（`{"role": "tool", ...}` 或帶 `tool_call_id` 的 dict）的地方。格式一律走
    `llm.client.tool_calls`：每個 tool_call_id 都要回、id 要對上，少一則後端就拒絕（2026-10-09 /askai 接上
    情報搜尋，成為第二個工具迴圈時抽出）。"""
    found = []
    for node in ast.walk(_parse(path)):
        if not isinstance(node, ast.Dict):
            continue
        pairs = {k.value: v for k, v in zip(node.keys, node.values) if isinstance(k, ast.Constant)}
        role = pairs.get("role")
        if "tool_call_id" in pairs or (isinstance(role, ast.Constant) and role.value == "tool"):
            found.append(node.lineno)
    return sorted(found)


_SPLITTER_NAME = re.compile(r"^_?split\w*(text|content|message)", re.IGNORECASE)


def _find_message_splitters(path: Path) -> list[int]:
    """自己寫「把長文切成 Discord 放得下的多段」的函式。一律走 `utils.discord_content.split_message`：不丟內容、
    優先在換行與空白切、不把暴雷標記 `||` 切壞（2026-10-09 /askai 長回答要切段時，從 Telegram 轉發抽出）。"""
    return sorted(
        node.lineno for node in ast.walk(_parse(path))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _SPLITTER_NAME.match(node.name)
    )


def _find_direct_searxng_queries(path: Path) -> list[int]:
    """直接呼叫 `fetch_web_results` 打 SearXNG 的地方。一律走 `llm.retrievers.web.search_web`：哪類題目用哪組引擎、
    結果太少時換通用引擎補查，都是實測出來的規則，只能有一份（2026-10-09 網路搜尋改成模型用的工具、成為第二個
    呼叫端時，從 /askai 抽出）。"""
    found = []
    for node in ast.walk(_parse(path)):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            if name == "fetch_web_results":
                found.append(node.lineno)
    return sorted(found)


def _find_sleep_until(path: Path) -> list[int]:
    return _find_sleep_until_in_tree(_parse(path))

RULES = [
    Rule(
        name="全站時區",
        finder=_find_hardcoded_utc_offsets,
        canonical="sys_settings.time_settings.APP_TZ",
        allowed={
            "sys_settings/time_settings.py",
            # scraper 是獨立容器（掛 ./src/scraper → /app），看不到 sys_settings
            "scraper/tools/extract_fingerprint.py",
            # event_time_parser.SERVER_TZ 是「公告宣告的時區」，不是「本機時區」。
            # 值相同但語意不同，**收斂會出事**——見 AnnouncementTimezoneTests。
            "services/events/event_time_parser.py",
        },
    ),
    Rule(
        name="時區別名（一個東西多個名字＝收斂了等於沒收斂）",
        pattern=r"^\s*_?[A-Z_]*TZ\w* = APP_TZ",
        canonical="直接用 APP_TZ",
        allowed=set(),
    ),
    Rule(
        name="容器掛載點的路徑（寫死 /app、/logs 在容器外就找不到）",
        finder=_find_hardcoded_app_root,
        canonical="sys_settings.paths（APP_ROOT、LOGS_DIR、SETTINGS_DIR、prompt_file()…）",
        allowed={
            "sys_settings/paths.py",
            # 爬蟲是獨立容器（各自掛子目錄到 /app），看不到 sys_settings
            "scraper/",
            "telegram_scraper/",
            "test/",
        },
    ),
    Rule(
        name="settings/runtime/ 底下 bot 寫的 JSON（面板、點名、音樂、價格表、關鍵字監控）的讀寫",
        finder=_find_raw_runtime_json_io,
        canonical="utils.runtime_file.load / save / update（面板走 panel_bump 的 load_runtime / update_runtime）",
        allowed={
            "utils/runtime_file.py",
            # 人手改的 LLM 設定（llm_runtime_config.json），嚴格讀取、缺檔要炸；不是程式寫的狀態
            "sys_settings/llm_settings.py",
            # 爬蟲是獨立容器，看不到 utils
            "scraper/",
            "telegram_scraper/",
            "scripts/",
            "test/",
        },
    ),
    Rule(
        name="pgvector 連線",
        pattern=r"psycopg2\.connect\(",
        canonical="LLMServiceSettings.pgvector_connect()",
        allowed={"sys_settings/llm_settings.py"},
    ),
    Rule(
        name="LlamaIndex 向量庫（PGVectorStore）的建立：三處各自建，就會有一處漏掉借出前檢查",
        pattern=r"PGVectorStore\.from_params\(",
        canonical="LLMServiceSettings.pgvector_vector_store(table_name=…, embed_dim=…)",
        allowed={"sys_settings/llm_settings.py"},
    ),
    Rule(
        name="取 thread：快取沒有就 fetch、封存的也要拿得到、「不存在」與「暫時失敗」要分開（曾把一次 5xx 當成串被刪而清紀錄重開）",
        pattern=r"\.fetch_channel\(",
        canonical="utils.discord_threads.fetch_thread(client, thread_id, raise_errors=…)",
        allowed={
            "utils/discord_threads.py",
            # 取的是文字頻道不是 thread：Telegram 轉發的主頻道、搬隔離區的一次性腳本
            "services/relay/telegram_relay_service.py",
            "scripts/telegram_move_to_quarantine.py",
        },
    ),
    Rule(
        name="取伺服器成員：先查快取、沒有再向 API 查（快取偶爾漏人，接單曾因此失敗）",
        pattern=r"\bguild\.fetch_member\(",
        canonical="utils.discord_members.resolve_member(guild, user_id)",
        allowed={
            "utils/discord_members.py",
            # 點名刻意只用 API：快取漏人會把還在的人誤判成離開而踢掉
            "services/community/rollcall_service.py",
        },
    ),
    Rule(
        name="實體表名（沒消毒會有 identifier 注入風險）",
        pattern=r'f"data_\{',
        canonical="HybridRetrievalSettings.physical_table() / chat_table() / source_table()",
        allowed={"sys_settings/pgvector_settings.py"},
    ),
    Rule(
        name="prompt 檔 mtime 快取",
        pattern=r'_PROMPT_CACHE\s*[:=]\s*(?:dict)?\s*[:=]?\s*\{"text"',
        canonical="utils.hot_files.read_text() / read_json()",
        # ambient_reply 是多檔疊層（identity+guardrails+行為+examples）且有自己的
        # 組裝順序，硬套單檔載入器反而更繞——形狀不同就不該硬收斂。
        allowed={"utils/hot_files.py", "llm/ambient/ambient_reply.py"},
    ),
    Rule(
        name="模組 logger 一律用 __name__（分類與去向寫在 settings/logging.json）",
        finder=_find_named_module_loggers,
        canonical="logging.getLogger(__name__)",
        # discord_bot.py 以 script 執行（__name__ 是 __main__），明確命名成 discord_bot；
        # scraper 是獨立容器、有自己的 utils/logger.py；scripts 是手動執行的 CLI 工具
        allowed={"discord_bot.py", "scraper/", "scripts/"},
    ),
    Rule(
        name="prompt 裡認人的錨點（名字#尾碼）",
        finder=_find_handwritten_person_anchors,
        canonical="llm.preprocess.person_anchor.label() / suffix()",
        allowed={"llm/preprocess/person_anchor.py"},
    ),
    Rule(
        name="群友的 Discord 名字（顯示名稱、伺服器暱稱、全域名稱）",
        pattern=r"\.global_name\b|\.nick\b",
        canonical="llm.persona.member_names.member_names_from_guild()",
        # 名字要從同一處讀，④ 的名字表、⑤ 的擋名字、白天的名字對照與找人才會一致
        allowed={"llm/persona/member_names.py"},
    ),
    Rule(
        name="查 X 貼文（syndication CDN）",
        finder=_find_syndication_urls,
        canonical="utils.link_fix.fetch_tweet / llm.preprocess.tweet_context.expand_tweets",
        allowed={"utils/link_fix.py"},
    ),
    Rule(
        name="讀寫自訂表情字典",
        finder=_find_emoji_dictionary_paths,
        canonical="llm.preprocess.emoji_dictionary.entries() / fill()",
        allowed={"llm/preprocess/emoji_dictionary.py"},
    ),
    Rule(
        name="讀寫別的伺服器的貼圖字典",
        finder=_find_sticker_dictionary_paths,
        canonical="llm.preprocess.sticker_dictionary.lookup() / add()",
        allowed={"llm/preprocess/sticker_dictionary.py"},
    ),
    Rule(
        name="不用 print 記錄（只會出現在 docker logs，不會進 log 檔）",
        pattern=r"(?<![\w.])print\(",
        canonical="logging.getLogger(__name__)",
        # scraper 是獨立容器；scripts 是手動執行的 CLI 工具。
        # telegram_scraper 也是獨立容器，但已改用 logger（log_config.py 由入口設定）
        allowed={"scraper/", "scripts/"},
    ),
    Rule(
        name="爬蟲下載 Telegram 媒體（卡住偵測）",
        pattern=r"\.download_media\(",
        canonical="telegram_scraper.media_download.download_with_stall_guard",
        # Telethon 的 download_media 沒有逾時，照片曾卡 1～1.6 小時、整輪補掃跟著停；一律經過卡住偵測
        allowed={"telegram_scraper/media_download.py"},
    ),
    Rule(
        name="取模型回答的最後一行結論（去思考區塊與照抄格式的前綴）",
        finder=_find_think_block_parsing,
        canonical="llm.prompt.answer_line.final_line",
        allowed={"llm/prompt/answer_line.py"},
    ),
    Rule(
        name="功能開關（開／關、off／dry_run／on）",
        finder=_find_switch_fields,
        canonical="settings/switches.json（名稱、預設、允許的值：sys_settings.switches.Switches）",
        allowed={"sys_settings/switches.py"},
    ),
    Rule(
        name="寫 config.json",
        finder=_find_config_json_writes,
        canonical="ChannelConfig.update_config（重讀最新內容、只改這次的 key、安全寫入加備份）",
        allowed={"utils/utils.py"},
    ),
    Rule(
        name="整則只有連結的判斷（純連結、純表情、純貼圖要同一套標準）",
        finder=_find_hand_rolled_link_only_checks,
        canonical="llm.preprocess.emoji_text_utils.is_link_only／is_emoji_or_symbol_only",
        allowed={
            "llm/preprocess/emoji_text_utils.py",
            # 爬蟲是獨立容器，判斷的是網頁上的連結，不是聊天訊息
            "scraper/",
        },
    ),
    Rule(
        name="每天最多做幾次的計數（換日歸零）",
        finder=_find_hand_rolled_daily_quotas,
        canonical="utils.daily_quota.DailyQuota",
        allowed=set(),
    ),
    Rule(
        name="讀影片長度（ffprobe）",
        finder=_find_ffprobe_calls,
        canonical="utils.media_probe.probe_duration",
        allowed={"utils/media_probe.py"},
    ),
    Rule(
        name="跑子行程（ffmpeg 這類）：每一處都要有逾時、逾時要收掉行程（轉發一次只處理一則，卡住整條就停）",
        pattern=r"create_subprocess_exec\(|create_subprocess_shell\(|subprocess\.(?:run|Popen|check_output)\(",
        canonical="utils.media_probe.run_media_tool(cmd, timeout=…)",
        allowed={"utils/media_probe.py", "scraper/", "telegram_scraper/"},
    ),
    Rule(
        name="開 articles.db：路徑與唯讀連線字串只有一份（mode=ro、不用 immutable）",
        finder=_find_sqlite_openers,
        canonical="sys_settings.paths.sqlite_readonly_uri(path)（articles.db 的路徑用 ARTICLES_DB）",
        allowed={"sys_settings/paths.py", "scraper/", "telegram_scraper/"},
    ),
    Rule(
        name="Telegram 轉發送出與寫發送紀錄",
        finder=_find_relay_sends_outside_helper,
        canonical="MessageRelayWorker._send_unit（送出前由呼叫端過濾、決定去向）",
        allowed=set(),
    ),
    Rule(
        name="解除 thread 封存",
        finder=_find_thread_unarchive,
        canonical="utils.discord_threads.reopen_thread（取得 thread 用 fetch_thread）",
        # 2026-10-06 抽出時已有這五份，之後改到哪個檔就順手換掉、從這裡移除
        allowed={
            "utils/discord_threads.py",
            "commands/community_lookup_commands.py",
            "services/community/trade_service.py",
            "services/community/shop_service.py",
            "services/relay/bahamut_monitor.py",
        },
    ),
    Rule(
        name="官方公告原文網址",
        finder=_find_hardcoded_article_urls,
        canonical="services.source_urls.official_article_url()",
        allowed={"services/source_urls.py"},
    ),
    Rule(
        name="對公告、FB、論壇文章做關鍵字搜尋",
        finder=_find_content_keyword_search,
        canonical="services.search（SearchIndex.search／fetch）",
        # VersionDateResolver 找的是固定格式的公告（維護預告、第二期卡池），不是給人搜尋
        allowed={"services/events/event_scheduler.py"},
    ),
    Rule(
        name="名次融合（RRF）",
        pattern=r"def\s+_?\w*rrf\w*\s*\(",
        canonical="utils.rank_fusion（rrf_score／fuse_rankings）",
        allowed={"utils/rank_fusion.py"},
    ),
    Rule(
        name="巴哈單一樓層網址",
        finder=_find_hardcoded_bahamut_floor_urls,
        canonical="services.source_urls.bahamut_floor_url()",
        allowed={"services/source_urls.py"},
    ),
    Rule(
        name="讀交易 thread 的歷史",
        finder=_find_trade_thread_reads,
        canonical="TradeService.read（services.community.trade_service.TradeThreadLog）",
        allowed=set(),
    ),
    Rule(
        name="解析使用者在視窗打的日期／時間",
        finder=_find_user_date_parsing,
        canonical="utils.user_dates.parse_user_date / parse_user_datetime",
        # 點名讀的是自己存在 runtime 檔的 ISO 截止時間，不是人打的字
        allowed={"commands/rollcall_commands.py"},
    ),
    Rule(
        name="頻道沒綁定的判斷（比對 ChannelConfig.DEFAULT_ID）",
        pattern=r"[!=]=\s*ChannelConfig\.DEFAULT_ID",
        canonical="ChannelConfig.get_configured_id()（沒綁定回 None）",
        # 2026-10-03 收成 get_configured_id 時已有這六份，之後改到哪個檔就順手換掉、從這裡移除
        allowed={
            "utils/utils.py",
            "services/community/member_welcome.py",
            "llm/ambient/ambient_reply.py",
            "llm/ambient/ambient_diary.py",
            "commands/periodic_reminder_commands.py",
            "commands/management_commands.py",
            "commands/community_lookup_commands.py",
        },
    ),
    Rule(
        name="工具呼叫的訊息格式（assistant 的 tool_calls、role: tool 的回覆、解析工具參數）",
        finder=_find_tool_call_messages,
        canonical="llm.client.tool_calls（assistant_message／tool_message／call_name_and_arguments／parse_arguments）",
        allowed={"llm/client/tool_calls.py"},
    ),
    Rule(
        name="把長文切成 Discord 放得下的多段",
        finder=_find_message_splitters,
        canonical="utils.discord_content.split_message",
        allowed={
            "utils/discord_content.py",
            # 搜尋索引的切段是給向量用的（有重疊、每段帶標題），不是切訊息
            "services/search/chunking.py",
            # 巴哈轉發的 embed 切段（第一段放標題、首段與後續段上限不同），2026-10-09 抽出共用版時已存在，改到再搬
            "services/relay/bahamut_monitor.py",
        },
    ),
    Rule(
        name="網路搜尋（SearXNG 的引擎路由與結果太少時補查）",
        finder=_find_direct_searxng_queries,
        canonical="llm.retrievers.web.search_web",
        allowed={"llm/retrievers/web/"},
    ),
    Rule(
        name="定時排程（算出離下一次還有幾秒、睡到那時）",
        finder=_find_sleep_until,
        canonical="utils.due_loop.run_due_loop（tick 回傳下一次的時刻）",
        allowed=set(),
    ),
    Rule(
        name="指令一律用斜線（前綴指令是一般訊息，會被當聊天存進向量庫）",
        pattern=r"@(?:commands|bot)\.command\(",
        canonical="@app_commands.command（discord.app_commands）",
        allowed=set(),
    ),
    Rule(
        name="背景任務：結果被丟掉的 create_task（沒人留參照、失敗沒人知道）",
        finder=_find_discarded_create_task,
        canonical="utils.background_tasks.spawn（該一直跑的迴圈用 supervise）",
        allowed={
            # 獨立容器，看不到 utils
            "scraper/",
            "telegram_scraper/",
        },
    ),
]


def _source_files():
    for path in Path(SRC_DIR).rglob("*.py"):
        rel = str(path.relative_to(SRC_DIR))
        if rel.startswith("test/") or "__pycache__" in rel:
            continue
        yield rel, path


@functools.cache
def _code_lines(path: Path) -> list[tuple[int, str]]:
    """回傳 (行號, 只剩程式碼的該行)——註解與字串內容都遮成空白。

    用 `tokenize` 而不是「開頭是不是 #」：說明文字裡本來就會提到被禁的樣式
    （例如 docstring 寫「原本六處各自 psycopg2.connect(...)」），用行首判斷會誤判，
    而**誤判會讓容器啟動 gate 紅掉**，比漏判更難收拾。

    快取理由同 `_parse`：4 條 regex 規則會各掃一遍同一批檔，而 tokenize 是重工。
    **回傳的 list 不可以被 caller 就地修改**（現在都只讀著跑 regex），否則會污染快取。
    """
    src = path.read_text(encoding="utf-8")
    lines = src.splitlines()
    masked = list(lines)
    try:
        with tokenize.open(path) as fh:
            tokens = list(tokenize.generate_tokens(fh.readline))
    except (tokenize.TokenError, SyntaxError, UnicodeDecodeError):
        return list(enumerate(lines, 1))
    for tok in tokens:
        if tok.type not in (tokenize.COMMENT, tokenize.STRING):
            continue
        (r1, c1), (r2, c2) = tok.start, tok.end
        for row in range(r1, r2 + 1):
            i = row - 1
            if i >= len(masked):
                break
            line = masked[i]
            start = c1 if row == r1 else 0
            end = c2 if row == r2 else len(line)
            masked[i] = line[:start] + " " * (end - start) + line[end:]
    return list(enumerate(masked, 1))


class NoReinventedWheelsTests(unittest.TestCase):
    """掃原始碼而非列舉模組——列舉只擋得住今天存在的檔案，掃描連明天新增的也擋。"""

    def test_every_shared_component_has_one_source(self):
        for rule in RULES:
            with self.subTest(rule=rule.name):
                offenders = []
                for rel, path in _source_files():
                    if rule.allows(rel):
                        continue
                    if rule.finder is not None:
                        offenders.extend(f"{rel}:{i}" for i in rule.finder(path))
                        continue
                    for i, line in _code_lines(path):
                        if re.search(rule.pattern, line):
                            offenders.append(f"{rel}:{i}")
                self.assertEqual(
                    offenders, [],
                    f"「{rule.name}」只能有一個來源（{rule.canonical}）；"
                    f"以下自己造了一份：{offenders}",
                )


class TimezoneGuardTests(unittest.TestCase):
    """守衛自己的守衛：證明「換個 import 別名」躲不掉。

    2026-09-02 的真實漏網：`discord_bot.py` 的日記排程寫成 `_tz(_td(hours=8))`
    （`timezone as _tz` / `timedelta as _td`），regex 版守衛完全沒反應，違規就這樣
    綠燈躺著。改用 AST 之後補這一組——**沒有它，哪天有人把 finder「簡化」回 regex，
    一樣不會有任何測試變紅**，等於白修一次。
    """

    def test_catches_plain_form(self):
        src = "from datetime import timezone, timedelta\nTZ = timezone(timedelta(hours=8))\n"
        self.assertEqual(_find_hardcoded_utc_offsets_in_source(src), [2])

    def test_catches_aliased_form(self):
        """真實漏網的那一種。"""
        src = (
            "from datetime import timezone as _tz, timedelta as _td\n"
            "DIARY_TZ = _tz(_td(hours=8))\n"
        )
        self.assertEqual(_find_hardcoded_utc_offsets_in_source(src), [2])

    def test_catches_module_attribute_form(self):
        src = "import datetime as dt\nTZ = dt.timezone(dt.timedelta(hours=8))\n"
        self.assertEqual(_find_hardcoded_utc_offsets_in_source(src), [2])

    def test_ignores_timedelta_used_as_duration(self):
        """`timedelta(hours=8)` 當「時間長度」是完全合法的，不可以誤判。"""
        src = "from datetime import timedelta\nGRACE = timedelta(hours=8)\n"
        self.assertEqual(_find_hardcoded_utc_offsets_in_source(src), [])

    def test_ignores_timezone_utc(self):
        src = "from datetime import timezone\nUTC = timezone.utc\n"
        self.assertEqual(_find_hardcoded_utc_offsets_in_source(src), [])


class LinkOnlyFinderTests(unittest.TestCase):
    """「整則只有連結」規則的偵測器本身：抓 all(...) 裡的 startswith(http)（單一字串與 tuple），不抓單純驗網址的 startswith。"""

    def _scan(self, src):
        return _find_link_only_checks_in_tree(ast.parse(src))

    def test_catches_plain_and_tuple_forms(self):
        src = (
            "def a(s):\n    return all(t.startswith('http://') or t.startswith('https://') for t in s.split())\n"
            "def b(s):\n    return any(t.startswith(('http://', 'https://')) for t in s.split())\n"
        )
        self.assertEqual(self._scan(src), [2, 4])

    def test_ignores_plain_url_validation(self):
        src = "def ok(url):\n    return url.startswith('https://') and 'x' in url\n"
        self.assertEqual(self._scan(src), [])


class SleepUntilFinderTests(unittest.TestCase):
    """「定時排程」規則的偵測器本身。四份手寫排程都是先把秒數存進變數再睡，
    只認 `asyncio.sleep(x.total_seconds())` 的話一份都抓不到。"""

    def _scan(self, src):
        return _find_sleep_until_in_tree(ast.parse(src))

    def test_catches_seconds_computed_into_a_variable(self):
        src = (
            "import asyncio\n"
            "async def loop(target, now):\n"
            "    wait_seconds = (target - now).total_seconds()\n"
            "    await asyncio.sleep(max(wait_seconds, 1))\n"
        )
        self.assertEqual(self._scan(src), [4])

    def test_ignores_fixed_intervals(self):
        src = (
            "import asyncio\n"
            "INTERVAL = 6 * 3600\n"
            "async def loop():\n"
            "    await asyncio.sleep(INTERVAL)\n"
            "    await asyncio.sleep(0.5)\n"
        )
        self.assertEqual(self._scan(src), [])


class AnnouncementTimezoneTests(unittest.TestCase):
    """**這一組守的是「不可以合併」**，跟本檔其他規則方向相反。

    `SERVER_TZ`（公告宣告的伺服器時間，遊戲決定、固定 UTC+8）曾經被誤併進
    `APP_TZ`（本機時區，可設定）。兩者今天同值，所以測試不會紅、人也看不出來，
    但只要 `APP_UTC_OFFSET_HOURS` 一改就有兩種災情：

      ① 公告「10:00（伺服器時間）」被當成新時區的 10:00 → 活動時間整批偏移
      ② `event_fingerprint` 用它正規化 → 既有指紋全部失配 → 去重表失效、
         所有舊活動被重新建立一次（`created_events` 是持久化的）

    值相同不代表是同一件事——這裡刻意驗「不是同一個物件」而不是「值不同」。
    """

    def test_server_tz_is_independent_of_app_tz(self):
        from services.events.event_time_parser import SERVER_TZ
        from sys_settings.time_settings import APP_TZ

        self.assertIsNot(
            SERVER_TZ, APP_TZ,
            "SERVER_TZ 是公告宣告的時區、APP_TZ 是本機時區，不可以指向同一個物件",
        )

    def test_server_tz_is_pinned_to_utc8(self):
        """公告的閘門只認 UTC+8／GMT+8，所以這個常數必須釘死。"""
        from services.events.event_time_parser import SERVER_TZ

        self.assertEqual(SERVER_TZ.utcoffset(None).total_seconds() / 3600, 8)

    def test_fingerprint_is_stable_regardless_of_app_tz(self):
        """指紋若跟著本機時區跑，去重表會整批失效。"""
        from datetime import datetime, timedelta, timezone

        from services.events.event_time_parser import SERVER_TZ, event_fingerprint

        start = datetime(2026, 8, 20, 10, 0, tzinfo=SERVER_TZ)
        end = datetime(2026, 9, 3, 23, 59, tzinfo=SERVER_TZ)
        baseline = event_fingerprint("坎特蕾拉", start, end)
        # 同一時刻、換個時區表示 → 指紋必須相同
        other = timezone(timedelta(hours=0))
        self.assertEqual(
            baseline,
            event_fingerprint("坎特蕾拉", start.astimezone(other), end.astimezone(other)),
        )


class UndefinedConstantTests(unittest.TestCase):
    """引用了不存在的模組層常數 → 執行期才 NameError。

    **這組測試存在的原因**：一次 patch 腳本在寫檔前就中斷，`ESTIMATE_SCALE_RANGE`
    的定義沒被寫進去，但引用它的程式碼寫進去了。`py_compile` 全過（Python 執行期
    才解析名字）、303 個測試也全過（那段分支的條件在假資料裡從沒成立），
    直到真的跑起來才炸。

    只查 ALL_CAPS 名字：那幾乎一定是模組層常數，判定明確、誤判率低。
    完整的名字解析要做作用域分析，那是 linter 的工作，這裡只補最會出事的那一類。
    """

    def test_no_constant_is_used_without_being_defined(self):
        offenders = []
        for rel, path in _source_files():
            tree = _parse(path)
            defined = set(dir(builtins))
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for t in node.targets:
                        if isinstance(t, ast.Name):
                            defined.add(t.id)
                        elif isinstance(t, ast.Tuple):
                            defined.update(
                                e.id for e in t.elts if isinstance(e, ast.Name)
                            )
                elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                    defined.add(node.target.id)
                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    for a in node.names:
                        defined.add((a.asname or a.name).split(".")[0])
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    defined.add(node.name)
                elif isinstance(node, ast.Global):
                    defined.update(node.names)
                elif isinstance(node, (ast.For, ast.comprehension)):
                    target = getattr(node, "target", None)
                    if isinstance(target, ast.Name):
                        defined.add(target.id)

            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Name)
                    and isinstance(node.ctx, ast.Load)
                    and node.id.isupper()
                    and len(node.id) > 2
                    and node.id not in defined
                ):
                    offenders.append(f"{rel}:{node.lineno} {node.id}")

        self.assertEqual(
            offenders, [],
            f"引用了沒有定義的常數（執行期才會 NameError）：{offenders}",
        )


class CanonicalHelperTests(unittest.TestCase):
    """正規元件本身的行為（規則指向它們，它們得先是對的）。"""

    def test_table_name_is_sanitized(self):
        self.assertEqual(H.physical_table("ok_name_1"), "data_ok_name_1")
        self.assertEqual(H.physical_table('a-b";DROP TABLE x'), "data_abDROPTABLEx")

    def test_source_table_raises_when_unknown_and_no_default(self):
        with self.assertRaises(KeyError):
            H.source_table("no_such_source")

    def test_timezone_offset_comes_from_settings(self):
        from sys_settings.time_settings import APP_TZ, TimeSettings

        self.assertEqual(TimeSettings().app_utc_offset_hours, 8)
        self.assertEqual(APP_TZ.utcoffset(None).total_seconds() / 3600, 8)

    def test_askai_no_longer_owns_the_timezone(self):
        """舊的 askai 專屬欄位已移除——留著會變成第二個真相來源。"""
        from sys_settings.llm_settings import AskAICommandSettings

        self.assertNotIn("taipei_utc_offset_hours", AskAICommandSettings.model_fields)

    def test_prompt_loader_handles_missing_files(self):
        from utils import hot_files

        self.assertEqual(hot_files.read_text("/nope/missing.txt"), "")
        self.assertIsNone(hot_files.read_json("/nope/missing.json"))


class DiscardedCreateTaskFinderTests(unittest.TestCase):
    """守衛的 finder 本身：只抓「結果被丟掉」的那幾種寫法，留著參照的不抓（抓錯會讓 gate 紅掉）。"""

    def test_flags_only_statements_that_drop_the_task(self):
        src = textwrap.dedent("""
            import asyncio
            async def f():
                asyncio.create_task(a())                        # 丟掉
                asyncio.get_running_loop().create_task(b())     # 丟掉
                asyncio.ensure_future(c())                      # 丟掉
                task = asyncio.create_task(d())                 # 留著
                tasks.append(asyncio.create_task(e()))          # 留著
                await asyncio.create_task(g())                  # 留著
                spawn(h(), name="x")                            # 走統一入口
        """)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.py"
            path.write_text(src, encoding="utf-8")
            self.assertEqual(_find_discarded_create_task(path), [4, 5, 6])


if __name__ == "__main__":
    unittest.main()
