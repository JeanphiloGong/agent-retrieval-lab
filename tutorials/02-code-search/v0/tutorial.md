# 代码与精确检索 v0：受限文件读取

本版从 01 的来源与行号契约出发，给代码工具增加第一个可运行能力：读取工作目录内的 UTF-8 文件及包含两端的行范围。实现位于 `labs/code_search/reader.py`，固定资料在 `fixtures/code_search/repository/`。不调用模型，也不执行被读取的源代码。

场景是助手已知道 `database.py` 包含 E104 的定义，准备读原文。直接使用 `Path(path).read_text()` 会让调用者读到 `../` 指向的文件；只检查字符串不含 `..` 又挡不住指向目录外的符号链接。因此这里的规则是：工作目录由宿主确定，外部输入只允许相对路径，解析后的真实文件仍必须在真实工作目录内。

## 1. 定义读取结果和路径边界

`FileRead` 是不可变结果，包含相对路径、起止行号和原始文本。`WorkspaceError` 表示输入不满足读取契约。查看实现的第一部分：

```bash
sed -n '1,55p' labs/code_search/reader.py
```

`_resolve_file(workspace, relative_path)` 的输入是可信工作目录和不可信相对路径，输出是已解析的根目录与文件路径，不读取文件。它按以下顺序检查：路径为非空字符串；拒绝绝对路径与 `..`；使用 `resolve(strict=True)` 跟随符号链接并要求目标存在；最后验证 `target.is_relative_to(root)` 和 `target.is_file()`。拒绝目录可以避免调用者把一次“读文件”变成目录扫描。

路径检查和文件打开之间仍存在文件系统竞争窗口；这个本地可信样例没有声称提供容器或操作系统沙箱。面对恶意并发修改的文件树，需要基于文件描述符的安全打开方式或只读隔离挂载。

## 2. 按范围读取并限制返回大小

`read_range()` 是本版对外入口。`start_line` 从 1 开始，`end_line` 为包含端点；省略结束行表示读到文件结束。返回大小按 UTF-8 字节计算，默认 8192 字节。`read_file()` 只是同一读取实现的完整文件入口，不建立另一条绕过边界的路径。

从仓库根目录运行：

```bash
uv run python - <<'PY'
from pathlib import Path
from labs.code_search import read_range

result = read_range(
    Path('fixtures/code_search/repository'),
    'database.py',
    start_line=3,
    end_line=3,
)
print(result.path, result.start_line, result.end_line)
print(result.text, end='')
PY
```

结果是：

```text
database.py 3 3
ERROR_TIMEOUT = "[E104]: connection timed out"
```

实现逐行读取，只累计选中的行，选中范围超过 `max_bytes` 就失败。它保持原行尾，所以返回的 `text` 可以与原文精确比对；这也意味着末尾的换行符计入字节预算。起始行超过文件末尾属于错误，空文件的完整读取则合法，返回 `start_line=1, end_line=0, text=''`。

将本版新增文件完整写为 `labs/code_search/reader.py`，代码如下。此前版本的文件保持不变。

```python
"""Workspace-bounded file reads.

The reader is deliberately small.  It is a trust boundary for paths supplied
by a caller, so it resolves the workspace and the requested file before
opening it and rejects symlinks that leave the workspace.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class WorkspaceError(ValueError):
    """An input cannot be safely read from the workspace."""


@dataclass(frozen=True)
class FileRead:
    """A bounded, line-addressed file result."""

    path: str
    start_line: int
    end_line: int
    text: str

    @property
    def bytes_read(self) -> int:
        return len(self.text.encode("utf-8"))


def _resolve_file(workspace: Path, relative_path: str) -> tuple[Path, Path]:
    if not isinstance(relative_path, str) or not relative_path:
        raise WorkspaceError("path must be a nonempty string")
    relative = Path(relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise WorkspaceError("path is outside workspace")
    try:
        root = workspace.resolve(strict=True)
        target = (root / relative).resolve(strict=True)
    except OSError as exc:
        raise WorkspaceError(type(exc).__name__) from exc
    if not target.is_relative_to(root):
        raise WorkspaceError("path is outside workspace")
    if not target.is_file():
        raise WorkspaceError("expected a file inside workspace")
    return root, target


def read_range(
    workspace: Path,
    relative_path: str,
    *,
    start_line: int = 1,
    end_line: int | None = None,
    max_bytes: int = 8192,
) -> FileRead:
    """Read an inclusive line range from one UTF-8 file.

    ``workspace`` is the only allowed root.  The selected text, including
    line endings, must fit in ``max_bytes``.  A bounded line iterator avoids
    loading a whole large file into memory.
    """

    if start_line < 1:
        raise WorkspaceError("start_line must be positive")
    if end_line is not None and end_line < start_line:
        raise WorkspaceError("end_line must be >= start_line")
    if max_bytes < 1:
        raise WorkspaceError("max_bytes must be positive")
    _, target = _resolve_file(workspace, relative_path)

    selected: list[bytes] = []
    selected_bytes = 0
    try:
        with target.open("rb") as source:
            line_number = 1
            while end_line is None or line_number <= end_line:
                chunk = source.readline(max_bytes + 1)
                if not chunk:
                    break
                if line_number >= start_line:
                    selected.append(chunk)
                    selected_bytes += len(chunk)
                    if selected_bytes > max_bytes:
                        raise WorkspaceError("selected range exceeds max_bytes")
                # A line may be larger than the budget.  Bounded chunks let
                # skipped lines stay bounded without changing line numbers.
                if chunk.endswith(b"\n"):
                    line_number += 1
            data = b"".join(selected)
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise WorkspaceError("file is not valid UTF-8") from exc
    except OSError as exc:
        raise WorkspaceError(type(exc).__name__) from exc

    if start_line > 1 and not selected:
        raise WorkspaceError("start_line is past end of file")
    line_count = data.count(b"\n") + int(bool(data) and not data.endswith(b"\n"))
    actual_end = start_line + line_count - 1
    return FileRead(
        path=target.relative_to(Path(workspace).resolve()).as_posix(),
        start_line=start_line,
        end_line=actual_end,
        text=text,
    )


def read_file(
    workspace: Path,
    relative_path: str,
    *,
    max_bytes: int = 8192,
) -> FileRead:
    """Read a complete bounded file through :func:`read_range`."""

    return read_range(workspace, relative_path, max_bytes=max_bytes)
```

## 3. 运行拒绝实验

下面的请求必须失败，不能返回“没有内容”来掩盖权限边界：

```bash
uv run python - <<'PY'
from pathlib import Path
from labs.code_search import WorkspaceError, read_file

try:
    read_file(Path('fixtures/code_search/repository'), '../questions.json')
except WorkspaceError as exc:
    print(type(exc).__name__, str(exc))
PY
```

预期输出为 `WorkspaceError path is outside workspace`。字节上限的实验是把一个存在文件的 `max_bytes` 改成 4；它应报告 `selected range exceeds max_bytes`，不能悄悄截断成看似完整的证据。

`tests/code_search/test_code_search.py` 的 v0 用临时目录检查普通读取、单行范围、路径穿越、越界符号链接和过大返回。这些检查保护的是执行边界，不能证明文件内容值得信任；下一步给模型的材料仍然只是数据。

## 检查点

本版完整文件集合是 `reader.py` 与固定样例树。后续版本增加文件时不会改写本版接口。运行：

```bash
uv run python -m unittest discover -s tests/code_search -v
```

本专题共 10 个测试通过；其中 v0 的两项专门检查本版行为。当前仍须事先知道文件名，也没有文件快照或操作系统沙箱。下一版用字面量检索定位包含 E104 的文件和行号，再回到本版读取上下文。
完整可重放源码保存在 `labs/code_search/checkpoints/v0/`。将本篇示例的导入改为 `from labs.code_search.checkpoints.v0 import ...`，即可直接运行该版；目录中的每个文件都是完整源码，按 reader、grep_search、ast_search、symbols 的顺序只取本版已有文件即可重建。
