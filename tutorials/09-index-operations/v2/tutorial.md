# 索引更新与运行成本 v2：带权限和代数的查询缓存

缓存键包含租户、主体、角色、权限版本、索引 generation 和问题。文档变更后 generation 改变；撤权后 policy version 改变。两者都会使旧答案失效。

```python
hits, cached = cache.query(identity, index.generation("tenant-a"), "hello", compute)
```

运行 `test_cache_update_and_subject_scope`，检查命中只能证明同一权限边界下的同一索引版本可复用。
+

完整 v2 源码位于 `labs/operations/checkpoints/v2/index.py`，新增 `QueryCache` 并把索引 generation 和身份范围纳入键。回放导入：

```bash
uv run python -c "from labs.operations.checkpoints.v2.index import Index, QueryCache; print(Index.__module__, QueryCache.__module__)"
```
