from pathlib import Path

from labs.documents.v0_extract import extract_document
from labs.documents.v1_structure import structure_document


FIXTURES = Path(__file__).parents[2] / "fixtures" / "documents"


def _handbook():
    return structure_document(
        extract_document(FIXTURES / "handbook-v1.md", "handbook", "v1")
    )


def test_repeated_headings_have_distinct_line_positions_and_paths() -> None:
    document = _handbook()
    headings = [block for block in document.blocks if block.kind == "heading" and block.text == "Refunds"]

    assert len(headings) == 2
    assert headings[0].start_line != headings[1].start_line
    assert headings[0].heading_path == ("Support Handbook", "Refunds")
    assert headings[1].heading_path == ("Support Handbook", "Refunds")


def test_table_is_one_traceable_block() -> None:
    document = _handbook()
    tables = [block for block in document.blocks if block.kind == "table"]

    assert len(tables) == 1
    assert tables[0].start_line < tables[0].end_line
    assert "Refund window" in tables[0].text
    assert tables[0].heading_path == ("Support Handbook", "Refunds")


def test_paragraphs_keep_the_heading_context() -> None:
    document = _handbook()
    limits = next(block for block in document.blocks if "02:00 UTC" in block.text)

    assert limits.kind == "paragraph"
    assert limits.heading_path == ("Support Handbook", "Deployment", "Limits")
    assert limits.start_line == limits.end_line
