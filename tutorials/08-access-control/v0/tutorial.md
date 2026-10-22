# 权限与多租户 v0：身份决定租户范围

创建空的 `labs/access/__init__.py`，在 `labs/access/control.py` 手写 `Identity`、`ProtectedDocument` 与 `visible_documents`；`labs/__init__.py` 若尚不存在也创建为空文件。本页是实现导引，完整类与函数可对照文末参考文件理解后编写。先构造两个租户和同名文档，检查结果只含当前租户；按[学习流程](../../../docs/learning-workflow.md)保存自己的 v0。

同一个文档 ID 可以在两个租户中存在。工具参数里的 `tenant` 不能成为权限来源；调用边界先接收可信 `Identity`，再按租户过滤。

```python
assert [doc.id for doc in visible_documents(alice, docs)] == ["public-a"]
```

缺失身份直接拒绝。用自己构造的租户例子确认查询字符串不能把结果切换到 tenant-b。完整专题测试留到 v3，避免早期版本为导入测试而实现未来 API。

完整 v0 参考源码位于 `reference/labs/access/checkpoints/v0/control.py`。自己的代码写好后，运行主线检查：

```bash
uv run python -c "from labs.access.control import Identity, ProtectedDocument, visible_documents; print(visible_documents(Identity('alice', 'tenant-a'), [ProtectedDocument('a', 'tenant-a', 'release')]))"
```
