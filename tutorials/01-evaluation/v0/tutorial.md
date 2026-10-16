# v0：固定问题与证据

这一版回答一个很小但容易被忽略的问题：我们怎样知道一次回答使用了正确的原文？读者扮演技术知识助手的评测者。样例只有错误码说明和退款政策两份文本，却保留三种真实查询：精确询问 `E104`、换一种说法询问退款期限，以及材料中没有答案的国际配送费用。

如果只看答案句子，下面两次回答都可能“听起来合理”：

```text
E104 means the connection timed out.       # 可能有依据
International shipping costs $20.           # 样例材料没有这句话
```

因此本版把“答案是否可回答”和“答案依据哪一段原文”记录下来。我们暂时不调用模型，也不做检索；先把以后所有实验都要遵守的证据契约固定住。

## 先建立最小样例

来源清单位于 `fixtures/evaluation/sources.json`。它只允许两个稳定的来源身份：`errors/v1` 和 `policy/v1`。路径是清单旁的相对路径，验证器不会接受标注中任意填写的文件路径。

错误码原文 `fixtures/evaluation/sources/errors-v1.txt` 的第二行是：

```text
E104 means that the client connection timed out while contacting the service.
```

政策原文 `fixtures/evaluation/sources/policy-v1.txt` 的第二行是：

```text
Customers may request a refund within seven days of purchase.
```

标注文件 `fixtures/evaluation/questions.json` 用以下形状表达一题：

```json
{
  "question_id": "error-meaning",
  "question": "What does error E104 mean?",
  "answerable": true,
  "gold_evidence": [
    {
      "source_id": "errors",
      "source_version": "v1",
      "start_line": 2,
      "end_line": 2,
      "quote": "E104 means that the client connection timed out while contacting the service."
    }
  ]
}
```

行号从 1 开始，并且两端都包含。第三题 `international-shipping-cost` 的 `answerable` 是 `false`，其 `gold_evidence` 必须是空数组。无答案是合法结果，不应该被伪造的引用填满。

## 第一个压力：手工标注会悄悄指错行

最朴素的做法是打开文本、凭印象记下“第二行”。它无法发现两类错误：复制了重复的 `question_id`，或者把 `quote` 写成看似相近的另一行。错误会一直留到检索或回答阶段才暴露，而且那时已经无法判断是检索错还是基准错。

所以只增加一个边界检查器。`labs/evaluation/validate.py` 中的 `load_sources` 读取可信来源清单，`load_questions` 读取并检查 JSON 的字段和类型，`validate_questions` 再把每条证据映射回来源并比较真实行内容。三个函数都只读文件，不修改输入。

运行完整的 v0 检查点：

```bash
uv run python -m labs.evaluation.validate \
  fixtures/evaluation/questions.json \
  fixtures/evaluation/sources.json
```

预期输出：

```text
valid: fixtures/evaluation/questions.json
```

这就是本步的 `checkpoint`：来源清单、三道题和一个可重放的验证命令共同组成了最小基线。

## 让失败可观察

复制一份 `questions.json`，把第一条证据的 `end_line` 改成 `99`，再运行同一命令。验证器应该返回非零退出码，并报告类似下面的错误：

```text
error: error-meaning: evidence 0 ends beyond errors-v1.txt (3 lines)
```

把 `quote` 改成 `wrong line` 也应该失败。复制 `question_id`、把可回答题的证据清空、给不可回答题添加证据，以及引用不存在的 `source_id/source_version`，都属于错误的输入契约，而不是“模型可能答错”。

## 代码边界

本版故意没有定义统一的 `Retriever` 类，也没有预留向量数据库接口。当前 helper 的职责很小：来源清单决定能读哪些文件，问题记录决定期待哪些证据，验证器只检查两者是否一致。UTF-8 文本和行号是本版的压缩模型；PDF 页码、HTML DOM 范围和多租户授权会在后续专题另行定义。

从仓库根目录重放测试：

```bash
uv run python -m unittest discover -s tests/evaluation
```

当前检查点能证明标注记录结构正确、引用确实来自指定行。它仍然不能证明检索器能找回这些行，也不能证明一个自然语言答案忠于引用。下一版只处理前一个缺口：用确定性的关键词基线返回真实位置。

## 完整代码检查点

本版的完整代码已保存在 [v0/validate.py](../../../labs/evaluation/checkpoints/v0/validate.py)；这是独立的 `checkpoint`，不是指向未来最新版的链接。来源清单、问题文件和原文沿用本页已解释的固定 v1 数据。从仓库根目录执行精确的旧版验证器：

```bash
uv run python -m labs.evaluation.checkpoints.v0.validate \
  fixtures/evaluation/questions.json fixtures/evaluation/sources.json
```

逐个看完整文件时，先从 `main` 开始：它解析两个路径，调用 `validate_questions`，把非空错误列表转成退出码 1。`validate_questions` 先建立来源身份到文件的映射，再逐条检查 `gold_evidence` 的范围和原文。`load_questions` 在外部输入边界拒绝错误字段和类型，后面的验证循环就可以使用结构化记录，而不需要反复猜 JSON 的形状。

## Checkpoint

冻结以下文件作为 v0：

```text
fixtures/evaluation/sources.json
fixtures/evaluation/sources/errors-v1.txt
fixtures/evaluation/sources/policy-v1.txt
fixtures/evaluation/questions.json
labs/evaluation/validate.py
tests/evaluation/test_validate.py
```

验证器是一个永久的边界，不是对人工标注语义正确性的证明。若有人把错误的事实写进合法行号，v0 会接受；这正是 v1 需要单独观察检索质量的原因。
