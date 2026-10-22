# 索引更新与运行成本 v3：有界 Worker 和背压

从自己的 v2 继续，新建 `labs/operations/serving.py`，实现 `WorkerPool` 与 `Overloaded`，保持 `index.py` 的已有能力。先运行一个 worker、一个等待槽的受控异步实验，验证过载与取消释放。完整参考供逐段对照，按[学习流程](../../../docs/learning-workflow.md)保存自己的 v3。

无界并发会把慢模型变成无界队列。`WorkerPool` 分开限制 worker 数和等待队列；满载时抛出 `Overloaded`，取消任务会取消底层操作并释放槽位。

用受控的异步任务观察第三个请求在一个 worker、一个等待槽时被拒绝，取消第一个任务后第二个仍能完成。完整异步测试留到最终 API 组装后运行；这个行为是过载契约，不是“排队越多越好”。

完整 v3 参考源码位于 `reference/labs/operations/checkpoints/v3/index.py` 和 `serving.py`。它们只供对照；下面先检查你写好的主线导入，不能以可导入代替上述背压与取消实验。

```bash
uv run python -c "from labs.operations.serving import WorkerPool; print(WorkerPool.__module__)"
```
