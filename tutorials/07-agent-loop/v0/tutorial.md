# Agent 检索循环 v0：一次真实检索与可核对回答

前置：04 v4、05 v3、06 v3，后续复用 02 的代码读取。用户问错误码时，先建立一个最小可信基线：执行一次调用者选好的工具，从返回证据中摘取文本并附引用；没有证据就拒答。本专题先用确定性规划器讲运行机制，不调用 LLM。

全部命令从仓库根目录执行，使用你自己的 `labs/`，沿用 `uv sync --locked` 安装的环境。检查通过后按[学习流程](../../../docs/learning-workflow.md)保存自己的版本。

## 1. 让工具返回证据，而不是自称成功

Evidence 保存来源 ID 与原文，Tool 保存工具名和接收参数映射的函数；AgentAnswer 明确 answerable 与停止原因。answer_once 检查问题非空，执行一次工具，结果为空返回 no_evidence。这里回答只摘取第一条原文，引用来自实际工具结果。本版使用固定单版本语料，引用暂时只保存 ID；v1 接多种来源时再加入版本和定位信息。

```bash
mkdir -p labs/agent
touch labs/__init__.py labs/agent/__init__.py
```

这两个 `__init__.py` 是空的包文件；已有文件保留，下面才开始实现本版行为。

`labs/agent/loop.py` — checkpoint：将这个文件完整写为下面的代码。

```python
"""Standalone v0 checkpoint: one tool call, or a refusal."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping


@dataclass(frozen=True)
class Evidence:
    source_id: str
    text: str

    @property
    def citation(self) -> str:
        return self.source_id


@dataclass(frozen=True)
class Tool:
    name: str
    run: Callable[[Mapping[str, object]], tuple[Evidence, ...]]


@dataclass(frozen=True)
class AgentAnswer:
    answerable: bool
    text: str
    citations: tuple[str, ...]
    stop_reason: str


def answer_once(question: str, tool: Tool, arguments: Mapping[str, object]) -> AgentAnswer:
    if not question.strip():
        raise ValueError("question must be nonempty")
    evidence = tool.run(arguments)
    if not evidence:
        return AgentAnswer(False, "The allowed sources do not answer this question.", (), "no_evidence")
    first = evidence[0]
    return AgentAnswer(True, first.text, tuple(item.citation for item in evidence), "answered")
```

```bash
uv run python - <<'PY'
from labs.agent.loop import Evidence, Tool, answer_once
from labs.hybrid.retrieval import Document, bm25_rank

docs = [Document("error", "E104 means connection timeout"),
        Document("other", "refund rules")]
def search(arguments):
    return tuple(Evidence(hit.document.id, hit.document.text)
                 for hit in bm25_rank(docs, arguments["query"]))

tool = Tool("bm25_search", search)
answer = answer_once("E104", tool, {"query": "E104"})
assert answer.answerable and answer.citations == ("error",)
assert answer.text == "E104 means connection timeout"
missing = answer_once("unknown", tool, {"query": "unmentioned"})
assert not missing.answerable and missing.stop_reason == "no_evidence"
assert missing.citations == ()
print(answer.text, answer.citations)
print(missing.stop_reason)
PY
```

预期显示错误码原文、引用 error，以及 no_evidence。这里确实调用了 04 的 BM25；不是预先拼好答案。工具异常目前向上传播，预算和统一错误停止留到 v3。

## 本版检查点

loop.py 中 Evidence、Tool、AgentAnswer 和 answer_once 构成完整 v0。它不会自己选工具，也不能判断多条证据是否回答完整；下一版把选择变成 ToolCall 数据交给运行时执行。

需要对照时可阅读[本版参考源码](../../../reference/labs/agent/checkpoints/v0/loop.py)。自己的检查必须在 `labs/` 上通过；参考答案不会更新个人进度。
