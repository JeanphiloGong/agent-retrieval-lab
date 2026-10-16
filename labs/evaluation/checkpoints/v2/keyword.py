"""A small deterministic keyword baseline for line-addressable sources."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .validate import load_sources

TOKEN = re.compile(r"[A-Za-z0-9]+")


@dataclass(frozen=True)
class DocumentLine:
    source_id: str
    source_version: str
    line_number: int
    text: str


@dataclass(frozen=True)
class SearchResult:
    source_id: str
    source_version: str
    start_line: int
    end_line: int
    text: str
    score: int


def tokenize(text: str) -> tuple[str, ...]:
    """Return lowercase alphanumeric terms while preserving code-like IDs."""

    return tuple(match.group(0).lower() for match in TOKEN.finditer(text))


def load_documents(source_manifest_path: Path) -> tuple[DocumentLine, ...]:
    """Read each allow-listed source as independent, addressable lines."""

    documents: list[DocumentLine] = []
    for source in load_sources(source_manifest_path):
        lines = source.path.read_text(encoding="utf-8").splitlines()
        documents.extend(
            DocumentLine(
                source_id=source.source_id,
                source_version=source.source_version,
                line_number=line_number,
                text=text,
            )
            for line_number, text in enumerate(lines, start=1)
        )
    return tuple(documents)


def search(
    query: str,
    documents: Iterable[DocumentLine],
    *,
    limit: int = 5,
) -> list[SearchResult]:
    """Rank source lines by how many query terms they contain.

    This is intentionally a baseline: it has no stemming, synonym expansion,
    embeddings, or cross-line passage construction. Ties use source identity
    and line number so the same input always produces the same ranking.
    """

    if limit < 1:
        raise ValueError("limit must be positive")
    query_terms = tokenize(query)
    if not query_terms:
        return []
    term_set = set(query_terms)
    results: list[SearchResult] = []
    for document in documents:
        score = len(term_set & set(tokenize(document.text)))
        if score:
            results.append(
                SearchResult(
                    source_id=document.source_id,
                    source_version=document.source_version,
                    start_line=document.line_number,
                    end_line=document.line_number,
                    text=document.text,
                    score=score,
                )
            )
    results.sort(
        key=lambda result: (
            -result.score,
            result.source_id,
            result.source_version,
            result.start_line,
        )
    )
    return results[:limit]


def search_manifest(
    query: str,
    source_manifest_path: Path,
    *,
    limit: int = 5,
) -> list[SearchResult]:
    """Convenience entry point used by the tutorial and command examples."""

    return search(query, load_documents(source_manifest_path), limit=limit)
