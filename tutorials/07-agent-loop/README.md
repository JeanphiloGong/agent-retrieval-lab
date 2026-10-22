# Agent 检索循环

资料状态：v0-v3 的教程、参考代码与测试已准备；你的实现从 v0 开始。前置：04 v4、05 v3、06 v3；复用确定性工具契约。

你的实现目标：`labs/agent/loop.py`，逐步增加 `tools.py`、`planner.py`、`demo.py`；参考答案：`reference/labs/agent/`；测试材料：`tests/test_agent.py`。先读[手动构建流程](../../docs/learning-workflow.md)。

- [v0：单次检索回答](v0/tutorial.md)（范围计划：[plan.md](v0/plan.md)）
- [v1：工具选择](v1/tutorial.md)（范围计划：[plan.md](v1/plan.md)）
- [v2：多轮补证](v2/tutorial.md)（范围计划：[plan.md](v2/plan.md)）
- [v3：预算与停止](v3/tutorial.md)（范围计划：[plan.md](v3/plan.md)）

每版修改自己的文件并提交 Git 检查点，预写参考代码通过显式命令单独回放。现有测试导入最终循环和工具 API，早期版本先用本版小例子检查，v3 再验收整个专题。参考回放通过不会增加你的学习进度。参见[编写约定](../../docs/authoring.md)。
