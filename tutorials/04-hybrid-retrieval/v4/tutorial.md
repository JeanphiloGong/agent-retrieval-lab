# 混合检索 v4：用消融实验决定组合

## 你要手动构建的部分

从自己的 v3 继续，新建 `labs/hybrid/benchmark.py`，连接固定问题集、锁定模型、各条检索管线和报告输出。下面的小函数只演示组合关系，不是完整 benchmark；完整报告字段与实现可对照 `reference/labs/hybrid/benchmark.py`。全部命令从仓库根目录执行，按[学习流程](../../../docs/learning-workflow.md)用自己的结果冻结本版。

单个查询改善不能证明系统改善。固定一组精确码、语义改写、中文问题和无答案问题，分别运行 BM25、向量、RRF 和重排组合，报告每组的 Recall@k、MRR、证据命中率与耗时。

```python
from labs.hybrid.retrieval import Document, HashEmbedding, bm25_rank, rrf_fuse, rerank

def pipeline(documents, question):
    lexical = bm25_rank(documents, question)
    semantic = HashEmbedding().rank(documents, question)
    return rerank(question, rrf_fuse(lexical, semantic))
```

不要把平均分写成唯一结论：精确错误码可能需要词法召回，改写问题可能需要向量，长文档和否定条件可能需要重排。测试数据、模型配置、缓存状态和硬件必须随报告保存；模型失败要进入失败率而不是变成空的成功结果。

参考回放入口位于 [`reference/labs/hybrid/checkpoints/v4_benchmark.py`](../../../reference/labs/hybrid/checkpoints/v4_benchmark.py)，完整测量代码在参考 `benchmark.py` 中。自己的实现组装好后，先验收主线：

```bash
uv run python -m pytest -q tests/test_hybrid.py
uv run python -m labs.hybrid.benchmark --output artifacts/my-hybrid-heldout.json --split heldout
```

以下是独立的参考答案回放，不代表你已通过上述个人验收：

```bash
PYTHONPATH=reference uv run python -P -m labs.hybrid.checkpoints.v4_benchmark \
  --output artifacts/hybrid-heldout.json --split heldout
PYTHONPATH=reference uv run python -P -m pytest --import-mode=importlib -q tests/test_hybrid.py reference/tests/test_hybrid_checkpoints.py
```

报告保存每题每管线行、分组 Recall/MRR/nDCG、p50/p95、模型 revision、环境和失败字段。这个版本完成本专题的可运行基线，但小型样例不能预测生产 QPS 或模型收益。
