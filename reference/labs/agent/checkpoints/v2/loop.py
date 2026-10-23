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
