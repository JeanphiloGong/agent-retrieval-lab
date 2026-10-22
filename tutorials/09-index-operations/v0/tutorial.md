# 索引更新与运行成本 v0：让索引能重启

创建空的 `labs/operations/__init__.py`，在 `labs/operations/index.py` 手写 `Index` 的 SQLite schema、配置校验、写入与读取；`labs/__init__.py` 若尚不存在也创建为空文件。本页是实现导引，完整实现可对照文末参考源码逐段编写。先用临时数据库写入、关闭、重开并读取，再按[学习流程](../../../docs/learning-workflow.md)保存自己的 v0。

进程内的向量列表在重启后消失。`Index` 把来源版本、分块版本、文本和向量写入 SQLite；打开一个不匹配的模型或分块版本会拒绝静默复用旧索引。

```python
index = Index(Path("index.sqlite"), "model-v1", "chunk-v1")
index.apply("tenant-a", "doc-1", 1, "hello", [1, 0])
```

关闭后重新打开并查询，确认自己的数据仍然存在；更换模型配置应拒绝复用。完整测试 `test_restart_and_configuration_guard` 留到 v4，避免测试模块的最终 API 导入阻碍 v0。配置变化必须显式重建。

完整 v0 参考源码位于 `reference/labs/operations/checkpoints/v0/index.py`，只包含持久化索引和配置版本检查。自己的文件写好后，先确认主线可导入，再执行上述临时数据库实验：

```bash
uv run python -c "from labs.operations.index import Index; print(Index.__module__)"
```
