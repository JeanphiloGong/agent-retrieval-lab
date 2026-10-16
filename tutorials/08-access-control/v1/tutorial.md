# 权限与多租户 v1：检索前执行文档授权

同租户也有角色边界。`ProtectedDocument.roles` 是读取文档的要求，`authorize` 在检索前执行；未授权文本不会进入候选列表，也不会进入重排。

运行 `test_tenant_and_role_are_both_required`，比较 reader 和 finance 身份的可见集合。提示词不能替代这个边界。
+

完整 v1 源码位于 `labs/access/checkpoints/v1/control.py`。它在 v0 的租户边界上增加角色集合，运行：

```bash
uv run python -c "from labs.access.checkpoints.v1.control import Identity, ProtectedDocument, authorize; print(authorize(Identity('alice', 'tenant-a', frozenset({'reader'})), ProtectedDocument('finance', 'tenant-a', 'report', frozenset({'finance'}))))"
```

输出 `False`，说明未授权文档在检索前被排除。
