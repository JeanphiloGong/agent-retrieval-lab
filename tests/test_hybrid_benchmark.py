"""Report failures must remain visible in both rows and aggregate denominators."""

import json
from pathlib import Path

import pytest

from labs.hybrid.benchmark import run


class FixedEncoder:
    def embed(self, texts):
        return iter([[1.0, 0.0] for _ in texts])

    def query_embed(self, query):
        return iter([[1.0, 0.0]])


class FixedReranker:
    def rerank(self, query, texts):
        return [1.0] * len(texts)


@pytest.mark.parametrize("stage", ["embedding_load", "query_embed", "reranker_load", "rerank"])
def test_model_failures_write_report_and_keep_denominators(tmp_path, monkeypatch, stage):
    encoder, reranker = FixedEncoder(), FixedReranker()

    def fail(*args, **kwargs):
        raise RuntimeError("injected model failure")

    monkeypatch.setattr("labs.hybrid.benchmark.load_embedding", lambda cache: encoder)
    monkeypatch.setattr("labs.hybrid.benchmark.load_reranker", lambda cache: reranker)
    if stage == "embedding_load":
        monkeypatch.setattr("labs.hybrid.benchmark.load_embedding", fail)
    elif stage == "query_embed":
        monkeypatch.setattr(encoder, "query_embed", fail)
    elif stage == "reranker_load":
        monkeypatch.setattr("labs.hybrid.benchmark.load_reranker", fail)
    else:
        monkeypatch.setattr(reranker, "rerank", fail)
    output = tmp_path / "report.json"
    report = run(output)
    assert json.loads(output.read_text())["rows"] == report["rows"]
    expected_failures = {"vector", "rrf", "rerank"} if stage in {"embedding_load", "query_embed"} else {"rerank"}
    questions = [q for q in json.loads(Path("fixtures/hybrid/questions.json").read_text()) if q["split"] == "heldout"]
    assert len(report["rows"]) == 4 * len(questions)
    for row in report["rows"]:
        assert row["failure"] == (row["pipeline"] in expected_failures)
        if row["failure"]:
            assert row["ids"] == [] and row["error"] == "RuntimeError"
            if not row["requires_abstention"]:
                assert row["recall"] == row["mrr"] == row["ndcg"] == 0
    for group in report["groups"]:
        assert group["failure_rate"] == int(group["pipeline"] in expected_failures)


def test_success_writes_four_pipeline_rows_per_question(tmp_path, monkeypatch):
    monkeypatch.setattr("labs.hybrid.benchmark.load_embedding", lambda cache: FixedEncoder())
    monkeypatch.setattr("labs.hybrid.benchmark.load_reranker", lambda cache: FixedReranker())
    report = run(tmp_path / "report.json")
    assert report["setup_errors"] == {}
    assert {row["pipeline"] for row in report["rows"]} == {"bm25", "vector", "rrf", "rerank"}
    assert all(not row["failure"] for row in report["rows"])
    assert all(group["failure_rate"] == 0 for group in report["groups"])
