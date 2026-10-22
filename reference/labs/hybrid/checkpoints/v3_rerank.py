"""v3: rerank only a bounded fused candidate set."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from labs.hybrid.checkpoints.v1_vector import Encoder
from labs.hybrid.checkpoints.v2_fusion import fuse
from labs.hybrid.models import load_embedding, load_reranker
from labs.hybrid.retrieval import Document, Hit, rerank


def rerank_candidates(
    documents: Sequence[Document],
    query: str,
    encoder: Encoder,
    scorer: Callable[[str, Sequence[str]], Sequence[float]],
    *,
    candidate_limit: int = 6,
) -> list[Hit]:
    if candidate_limit < 1:
        raise ValueError("candidate_limit must be positive")
    candidates = fuse(documents, query, encoder)[:candidate_limit]
    return rerank(query, candidates, scorer=scorer)


def rerank_with_models(
    documents: Sequence[Document], query: str, cache: Path, *, candidate_limit: int = 6
) -> list[Hit]:
    embedding = load_embedding(cache)
    cross_encoder = load_reranker(cache)
    return rerank_candidates(
        documents,
        query,
        embedding,
        cross_encoder.rerank,
        candidate_limit=candidate_limit,
    )


if __name__ == "__main__":
    docs = (Document("e104", "E104 means connection timeout while opening a socket"),)
    for hit in rerank_with_models(docs, "network deadline", Path("artifacts/models")):
        print(hit.document.id, round(hit.score, 4), hit.sources)
