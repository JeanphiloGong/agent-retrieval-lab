"""Separate retrieval ranking metrics from answer citation support."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from .validate import Question


@dataclass(frozen=True)
class RetrievalReport:
    recall_at_k: float
    mrr: float
    answerable_count: int
    no_answer_count: int
    no_answer_false_positive_count: int
    per_question: dict[str, dict[str, float | int | bool]]


@dataclass(frozen=True)
class AnswerReport:
    answerable_accuracy: float
    support_rate: float
    answer_count: int
    supported_count: int
    no_answer_accuracy: float
    unsupported_question_ids: tuple[str, ...]


def _value(item: Any, name: str) -> Any:
    if isinstance(item, Mapping):
        return item.get(name)
    return getattr(item, name, None)


def evidence_key(item: Any) -> tuple[Any, ...]:
    """Use source and inclusive line range as the stable evidence identity."""

    return (
        _value(item, "source_id"),
        _value(item, "source_version"),
        _value(item, "start_line"),
        _value(item, "end_line"),
    )


def evaluate_retrieval(
    questions: Sequence[Question],
    rankings: Mapping[str, Iterable[Any]],
    *,
    k: int = 5,
) -> RetrievalReport:
    """Calculate ranking quality for answerable questions and no-answer safety.

    Recall is the fraction of gold evidence ranges found in the first ``k``
    results. MRR uses the rank of the first matching range. Unanswerable
    questions are reported separately so they do not look like failed recall.
    """

    if k < 1:
        raise ValueError("k must be positive")
    answerable = [question for question in questions if question.answerable]
    no_answer = [question for question in questions if not question.answerable]
    recall_total = 0.0
    reciprocal_total = 0.0
    false_positives = 0
    per_question: dict[str, dict[str, float | int | bool]] = {}
    for question in questions:
        results = list(rankings.get(question.question_id, ()))[:k]
        if not question.answerable:
            false_positive = bool(results)
            false_positives += false_positive
            per_question[question.question_id] = {
                "answerable": False,
                "false_positive": false_positive,
                "result_count": len(results),
            }
            continue
        gold = {evidence_key(evidence) for evidence in question.gold_evidence}
        found = {evidence_key(result) for result in results} & gold
        recall = len(found) / len(gold)
        first_rank = next(
            (rank for rank, result in enumerate(results, start=1) if evidence_key(result) in gold),
            None,
        )
        reciprocal = 0.0 if first_rank is None else 1.0 / first_rank
        recall_total += recall
        reciprocal_total += reciprocal
        per_question[question.question_id] = {
            "answerable": True,
            "recall": recall,
            "reciprocal_rank": reciprocal,
            "result_count": len(results),
        }
    answerable_count = len(answerable)
    return RetrievalReport(
        recall_at_k=recall_total / answerable_count if answerable_count else 0.0,
        mrr=reciprocal_total / answerable_count if answerable_count else 0.0,
        answerable_count=answerable_count,
        no_answer_count=len(no_answer),
        no_answer_false_positive_count=false_positives,
        per_question=per_question,
    )


def _is_supported(question: Question, answer: Any) -> bool:
    predicted_answerable = _value(answer, "answerable")
    text = _value(answer, "answer")
    citations = _value(answer, "cited_evidence")
    if type(predicted_answerable) is not bool or not isinstance(text, str) or not text.strip():
        return False
    if not isinstance(citations, list):
        return False
    if predicted_answerable != question.answerable:
        return False
    if not question.answerable:
        return not citations
    gold = {evidence_key(evidence) for evidence in question.gold_evidence}
    cited = {evidence_key(evidence) for evidence in citations}
    gold_quotes = {
        evidence_key(evidence): evidence.quote for evidence in question.gold_evidence
    }
    return (
        bool(cited)
        and cited <= gold
        and all(
            _value(evidence, "quote") == gold_quotes[evidence_key(evidence)]
            for evidence in citations
        )
    )


def evaluate_answer_support(
    questions: Sequence[Question],
    answers: Mapping[str, Any],
) -> AnswerReport:
    """Score citation support independently from where retrieval ranked results."""

    if not questions:
        raise ValueError("questions must not be empty")
    supported = 0
    answerable_correct = 0
    no_answer_correct = 0
    unsupported: list[str] = []
    answerable_total = 0
    no_answer_total = 0
    for question in questions:
        if question.answerable:
            answerable_total += 1
        else:
            no_answer_total += 1
        answer = answers.get(question.question_id)
        if answer is None:
            unsupported.append(question.question_id)
            continue
        predicted = _value(answer, "answerable")
        if type(predicted) is bool and predicted == question.answerable:
            if question.answerable:
                answerable_correct += 1
            else:
                no_answer_correct += 1
        if _is_supported(question, answer):
            supported += 1
        else:
            unsupported.append(question.question_id)
    return AnswerReport(
        answerable_accuracy=(answerable_correct / answerable_total if answerable_total else 0.0),
        support_rate=supported / len(questions),
        answer_count=len(answers),
        supported_count=supported,
        no_answer_accuracy=(no_answer_correct / no_answer_total if no_answer_total else 0.0),
        unsupported_question_ids=tuple(unsupported),
    )
