from __future__ import annotations

import unittest
from pathlib import Path

from labs.evaluation.keyword import load_documents, search, search_manifest


ROOT = Path(__file__).parents[2]
MANIFEST = ROOT / "fixtures" / "evaluation" / "sources.json"


class KeywordSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.documents = load_documents(MANIFEST)

    def test_exact_error_code_returns_real_location(self) -> None:
        results = search("E104", self.documents)
        self.assertEqual(len(results), 1)
        self.assertEqual(
            (results[0].source_id, results[0].source_version, results[0].start_line),
            ("errors", "v1", 2),
        )
        self.assertIn("timed out", results[0].text)

    def test_rewritten_refund_question_finds_policy_line(self) -> None:
        results = search("How long can a customer request a refund?", self.documents)
        self.assertEqual(results[0].source_id, "policy")
        self.assertEqual(results[0].start_line, 2)

    def test_empty_and_unknown_queries_have_no_results(self) -> None:
        self.assertEqual(search("", self.documents), [])
        self.assertEqual(search("database partition", self.documents), [])

    def test_limit_and_ties_are_deterministic(self) -> None:
        results = search("the", self.documents, limit=1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].source_id, "errors")
        with self.assertRaises(ValueError):
            search("E104", self.documents, limit=0)

    def test_manifest_entry_point_matches_loaded_documents(self) -> None:
        direct = search("E104", self.documents)
        via_manifest = search_manifest("E104", MANIFEST)
        self.assertEqual(via_manifest, direct)


if __name__ == "__main__":
    unittest.main()
