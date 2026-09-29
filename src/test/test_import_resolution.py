"""所有指向本專案模組的 import 與模組字串，都必須找得到對象。

守的底線：
  1. 每一行 import 都指向存在的模組——包括寫在函式裡、要等執行到那段才載入的延遲 import。
     搬檔或改名時漏改一處，要在啟動 gate 就擋下，而不是等到 04:00 維護或某個指令被按下才
     ImportError（啟動時只會載入頂層 import，函式內的不會）。
  2. `from 模組 import 名稱` 的名稱必須真的存在：是子模組，或在該模組頂層有定義／匯入
     （只寫在 `if TYPE_CHECKING:` 裡的不算，執行時並不存在）。
  3. 以字串指定模組的地方（`mock.patch` 目標、`__import__`、`COMMAND_MODULES` 這類清單）
     也必須指向存在的模組與屬性；字串不會被一般 import 檢查到，搬檔時最容易漏。
  4. 透過模組別名讀屬性（`import llm` 後的 `llm.某名稱`、`llm.retrievers.web.某名稱`）也要存在：
     它不是 import，漏掉轉出也不會在 import 當下報錯。

這個測試跑在啟動 gate 裡，誤判會讓 bot 起不來，所以規則寧可少抓、不可誤判：
  - 只看 src/ 底下的專案模組，第三方套件不管。scraper/、telegram_scraper/ 在自己的 container
    以自己的資料夾為根執行，裡面的檔案不掃描（但 bot 端 import 它們時，目標仍要存在）。
  - 屬性檢查只看模組頂層 import 的別名，而且在同名變數被重新賦值的範圍內不檢查。
  - 字串只檢查整串是「a.b.c」形狀、開頭是專案套件、結尾不是副檔名的。
  - 全程只讀原始碼（AST），不實際 import，不會觸發任何模組的副作用。
  - 真的長得像模組路徑、卻不是模組的字串，加進 `_NOT_MODULE_STRINGS` 並寫理由。
"""

import ast
import os
import re
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC_DIR = HERE.parent

# 這兩個資料夾在自己的 container 以自己為根執行，import 寫法不同；只當 import 目標，不掃描
_NOT_SCANNED_DIRS = {"scraper", "telegram_scraper"}
_SKIP_DIR_NAMES = {"__pycache__"}

# 整串都是「a.b.c」形狀的字串，才當成模組路徑檢查（句子不會整串符合）
_DOTTED_RE = re.compile(r"^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+$")
# 「discord_bot.py」「test.gif」這類檔名也長成 a.b，以副檔名排除
_FILE_SUFFIXES = {
    "py", "pyc", "json", "jsonl", "txt", "log", "md", "rst", "csv", "tsv", "yaml", "yml", "toml",
    "ini", "cfg", "env", "sql", "db", "sqlite", "sqlite3", "bak", "tmp", "lock", "html", "htm",
    "css", "js", "xml", "svg", "png", "jpg", "jpeg", "gif", "webp", "bmp", "ico", "tif", "tiff",
    "mp3", "mp4", "m4a", "wav", "ogg", "opus", "flac", "webm", "mkv", "mov", "avi",
    "zip", "gz", "tar", "tgz", "pdf", "ttf", "otf", "woff", "woff2",
}
# 長得像模組路徑、但本來就不是模組的字串：{(檔案, 字串依「.」切開的各段): 理由}
# （分段寫，這份清單本身才不會被當成模組字串檢查）
_NOT_MODULE_STRINGS = {
    ("test/test_logger_config.py", ("services", "some_module")): "刻意虛構的 logger 名稱，驗證模組 logger 會傳到 root",
}


def _is_type_checking(test: ast.expr) -> bool:
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    )


class _Resolver:
    """以檔案系統解析模組路徑、以 AST 收集模組頂層名稱（有快取）。"""

    def __init__(self, root: Path = SRC_DIR):
        self.root = root
        self.top_names: set[str] = set()
        for entry in root.iterdir():
            if entry.name.startswith(".") or entry.name in _SKIP_DIR_NAMES:
                continue
            if entry.is_dir() or entry.suffix == ".py":
                self.top_names.add(entry.name if entry.is_dir() else entry.stem)
        self._defined_cache: dict[Path, tuple[set[str], bool]] = {}

    def is_project(self, dotted: str) -> bool:
        return dotted.split(".", 1)[0] in self.top_names

    @staticmethod
    def _is_namespace_dir(path: Path) -> bool:
        """沒有 __init__.py 的資料夾要真的有程式才算套件；只剩 __pycache__ 的是搬檔留下的空殼。"""
        for child in path.iterdir():
            if child.name.startswith(".") or child.name in _SKIP_DIR_NAMES:
                continue
            if child.suffix == ".py" and child.is_file():
                return True
            if child.is_dir() and (child / "__init__.py").is_file():
                return True
        return False

    def module_file(self, dotted: str) -> Path | None:
        """模組對應的檔案；套件回傳 __init__.py，沒有 __init__ 的資料夾回傳資料夾本身。"""
        base = self.root.joinpath(*dotted.split("."))
        as_file = base.parent / f"{base.name}.py"
        if as_file.is_file():
            return as_file
        if base.is_dir():
            init = base / "__init__.py"
            if init.is_file():
                return init
            return base if self._is_namespace_dir(base) else None
        return None

    def _defined(self, path: Path) -> tuple[set[str], bool]:
        """(模組頂層名稱, 是否接受任何名稱)。"""
        if path in self._defined_cache:
            return self._defined_cache[path]
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        names: set[str] = set()
        accept_any = False

        def add_target(target: ast.AST) -> None:
            if isinstance(target, ast.Name):
                names.add(target.id)
            elif isinstance(target, (ast.Tuple, ast.List)):
                for elt in target.elts:
                    add_target(elt)
            elif isinstance(target, ast.Starred):
                add_target(target.value)

        def visit(stmts: list[ast.stmt]) -> None:
            nonlocal accept_any
            for node in stmts:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    names.add(node.name)
                    if node.name == "__getattr__":
                        accept_any = True  # PEP 562：模組可以動態提供任何名稱
                elif isinstance(node, ast.Assign):
                    for t in node.targets:
                        add_target(t)
                elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
                    add_target(node.target)
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        names.add(alias.asname or alias.name.split(".", 1)[0])
                elif isinstance(node, ast.ImportFrom):
                    for alias in node.names:
                        if alias.name == "*":
                            accept_any = True
                        else:
                            names.add(alias.asname or alias.name)
                elif isinstance(node, ast.If):
                    if not _is_type_checking(node.test):
                        visit(node.body)  # TYPE_CHECKING 區塊執行時不存在
                    visit(node.orelse)
                elif isinstance(node, ast.Try) or type(node).__name__ == "TryStar":
                    visit(node.body)
                    for handler in node.handlers:
                        visit(handler.body)
                    visit(node.orelse)
                    visit(node.finalbody)
                elif isinstance(node, (ast.With, ast.AsyncWith)):
                    for item in node.items:
                        if item.optional_vars is not None:
                            add_target(item.optional_vars)
                    visit(node.body)
                elif isinstance(node, (ast.For, ast.AsyncFor)):
                    add_target(node.target)
                    visit(node.body)
                    visit(node.orelse)
                elif isinstance(node, ast.While):
                    visit(node.body)
                    visit(node.orelse)

        visit(tree.body)
        # 函式裡用 global 宣告後才賦值的，也是模組頂層名稱
        for node in ast.walk(tree):
            if isinstance(node, ast.Global):
                names.update(node.names)
        result = (names, accept_any)
        self._defined_cache[path] = result
        return result

    def check_name(self, module: str, name: str) -> str | None:
        """`module` 底下的 `name`（子模組或頂層名稱）解析不到時回傳原因；module 本身須存在。"""
        if self.module_file(f"{module}.{name}") is not None:
            return None
        path = self.module_file(module)
        if path is None:
            return f"找不到模組 {module}"
        if path.is_dir():
            return f"{module} 是沒有 __init__.py 的資料夾，裡面沒有 {name}"
        names, accept_any = self._defined(path)
        if accept_any or name in names:
            return None
        return f"{module} 沒有定義 {name}"

    def check_dotted_string(self, dotted: str) -> str | None:
        """字串形式的「模組.屬性」解析不到時回傳原因（只檢查到模組下的第一層名稱）。"""
        parts = dotted.split(".")
        for cut in range(len(parts), 0, -1):
            module = ".".join(parts[:cut])
            if self.module_file(module) is None:
                continue
            rest = parts[cut:]
            return None if not rest else self.check_name(module, rest[0])
        return f"找不到模組 {parts[0]}"


def _source_files(root: Path = SRC_DIR):
    """要掃描的 .py 檔（剪掉不掃描的資料夾，不走進 telegram_scraper 的大量媒體檔）。"""
    for dirpath, dirnames, filenames in os.walk(root):
        if Path(dirpath) == root:
            dirnames[:] = [d for d in dirnames if d not in _NOT_SCANNED_DIRS]
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIR_NAMES and not d.startswith(".")]
        for name in filenames:
            if name.endswith(".py"):
                yield Path(dirpath) / name


def _docstring_ids(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                ids.add(id(body[0].value))
    return ids


def _bound_names(scope: ast.AST) -> set[str]:
    """一個函式／類別範圍裡被綁定的名稱（參數、賦值、for／with／except、import），不含內層函式。"""
    bound: set[str] = set()
    if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        args = scope.args
        for a in [*args.posonlyargs, *args.args, *args.kwonlyargs, args.vararg, args.kwarg]:
            if a is not None:
                bound.add(a.arg)
    body = scope.body if isinstance(scope.body, list) else [scope.body]
    stack: list[ast.AST] = list(body)
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
            continue  # 內層範圍自己處理
        if isinstance(node, ast.Lambda):
            continue
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            bound.add(node.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                bound.add(alias.asname or alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ExceptHandler) and node.name:
            bound.add(node.name)
        stack.extend(ast.iter_child_nodes(node))
    for node in ast.walk(scope):
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            bound.difference_update(node.names)
    return bound


def check_file(path: Path, resolver: _Resolver) -> list[str]:
    """回傳這個檔案裡所有解析不到的 import／模組字串／屬性（`相對路徑:行號: 說明`）。"""
    root = resolver.root
    rel = path.relative_to(root)
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    problems: list[str] = []
    docstrings = _docstring_ids(tree)
    package = list(rel.parent.parts)

    def resolve_from(node: ast.ImportFrom) -> str:
        if not node.level:
            return node.module or ""
        base = package[: len(package) - (node.level - 1)] if node.level > 1 else package
        return ".".join(base + ([node.module] if node.module else []))

    # ---- 1～3：import 陳述與模組字串 ----
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if resolver.is_project(alias.name) and resolver.module_file(alias.name) is None:
                    problems.append(f"{rel}:{node.lineno}: import {alias.name} → 找不到模組")
        elif isinstance(node, ast.ImportFrom):
            module = resolve_from(node)
            if not module or not resolver.is_project(module):
                continue
            if resolver.module_file(module) is None:
                problems.append(f"{rel}:{node.lineno}: from {module} import … → 找不到模組 {module}")
                continue
            for alias in node.names:
                if alias.name == "*":
                    continue
                reason = resolver.check_name(module, alias.name)
                if reason:
                    problems.append(f"{rel}:{node.lineno}: from {module} import {alias.name} → {reason}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            text = node.value
            if id(node) in docstrings or not _DOTTED_RE.match(text) or not resolver.is_project(text):
                continue
            if text.rsplit(".", 1)[1].lower() in _FILE_SUFFIXES:
                continue
            if (rel.as_posix(), tuple(text.split("."))) in _NOT_MODULE_STRINGS:
                continue
            reason = resolver.check_dotted_string(text)
            if reason:
                problems.append(f"{rel}:{node.lineno}: 字串 \"{text}\" → {reason}")

    # ---- 4：模組別名的屬性讀取 ----
    # 只收模組頂層 import 的別名；頂層又被賦值成別的東西的名稱不算（分不清是哪個）
    aliases: dict[str, str] = {}

    def collect_top(stmts: list[ast.stmt]) -> None:
        for node in stmts:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if resolver.is_project(alias.name) and resolver.module_file(alias.name):
                        if alias.asname:
                            aliases[alias.asname] = alias.name
                        else:
                            top = alias.name.split(".", 1)[0]
                            aliases[top] = top  # `import a.b` 綁定的名稱是 a
            elif isinstance(node, ast.ImportFrom):
                module = resolve_from(node)
                if module and resolver.is_project(module):
                    for alias in node.names:
                        if alias.name != "*" and resolver.module_file(f"{module}.{alias.name}"):
                            aliases[alias.asname or alias.name] = f"{module}.{alias.name}"
            elif isinstance(node, ast.If):
                if not _is_type_checking(node.test):
                    collect_top(node.body)
                collect_top(node.orelse)
            elif isinstance(node, ast.Try) or type(node).__name__ == "TryStar":
                collect_top(node.body)
                for handler in node.handlers:
                    collect_top(handler.body)
                collect_top(node.orelse)
                collect_top(node.finalbody)

    collect_top(tree.body)
    for node in tree.body:
        targets: list[ast.AST] = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            targets = [node.target]
        for t in targets:
            for sub in ast.walk(t):
                if isinstance(sub, ast.Name):
                    aliases.pop(sub.id, None)
    if not aliases:
        return problems

    def check_chain(node: ast.Attribute) -> None:
        chain: list[str] = []
        base: ast.AST = node
        while isinstance(base, ast.Attribute):
            chain.append(base.attr)
            base = base.value
        chain.reverse()
        assert isinstance(base, ast.Name)
        module = aliases[base.id]
        for attr in chain:
            if resolver.module_file(f"{module}.{attr}") is not None:
                module = f"{module}.{attr}"
                continue
            reason = resolver.check_name(module, attr)
            if reason:
                dotted = ".".join([base.id, *chain[: chain.index(attr) + 1]])
                problems.append(f"{rel}:{node.lineno}: {dotted} → {reason}")
            return  # 之後是物件屬性，不是模組，不再追

    def walk(node: ast.AST, shadowed: frozenset[str]) -> None:
        if isinstance(node, ast.AnnAssign):
            # 型別註記可能只是字串或 TYPE_CHECKING 名稱，執行時不求值；只看目標與值
            walk(node.target, shadowed)
            if node.value is not None:
                walk(node.value, shadowed)
            return
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            outer = list(getattr(node, "decorator_list", [])) + list(getattr(node, "bases", []))
            if not isinstance(node, ast.ClassDef):
                # 參數預設值在定義當下求值（屬外層範圍）；參數與回傳的型別註記不求值，不看
                outer += list(node.args.defaults) + [d for d in node.args.kw_defaults if d is not None]
            for child in outer:
                walk(child, shadowed)
            inner = shadowed | _bound_names(node) if not isinstance(node, ast.ClassDef) else shadowed
            body = node.body if isinstance(node.body, list) else [node.body]
            for child in body:
                walk(child, frozenset(inner))
            return
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            comp_bound = {
                n.id for gen in node.generators for n in ast.walk(gen.target) if isinstance(n, ast.Name)
            }
            shadowed = frozenset(shadowed | comp_bound)
        if isinstance(node, ast.Attribute):
            base = node
            while isinstance(base, ast.Attribute):
                base = base.value
            if isinstance(base, ast.Name) and base.id in aliases and base.id not in shadowed:
                if isinstance(node.ctx, ast.Load):
                    check_chain(node)
                return  # 賦值（測試替換模組屬性）本來就可以是新名稱
        for child in ast.iter_child_nodes(node):
            walk(child, shadowed)

    for stmt in tree.body:
        walk(stmt, frozenset())
    return problems


class ImportResolutionTests(unittest.TestCase):
    """整個 bot 端程式的 import 與模組字串都解析得到。"""

    def test_all_project_imports_resolve(self):
        resolver = _Resolver()
        files = sorted(_source_files())
        scanned = {p.relative_to(SRC_DIR).as_posix() for p in files}
        # 確認真的有掃到東西：檔案位置或剪枝規則改錯時，不能「什麼都沒掃」還顯示通過
        self.assertTrue({"commands", "services", "llm", "utils"} <= resolver.top_names)
        self.assertTrue(
            {"discord_bot.py", "commands/llm_commands.py", "llm/__init__.py"} <= scanned,
            "守衛沒有掃到核心檔案，檢查 SRC_DIR 與剪枝規則",
        )
        self.assertGreater(len(files), 100)
        problems: list[str] = []
        for path in files:
            problems.extend(check_file(path, resolver))
        self.assertEqual(
            problems, [],
            "以下 import 或模組字串指向不存在的模組／名稱（搬檔、改名時漏改？）。"
            "若字串本來就不是模組路徑，加進 _NOT_MODULE_STRINGS 並寫理由：\n  "
            + "\n  ".join(problems),
        )


class CheckerSelfTests(unittest.TestCase):
    """守衛本身要抓得到該抓的、也不能誤判：用暫存的假專案驗證，避免規則悄悄失效。"""

    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        pkg = self.root / "pkg"
        (pkg / "sub").mkdir(parents=True)
        (pkg / "__init__.py").write_text("from .mod import exported\n", encoding="utf-8")
        (pkg / "mod.py").write_text(
            "from typing import TYPE_CHECKING\n"
            "if TYPE_CHECKING:\n    from pkg.sub.leaf import VALUE as ONLY_FOR_TYPES\n"
            "exported = 1\n"
            "def func():\n    pass\n"
            "class Klass:\n    def method(self):\n        pass\n",
            encoding="utf-8",
        )
        (pkg / "sub" / "__init__.py").write_text("", encoding="utf-8")
        (pkg / "sub" / "leaf.py").write_text("VALUE = 1\n", encoding="utf-8")
        (self.root / "nsdir").mkdir()
        (self.root / "nsdir" / "thing.py").write_text("X = 1\n", encoding="utf-8")
        # 搬檔後只剩 __pycache__ 的舊資料夾
        (pkg / "stale" / "__pycache__").mkdir(parents=True)
        (pkg / "stale" / "__pycache__" / "old.cpython-312.pyc").write_bytes(b"")

    def tearDown(self):
        self._tmp.cleanup()

    def _problems(self, code: str) -> list[str]:
        target = self.root / "pkg" / "sub" / "probe.py"
        target.write_text(code, encoding="utf-8")
        return check_file(target, _Resolver(self.root))

    def test_valid_code_passes(self):
        self.assertEqual(self._problems(
            "import os\n"
            "import pkg\n"
            "import pkg.mod\n"
            "from pkg import mod, exported\n"
            "from pkg.mod import func, Klass\n"
            "from pkg.sub import leaf\n"
            "from nsdir import thing\n"
            "from . import leaf as l2\n"
            "from .leaf import VALUE\n"
            "from ..mod import func as f2\n"
            "def lazy():\n    from pkg.sub.leaf import VALUE\n"
            "pkg.exported\n"
            "pkg.sub.leaf.VALUE\n"
            "mod.Klass().method\n"
            "mod.patched_in_test = 1\n"
            "TARGETS = ['pkg.mod.func', 'pkg.mod.Klass', 'pkg.sub.leaf']\n"
        ), [])

    def test_lazy_import_of_missing_module_is_caught(self):
        problems = self._problems("def lazy():\n    from pkg.moved_away import func\n")
        self.assertEqual(len(problems), 1)
        self.assertIn("pkg.moved_away", problems[0])

    def test_missing_name_is_caught(self):
        self.assertEqual(len(self._problems("from pkg.mod import gone\n")), 1)
        self.assertEqual(len(self._problems("from pkg import gone\n")), 1)
        self.assertEqual(len(self._problems("from nsdir import gone\n")), 1)

    def test_type_checking_only_name_is_not_importable(self):
        # 只在 TYPE_CHECKING 區塊 import 的名稱，執行時不存在
        self.assertEqual(len(self._problems("from pkg.mod import ONLY_FOR_TYPES\n")), 1)

    def test_relative_import_of_missing_module_is_caught(self):
        self.assertEqual(len(self._problems("from .gone import x\n")), 1)
        self.assertEqual(len(self._problems("from ..gone import x\n")), 1)

    def test_plain_import_of_missing_module_is_caught(self):
        self.assertEqual(len(self._problems("import pkg.gone\n")), 1)

    def test_leftover_folder_with_only_pycache_is_not_a_module(self):
        self.assertEqual(len(self._problems("import pkg.stale\n")), 1)
        self.assertEqual(len(self._problems("from pkg.stale import old\n")), 1)

    def test_stale_module_string_is_caught(self):
        self.assertEqual(len(self._problems("PATCH = 'pkg.gone.func'\n")), 1)
        self.assertEqual(len(self._problems("PATCH = 'pkg.mod.gone'\n")), 1)

    def test_attribute_access_on_module_alias_is_checked(self):
        self.assertEqual(len(self._problems("import pkg\npkg.gone()\n")), 1)
        self.assertEqual(len(self._problems("import pkg\npkg.sub.leaf.GONE\n")), 1)
        self.assertEqual(len(self._problems("from pkg import mod as m\nm.gone\n")), 1)

    def test_rebound_names_are_not_treated_as_modules(self):
        # 函式參數、區域變數、頂層重新賦值跟模組同名時，不能拿模組去檢查
        self.assertEqual(self._problems(
            "from pkg import mod\n"
            "import pkg\n"
            "def f(mod):\n    return mod.anything\n"
            "def g():\n    mod = object()\n    return mod.anything\n"
            "def h():\n    return [pkg.anything for pkg in range(3)]\n"
        ), [])
        self.assertEqual(self._problems("from pkg import mod\nmod = None\nmod.anything\n"), [])

    def test_non_module_strings_and_docstrings_are_ignored(self):
        self.assertEqual(self._problems(
            '"""pkg.gone.func 寫在 docstring 裡不算"""\n'
            "A = 'asyncio.sleep'\n"
            "B = 'pkg.gone 不是整串的路徑'\n"
            "C = 'config.json'\n"
            "D = 'pkg.gif'\n"
            "E = 'pkg.MP4'\n"
        ), [])


if __name__ == "__main__":
    unittest.main()
