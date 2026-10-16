# 索引更新与运行成本 v4：同时报告质量、延迟和成本

平均延迟不能说明答案质量。`labs.operations.benchmark` 使用固定语料和锁定 Embedding 模型，分别测冷缓存和暖缓存，并输出 p50、p95、失败率、质量、缓存命中和删除可见延迟。

```bash
uv run python -m labs.hybrid.benchmark --output artifacts/hybrid-heldout.json
uv run python -m labs.operations.benchmark --output artifacts/operations.json
```

报告必须保存 Python、平台、并发、数据规模、模型版本和缓存状态。结果只描述本地教学负载，不能外推生产容量；过载请求进入失败分母。
+

完整 v4 源码位于 `labs/operations/checkpoints/v4/index.py`、`serving.py` 和 `benchmark.py`。benchmark 在检查点包内使用同包的索引与 worker 实现；运行前先准备锁定模型和固定语料：

```bash
uv run python -c "from labs.operations.checkpoints.v4.benchmark import run; print(run.__module__)"
```
