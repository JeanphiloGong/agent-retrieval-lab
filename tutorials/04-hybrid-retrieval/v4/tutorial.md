# 混合检索 v4：比较质量、耗时与模型失败

从自己的 v3 继续，使用 `fixtures/hybrid/corpus.json` 和 `questions.json`。单个改写题改善不足以证明组合有效。本版在同一固定分组上运行 BM25、vector、RRF、rerank，并生成逐题与分组报告。输出文件属于实验产物；无答案题仍需要回答层拒答。

全部命令从仓库根目录执行，使用你自己的 `labs/`，沿用 `uv sync --locked` 安装的环境。检查通过后按[学习流程](../../../docs/learning-workflow.md)保存自己的版本。

## 1. 先固定报告的分母

新建 benchmark.py。`quality` 计算 Recall@3、完整排名的 MRR 与 nDCG@3；无 gold 的问题返回 null，不能用“检索返回空”推断答案正确。`summarize` 按管线和问题组聚合，失败的可回答题以零分进入质量分母，所有失败都进入 failure_rate。p50/p95 使用最近秩法，包含失败请求耗时。

`labs/hybrid/benchmark.py` — checkpoint：将这个文件完整写为下面的代码。

```python
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
```

```bash
uv run python - <<'PY'
from labs.hybrid.benchmark import quality, summarize

assert quality(["x", "gold"], ["gold"])["mrr"] == .5
assert quality([], ["gold"])["recall"] == 0
assert quality([], [])["recall"] is None
rows = []
for pipeline in ("bm25", "vector", "rrf", "rerank"):
    for failed, ids in ((False, ["gold"]), (True, [])):
        rows.append({"pipeline": pipeline, "group": "exact", "failure": failed,
                     "latency_ms": 10 if failed else 1, **quality(ids, ["gold"])})
for group in summarize(rows):
    assert group["recall"] == .5 and group["failure_rate"] == .5
    assert group["p95_ms"] == 10
print("report denominators passed")
PY
```

预期打印 `report denominators passed`。删掉失败行会把召回率伪造为 1；此检查固定分母后再接执行器。

## 2. 连接四条管线并保留失败记录

追加 run。先读取固定数据，再分别尝试加载两个模型；模型故障记录类型名，不转成备用排名。embedding 不可用时 BM25 仍能执行，其余依赖向量的管线标为失败。reranker 不可用只影响 rerank。每题都保留四行，失败行 ids 为空且 failure=True，不能当“成功但没有答案”。文件不存在、坏 JSON 等输入错误直接报错，不伪装为模型故障。

`labs/hybrid/benchmark.py` — patch：将下面的完整定义追加到文件末尾，已有定义保留。

```python
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
```

文档向量只在 setup 阶段计算一次。查询的 vector/RRF/rerank 比较共享这次向量结果，所以各行耗时是对应阶段的累计值；setup_seconds 单独记录。model_calls 是每条管线尝试的查询推理次数，不包含模型加载和语料编码，不应将共享阶段的四行相加当作实际总调用数。故障类型保存在 error，加载阶段故障还在 setup_errors。

```bash
uv run python -m pytest -q tests/test_hybrid_benchmark.py
```

5 项检查应通过：模型加载、查询编码与重排故障均生成报告，失败保留在分母中。测试通过明确注入固定模型检查报告控制流，不替代真实质量测量。

## 3. 提供命令行并生成自己的测量

最后追加命令行入口。`--split` 限定 dev/heldout，避免拼错后生成空报告。输出报告记录确切模型 revision、系统环境、缓存方式和样本量。

`labs/hybrid/benchmark.py` — patch：将下面的完整定义追加到文件末尾，已有定义保留。

```python
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("artifacts/hybrid-heldout.json"))
    parser.add_argument("--split", choices=["dev", "heldout"], default="heldout")
    arguments = parser.parse_args()
    run(arguments.output, split=arguments.split)
```

```bash
uv run python -m labs.hybrid.benchmark --output artifacts/my-hybrid-heldout.json --split heldout
```

应生成每题四行的 JSON 报告；有模型故障时仍生成带 failure/error 的报告。命令退出成功只说明报告已写出，必须继续检查故障字段。

```bash
uv run python - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("artifacts/my-hybrid-heldout.json").read_text())
questions = [q for q in json.loads(Path("fixtures/hybrid/questions.json").read_text()) if q["split"] == "heldout"]
assert len(report["rows"]) == 4 * len(questions)
assert all("failure_rate" in group for group in report["groups"])
print("setup errors:", report["setup_errors"])
for group in report["groups"]:
    print(group["pipeline"], group["group"], group["count"], group["recall"], group["failure_rate"])
assert not any(row["failure"] for row in report["rows"]), "resolve model failures before comparing quality"
PY
```

正常模型环境下最后断言通过；若失败，先依据 setup_errors/error 修复模型运行，再比较质量。记录精确码、改写、中文及无答案组的差异，不以平均分抹掉退步。

## 本版检查点

完整 checkpoint 是保留的 retrieval.py、models.py 和本版三段组成的 benchmark.py。报告能区分检索质量、故障和耗时；这份小样本不能推断生产 QPS，也没有实现答案正确性判断。后续 05 复用这些检索函数比较结构导航。

需要对照时可阅读[本版参考源码](../../../reference/labs/hybrid/benchmark.py)。自己的检查必须在 `labs/` 上通过；参考答案不会更新个人进度。
