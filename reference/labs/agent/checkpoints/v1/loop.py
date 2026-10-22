"""Standalone v1 checkpoint: a planner selects one registered tool."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Protocol


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
class ToolCall:
    name: str
    arguments: Mapping[str, object]


@dataclass(frozen=True)
class Finish:
    text: str
    citations: tuple[str, ...]


class Planner(Protocol):
    def decide(self, question: str, tool_names: tuple[str, ...]) -> ToolCall | Finish: ...


@dataclass(frozen=True)
class AgentAnswer:
    answerable: bool
    text: str
    citations: tuple[str, ...]
    trace: tuple[str, ...]
    stop_reason: str


def run_agent(question: str, tools: tuple[Tool, ...], planner: Planner) -> AgentAnswer:
    if not question.strip():
        raise ValueError("question must be nonempty")
    registry = {tool.name: tool for tool in tools}
    decision = planner.decide(question, tuple(registry))
    if isinstance(decision, Finish):
        return AgentAnswer(bool(decision.citations), decision.text, decision.citations, (), "answered")
    tool = registry.get(decision.name)
    if tool is None:
        return AgentAnswer(False, "Unknown tool.", (), (), "unknown_tool")
    evidence = tool.run(decision.arguments)
    if not evidence:
        return AgentAnswer(False, "The allowed sources do not answer this question.", (), (tool.name,), "no_evidence")
    known = tuple(item.citation for item in evidence)
    return AgentAnswer(True, evidence[0].text, known, (tool.name,), "answered")
