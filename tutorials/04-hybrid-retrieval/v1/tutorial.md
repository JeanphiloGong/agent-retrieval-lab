# 混合检索 v1：连接锁定版本的向量模型

从自己的 v0 继续。用户把 `socket timeout` 改写成 `network deadline` 时，词法排名可能为空。本版增加余弦排名和真实 embedding 加载；文档 ID、稳定排序和错误显式传播继续保留。先手算验证排名，再运行锁定模型，不用固定向量证明模型质量。

全部命令从仓库根目录执行，使用你自己的 `labs/`，沿用 `uv sync --locked` 安装的环境。检查通过后按[学习流程](../../../docs/learning-workflow.md)保存自己的版本。

## 1. 将模型输出变成可验证的排名

`vector_rank` 接收同序的文档和向量，以及一个查询向量。它不负责生成 embedding，所以可以先用二维向量手算。维度、数量和有限数检查在这个数值入口执行；零向量余弦定义为 0，距离相同按 ID 排序。余弦分数只在这一路排名内部有意义。

`labs/hybrid/retrieval.py` — patch：在现有导入之后加入下面的导入；不要重复已有项。

```python
import math
```

`labs/hybrid/retrieval.py` — patch：将下面的完整定义追加到文件末尾，已有定义保留。

```python
def vector_rank(documents: Sequence[Document], vectors: Sequence[Sequence[float]], query_vector: Sequence[float]) -> list[Hit]:
    if len(documents) != len(vectors) or not query_vector:
        raise ValueError("vector count or dimensions do not match")
    if any(len(vector) != len(query_vector) for vector in vectors):
        raise ValueError("vector dimensions do not match")
    if any(not math.isfinite(value) for vector in [query_vector, *vectors] for value in vector):
        raise ValueError("vectors must be finite")
    def cosine(vector):
        norm = math.sqrt(sum(value * value for value in vector) * sum(value * value for value in query_vector))
        return sum(a * b for a, b in zip(vector, query_vector)) / norm if norm else 0.0
    scored = [Hit(doc, cosine(vector), ("vector",)) for doc, vector in zip(documents, vectors)]
    return sorted(scored, key=lambda hit: (-hit.score, hit.document.id))
```

```bash
uv run python - <<'PY'
from labs.hybrid.retrieval import Document, vector_rank

docs = [Document("network", "socket timeout"), Document("refund", "return money")]
hits = vector_rank(docs, [[1, 0], [0, 1]], [1, 0])
assert [(h.document.id, h.score) for h in hits] == [("network", 1.0), ("refund", 0.0)]
for vectors in ([[1], [0]], [[float("nan"), 0], [0, 1]]):
    try:
        vector_rank(docs, vectors, [1, 0])
    except ValueError:
        continue
    raise AssertionError("invalid vector accepted")
print("cosine and invalid-vector checks passed")
PY
```

预期打印 `cosine and invalid-vector checks passed`。这一步只冻结数值契约。

## 2. 加载确切模型并接上真实查询

新建 `models.py`。`download` 只取 tokenizer/config 和 ONNX 权重；仓库名与 commit revision 一起标识模型。`load_embedding` 为 FastEmbed 注册相同配置，再从该快照加载，使用 384 维、mean pooling 与归一化。模型文件保存在被忽略的 `artifacts/models`，首次运行需要下载。下载或推理失败直接抛出异常；本版没有备用词法结果。

`labs/hybrid/models.py` — checkpoint：将这个文件完整写为下面的代码。

```python
"""Pinned embedding model for the vector checkpoint."""
from pathlib import Path

from fastembed import TextEmbedding
from fastembed.common.model_description import ModelSource, PoolingType
from huggingface_hub import snapshot_download

EMBEDDING = ("sentence-transformers/all-MiniLM-L6-v2", "1110a243fdf4706b3f48f1d95db1a4f5529b4d41")


def download(model: tuple[str, str], cache: Path) -> str:
    return snapshot_download(model[0], revision=model[1], cache_dir=str(cache), allow_patterns=[
        "config.json", "tokenizer.json", "tokenizer_config.json", "special_tokens_map.json",
        "vocab.txt", "sentence_bert_config.json", "1_Pooling/config.json", "onnx/model.onnx",
    ])


def load_embedding(cache: Path):
    path = download(EMBEDDING, cache)
    name = "lab/all-MiniLM-L6-v2-pinned"
    if not any(model["model"] == name for model in TextEmbedding.list_supported_models()):
        TextEmbedding.add_custom_model(name, pooling=PoolingType.MEAN, normalization=True,
            sources=ModelSource(hf=EMBEDDING[0]), dim=384, model_file="onnx/model.onnx")
    return TextEmbedding(name, threads=2, specific_model_path=path)
```

```bash
uv run python - <<'PY'
from pathlib import Path
from labs.hybrid.models import EMBEDDING, load_embedding
from labs.hybrid.retrieval import Document, bm25_rank, vector_rank

docs = [Document("network", "socket timeout while connecting to the server"),
        Document("refund", "refund policy for returned products")]
query = "network deadline"
encoder = load_embedding(Path("artifacts/models"))
vectors = [list(v) for v in encoder.embed([doc.text for doc in docs])]
query_vector = list(next(encoder.query_embed(query)))
hits = vector_rank(docs, vectors, query_vector)
assert len(query_vector) == 384
assert {h.document.id for h in hits} == {d.id for d in docs}
print("model", EMBEDDING)
print("lexical", [h.document.id for h in bm25_rank(docs, query)])
print("vector", [(h.document.id, round(h.score, 4)) for h in hits])
PY
```

应显示锁定 revision、空的 lexical 排名和两个 vector 候选。记录实际分数与首位结果；不要把相似度阈值写成事实正确率。模型不可用时停在本版，不能用二维实验代替模型连接验收。

## 本版检查点

retrieval.py 保留 v0 并增加 vector_rank；models.py 现在只加载 embedding。下一版处理两种分数尺度不同的问题。

需要对照时可阅读[本版参考源码](../../../reference/labs/hybrid/checkpoints/v1_vector.py)。自己的检查必须在 `labs/` 上通过；参考答案不会更新个人进度。
