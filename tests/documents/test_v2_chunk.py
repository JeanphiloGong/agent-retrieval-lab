import json
from pathlib import Path

import pytest

from labs.documents.v0_extract import extract_document
from labs.documents.v1_structure import structure_document
from labs.documents.v2_chunk import fixed_window_chunks, structure_chunks


FIXTURES = Path(__file__).parents[2] / "fixtures" / "documents"


def _handbook():
    return structure_document(
        extract_document(FIXTURES / "handbook-v1.md", "handbook", "v1")
    )


def test_fixed_windows_are_a_baseline_that_can_split_context() -> None:
    chunks = fixed_window_chunks(_handbook(), max_lines=3)

    assert len(chunks) > 1
    assert all(chunk.block_ids == () for chunk in chunks)
    assert chunks[0].start_line == 1
    assert chunks[0].end_line == 3


def test_structure_chunks_keep_heading_path_and_bound_size() -> None:
    chunks = structure_chunks(_handbook(), max_chars=100)

    assert chunks
    assert all(len(chunk.text) <= 100 for chunk in chunks)
    assert any(chunk.heading_path[-1:] == ("Refunds",) for chunk in chunks)
    assert all(chunk.block_ids for chunk in chunks)


def test_a_chunk_does_not_mix_unrelated_heading_paths() -> None:
    document = _handbook()
    chunks = structure_chunks(document, max_chars=1000)
    blocks = {block.block_id: block for block in document.blocks}

    assert len(chunks) >= 4
    for chunk in chunks:
        assert all(
            blocks[block_id].heading_path == chunk.heading_path
            for block_id in chunk.block_ids
        )


def test_same_questions_compare_evidence_completeness_and_size() -> None:
    document = _handbook()
    questions = json.loads((FIXTURES / "chunk-questions.json").read_text())
    fixed = fixed_window_chunks(document, max_lines=3)
    structured = structure_chunks(document, max_chars=180)

    def complete(chunks, item):
        return any(
            all(term in " ".join((*chunk.heading_path, chunk.text)) for term in item["evidence_terms"])
            for chunk in chunks
        )

    fixed_score = sum(complete(fixed, item) for item in questions)
    structured_score = sum(complete(structured, item) for item in questions)
    assert structured_score == len(questions)
    assert fixed_score < structured_score
    assert max(len(chunk.text) for chunk in structured) <= 180


def test_oversized_single_line_is_still_bounded() -> None:
    extracted = extract_document(FIXTURES / "handbook-v1.md", "handbook", "v1")
    structured = structure_document(extracted)
    chunks = structure_chunks(structured, max_chars=8)

    assert chunks
    assert all(len(chunk.text) <= 8 for chunk in chunks)


def test_invalid_chunk_limits_are_rejected() -> None:
    document = _handbook()
    with pytest.raises(ValueError, match="max_lines"):
        fixed_window_chunks(document, max_lines=0)
    with pytest.raises(ValueError, match="max_chars"):
        structure_chunks(document, max_chars=0)
