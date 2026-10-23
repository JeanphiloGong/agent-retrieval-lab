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

class Planner(Protocol):
    def decide(self, question: str, tools: tuple[ToolInfo, ...]) -> ToolCall | Finish:
        """Choose one registered tool or decline the question."""


@dataclass(frozen=True)
class AgentAnswer:
    answerable: bool
    text: str
    citations: tuple[str, ...]
    trace: tuple[str, ...]
    stop_reason: str


def answer_once(question: str, tool: Tool, arguments: Mapping[str, Any]) -> AgentAnswer:
    if not question.strip():
        raise ValueError("question must be nonempty")
    evidence = tool.run(arguments)
    if not evidence:
        return AgentAnswer(False, "The allowed sources do not answer this question.", (), (tool.info.name,), "no_evidence")
    return AgentAnswer(True, evidence[0].text, tuple(item.citation for item in evidence), (tool.info.name,), "answered")


def run_agent(question: str, tools: Sequence[Tool], planner: Planner) -> AgentAnswer:
    if not question.strip():
        raise ValueError("question must be nonempty")
    registry = {tool.info.name: tool for tool in tools}
    if len(registry) != len(tools):
        raise ValueError("tool names must be unique")
    decision = planner.decide(question, tuple(tool.info for tool in tools))
    if isinstance(decision, Finish):
        if decision.answerable or decision.citations:
            return AgentAnswer(False, "No observed evidence.", (), (), "invalid_citation")
        return AgentAnswer(False, decision.text, (), (), "no_evidence")
    tool = registry.get(decision.name)
    if tool is None:
        return AgentAnswer(False, "Unknown tool.", (), (), "unknown_tool")
    return answer_once(question, tool, decision.arguments)
