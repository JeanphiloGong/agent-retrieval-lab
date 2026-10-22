# 索引更新与运行成本 v4：同时报告质量、延迟和成本

从自己的 v3 继续，新建 `labs/operations/benchmark.py`，连接你的索引、缓存与 worker，输出固定语料下的质量和运行成本。下面命令要在报告代码写好后，从仓库根目录执行；完整参考用于对照未展开的测量逻辑。最后验收完整主线 API 并按[学习流程](../../../docs/learning-workflow.md)保存个人检查点。

平均延迟不能说明答案质量。`labs.operations.benchmark` 使用固定语料和锁定 Embedding 模型，分别测冷缓存和暖缓存，并输出 p50、p95、失败率、质量、缓存命中和删除可见延迟。

```bash
uv run python -m labs.hybrid.benchmark --output artifacts/hybrid-heldout.json
uv run python -m labs.operations.benchmark --output artifacts/operations.json
```

报告必须保存 Python、平台、并发、数据规模、模型版本和缓存状态。结果只描述本地教学负载，不能外推生产容量；过载请求进入失败分母。

自己的最终 API 组装好后，验收主线：

```bash
uv run python -m pytest -q tests/test_operations.py
```

完整 v4 参考源码位于 `reference/labs/operations/checkpoints/v4/index.py`、`serving.py` 和 `benchmark.py`。benchmark 在参考检查点包内使用同包的索引与 worker 实现。单独回放参考答案时，显式选择参考路径；运行前先准备锁定模型和固定语料：

```bash
PYTHONPATH=reference uv run python -P -m labs.operations.checkpoints.v4.benchmark --output artifacts/reference-operations.json
PYTHONPATH=reference uv run python -P -m pytest --import-mode=importlib -q tests/test_operations.py reference/tests/test_saved_checkpoints.py -k 'operation or IndexTests or PoolTests'
```

这些参考命令不会完成你的个人检查点。
