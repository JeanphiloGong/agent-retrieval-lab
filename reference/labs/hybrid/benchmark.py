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
    dcg = sum(1/math.log2(i+1) for i, doc_id in enumerate(chosen, 1) if doc_id in relevant)
    ideal = sum(1/math.log2(i+1) for i in range(1, min(k, len(relevant))+1))
    return {"recall": recall, "mrr": 1/rank if rank else 0, "ndcg": dcg/ideal, "requires_abstention": False}


def run(output: Path, *, split: str = "heldout"):
    root = Path.cwd()
    docs = [Document(**record) for record in json.loads((root/"fixtures/hybrid/corpus.json").read_text())]
    questions = [q for q in json.loads((root/"fixtures/hybrid/questions.json").read_text()) if q["split"] == split]
    start = perf_counter()
    encoder = load_embedding(root/"artifacts/models")
    cross_encoder = load_reranker(root/"artifacts/models")
    vectors = [v.tolist() for v in encoder.embed([doc.text for doc in docs])]
    setup_seconds = perf_counter()-start
    rows = []
    for question in questions:
        query = question["query"]
        started = perf_counter()
        lexical = bm25_rank(docs, query)
        lexical_ms = 1000*(perf_counter()-started)
        started = perf_counter()
        q_vector = next(encoder.query_embed(query)).tolist()
        semantic = vector_rank(docs, vectors, q_vector)
        vector_ms = 1000*(perf_counter()-started)
        started = perf_counter()
        fused = rrf_fuse(lexical, semantic)
        fusion_ms = 1000*(perf_counter()-started)
        started = perf_counter()
        reordered = rerank(query, fused[:6], scorer=cross_encoder.rerank)
        rerank_ms = 1000*(perf_counter()-started)
        for name, hits, elapsed in [("bm25",lexical,lexical_ms),("vector",semantic,vector_ms),("rrf",fused,lexical_ms+vector_ms+fusion_ms),("rerank",reordered,lexical_ms+vector_ms+fusion_ms+rerank_ms)]:
            ids = [hit.document.id for hit in hits]
            rows.append({"question":question["id"],"group":question["group"],"pipeline":name,"ids":ids,"latency_ms":elapsed,**quality(ids,question["gold"]),"model_calls": int(name in {"vector","rrf","rerank"})+int(name=="rerank"),"failure":False})
    grouped = []
    for pipeline in ("bm25","vector","rrf","rerank"):
        for group in sorted({row["group"] for row in rows}):
            subset = [row for row in rows if row["pipeline"]==pipeline and row["group"]==group]
            latency = sorted(row["latency_ms"] for row in subset)
            metrics = {metric: sum(row[metric] for row in subset if row[metric] is not None)/sum(row[metric] is not None for row in subset) if any(row[metric] is not None for row in subset) else None for metric in ("recall","mrr","ndcg")}
            grouped.append({"pipeline":pipeline,"group":group,"count":len(subset),**metrics,"p50_ms":latency[math.ceil(.5*len(latency))-1],"p95_ms":latency[math.ceil(.95*len(latency))-1]})
    report = {"embedding":EMBEDDING,"reranker":RERANKER,"split":split,"environment":{"python":platform.python_version(),"platform":platform.platform(),"threads":2,"corpus_size":len(docs),"setup_seconds":setup_seconds,"cache":"model cached after download; embeddings computed once","cost":"local CPU; model_calls recorded, no provider charges"},"rows":rows,"groups":grouped,"limitations":["Tiny authored teaching corpus, not a production quality estimate","Unanswerable and realtime questions require answer-layer abstention; a retriever always returns neighbors","Model is primarily English; Chinese results measured separately"]}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    print(f"Wrote {len(rows)} measured rows to {output}")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,default=Path("artifacts/hybrid-heldout.json"))
    parser.add_argument("--split",choices=["dev","heldout"],default="heldout")
    arguments = parser.parse_args()
    run(arguments.output,split=arguments.split)
