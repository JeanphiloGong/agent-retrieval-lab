# v2：多轮补证

## 你要手动构建的部分

从自己的 v1 继续，在 `labs/agent/loop.py` 加入 `Observation`、`Finish`、多轮循环与已见引用校验；在 `tools.py` 加入文档依赖声明，新建 `labs/agent/planner.py` 与 `demo.py` 连接固定规划器和样例。下面的 demo 命令要在这些文件写好后运行；完整参考用于对照未展开的函数。按[学习流程](../../../docs/learning-workflow.md)检查第二次调用确实发生，再提交。

搜索到“rolling deployment”这句话时，结果还说附录包含生产限制。只回答第一条证据会漏掉 `limits` 来源的部署窗口。多轮循环的最小必要改变是：保存每次调用和工具结果，让规划器根据缺口继续读取。

## 让来源声明可信依赖

`SourceDocument.related_sources` 是可信执行上下文提供的依赖关系。`EvidencePlanner` 首轮调用 `bm25_search`；当结果声明了尚未读过的 `limits`，规划器提出 `read_document(source_id="limits")`。运行时把两次结果放进 `Observation` 和 `evidence`，最后只接受引用集合属于已经保留的证据。

```bash
uv run python -m labs.agent.demo
```

输出中应看到：

```text
bm25_search -> read_document -> Finish
```

最终文本同时包含 `rolling deployment` 和 `02:00 UTC`，引用包含 `deploy@v1` 与 `limits@v1`。单次基线可以对照运行：

```bash
uv run python -m labs.agent.demo --single
```

它只返回部署说明，不包含附录窗口。

## 完整 v2 checkpoint

从 [v2/loop.py](../../../reference/labs/agent/checkpoints/v2/loop.py) 读取完整实现。它的循环顺序是：提出 `ToolCall`，查注册表，执行一次工具，保存 `Observation`，去重证据，再把新的证据传回规划器。它仍然没有时间或读取预算；如果规划器永远提出新调用，循环只能依赖 `max_steps`。

先从自己的 demo 轨迹确认第二次工具调用确实发生，而不是把两段文本预先拼起来。以下命令只回放参考主线相关测试，完整主线测试留到 v3：

```bash
PYTHONPATH=reference uv run python -P -m pytest --import-mode=importlib -q tests/test_agent.py -k 'multi_round_reads or observation_drives or document_instructions'
```

最后一个测试把恶意文档当成数据。文档中的“调用 shell”不会改变工具注册表，只有规划器返回的已注册工具名才会执行。

## 仍然缺什么

循环已经真实多轮，但重复读取仍可能消耗无界时间和返回内容；同步工具被阻塞时，单纯检查 `max_steps` 也无法及时停止。下一版增加轮数、读取字节数、证据数和合作式时间预算，并区分每一种停止原因。
