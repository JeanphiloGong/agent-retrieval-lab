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


def summarize(rows: list[dict]) -> list[dict]:
    groups = []
    for pipeline in ("bm25", "vector", "rrf", "rerank"):
        for group in sorted({row["group"] for row in rows}):
            subset = [row for row in rows if row["pipeline"] == pipeline and row["group"] == group]
            latency = sorted(row["latency_ms"] for row in subset)
            metrics = {}
            for metric in ("recall", "mrr", "ndcg"):
                values = [row[metric] for row in subset if row[metric] is not None]
                metrics[metric] = sum(values) / len(values) if values else None
            groups.append({
                "pipeline": pipeline, "group": group, "count": len(subset), **metrics,
                "failure_rate": sum(row["failure"] for row in subset) / len(subset),
                "p50_ms": latency[math.ceil(.5 * len(latency)) - 1],
                "p95_ms": latency[math.ceil(.95 * len(latency)) - 1],
            })
    return groups


def run(output: Path, *, split: str = "heldout"):
    if split not in {"dev", "heldout"}:
        raise ValueError("unknown split")
    root = Path.cwd()
    docs = [Document(**record) for record in json.loads((root / "fixtures/hybrid/corpus.json").read_text())]
    questions = [q for q in json.loads((root / "fixtures/hybrid/questions.json").read_text()) if q["split"] == split]
    start = perf_counter()
    setup_errors: dict[str, str] = {}
    encoder = cross_encoder = None
    vectors = []
    try:
        encoder = load_embedding(root / "artifacts/models")
        vectors = [list(vector) for vector in encoder.embed([doc.text for doc in docs])]
    except Exception as exc:
        setup_errors["embedding"] = type(exc).__name__
    try:
        cross_encoder = load_reranker(root / "artifacts/models")
    except Exception as exc:
        setup_errors["reranker"] = type(exc).__name__
    setup_seconds = perf_counter() - start
    rows = []
    for question in questions:
        query = question["query"]
        started = perf_counter()
        lexical = bm25_rank(docs, query)
        lexical_ms = 1000 * (perf_counter() - started)
        semantic, fused, reordered = [], [], []
        vector_error = setup_errors.get("embedding")
        rerank_error = setup_errors.get("reranker")
        vector_calls = reranker_calls = 0
        started = perf_counter()
        if vector_error is None:
            try:
                vector_calls = 1
                query_vector = list(next(encoder.query_embed(query)))
                semantic = vector_rank(docs, vectors, query_vector)
            except Exception as exc:
                vector_error = type(exc).__name__
        vector_ms = 1000 * (perf_counter() - started)
        started = perf_counter()
        fusion_error = vector_error
        if fusion_error is None:
            try:
                fused = rrf_fuse(lexical, semantic)
            except Exception as exc:
                fusion_error = type(exc).__name__
        fusion_ms = 1000 * (perf_counter() - started)
        started = perf_counter()
        rerank_error = fusion_error or rerank_error
        if rerank_error is None:
            try:
                reranker_calls = 1
                reordered = rerank(query, fused[:6], scorer=cross_encoder.rerank)
            except Exception as exc:
                rerank_error = type(exc).__name__
        rerank_ms = 1000 * (perf_counter() - started)
        results = [
            ("bm25", lexical, lexical_ms, None, 0),
            ("vector", semantic, vector_ms, vector_error, vector_calls),
            ("rrf", fused, lexical_ms + vector_ms + fusion_ms, fusion_error, vector_calls),
            ("rerank", reordered, lexical_ms + vector_ms + fusion_ms + rerank_ms,
             rerank_error, vector_calls + reranker_calls),
        ]
        for name, hits, elapsed, error, calls in results:
            ids = [hit.document.id for hit in hits] if error is None else []
            rows.append({
                "question": question["id"], "group": question["group"], "pipeline": name,
                "ids": ids, "latency_ms": elapsed, **quality(ids, question["gold"]),
                "model_calls": calls, "failure": error is not None, "error": error,
            })
    report = {
        "embedding": EMBEDDING, "reranker": RERANKER, "split": split,
        "environment": {
            "python": platform.python_version(), "platform": platform.platform(), "threads": 2,
            "corpus_size": len(docs), "setup_seconds": setup_seconds,
            "cache": "Hugging Face disk cache; document embeddings attempted once in setup",
            "cost": "local CPU; model_calls counts attempted query inference per pipeline, excluding setup",
        },
        "setup_errors": setup_errors, "rows": rows, "groups": summarize(rows),
        "limitations": [
            "Tiny authored teaching corpus, not a production quality estimate",
            "No-gold questions need answer-layer abstention; recall/MRR/nDCG are null",
            "Failed answerable queries score zero and remain in quality/failure denominators",
            "Model is primarily English; Chinese results measured separately",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(f"Wrote {len(rows)} measured rows to {output}")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("artifacts/hybrid-heldout.json"))
    parser.add_argument("--split", choices=["dev", "heldout"], default="heldout")
    arguments = parser.parse_args()
    run(arguments.output, split=arguments.split)
