# v0：单次检索回答

用户已经能手工看到检索结果，但知识助手必须给出一个可核验的结论。最小压力是：一次查询找到错误码说明时，回答应携带来源；查不到时，应明确拒答。

## 把问题压缩到一次工具调用

本版不引入模型、不让答案自由编造，也不支持多轮。工具的唯一输出是 `Evidence(source_id, text)`，`answer_once` 只选择第一条证据并把所有证据的身份转为引用。它有两个可观察结果：`answered` 和 `no_evidence`。

```python
from labs.agent.checkpoints.v0.loop import Evidence, Tool, answer_once

search = Tool(
    "search",
    lambda arguments: (Evidence("errors@v1:line:2", "E104 means connection timeout."),)
    if arguments["query"] == "E104" else (),
)
answer = answer_once("E104", search, {"query": "E104"})
assert answer.answerable
assert answer.citations == ("errors@v1:line:2",)
```

如果工具返回空元组，`answer_once` 返回说明性拒答而不是空字符串。这个检查点建立了最小回答契约：有证据才回答，引用来自工具结果。

## 代码变更和检查

这是从调用者输入开始的 `checkpoint`，完整文件在 [v0/loop.py](../../../labs/agent/checkpoints/v0/loop.py)。它刻意把工具函数作为参数传入，调用者可以用固定函数重放，不需要网络凭据。

```bash
uv run python -m unittest tests.test_agent.AgentTests.test_single_tool_answer_has_resolvable_citation
uv run python -m unittest tests.test_agent.AgentTests.test_no_evidence_is_refusal_not_empty_text
```

这两个测试证明正常和无答案路径。它们没有证明工具本身检索质量，也没有证明引用的行范围存在；那属于前面评测专题和后续版本的边界。

## 仍然缺什么

所有问题都只能交给一个已选工具，工具参数也没有公开契约。错误码、手册和库存需要不同的输入。下一版只增加工具名称、描述和显式参数，先让选择行为可观察。
