# 混合检索 v4：用消融实验决定组合

单个查询改善不能证明系统改善。固定一组精确码、语义改写、中文问题和无答案问题，分别运行 BM25、向量、RRF 和重排组合，报告每组的 Recall@k、MRR、证据命中率与耗时。

```python
from labs.hybrid.retrieval import Document, HashEmbedding, bm25_rank, rrf_fuse, rerank

def pipeline(documents, question):
    lexical = bm25_rank(documents, question)
    semantic = HashEmbedding().rank(documents, question)
    return rerank(question, rrf_fuse(lexical, semantic))
```

不要把平均分写成唯一结论：精确错误码可能需要词法召回，改写问题可能需要向量，长文档和否定条件可能需要重排。测试数据、模型配置、缓存状态和硬件必须随报告保存；模型失败要进入失败率而不是变成空的成功结果。

完整 checkpoint 位于 [`labs/hybrid/checkpoints/v4_benchmark.py`](../../../labs/hybrid/checkpoints/v4_benchmark.py)。运行真实模型评测：

```bash
uv run python -m labs.hybrid.checkpoints.v4_benchmark \
  --output artifacts/hybrid-heldout.json --split heldout
uv run python -m pytest -q tests/test_hybrid.py tests/test_hybrid_checkpoints.py
```

报告保存每题每管线行、分组 Recall/MRR/nDCG、p50/p95、模型 revision、环境和失败字段。这个版本完成本专题的可运行基线，但小型样例不能预测生产 QPS 或模型收益。
