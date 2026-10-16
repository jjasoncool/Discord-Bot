"""錯誤邊界：技術層與服務層（`llm/`、`services/` 裡不是功能的模組）不該接所有例外。

守的底線：
  - 內層模組裡「接所有例外」的地方（`except:`、`except Exception`、`except BaseException`、含它們的 tuple）只准減不准增：
    每個檔的數量記在 BASELINE，多出來就紅；少了也紅，提醒把基準往下調，基準才不會虛胖
  - 真的是邊界（排程的一次 tick、每則訊息、每個工具呼叫、對外的一次請求）才接所有例外，而且要在那一行註明
    `# 邊界：原因`——有註明的不計入
  - 功能層與介面層（插話、轉發、指令、音樂）是 Discord 應用本身，邊界本來就在那裡，不在此規則內

為什麼：接所有例外的地方有六百多處，多數是「不讓一個失敗拖垮全部」的合理用法，但每個呼叫點自己決定吞不吞，
錯誤就在內層被吃掉、外層看不到原因。先把現況凍住、擋新的，再逐步清。

重算基準：`cd src && python -m test.test_error_boundaries --baseline`（印出來貼回 BASELINE）。
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

from test.test_layering import SERVICE, TECH, layer_of  # noqa: E402

#: 這一行有這個字就算邊界（寫成 `# 邊界：原因`）
BOUNDARY_MARK = "邊界"
BROAD_NAMES = {"Exception", "BaseException"}
SCAN_ROOTS = ("llm", "services")

#: 檔案 → 接所有例外的地方有幾個（記錄當下的現況；只准減不准增）
BASELINE: dict[str, int] = {
    "llm/client/embedding_client.py": 6,
    "llm/client/http_client.py": 4,
    "llm/persona/member_names.py": 1,
    "llm/persona/preference_extractor.py": 2,
    "llm/persona/signature_tag_extractor.py": 3,
    "llm/preprocess/chat_line.py": 1,
    "llm/preprocess/external_emoji.py": 1,
    "llm/preprocess/tweet_context.py": 1,
    "llm/preprocess/vision_image.py": 4,
    "llm/retrievers/context_retriever.py": 11,
    "llm/retrievers/intel/client.py": 2,
    "llm/retrievers/web/searxng.py": 2,
    "llm/retrievers/web/tools.py": 1,
    "llm/storage/ai_interactions_store.py": 14,
    "llm/storage/member_profile_store.py": 15,
    "services/llm_service.py": 4,
    "services/memory_service.py": 1,
    "services/search/background.py": 1,
    "services/search/eval/evaluate.py": 1,
    "services/search/index.py": 3,
    "services/state_db.py": 2,
}


def _is_broad(handler: ast.ExceptHandler) -> bool:
    node = handler.type
    if node is None:
        return True
    names = node.elts if isinstance(node, ast.Tuple) else [node]
    for name in names:
        if isinstance(name, ast.Name) and name.id in BROAD_NAMES:
            return True
        if isinstance(name, ast.Attribute) and name.attr in BROAD_NAMES:
            return True
    return False


def broad_except_lines(path: Path) -> list[int]:
    """檔案裡接所有例外、又沒標成邊界的 except 行號。"""
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()
    hits = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ExceptHandler) and _is_broad(node):
            line = lines[node.lineno - 1]
            if "#" in line and BOUNDARY_MARK in line.split("#", 1)[1]:
                continue
            hits.append(node.lineno)
    return hits


def inner_layer_files():
    """`llm/`、`services/` 底下屬於技術層或服務層的模組（功能層不算）。"""
    for root in SCAN_ROOTS:
        for path in sorted((Path(SRC_DIR) / root).rglob("*.py")):
            rel = str(path.relative_to(SRC_DIR))
            if "__pycache__" in rel:
                continue
            module = rel[:-3].replace("/", ".")
            if module.endswith(".__init__"):
                module = module[: -len(".__init__")]
            if layer_of(module) in (TECH, SERVICE):
                yield rel, path


def current_counts() -> dict[str, int]:
    return {rel: len(broad_except_lines(path)) for rel, path in inner_layer_files()}


class ErrorBoundaryTests(unittest.TestCase):
    def test_inner_layers_do_not_grow_broad_excepts(self):
        counts = current_counts()
        problems = []
        for rel, count in counts.items():
            baseline = BASELINE.get(rel, 0)
            if count > baseline:
                lines = broad_except_lines(Path(SRC_DIR) / rel)
                problems.append(
                    f"{rel}：接所有例外的地方 {count} 個，基準 {baseline}（行 {lines}）。"
                    f"內層讓例外往外走、交給邊界處理；真的是邊界就在那一行註明 `# {BOUNDARY_MARK}：原因`"
                )
            elif count < baseline:
                problems.append(f"{rel}：剩 {count} 個（基準 {baseline}），請把 BASELINE 降到 {count}，基準只准往下調")
        for rel in BASELINE:
            if rel not in counts:
                problems.append(f"{rel}：基準裡有、掃不到這個檔（搬走或改名了），請更新 BASELINE")
        self.assertFalse(problems, "\n" + "\n".join(problems))

    def test_marked_boundary_is_not_counted(self):
        path = Path(HERE) / "_boundary_sample.py"
        path.write_text(
            "def f():\n"
            "    try:\n        pass\n"
            f"    except Exception:  # {BOUNDARY_MARK}：每則訊息一個邊界\n        pass\n"
            "    try:\n        pass\n"
            "    except (ValueError, Exception):\n        pass\n"
            "    try:\n        pass\n"
            "    except:\n        pass\n"
            "    try:\n        pass\n"
            "    except ValueError:\n        pass\n",
            encoding="utf-8",
        )
        try:
            self.assertEqual([8, 12], broad_except_lines(path))
        finally:
            path.unlink()


if __name__ == "__main__":
    if "--baseline" in sys.argv:
        for rel, count in current_counts().items():
            if count:
                print(f'    "{rel}": {count},')
    else:
        unittest.main()
