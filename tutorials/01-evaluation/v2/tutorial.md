# v2：分别评估检索与回答

v1 可以告诉我们 `E104` 的第二行排在结果里，但“检索到了正确证据”和“回答受到证据支持”是两个不同的断言。一个回答可能引用了正确行，却在文字中添加材料没有的费用；也可能回答“无法确定”而检索器其实已经找到了证据。本版把这两种质量分开。

## 两个数据集，两份问题

开发问题位于 `fixtures/evaluation/questions-v2-dev.json`，只包含错误码和退款期限。保留问题位于 `fixtures/evaluation/questions-v2-heldout.json`，包含一个无答案的国际配送费用问题和一个换写后的连接失败问题。它们都复用 v0 的来源身份和行范围，但不会在调参时混在一起。

回答记录单独存放在 `fixtures/evaluation/answers-v2-dev.json`。它记录模型（或人工回答）声称的 `answerable`、回答文本和 `cited_evidence`。答案文本不是本版的语言质量评测对象；我们先检查它是否做出正确的可回答判断、是否给出了非空答案，以及引用范围是否属于该题的 gold evidence。

## 1. 定义两个报告和证据身份

本版从你自己完成的 v1 开始，保留 `validate.py` 和 `keyword.py`。新建 `labs/evaluation/metrics.py`，先写入以下内容：

```python
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
```

检索器输出的是 `SearchResult`，回答文件中的引用是字典。`_value` 在这个评测输入边界读取同名字段，让 `evidence_key` 可以提取同一组位置身份；它不负责生成检索结果或修改引用。`RetrievalReport` 和 `AnswerReport` 分开保存结果，避免一个总分掩盖不同故障。

此时可以检查身份规则：

```bash
uv run python -c '
from labs.evaluation.metrics import evidence_key
print(evidence_key({"source_id": "errors", "source_version": "v1", "start_line": 2, "end_line": 2}))
'
```

预期输出 `('errors', 'v1', 2, 2)`。排名分数与文本没有进入身份；同一位置不会因为检索算法改变而变成另一个证据。

## 2. 实现并手算检索指标

对两个可回答问题，假设结果如下：

```text
error-meaning: [policy line 2, errors line 2]
refund-window: [policy line 2]
```

在 `k=2` 时，两题都找到了 gold evidence，所以 Recall@2 是 `(1 + 1) / 2 = 1.0`。第一题正确证据排在第二位，第二题排在第一位，所以 MRR 是 `(1/2 + 1) / 2 = 0.75`。无答案题不进入这两个平均数；如果它返回了任意结果，单独记为 no-answer false positive。

`labs/evaluation/metrics.py` 的 `evaluate_retrieval` 正是这个计算。它使用来源身份和包含端点的范围作为稳定 evidence key，不把不同检索器的原始 score 混成一个尺度。返回的 `RetrievalReport` 同时包含整体 Recall@k、MRR、可回答题数量、无答案题数量、无答案误命中数量和每题明细。

在 `labs/evaluation/metrics.py` 末尾追加以下完整函数：

```python
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
```

先按 `k` 截断结果，再用证据身份集合计算命中数，所以重复结果不会重复增加 Recall。`next(..., None)` 找到第一条正确证据的排名，未命中时贡献 0。无答案问题的任何候选都记作误命中，这是本基线明确选择的保守规则；它不是最终回答是否幻觉的判断。

调用方式：

```python
from pathlib import Path

from labs.evaluation.keyword import load_documents, search
from labs.evaluation.metrics import evaluate_retrieval
from labs.evaluation.validate import load_questions

root = Path("fixtures/evaluation")
questions = load_questions(root / "questions-v2-dev.json")
documents = load_documents(root / "sources.json")
rankings = {
    question.question_id: search(question.question, documents)
    for question in questions
}
report = evaluate_retrieval(questions, rankings, k=5)
print(report.recall_at_k, report.mrr)
```

## 3. 再单独检查回答支持度

继续在同一文件末尾追加下面两个函数：

```python
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
```

`_is_supported` 判定一条回答的引用契约，`evaluate_answer_support` 遍历问题并汇总。缺失回答仍进入问题总数，因此不能靠省略难题提高支持率。`answerable_accuracy` 的分母仅包含实际可回答的问题；实际不可回答问题另看 `no_answer_accuracy`。没有某一类问题时相应值返回 0，不应将它当成该类质量已经验证。

至此 `metrics.py` 的三个代码块已按顺序组装完整，可以运行本页下面的调用示例。

`evaluate_answer_support` 不读取检索排名。它只读取问题的 gold evidence 和回答记录：可回答问题必须预测 `answerable=true`、有非空文本，并引用至少一条且全部属于 gold evidence，引用原文也必须逐字相等；不可回答问题必须预测 `false`、有说明性文本且不携带引用。这样，“检索排名很好但回答没有依据”和“回答有依据但检索排名靠后”会落在不同报告中。

```python
import json

from labs.evaluation.metrics import evaluate_answer_support

answers = {
    item["question_id"]: item
    for item in json.loads((root / "answers-v2-dev.json").read_text())
}
answer_report = evaluate_answer_support(questions, answers)
print(answer_report.answerable_accuracy)
print(answer_report.support_rate)
```

开发集中的两条回答都引用了精确金标准范围，所以支持度报告会将它们记为 supported。这个判断仍然没有理解自然语言事实：如果回答把“七天”改成“七十天”，但继续引用正确行，本版不会发现语义矛盾。那属于需要人工标注或校准后的 LLM-as-judge 的后续工作，不能伪装成这里的确定性指标。

## 重放与反例

运行 v2 测试：

```bash
uv run python -m pytest -q tests/evaluation/test_metrics.py
```

测试手算了 `Recall@2=1.0`、`MRR=0.75`，也验证了 `k=1` 会改变排名指标而不会修改问题标签。另一个测试给退款题一个没有引用的回答：`answerable_accuracy` 仍可为 1.0，但 `support_rate` 只有 0.5。这正是两个报告不能合并成一个“准确率”的原因。不可回答题带有一条检索结果时，检索报告只增加 no-answer false positive，不会拉低可回答题的 Recall。

完整重放命令：

```bash
uv run python -m pytest -q tests/evaluation
```

## 完整代码检查点

预写参考包位于 [reference/checkpoints/v2](../../../reference/labs/evaluation/checkpoints/v2)，其中 [metrics.py](../../../reference/labs/evaluation/checkpoints/v2/metrics.py) 是本版新增实现的对照。它还保存了 v0 的验证器与 v1 的检索器。参考代码已备好，你自己的进度由普通命令针对 `labs/` 的验收决定。

以下命令显式运行参考 v2，输出开发集的确定性结果。运行自己的实现时，去掉 `PYTHONPATH=reference` 和 `-P`，并将三个导入路径的 `.checkpoints.v2` 删除：

```bash
PYTHONPATH=reference uv run python -P -c '
import json
from pathlib import Path
from labs.evaluation.checkpoints.v2.validate import load_questions
from labs.evaluation.checkpoints.v2.keyword import load_documents, search
from labs.evaluation.checkpoints.v2.metrics import evaluate_retrieval, evaluate_answer_support
root = Path("fixtures/evaluation")
questions = load_questions(root / "questions-v2-dev.json")
documents = load_documents(root / "sources.json")
rankings = {q.question_id: search(q.question, documents) for q in questions}
retrieval = evaluate_retrieval(questions, rankings, k=5)
answers = {a["question_id"]: a for a in json.loads((root / "answers-v2-dev.json").read_text())}
support = evaluate_answer_support(questions, answers)
print(retrieval.recall_at_k, retrieval.mrr, support.support_rate)
'
```

预期为 `1.0 0.75 1.0`。错误码题中的 `error` 也命中了标题，和 `E104` 所在行同分，按行号排序后正确证据排在第二位，所以 MRR 低于 Recall。这个结果只描述当前两道开发题，不能推导检索器在未知语料上的效果。

## Checkpoint

当你自己实现并通过整个 `tests/evaluation` 后，v2 才成为你的完整学习检查点：

```text
fixtures/evaluation/sources.json
fixtures/evaluation/sources/*.txt
fixtures/evaluation/questions.json
fixtures/evaluation/questions-v2-dev.json
fixtures/evaluation/questions-v2-heldout.json
fixtures/evaluation/answers-v2-dev.json
labs/evaluation/validate.py
labs/evaluation/keyword.py
labs/evaluation/metrics.py
tests/evaluation/*.py
```

这条基线现在能重放标注校验、关键词排名、Recall@k、MRR、无答案误命中和引用支持度，并且知道开发集与保留集的边界。它还没有 BM25、向量索引、reranker、文档树或 Agent 工具选择；下一专题可以在这组固定评测上引入这些机制，比较它们到底改善了哪一类问题。
