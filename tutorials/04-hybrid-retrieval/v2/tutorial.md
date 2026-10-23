# 混合检索 v2：用 RRF 合并排名

从自己的 v1 继续。BM25 分数可能是 8，余弦是 0.8；相加会让数值尺度决定胜负。本版只用每路排名的位置融合，同一个文档保留两路来源。模型加载继续复用 v1。

全部命令从仓库根目录执行，使用你自己的 `labs/`，沿用 `uv sync --locked` 安装的环境。检查通过后按[学习流程](../../../docs/learning-workflow.md)保存自己的版本。

## 1. 按排名累积贡献并约束证据身份

RRF 给第 r 名贡献 `1 / (k + r)`，这里 r 从 1 开始。k 越大，前几名之间的差异越小。`rrf_fuse` 以 ID 合并，各路内重复 ID 必须报错，否则同一证据会重复投票；同 ID 不同内容也报错，不能静默选择其中之一。输入可以是列表或迭代器，函数只消费一次。

`labs/hybrid/retrieval.py` — patch：在现有导入之后加入下面的导入；不要重复已有项。

```python
from typing import Iterable
```

`labs/hybrid/retrieval.py` — patch：将下面的完整定义追加到文件末尾，已有定义保留。

```python
def rrf_fuse(*rankings: Iterable[Hit], k: int = 60) -> list[Hit]:
    if k <= 0:
        raise ValueError("k must be positive")
    merged: dict[str, tuple[Document, float, set[str]]] = {}
    for ranking in rankings:
        seen = set()
        for position, hit in enumerate(ranking, start=1):
            if hit.document.id in seen:
                raise ValueError("a ranking contains duplicate document IDs")
            seen.add(hit.document.id)
            document, score, sources = merged.get(hit.document.id, (hit.document, 0.0, set()))
            if document != hit.document:
                raise ValueError("the same ID refers to different documents")
            sources.update(hit.sources)
            merged[hit.document.id] = (document, score + 1 / (k + position), sources)
    return [Hit(doc, score, tuple(sorted(sources))) for doc, score, sources in sorted(
        merged.values(), key=lambda item: (-item[1], item[0].id)
    )]
```

```bash
uv run python - <<'PY'
from labs.hybrid.retrieval import Document, Hit, rrf_fuse

a, b = Document("a", "alpha"), Document("b", "beta")
lexical = [Hit(a, 8, ("bm25",)), Hit(b, 7, ("bm25",))]
semantic = [Hit(b, .8, ("vector",))]
hits = rrf_fuse(lexical, semantic, k=1)
assert hits[0].document.id == "b"
assert abs(hits[0].score - (1 / 3 + 1 / 2)) < 1e-12
assert set(hits[0].sources) == {"bm25", "vector"}
for ranking in ([Hit(a, 1), Hit(a, 2)],):
    try:
        rrf_fuse(ranking)
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate votes accepted")
try:
    rrf_fuse([Hit(a, 1)], [Hit(Document("a", "changed"), 1)])
except ValueError:
    print("RRF arithmetic and identity checks passed")
else:
    raise AssertionError("conflicting identity accepted")
PY
```

预期打印 `RRF arithmetic and identity checks passed`。b 的分数是 1/3 + 1/2；原始 BM25 和余弦得分没有参与相加。

## 2. 把已有两路接成一个调用

下面直接调用 v0/v1 的函数；只计算一次文档 embedding，用 `query_embed` 计算查询向量。融合排序的来源字段解释每条候选来自哪一路。

```bash
uv run python - <<'PY'
from pathlib import Path
from labs.hybrid.models import load_embedding
from labs.hybrid.retrieval import Document, bm25_rank, vector_rank, rrf_fuse

docs = [Document("error", "E104 connection timeout"), Document("policy", "refund policy")]
encoder = load_embedding(Path("artifacts/models"))
vectors = [list(v) for v in encoder.embed([d.text for d in docs])]
query = "E104"
hits = rrf_fuse(bm25_rank(docs, query),
                vector_rank(docs, vectors, list(next(encoder.query_embed(query)))))
assert len({h.document.id for h in hits}) == len(hits)
error = next(h for h in hits if h.document.id == "error")
assert set(error.sources) == {"bm25", "vector"}
print([(h.document.id, h.sources) for h in hits])
PY
```

应看到 error 带有 bm25 和 vector 两个来源，每个 ID 只出现一次。

## 本版检查点

v1 的检索和模型文件继续保留，只新增 rrf_fuse。RRF 合并相似候选，但没有逐对判断问题与文本的条件关系；下一版只对有限候选重排。

需要对照时可阅读[本版参考源码](../../../reference/labs/hybrid/checkpoints/v2_fusion.py)。自己的检查必须在 `labs/` 上通过；参考答案不会更新个人进度。
