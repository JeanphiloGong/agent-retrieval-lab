"""v4: replay the fixed held-out benchmark and write its measured report."""

from __future__ import annotations

import argparse
import json
import math
import platform
from pathlib import Path
from time import perf_counter

from labs.hybrid.models import EMBEDDING, RERANKER, load_embedding, load_reranker
from labs.hybrid.retrieval import Document, bm25_rank, rerank, rrf_fuse, vector_rank


def quality(ids, gold, k=3):
    if not gold:
        return {"recall": None, "mrr": None, "ndcg": None, "requires_abstention": True}
    chosen = ids[:k]
    relevant = set(gold)
    recall = len(set(chosen) & relevant) / len(relevant)
    rank = next((i for i, doc_id in enumerate(ids, 1) if doc_id in relevant), None)
    dcg = sum(1 / math.log2(i + 1) for i, doc_id in enumerate(chosen, 1) if doc_id in relevant)
    ideal = sum(1 / math.log2(i + 1) for i in range(1, min(k, len(relevant)) + 1))
    return {"recall": recall, "mrr": 1 / rank if rank else 0, "ndcg": dcg / ideal, "requires_abstention": False}


def run(output: Path, *, split: str = "heldout") -> dict:
    root = Path.cwd()
    documents = [
        Document(**record)
        for record in json.loads((root / "fixtures/hybrid/corpus.json").read_text(encoding="utf-8"))
    ]
    questions = [
        question
        for question in json.loads((root / "fixtures/hybrid/questions.json").read_text(encoding="utf-8"))
        if question["split"] == split
    ]
    started = perf_counter()
    encoder = load_embedding(root / "artifacts/models")
    cross_encoder = load_reranker(root / "artifacts/models")
    vectors = [vector.tolist() for vector in encoder.embed([document.text for document in documents])]
    setup_seconds = perf_counter() - started
    rows = []
    for question in questions:
        query = question["query"]
        started = perf_counter()
        lexical = bm25_rank(documents, query)
        lexical_ms = 1000 * (perf_counter() - started)
        started = perf_counter()
        query_vector = next(encoder.query_embed(query)).tolist()
        semantic = vector_rank(documents, vectors, query_vector)
        vector_ms = 1000 * (perf_counter() - started)
        started = perf_counter()
        fused = rrf_fuse(lexical, semantic)
        fusion_ms = 1000 * (perf_counter() - started)
        started = perf_counter()
        reordered = rerank(query, fused[:6], scorer=cross_encoder.rerank)
        rerank_ms = 1000 * (perf_counter() - started)
        measurements = (
            ("bm25", lexical, lexical_ms),
            ("vector", semantic, vector_ms),
            ("rrf", fused, lexical_ms + vector_ms + fusion_ms),
            ("rerank", reordered, lexical_ms + vector_ms + fusion_ms + rerank_ms),
        )
        for name, hits, elapsed in measurements:
            ids = [hit.document.id for hit in hits]
            rows.append({
                "question": question["id"],
                "group": question["group"],
                "pipeline": name,
                "ids": ids,
                "latency_ms": elapsed,
                **quality(ids, question["gold"]),
                "model_calls": int(name in {"vector", "rrf", "rerank"}) + int(name == "rerank"),
                "failure": False,
            })
    groups = []
    for pipeline in ("bm25", "vector", "rrf", "rerank"):
        for group in sorted({row["group"] for row in rows}):
            subset = [row for row in rows if row["pipeline"] == pipeline and row["group"] == group]
            latency = sorted(row["latency_ms"] for row in subset)
            metrics = {
                metric: (
                    sum(row[metric] for row in subset if row[metric] is not None)
                    / sum(row[metric] is not None for row in subset)
                    if any(row[metric] is not None for row in subset)
                    else None
                )
                for metric in ("recall", "mrr", "ndcg")
            }
            groups.append({
                "pipeline": pipeline,
                "group": group,
                "count": len(subset),
                **metrics,
                "p50_ms": latency[math.ceil(0.5 * len(latency)) - 1],
                "p95_ms": latency[math.ceil(0.95 * len(latency)) - 1],
            })
    report = {
        "embedding": EMBEDDING,
        "reranker": RERANKER,
        "split": split,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "threads": 2,
            "corpus_size": len(documents),
            "setup_seconds": setup_seconds,
            "cache": "model cached after download; embeddings computed once",
            "cost": "local CPU; model_calls recorded, no provider charges",
        },
        "rows": rows,
        "groups": groups,
        "limitations": [
            "Tiny authored teaching corpus, not a production quality estimate",
            "Unanswerable and realtime questions require answer-layer abstention; a retriever always returns neighbors",
            "Model is primarily English; Chinese results measured separately",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(rows)} measured rows to {output}")
    return report


def benchmark(output: Path, *, split: str = "heldout") -> dict:
    """Run every pipeline and persist rows, groups, latency, and model metadata."""
    if split not in {"dev", "heldout"}:
        raise ValueError("split must be dev or heldout")
    return run(output, split=split)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the hybrid retrieval benchmark")
    parser.add_argument("--output", type=Path, default=Path("artifacts/hybrid-heldout.json"))
    parser.add_argument("--split", choices=("dev", "heldout"), default="heldout")
    args = parser.parse_args()
    benchmark(args.output, split=args.split)
