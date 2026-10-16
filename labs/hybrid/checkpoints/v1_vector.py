"""v1: use the pinned FastEmbed model for a second, semantic ranking."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from labs.hybrid.models import load_embedding
from labs.hybrid.retrieval import Document, Hit, vector_rank


class Encoder(Protocol):
    def embed(self, documents: Sequence[str]): ...

    def query_embed(self, query: str): ...


def _values(vector) -> list[float]:
    values = vector.tolist() if hasattr(vector, "tolist") else vector
    return [float(value) for value in values]


def rank_with_encoder(
    documents: Sequence[Document], query: str, encoder: Encoder
) -> list[Hit]:
    vectors = [_values(vector) for vector in encoder.embed([doc.text for doc in documents])]
    query_vector = _values(next(encoder.query_embed(query)))
    return vector_rank(documents, vectors, query_vector)


def rank_with_model(
    documents: Sequence[Document], query: str, cache: Path
) -> list[Hit]:
    """Load the pinned model and fail loudly if it cannot be loaded."""
    return rank_with_encoder(documents, query, load_embedding(cache))


if __name__ == "__main__":
    docs = (Document("e104", "E104 means connection timeout while opening a socket"),)
    for hit in rank_with_model(docs, "network deadline", Path("artifacts/models")):
        print(hit.document.id, round(hit.score, 4), hit.sources)
