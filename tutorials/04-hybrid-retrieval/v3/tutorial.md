# 混合检索 v3：只重排已召回的候选

从自己的 v2 继续。两个段落都谈 shipping，但其中一个说“不适用”；单纯主题相似不能处理所有限制。本版增加交叉编码器重排。它只能改变候选顺序，不能补回根本没召回的证据。

全部命令从仓库根目录执行，使用你自己的 `labs/`，沿用 `uv sync --locked` 安装的环境。检查通过后按[学习流程](../../../docs/learning-workflow.md)保存自己的版本。

## 1. 分开候选选择和评分

`rerank` 的必需关键字参数 `scorer` 接收 `(query, texts)`，返回同序的数值分数。它不创建新文档，并保留每个 Hit 的来源。评分数量不匹配或出现 NaN/Inf 都是故障；调用者在传入前用 `fused[:6]` 限制候选数，函数本身不猜预算。

`labs/hybrid/retrieval.py` — patch：将下面的完整定义追加到文件末尾，已有定义保留。

```python
def rerank(query: str, candidates: Sequence[Hit], *, scorer) -> list[Hit]:
    """Apply a bounded relevance function while preserving retrieval provenance."""
    scores = list(scorer(query, [hit.document.text for hit in candidates]))
    if len(scores) != len(candidates) or any(not math.isfinite(float(score)) for score in scores):
        raise ValueError("reranker returned invalid scores")
    ranked = [Hit(hit.document, float(score), hit.sources) for hit, score in zip(candidates, scores)]
    return sorted(ranked, key=lambda hit: (-hit.score, hit.document.id))
```

```bash
uv run python - <<'PY'
from labs.hybrid.retrieval import Document, Hit, rerank

candidates = [Hit(Document("a", "shipping allowed"), 1, ("bm25",)),
              Hit(Document("b", "shipping excluded"), .9, ("vector",))]
ranked = rerank("shipping restriction", candidates, scorer=lambda q, texts: [.1, .9])
assert [h.document.id for h in ranked] == ["b", "a"]
assert ranked[0].sources == ("vector",)
for scores in ([], [float("nan"), .2]):
    try:
        rerank("q", candidates, scorer=lambda q, texts: scores)
    except ValueError:
        continue
    raise AssertionError("invalid scores accepted")
print("rerank candidate and failure checks passed")
PY
```

预期打印 `rerank candidate and failure checks passed`。固定 scorer 只测试接线和边界。

## 2. 接入真实交叉编码器

在 models.py 引入 TextCrossEncoder，锁定 reranker 的 revision，再添加加载函数。这里沿用 v1 的 download；两个模型在同一缓存目录中按仓库与 revision 隔离。交叉编码器同时读取问题和候选文本，成本随候选数增加。

`labs/hybrid/models.py` — patch：在现有导入之后加入下面的导入；不要重复已有项。

```python
from fastembed.rerank.cross_encoder import TextCrossEncoder
```

`labs/hybrid/models.py` — patch：将下面的完整定义追加到文件末尾，已有定义保留。

```python
RERANKER = ("Xenova/ms-marco-MiniLM-L-6-v2", "a09144355adeed5f58c8ed011d209bf8ee5a1fec")


def load_reranker(cache: Path):
    path = download(RERANKER, cache)
    return TextCrossEncoder(RERANKER[0], threads=2, specific_model_path=path)
```

```bash
uv run python - <<'PY'
from pathlib import Path
from labs.hybrid.models import load_embedding, load_reranker
from labs.hybrid.retrieval import Document, bm25_rank, vector_rank, rrf_fuse, rerank

docs = [Document("allowed", "shipping is available for business plans"),
        Document("excluded", "shipping is not available for free plans")]
query = "Can free plans use shipping?"
encoder = load_embedding(Path("artifacts/models"))
scorer = load_reranker(Path("artifacts/models"))
vectors = [list(v) for v in encoder.embed([d.text for d in docs])]
candidates = rrf_fuse(bm25_rank(docs, query),
                      vector_rank(docs, vectors, list(next(encoder.query_embed(query)))))[:6]
ranked = rerank(query, candidates, scorer=scorer.rerank)
assert {h.document.id for h in ranked} == {h.document.id for h in candidates}
print([(h.document.id, round(h.score, 4)) for h in ranked])
PY
```

应返回同一候选集合的真实分数和顺序。记录实际结果，不预设模型必定理解否定条件；v4 用整组问题判断收益。

```bash
uv run python -m pytest -q tests/test_hybrid.py
```

此时最终检索 API 已齐全，9 项测试应通过。它们检查算术和候选边界，真实模型能力由上一条命令与下一版报告测量。

## 本版检查点

retrieval.py 的五个公开单元与 models.py 的两个模型加载器已连接。下一版把相同语料、问题、模型和故障一起写入比较报告。

需要对照时可阅读[本版参考源码](../../../reference/labs/hybrid/retrieval.py)。自己的检查必须在 `labs/` 上通过；参考答案不会更新个人进度。
