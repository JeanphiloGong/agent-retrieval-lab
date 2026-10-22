"""Standalone v2 checkpoint: a planner may gather evidence in multiple rounds."""

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
    answerable: bool
    text: str
    citations: tuple[str, ...]


@dataclass(frozen=True)
class Observation:
    call: ToolCall
    evidence: tuple[Evidence, ...]


class Planner(Protocol):
    def decide(self, question: str, observations: tuple[Observation, ...], evidence: tuple[Evidence, ...]) -> ToolCall | Finish: ...


@dataclass(frozen=True)
class AgentAnswer:
    answerable: bool
    text: str
    citations: tuple[str, ...]
    trace: tuple[Observation, ...]
    stop_reason: str


def run_agent(question: str, tools: tuple[Tool, ...], planner: Planner, *, max_steps: int = 8) -> AgentAnswer:
    if not question.strip() or max_steps < 1:
        raise ValueError("question and max_steps must be valid")
    registry = {tool.name: tool for tool in tools}
    observations: list[Observation] = []
    evidence: list[Evidence] = []
    for _ in range(max_steps):
        decision = planner.decide(question, tuple(observations), tuple(evidence))
        if isinstance(decision, Finish):
            known = {item.citation for item in evidence}
            if decision.answerable and not set(decision.citations) <= known:
                return AgentAnswer(False, "Invalid citation.", (), tuple(observations), "invalid_citation")
            return AgentAnswer(decision.answerable, decision.text, decision.citations, tuple(observations), "answered")
        tool = registry.get(decision.name)
        if tool is None:
            return AgentAnswer(False, "Unknown tool.", (), tuple(observations), "unknown_tool")
        result = tool.run(decision.arguments)
        observation = Observation(decision, result)
        observations.append(observation)
        known = {item.citation for item in evidence}
        evidence.extend(item for item in result if item.citation not in known)
    return AgentAnswer(False, "The agent step budget was exhausted.", (), tuple(observations), "step_budget")
