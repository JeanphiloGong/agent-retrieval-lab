# 代码与精确检索 v1：grep 定位

v0 能安全读取已知文件，但用户问“E104 在哪里定义”时，助手还不知道该读哪个文件。本版增加 `labs/code_search/grep_search.py`，保留 v0 的读取边界。这里的 grep 指字面量逐行检索，使用标准库完成确定性实验，不依赖外部 `grep` 命令。

从自己已通过 v0 验收的 `labs/code_search/reader.py` 继续。先按下文写出 `grep_search.py`，再运行第 3 节以后的实验；包的 `__init__.py` 保持为空。

固定资料故意让 `[E104]` 同时出现在 Python 常量和说明文本中。检索只负责给出位置；判断哪个位置是定义属于之后的语法或证据分析。

## 1. 明确三种结果

`grep_literal(workspace, needle, glob='**/*', max_results=100, timeout_seconds=2.0)` 返回 `GrepResult`。`matches` 是 `GrepMatch(path, line, text)` 的有序元组；路径相对工作目录，行号从 1 开始。`status` 有三种值：

| 状态 | 含义 |
| --- | --- |
| `matched` | 已找到结果，可能因达到结果上限提前停止 |
| `no_match` | 在本次扫描范围内没有匹配 |
| `timeout` | 时间预算耗尽，已有结果只是部分结果 |

`timeout` 不能伪装成 `no_match`，否则系统会把“没有查完”误写成“仓库没有这个符号”。空查询和非正数预算直接拒绝，避免返回全部文件或制造不可解释的执行。

## 2. 写出字面量检索

将本版新增文件完整写为 `labs/code_search/grep_search.py`，代码如下。此前版本的文件保持不变。

```python
"""Literal, bounded text search for source trees."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .reader import WorkspaceError


class SearchTimeout(WorkspaceError):
    """The search exceeded its caller-provided time budget."""


@dataclass(frozen=True)
class GrepMatch:
    path: str
    line: int
    text: str


@dataclass(frozen=True)
class GrepResult:
    status: Literal["matched", "no_match", "timeout"]
    matches: tuple[GrepMatch, ...]


def _files(root: Path, glob: str) -> list[Path]:
    # A sorted list makes output stable across filesystems and test runs.
    return sorted(path for path in root.glob(glob) if path.is_file())


def grep_literal(
    workspace: Path,
    needle: str,
    *,
    glob: str = "**/*",
    max_results: int = 100,
    timeout_seconds: float = 2.0,
) -> GrepResult:
    """Find ``needle`` as a literal substring and return source lines.

    This intentionally does not use regular expressions: ``[`` and ``*`` in
    an error code or function name retain their literal meaning.  A timeout is
    represented separately from an empty result so callers cannot mistake an
    interrupted search for a proven miss.
    """

    if not isinstance(needle, str) or not needle:
        raise WorkspaceError("needle must be a nonempty string")
    if max_results < 1:
        raise WorkspaceError("max_results must be positive")
    if timeout_seconds <= 0:
        raise WorkspaceError("timeout_seconds must be positive")
    try:
        root = workspace.resolve(strict=True)
    except OSError as exc:
        raise WorkspaceError(type(exc).__name__) from exc
    if not root.is_dir():
        raise WorkspaceError("workspace must be a directory")

    deadline = time.monotonic() + timeout_seconds
    matches: list[GrepMatch] = []
    for path in _files(root, glob):
        if time.monotonic() >= deadline:
            return GrepResult("timeout", tuple(matches))
        try:
            if not path.resolve(strict=True).is_relative_to(root):
                continue
        except OSError as exc:
            raise WorkspaceError(type(exc).__name__) from exc
        try:
            with path.open("r", encoding="utf-8") as source:
                for line_number, line in enumerate(source, start=1):
                    if time.monotonic() >= deadline:
                        return GrepResult("timeout", tuple(matches))
                    if needle in line:
                        matches.append(
                            GrepMatch(
                                path=path.relative_to(root).as_posix(),
                                line=line_number,
                                text=line.rstrip("\r\n"),
                            )
                        )
                        if len(matches) >= max_results:
                            return GrepResult("matched", tuple(matches))
        except UnicodeDecodeError:
            # Binary or non-UTF-8 files are not source evidence.
            continue
        except OSError as exc:
            raise WorkspaceError(type(exc).__name__) from exc
    return GrepResult("matched" if matches else "no_match", tuple(matches))
```

## 3. 理解扫描与预算

写完文件后运行固定资料：

```bash
uv run python - <<'PY'
from pathlib import Path
from labs.code_search.grep_search import grep_literal

root = Path('fixtures/code_search/repository')
result = grep_literal(root, '[E104]')
print(result.status)
for match in result.matches:
    print(f'{match.path}:{match.line}: {match.text}')
print(grep_literal(root, 'a[b]*').status)
print(grep_literal(root, 'E999').status)
PY
```

第一个请求会命中 `README.txt:1` 与 `database.py:3`；后两个状态分别为 `matched` 和 `no_match`。`[`、`]` 和 `*` 没有正则表达式语义，故 `a[b]*` 只匹配同样的文字。这对错误码、函数签名和包含标点的精确语法尤其重要。

实现先按路径排序，使同样资料产生同样顺序，再逐行判断 `needle in line`。每个文件和每行之间检查单调时钟；`max_results` 约束返回大小。非 UTF-8 文件不作为文本证据；越界符号链接不进入扫描。文件读取故障抛出 `WorkspaceError`，而不是变成无匹配。

本版只做合作式时间预算：检查发生在读取行之间，单次文件系统调用仍可能阻塞。它也不是大仓库生产搜索器，没有倒排索引、ignore 规则和结果完整性计数。数据规模变大时，应由成熟文本搜索工具或索引后端承担扫描，Agent 保留相同的“查询到定位结果”工具契约。

## 4. 将定位交回 v0

```bash
uv run python - <<'PY'
from pathlib import Path
from labs.code_search.grep_search import grep_literal
from labs.code_search.reader import read_range

root = Path('fixtures/code_search/repository')
for hit in grep_literal(root, '[E104]', glob='**/*.py').matches:
    evidence = read_range(root, hit.path, start_line=hit.line, end_line=hit.line)
    print(evidence.path, evidence.start_line, repr(evidence.text))
PY
```

这里 `glob` 限定 Python 文件，只把 `database.py:3` 交给读取工具。定位结果是线索，`read_range` 返回的原文才是可核对的证据。两者都不解释或执行原文里的指令。

## 检查点

本版文件集合是 v0 的 `reader.py` 加 `grep_search.py`。`tests/code_search/test_code_search.py` 的 v1 检查字面量、无命中、行号与超时的区别。

```bash
uv run python -m pytest -q tests/code_search/test_code_search.py -k 'test_v0 or test_v1'
```

预期为 v0 与 v1 的 4 项检查通过。把查询改成 `connect` 会看见注释、定义和调用全都匹配，这是文本检索的正常行为。下一版使用 AST 提取真正的定义范围，不靠正则推断 Python 语法。

参考快照位于 `reference/labs/code_search/checkpoints/v1/`；显式重放可运行下列命令。它只核对参考答案，不计为个人学习进度。

```bash
PYTHONPATH=reference uv run python -P -c 'from pathlib import Path; from labs.code_search.checkpoints.v1 import grep_literal; print(grep_literal(Path("fixtures/code_search/repository"), "[E104]").status)'
```
