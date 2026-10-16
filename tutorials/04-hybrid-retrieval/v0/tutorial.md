# 混合检索 v0：先建立 BM25 基线

## 场景

技术助手收到 `E104`、`refund` 或一段中文问题，需要从一组版本固定的文档块中返回候选证据。这个版本只回答“哪些文本包含查询词”，不生成答案，也不假装语义理解已经解决。

## 从零开始

最直接的做法是数词频。只按出现次数排序会让长文档占便宜；同一个词在短文档中出现一次，往往比在很长的日志里出现三次更有区分度。BM25 保留词频，同时用逆文档频率和长度归一化修正这两个压力。

```python
from labs.hybrid.retrieval import Document, bm25_rank

documents = [
    Document("error", "E104 connection timeout while opening a socket"),
    Document("policy", "Refund reimbursement is available within seven days"),
]
for hit in bm25_rank(documents, "E104"):
    print(hit.document.id, round(hit.score, 3), hit.sources)
```

`bm25_rank` 使用固定 tokenizer，返回 `Hit(document, score, sources)`。分数只在同一次查询、同一套参数内比较；不要把它和向量分数直接相加。

## 检查与冻结

完整 checkpoint 位于 [`labs/hybrid/checkpoints/v0_bm25.py`](../../../labs/hybrid/checkpoints/v0_bm25.py)。运行：

```bash
uv run python -m labs.hybrid.checkpoints.v0_bm25
uv run python -m pytest -q tests/test_hybrid.py tests/test_hybrid_checkpoints.py -k 'bm25 or v0'
```

结果必须把 `e104` 排在第一位。再用中文查询和空查询观察 tokenizer 的边界。这个检查点能提供可复现的词项基线，仍无法找到只在改写词中表达的证据；v1 将增加独立的向量对照。
