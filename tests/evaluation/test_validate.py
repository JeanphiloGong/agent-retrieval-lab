from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from labs.evaluation.validate import (
    load_questions,
    main,
    validate_questions,
)


ROOT = Path(__file__).parents[2]
FIXTURES = ROOT / "fixtures" / "evaluation"


class ValidationTests(unittest.TestCase):
    def test_checked_in_questions_are_valid(self) -> None:
        for filename in ("questions.json", "questions-v2-dev.json", "questions-v2-heldout.json"):
            self.assertEqual(
                validate_questions(FIXTURES / filename, FIXTURES / "sources.json"), []
            )

    def test_duplicate_id_is_rejected(self) -> None:
        data = json.loads((FIXTURES / "questions.json").read_text())
        data.append(data[0])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "questions.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            errors = validate_questions(path, FIXTURES / "sources.json")
        self.assertTrue(any("duplicate question_id" in error for error in errors))

    def test_bad_range_and_quote_are_rejected(self) -> None:
        data = json.loads((FIXTURES / "questions.json").read_text())
        data[0]["gold_evidence"][0]["end_line"] = 99
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "questions.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            errors = validate_questions(path, FIXTURES / "sources.json")
        self.assertTrue(any("ends beyond" in error for error in errors))

        data = json.loads((FIXTURES / "questions.json").read_text())
        data[0]["gold_evidence"][0]["quote"] = "wrong line"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "questions.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            errors = validate_questions(path, FIXTURES / "sources.json")
        self.assertTrue(any("quote does not match" in error for error in errors))

    def test_answerable_and_unanswerable_rules_are_rejected(self) -> None:
        data = json.loads((FIXTURES / "questions.json").read_text())
        data[0]["gold_evidence"] = []
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "questions.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            errors = validate_questions(path, FIXTURES / "sources.json")
        self.assertTrue(any("needs evidence" in error for error in errors))

        data = json.loads((FIXTURES / "questions.json").read_text())
        data[2]["gold_evidence"] = [data[0]["gold_evidence"][0]]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "questions.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            errors = validate_questions(path, FIXTURES / "sources.json")
        self.assertTrue(any("needs no evidence" in error for error in errors))

    def test_missing_file_and_invalid_json_fail_cli(self) -> None:
        output = StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            code = main([str(FIXTURES / "questions.json"), str(FIXTURES / "missing.json")])
        self.assertEqual(code, 1)
        self.assertIn("error:", output.getvalue())

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "questions.json"
            path.write_text("{", encoding="utf-8")
            output = StringIO()
            with redirect_stdout(output), redirect_stderr(output):
                code = main([str(path), str(FIXTURES / "sources.json")])
        self.assertEqual(code, 1)
        self.assertIn("error:", output.getvalue())

    def test_load_questions_returns_typed_records(self) -> None:
        questions = load_questions(FIXTURES / "questions.json")
        self.assertEqual(questions[0].question_id, "error-meaning")
        self.assertEqual(questions[2].gold_evidence, ())

    def test_bad_types_and_unknown_source_are_rejected(self) -> None:
        for field, value in (("answerable", "true"), ("question", 123)):
            with self.subTest(field=field):
                data = json.loads((FIXTURES / "questions.json").read_text())
                data[0][field] = value
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "questions.json"
                    path.write_text(json.dumps(data), encoding="utf-8")
                    self.assertTrue(validate_questions(path, FIXTURES / "sources.json"))
        data = json.loads((FIXTURES / "questions.json").read_text())
        data[0]["gold_evidence"][0]["source_id"] = "not-a-source"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "questions.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            self.assertTrue(any("missing source" in error for error in validate_questions(path, FIXTURES / "sources.json")))

    def test_development_and_heldout_ids_are_disjoint(self) -> None:
        dev = load_questions(FIXTURES / "questions-v2-dev.json")
        heldout = load_questions(FIXTURES / "questions-v2-heldout.json")
        self.assertFalse({question.question_id for question in dev} & {question.question_id for question in heldout})


if __name__ == "__main__":
    unittest.main()
