# v3：预算与停止原因

v2 的循环可能反复请求同一个来源，或者在工具返回很大文本后耗尽上下文。现在运行时负责资源边界，规划器只能提出动作。

## 四个预算

当前 [loop.py](../../../labs/agent/loop.py) 的 `run_agent` 接受：

```python
run_agent(
    question,
    tools,
    planner,
    max_steps=8,
    max_seconds=5.0,
    max_read_bytes=65536,
    max_evidence=16,
)
```

`max_steps` 计算规划器调用次数，包括最后一次 `Finish`；`max_read_bytes` 是工具结果累计 UTF-8 字节数；`max_evidence` 限制去重后的证据条数。每次规划前后和工具返回后都检查 `max_seconds`。同步工具被卡住时，合作式检查无法中断它，生产环境仍需给数据库、HTTP 或子进程设置自身超时。

停止原因是数据的一部分：`answered`、`no_evidence`、`step_budget`、`time_budget`、`read_budget`、`evidence_budget`、`duplicate_tool_call`、`unknown_tool`、`tool_error` 和 `invalid_citation`。调用方不能把所有失败都显示成“没有结果”。

## 反例先行

```bash
uv run python -m unittest tests.test_agent.AgentTests.test_duplicate_call_stops_before_second_execution
uv run python -m unittest tests.test_agent.AgentTests.test_step_limit_is_reachable_after_actual_tool_call
uv run python -m unittest tests.test_agent.AgentTests.test_read_and_evidence_limits_are_reachable
uv run python -m unittest tests.test_agent.AgentTests.test_time_limit_after_tool_discards_unfinished_answer
```

这些测试使用脚本规划器和可控时钟，因此不依赖真实网络延迟。重复调用在第二次执行前停止；工具返回超过剩余字节预算时，过大的结果不会进入证据上下文；工具执行后发现时间已耗尽时，运行时不会返回一个看似完整的答案。

## 引用是运行时不变量

`Evidence.citation` 由来源、版本、定位符和文本摘要组成。`Finish` 的每个引用必须出现在运行时保存的证据中；可回答答案没有引用，或引用伪造摘要，都会变成 `invalid_citation`。工具参数在 [tools.py](../../../labs/agent/tools.py) 中再次校验，代码工具继续复用工作区边界和行范围检查，库存工具继续使用参数化 allow-list 查询。

完整 v3 文件保存在 [checkpoints/v3](../../../labs/agent/checkpoints/v3)：

```text
loop.py       # 循环、预算、Observation、引用校验
planner.py    # 可重放的确定性多轮策略
tools.py      # BM25、代码读取、SQLite 工具绑定
```

执行完整检查：

```bash
uv run python -m unittest tests.test_agent
uv run python -m labs.agent.demo --max-steps 1
```

第一条命令验证正常路径、四类预算、坏工具结果、越权路径和恶意文档；第二条命令应返回 `step_budget`，因为一次检索后还没有机会完成第二次规划。

## 边界和下一步

这是一个确定性 Planner 协议，不是假装已经接入模型。接入 OpenAI 或其他模型时，只需把其结构化输出解析为 `ToolCall` 或 `Finish`，仍由此运行时执行工具和验证引用。模型不能通过自由文本改变租户、路径、SQL 或预算。下一专题可以在同一协议上加入 Agent 评测与真实模型回放，但必须保留本版的固定工具轨迹作为回归基线。
