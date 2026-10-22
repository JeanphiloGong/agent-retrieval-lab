# 索引更新与运行成本 v1：增量、删除和幂等

从自己的 v0 继续修改 `labs/operations/index.py`：加入事件修订号、同版本冲突检查与删除 tombstone。按顺序重放重复、乱序与删除后旧写入，检查最终可见内容。完整参考供对照未展开的函数，按[学习流程](../../../docs/learning-workflow.md)验证后保存个人版本。

文档事件可能重复或乱序。`Index.apply` 用 `(tenant, id, revision)` 判断：同版本同内容是幂等，旧版本被忽略，同版本不同内容拒绝，删除是带版本的 tombstone。

在自己的索引上重放重复与乱序事件，确认旧文档不会在删除后复活，同修订号的不同内容会被拒绝。对应完整测试留到最终 API 组装完成后运行。

完整 v1 参考源码位于 `reference/labs/operations/checkpoints/v1/index.py`。它只供对照；下面先检查自己的主线导入，幂等、乱序丢弃和 tombstone 删除仍需上述实际事件实验验证。

```bash
uv run python -c "from labs.operations.index import Index; print(Index.__module__)"
```
