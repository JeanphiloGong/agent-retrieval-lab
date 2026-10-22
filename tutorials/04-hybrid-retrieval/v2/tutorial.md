# 混合检索 v2：用 RRF 合并排名

## 你要手动构建的部分

从自己的 v1 继续，在 `labs/hybrid/retrieval.py` 增加 `rrf_fuse`，保持 `Document.id` 去重和来源合并。先手算两条短排名再运行下面示例。本页片段是调用方，完整算法可对照文末参考答案逐行实现；你的主线不导入 `checkpoints`。按[学习流程](../../../docs/learning-workflow.md)检查后提交自己的版本。

BM25 的分数取决于词频和语料，向量分数取决于模型空间。把两个浮点数相加没有共同单位。我们只融合排名位置，并保留每个候选来自哪一路。

```python
from pathlib import Path
from labs.hybrid.models import load_embedding
from labs.hybrid.retrieval import Document, bm25_rank, rrf_fuse, vector_rank

docs = [Document("error", "E104 connection timeout"), Document("policy", "refund in seven days")]
encoder = load_embedding(Path("artifacts/models"))
vectors = [vector.tolist() for vector in encoder.embed([doc.text for doc in docs])]
query_vector = next(encoder.query_embed("refund")).tolist()
fused = rrf_fuse(bm25_rank(docs, "refund"), vector_rank(docs, vectors, query_vector))
assert fused[0].document.id == "policy"
assert set(fused[0].sources) == {"bm25", "vector"}
```

RRF 为第 `r` 名贡献 `1 / (k + r)`。同一 `document.id` 只出现一次，来源集合合并。`k` 不是质量旋钮，改变它必须重新评测。

参考回放入口位于 [`reference/labs/hybrid/checkpoints/v2_fusion.py`](../../../reference/labs/hybrid/checkpoints/v2_fusion.py)，RRF 定义在完整参考 `retrieval.py` 中。以下命令单独回放参考答案；你的主线用上面的例子和手算排名检查：

```bash
PYTHONPATH=reference uv run python -P -m labs.hybrid.checkpoints.v2_fusion
PYTHONPATH=reference uv run python -P -m pytest --import-mode=importlib -q tests/test_hybrid.py reference/tests/test_hybrid_checkpoints.py -k 'rrf or v2'
```

再手算两个短排名验证结果。当前检查点只负责召回和来源追踪，尚未判断候选是否真正回答了问题；v3 将在有界候选上重排。
