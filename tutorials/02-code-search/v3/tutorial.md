# 代码与精确检索 v3：符号与引用

v2 能区分 `connect` 的多个定义，但调用者可能使用 `open_database()`，也可能使用 `obj.connect()`。本版新增 `labs/code_search/symbols.py`，为固定 Python 源树建立静态符号索引，将“已经确认的引用”和“仅是候选或未知的引用”分别返回。

本版直接接入 Jedi 0.19 的静态解析能力。Jedi 会处理词法作用域、导入别名及一部分类型推断，避免自行用短名猜测引用。它读取源码，不执行样例 Python 文件；静态分析仍不能证明任意运行时行为。

## 1. 建立索引

`SymbolIndex.build(workspace)` 按排序后的 `.py` 文件遍历语法树记录定义，然后将 `Name` 和 `Attribute` 读取节点的位置交给 `jedi.Script.goto(..., follow_imports=True)`。`Symbol` 保存路径、模块、短名、限定名、类型及行范围。`Reference` 保存引用位置、文本表达式、解析状态、确认目标及候选列表。先运行 `uv sync --locked` 安装锁定的 Jedi 与 Parso 依赖。

三个解析状态有不同含义：

| 状态 | 本实验的解释 |
| --- | --- |
| `confirmed` | Jedi 的该位置解析结果映射到一个工作目录内的定义 |
| `candidate` | 同名定义存在多个，当前规则不能选择 |
| `unresolved` | 没有静态目标，例如未知对象的方法访问 |

语法错误保存在 `index.syntax_errors`，以便调用者知道索引覆盖范围不完整。调用者应先检查错误，不能把部分成功索引当作全仓库结论。

## 2. 观察别名导入

```bash
uv run python - <<'PY'
from pathlib import Path
from labs.code_search import SymbolIndex

index = SymbolIndex.build(Path('fixtures/code_search/repository'))
for symbol in index.find_symbols('connect'):
    print('definition', symbol.qualified_name, symbol.path, symbol.line)
for reference in index.references('connect', path='app.py'):
    target = reference.target.qualified_name if reference.target else None
    print(reference.line, reference.expression, reference.resolution, target)
print('syntax errors:', index.syntax_errors)
PY
```

在 `app.py` 中，`open_database` 通过 `from database import connect as open_database` 解析到 `database.connect`，状态为 `confirmed`。`obj.connect` 没有对象类型信息，因此保持 `unresolved`。这比把所有 `connect` 文本位置都称作调用者更可靠，也不会把未知对象误指向 `database.Client.connect`。

将本版新增文件完整写为 `labs/code_search/symbols.py`，代码如下。此前版本的文件保持不变。

```python
"""Python symbol lookup using Jedi's source-only static analysis."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import jedi

from .reader import WorkspaceError


@dataclass(frozen=True)
class Symbol:
    path: str
    module: str
    name: str
    qualified_name: str
    kind: Literal["function", "async_function", "class"]
    line: int
    end_line: int


@dataclass(frozen=True)
class Reference:
    path: str
    line: int
    column: int
    expression: str
    resolution: Literal["confirmed", "candidate", "unresolved"]
    target: Symbol | None = None
    candidates: tuple[Symbol, ...] = ()


def _module_name(root: Path, path: Path) -> str:
    parts = list(path.relative_to(root).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts) or root.name


def _collect_symbols(
    node: ast.AST,
    path: str,
    module: str,
    scope: tuple[str, ...] = (),
) -> list[Symbol]:
    symbols: list[Symbol] = []
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            kind: Literal["function", "async_function", "class"]
            kind = "class" if isinstance(child, ast.ClassDef) else "function"
            if isinstance(child, ast.AsyncFunctionDef):
                kind = "async_function"
            symbols.append(Symbol(path, module, child.name,
                                  ".".join((module, *scope, child.name)), kind,
                                  child.lineno, child.end_lineno or child.lineno))
            symbols.extend(_collect_symbols(child, path, module, (*scope, child.name)))
        else:
            symbols.extend(_collect_symbols(child, path, module, scope))
    return symbols


def _reference_position(node: ast.AST) -> tuple[int, int, str] | None:
    if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
        return node.lineno, node.col_offset, node.id
    if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
        return (node.end_lineno or node.lineno,
                (node.end_col_offset or 0) - len(node.attr.encode("utf-8")),
                ast.unparse(node))
    return None


class SymbolIndex:
    """Index definitions with AST and delegate reference targets to Jedi."""

    def __init__(
        self,
        root: Path,
        symbols: tuple[Symbol, ...],
        references: tuple[Reference, ...],
        syntax_errors: tuple[tuple[str, str], ...],
    ) -> None:
        self.root = root
        self.symbols = symbols
        self._references = references
        self.syntax_errors = syntax_errors

    @classmethod
    def build(cls, workspace: Path) -> "SymbolIndex":
        root = workspace.resolve(strict=True)
        if not root.is_dir():
            raise WorkspaceError("workspace must be a directory")
        parsed: list[tuple[Path, str, ast.AST]] = []
        errors: list[tuple[str, str]] = []
        symbols: list[Symbol] = []
        for path in sorted(path for path in root.glob("**/*.py") if path.is_file()):
            if not path.resolve(strict=True).is_relative_to(root):
                continue
            relative = path.relative_to(root).as_posix()
            try:
                source = path.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=relative)
            except (SyntaxError, UnicodeDecodeError) as exc:
                message = exc.msg if isinstance(exc, SyntaxError) else "file is not valid UTF-8"
                errors.append((relative, message))
                continue
            module = _module_name(root, path)
            symbols.extend(_collect_symbols(tree, relative, module))
            parsed.append((path, source, tree))

        by_location = {(str((root / symbol.path).resolve()), symbol.line, symbol.name): symbol
                       for symbol in symbols}
        references: list[Reference] = []
        project = jedi.Project(path=str(root), added_sys_path=[str(root)], smart_sys_path=False)
        for path, source, tree in parsed:
            script = jedi.Script(code=source, path=str(path), project=project)
            for node in ast.walk(tree):
                position = _reference_position(node)
                if position is None:
                    continue
                line, column, expression = position
                # AST columns count UTF-8 bytes; Jedi columns count characters.
                raw_line = source.splitlines()[line - 1]
                column = len(raw_line.encode("utf-8")[:column].decode("utf-8"))
                targets: list[Symbol] = []
                for name in script.goto(line, column, follow_imports=True):
                    target = by_location.get((str(name.module_path), name.line, name.name))
                    if target is not None and target not in targets:
                        targets.append(target)
                targets.sort(key=lambda target: (target.path, target.line))
                status: Literal["confirmed", "candidate", "unresolved"]
                status = "confirmed" if len(targets) == 1 else "candidate" if targets else "unresolved"
                references.append(Reference(
                    path.relative_to(root).as_posix(), line, column, expression, status,
                    targets[0] if len(targets) == 1 else None,
                    tuple(targets) if len(targets) > 1 else (),
                ))
        return cls(root, tuple(symbols), tuple(references), tuple(errors))

    def find_symbols(self, name: str, *, path: str | None = None) -> tuple[Symbol, ...]:
        """Find definitions by short or module-qualified name."""

        return tuple(symbol for symbol in self.symbols
                     if (symbol.name == name or symbol.qualified_name == name)
                     and (path is None or symbol.path == path))

    def references(self, name: str, *, path: str | None = None) -> tuple[Reference, ...]:
        """Return confirmed targets, ambiguous targets and unresolved mentions."""

        symbols = self.find_symbols(name)
        qualified = {symbol.qualified_name for symbol in symbols}
        short = {symbol.name for symbol in symbols} or {name.rsplit(".", 1)[-1]}
        return tuple(
            reference for reference in self._references
            if (path is None or reference.path == path) and (
                (reference.target and reference.target.qualified_name in qualified)
                or any(candidate.qualified_name in qualified for candidate in reference.candidates)
                or (reference.resolution == "unresolved" and (
                    reference.expression in short
                    or any(reference.expression.endswith(f".{item}") for item in short)
                ))
            )
        )
```

## 3. 理解确认范围

`_collect_symbols()` 记录定义及词法嵌套；`_reference_position()` 取名称或属性的定位位置。AST 列号按 UTF-8 字节计数，而 Jedi 按字符计数，所以调用 Jedi 前进行一次边界转换；含中文标识符时两者不能直接混用。Jedi 返回的模块路径、行号和名称共同匹配本索引的定义，库外定义保留为未解析。`references()` 根据确认目标、候选目标和无法解析的同名属性返回相关引用。

这里“确认”只在 Jedi 的静态假设下成立。本版仅把函数与类纳入目标索引，没有索引变量赋值、外部依赖、生成代码和跨语言引用。描述符、猴子补丁、`getattr(obj, name)` 与 `globals()[name]` 这类动态表达式仍可能无法关联到所查询的符号。空结果不证明没有运行时引用。

索引建立时不会自动执行所有项目环境的安装配置；本版将固定根目录加入 Jedi 项目搜索路径。真实项目需要使用对应解释器和包配置，并保留同样的结果分级。不要用“语言服务返回了结果”推导“静态分析是完整的”。

## 4. 跑一条完整检索链

本专题的四个工具分别承担不同职责：

```python
from pathlib import Path
from labs.code_search import SymbolIndex, grep_literal, read_range

root = Path('fixtures/code_search/repository')
hits = grep_literal(root, '[E104]', glob='**/*.py')
evidence = read_range(root, hits.matches[0].path,
                      start_line=hits.matches[0].line,
                      end_line=hits.matches[0].line)
index = SymbolIndex.build(root)
references = index.references('database.connect')
```

字面量检索定位错误码，范围读取保留可核验原文，AST 定位定义，索引解释导入与引用。它们无需先向量化代码；后续 Agent 通过明确工具选择组合使用它们。

## 最终检查点

本专题全部实现文件是 `reader.py`、`grep_search.py`、`ast_search.py`、`symbols.py` 与包导出 `__init__.py`。固定资料在 `fixtures/code_search/repository/`，测试在 `tests/code_search/test_code_search.py`。

```bash
uv run python -m unittest discover -s tests/code_search -v
```

Python 3.12 环境下 10 项测试通过，覆盖安全读取、字面量检索、超时、定义范围、语法错误、导入别名和动态属性的不确定性。这是可信本地、小型 Python 项目的教学检查点；没有验证恶意并发文件系统、百万文件规模、完整 Python 语义或任意语言。后续 07 将把这些能力作为 Agent 的可调用工具，08 再将读取与检索纳入可信身份授权边界。
完整可重放源码保存在 `labs/code_search/checkpoints/v3/`。将本篇示例的导入改为 `from labs.code_search.checkpoints.v3 import ...`，即可直接运行该版；目录中的每个文件都是完整源码，按 reader、grep_search、ast_search、symbols 的顺序只取本版已有文件即可重建。
