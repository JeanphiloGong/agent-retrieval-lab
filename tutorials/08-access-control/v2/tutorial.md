# 权限与多租户 v2：缓存键包含权限范围

管理员的缓存结果不能被普通成员命中。`ScopedCache` 的键包含租户、主体、权限版本和查询，并带 TTL；撤权时递增 `policy_version` 即可使旧条目失效。

运行 `test_cache_is_scoped_to_subject_and_policy`，确认相同查询不会跨主体共享结果。
+

完整 v2 源码位于 `labs/access/checkpoints/v2/control.py`，包括带 TTL、主体、角色和权限版本的 `ScopedCache`。直接重放：

```bash
uv run python -c "from labs.access.checkpoints.v2.control import Identity, ScopedCache; c=ScopedCache(); i=Identity('alice','tenant-a',frozenset({'reader'})); c.put(i,'q',['doc']); print(c.get(i,'q'))"
```
