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
