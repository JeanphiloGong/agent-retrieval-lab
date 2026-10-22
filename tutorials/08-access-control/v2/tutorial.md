# 权限与多租户 v2：缓存键包含权限范围

从自己的 v1 继续修改 `labs/access/control.py`，新增带 TTL 的 `ScopedCache`，把主体、角色与权限版本纳入键。先检查同一身份命中，再更换主体或权限版本确认不能复用。完整参考供对照未展开的代码，完成后按[学习流程](../../../docs/learning-workflow.md)提交自己的 v2。

管理员的缓存结果不能被普通成员命中。`ScopedCache` 的键包含租户、主体、权限版本和查询，并带 TTL；撤权时递增 `policy_version` 即可使旧条目失效。

在自己的代码中确认相同查询不会跨主体共享结果，并对 TTL 到期和权限版本变化做同样检查。完整测试留到 v3。

完整 v2 参考源码位于 `reference/labs/access/checkpoints/v2/control.py`，包括带 TTL、主体、角色和权限版本的 `ScopedCache`。先对自己的主线做基本检查：

```bash
uv run python -c "from labs.access.control import Identity, ScopedCache; c=ScopedCache(); i=Identity('alice','tenant-a',frozenset({'reader'})); c.put(i,'q',['doc']); print(c.get(i,'q'))"
```
