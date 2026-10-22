"""Validate the small, line-addressable evaluation contract.

The validator deliberately has no retrieval or model dependency. It checks that
every annotation points at an allowed source and quotes the exact source lines.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


@dataclass(frozen=True)
class Source:
    source_id: str
    source_version: str
    path: Path


@dataclass(frozen=True)
class Evidence:
    source_id: str
    source_version: str
    start_line: int
    end_line: int
    quote: str


@dataclass(frozen=True)
class Question:
    question_id: str
    question: str
    answerable: bool
    gold_evidence: tuple[Evidence, ...]


def _load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_sources(path: Path) -> tuple[Source, ...]:
    """Load the trusted source allow-list and resolve its paths beside it."""

    raw = _load_json(path)
    if not isinstance(raw, list):
        raise ValueError("source manifest must be a JSON list")
    sources: list[Source] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"source manifest item {index} must be an object")
        if set(item) != {"source_id", "source_version", "path"}:
            raise ValueError(f"source manifest item {index} has invalid fields")
        if not all(isinstance(item[key], str) and item[key] for key in item):
            raise ValueError(f"source manifest item {index} has invalid values")
        relative = Path(item["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"source manifest item {index} has unsafe path")
        source = Source(
            source_id=item["source_id"],
            source_version=item["source_version"],
            path=(path.parent / relative).resolve(),
        )
        if any(
            (existing.source_id, existing.source_version)
            == (source.source_id, source.source_version)
            for existing in sources
        ):
            raise ValueError(
                f"duplicate source {source.source_id}/{source.source_version}"
            )
        if not source.path.is_file():
            raise ValueError(f"missing source file: {source.path}")
        sources.append(source)
    return tuple(sources)


def _evidence(item: Any, question_id: str, index: int) -> Evidence:
    if not isinstance(item, dict):
        raise ValueError(f"{question_id}: evidence {index} must be an object")
    fields = {"source_id", "source_version", "start_line", "end_line", "quote"}
    if set(item) != fields:
        raise ValueError(f"{question_id}: evidence {index} has invalid fields")
    if not isinstance(item["source_id"], str) or not item["source_id"]:
        raise ValueError(f"{question_id}: evidence {index} has invalid source_id")
    if not isinstance(item["source_version"], str) or not item["source_version"]:
        raise ValueError(f"{question_id}: evidence {index} has invalid source_version")
    if type(item["start_line"]) is not int or type(item["end_line"]) is not int:
        raise ValueError(f"{question_id}: evidence {index} line numbers must be integers")
    if not isinstance(item["quote"], str):
        raise ValueError(f"{question_id}: evidence {index} quote must be a string")
    return Evidence(
        source_id=item["source_id"],
        source_version=item["source_version"],
        start_line=item["start_line"],
        end_line=item["end_line"],
        quote=item["quote"],
    )


def load_questions(path: Path) -> tuple[Question, ...]:
    """Load annotations while checking their structural types."""

    raw = _load_json(path)
    if not isinstance(raw, list):
        raise ValueError("questions file must be a JSON list")
    questions: list[Question] = []
    ids: set[str] = set()
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"question {index} must be an object")
        fields = {"question_id", "question", "answerable", "gold_evidence"}
        if set(item) != fields:
            raise ValueError(f"question {index} has invalid fields")
        question_id = item["question_id"]
        if not isinstance(question_id, str) or not question_id:
            raise ValueError(f"question {index} has invalid question_id")
        if question_id in ids:
            raise ValueError(f"duplicate question_id: {question_id}")
        ids.add(question_id)
        if not isinstance(item["question"], str) or not item["question"].strip():
            raise ValueError(f"{question_id}: question must be nonempty text")
        if type(item["answerable"]) is not bool:
            raise ValueError(f"{question_id}: answerable must be boolean")
        if not isinstance(item["gold_evidence"], list):
            raise ValueError(f"{question_id}: gold_evidence must be a list")
        evidence = tuple(
            _evidence(value, question_id, evidence_index)
            for evidence_index, value in enumerate(item["gold_evidence"])
        )
        if item["answerable"] and not evidence:
            raise ValueError(f"{question_id}: answerable question needs evidence")
        if not item["answerable"] and evidence:
            raise ValueError(f"{question_id}: unanswerable question needs no evidence")
        questions.append(
            Question(
                question_id=question_id,
                question=item["question"],
                answerable=item["answerable"],
                gold_evidence=evidence,
            )
        )
    return tuple(questions)


def _read_lines(source: Source) -> list[str]:
    try:
        return source.path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise ValueError(f"source is not UTF-8: {source.path}") from exc


def validate_questions(question_path: Path, source_manifest_path: Path) -> list[str]:
    """Return human-readable annotation errors; an empty list means valid."""

    try:
        sources = load_sources(source_manifest_path)
        questions = load_questions(question_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return [str(exc)]

    by_key = {(source.source_id, source.source_version): source for source in sources}
    lines_by_key: dict[tuple[str, str], list[str]] = {}
    errors: list[str] = []
    for source in sources:
        try:
            lines_by_key[(source.source_id, source.source_version)] = _read_lines(source)
        except (OSError, ValueError) as exc:
            errors.append(str(exc))

    for question in questions:
        for evidence_index, evidence in enumerate(question.gold_evidence):
            key = (evidence.source_id, evidence.source_version)
            source = by_key.get(key)
            if source is None:
                errors.append(
                    f"{question.question_id}: evidence {evidence_index} references "
                    f"missing source {evidence.source_id}/{evidence.source_version}"
                )
                continue
            lines = lines_by_key.get(key)
            if lines is None:
                continue
            if evidence.start_line < 1 or evidence.end_line < evidence.start_line:
                errors.append(
                    f"{question.question_id}: evidence {evidence_index} has invalid range"
                )
                continue
            if evidence.end_line > len(lines):
                errors.append(
                    f"{question.question_id}: evidence {evidence_index} ends beyond "
                    f"{source.path.name} ({len(lines)} lines)"
                )
                continue
            expected = "\n".join(lines[evidence.start_line - 1 : evidence.end_line])
            if evidence.quote != expected:
                errors.append(
                    f"{question.question_id}: evidence {evidence_index} quote does not "
                    "match the selected source lines"
                )
    return errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate evaluation annotations")
    parser.add_argument("questions", type=Path)
    parser.add_argument("sources", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    errors = validate_questions(args.questions, args.sources)
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"valid: {args.questions}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
