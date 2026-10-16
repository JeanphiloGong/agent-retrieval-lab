# 混合检索 v3：在候选边界内重排

主题相似的段落可能包含“不可用”或适用范围限制。重排器只能处理已召回的候选，不能弥补召回遗漏；因此先用 BM25 与 RRF 得到小集合，再应用明确的评分函数。

```python
from labs.hybrid.retrieval import Document, bm25_rank, rerank

docs = [
    Document("allowed", "shipping is available for this region"),
    Document("excluded", "shipping is not available for this region"),
]
hits = rerank("shipping", bm25_rank(docs, "shipping"), scorer=lambda query, texts: [1.0] * len(texts))
assert {hit.document.id for hit in hits} == {"allowed", "excluded"}
```

`rerank` 接收显式 scorer；真实实验把 FastEmbed `Xenova/ms-marco-MiniLM-L-6-v2` 交叉编码器传入它。生产 reranker 必须记录模型版本、候选数、延迟和失败原因，失败不能悄悄退回一个看似成功的排序。

完整 checkpoint 位于 [`labs/hybrid/checkpoints/v3_rerank.py`](../../../labs/hybrid/checkpoints/v3_rerank.py)。运行：

```bash
uv run python -m labs.hybrid.checkpoints.v3_rerank
uv run python -m pytest -q tests/test_hybrid_checkpoints.py -k v3
```

确认重排没有偷偷新增文档。模型加载或评分失败会直接报错；教程不把失败伪装成一个成功的 lexical fallback。这个检查点冻结“召回与排序分开”的边界；v4 才对不同组合做分组评测。
