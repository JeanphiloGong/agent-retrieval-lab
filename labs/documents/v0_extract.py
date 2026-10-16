"""v0: extract local Markdown and PDF text with source and page metadata."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError


@dataclass(frozen=True)
class ExtractionIssue:
    code: str
    message: str
    page_number: int | None = None


@dataclass(frozen=True)
class ExtractedDocument:
    source_id: str
    source_version: str
    path: Path
    format: str
    text: str
    page_text: tuple[str, ...]
    issues: tuple[ExtractionIssue, ...] = ()

    @property
    def needs_ocr(self) -> bool:
        return any(issue.code == "ocr_required" for issue in self.issues)


def _require_metadata(source_id: str, source_version: str) -> None:
    if not source_id.strip():
        raise ValueError("source_id must be non-empty")
    if not source_version.strip():
        raise ValueError("source_version must be non-empty")


def extract_document(
    path: str | Path,
    source_id: str,
    source_version: str,
) -> ExtractedDocument:
    """Read a local document while retaining source and version metadata."""

    _require_metadata(source_id, source_version)
    document_path = Path(path)
    if not document_path.is_file():
        raise FileNotFoundError(document_path)

    suffix = document_path.suffix.lower()
    if suffix in {".md", ".markdown"}:
        text = document_path.read_text(encoding="utf-8")
        return ExtractedDocument(
            source_id,
            source_version,
            document_path,
            "markdown",
            text,
            (text,),
        )

    if suffix == ".pdf":
        try:
            reader = PdfReader(document_path, strict=True)
            if reader.is_encrypted:
                raise ValueError("encrypted PDF requires a password")
            pages = tuple(page.extract_text().strip() for page in reader.pages)
            if not pages:
                raise ValueError("PDF has no pages")
        except PdfReadError as exc:
            raise ValueError("PDF could not be parsed") from exc
        issues = tuple(
            ExtractionIssue(
                "ocr_required",
                "page contains no extractable text; inspect it for OCR",
                page_number=index,
            )
            for index, text in enumerate(pages, start=1)
            if not text
        )
        return ExtractedDocument(
            source_id,
            source_version,
            document_path,
            "pdf",
            "\n\f\n".join(pages),
            pages,
            issues,
        )

    raise ValueError(f"unsupported document format: {suffix or '<none>'}")
