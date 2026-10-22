"""Measure cold/warm serving with real queries and isolated temporary storage."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import platform
import tempfile
from time import perf_counter

from labs.access.control import Identity
from labs.hybrid.models import EMBEDDING, load_embedding
from labs.hybrid.retrieval import Document
from .index import Index, QueryCache
from .serving import Overloaded, Sample, WorkerPool, report


async def run(output: Path, workers: int = 2, waiting: int = 4):
    root = Path.cwd()
    docs = [Document(**row) for row in json.loads((root/"fixtures/hybrid/corpus.json").read_text())]
    questions = [row for row in json.loads((root/"fixtures/hybrid/questions.json").read_text()) if row["gold"]]
    encoder = load_embedding(root/"artifacts/models")
    vectors = [vector.tolist() for vector in encoder.embed([doc.text for doc in docs])]
    query_vectors = {q["query"]: next(encoder.query_embed(q["query"])).tolist() for q in questions}
    identity = Identity("benchmark", "lab")
    summaries = []
    with tempfile.TemporaryDirectory() as directory:
        index = Index(Path(directory)/"index.sqlite", ":".join(EMBEDDING), "authored-v1")
        for doc, vector in zip(docs, vectors):
            index.apply("lab", doc.id, 1, doc.text, vector)
        cache = QueryCache(32)
        for mode in ("cold", "warm"):
            samples = []
            pool = WorkerPool(workers, waiting)
            async def query(question):
                start = perf_counter()
                async def execute():
                    await asyncio.sleep(.002)
                    hits, hit = cache.query(identity, index.generation("lab"), question["query"], lambda: index.search(identity, query_vectors[question["query"]], 3))
                    return hits, hit
                try:
                    hits, cached = await pool.submit(execute)
                    correct = bool({hit.document.id for hit in hits} & set(question["gold"]))
                    sample = Sample(perf_counter()-start, correct, cost=0)
                    samples.append((sample, cached))
                except Overloaded:
                    samples.append((Sample(perf_counter()-start, False, True), False))
            started = perf_counter()
            await asyncio.gather(*(query(q) for q in questions))
            elapsed = perf_counter()-started
            await pool.close()
            result = report([sample for sample, _ in samples], elapsed, environment={
                "python":platform.python_version(), "platform":platform.platform(), "cache":mode,
                "workers":workers,"waiting":waiting,"concurrency":len(questions),"documents":len(docs),
                "embedding":EMBEDDING,"query_embeddings":"precomputed before timed serving",
                "simulated_io_seconds":.002,"cost":"local CPU; no billed model calls in serving",
            })
            result["cache_hits"] = sum(cached for _, cached in samples)
            summaries.append(result)
        # Deletion visibility is measured independently of answer latency.
        started = perf_counter()
        index.apply("lab", docs[0].id, 2, None)
        remaining = index.search(identity, vectors[0], 100)
        assert docs[0].id not in {hit.document.id for hit in remaining}
        delete_visibility = perf_counter()-started
        index.close()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"reports":summaries,"delete_visibility_seconds":delete_visibility,
        "limitations":["Small local teaching load, not a production capacity estimate","Queries use fixed embeddings; report excludes encoder latency","Overload counts in quality and failure denominator"]},indent=2)+"\n")
    print(f"Wrote serving and deletion measurements to {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,default=Path("artifacts/operations.json"))
    parser.add_argument("--workers",type=int,default=2)
    parser.add_argument("--waiting",type=int,default=4)
    args = parser.parse_args()
    asyncio.run(run(args.output,args.workers,args.waiting))
