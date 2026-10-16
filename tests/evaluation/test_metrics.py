from __future__ import annotations

import unittest
from pathlib import Path

from labs.evaluation.keyword import SearchResult
from labs.evaluation.metrics import evaluate_answer_support, evaluate_retrieval
from labs.evaluation.validate import load_questions


ROOT = Path(__file__).parents[2]
FIXTURES = ROOT / "fixtures" / "evaluation"


def result(source: str, line: int) -> SearchResult:
    return SearchResult(source, "v1", line, line, "fixture", 1)


class MetricTests(unittest.TestCase):
    def test_recall_mrr_and_no_answer_are_separate(self) -> None:
        questions = load_questions(FIXTURES / "questions.json")
        rankings = {
            "error-meaning": [result("policy", 2), result("errors", 2)],
            "refund-window": [result("policy", 2)],
            "international-shipping-cost": [result("policy", 2)],
        }
        report = evaluate_retrieval(questions, rankings, k=2)
        self.assertAlmostEqual(report.recall_at_k, 1.0)
        self.assertAlmostEqual(report.mrr, 0.75)  # (1/2 + 1) / 2
        self.assertEqual(report.answerable_count, 2)
        self.assertEqual(report.no_answer_count, 1)
        self.assertEqual(report.no_answer_false_positive_count, 1)
        self.assertEqual(report.per_question["error-meaning"]["recall"], 1.0)

    def test_k_changes_mrr_without_mutating_question_labels(self) -> None:
        questions = load_questions(FIXTURES / "questions.json")[:2]
        rankings = {
            "error-meaning": [result("policy", 2), result("errors", 2)],
            "refund-window": [result("policy", 2)],
        }
        report = evaluate_retrieval(questions, rankings, k=1)
        self.assertEqual(report.recall_at_k, 0.5)
        self.assertEqual(report.mrr, 0.5)

    def test_answer_support_is_independent_of_retrieval_rank(self) -> None:
        questions = load_questions(FIXTURES / "questions-v2-dev.json")
        answers = {
            "error-meaning": {
                "answerable": True,
                "answer": "E104 is a connection timeout.",
                "cited_evidence": [
                    {
                        "source_id": "errors",
                        "source_version": "v1",
                        "start_line": 2,
                        "end_line": 2,
                        "quote": "E104 means that the client connection timed out while contacting the service.",
                    }
                ],
            },
            "refund-window": {
                "answerable": True,
                "answer": "Refunds are always available.",
                "cited_evidence": [],
            },
        }
        report = evaluate_answer_support(questions, answers)
        self.assertEqual(report.answer_count, 2)
        self.assertEqual(report.answerable_accuracy, 1.0)
        self.assertEqual(report.support_rate, 0.5)
        self.assertEqual(report.unsupported_question_ids, ("refund-window",))

    def test_unanswerable_answer_requires_no_citations(self) -> None:
        questions = load_questions(FIXTURES / "questions.json")[2:]
        answers = {
            "international-shipping-cost": {
                "answerable": False,
                "answer": "The supplied material does not state a fee.",
                "cited_evidence": [],
            }
        }
        report = evaluate_answer_support(questions, answers)
        self.assertEqual(report.no_answer_accuracy, 1.0)
        self.assertEqual(report.support_rate, 1.0)

    def test_missing_answer_counts_in_denominator(self) -> None:
        questions = load_questions(FIXTURES / "questions.json")[:2]
        answers = {
            "error-meaning": {
                "answerable": True,
                "answer": "E104 is a timeout.",
                "cited_evidence": [],
            }
        }
        report = evaluate_answer_support(questions, answers)
        self.assertEqual(report.answerable_accuracy, 0.5)
        self.assertEqual(report.support_rate, 0.0)

    def test_right_location_with_fabricated_quote_is_unsupported(self) -> None:
        questions = load_questions(FIXTURES / "questions.json")[:1]
        answers = {
            "error-meaning": {
                "answerable": True,
                "answer": "E104 means authentication failed.",
                "cited_evidence": [
                    {
                        "source_id": "errors",
                        "source_version": "v1",
                        "start_line": 2,
                        "end_line": 2,
                        "quote": "E104 means authentication failed.",
                    }
                ],
            }
        }
        self.assertEqual(evaluate_answer_support(questions, answers).support_rate, 0.0)


if __name__ == "__main__":
    unittest.main()
