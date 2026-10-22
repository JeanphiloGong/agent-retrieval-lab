"""v3: resolve citations against immutable source versions."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .v1_structure import DocumentBlock, StructuredDocument


class CitationUnavailable(LookupError):
    """The cited source version is no longer available."""


class CitationMismatch(ValueError):
    """The cited range exists but no longer has the cited content."""


@dataclass(frozen=True)
class Citation:
    source_id: str
    source_version: str
    start_line: int
    end_line: int
    quote_sha256: str


def _range_text(document: StructuredDocument, start_line: int, end_line: int) -> str:
    if start_line < 1 or end_line < start_line:
        raise ValueError("citation line range is invalid")
    lines = document.text.splitlines()
    if end_line > len(lines):
        raise ValueError("citation line range is outside document")
    return "\n".join(lines[start_line - 1 : end_line])


def make_citation(document: StructuredDocument, start_line: int, end_line: int) -> Citation:
    quote = _range_text(document, start_line, end_line)
    return Citation(
        source_id=document.source_id,
        source_version=document.source_version,
        start_line=start_line,
        end_line=end_line,
        quote_sha256=hashlib.sha256(quote.encode("utf-8")).hexdigest(),
    )


def cite_block(document: StructuredDocument, block: DocumentBlock) -> Citation:
    return make_citation(document, block.start_line, block.end_line)


class VersionedDocumentStore:
    """Keep each source version addressable without silently overwriting it."""

    def __init__(self) -> None:
        self._documents: dict[tuple[str, str], StructuredDocument] = {}

    def add(self, document: StructuredDocument) -> None:
        key = (document.source_id, document.source_version)
        existing = self._documents.get(key)
        if existing is not None and existing.text != document.text:
            raise ValueError(f"source version already contains different content: {key}")
        self._documents[key] = document

    def remove(self, source_id: str, source_version: str) -> None:
        self._documents.pop((source_id, source_version), None)

    def resolve(self, citation: Citation) -> str:
        document = self._documents.get((citation.source_id, citation.source_version))
        if document is None:
            raise CitationUnavailable(
                f"source version unavailable: {citation.source_id}@{citation.source_version}"
            )
        quote = _range_text(document, citation.start_line, citation.end_line)
        digest = hashlib.sha256(quote.encode("utf-8")).hexdigest()
        if digest != citation.quote_sha256:
            raise CitationMismatch("cited range changed for the recorded source version")
        return quote
