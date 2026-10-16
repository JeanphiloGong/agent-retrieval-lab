# 权限与多租户 v3：对抗内容也必须经过边界

检索到的文档本身可能包含提示注入。`safe_context` 先做授权，再对内容执行最小的恶意标记检查；它只返回允许进入上下文的文档 ID。真正系统还需要审计、网络隔离和更完整的攻击集。

运行 `uv run python -m unittest tests.test_access`，确认 hostile 文档不会进入上下文。安全测试检查工具执行记录和实际上下文，而不是只检查模型是否说了拒绝。
+

完整 v3 源码位于 `labs/access/checkpoints/v3/control.py`，将租户、角色、缓存、授权读取、ranker 越权检查和恶意内容边界组装在一起。运行专题回放：

```bash
uv run python -m unittest tests.test_access -v
```
