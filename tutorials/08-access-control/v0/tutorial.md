# 权限与多租户 v0：身份决定租户范围

同一个文档 ID 可以在两个租户中存在。工具参数里的 `tenant` 不能成为权限来源；调用边界先接收可信 `Identity`，再按租户过滤。

```python
assert [doc.id for doc in visible_documents(alice, docs)] == ["public-a"]
```

缺失身份直接拒绝。运行租户测试，确认查询字符串不能把结果切换到 tenant-b。
+

完整 v0 源码位于 `labs/access/checkpoints/v0/control.py`，可独立重放：

```bash
uv run python -c "from labs.access.checkpoints.v0.control import Identity, ProtectedDocument, visible_documents; print(visible_documents(Identity('alice', 'tenant-a'), [ProtectedDocument('a', 'tenant-a', 'release')]))"
```
