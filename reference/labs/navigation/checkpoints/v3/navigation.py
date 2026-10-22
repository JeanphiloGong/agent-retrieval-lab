"""Line- and character-addressable Markdown navigation.

Only ATX headings are supported.  Fenced code is opaque; returned ranges are
exact slices of the original text, including its line endings.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Iterable, Literal, Mapping, Sequence


@dataclass
class Section:
    id: str
    title: str
    level: int
    start_line: int
    end_line: int
    parent: str | None = None
    children: list[str] = field(default_factory=list)
    text: str = ""
    own_end_line: int = 0
    start_offset: int = 0
    end_offset: int = 0
    source_id: str = "markdown"
    source_version: str = ""
    source_digest: str = ""


def _line_offsets(lines: Sequence[str]) -> list[int]:
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    return offsets


def document_tree(
    text: str,
    *,
    source_id: str = "markdown",
    source_version: str | None = None,
) -> list[Section]:
    """Build ordered sections without treating fenced examples as headings."""

    if not source_id or source_version == "":
        raise ValueError("source metadata must be nonempty")
    lines = text.splitlines(keepends=True)
    if not lines:
        return []
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    version = source_version or digest
    offsets = _line_offsets(lines)
    headings: list[tuple[int, int, str]] = []
    fence_char: str | None = None
    fence_length = 0
    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.rstrip("\r\n")
        fence = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if fence_char:
            closing = re.match(rf"^ {{0,3}}{re.escape(fence_char)}{{{fence_length},}}[ \t]*$", line)
            if closing:
                fence_char = None
            continue
        if fence:
            marker, info = fence.groups()
            if marker[0] != "`" or "`" not in info:
                fence_char, fence_length = marker[0], len(marker)
            continue
        match = re.match(r"^ {0,3}(#{1,6})(?:[ \t]+(.*)|[ \t]*)$", line)
        if match:
            title = re.sub(r"[ \t]+#+[ \t]*$", "", match.group(2) or "").strip()
            headings.append((line_number, len(match.group(1)), title))

    if not headings:
        return [Section("s1", "Document", 0, 1, len(lines), text=text,
                        own_end_line=len(lines), end_offset=len(text),
                        source_id=source_id, source_version=version, source_digest=digest)]

    sections: list[Section] = []
    stack: list[Section] = []
    if headings[0][0] > 1 and any(line.strip() for line in lines[:headings[0][0] - 1]):
        end = headings[0][0] - 1
        sections.append(Section("preamble", "Preamble", 0, 1, end,
                                text="".join(lines[:end]), own_end_line=end,
                                end_offset=offsets[end], source_id=source_id,
                                source_version=version, source_digest=digest))
    for number, (start, level, title) in enumerate(headings):
        while stack and stack[-1].level >= level:
            previous = stack.pop()
            previous.end_line = start - 1
            previous.end_offset = offsets[start - 1]
        parent = stack[-1] if stack else None
        own_end = headings[number + 1][0] - 1 if number + 1 < len(headings) else len(lines)
        section = Section(
            f"s{number + 1}", title, level, start, len(lines),
            parent.id if parent else None,
            text="".join(lines[start:own_end]), own_end_line=own_end,
            start_offset=offsets[start - 1], end_offset=len(text),
            source_id=source_id, source_version=version, source_digest=digest,
        )
        if parent:
            parent.children.append(section.id)
        sections.append(section)
        stack.append(section)
    return sections


def parse_markdown(
    text: str,
    *,
    source_id: str = "markdown",
    source_version: str | None = None,
) -> list[Section]:
    """Public name retained for callers that used the original parser API."""

    return document_tree(text, source_id=source_id, source_version=source_version)


def _terms(text: str) -> set[str]:
    return {term.lower() for term in re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]", text)}


def find_sections(sections: Iterable[Section], query: str) -> list[Section]:
    """Rank a node's own title/body; descendants do not inflate parent scores."""

    terms = _terms(query)
    if not terms:
        return []
    ranked: list[tuple[int, Section]] = []
    for section in sections:
        score = len((_terms(section.title) | _terms(section.text)) & terms)
        if score:
            ranked.append((score, section))
    ranked.sort(key=lambda item: (-item[0], -item[1].level,
                                  item[1].source_id, item[1].source_version,
                                  item[1].start_line))
    return [section for _, section in ranked]


@dataclass(frozen=True)
class RangeRead:
    source_id: str
    source_version: str
    section_id: str
    quote: str
    start_line: int
    end_line: int
    start_offset: int
    end_offset: int
    truncated: bool

    def __iter__(self):
        """Allow old ``quote, truncated = read_range(...)`` call sites."""

        yield self.quote
        yield self.truncated


def read_range(
    text: str,
    section: Section,
    *,
    before: int = 0,
    after: int = 0,
    max_lines: int = 80,
) -> RangeRead:
    """Read an exact, budgeted slice and report the actual returned range."""

    if min(before, after) < 0 or max_lines < 1:
        raise ValueError("range limits must be non-negative and max_lines must be positive")
    if hashlib.sha256(text.encode("utf-8")).hexdigest() != section.source_digest:
        raise ValueError("section belongs to different document content")
    lines = text.splitlines(keepends=True)
    if not 1 <= section.start_line <= section.end_line <= len(lines):
        raise ValueError("section range is outside document")
    offsets = _line_offsets(lines)
    start = max(1, section.start_line - before)
    requested_end = min(len(lines), section.end_line + after)
    actual_end = min(requested_end, start + max_lines - 1)
    start_offset, end_offset = offsets[start - 1], offsets[actual_end]
    return RangeRead(section.source_id, section.source_version, section.id,
                     text[start_offset:end_offset], start, actual_end,
                     start_offset, end_offset, actual_end < requested_end)


@dataclass(frozen=True)
class Evidence:
    source_id: str
    section_id: str
    quote: str
    start_line: int
    end_line: int
    source_version: str
    start_offset: int
    end_offset: int
    truncated: bool


def combine_evidence(
    documents: Mapping[tuple[str, str], str],
    queries: Iterable[str],
    *,
    strategy: Literal["tree", "hybrid"] = "tree",
    top_k: int = 1,
    max_lines: int = 40,
    embedding=None,
) -> list[Evidence]:
    """Gather evidence across sources without merging contradictory quotes.

    Queries are explicit evidence subquestions, supplied by the caller.  This
    function does not infer that a question is completely answered merely
    because one section was returned.
    """

    if strategy not in {"tree", "hybrid"}:
        raise ValueError("unknown navigation strategy")
    if top_k < 1:
        raise ValueError("top_k must be positive")
    sections: list[Section] = []
    for (source_id, version), text in documents.items():
        sections.extend(document_tree(text, source_id=source_id, source_version=version))
    if strategy == "hybrid":
        from labs.hybrid.retrieval import Document, bm25_rank, rrf_fuse, vector_rank

        if embedding is None:
            raise ValueError("hybrid navigation requires an embedding model")
        corpus = [Document(str(index), section.title + "\n" + section.text)
                  for index, section in enumerate(sections)]
        vectors = [list(vector) for vector in embedding.embed([document.text for document in corpus])]
    chosen: list[Evidence] = []
    known: set[tuple[str, str, str]] = set()
    for query in queries:
        if strategy == "tree":
            ranked = find_sections(sections, query)
        else:
            query_vector = list(next(iter(embedding.embed([query]))))
            fused = rrf_fuse(bm25_rank(corpus, query), vector_rank(corpus, vectors, query_vector))
            ranked = [sections[int(hit.document.id)] for hit in fused]
        for section in ranked[:top_k]:
            identity = (section.source_id, section.source_version, section.id)
            if identity in known:
                continue
            result = read_range(documents[(section.source_id, section.source_version)],
                                section, max_lines=max_lines)
            chosen.append(Evidence(result.source_id, result.section_id, result.quote,
                                   result.start_line, result.end_line, result.source_version,
                                   result.start_offset, result.end_offset, result.truncated))
            known.add(identity)
    return chosen


def compare_navigation(
    documents: Mapping[tuple[str, str], str],
    cases: Sequence[dict],
    *,
    top_k: int = 1,
    embedding=None,
) -> dict[str, dict[str, dict[str, float | int]]]:
    """Compare evidence recall, separately for single/multiple source questions."""

    report: dict[str, dict[str, dict[str, float | int]]] = {}
    for strategy in ("tree", "hybrid"):
        groups: dict[str, list[tuple[float, bool]]] = {"single_document": [], "multi_document": []}
        for case in cases:
            category = case["category"]
            if category not in groups:
                raise ValueError("unknown question category")
            expected = {(item["source_id"], item["source_version"], item["section_id"])
                        for item in case["gold_evidence"]}
            if not expected:
                raise ValueError("evaluation case requires gold evidence")
            evidence = combine_evidence(documents, case["queries"], strategy=strategy,
                                        top_k=top_k, embedding=embedding)
            actual = {(item.source_id, item.source_version, item.section_id) for item in evidence}
            recall = len(expected & actual) / len(expected)
            groups[category].append((recall, expected <= actual))
        report[strategy] = {
            category: {
                "questions": len(values),
                "mean_recall": sum(value[0] for value in values) / len(values) if values else 0.0,
                "complete_evidence_rate": sum(value[1] for value in values) / len(values) if values else 0.0,
            }
            for category, values in groups.items()
        }
    return report
