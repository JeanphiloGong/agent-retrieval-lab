# 权限与多租户 v1：检索前执行文档授权

从自己的 v0 继续修改 `labs/access/control.py`：为身份与文档加入角色集合，实现 `authorize` 并让可见文档入口先授权后检索。以下是契约与调用例子，完整参考只供对照。写好后检查 reader 不能读取 finance 文档，再按[学习流程](../../../docs/learning-workflow.md)保存个人版本。

同租户也有角色边界。`ProtectedDocument.roles` 是读取文档的要求，`authorize` 在检索前执行；未授权文本不会进入候选列表，也不会进入重排。

比较你自己代码中 reader 和 finance 身份的可见集合。完整测试 `test_tenant_and_role_are_both_required` 留到 v3；提示词不能替代这个边界。

完整 v1 参考源码位于 `reference/labs/access/checkpoints/v1/control.py`。它在 v0 的租户边界上增加角色集合；自己的代码写好后，运行：

```bash
uv run python -c "from labs.access.control import Identity, ProtectedDocument, authorize; print(authorize(Identity('alice', 'tenant-a', frozenset({'reader'})), ProtectedDocument('finance', 'tenant-a', 'report', frozenset({'finance'}))))"
```

输出 `False`，说明未授权文档在检索前被排除。
