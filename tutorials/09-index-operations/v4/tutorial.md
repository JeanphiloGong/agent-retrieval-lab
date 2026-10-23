# 索引更新与运行成本 v4：共同观察质量与服务成本

从自己的 v3 继续。把队列缩小后成功请求可能变快，但更多问题被拒绝。只看平均延迟会得出错误结论。本版把每次请求都记为 Sample，报告 QPS、p50/p95、失败率与质量；再连接本地模型向量、SQLite、缓存和 WorkerPool。

全部命令从仓库根目录执行，使用你自己的 `labs/`，沿用 `uv sync --locked` 安装的环境。检查通过后按[学习流程](../../../docs/learning-workflow.md)保存自己的版本。

## 1. 失败必须留在分母里

Sample.latency_seconds 包括排队，failed 标记服务失败，correct 表示找到了目标。report 的 quality 使用全部样本作分母，失败即使误标 correct 也不计成功；QPS 是所有完成或被拒绝的请求速率，不等于成功吞吐。cost 是调用者提供的可加总量，本地实验为 0。

`labs/operations/serving.py` — patch：在现有导入之后加入下面的导入；不要重复已有项。

```python
from dataclasses import dataclass
import math
```

`labs/operations/serving.py` — patch：将下面的完整定义追加到文件末尾，已有定义保留。

```python
@dataclass(frozen=True)
class Sample:
    latency_seconds: float
    correct: bool
    failed: bool = False
    cost: float = 0.0


def report(samples: list[Sample], elapsed: float, *, environment: dict) -> dict:
    if elapsed <= 0 or not samples:
        raise ValueError("report requires samples and positive elapsed time")
    latencies = sorted(sample.latency_seconds for sample in samples)
    percentile = lambda p: latencies[max(0, math.ceil(p * len(latencies)) - 1)]
    return {
        "requests": len(samples), "qps": len(samples) / elapsed,
        "p50": percentile(.5), "p95": percentile(.95),
        "failure_rate": sum(sample.failed for sample in samples) / len(samples),
        "quality": sum(sample.correct and not sample.failed for sample in samples) / len(samples),
        "cost": sum(sample.cost for sample in samples), "environment": environment,
    }
```

```bash
uv run python - <<'PY'
from labs.operations.serving import Sample, report

summary = report([Sample(.1, True), Sample(.5, True, failed=True)], 1,
                 environment={"cache": "cold", "workers": 1})
assert summary["quality"] == .5
assert summary["failure_rate"] == .5
assert summary["qps"] == 2
assert summary["p50"] == .1 and summary["p95"] == .5
assert summary["cost"] == 0
print("joint report denominators passed")
PY
```

预期打印 `joint report denominators passed`。故障行没有从质量或吞吐统计中消失。

```bash
uv run python -m pytest -q tests/test_operations.py
```

此时 Index、QueryCache、WorkerPool 和 report 全部齐备，8 项专题测试应通过。

## 2. 用固定问题运行真实索引和队列

新建 benchmark.py。setup 用锁定 embedding 为语料与查询生成向量，计时只覆盖 serving；TemporaryDirectory 中创建索引。cold 从空 QueryCache 开始，warm 保留此前成功请求写入的条目，因此应查看实际 cache_hits，不能假设全部预热。每个 async execute 等待 2ms 模拟 I/O，然后同步查询小索引；报告会声明这段模拟和预计算边界。

run 只把明确的 Overloaded 计入本次服务失败，其他错误直接中止实验，防止坏实现也产出可比较的成功报告。这里 quality 是 gold 任意一个出现在 top-3 的 hit rate，不是多证据 Recall@3。删除可见性在负载之外单独测量。所有 SQL 仍在一个事件循环线程执行，不声称实现并行数据库查询。

`labs/operations/benchmark.py` — checkpoint：将这个文件完整写为下面的代码。

```python
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
from labs.operations.index import Index, QueryCache
from labs.operations.serving import Overloaded, Sample, WorkerPool, report


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
```

```bash
uv run python -m labs.operations.benchmark --output artifacts/my-operations.json --workers 2 --waiting 4
```

应生成 cold/warm 两份报告与删除可见耗时。模型首次运行可能下载，已有缓存则直接加载；模型故障会使本次 benchmark 失败。

```bash
uv run python - <<'PY'
import json
from pathlib import Path

result = json.loads(Path("artifacts/my-operations.json").read_text())
assert len(result["reports"]) == 2
for row in result["reports"]:
    assert row["requests"] > 0
    assert 0 <= row["quality"] <= 1
    assert 0 <= row["failure_rate"] <= 1
    assert row["p95"] >= row["p50"] >= 0
    assert row["environment"]["workers"] == 2
    print(row["environment"]["cache"], row["cache_hits"], row["quality"], row["failure_rate"], row["qps"])
assert result["delete_visibility_seconds"] >= 0
PY
```

输出实际缓存命中、质量、失败率与 QPS，数值随机器变化，不写固定延迟断言。拥塞拒绝可能存在，应结合 failure_rate 解释吞吐。

## 本版检查点

最终 checkpoint 是 index.py、serving.py 和 benchmark.py。已经跑通持久化、增量/删除、缓存、背压与共同报告。这里只能说明小型本地负载下的行为；没有证明生产容量、多写者事务、分布式刷新或模型在线计费成本。

需要对照时可阅读[本版参考源码](../../../reference/labs/operations/benchmark.py)。自己的检查必须在 `labs/` 上通过；参考答案不会更新个人进度。
