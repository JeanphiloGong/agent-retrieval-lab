# 代码与精确检索 v2：AST 定位

运行 v1 的 `grep_literal(root, 'connect')` 会命中说明、注释、调用以及三个不同位置的定义。用户若问“`connect` 函数的实现是什么”，这些结果不能直接当答案。本版新增 `labs/code_search/ast_search.py`，用 Python 标准库 `ast` 找定义及其行范围。

保留自己已验收的 v0、v1 文件，先手写下面的 `ast_search.py`，再运行第 3 节的调用。无需创建参考快照目录，`__init__.py` 也无需提前导入未来的符号。

AST 是解析后的语法树。`FunctionDef`、`AsyncFunctionDef` 与 `ClassDef` 分别表示函数、异步函数和类；注释不会成为这些节点。解析只读取文本，不执行 Python 文件，因此不会触发资料里的导入、网络访问或副作用。

## 1. 定义返回契约

`find_definitions(workspace, relative_path, name=None)` 使用 v0 的路径边界，返回 `list[Definition]` 或 `SyntaxErrorResult`。每条定义包含：相对路径、短名、节点类型、起止行、限定名。限定名记录词法嵌套，例如 `wrapper.connect` 和 `Client.connect`，但它还不是跨文件语义解析。

语法错误用独立结果携带文件、消息和错误行号。空列表表示文件成功解析但没有符合条件的定义；它与无法解析文件必须区分。

## 2. 写出定义定位

将本版新增文件完整写为 `labs/code_search/ast_search.py`，代码如下。此前版本的文件保持不变。

```python
"""Python definition lookup using the standard-library AST."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .reader import WorkspaceError, _resolve_file


@dataclass(frozen=True)
class Definition:
    path: str
    name: str
    kind: Literal["function", "async_function", "class"]
    line: int
    end_line: int
    qualified_name: str


@dataclass(frozen=True)
class SyntaxErrorResult:
    path: str
    message: str
    line: int | None


def _walk_definitions(node: ast.AST, parents: tuple[str, ...] = ()) -> list[Definition]:
    found: list[Definition] = []
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            kind: Literal["function", "async_function", "class"]
            if isinstance(child, ast.ClassDef):
                kind = "class"
            elif isinstance(child, ast.AsyncFunctionDef):
                kind = "async_function"
            else:
                kind = "function"
            qualified = ".".join((*parents, child.name))
            found.append(
                Definition(
                    path="",
                    name=child.name,
                    kind=kind,
                    line=child.lineno,
                    end_line=getattr(child, "end_lineno", child.lineno),
                    qualified_name=qualified,
                )
            )
            # A class/function body may contain nested definitions.  Include
            # them so callers can distinguish a nested definition from a call.
            found.extend(_walk_definitions(child, (*parents, child.name)))
        else:
            found.extend(_walk_definitions(child, parents))
    return found


def find_definitions(
    workspace: Path,
    relative_path: str,
    name: str | None = None,
) -> list[Definition] | SyntaxErrorResult:
    """Return Python definitions in a file, optionally filtered by name.

    Syntax failures are returned as data because a repository search should
    explain which file could not be indexed rather than pretending it had no
    definitions.
    """

    if name is not None and (not isinstance(name, str) or not name):
        raise WorkspaceError("name must be a nonempty string")
    root, target = _resolve_file(workspace, relative_path)
    try:
        source = target.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise WorkspaceError("file is not valid UTF-8") from exc
    except OSError as exc:
        raise WorkspaceError(type(exc).__name__) from exc
    try:
        tree = ast.parse(source, filename=str(target))
    except SyntaxError as exc:
        return SyntaxErrorResult(
            path=target.relative_to(root).as_posix(),
            message=exc.msg,
            line=exc.lineno,
        )
    definitions = []
    for definition in _walk_definitions(tree):
        if name is None or definition.name == name:
            definitions.append(
                Definition(
                    path=target.relative_to(root).as_posix(),
                    name=definition.name,
                    kind=definition.kind,
                    line=definition.line,
                    end_line=definition.end_line,
                    qualified_name=definition.qualified_name,
                )
            )
    return definitions
```

## 3. 跟随语法树中的作用域

写完文件后，从名字定位到原文：

```bash
uv run python - <<'PY'
from pathlib import Path
from labs.code_search.ast_search import find_definitions
from labs.code_search.reader import read_range

root = Path('fixtures/code_search/repository')
definitions = find_definitions(root, 'app.py', 'connect')
for definition in definitions:
    print(definition.qualified_name, definition.line, definition.end_line)
    print(read_range(root, definition.path,
                     start_line=definition.line,
                     end_line=definition.end_line).text, end='')
PY
```

结果包含 `wrapper.connect`，范围是 `app.py` 第 11–12 行，而不是第 3 行的注释或第 13 行的调用。查看 `database.py` 时会返回顶层 `connect` 和 `Client.connect`；调用者应保留全部候选，不能只取第一个就宣布找到了用户想要的定义。

实现的 `_walk_definitions(node, parents)` 遍历子节点。遇到定义时记录节点的 `lineno`、`end_lineno`，再把新名字加入 `parents` 继续向下。这样 `wrapper` 中的函数仍然会被发现，并得到可解释的限定名。普通 `if` 或 `for` 节点不建立 Python 函数/类命名空间，但其中的定义仍会被继续遍历。

本版返回的行范围从 `def` 或 `class` 开始，不包含上方装饰器。它用于定位实现正文；需要连装饰器一起作为证据时，应明确扩大读取范围。行范围也不能说明运行时最终绑定到了哪个对象。

## 4. 让故障可见

```bash
uv run python - <<'PY'
import tempfile
from pathlib import Path
from labs.code_search.ast_search import find_definitions

with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    (root / 'broken.py').write_text('def broken(:\n', encoding='utf-8')
    print(find_definitions(root, 'broken.py'))
PY
```

输出为 `SyntaxErrorResult`，包含 `broken.py`、语法错误消息与第 1 行。具体英文消息可能随 Python 小版本变化，测试只要求错误位置与错误类型清楚，不能把措辞当业务契约。

## 检查点

本版文件集合是 `reader.py`、`grep_search.py` 和 `ast_search.py`。`tests/code_search/test_code_search.py` 的 v2 检查嵌套定义、限定名、结束行及语法错误。

```bash
uv run python -m pytest -q tests/code_search/test_code_search.py -k 'test_v0 or test_v1 or test_v2'
```

预期为到 v2 为止的 6 项检查通过。本版识别语法定义，但 `from database import connect as open_database` 的调用仍叫 `open_database`。下一版加入符号索引来解释可静态确定的导入引用，并保留无法确定的候选。

参考快照位于 `reference/labs/code_search/checkpoints/v2/`；下面只重放参考版本，不验证个人进度：

```bash
PYTHONPATH=reference uv run python -P -c 'from pathlib import Path; from labs.code_search.checkpoints.v2 import find_definitions; print(find_definitions(Path("fixtures/code_search/repository"), "app.py", "connect"))'
```
