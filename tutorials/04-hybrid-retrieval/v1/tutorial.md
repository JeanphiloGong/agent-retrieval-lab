# 混合检索 v1：增加可重放的向量对照

BM25 对精确错误码很合适，但用户问“网络截止时间”时，文档可能只写 `connection timeout`。本仓库使用 FastEmbed 的 `sentence-transformers/all-MiniLM-L6-v2`，并在 `labs/hybrid/models.py` 中锁定 Hugging Face revision。首次运行需要下载模型；模型失败必须报告，而不是伪造向量命中。

```python
from pathlib import Path
from labs.hybrid.models import load_embedding
from labs.hybrid.retrieval import Document, vector_rank

model = load_embedding(Path("artifacts/models"))
docs = [Document("error", "E104 connection timeout")]
vectors = [v.tolist() for v in model.embed([docs[0].text])]
hits = vector_rank(docs, vectors, next(model.query_embed("network deadline")).tolist())
assert hits[0].document.id == "error"
```

模型版本、维度和模型文件属于索引契约；改变它们后，旧分数不能当作同一实验的结果。空向量不会产生伪命中。

完整 checkpoint 位于 [`labs/hybrid/checkpoints/v1_vector.py`](../../../labs/hybrid/checkpoints/v1_vector.py)。运行 `uv sync --locked` 后执行：

```bash
uv run python -m labs.hybrid.checkpoints.v1_vector
uv run python -m pytest -q tests/test_hybrid_checkpoints.py -k v1
```

首次运行会下载锁定 revision；离线环境应先准备 `artifacts/models`，下载失败会直接报错。不要因为向量命中改写题就宣称它对所有问题更好。这个检查点冻结两条独立排名，下一步需要解决分数尺度不同的问题。
