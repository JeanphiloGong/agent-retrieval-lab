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
