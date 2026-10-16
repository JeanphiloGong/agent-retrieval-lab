# 索引更新与运行成本 v3：有界 Worker 和背压

无界并发会把慢模型变成无界队列。`WorkerPool` 分开限制 worker 数和等待队列；满载时抛出 `Overloaded`，取消任务会取消底层操作并释放槽位。

运行异步测试，观察第三个请求在一个 worker、一个等待槽时被拒绝，取消第一个任务后第二个仍能完成。这个行为是过载契约，不是“排队越多越好”。
+

完整 v3 源码位于 `labs/operations/checkpoints/v3/index.py` 和 `serving.py`。两个文件没有转发到最新实现，直接在检查点包中组成可运行的索引与 worker 版本。

```bash
uv run python -c "from labs.operations.checkpoints.v3.serving import WorkerPool; print(WorkerPool.__module__)"
```
