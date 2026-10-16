# 文档处理与证据定位 v2：分块

## 读者目标

结构块解决了“这段属于哪个标题”，但模型仍有读取预算。分块必须在大小上有界，同时尽量把标题、条件和结论留在一起。

## 压力示例

固定的每三行窗口很容易把 `## Limits` 和后面的部署时间拆开；它也没有 `block_id` 或标题路径。这个基线仍然有价值，因为它提供了可测量的对照组。

## 第一步：保留一个机械对照组

`fixed_window_chunks` 只按行数切分，返回 `DocumentChunk`，但故意没有结构信息。接着 `structure_chunks` 按 v1 的块顺序合并，块之间用空行连接；标题路径变化时先提交已有块，避免把 Deployment 的文字放进 Refunds 的路径。若组合会超过 `max_chars`，也先提交已有块；超长单行再按字符切开，保证硬上限。

```python
from pathlib import Path
from labs.documents.v0_extract import extract_document
from labs.documents.v1_structure import structure_document
from labs.documents.v2_chunk import fixed_window_chunks, structure_chunks

raw = extract_document(Path("fixtures/documents/handbook-v1.md"), "handbook", "v1")
document = structure_document(raw)
print(fixed_window_chunks(document, max_lines=3)[0])
for chunk in structure_chunks(document, max_chars=100):
    print(chunk.chunk_id, chunk.heading_path, len(chunk.text), chunk.block_ids)
```

这两个函数都校验正数上限。结构分块并不承诺“一个块永远完整”：当单个段落超过预算时，它只能在该段内部切开；但每个结果仍能指出来源行范围和标题路径。

## 第二步：冻结完整检查点

下面是 `labs/documents/v2_chunk.py` 的完整 checkpoint。它只包含上面已经解释的机制；保留前一版本模块并创建本版模块，不需要将分散片段拼接。

```python
"""v2: compare fixed windows with structure-aware document chunks."""

from __future__ import annotations

from dataclasses import dataclass

from .v1_structure import DocumentBlock, StructuredDocument


@dataclass(frozen=True)
class DocumentChunk:
    chunk_id: str
    source_id: str
    source_version: str
    text: str
    start_line: int
    end_line: int
    block_ids: tuple[str, ...]
    heading_path: tuple[str, ...]


def _validate_limit(max_chars: int) -> None:
    if max_chars < 1:
        raise ValueError("max_chars must be positive")


def fixed_window_chunks(document: StructuredDocument, max_lines: int = 4) -> tuple[DocumentChunk, ...]:
    """Split source lines mechanically, without preserving document structure."""

    if max_lines < 1:
        raise ValueError("max_lines must be positive")
    lines = document.text.splitlines()
    chunks: list[DocumentChunk] = []
    for offset in range(0, len(lines), max_lines):
        selected = lines[offset : offset + max_lines]
        if not selected:
            continue
        chunks.append(
            DocumentChunk(
                chunk_id=f"fixed-{len(chunks) + 1:04d}",
                source_id=document.source_id,
                source_version=document.source_version,
                text="\n".join(selected),
                start_line=offset + 1,
                end_line=offset + len(selected),
                block_ids=(),
                heading_path=(),
            )
        )
    return tuple(chunks)


def _split_large_block(block: DocumentBlock, max_chars: int) -> list[tuple[str, int, int]]:
    lines = block.text.splitlines() or [""]
    pieces: list[tuple[str, int, int]] = []
    current: list[str] = []
    current_start = block.start_line
    for index, line in enumerate(lines):
        candidate = "\n".join(current + [line])
        if current and len(candidate) > max_chars:
            pieces.append(("\n".join(current), current_start, current_start + len(current) - 1))
            current = []
            current_start = block.start_line + index
        current.append(line)
    if current:
        pieces.append(("\n".join(current), current_start, current_start + len(current) - 1))

    # A single line can exceed the limit. Split it by characters as the only
    # way to keep the explicit size bound true.
    bounded: list[tuple[str, int, int]] = []
    for text, start, end in pieces:
        if len(text) <= max_chars:
            bounded.append((text, start, end))
            continue
        for offset in range(0, len(text), max_chars):
            bounded.append((text[offset : offset + max_chars], start, end))
    return bounded


def structure_chunks(document: StructuredDocument, max_chars: int = 240) -> tuple[DocumentChunk, ...]:
    """Pack whole structural blocks while keeping heading context on chunks."""

    _validate_limit(max_chars)
    chunks: list[DocumentChunk] = []
    current_text: list[str] = []
    current_blocks: list[str] = []
    current_start = 0
    current_end = 0
    current_path: tuple[str, ...] = ()

    def flush() -> None:
        nonlocal current_text, current_blocks, current_start, current_end, current_path
        if not current_text:
            return
        chunks.append(
            DocumentChunk(
                chunk_id=f"structure-{len(chunks) + 1:04d}",
                source_id=document.source_id,
                source_version=document.source_version,
                text="\n\n".join(current_text),
                start_line=current_start,
                end_line=current_end,
                block_ids=tuple(current_blocks),
                heading_path=current_path,
            )
        )
        current_text = []
        current_blocks = []
        current_start = current_end = 0
        current_path = ()

    for block in document.blocks:
        if current_text and block.heading_path != current_path:
            flush()
        pieces = _split_large_block(block, max_chars)
        for piece_text, piece_start, piece_end in pieces:
            candidate = "\n\n".join(current_text + [piece_text])
            if current_text and len(candidate) > max_chars:
                flush()
            if not current_text:
                current_start = piece_start
                current_path = block.heading_path
            current_text.append(piece_text)
            current_blocks.append(block.block_id)
            current_end = piece_end
    flush()
    return tuple(chunks)
```



完整实现位于 [labs/documents/v2_chunk.py](../../../labs/documents/v2_chunk.py)。运行：

```bash
uv run pytest -q tests/documents/test_v2_chunk.py
```

测试使用 `fixtures/documents/chunk-questions.json` 的同一组问题，要求一个块同时包含问题所需的全部证据词。固定三行基线的完整证据得分是 1/2，结构分块是 2/2，且结构块最大长度不超过 180 字符。它还检查标题路径不混合、非法预算失败，以及单行超长时满足硬上限。这个小数据集只证明本例的取舍，不代表结构切块在所有语料上都更好。

## 冻结与下一步

现在模型可以收到有界并带结构上下文的块。仍然存在时间问题：回答中的行号会随着文档更新而指向新内容。下一版本为引用绑定来源版本和内容摘要，并对删除的旧版本显式失败。
