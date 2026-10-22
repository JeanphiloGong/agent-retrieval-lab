# v0：固定问题与证据

这一版回答一个很小但容易被忽略的问题：我们怎样知道一次回答使用了正确的原文？读者扮演技术知识助手的评测者。样例只有错误码说明和退款政策两份文本，却保留三种真实查询：精确询问 `E104`、换一种说法询问退款期限，以及材料中没有答案的国际配送费用。

如果只看答案句子，下面两次回答都可能“听起来合理”：

```text
E104 means the connection timed out.       # 可能有依据
International shipping costs $20.          # 样例材料没有这句话
```

因此本版把“答案是否可回答”和“答案依据哪一段原文”记录下来。我们暂时不调用模型，也不做检索；先把以后所有实验都要遵守的证据契约固定住。

这是你手动构建的第一个版本。初始 `labs/` 没有 Python 实现；本页的代码由你依次写入。仓库提供固定输入和验收测试，`reference/` 保存预写答案供对照；参考代码通过测试不代表你的 v0 已经完成。先在仓库根目录执行 `uv sync --locked`，后面的命令均从仓库根目录运行，并且不设置 `PYTHONPATH=reference`。

## 先建立最小样例

来源清单位于 `fixtures/evaluation/sources.json`。它只允许两个稳定的来源身份：`errors/v1` 和 `policy/v1`。路径是清单旁的相对路径，验证器不会接受标注中任意填写的文件路径。数据已经随仓库提供，这一步只需阅读，后面由你创建验证器。

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

## 1. 创建包与记录类型

手工标注容易复制出重复 ID，或者把引用写成看似相近的另一行。我们先建立读取标注所需的类型，再检查引用是否真的来自原文。

在 `labs/` 下新建空文件 `__init__.py`，新建目录 `labs/evaluation/`，并在其中新建空文件 `__init__.py`。这两个文件把你自己的代码目录声明为 Python 包；不要复制 `reference/labs/`。

新建 `labs/evaluation/validate.py`，写入下面的第一部分：

```python
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
```

`Source` 保存允许引用的来源；`Evidence` 保存来源身份、版本、行范围和逐字引文；`Question` 把题目与它的金标准证据连在一起。`frozen=True` 防止验证过程中意外改写这些记录。`_load_json` 只负责 UTF-8 JSON 读取，下一步负责验证形状。

先确认你创建的包能导入：

```bash
uv run python -c 'from labs.evaluation.validate import Source, Evidence, Question; print("records ready")'
```

预期输出 `records ready`。此时还没有完整验证器，继续在同一个文件末尾追加。

## 2. 在文件边界检查字段与类型

来源清单决定能读哪些文件，问题标注只能引用清单中的身份。以下三个函数把 JSON 转成结构化记录：`load_sources` 检查清单，`_evidence` 检查一条证据，`load_questions` 检查整组问题。将本代码块完整追加到 `labs/evaluation/validate.py`：

```python
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
```

字段集合必须精确匹配，避免拼错字段却被忽略。行号使用 `type(...) is int`，因为 Python 中 `bool` 是 `int` 的子类，`isinstance(True, int)` 会误接受布尔值作为行号。这里的路径校验针对仓库提供的可信清单，不构成处理不可信文件系统的安全沙箱。

运行：

```bash
uv run python -c '
from pathlib import Path
from labs.evaluation.validate import load_questions
questions = load_questions(Path("fixtures/evaluation/questions.json"))
print(len(questions), questions[0].question_id)
'
```

预期输出 `3 error-meaning`。这里只证明 JSON 结构正确，还没有比较引文与真实原文。

## 3. 核对来源、行范围和引文

把下面两个函数继续追加到 `labs/evaluation/validate.py`：

```python
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
```

`validate_questions` 的返回值是错误列表；空列表表示这批标注通过校验。先加载所有来源，再逐条证据检查来源身份、合法行范围和逐字引文。人类标注的 `2..2` 被转换为 Python 切片 `[1:2]`，所以末端仍然包含第二行。

运行一次函数级检查：

```bash
uv run python -c '
from pathlib import Path
from labs.evaluation.validate import validate_questions
print(validate_questions(
    Path("fixtures/evaluation/questions.json"),
    Path("fixtures/evaluation/sources.json"),
))
'
```

预期输出 `[]`。现在即使题目的结构正确，错误的行号或引文也会被发现。

## 4. 增加命令行入口并验收 v0

将最后一部分追加到 `labs/evaluation/validate.py`：

```python
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
```

`build_parser` 将两个命令行路径转换为 `Path`。`main` 调用验证器，把错误打印到标准错误流并返回退出码 1，成功时返回 0。`SystemExit` 将这个返回值交给 shell。现在完整的 `validate.py` 就是本页四个代码块按顺序连接后的结果。

运行你自己的 v0：

```bash
uv run python -m labs.evaluation.validate \
  fixtures/evaluation/questions.json \
  fixtures/evaluation/sources.json
uv run python -m pytest -q tests/evaluation/test_validate.py
```

第一条命令预期输出：

```text
valid: fixtures/evaluation/questions.json
```

第二条命令只收集 v0 验收测试，不会要求你提前实现 v1 的检索器或 v2 的指标。测试覆盖合法标注、重复 ID、越界行号、错误引文、类型错误、未知来源和错误 CLI 输入。测试还会读取已提供的后续数据文件，验证器不需要知道后续检索逻辑。

## 让失败可观察

复制一份 `questions.json` 到临时位置，把第一条证据的 `end_line` 改成 `99`，然后用这个副本的路径替换命令中的第一个参数。验证器应该返回非零退出码，并报告：

```text
error: error-meaning: evidence 0 ends beyond errors-v1.txt (3 lines)
```

把副本中的 `quote` 改成 `wrong line` 也应该失败。复制 `question_id`、把可回答题的证据清空、给不可回答题添加证据，以及引用不存在的 `source_id/source_version`，都属于错误的输入契约。保留仓库原始样例不变，实验结束后删除自己的临时副本。

## 参考代码与自己的检查点

需要对照时阅读 [参考 v0/validate.py](../../../reference/labs/evaluation/checkpoints/v0/validate.py)。下面的命令明确运行参考答案，仅用于确认材料或对照输出：

```bash
PYTHONPATH=reference uv run python -P -m labs.evaluation.checkpoints.v0.validate \
  fixtures/evaluation/questions.json fixtures/evaluation/sources.json
```

`PYTHONPATH=reference` 选择参考区，`-P` 防止仓库当前目录优先导入你的 `labs` 包。完成学习验收时使用前面的普通命令，不加这两个参考区参数。

你的 v0 检查点包含：

```text
labs/__init__.py
labs/evaluation/__init__.py
labs/evaluation/validate.py
```

固定输入与 `tests/evaluation/test_validate.py` 已由仓库提供。等你自己实现、解释并通过上述检查后，再提交自己的学习检查点。本版没有检索或模型依赖，也没有预留统一 `Retriever` 类。

当前验证器证明标注结构正确、引用来自指定行，无法证明自然语言事实正确，也无法证明检索器能找回这些行。下一版在这个检查点上增加确定性的关键词检索。
