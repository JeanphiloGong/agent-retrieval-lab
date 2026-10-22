# v1：工具选择

## 你要手动构建的部分

从自己的 v0 继续，在 `labs/agent/loop.py` 加入 `ToolInfo`、`ToolCall` 与单轮 `run_agent`；新建 `labs/agent/tools.py`，连接已完成的库存、代码和文档读取工具。以下是协议片段，运行前需自己定义并绑定 `inventory_tool`。完整实现可对照参考答案，主线不能导入其 checkpoint。参见[学习流程](../../../docs/learning-workflow.md)。

v0 的 `answer_once` 只能接收调用者事先挑好的工具。现实问题会同时涉及错误码、手册和实时库存；把所有输入塞给同一个搜索器会导致错误的参数和错误的数据源。

## 先把调用变成数据

本版的 `ToolInfo` 暴露名称、描述和参数类型，`ToolCall` 只表示规划器提出的调用。运行时通过名称查找注册表，找不到工具就停止并记录 `unknown_tool`。工具仍然只返回证据；模型或规划器没有执行 Python、SQL 或文件路径的权限。

```python
from labs.agent.loop import Tool, ToolCall, run_agent

class FixedPlanner:
    def decide(self, question, tool_names):
        return ToolCall("inventory_lookup", {"sku": "SKU_1"})

answer = run_agent("inventory SKU_1", (inventory_tool,), FixedPlanner())
```

完整 v1 参考 checkpoint 是 [v1/loop.py](../../../reference/labs/agent/checkpoints/v1/loop.py)。参考主线中的真实绑定位于 [tools.py](../../../reference/labs/agent/tools.py)：`lexical_tool` 调用现有 BM25，`code_tool` 调用工作区边界的 `read_range`，`inventory_tool` 调用 allow-list 查询 `get_product`。你要将相应绑定写入自己的 `tools.py`，不要接受模型提交的任意 SQL 或路径。

## 检查固定路由

先对自己的每个绑定执行固定参数调用，并补测缺失参数。以下只回放参考答案；测试模块导入最终 API，不要求你的 v1 提前完成后续循环：

```bash
PYTHONPATH=reference uv run python -P -m pytest --import-mode=importlib -q tests/test_agent.py -k 'three_fixed_routes or invalid_tool_parameters'
```

测试覆盖库存、手册、代码和 BM25 四种调用，并确认少传 `source_id` 时错误在工具边界可诊断。`ToolInfo` 是外部契约，参数校验仍由具体工具负责；这避免运行时相信规划器自己声称的类型。

## 仍然缺什么

工具选择现在只能产生一次调用，初始结果缺少附录限制时无法补证。下一版让规划器看到每次 `Observation`，继续提出下一次调用，直到它给出带已见引用的 `Finish`。
