# v1：关键词基线

v0 已经能证明 `E104` 的金标准引用确实指向错误说明的第二行，但它还不能回答“检索器能不能找回这一行”。本版从 v0 的固定来源和问题开始，增加一个可重复的关键词搜索器。

## 先看缺口

如果调用方只能拿到一串来源文件，它仍然要自己打开每份文件、自己猜应该返回哪一行：

```python
for source in sources:
    print(source.read_text())
```

这段代码没有查询、排序或稳定位置。即便它打印了正确文本，评测也无法区分“找到了错误码所在行”和“恰好把整份文件打印出来”。v0 的 `gold_evidence` 已经给出明确目标：结果必须含有 `source_id`、版本和包含端点的行范围。

## 1. 创建带位置的行记录

本版从你已通过 v0 验收的 `labs/evaluation/validate.py` 开始。参考区不进入普通导入路径；下面的新文件由你在自己的 `labs/` 中创建。

新建 `labs/evaluation/keyword.py`，先写入：

```python
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .validate import load_sources

TOKEN = re.compile(r"[A-Za-z0-9]+")


@dataclass(frozen=True)
class DocumentLine:
    source_id: str
    source_version: str
    line_number: int
    text: str


@dataclass(frozen=True)
class SearchResult:
    source_id: str
    source_version: str
    start_line: int
    end_line: int
    text: str
    score: int


def tokenize(text: str) -> tuple[str, ...]:
    """Return lowercase alphanumeric terms while preserving code-like IDs."""

    return tuple(match.group(0).lower() for match in TOKEN.finditer(text))


def load_documents(source_manifest_path: Path) -> tuple[DocumentLine, ...]:
    """Read each allow-listed source as independent, addressable lines."""

    documents: list[DocumentLine] = []
    for source in load_sources(source_manifest_path):
        lines = source.path.read_text(encoding="utf-8").splitlines()
        documents.extend(
            DocumentLine(
                source_id=source.source_id,
                source_version=source.source_version,
                line_number=line_number,
                text=text,
            )
            for line_number, text in enumerate(lines, start=1)
        )
    return tuple(documents)
```

`load_documents` 复用 v0 的来源清单，每行生成一个 `DocumentLine`。`enumerate(..., start=1)` 保持与标注一致的行号。`tokenize` 提取字母数字并转小写，让 `E104` 保留为 `e104`。这个规则面向本专题英文样例，尚不提供中文分词。

先运行一个小检查：

```bash
uv run python -c '
from pathlib import Path
from labs.evaluation.keyword import load_documents, tokenize
documents = load_documents(Path("fixtures/evaluation/sources.json"))
print(tokenize("Error E104!"))
print(next(line for line in documents if "E104" in line.text))
'
```

输出应包含 `('error', 'e104')`，以及 `source_id='errors'`、`line_number=2` 的记录。

## 2. 计算重叠分数并稳定排序

继续在 `labs/evaluation/keyword.py` 末尾追加：

```python
def search(
    query: str,
    documents: Iterable[DocumentLine],
    *,
    limit: int = 5,
) -> list[SearchResult]:
    """Rank source lines by how many query terms they contain.

    This is intentionally a baseline: it has no stemming, synonym expansion,
    embeddings, or cross-line passage construction. Ties use source identity
    and line number so the same input always produces the same ranking.
    """

    if limit < 1:
        raise ValueError("limit must be positive")
    query_terms = tokenize(query)
    if not query_terms:
        return []
    term_set = set(query_terms)
    results: list[SearchResult] = []
    for document in documents:
        score = len(term_set & set(tokenize(document.text)))
        if score:
            results.append(
                SearchResult(
                    source_id=document.source_id,
                    source_version=document.source_version,
                    start_line=document.line_number,
                    end_line=document.line_number,
                    text=document.text,
                    score=score,
                )
            )
    results.sort(
        key=lambda result: (
            -result.score,
            result.source_id,
            result.source_version,
            result.start_line,
        )
    )
    return results[:limit]


def search_manifest(
    query: str,
    source_manifest_path: Path,
    *,
    limit: int = 5,
) -> list[SearchResult]:
    """Convenience entry point used by the tutorial and command examples."""

    return search(query, load_documents(source_manifest_path), limit=limit)
```

`search` 只读取传入的行记录，不做文件 I/O。查询词与行词元的集合交集大小就是分数，因此重复写 `E104 E104` 不会翻倍加分。`search_manifest` 是本教程实际使用的文件入口，将加载与检索连起来。

分数前的负号实现降序；相同分数按来源 ID、版本、行号升序排序。这保证同样的输入不会因为列表顺序或多次运行而改变排名。它也意味着通用词可能把标题排到事实行之前，v2 会用 MRR 把这个问题显示出来。

## 3. 用查询调用刚完成的实现

`labs/evaluation/keyword.py` 把每个来源拆成 `DocumentLine`。`tokenize` 用一个很小的规则把字母数字序列转成小写词元，所以 `E104` 会保留为 `e104`，而标点不会影响匹配。`search` 对每一行计算查询词的重叠数量，只保留分数大于零的行，然后按分数、来源身份和行号排序。后两项是 tie-breaker，保证相同输入每次得到相同结果。

本版的 `checkpoint` API 是：

```python
from pathlib import Path

from labs.evaluation.keyword import search_manifest

results = search_manifest(
    "E104",
    Path("fixtures/evaluation/sources.json"),
    limit=5,
)
```

每一个 `SearchResult` 都带有 `source_id`、`source_version`、`start_line`、`end_line`、原文 `text` 和整数 `score`。因此调用方不需要从一段自由文本里猜证据位置。

运行一个精确查询：

```bash
uv run python -c '
from pathlib import Path
from labs.evaluation.keyword import search_manifest

for result in search_manifest("E104", Path("fixtures/evaluation/sources.json")):
    print(result)
'
```

输出包含：

```text
SearchResult(source_id='errors', source_version='v1', start_line=2, end_line=2, ...)
```

换一种说法询问退款期限也会返回 `policy/v1` 的第二行，因为查询中仍然包含 `refund`。完全空白查询和材料里不存在的 `database partition` 都返回空列表；它们不会被改写成“最相近的一行”。`limit` 必须为正数，避免调用方把 `0` 的含义误解成“没有限制”。

## 这只是基线

这个搜索器按行独立评分，不做词干化、同义词扩展、向量表示或跨行段落构建。查询 `connection timeout` 能找到错误行，但概念改写可能只共享一个词，排名未必可靠；一条需要前后两行共同解释的证据也不应被当成单行事实。我们保留这些限制，因为它们让下一版能测量改进，而不是把所有策略藏在一个不可解释的抽象后面。

测试覆盖精确命中、语义改写、无命中、空查询、并列排序和非法 `limit`：

```bash
uv run python -m pytest -q tests/evaluation/test_keyword.py
```

同时回归自己已完成的 v0 和 v1；先不要收集尚未实现的 v2 测试：

```bash
uv run python -m pytest -q tests/evaluation/test_validate.py tests/evaluation/test_keyword.py
```

## 完整代码检查点

预写参考包位于 [reference/checkpoints/v1](../../../reference/labs/evaluation/checkpoints/v1)，包含本版的 [keyword.py](../../../reference/labs/evaluation/checkpoints/v1/keyword.py) 和 v0 验证契约。它用于对照，不是你已经完成的学习检查点。以下命令显式选择参考区；验收自己的代码继续使用上面的普通命令：

```bash
PYTHONPATH=reference uv run python -P -c '
from pathlib import Path
from labs.evaluation.checkpoints.v1.keyword import search_manifest
assert search_manifest("E104", Path("fixtures/evaluation/sources.json"))[0].start_line == 2
'
```

完整文件中的数据流是 `search_manifest` → `load_documents` → `search`。前两个函数只读取清单和原文；`search` 不做文件 I/O，只把查询和已加载的行转换为排序结果。`DocumentLine` 保存原文位置，`SearchResult` 增加本次查询的分数；两者都不会修改原文。

## Checkpoint

当你自己写完新文件、理解排序结果并通过上述 v0/v1 测试后，可以冻结自己的 v1。新增实现是：

```text
labs/evaluation/keyword.py
tests/evaluation/test_keyword.py
```

测试文件已由仓库提供，需要你新建的是 `keyword.py`。它依赖 v0 的来源清单和原文，不复制一份隐含的语料。当前检查点能返回可核验的候选位置；它仍然没有回答“返回了相关位置后，最终回答是否忠于证据”。下一版把这两个问题分开报告，并把开发问题与保留问题分开。
