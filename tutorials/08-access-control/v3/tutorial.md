# 权限与多租户 v3：对抗内容也必须经过边界

从自己的 v2 继续修改 `labs/access/control.py`，加入授权读取、检索前过滤、ranker 返回值校验与 `safe_context`，让恶意内容继续受原有身份边界约束。下面是范围说明，完整参考供逐段对照；实现最终 API 后再运行主线专题测试。检查与提交方法见[学习流程](../../../docs/learning-workflow.md)。

检索到的文档本身可能包含提示注入。`safe_context` 先做授权，再对内容执行最小的恶意标记检查；它只返回允许进入上下文的文档 ID。真正系统还需要审计、网络隔离和更完整的攻击集。

完成自己的最终 API 后运行专题测试，确认 hostile 文档不会进入上下文。安全测试检查工具执行记录和实际上下文，而不是只检查模型是否说了拒绝。

完整 v3 参考源码位于 `reference/labs/access/checkpoints/v3/control.py`，将租户、角色、缓存、授权读取、ranker 越权检查和恶意内容边界组装在一起。验收自己的主线：

```bash
uv run python -m pytest -q tests/test_access.py
```

单独回放参考答案使用 `PYTHONPATH=reference uv run python -P -m pytest --import-mode=importlib -q tests/test_access.py reference/tests/test_saved_checkpoints.py -k access`。它不代表个人实现通过。
