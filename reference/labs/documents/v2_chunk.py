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
