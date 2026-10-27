"""分層方向的守衛：每個模組屬於哪一層寫在這裡，import 只能指向同層或更下層。

守的底線：
  - 層級由下往上：基礎（utils、sys_settings、settings、constants）→ 技術 → 服務 → 功能 → 介面（commands、discord_bot、music）
  - `llm/` 與 `services/` 兩個資料夾各自橫跨三層（定義：services＝服務、llm＝LLM 相關技術且 AI 功能也在裡面），
    所以分類寫到子資料夾／模組，不以頂層資料夾為準
  - 往上 import 一律紅，不分檔案開頭或函式內（函式內的延遲 import 多半是為了繞循環，正是這裡要抓的）
  - `if TYPE_CHECKING:` 裡的 import 不算（執行時不存在）
  - 每個模組都要分得到層；新資料夾沒登記就紅，逼人想清楚它是哪一層
  - 跨容器 import（`scraper`、`telegram_scraper` 各自是獨立容器）也算違規；現有的列在例外並寫理由，整理套件撞名時清掉
  - 技術層與服務層不可 import discord（`TYPE_CHECKING` 裡的不算）：它們要能離開 Discord 測試、重用；
    功能層與介面層就是 Discord 應用本身，可以；基礎層只有列在 `DISCORD_HELPERS_IN_BASE` 的 Discord 工具可以

分類表（`LAYERS`）就是文件：改分類＝改這張表，連同理由。

執行：
    cd src && python -m unittest test.test_layering -v
"""

import ast
import os
import sys
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(HERE)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

BASE, TECH, SERVICE, FEATURE, INTERFACE = 0, 1, 2, 3, 4
NAMES = {BASE: "基礎", TECH: "技術", SERVICE: "服務", FEATURE: "功能", INTERFACE: "介面"}

#: 模組前綴 → 層級。前面的先符合（子資料夾、單一模組寫在它所屬套件的前面）。
LAYERS = [
    # ── llm/ 裡的 AI 功能：使用者看得到的行為本身 ──
    ("llm.ambient", FEATURE),                       # 插話、日記、罵人應對
    ("llm.persona.agent", FEATURE),                 # 每晚的人格萃取 agent
    ("llm.persona.personality_extractor", FEATURE),  # 每晚的人格萃取（舊流程）
    ("llm.persona.daily_maintenance", FEATURE),     # 每日 04:00 維護的編排（五步順序、補跑）
    ("llm.preprocess.emoji_autofill", FEATURE),     # 看圖補字典（on_message 觸發）
    ("llm.storage.store_chat", FEATURE),            # Discord 訊息寫進聊天向量庫
    ("llm.storage.raw_message_store", FEATURE),     # Discord 訊息寫進原始備份表
    ("llm.storage.chat_index_backfill", FEATURE),   # 從原始備份補寫聊天向量庫漏掉的（交給 store_chat 寫）
    ("llm.storage.chat_reembed", FEATURE),          # 重算聊天向量（只嵌內文）到影子欄，另開行程手動跑
    # ── llm/ 裡的服務：共用的能力、資料存取、橋接 ──
    ("llm.storage.member_profile_store", SERVICE),  # 成員檔案（自介、印象、AI 觀察、偏好）的存取
    ("llm.storage.ai_interactions_store", SERVICE), # 插話互動紀錄的存取
    ("llm.retrievers.context_retriever", SERVICE),  # 聊天脈絡檢索：/askai、插話、寫入都用
    ("llm.retrievers.eval", SERVICE),               # 聊天檢索的評估（手動工具，考 search_chat）
    ("llm.retrievers.chat_search", SERVICE),        # /askai 的聊天紀錄搜尋工具（字面計數＋search_chat）
    ("llm.persona.member_names", SERVICE),          # 群友名字查詢（讀成員檔案）
    ("llm.persona.preference_extractor", SERVICE),  # 記憶服務的零件：抽偏好事實
    ("llm.persona.signature_tag_extractor", SERVICE),  # 記憶服務的零件：抽招牌梗
    ("llm.mcp_server", SERVICE),                    # 把搜尋服務接上 MCP 協定（橋接）
    # ── llm/ 裡的技術 ──
    ("llm.client", TECH), ("llm.prompt", TECH), ("llm.preprocess", TECH), ("llm.retrievers", TECH),
    ("llm.persona", TECH),                          # 剩下的：persona_card_builder、reaction_classifier
    ("llm.storage", TECH),
    ("llm.logger_factory", TECH),
    ("llm", TECH),
    # ── services/ 裡的 Discord 功能 ──
    ("services.relay", FEATURE), ("services.events", FEATURE), ("services.community", FEATURE),
    ("services.notify_server", FEATURE),            # 轉發功能的接收端點：收爬蟲通知再派給 relay
    # ── services/ 裡的服務 ──
    ("services.llm_service", SERVICE),              # 叫模型的門面
    ("services.llm_proxy", SERVICE),                # Hermes 的模型端點：驗金鑰、擋模型名、排閘門、原樣轉給 Lemonade
    ("services.memory_service", SERVICE),
    ("services.state_db", SERVICE),
    ("services.source_urls", SERVICE),
    ("services.search", SERVICE),
    ("services", SERVICE),
    # ── 介面與基礎 ──
    ("commands", INTERFACE), ("discord_bot", INTERFACE), ("music", INTERFACE),
    ("constants", BASE), ("sys_settings", BASE), ("utils", BASE), ("settings", BASE),
    ("shared", BASE),                               # 和爬蟲容器共用的定義；只能依賴標準庫
]

#: 跨容器的 import：bot 直接用另一個容器的程式。每條都要寫理由與去向；目前沒有：
#: 轉發端與爬蟲共用的頻道正規化與媒體時限在 `shared/telegram.py`，compose 把它唯讀掛進爬蟲容器，兩邊 import 同一份。
CROSS_CONTAINER_ALLOWED: set[tuple[str, str]] = set()
OTHER_CONTAINERS = ("scraper", "telegram_scraper")
#: 不在 bot 行程裡執行、或不是 bot 程式的資料夾
SKIP_DIRS = {"test", "scripts", "scraper", "telegram_scraper", "__pycache__"}

#: 這幾層不可 import discord。功能層與介面層是 Discord 應用本身，不限制。
DISCORD_FREE_LAYERS = {TECH, SERVICE}
#: 基礎層裡刻意認得 Discord 的共用元件：給介面層與功能層用的 Discord 工具，照名字就看得出是在講 Discord。
#: 新增一個要寫理由；不再 import discord 的要從這裡拿掉（下面有測試擋殭屍）。
DISCORD_HELPERS_IN_BASE = {
    "utils.utils": "check_guild／check_role 的權限檢查、ChannelConfig 的頻道 getter，講的就是 Discord 的身分組與頻道",
    "utils.discord_content": "發文到頻道、把長文切成 Discord 放得下的多段",
    "utils.discord_threads": "取得（含封存的）與解封 thread",
    "utils.discord_members": "取伺服器成員（快取沒有再問 API）、找能私訊的對象",
    "utils.dm_notifier": "私訊群友",
    "utils.panel_bump": "面板置底",
    "settings.channel_registry": "綁頻道時向 Discord 查頻道、建 thread",
}


def layer_of(module: str):
    for prefix, level in LAYERS:
        if module == prefix or module.startswith(prefix + "."):
            return level
    return None


def imports_in(tree: ast.Module):
    """(行號, 匯入的模組) ——略過 `if TYPE_CHECKING:` 區塊；相對 import 不會跨層，也略過。"""
    skip = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and "TYPE_CHECKING" in ast.unparse(node.test):
            skip.update(id(sub) for sub in ast.walk(node))
    for node in ast.walk(tree):
        if id(node) in skip:
            continue
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            yield node.lineno, node.module


def project_modules():
    """(模組名, 檔案路徑)：bot 行程會載入的程式。"""
    for path in sorted(Path(SRC_DIR).rglob("*.py")):
        rel = path.relative_to(SRC_DIR)
        if set(rel.parts) & SKIP_DIRS:
            continue
        module = ".".join(rel.with_suffix("").parts)
        if module.endswith(".__init__"):
            module = module[: -len(".__init__")]
        yield module, path


def violations():
    unclassified, upward, cross, discord_hits = [], [], [], []
    for module, path in project_modules():
        level = layer_of(module)
        if level is None:
            unclassified.append(module)
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for lineno, target in imports_in(tree):
            where = f"{path.relative_to(SRC_DIR)}:{lineno}"
            if target.split(".")[0] in OTHER_CONTAINERS:
                if (module, target) not in CROSS_CONTAINER_ALLOWED:
                    cross.append(f"{where}: {module} → {target}")
                continue
            if target.split(".")[0] == "discord":
                if level in DISCORD_FREE_LAYERS or (level == BASE and module not in DISCORD_HELPERS_IN_BASE):
                    discord_hits.append(f"{where}: {NAMES[level]}層的 {module} → {target}")
                continue
            target_level = layer_of(target)
            if target_level is not None and target_level > level:
                upward.append(f"{where}: {NAMES[level]}層的 {module} → {NAMES[target_level]}層的 {target}")
    return unclassified, upward, cross, discord_hits


def discord_importers():
    """有（執行時）import discord 的模組名，給例外清單的殭屍檢查用。"""
    found = set()
    for module, path in project_modules():
        for _, target in imports_in(ast.parse(path.read_text(encoding="utf-8"))):
            if target.split(".")[0] == "discord":
                found.add(module)
    return found


class LayeringTests(unittest.TestCase):
    def test_every_module_has_a_layer(self):
        unclassified, _, _, _ = violations()
        self.assertEqual(unclassified, [], "新模組要先在 LAYERS 登記屬於哪一層（並寫理由）：\n  " + "\n  ".join(unclassified))

    def test_imports_only_point_down_or_sideways(self):
        _, upward, _, _ = violations()
        self.assertEqual(upward, [], "往上 import：下層不該認得上層。改成由上層把東西交進來（介面、callback），"
                                     "或把放錯層的模組搬到對的層，或改 LAYERS 的分類並寫理由：\n  " + "\n  ".join(upward))

    def test_no_new_cross_container_imports(self):
        _, _, cross, _ = violations()
        self.assertEqual(cross, [], "bot 直接 import 另一個容器的程式。共用的東西抽進 utils/，或暫列 CROSS_CONTAINER_ALLOWED 並寫理由：\n  "
                                    + "\n  ".join(cross))

    def test_technology_and_service_layers_do_not_import_discord(self):
        _, _, _, hits = violations()
        self.assertEqual(hits, [], "技術層、服務層（與基礎層的非 Discord 工具）不認 discord：型別註解放進 `if TYPE_CHECKING:`，"
                                   "要 Discord 物件就由功能層或介面層傳進來，向 Discord 要資料的那段搬去呼叫端：\n  " + "\n  ".join(hits))

    def test_allowlist_only_holds_real_edges(self):
        """例外清單裡的邊要真的存在；清掉違規後要把它從清單拿掉，不留殭屍。"""
        present = set()
        for module, path in project_modules():
            for _, target in imports_in(ast.parse(path.read_text(encoding="utf-8"))):
                present.add((module, target))
        stale = sorted(edge for edge in CROSS_CONTAINER_ALLOWED if edge not in present)
        self.assertEqual(stale, [], f"例外清單裡已經不存在的邊，請拿掉：{stale}")
        importers = discord_importers()
        stale_helpers = sorted(name for name in DISCORD_HELPERS_IN_BASE if name not in importers)
        self.assertEqual(stale_helpers, [], f"這些基礎層模組已經不 import discord，請從 DISCORD_HELPERS_IN_BASE 拿掉：{stale_helpers}")


class LayerTableTests(unittest.TestCase):
    """守衛本身：分類表的解讀方式。"""

    def test_more_specific_prefix_wins(self):
        self.assertEqual(layer_of("llm.persona.agent.batch"), FEATURE)
        self.assertEqual(layer_of("llm.persona.persona_card_builder"), TECH)
        self.assertEqual(layer_of("llm.storage.member_profile_store"), SERVICE)
        self.assertEqual(layer_of("services.relay.bahamut_monitor"), FEATURE)
        self.assertEqual(layer_of("services.llm_service"), SERVICE)
        self.assertIsNone(layer_of("somewhere.else"))

    def test_type_checking_imports_are_ignored(self):
        # 範例用真的模組名：import 解析守衛會檢查字串裡長得像模組路徑的東西
        tree = ast.parse("from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import commands.llm_commands\nimport utils.hot_files\n")
        self.assertEqual([t for _, t in imports_in(tree)], ["typing", "utils.hot_files"])


if __name__ == "__main__":
    unittest.main()
