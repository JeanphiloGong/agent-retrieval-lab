# v1：工具选择

v0 的 `answer_once` 只能接收调用者事先挑好的工具。现实问题会同时涉及错误码、手册和实时库存；把所有输入塞给同一个搜索器会导致错误的参数和错误的数据源。

## 先把调用变成数据

本版的 `ToolInfo` 暴露名称、描述和参数类型，`ToolCall` 只表示规划器提出的调用。运行时通过名称查找注册表，找不到工具就停止并记录 `unknown_tool`。工具仍然只返回证据；模型或规划器没有执行 Python、SQL 或文件路径的权限。

```python
from labs.agent.checkpoints.v1.loop import Tool, ToolCall, run_agent

class FixedPlanner:
    def decide(self, question, tool_names):
        return ToolCall("inventory_lookup", {"sku": "SKU_1"})

answer = run_agent("inventory SKU_1", (inventory_tool,), FixedPlanner())
```

仓库的完整 v1 checkpoint 是 [v1/loop.py](../../../labs/agent/checkpoints/v1/loop.py)。当前实现中的真实绑定位于 [tools.py](../../../labs/agent/tools.py)：`lexical_tool` 调用现有 BM25，`code_tool` 调用工作区边界的 `read_range`，`inventory_tool` 调用 allow-list 查询 `get_product`。没有接受模型提交的任意 SQL 或路径。

## 检查固定路由

```bash
uv run python -m unittest tests.test_agent.AgentTests.test_three_fixed_routes_use_real_tools
uv run python -m unittest tests.test_agent.AgentTests.test_invalid_tool_parameters_are_diagnostic
```

测试覆盖库存、手册、代码和 BM25 四种调用，并确认少传 `source_id` 时错误在工具边界可诊断。`ToolInfo` 是外部契约，参数校验仍由具体工具负责；这避免运行时相信规划器自己声称的类型。

## 仍然缺什么

工具选择现在只能产生一次调用，初始结果缺少附录限制时无法补证。下一版让规划器看到每次 `Observation`，继续提出下一次调用，直到它给出带已见引用的 `Finish`。
