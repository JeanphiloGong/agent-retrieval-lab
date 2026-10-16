import json
from pathlib import Path

import pytest

from labs.hybrid.checkpoints.v0_bm25 import rank as bm25_checkpoint
from labs.hybrid.checkpoints.v1_vector import rank_with_encoder
from labs.hybrid.checkpoints.v2_fusion import fuse
from labs.hybrid.checkpoints.v3_rerank import rerank_candidates
from labs.hybrid.checkpoints.v4_benchmark import benchmark
from labs.hybrid.retrieval import Document


class FakeVector:
    def __init__(self, vectors):
        self.vectors = vectors

    def embed(self, documents):
        return iter(self.vectors[index] for index, _ in enumerate(documents))

    def query_embed(self, query):
        return iter([[1.0, 0.0]])


def docs():
    return (
        Document("exact", "E104 connection timeout while opening a socket"),
        Document("policy", "Refund reimbursement is available within seven days"),
        Document("other", "Delivery shipping options are listed here"),
    )


def test_v0_checkpoint_is_lexical_only():
    assert bm25_checkpoint(docs(), "E104")[0].document.id == "exact"


def test_v1_checkpoint_uses_current_encoder_shape():
    hits = rank_with_encoder(docs(), "network deadline", FakeVector([[1, 0], [0, 1], [0, 1]]))
    assert hits[0].document.id == "exact"
    assert hits[0].sources == ("vector",)


def test_v2_checkpoint_keeps_both_provenances_and_deduplicates():
    hits = fuse(docs(), "refund", FakeVector([[0, 1], [1, 0], [0, 1]]))
    policy = next(hit for hit in hits if hit.document.id == "policy")
    assert set(policy.sources) == {"bm25", "vector"}
    assert len({hit.document.id for hit in hits}) == len(hits)


def test_v3_checkpoint_never_reranks_outside_fused_candidates():
    candidates = docs()[:2]
    hits = rerank_candidates(
        candidates,
        "refund",
        FakeVector([[0, 1], [1, 0]]),
        lambda query, texts: [1.0] * len(texts),
        candidate_limit=1,
    )
    assert [hit.document.id for hit in hits] == ["policy"]


def test_v3_checkpoint_rejects_unbounded_candidate_limit():
    with pytest.raises(ValueError, match="candidate_limit"):
        rerank_candidates(docs(), "refund", FakeVector([[1, 0]] * 3), lambda q, t: [1] * len(t), candidate_limit=0)


def test_v4_checkpoint_rejects_unknown_split(tmp_path: Path):
    with pytest.raises(ValueError, match="split"):
        benchmark(tmp_path / "report.json", split="unknown")


def test_v4_report_replay_uses_fixed_contract(tmp_path: Path, monkeypatch):
    expected = {"split": "heldout", "rows": [{"pipeline": "bm25"}], "groups": []}

    def fake_run(output, *, split):
        output.write_text(json.dumps(expected), encoding="utf-8")
        return expected

    monkeypatch.setattr("labs.hybrid.checkpoints.v4_benchmark.run", fake_run)
    report = benchmark(tmp_path / "report.json")
    assert report == expected
    assert json.loads((tmp_path / "report.json").read_text()) == expected
