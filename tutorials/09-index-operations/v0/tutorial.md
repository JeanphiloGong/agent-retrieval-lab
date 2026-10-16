# 索引更新与运行成本 v0：让索引能重启

进程内的向量列表在重启后消失。`Index` 把来源版本、分块版本、文本和向量写入 SQLite；打开一个不匹配的模型或分块版本会拒绝静默复用旧索引。

```python
index = Index(Path("index.sqlite"), "model-v1", "chunk-v1")
index.apply("tenant-a", "doc-1", 1, "hello", [1, 0])
```

关闭后重新打开并查询，运行 `test_restart_and_configuration_guard`。旧索引能重放，配置变化必须显式重建。
+

完整 v0 源码位于 `labs/operations/checkpoints/v0/index.py`，只包含持久化索引和配置版本检查。可以确认它是独立模块：

```bash
uv run python -c "from labs.operations.checkpoints.v0.index import Index; print(Index.__module__)"
```
