# 索引更新与运行成本 v2：带权限和代数的查询缓存

从自己的 v1 继续修改 `labs/operations/index.py`，新增 `QueryCache`，在索引变更时更新租户 generation。用相同查询检查缓存命中，再修改索引或身份确认旧结果失效。完整参考只供对照，检查与个人提交见[学习流程](../../../docs/learning-workflow.md)。

缓存键包含租户、主体、角色、权限版本、索引 generation 和问题。文档变更后 generation 改变；撤权后 policy version 改变。两者都会使旧答案失效。

```python
hits, cached = cache.query(identity, index.generation("tenant-a"), "hello", compute)
```

在自己的代码中检查命中、索引更新后未命中、跨主体未命中；完整测试 `test_cache_update_and_subject_scope` 留到最终 API 组装后运行。命中只能证明同一权限边界下的同一索引版本可复用。

完整 v2 参考源码位于 `reference/labs/operations/checkpoints/v2/index.py`，新增 `QueryCache` 并把索引 generation 和身份范围纳入键。写好后检查自己的主线可导入，再执行缓存变化实验：

```bash
uv run python -c "from labs.operations.index import Index, QueryCache; print(Index.__module__, QueryCache.__module__)"
```
