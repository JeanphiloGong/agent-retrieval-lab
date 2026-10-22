"""v2: fuse lexical and vector rankings by rank, not incompatible scores."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from labs.hybrid.models import load_embedding
from labs.hybrid.retrieval import Document, Hit, bm25_rank, rrf_fuse
from labs.hybrid.checkpoints.v1_vector import Encoder, rank_with_encoder


def fuse(
    documents: Sequence[Document],
    query: str,
    encoder: Encoder,
    *,
    rrf_k: int = 60,
) -> list[Hit]:
    lexical = bm25_rank(documents, query)
    semantic = rank_with_encoder(documents, query, encoder)
    return rrf_fuse(lexical, semantic, k=rrf_k)


def fuse_with_model(
    documents: Sequence[Document], query: str, cache: Path
) -> list[Hit]:
    return fuse(documents, query, load_embedding(cache))


if __name__ == "__main__":
    docs = (Document("e104", "E104 means connection timeout while opening a socket"),)
    for hit in fuse_with_model(docs, "network deadline", Path("artifacts/models")):
        print(hit.document.id, round(hit.score, 4), hit.sources)
