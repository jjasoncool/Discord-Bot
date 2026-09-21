"""跨模組共用慣例的守衛（收斂後防止再度分岔）。

守的不是某個功能，而是「**同一件事只有一個來源**」這個結構性約定。

為什麼用測試而不是寫在文件裡：這個專案大部分由 AI 協作，而文件會被略讀、慣例會被
遺忘，但**紅掉的測試不會**。每條規則都是一次真實分岔的紀錄：

  - 實體表名：四處各自拼 `f"data_{...}"`，其中兩處**沒有消毒**（SQL identifier 注入）
  - 全站時區：八處各自寫死 UTC+8，四種命名；唯一可設定的來源只有一處在用
    （2026-09-02 追加：regex 版守衛被 `timezone as _tz` 的 import 別名繞過，改走 AST）
  - pgvector 連線：六處抄同樣的五個參數；要加 timeout 或換驅動得改六個地方
  - prompt 載入：三份一字不差的 mtime 快取實作

**新增共用元件時，順手在 `RULES` 加一條**，下一個人（或下一輪的 AI）就不會重造。

執行：
    cd src && python -m unittest test.test_shared_conventions -v
"""

import ast
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
        #: 根目錄看不到 sys_settings，只能自己保留一份。
        self.allowed = allowed


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
            "services/event_time_parser.py",
        },
    ),
    Rule(
        name="時區別名（一個東西多個名字＝收斂了等於沒收斂）",
        pattern=r"^\s*_?[A-Z_]*TZ\w* = APP_TZ",
        canonical="直接用 APP_TZ",
        allowed=set(),
    ),
    Rule(
        name="pgvector 連線",
        pattern=r"psycopg2\.connect\(",
        canonical="LLMServiceSettings.pgvector_connect()",
        allowed={"sys_settings/llm_settings.py"},
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
        canonical="llm.prompt_files.read_text() / read_json()",
        # ambient_reply 是多檔疊層（identity+guardrails+行為+examples）且有自己的
        # 組裝順序，硬套單檔載入器反而更繞——形狀不同就不該硬收斂。
        allowed={"llm/prompt_files.py", "llm/ambient_reply.py"},
    ),
    Rule(
        name="官方公告原文網址",
        finder=_find_hardcoded_article_urls,
        canonical="services.article_monitor.official_article_url()",
        allowed={"services/article_monitor.py"},
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
                    if rel in rule.allowed:
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
        from services.event_time_parser import SERVER_TZ
        from sys_settings.time_settings import APP_TZ

        self.assertIsNot(
            SERVER_TZ, APP_TZ,
            "SERVER_TZ 是公告宣告的時區、APP_TZ 是本機時區，不可以指向同一個物件",
        )

    def test_server_tz_is_pinned_to_utc8(self):
        """公告的閘門只認 UTC+8／GMT+8，所以這個常數必須釘死。"""
        from services.event_time_parser import SERVER_TZ

        self.assertEqual(SERVER_TZ.utcoffset(None).total_seconds() / 3600, 8)

    def test_fingerprint_is_stable_regardless_of_app_tz(self):
        """指紋若跟著本機時區跑，去重表會整批失效。"""
        from datetime import datetime, timedelta, timezone

        from services.event_time_parser import SERVER_TZ, event_fingerprint

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
        from llm import prompt_files

        self.assertEqual(prompt_files.read_text("/nope/missing.txt"), "")
        self.assertIsNone(prompt_files.read_json("/nope/missing.json"))


if __name__ == "__main__":
    unittest.main()
