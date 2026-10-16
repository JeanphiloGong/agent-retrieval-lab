# 文档处理与证据定位 v1：结构保留

## 读者目标

v0 能读到正文，但“Limits 下的部署窗口”和另一个同名标题下的内容仍是一串行。检索结果需要知道段落属于哪个标题，并且需要把整张表作为一个证据边界。

## 压力示例

`fixtures/documents/handbook-v1.md` 有两个 `Refunds` 标题。只保存文本时，两段文字都可能被返回为同一个命中；表格的标题行、分隔线和数据行也会被随意截断。结构不是装饰，它决定证据的语义范围。

## 第一步：让块成为可定位单位

在 `labs/documents/v1_structure.py` 中，`structure_document` 消费 v0 的 `ExtractedDocument`，按顺序输出三种 `DocumentBlock`：`heading`、`paragraph` 和 `table`。每个块包含从 1 开始的 `start_line`/`end_line`、确定性的 `block_id` 和当时的 `heading_path`。

标题解析会按层级截断旧路径；连续的 `|` 行合并成一个表格块；空行提交当前段落。解析过程不改写来源正文，所以行号仍可回到原文。

```python
from pathlib import Path
from labs.documents.v0_extract import extract_document
from labs.documents.v1_structure import structure_document

raw = extract_document(Path("fixtures/documents/handbook-v1.md"), "handbook", "v1")
structured = structure_document(raw)
for block in structured.blocks:
    print(block.kind, block.start_line, block.heading_path, repr(block.text))
```

## 第二步：冻结完整检查点

下面是 `labs/documents/v1_structure.py` 的完整 checkpoint。它只包含上面已经解释的机制；保留前一版本模块并创建本版模块，不需要将分散片段拼接。

```python
"""v1: retain headings, paragraphs, and table boundaries from Markdown."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .v0_extract import ExtractedDocument


@dataclass(frozen=True)
class DocumentBlock:
    block_id: str
    kind: str
    text: str
    start_line: int
    end_line: int
    heading_path: tuple[str, ...]


@dataclass(frozen=True)
class StructuredDocument:
    source_id: str
    source_version: str
    format: str
    text: str
    blocks: tuple[DocumentBlock, ...]


_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


def _block(block_number: int, kind: str, lines: list[str], start: int, path: tuple[str, ...]) -> DocumentBlock:
    return DocumentBlock(
        block_id=f"b{block_number:04d}",
        kind=kind,
        text="\n".join(lines),
        start_line=start,
        end_line=start + len(lines) - 1,
        heading_path=path,
    )


def structure_document(document: ExtractedDocument) -> StructuredDocument:
    """Parse an extracted document into ordered, line-addressable blocks."""

    lines = document.text.splitlines()
    blocks: list[DocumentBlock] = []
    heading_stack: list[tuple[int, str]] = []
    pending: list[str] = []
    pending_start = 0
    number = 1

    def flush_paragraph() -> None:
        nonlocal pending, pending_start, number
        if pending:
            path = tuple(title for _, title in heading_stack)
            blocks.append(_block(number, "paragraph", pending, pending_start, path))
            number += 1
            pending = []
            pending_start = 0

    index = 0
    while index < len(lines):
        line = lines[index]
        line_number = index + 1
        heading = _HEADING.match(line) if document.format == "markdown" else None
        if heading:
            flush_paragraph()
            level = len(heading.group(1))
            title = heading.group(2).strip()
            heading_stack[:] = [item for item in heading_stack if item[0] < level]
            heading_stack.append((level, title))
            path = tuple(item[1] for item in heading_stack)
            blocks.append(_block(number, "heading", [title], line_number, path))
            number += 1
            index += 1
            continue

        is_table = document.format == "markdown" and line.lstrip().startswith("|")
        if is_table:
            flush_paragraph()
            table_lines: list[str] = []
            table_start = line_number
            while index < len(lines) and lines[index].lstrip().startswith("|"):
                table_lines.append(lines[index])
                index += 1
            path = tuple(title for _, title in heading_stack)
            blocks.append(_block(number, "table", table_lines, table_start, path))
            number += 1
            continue

        if not line.strip():
            flush_paragraph()
            index += 1
            continue

        if not pending:
            pending_start = line_number
        pending.append(line)
        index += 1

    flush_paragraph()
    return StructuredDocument(
        source_id=document.source_id,
        source_version=document.source_version,
        format=document.format,
        text=document.text,
        blocks=tuple(blocks),
    )
```



完整实现位于 [labs/documents/v1_structure.py](../../../labs/documents/v1_structure.py)。例如第二个 `Refunds` 仍有自己的行号，`Limits` 段落的路径是 `("Support Handbook", "Deployment", "Limits")`，表格是一个 `table` 块。运行：

```bash
uv run pytest -q tests/documents/test_v1_structure.py
```

测试覆盖重复标题的位置、表格边界和段落标题上下文。

## 冻结与下一步

现在每个证据块都能回到标题和原文范围。仍然不能直接把整篇长文塞进模型上下文；若机械按字符切分，适用条件和结论会落入不同块。下一版本比较固定窗口与保留结构的分块结果。
