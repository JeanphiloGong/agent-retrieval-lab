# 索引更新与运行成本 v1：增量、删除和幂等

文档事件可能重复或乱序。`Index.apply` 用 `(tenant, id, revision)` 判断：同版本同内容是幂等，旧版本被忽略，同版本不同内容拒绝，删除是带版本的 tombstone。

运行 `test_duplicate_and_out_of_order_delete` 和 `test_conflicting_same_revision_rejected`，确认旧文档不会在删除后复活。
+

完整 v1 源码位于 `labs/operations/checkpoints/v1/index.py`。重放同一文件即可观察带修订号事件的幂等、乱序丢弃和 tombstone 删除。

```bash
uv run python -c "from labs.operations.checkpoints.v1.index import Index; print(Index.__module__)"
```
