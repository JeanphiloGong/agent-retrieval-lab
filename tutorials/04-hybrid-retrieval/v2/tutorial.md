# 混合检索 v2：用 RRF 合并排名

BM25 的分数取决于词频和语料，向量分数取决于模型空间。把两个浮点数相加没有共同单位。我们只融合排名位置，并保留每个候选来自哪一路。

```python
from pathlib import Path
from labs.hybrid.checkpoints.v2_fusion import fuse
from labs.hybrid.models import load_embedding
from labs.hybrid.retrieval import Document

docs = [Document("error", "E104 connection timeout"), Document("policy", "refund in seven days")]
encoder = load_embedding(Path("artifacts/models"))
fused = fuse(docs, "refund", encoder)
assert fused[0].document.id == "policy"
assert set(fused[0].sources) == {"bm25", "vector"}
```

RRF 为第 `r` 名贡献 `1 / (k + r)`。同一 `document.id` 只出现一次，来源集合合并。`k` 不是质量旋钮，改变它必须重新评测。

完整 checkpoint 位于 [`labs/hybrid/checkpoints/v2_fusion.py`](../../../labs/hybrid/checkpoints/v2_fusion.py)。运行：

```bash
uv run python -m labs.hybrid.checkpoints.v2_fusion
uv run python -m pytest -q tests/test_hybrid.py tests/test_hybrid_checkpoints.py -k 'rrf or v2'
```

再手算两个短排名验证结果。当前检查点只负责召回和来源追踪，尚未判断候选是否真正回答了问题；v3 将在有界候选上重排。
