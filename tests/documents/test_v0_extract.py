from pathlib import Path

import pytest
from pypdf import PdfWriter

from labs.documents.v0_extract import extract_document


FIXTURES = Path(__file__).parents[2] / "fixtures" / "documents"


def test_markdown_extraction_keeps_source_and_version() -> None:
    document = extract_document(FIXTURES / "handbook-v1.md", "handbook", "v1")

    assert document.format == "markdown"
    assert document.source_id == "handbook"
    assert document.source_version == "v1"
    assert "Refunds are available within seven days" in document.text
    assert document.page_text == (document.text,)
    assert not document.needs_ocr


def test_text_bearing_pdf_is_extractable() -> None:
    document = extract_document(FIXTURES / "notice.pdf", "notice", "v1")

    assert document.format == "pdf"
    assert document.page_text == (
        "Refunds are available within seven days.",
        "Keep the order number for support.",
    )
    assert document.text == "\n\f\n".join(document.page_text)
    assert not document.needs_ocr


def test_scanned_pdf_reports_ocr_requirement_instead_of_empty_success() -> None:
    document = extract_document(FIXTURES / "scanned.pdf", "scan", "v1")

    assert document.text == ""
    assert document.needs_ocr
    assert document.issues[0].code == "ocr_required"
    assert document.issues[0].page_number == 1


def test_unknown_format_and_bad_metadata_fail_early(tmp_path: Path) -> None:
    unknown = tmp_path / "notes.txt"
    unknown.write_text("hello", encoding="utf-8")

    with pytest.raises(ValueError, match="unsupported document format"):
        extract_document(unknown, "notes", "v1")
    with pytest.raises(ValueError, match="source_id"):
        extract_document(FIXTURES / "handbook-v1.md", "", "v1")
    with pytest.raises(FileNotFoundError):
        extract_document(tmp_path / "missing.md", "notes", "v1")


def test_malformed_pdf_is_a_failure_not_an_ocr_result(tmp_path: Path) -> None:
    malformed = tmp_path / "broken.pdf"
    malformed.write_bytes(b"%PDF-1.4\nnot a PDF object graph")
    with pytest.raises(ValueError, match="could not be parsed"):
        extract_document(malformed, "broken", "v1")


def test_encrypted_pdf_requires_explicit_password_handling(tmp_path: Path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.encrypt("example-password")
    encrypted = tmp_path / "locked.pdf"
    writer.write(encrypted)

    with pytest.raises(ValueError, match="requires a password"):
        extract_document(encrypted, "locked", "v1")
