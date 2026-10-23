# Agent 检索循环 v3：预算、去重与可诊断停止

从自己的 v2 继续。规划器可能重复读取同一来源，工具也可能返回大量文本或阻塞。本版限制规划轮数、累计返回 UTF-8 字节数、保留证据数和合作式经过时间，并将失败记录成停止原因。同步阻塞调用仍需要工具自己的 I/O 超时或进程隔离；运行时无法在调用中途抢占。

全部命令从仓库根目录执行，使用你自己的 `labs/`，沿用 `uv sync --locked` 安装的环境。检查通过后按[学习流程](../../../docs/learning-workflow.md)保存自己的版本。

## 1. 同时更新结果契约与工具回调

这是必须一起完成的接口修改：Tool.run 变成 `(arguments, remaining_bytes) -> ToolResult`，Observation 保存 result/耗时/错误。ToolResult.bytes_read 计算返回文本的 UTF-8 字节数；它不代表数据库内部读取字节数。ReadBudgetExceeded 区分“结果无法完整放入预算”和一般工具失败。Evidence 与 ToolInfo 的含义沿用 v2。

先将 loop.py 完整写为下列契约、停止/完成函数和单次基线。本步骤暂不提供 run_agent；第 2 步追加它后再使用 demo。_stop 统一返回未验证答案，_finish 验证非空文本、引用类型及来源，合法拒答不带引用。answer_once 也处理异常与错误工具返回；它是固定 65536 字节参数的对照基线，多轮完整资源限制在下一步。

`labs/agent/loop.py` — checkpoint：将这个文件完整写为下面的代码。

```python
"""A planner-driven retrieval loop with explicit evidence and resource limits.

The planner proposes actions. Only this runtime can execute registered tools;
tool output is data and cannot register a tool or change a budget.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
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
class ToolResult:
    evidence: tuple[Evidence, ...]

    @property
    def bytes_read(self) -> int:
        return sum(len(item.text.encode("utf-8")) for item in self.evidence)


@dataclass(frozen=True)
class ToolInfo:
    name: str
    description: str
    parameters: Mapping[str, str]


class ReadBudgetExceeded(ValueError):
    """A tool cannot return its complete evidence within the read budget."""


@dataclass(frozen=True)
class Tool:
    info: ToolInfo
    run: Callable[[Mapping[str, Any], int], ToolResult]


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
    result: ToolResult
    elapsed_seconds: float
    error: str | None = None


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
    planner_calls: int
    bytes_read: int


def _stop(
    reason: str,
    evidence: Sequence[Evidence],
    trace: Sequence[Observation],
    planner_calls: int,
    bytes_read: int,
) -> AgentAnswer:
    return AgentAnswer(
        False,
        f"No verified final answer: {reason}.",
        (),
        tuple(trace),
        tuple(evidence),
        reason,
        planner_calls,
        bytes_read,
    )


def _finish(
    decision: Finish,
    evidence: Sequence[Evidence],
    trace: Sequence[Observation],
    planner_calls: int,
    bytes_read: int,
) -> AgentAnswer:
    known = {item.citation for item in evidence}
    if type(decision.answerable) is not bool or not isinstance(decision.text, str) or not decision.text.strip():
        reason = "invalid_answer"
    elif not isinstance(decision.citations, tuple) or not all(isinstance(value, str) for value in decision.citations):
        reason = "invalid_citation"
    elif decision.answerable and (not decision.citations or not set(decision.citations) <= known):
        reason = "invalid_citation"
    elif not decision.answerable and decision.citations:
        reason = "invalid_citation"
    else:
        return AgentAnswer(
            decision.answerable,
            decision.text,
            tuple(dict.fromkeys(decision.citations)),
            tuple(trace),
            tuple(evidence),
            "answered" if decision.answerable else "no_evidence",
            planner_calls,
            bytes_read,
        )
    return _stop(reason, evidence, trace, planner_calls, bytes_read)


def answer_once(question: str, tool: Tool, arguments: Mapping[str, Any]) -> AgentAnswer:
    """Freeze the single-tool, extractive baseline used to compare the loop."""

    if not isinstance(question, str) or not question.strip():
        raise ValueError("question must be nonempty text")
    started = time.monotonic()
    call = ToolCall(tool.info.name, dict(arguments))
    try:
        result = tool.run(call.arguments, 65536)
    except Exception as exc:
        observation = Observation(1, call, ToolResult(()), time.monotonic() - started, str(exc))
        return _stop("tool_error", (), (observation,), 0, 0)
    if not isinstance(result, ToolResult) or not all(isinstance(item, Evidence) for item in result.evidence):
        observation = Observation(1, call, ToolResult(()), time.monotonic() - started, "invalid tool result")
        return _stop("invalid_tool_result", (), (observation,), 0, 0)
    observation = Observation(1, call, result, time.monotonic() - started)
    if not result.evidence:
        return _finish(Finish(False, "The allowed sources do not answer this question."), (), (observation,), 0, 0)
    first = result.evidence[0]
    return _finish(Finish(True, first.text, (first.citation,)), result.evidence, (observation,), 0, result.bytes_read)
```

随后完整替换 tools.py，让四个回调都接收预算。_bounded 由多个工具共同调用，固定证据为 ToolResult，并在完整结果超出剩余预算时抛错，不偷偷截掉证据。代码读取先把剩余预算传给 02 的 reader；文档和库存结果在返回前检查。_arguments、来源版本和宿主所有权沿用前面版本。

`labs/agent/tools.py` — checkpoint：将这个文件完整写为下面的代码。

```python
"""Bind real retrieval, file, and SQLite operations to the Agent contract."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from labs.code_search.reader import read_range
from labs.hybrid.retrieval import Document, bm25_rank
from labs.live_data.query import get_product

from .loop import Evidence, ReadBudgetExceeded, Tool, ToolInfo, ToolResult


@dataclass(frozen=True)
class SourceDocument:
    source_id: str
    source_version: str
    text: str
    related_sources: tuple[str, ...] = ()


def _arguments(arguments: Mapping[str, Any], expected: Mapping[str, type]) -> None:
    if set(arguments) != set(expected):
        raise ValueError(f"expected exactly {', '.join(sorted(expected))}")
    for name, value_type in expected.items():
        if type(arguments[name]) is not value_type:
            raise ValueError(f"{name} must be {value_type.__name__}")
        if value_type is str and not arguments[name].strip():
            raise ValueError(f"{name} must be nonempty")


def _bounded(evidence: Sequence[Evidence], budget: int) -> ToolResult:
    result = ToolResult(tuple(evidence))
    if result.bytes_read > budget:
        raise ReadBudgetExceeded("complete tool result exceeds remaining read bytes")
    return result


def lexical_tool(documents: Sequence[SourceDocument], *, limit: int = 1) -> Tool:
    """Run the existing BM25 implementation over versioned documents."""

    if limit < 1:
        raise ValueError("limit must be positive")
    by_id = {document.source_id: document for document in documents}
    if len(by_id) != len(documents):
        raise ValueError("source IDs must be unique in a searchable snapshot")
    corpus = [Document(document.source_id, document.text) for document in documents]

    def run(arguments: Mapping[str, Any], budget: int) -> ToolResult:
        _arguments(arguments, {"query": str})
        hits = bm25_rank(corpus, arguments["query"])[:limit]
        evidence: list[Evidence] = []
        for hit in hits:
            document = by_id[hit.document.id]
            evidence.append(
                Evidence(
                    document.source_id,
                    document.source_version,
                    f"lines:1-{max(1, len(document.text.splitlines()))}",
                    document.text,
                    document.related_sources,
                )
            )
        return _bounded(evidence, budget)

    return Tool(
        ToolInfo("bm25_search", "Search versioned source text using BM25", {"query": "string"}),
        run,
    )


def read_tool(documents: Sequence[SourceDocument]) -> Tool:
    """Read a whole small document from a trusted in-memory source registry."""

    by_id = {document.source_id: document for document in documents}
    if len(by_id) != len(documents):
        raise ValueError("source IDs must be unique in a readable snapshot")

    def run(arguments: Mapping[str, Any], budget: int) -> ToolResult:
        _arguments(arguments, {"source_id": str})
        document = by_id.get(arguments["source_id"])
        if document is None:
            return ToolResult(())
        return _bounded(
            [
                Evidence(
                    document.source_id,
                    document.source_version,
                    f"lines:1-{max(1, len(document.text.splitlines()))}",
                    document.text,
                    document.related_sources,
                )
            ],
            budget,
        )

    return Tool(
        ToolInfo("read_document", "Read a known source ID, never an arbitrary path", {"source_id": "string"}),
        run,
    )


def code_tool(workspace: Path, *, source_version: str) -> Tool:
    """Reuse the code-search topic's bounded, workspace-confined range reader."""

    def run(arguments: Mapping[str, Any], budget: int) -> ToolResult:
        _arguments(arguments, {"path": str, "start_line": int, "end_line": int})
        try:
            result = read_range(
                workspace,
                arguments["path"],
                start_line=arguments["start_line"],
                end_line=arguments["end_line"],
                max_bytes=budget,
            )
        except ValueError as exc:
            if "exceeds max_bytes" in str(exc):
                raise ReadBudgetExceeded(str(exc)) from exc
            raise
        return _bounded(
            [Evidence(result.path, source_version, f"lines:{result.start_line}-{result.end_line}", result.text)],
            budget,
        )

    return Tool(
        ToolInfo("read_code", "Read an inclusive UTF-8 line range inside the fixed workspace", {"path": "string", "start_line": "integer", "end_line": "integer"}),
        run,
    )


def inventory_tool(connection: sqlite3.Connection) -> Tool:
    """Use the real allow-listed inventory lookup; never accept model SQL."""

    def run(arguments: Mapping[str, Any], budget: int) -> ToolResult:
        _arguments(arguments, {"sku": str})
        result = get_product(connection, arguments["sku"])
        if result is None:
            return ToolResult(())
        text = json.dumps({"sku": result.sku, "category": result.category, "quantity": result.quantity, "observed_at": result.observed_at}, sort_keys=True)
        return _bounded(
            [Evidence("inventory", result.observed_at, f"sku:{result.sku}", text)],
            budget,
        )

    return Tool(
        ToolInfo("inventory_lookup", "Read current quantity of a validated product SKU", {"sku": "string"}),
        run,
    )
```

```bash
uv run python - <<'PY'
from labs.agent.loop import ReadBudgetExceeded, answer_once
from labs.agent.tools import SourceDocument, lexical_tool

tool = lexical_tool((SourceDocument("deploy", "v1", "rolling deployment"),))
answer = answer_once("rolling", tool, {"query": "rolling"})
assert answer.answerable and answer.bytes_read == len("rolling deployment".encode())
assert answer.trace[0].result.evidence[0].source_id == "deploy"
try:
    tool.run({"query": "rolling"}, 1)
except ReadBudgetExceeded:
    print("new callback contract and complete-result budget passed")
else:
    raise AssertionError("oversized tool result accepted")
PY
```

预期打印 `new callback contract and complete-result budget passed`。这条检查调用更新后的两个文件，不能将新 loop 与旧单参数工具混用。

## 2. 在每个外部调用前后执行停止规则

追加 run_agent。入口校验预算与工具名唯一；clock 默认 monotonic，可在实验中换成确定性时钟。每次规划前后检查时间，规划器失败为 planner_error。动作必须是 Finish/ToolCall，工具名必须在注册表中。参数使用排序 JSON 形成指纹；同一工具同一参数第二次出现停止 duplicate_tool_call，即使字典键顺序不同。

执行前把剩余字节传给工具，返回后再次检查 ToolResult 与大小，防止工具没有遵守预算；超限结果不保留。去重后的新证据总数不能超 max_evidence。正常结果保存 Observation，再累计返回字节。时间检查在同步调用返回后才有机会运行；超时结果被丢弃并留下轨迹，已发生的外部副作用不会被撤销。本教程工具只读。

`labs/agent/loop.py` — patch：将下面的完整定义追加到文件末尾，已有定义保留。

```python
def run_agent(
    question: str,
    tools: Sequence[Tool],
    planner: Planner,
    *,
    max_steps: int = 8,
    max_seconds: float = 5.0,
    max_read_bytes: int = 65536,
    max_evidence: int = 16,
    clock: Callable[[], float] = time.monotonic,
) -> AgentAnswer:
    """Execute planner actions while retaining only validated tool evidence.

    ``max_steps`` counts planner calls, including the final answer decision.
    Time checks are cooperative, before and after each synchronous call. A
    blocked tool needs its own I/O timeout or process isolation to be killed.
    ``max_read_bytes`` bounds cumulative returned UTF-8 evidence, not bytes a
    database or index internally reads from disk.
    """

    if not isinstance(question, str) or not question.strip():
        raise ValueError("question must be nonempty text")
    if type(max_steps) is not int or max_steps < 1:
        raise ValueError("max_steps must be a positive integer")
    if not isinstance(max_seconds, (int, float)) or isinstance(max_seconds, bool) or not math.isfinite(max_seconds) or max_seconds <= 0:
        raise ValueError("max_seconds must be finite and positive")
    if type(max_read_bytes) is not int or max_read_bytes < 1 or type(max_evidence) is not int or max_evidence < 1:
        raise ValueError("read and evidence budgets must be positive integers")
    registry = {tool.info.name: tool for tool in tools}
    if len(registry) != len(tools):
        raise ValueError("tool names must be unique")
    infos = tuple(tool.info for tool in tools)
    started = clock()
    trace: list[Observation] = []
    evidence: list[Evidence] = []
    seen: set[str] = set()
    read_bytes = 0
    for step in range(1, max_steps + 1):
        if clock() - started >= max_seconds:
            return _stop("time_budget", evidence, trace, step - 1, read_bytes)
        try:
            decision = planner.decide(question, infos, tuple(trace), tuple(evidence))
        except Exception:
            return _stop("planner_error", evidence, trace, step, read_bytes)
        if clock() - started >= max_seconds:
            return _stop("time_budget", evidence, trace, step, read_bytes)
        if isinstance(decision, Finish):
            return _finish(decision, evidence, trace, step, read_bytes)
        if not isinstance(decision, ToolCall):
            return _stop("invalid_action", evidence, trace, step, read_bytes)
        tool = registry.get(decision.name)
        if tool is None:
            return _stop("unknown_tool", evidence, trace, step, read_bytes)
        if not isinstance(decision.arguments, Mapping):
            return _stop("invalid_arguments", evidence, trace, step, read_bytes)
        try:
            fingerprint = json.dumps([decision.name, decision.arguments], sort_keys=True, allow_nan=False)
        except (TypeError, ValueError):
            return _stop("invalid_arguments", evidence, trace, step, read_bytes)
        if fingerprint in seen:
            return _stop("duplicate_tool_call", evidence, trace, step, read_bytes)
        seen.add(fingerprint)
        if read_bytes >= max_read_bytes:
            return _stop("read_budget", evidence, trace, step, read_bytes)
        call_started = clock()
        try:
            result = tool.run(decision.arguments, max_read_bytes - read_bytes)
        except ReadBudgetExceeded as exc:
            trace.append(Observation(step, decision, ToolResult(()), clock() - call_started, str(exc)))
            return _stop("read_budget", evidence, trace, step, read_bytes)
        except Exception as exc:
            trace.append(Observation(step, decision, ToolResult(()), clock() - call_started, str(exc)))
            return _stop("tool_error", evidence, trace, step, read_bytes)
        elapsed = clock() - call_started
        if clock() - started >= max_seconds:
            trace.append(Observation(step, decision, ToolResult(()), elapsed, "time budget exceeded after tool"))
            return _stop("time_budget", evidence, trace, step, read_bytes)
        if not isinstance(result, ToolResult) or not all(isinstance(item, Evidence) for item in result.evidence):
            trace.append(Observation(step, decision, ToolResult(()), elapsed, "invalid tool result"))
            return _stop("invalid_tool_result", evidence, trace, step, read_bytes)
        if result.bytes_read > max_read_bytes - read_bytes:
            trace.append(Observation(step, decision, ToolResult(()), elapsed, "returned text exceeds read budget"))
            return _stop("read_budget", evidence, trace, step, read_bytes)
        known = {item.citation for item in evidence}
        additions = list({item.citation: item for item in result.evidence if item.citation not in known}.values())
        if len(evidence) + len(additions) > max_evidence:
            trace.append(Observation(step, decision, ToolResult(()), elapsed, "returned evidence exceeds count budget"))
            return _stop("evidence_budget", evidence, trace, step, read_bytes)
        trace.append(Observation(step, decision, result, elapsed))
        read_bytes += result.bytes_read
        for item in additions:
            if item.citation not in {value.citation for value in evidence}:
                evidence.append(item)
    return _stop("step_budget", evidence, trace, max_steps, read_bytes)
```

```bash
uv run python - <<'PY'
from labs.agent.loop import Finish, ToolCall, run_agent
from labs.agent.planner import EvidencePlanner
from labs.agent.tools import SourceDocument, lexical_tool, read_tool

sources = (SourceDocument("deploy", "v1", "rolling deployment", ("limits",)),
           SourceDocument("limits", "v1", "Only at 02:00 UTC"))
tools = (lexical_tool(sources), read_tool(sources))
assert run_agent("rolling", tools, EvidencePlanner()).answerable
assert run_agent("rolling", tools, EvidencePlanner(), max_read_bytes=1).stop_reason == "read_budget"
assert run_agent("rolling", tools, EvidencePlanner(), max_evidence=1).stop_reason == "evidence_budget"
assert run_agent("rolling", tools, EvidencePlanner(), max_steps=1).stop_reason == "step_budget"
class Repeat:
    def decide(self, *args):
        return ToolCall("read_document", {"source_id": "deploy"})
assert run_agent("q", tools, Repeat()).stop_reason == "duplicate_tool_call"
class Unsupported:
    def decide(self, *args):
        return Finish(True, "fabricated", ())
assert run_agent("q", tools, Unsupported()).stop_reason == "invalid_citation"
ticks = iter((0.0, 0.0, 2.0))
assert run_agent("rolling", tools, EvidencePlanner(), max_seconds=1, clock=lambda: next(ticks)).stop_reason == "time_budget"
print("success, citation, duplicate, byte, count, step and time checks passed")
PY
```

预期打印所有停止检查通过。时间反例改变 clock 而不是 sleep，验证一次规划返回后超时即停止。完整专题测试还覆盖工具错误、规划器错误、非法动作和恶意文档。

## 3. 把预算接到命令行并回归完整专题

planner.py 的四参数协议不变，保留 v2 的 EvidencePlanner。完整替换 demo.py，新加 max-read-bytes/max-evidence/max-seconds 参数并传入 run_agent；它输出 planner_calls、bytes_read 和明确的 stop_reason。命令退出码 1 表示未成功完成的预算/错误停止。

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
    parser.add_argument("--max-read-bytes", type=int, default=65536)
    parser.add_argument("--max-evidence", type=int, default=16)
    parser.add_argument("--max-seconds", type=float, default=5.0)
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
            answer = run_agent(args.question, tools, EvidencePlanner(), max_steps=args.max_steps, max_read_bytes=args.max_read_bytes, max_evidence=args.max_evidence, max_seconds=args.max_seconds)
    finally:
        connection.close()
    print(json.dumps(asdict(answer), ensure_ascii=False, indent=2))
    return 0 if answer.answerable or answer.stop_reason == "no_evidence" else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

```bash
uv run python -m pytest -q tests/test_agent.py
```

19 项测试及 9 个子测试应通过。此时验收的是自己组装的最终模块；历史 v1/v2 的正确性由各页的正文实验独立验证。

```bash
uv run python -m labs.agent.demo
```

正常情况下生成包含两次调用轨迹和两个来源引用的 JSON，stop_reason 为 answered。

```bash
uv run python - <<'PY'
import json
import subprocess
import sys

result = subprocess.run([sys.executable, "-m", "labs.agent.demo", "--max-read-bytes", "1"], capture_output=True, text=True)
assert result.returncode == 1
answer = json.loads(result.stdout)
assert answer["stop_reason"] == "read_budget"
assert answer["answerable"] is False
print("CLI budget reaches runtime and reports failure")
PY
```

预期打印 `CLI budget reaches runtime and reports failure`。这一步验证命令行参数实际影响运行时，而不仅是函数层能设置预算。

## 本版检查点

loop.py 由步骤 1 的完整前半文件和步骤 2 的 run_agent 组成，tools.py/demo.py 已更新，planner.py 复用 v2。运行时完成确定性多轮、来源引用与资源停止，不代表已实现 LLM 规划质量、持久恢复或工具强制隔离。

需要对照时可阅读[本版参考源码](../../../reference/labs/agent)。自己的检查必须在 `labs/` 上通过；参考答案不会更新个人进度。
