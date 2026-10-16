# v2：分别评估检索与回答

v1 可以告诉我们 `E104` 的第二行排在结果里，但“检索到了正确证据”和“回答支持了证据”是两个不同的断言。一个回答可能引用了正确行，却在文字中添加材料没有的费用；也可能回答“无法确定”而检索器其实已经找到了证据。本版把这两种质量分开。

## 两个数据集，两份问题

开发问题位于 `fixtures/evaluation/questions-v2-dev.json`，只包含错误码和退款期限。保留问题位于 `fixtures/evaluation/questions-v2-heldout.json`，包含一个无答案的国际配送费用问题和一个换写后的连接失败问题。它们都复用 v0 的来源身份和行范围，但不会在调参时混在一起。

回答记录单独存放在 `fixtures/evaluation/answers-v2-dev.json`。它记录模型（或人工回答）声称的 `answerable`、回答文本和 `cited_evidence`。答案文本不是本版的语言质量评测对象；我们先检查它是否做出正确的可回答判断、是否给出了非空答案，以及引用范围是否属于该题的 gold evidence。

## 先手算一遍检索指标

对两个可回答问题，假设结果如下：

```text
error-meaning: [policy line 2, errors line 2]
refund-window: [policy line 2]
```

在 `k=2` 时，两题都找到了 gold evidence，所以 Recall@2 是 `(1 + 1) / 2 = 1.0`。第一题正确证据排在第二位，第二题排在第一位，所以 MRR 是 `(1/2 + 1) / 2 = 0.75`。无答案题不进入这两个平均数；如果它返回了任意结果，单独记为 no-answer false positive。

`labs/evaluation/metrics.py` 的 `evaluate_retrieval` 正是这个计算。它使用来源身份和包含端点的范围作为稳定 evidence key，不把不同检索器的原始 score 混成一个尺度。返回的 `RetrievalReport` 同时包含整体 Recall@k、MRR、可回答题数量、无答案题数量、无答案误命中数量和每题明细。

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

## 再单独检查回答支持度

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
uv run python -m unittest tests.evaluation.test_metrics
```

测试手算了 `Recall@2=1.0`、`MRR=0.75`，也验证了 `k=1` 会改变排名指标而不会修改问题标签。另一个测试给退款题一个没有引用的回答：`answerable_accuracy` 仍可为 1.0，但 `support_rate` 只有 0.5。这正是两个报告不能合并成一个“准确率”的原因。不可回答题带有一条检索结果时，检索报告只增加 no-answer false positive，不会拉低可回答题的 Recall。

完整重放命令：

```bash
uv run python -m unittest discover -s tests/evaluation
```

## 完整代码检查点

本专题的完整 `checkpoint` 包位于 [checkpoints/v2](../../../labs/evaluation/checkpoints/v2)，其中 [metrics.py](../../../labs/evaluation/checkpoints/v2/metrics.py) 是本版新增的完整实现。它还保存了 v0 的验证器与 v1 的检索器，因此旧版不会悄悄依赖未来新行为。

以下命令使用冻结的 v2 包，并输出开发集的确定性结果：

```bash
uv run python -c '
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

v2 组装了本专题目前的完整检查点：

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
