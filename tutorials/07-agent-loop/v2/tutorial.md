# Agent 检索循环 v2：看过结果再决定补读

从自己的 v1 继续。搜索 rolling deployment 命中正文，但宿主元数据声明 limits 来源含生产窗口。本版增加 Observation、多轮 Planner 与来源依赖，实际执行第二次读取，再给出包含两条出处的回答。只有取得的引用可用于成功 Finish。

全部命令从仓库根目录执行，使用你自己的 `labs/`，沿用 `uv sync --locked` 安装的环境。检查通过后按[学习流程](../../../docs/learning-workflow.md)保存自己的版本。

## 1. 保存调用与结果，拒绝没有证据的结论

完整替换 loop.py。Evidence 新增 related_sources，Observation 保存 step/call/evidence，AgentAnswer 保存 trace 与去重证据。Planner.decide 现在接收 `(question, tools, observations, evidence)` 四个参数，v1 的两参数固定规划器要按本页更新。每轮只能产生一个动作；max_steps 计规划器调用，最终 Finish 也占一轮。

运行顺序是决策、查注册表、执行、保存 Observation、按 citation 去重。成功 Finish 必须含非空引用且全部来自已保留证据；拒答不能携带引用。answer_once 也更新返回结构，继续用作单次基线。本版不检查时间/字节预算，不自动重试。

`labs/agent/loop.py` — checkpoint：将这个文件完整写为下面的代码。

```python
"""A version-local Agent contract; no future runtime imports."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol, Sequence

@dataclass(frozen=True)
class Evidence:
    source_id: str
    source_version: str
    locator: str
    text: str
    related_sources: tuple[str, ...] = ()

    @property
    def citation(self) -> str:
        digest = hashlib.sha256(self.text.encode("utf-8")).hexdigest()[:16]
        return f"{self.source_id}@{self.source_version}:{self.locator}#{digest}"

@dataclass(frozen=True)
class ToolInfo:
    name: str
    description: str
    parameters: Mapping[str, str]

@dataclass(frozen=True)
class Tool:
    info: ToolInfo
    run: Callable[[Mapping[str, Any]], tuple[Evidence, ...]]

@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: Mapping[str, Any]

@dataclass(frozen=True)
class Finish:
    answerable: bool
    text: str
    citations: tuple[str, ...] = ()

@dataclass(frozen=True)
class Observation:
    step: int
    call: ToolCall
    evidence: tuple[Evidence, ...]

class Planner(Protocol):
    def decide(
        self,
        question: str,
        tools: tuple[ToolInfo, ...],
        observations: tuple[Observation, ...],
        evidence: tuple[Evidence, ...],
    ) -> ToolCall | Finish:
        """Inspect prior observations and propose exactly one next action."""

@dataclass(frozen=True)
class AgentAnswer:
    answerable: bool
    text: str
    citations: tuple[str, ...]
    trace: tuple[Observation, ...]
    evidence: tuple[Evidence, ...]
    stop_reason: str


def answer_once(question: str, tool: Tool, arguments: Mapping[str, Any]) -> AgentAnswer:
    if not question.strip():
        raise ValueError("question must be nonempty")
    result = tool.run(arguments)
    trace = (Observation(1, ToolCall(tool.info.name, arguments), result),)
    if not result:
        return AgentAnswer(False, "The allowed sources do not answer this question.", (), trace, (), "no_evidence")
    return AgentAnswer(True, result[0].text, (result[0].citation,), trace, result, "answered")


def run_agent(question: str, tools: Sequence[Tool], planner: Planner, *, max_steps: int = 8) -> AgentAnswer:
    if not question.strip() or max_steps < 1:
        raise ValueError("question and max_steps must be valid")
    registry = {tool.info.name: tool for tool in tools}
    if len(registry) != len(tools):
        raise ValueError("tool names must be unique")
    infos = tuple(tool.info for tool in tools)
    trace: list[Observation] = []
    evidence: list[Evidence] = []
    for step in range(1, max_steps + 1):
        decision = planner.decide(question, infos, tuple(trace), tuple(evidence))
        if isinstance(decision, Finish):
            known = {item.citation for item in evidence}
            if decision.answerable and (not decision.citations or not set(decision.citations) <= known):
                return AgentAnswer(False, "Invalid citation.", (), tuple(trace), tuple(evidence), "invalid_citation")
            if not decision.answerable and decision.citations:
                return AgentAnswer(False, "Invalid citation.", (), tuple(trace), tuple(evidence), "invalid_citation")
            reason = "answered" if decision.answerable else "no_evidence"
            return AgentAnswer(decision.answerable, decision.text, decision.citations, tuple(trace), tuple(evidence), reason)
        tool = registry.get(decision.name)
        if tool is None:
            return AgentAnswer(False, "Unknown tool.", (), tuple(trace), tuple(evidence), "unknown_tool")
        result = tool.run(decision.arguments)
        trace.append(Observation(step, decision, result))
        known = {item.citation for item in evidence}
        for item in result:
            if item.citation not in known:
                evidence.append(item)
                known.add(item.citation)
    return AgentAnswer(False, "The agent step budget was exhausted.", (), tuple(trace), tuple(evidence), "step_budget")
```

```bash
uv run python - <<'PY'
from labs.agent.loop import Evidence, Finish, Tool, ToolCall, ToolInfo, run_agent

item = Evidence("manual", "v1", "lines:1-1", "deploy safely")
tool = Tool(ToolInfo("read", "Read fixed text", {}), lambda args: (item,))
class ReadThenFinish:
    def decide(self, question, infos, observations, evidence):
        if not observations:
            return ToolCall("read", {})
        return Finish(True, evidence[0].text, (evidence[0].citation,))
answer = run_agent("deploy", (tool,), ReadThenFinish())
assert answer.answerable and len(answer.trace) == 1
for citations in ((), ("fabricated",)):
    class PrematureFinish:
        def decide(self, question, infos, observations, evidence):
            return Finish(True, "unsupported", citations)
    result = run_agent("deploy", (), PrematureFinish())
    assert not result.answerable and result.stop_reason == "invalid_citation"
assert run_agent("deploy", (tool,), ReadThenFinish(), max_steps=1).stop_reason == "step_budget"
print("multi-round history, citation checks and step budget passed")
PY
```

预期打印 `multi-round history, citation checks and step budget passed`。一个工具调用已完成却没有足够轮数 Finish 时，仍不能宣布回答成功。

## 2. 把可信来源依赖交给规划器

替换 tools.py 的 SourceDocument、lexical_tool、read_tool 三个完整定义。新增 related_sources 字段由宿主配置，随证据返回；文档文本里的指令不改变该字段。_arguments、code_tool、inventory_tool 沿用 v1，回调仍只有一个参数。

`labs/agent/tools.py` — patch：完整替换 `SourceDocument`，保留其他定义。

```python
@dataclass(frozen=True)
class SourceDocument:
    source_id: str
    source_version: str
    text: str
    related_sources: tuple[str, ...] = ()
```

`labs/agent/tools.py` — patch：完整替换 `lexical_tool`，保留其他定义。

```python
def lexical_tool(documents: Sequence[SourceDocument], *, limit: int=1) -> Tool:
    """Run the existing BM25 implementation over versioned documents."""
    if limit < 1:
        raise ValueError('limit must be positive')
    by_id = {document.source_id: document for document in documents}
    if len(by_id) != len(documents):
        raise ValueError('source IDs must be unique in a searchable snapshot')
    corpus = [Document(document.source_id, document.text) for document in documents]

    def run(arguments: Mapping[str, Any]) -> tuple[Evidence, ...]:
        _arguments(arguments, {'query': str})
        hits = bm25_rank(corpus, arguments['query'])[:limit]
        evidence: list[Evidence] = []
        for hit in hits:
            document = by_id[hit.document.id]
            evidence.append(Evidence(document.source_id, document.source_version, f'lines:1-{max(1, len(document.text.splitlines()))}', document.text, document.related_sources))
        return tuple(evidence)
    return Tool(ToolInfo('bm25_search', 'Search versioned source text using BM25', {'query': 'string'}), run)
```

`labs/agent/tools.py` — patch：完整替换 `read_tool`，保留其他定义。

```python
def read_tool(documents: Sequence[SourceDocument]) -> Tool:
    """Read a whole small document from a trusted in-memory source registry."""
    by_id = {document.source_id: document for document in documents}
    if len(by_id) != len(documents):
        raise ValueError('source IDs must be unique in a readable snapshot')

    def run(arguments: Mapping[str, Any]) -> tuple[Evidence, ...]:
        _arguments(arguments, {'source_id': str})
        document = by_id.get(arguments['source_id'])
        if document is None:
            return ()
        return tuple([Evidence(document.source_id, document.source_version, f'lines:1-{max(1, len(document.text.splitlines()))}', document.text, document.related_sources)])
    return Tool(ToolInfo('read_document', 'Read a known source ID, never an arbitrary path', {'source_id': 'string'}), run)
```

```bash
uv run python - <<'PY'
from labs.agent.tools import SourceDocument, lexical_tool, read_tool

sources = (SourceDocument("deploy", "v1", "rolling deployment", ("limits",)),
           SourceDocument("limits", "v1", "Only at 02:00 UTC"))
first = lexical_tool(sources).run({"query": "rolling deployment"})
assert first[0].related_sources == ("limits",)
second = read_tool(sources).run({"source_id": first[0].related_sources[0]})
assert second[0].source_id == "limits"
print("trusted dependency metadata reaches tool evidence")
PY
```

预期打印 `trusted dependency metadata reaches tool evidence`。这只是绑定验证，下一步让规划器自己提出第二次调用。

## 3. 实现确定性的补证决策

新建 planner.py。EvidencePlanner 首轮识别固定 inventory/manual/code 语法，其余问题调用 BM25。后续只跟随可信 related_sources；已请求但没读到的依赖导致拒答，避免永远读取不存在的来源。证据齐全后拼接原文并引用全部来源。它是真实多轮策略，但没有使用语言模型，也不会理解任意复杂任务。

`labs/agent/planner.py` — checkpoint：将这个文件完整写为下面的代码。

```python
"""A deterministic planner implementation for reproducible Agent experiments.

This is a real multi-call policy, but it is not an LLM. Replacing it requires an
object that implements the same ``decide`` protocol; no tool executor changes.
"""

from __future__ import annotations

import re

from .loop import Evidence, Finish, Observation, ToolCall, ToolInfo


class EvidencePlanner:
    """Route fixed teaching syntax and follow trusted source dependencies."""

    def __init__(self, *, follow_related: bool = True) -> None:
        self.follow_related = follow_related

    def decide(
        self,
        question: str,
        tools: tuple[ToolInfo, ...],
        observations: tuple[Observation, ...],
        evidence: tuple[Evidence, ...],
    ) -> ToolCall | Finish:
        available = {tool.name for tool in tools}
        if not observations:
            if match := re.fullmatch(r"inventory ([A-Z0-9_-]+)", question):
                return ToolCall("inventory_lookup", {"sku": match.group(1)})
            if match := re.fullmatch(r"manual ([A-Za-z0-9_-]+)", question):
                return ToolCall("read_document", {"source_id": match.group(1)})
            if match := re.fullmatch(r"code ([A-Za-z0-9_./-]+):(\d+)-(\d+)", question):
                return ToolCall("read_code", {"path": match.group(1), "start_line": int(match.group(2)), "end_line": int(match.group(3))})
            if "bm25_search" in available:
                return ToolCall("bm25_search", {"query": question})
            return Finish(False, "No registered tool can handle this question.")
        if not evidence:
            return Finish(False, "The allowed sources do not answer this question.")
        if self.follow_related:
            read_ids = {item.source_id for item in evidence}
            requested_ids = {
                observation.call.arguments["source_id"]
                for observation in observations
                if observation.call.name == "read_document"
            }
            for item in evidence:
                for source_id in item.related_sources:
                    if source_id not in read_ids:
                        if source_id in requested_ids:
                            return Finish(False, "A required related source is unavailable.")
                        return ToolCall("read_document", {"source_id": source_id})
        return Finish(True, "\n".join(item.text for item in evidence), tuple(item.citation for item in evidence))
```

```bash
uv run python - <<'PY'
from labs.agent.loop import run_agent
from labs.agent.planner import EvidencePlanner
from labs.agent.tools import SourceDocument, lexical_tool, read_tool

sources = (SourceDocument("deploy", "v1", "rolling deployment", ("limits",)),
           SourceDocument("limits", "v1", "Only at 02:00 UTC"))
answer = run_agent("rolling deployment", (lexical_tool(sources), read_tool(sources)), EvidencePlanner())
assert [o.call.name for o in answer.trace] == ["bm25_search", "read_document"]
assert answer.answerable and "02:00 UTC" in answer.text
assert len(answer.citations) == 2
missing = sources[:1]
result = run_agent("rolling deployment", (lexical_tool(missing), read_tool(missing)), EvidencePlanner())
assert not result.answerable and result.stop_reason == "no_evidence"
print("search -> related read -> Finish; missing source refuses")
PY
```

预期打印 `search -> related read -> Finish; missing source refuses`。第二次读取来自第一次观察结果，不是预先拼在一起的答案。

## 4. 把已有入口组装成可重复的实验

新建 demo.py，读取仓库固定语料，建立库存连接，注册四个工具，最后打印 AgentAnswer JSON。--single 调用 answer_once，默认走多轮；finally 保证关闭数据库。--max-steps 传给当前 run_agent，预算参数留到下一版。

`labs/agent/demo.py` — checkpoint：将这个文件完整写为下面的代码。

```python
"""Run the fixed Agent comparison without credentials or model calls."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from labs.live_data.query import open_database, seed

from .loop import answer_once, run_agent
from .planner import EvidencePlanner
from .tools import SourceDocument, code_tool, inventory_tool, lexical_tool, read_tool


def documents() -> tuple[SourceDocument, ...]:
    root = Path.cwd() / "fixtures" / "agent"
    return (
        SourceDocument("deploy", "v1", (root / "deployment-v1.txt").read_text().rstrip("\n"), ("limits",)),
        SourceDocument("limits", "v1", (root / "limits-v1.txt").read_text().rstrip("\n")),
        SourceDocument("e104", "v1", (root / "errors-v1.txt").read_text().rstrip("\n")),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the fixed retrieval Agent experiment")
    parser.add_argument("--question", default="rolling deployment")
    parser.add_argument("--single", action="store_true")
    parser.add_argument("--max-steps", type=int, default=8)
    args = parser.parse_args()
    sources = documents()
    search = lexical_tool(sources)
    connection = open_database()
    try:
        seed(connection, [("SKU_1", "widget", 12)])
        tools = [search, read_tool(sources), inventory_tool(connection), code_tool(Path.cwd() / "fixtures" / "code_search" / "repository", source_version="fixture-v1")]
        if args.single:
            answer = answer_once(args.question, search, {"query": args.question})
        else:
            answer = run_agent(args.question, tools, EvidencePlanner(), max_steps=args.max_steps)
    finally:
        connection.close()
    print(json.dumps(asdict(answer), ensure_ascii=False, indent=2))
    return 0 if answer.answerable or answer.stop_reason == "no_evidence" else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

```bash
uv run python -m labs.agent.demo
uv run python -m labs.agent.demo --single
```

默认 JSON 的 trace 应依次含 bm25_search/read_document，text 同时含 rolling deployment 与 02:00 UTC；单次版本只含正文。citations 带来源、版本、范围及摘要，不是仅打印来源名。

## 本版检查点

完整 checkpoint 是 loop.py、tools.py、planner.py、demo.py 四个兼容文件。工具异常当前会传播，重复请求只能消耗 max_steps；下一版增加时间、读取、证据预算和独立停止原因。

需要对照时可阅读[本版参考源码](../../../reference/labs/agent/checkpoints/v2)。自己的检查必须在 `labs/` 上通过；参考答案不会更新个人进度。
