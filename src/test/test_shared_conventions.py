"""跨模組共用慣例的守衛（收斂後防止再度分岔）。

守的不是某個功能，而是「**同一件事只有一個來源**」這個結構性約定。

為什麼用測試而不是寫在文件裡：這個專案大部分由 AI 協作，而文件會被略讀、慣例會被
遺忘，但**紅掉的測試不會**。每條規則都是一次真實分岔的紀錄：

  - 實體表名：四處各自拼 `f"data_{...}"`，其中兩處**沒有消毒**（SQL identifier 注入）
  - 全站時區：八處各自寫死 UTC+8，四種命名；唯一可設定的來源只有一處在用
  - pgvector 連線：六處抄同樣的五個參數；要加 timeout 或換驅動得改六個地方
  - prompt 載入：三份一字不差的 mtime 快取實作

**新增共用元件時，順手在 `RULES` 加一條**，下一個人（或下一輪的 AI）就不會重造。

執行：
    cd src && python -m unittest test.test_shared_conventions -v
"""

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
    """一條「這件事只能有一個來源」的規則。"""

    def __init__(self, name: str, pattern: str, canonical: str, allowed: set[str]):
        self.name = name
        self.pattern = pattern
        self.canonical = canonical
        #: 合法的例外。scraper 是獨立容器（掛載 ./src/scraper → /app），
        #: 根目錄看不到 sys_settings，只能自己保留一份。
        self.allowed = allowed


RULES = [
    Rule(
        name="全站時區",
        pattern=r"timezone\(timedelta\(hours=",
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
]


def _source_files():
    for path in Path(SRC_DIR).rglob("*.py"):
        rel = str(path.relative_to(SRC_DIR))
        if rel.startswith("test/") or "__pycache__" in rel:
            continue
        yield rel, path


def _code_lines(path: Path) -> list[tuple[int, str]]:
    """回傳 (行號, 只剩程式碼的該行)——註解與字串內容都遮成空白。

    用 `tokenize` 而不是「開頭是不是 #」：說明文字裡本來就會提到被禁的樣式
    （例如 docstring 寫「原本六處各自 psycopg2.connect(...)」），用行首判斷會誤判，
    而**誤判會讓容器啟動 gate 紅掉**，比漏判更難收拾。
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
                    for i, line in _code_lines(path):
                        if re.search(rule.pattern, line):
                            offenders.append(f"{rel}:{i}")
                self.assertEqual(
                    offenders, [],
                    f"「{rule.name}」只能有一個來源（{rule.canonical}）；"
                    f"以下自己造了一份：{offenders}",
                )


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
