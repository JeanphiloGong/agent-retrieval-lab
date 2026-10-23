# 混合检索 v0：建立可解释的 BM25 基线

前置：01 v2 的评测概念和 03 v3 的来源标识。用户搜 `E104` 时，我们希望包含错误码的块排在前面；只数共同词会忽略词频与文档长度。本版在固定的 `Document` 列表上使用 BM25Plus，输出带来源的排名。这里不加载模型，也不把排名等同于答案。

全部命令从仓库根目录执行，使用你自己的 `labs/`，沿用 `uv sync --locked` 安装的环境。检查通过后按[学习流程](../../../docs/learning-workflow.md)保存自己的版本。

## 1. 从有出处的文档计算词法排名

`Document.id` 是这批语料中的唯一证据身份，`topic` 只供分组；`Hit` 保存文档、内部得分和检索来源。分词器把英文数字标记转小写、中文逐字切分，使精确码保留下来。`bm25_rank` 调用库的 BM25Plus；k1 控制词频饱和，b 控制长度归一化。零词项命中的文档被过滤，避免 BM25Plus 的平滑分数被误当成召回证据。

```bash
mkdir -p labs/hybrid
touch labs/__init__.py labs/hybrid/__init__.py
```

这两个 `__init__.py` 是空的包文件；已有文件保留，下面才开始实现本版行为。

`labs/hybrid/retrieval.py` — checkpoint：将这个文件完整写为下面的代码。

```python
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Sequence

from rank_bm25 import BM25Plus

TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[一-鿿]")


@dataclass(frozen=True)
class Document:
    id: str
    text: str
    topic: str = ""


@dataclass(frozen=True)
class Hit:
    document: Document
    score: float
    sources: tuple[str, ...] = ()


def tokenize(text: str) -> list[str]:
    """Use one stable tokenizer for every lexical measurement."""
    return [token.lower() for token in TOKEN_RE.findall(text)]


def bm25_rank(documents: Sequence[Document], query: str, *, k1: float = 1.5, b: float = 0.75) -> list[Hit]:
    if k1 < 0 or not 0 <= b <= 1:
        raise ValueError("invalid BM25 parameters")
    terms = tokenize(query)
    if not terms or not documents:
        return []
    tokenized = [tokenize(doc.text) for doc in documents]
    if not any(tokenized):
        return []
    scores = BM25Plus(tokenized, k1=k1, b=b).get_scores(terms)
    scored = [Hit(doc, float(score), ("bm25",)) for doc, tokens, score in zip(documents, tokenized, scores) if set(tokens) & set(terms)]
    return sorted(scored, key=lambda hit: (-hit.score, hit.document.id))
```

排序采用分数降序、ID 升序，同分输入也有稳定结果。空查询、空语料以及全部无词项的语料返回空列表；不合法的 k1/b 报错。这个函数不读取文件、不修改输入。调用者负责把 03 的块文本和稳定标识装入 Document。

```bash
uv run python - <<'PY'
from labs.hybrid.retrieval import Document, bm25_rank, tokenize

docs = [Document("error", "E104 socket timeout"),
        Document("refund", "退款七天内可申请"),
        Document("other", "delivery options")]
assert tokenize("E104") == ["e104"]
assert bm25_rank(docs, "E104")[0].document.id == "error"
assert bm25_rank(docs, "退款")[0].document.id == "refund"
assert bm25_rank(docs, "") == []
assert bm25_rank(docs, "unmentioned") == []
assert bm25_rank([], "E104") == []
try:
    bm25_rank(docs, "E104", b=2)
except ValueError:
    print("BM25 exact, Chinese and boundary checks passed")
else:
    raise AssertionError("invalid b accepted")
PY
```

预期打印 `BM25 exact, Chinese and boundary checks passed`。中文例子只证明分词路径接通，不证明自然语言理解质量。

## 本版检查点

当前完整文件包含 Document、Hit、tokenize 和 bm25_rank。保留它作为后续对照：`network deadline` 与 `socket timeout` 可能没有共同词。下一版增加向量相似度；现有 `tests/test_hybrid.py` 导入最终 API，留到 v3 再整份执行。

需要对照时可阅读[本版参考源码](../../../reference/labs/hybrid/checkpoints/v0_bm25.py)。自己的检查必须在 `labs/` 上通过；参考答案不会更新个人进度。
