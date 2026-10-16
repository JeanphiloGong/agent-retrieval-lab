# Agent 检索循环

状态：v0-v3 已实现并通过本地重放。前置：04 v4、05 v3、06 v3；复用确定性工具契约。

实现目标：`labs/agent/loop.py`；测试目标：`tests/test_agent.py`。

- [v0：单次检索回答](v0/tutorial.md)（范围计划：[plan.md](v0/plan.md)）
- [v1：工具选择](v1/tutorial.md)（范围计划：[plan.md](v1/plan.md)）
- [v2：多轮补证](v2/tutorial.md)（范围计划：[plan.md](v2/plan.md)）
- [v3：预算与停止](v3/tutorial.md)（范围计划：[plan.md](v3/plan.md)）

每版完成后保留可重放检查点，最后一版汇总该专题已讲解的完整实现与验证边界。参见 [编写约定](../../docs/authoring.md)。
