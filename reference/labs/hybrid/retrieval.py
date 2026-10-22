from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Iterable, Sequence

from rank_bm25 import BM25Plus


TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[一-鿿]")


@dataclass(frozen=True)
class Document:
    id: str
    text: str
    topic: str = ""


@dataclass(frozen=True)
class Hit:
    document: Document
    score: float
    sources: tuple[str, ...] = ()


def tokenize(text: str) -> list[str]:
    """Use one stable tokenizer for every lexical measurement."""
    return [token.lower() for token in TOKEN_RE.findall(text)]


def bm25_rank(documents: Sequence[Document], query: str, *, k1: float = 1.5, b: float = 0.75) -> list[Hit]:
    if k1 < 0 or not 0 <= b <= 1:
        raise ValueError("invalid BM25 parameters")
    terms = tokenize(query)
    if not terms or not documents:
        return []
    tokenized = [tokenize(doc.text) for doc in documents]
    if not any(tokenized):
        return []
    scores = BM25Plus(tokenized, k1=k1, b=b).get_scores(terms)
    scored = [Hit(doc, float(score), ("bm25",)) for doc, tokens, score in zip(documents, tokenized, scores) if set(tokens) & set(terms)]
    return sorted(scored, key=lambda hit: (-hit.score, hit.document.id))


def vector_rank(documents: Sequence[Document], vectors: Sequence[Sequence[float]], query_vector: Sequence[float]) -> list[Hit]:
    if len(documents) != len(vectors) or not query_vector:
        raise ValueError("vector count or dimensions do not match")
    if any(len(vector) != len(query_vector) for vector in vectors):
        raise ValueError("vector dimensions do not match")
    if any(not math.isfinite(value) for vector in [query_vector, *vectors] for value in vector):
        raise ValueError("vectors must be finite")
    def cosine(vector):
        norm = math.sqrt(sum(value * value for value in vector) * sum(value * value for value in query_vector))
        return sum(a * b for a, b in zip(vector, query_vector)) / norm if norm else 0.0
    scored = [Hit(doc, cosine(vector), ("vector",)) for doc, vector in zip(documents, vectors)]
    return sorted(scored, key=lambda hit: (-hit.score, hit.document.id))


def rrf_fuse(*rankings: Iterable[Hit], k: int = 60) -> list[Hit]:
    if k <= 0:
        raise ValueError("k must be positive")
    merged: dict[str, tuple[Document, float, set[str]]] = {}
    for ranking in rankings:
        seen = set()
        for position, hit in enumerate(ranking, start=1):
            if hit.document.id in seen:
                raise ValueError("a ranking contains duplicate document IDs")
            seen.add(hit.document.id)
            document, score, sources = merged.get(hit.document.id, (hit.document, 0.0, set()))
            if document != hit.document:
                raise ValueError("the same ID refers to different documents")
            sources.update(hit.sources)
            merged[hit.document.id] = (document, score + 1 / (k + position), sources)
    return [Hit(doc, score, tuple(sorted(sources))) for doc, score, sources in sorted(
        merged.values(), key=lambda item: (-item[1], item[0].id)
    )]


def rerank(query: str, candidates: Sequence[Hit], *, scorer) -> list[Hit]:
    """Apply a bounded relevance function while preserving retrieval provenance."""
    scores = list(scorer(query, [hit.document.text for hit in candidates]))
    if len(scores) != len(candidates) or any(not math.isfinite(float(score)) for score in scores):
        raise ValueError("reranker returned invalid scores")
    ranked = [Hit(hit.document, float(score), hit.sources) for hit, score in zip(candidates, scores)]
    return sorted(ranked, key=lambda hit: (-hit.score, hit.document.id))
