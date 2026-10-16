from dataclasses import replace
from pathlib import Path

import pytest

from labs.documents.v0_extract import extract_document
from labs.documents.v1_structure import structure_document
from labs.documents.v3_citations import (
    CitationMismatch,
    CitationUnavailable,
    VersionedDocumentStore,
    cite_block,
    make_citation,
)


FIXTURES = Path(__file__).parents[2] / "fixtures" / "documents"


def _document(name: str, version: str):
    return structure_document(
        extract_document(FIXTURES / name, "handbook", version)
    )


def test_citation_resolves_against_the_recorded_version() -> None:
    document = _document("handbook-v1.md", "v1")
    block = next(block for block in document.blocks if "seven days" in block.text)
    citation = cite_block(document, block)
    store = VersionedDocumentStore()
    store.add(document)

    assert store.resolve(citation).startswith(
        "Refunds are available within seven days of delivery."
    )
    assert "Keep the order number" in store.resolve(citation)


def test_new_version_does_not_repoint_old_citation() -> None:
    old = _document("handbook-v1.md", "v1")
    new = _document("handbook-v2.md", "v2")
    old_block = next(block for block in old.blocks if "seven days" in block.text)
    citation = cite_block(old, old_block)
    store = VersionedDocumentStore()
    store.add(old)
    store.add(new)

    resolved = store.resolve(citation)
    assert resolved.startswith("Refunds are available within seven days of delivery.")
    assert "fourteen days" not in resolved


def test_deleted_version_is_explicitly_unavailable() -> None:
    document = _document("handbook-v1.md", "v1")
    citation = cite_block(document, document.blocks[0])
    store = VersionedDocumentStore()
    store.add(document)
    store.remove("handbook", "v1")

    with pytest.raises(CitationUnavailable, match="handbook@v1"):
        store.resolve(citation)


def test_same_version_cannot_be_silently_overwritten() -> None:
    old = _document("handbook-v1.md", "v1")
    new_content = _document("handbook-v2.md", "v1")
    store = VersionedDocumentStore()
    store.add(old)

    with pytest.raises(ValueError, match="already contains different content"):
        store.add(new_content)


def test_corrupted_citation_digest_is_detected() -> None:
    document = _document("handbook-v1.md", "v1")
    citation = cite_block(document, document.blocks[0])
    store = VersionedDocumentStore()
    store.add(document)

    with pytest.raises(CitationMismatch):
        store.resolve(replace(citation, quote_sha256="0" * 64))


@pytest.mark.parametrize("start,end", [(0, 1), (2, 1), (1, 999)])
def test_citation_rejects_ranges_outside_source(start: int, end: int) -> None:
    document = _document("handbook-v1.md", "v1")
    with pytest.raises(ValueError, match="range"):
        make_citation(document, start, end)
