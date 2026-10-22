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
