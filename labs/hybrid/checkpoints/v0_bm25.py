"""v0: a reproducible lexical BM25 checkpoint."""

from __future__ import annotations

from collections.abc import Sequence

from labs.hybrid.retrieval import Document, Hit, bm25_rank


def rank(documents: Sequence[Document], query: str) -> list[Hit]:
    """Return lexical candidates; no semantic model is involved in v0."""
    return bm25_rank(documents, query)


if __name__ == "__main__":
    documents = (
        Document("e104", "E104 means connection timeout while opening a socket"),
        Document("refund", "Customers may request a refund within seven days"),
    )
    for hit in rank(documents, "E104"):
        print(hit.document.id, round(hit.score, 4), hit.sources)
