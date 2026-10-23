# 索引更新与运行成本 v0：重启后仍能查询

前置：04 v4、08 v3。向量仅保存在 Python 列表时，重启就要重新生成。本版用一个本地 SQLite 文件保存来源版本、文本和向量，打开时核对模型/分块版本。先验证存储与查询，不测生产容量；实验数据库用 TemporaryDirectory 隔离。

全部命令从仓库根目录执行，使用你自己的 `labs/`，沿用 `uv sync --locked` 安装的环境。检查通过后按[学习流程](../../../docs/learning-workflow.md)保存自己的版本。

## 1. 持久化一个可识别的索引世代

metadata 保存 model/chunker 版本，documents 用 `(tenant, id)` 作主键。构造器只在空库中写配置，不匹配时关闭连接并报错，避免旧向量被当成新模型输出。apply 在连接事务中批量写入，search 先按租户 SQL 过滤，再复用 vector_rank。generation 返回稳定排序的来源版本清单，后续会用它给缓存失效。

```bash
mkdir -p labs/operations
touch labs/__init__.py labs/operations/__init__.py
```

这两个 `__init__.py` 是空的包文件；已有文件保留，下面才开始实现本版行为。

当前 apply 是批量覆盖语义，不拒绝乱序更新，text 必须非空。schema 中的 deleted 默认写 0，为下一版墓碑预留存储字段；本版尚无删除规则。SQLite 每次写入都通过 with connection 提交，close 只负责关闭连接。

`labs/operations/index.py` — checkpoint：将这个文件完整写为下面的代码。

```python
from __future__ import annotations

import json
import math
from pathlib import Path
import sqlite3
from typing import Sequence

from labs.access.control import Identity
from labs.hybrid.retrieval import Document, vector_rank


class Index:
    """Persistent batch index with an explicit model/chunker configuration."""

    def __init__(self, path: Path, model_version: str, chunk_version: str) -> None:
        self.connection = sqlite3.connect(path)
        self.connection.execute("CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT)")
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS documents("
            "tenant TEXT, id TEXT, revision INTEGER, deleted INTEGER, "
            "text TEXT, vector TEXT, PRIMARY KEY(tenant,id))"
        )
        metadata = dict(self.connection.execute("SELECT key,value FROM metadata"))
        wanted = {"model": model_version, "chunker": chunk_version}
        if metadata and metadata != wanted:
            self.connection.close()
            raise ValueError("index configuration mismatch; rebuild explicitly")
        self.connection.executemany("INSERT OR IGNORE INTO metadata VALUES(?,?)", wanted.items())
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def apply(self, tenant: str, doc_id: str, revision: int, text: str,
              vector: Sequence[float]) -> None:
        """Insert one batch document; updates and deletion arrive in v1."""
        if revision < 1 or not tenant or not doc_id or not text:
            raise ValueError("batch document requires identity and text")
        if not vector or any(not math.isfinite(float(value)) for value in vector):
            raise ValueError("batch document requires a finite embedding")
        serialized = json.dumps(list(vector))
        with self.connection:
            self.connection.execute(
                "INSERT INTO documents VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(tenant,id) DO UPDATE SET revision=excluded.revision,"
                "deleted=0,text=excluded.text,vector=excluded.vector",
                (tenant, doc_id, revision, 0, text, serialized),
            )

    def generation(self, tenant: str) -> tuple[tuple[str, int], ...]:
        return tuple(self.connection.execute(
            "SELECT id,revision FROM documents WHERE tenant=? AND deleted=0 ORDER BY id",
            (tenant,),
        ))

    def search(self, identity: Identity, query_vector: Sequence[float], limit: int = 5):
        if not 1 <= limit <= 100:
            raise ValueError("limit must be within 1..100")
        rows = list(self.connection.execute(
            "SELECT id,text,vector FROM documents WHERE tenant=? AND deleted=0 ORDER BY id",
            (identity.tenant,),
        ))
        return vector_rank(
            [Document(row[0], row[1]) for row in rows],
            [json.loads(row[2]) for row in rows],
            query_vector,
        )[:limit] if rows else []
```

```bash
uv run python - <<'PY'
from pathlib import Path
from tempfile import TemporaryDirectory
from labs.access.control import Identity
from labs.operations.index import Index

with TemporaryDirectory() as directory:
    path = Path(directory) / "index.sqlite"
    index = Index(path, "model-v1", "chunk-v1")
    index.apply("a", "doc", 1, "hello", [1, 0])
    index.close()
    index = Index(path, "model-v1", "chunk-v1")
    try:
        assert index.search(Identity("alice", "a"), [1, 0])[0].document.id == "doc"
        assert index.search(Identity("bob", "b"), [1, 0]) == []
        assert index.generation("a") == (("doc", 1),)
        try:
            Index(path, "model-v2", "chunk-v1")
        except ValueError:
            pass
        else:
            raise AssertionError("configuration drift accepted")
    finally:
        index.close()
print("restart, tenant query and configuration guard passed")
PY
```

预期打印 `restart, tenant query and configuration guard passed`。验证先关闭再重开，真正读到了持久化数据；不是只检查模块能导入。

## 本版检查点

index.py 包含完整 Index。这里仍按租户查询，没有接入每文档 ACL；外部服务必须使用 08 的授权流程。本地 SQLite 单连接实验也不证明多进程写入一致性。下一版处理重复、乱序及删除事件。

需要对照时可阅读[本版参考源码](../../../reference/labs/operations/checkpoints/v0/index.py)。自己的检查必须在 `labs/` 上通过；参考答案不会更新个人进度。
