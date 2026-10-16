# v1：关键词基线

v0 已经能证明 `E104` 的金标准引用确实指向错误说明的第二行，但它还不能回答“检索器能不能找回这一行”。本版从 v0 的固定来源和问题开始，增加一个可重复的关键词搜索器。

## 先看缺口

如果调用方只能拿到一串来源文件，它仍然要自己打开每份文件、自己猜应该返回哪一行：

```python
for source in sources:
    print(source.read_text())
```

这段代码没有查询、排序或稳定位置。即便它打印了正确文本，评测也无法区分“找到了错误码所在行”和“恰好把整份文件打印出来”。v0 的 `gold_evidence` 已经给出明确目标：结果必须含有 `source_id`、版本和包含端点的行范围。

## 只加一个确定性检索器

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
uv run python -m unittest tests.evaluation.test_keyword
```

完整评测测试仍可一起运行：

```bash
uv run python -m unittest discover -s tests/evaluation
```

## 完整代码检查点

完整 `checkpoint` 包位于 [checkpoints/v1](../../../labs/evaluation/checkpoints/v1)，包含本版的 [keyword.py](../../../labs/evaluation/checkpoints/v1/keyword.py) 和此前已解释的验证契约。可以完全绕开未来的最新版代码重放：

```bash
uv run python -c '
from pathlib import Path
from labs.evaluation.checkpoints.v1.keyword import search_manifest
assert search_manifest("E104", Path("fixtures/evaluation/sources.json"))[0].start_line == 2
'
```

完整文件中的数据流是 `search_manifest` → `load_documents` → `search`。前两个函数只读取清单和原文；`search` 不做文件 I/O，只把查询和已加载的行转换为排序结果。`DocumentLine` 保存原文位置，`SearchResult` 增加本次查询的分数；两者都不会修改原文。

## Checkpoint

v1 冻结的新增文件是：

```text
labs/evaluation/keyword.py
tests/evaluation/test_keyword.py
```

它们依赖 v0 的来源清单和原文，不复制一份隐含的语料。当前检查点能返回可核验的候选位置；它仍然没有回答“返回了相关位置后，最终回答是否忠于证据”。下一版把这两个问题分开报告，并把开发问题与保留问题分开。
