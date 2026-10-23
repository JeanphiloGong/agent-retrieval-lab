"""Intermediate versions must assemble without future Agent contracts."""

import importlib
from pathlib import Path

import pytest

from labs.live_data.query import open_database, seed


@pytest.mark.parametrize("version", [1, 2])
def test_checkpoint_tool_bindings_use_their_own_contract(version):
    bindings = importlib.import_module(f"labs.agent.checkpoints.v{version}.tools")
    loop = importlib.import_module(f"labs.agent.checkpoints.v{version}.loop")
    documents = (bindings.SourceDocument("manual", "v1", "deployment instructions"),)
    db = open_database()
    try:
        seed(db, [("SKU_1", "widget", 12)])
        cases = [
            (bindings.lexical_tool(documents), {"query": "deployment"}),
            (bindings.read_tool(documents), {"source_id": "manual"}),
            (bindings.inventory_tool(db), {"sku": "SKU_1"}),
            (bindings.code_tool(Path("fixtures/code_search/repository"), source_version="v1"),
             {"path": "app.py", "start_line": 1, "end_line": 2}),
        ]
        for tool, arguments in cases:
            evidence = tool.run(arguments)
            assert evidence and all(isinstance(item, loop.Evidence) for item in evidence)
        with pytest.raises(ValueError):
            bindings.read_tool(documents).run({})
    finally:
        db.close()


@pytest.mark.parametrize("version", [1, 2])
@pytest.mark.parametrize("citations", [(), ("never-seen-source",)])
def test_finish_cannot_answer_before_observing_evidence(version, citations):
    loop = importlib.import_module(f"labs.agent.checkpoints.v{version}.loop")

    class FabricatingPlanner:
        def decide(self, *args):
            return loop.Finish(True, "fabricated answer", citations)

    result = loop.run_agent("question", (), FabricatingPlanner())
    assert not result.answerable
    assert result.stop_reason == "invalid_citation"
    assert result.trace == ()


def test_v2_assembles_demo_planner_and_follows_related_sources():
    from labs.agent.checkpoints.v2.demo import documents
    from labs.agent.checkpoints.v2.loop import run_agent
    from labs.agent.checkpoints.v2.planner import EvidencePlanner
    from labs.agent.checkpoints.v2.tools import lexical_tool, read_tool

    sources = documents()
    answer = run_agent("rolling deployment", (lexical_tool(sources), read_tool(sources)), EvidencePlanner())
    assert answer.answerable
    assert [observation.call.name for observation in answer.trace] == ["bm25_search", "read_document"]
    assert "02:00 UTC" in answer.text
    assert set(answer.citations) <= {item.citation for item in answer.evidence}
