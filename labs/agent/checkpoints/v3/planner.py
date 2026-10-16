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
