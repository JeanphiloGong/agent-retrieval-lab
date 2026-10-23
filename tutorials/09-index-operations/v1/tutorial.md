# 索引更新与运行成本 v1：乱序更新不能复活删除

从自己的 v0 继续，保留数据库表结构。来源先发 revision=3 删除，再重试 revision=2 更新；直接覆盖会复活旧内容。本版让 apply 以单来源递增 revision 决定是否接受，并用墓碑保存删除版本。

全部命令从仓库根目录执行，使用你自己的 `labs/`，沿用 `uv sync --locked` 安装的环境。检查通过后按[学习流程](../../../docs/learning-workflow.md)保存自己的版本。

## 1. 在一个事务里比较版本并写入

完整替换 Index.apply。text=None 表示删除；空字符串仍可代表活文档，但必须有有限向量。相同 revision 和相同负载返回 False，相同 revision 不同负载报冲突，更旧事件忽略，更新事件返回 True。墓碑仍保留 `(tenant,id,revision)`，不能物理删行后丢掉最后版本。读旧值与写新值都在本连接事务范围内；这仍是单写者教学实现，不是多写者 CAS。

`labs/operations/index.py` — patch：完整替换 `Index.apply`，保留其他定义。

```python
def apply(self, tenant: str, doc_id: str, revision: int, text: str | None, vector: Sequence[float] = ()) -> bool:
    if revision < 1 or not tenant or not doc_id:
        raise ValueError("event requires identity and positive revision")
    if text is not None and (not vector or any(not math.isfinite(float(value)) for value in vector)):
        raise ValueError("live documents require a finite embedding")
    serialized = json.dumps(list(vector)) if text is not None else "[]"
    with self.connection:
        old = self.connection.execute("SELECT revision,deleted,text,vector FROM documents WHERE tenant=? AND id=?", (tenant, doc_id)).fetchone()
        desired = (revision, int(text is None), text or "", serialized)
        if old and revision == old[0]:
            if tuple(old) != desired:
                raise ValueError("conflicting event at the same revision")
            return False
        if old and revision < old[0]:
            return False
        self.connection.execute("INSERT INTO documents VALUES(?,?,?,?,?,?) ON CONFLICT(tenant,id) DO UPDATE SET revision=excluded.revision,deleted=excluded.deleted,text=excluded.text,vector=excluded.vector", (tenant, doc_id, *desired))
    return True
```

generation 必须包含墓碑，否则删除后缓存可能看不见版本变化。完整替换下面的方法，其余 v0 方法继续使用。

`labs/operations/index.py` — patch：完整替换 `Index.generation`，保留其他定义。

```python
def generation(self, tenant: str) -> tuple[tuple[str, int], ...]:
    return tuple(self.connection.execute("SELECT id,revision FROM documents WHERE tenant=? ORDER BY id", (tenant,)))
```

```bash
uv run python - <<'PY'
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from labs.access.control import Identity
from labs.operations.index import Index

with TemporaryDirectory() as directory:
    index = Index(Path(directory) / "index.sqlite", "m1", "c1")
    try:
        assert index.apply("a", "doc", 1, "hello", [1, 0]) is True
        assert index.apply("a", "doc", 1, "hello", [1, 0]) is False
        try:
            index.apply("a", "doc", 1, "different", [1, 0])
        except ValueError:
            pass
        else:
            raise AssertionError("conflicting event accepted")
        started = perf_counter()
        assert index.apply("a", "doc", 3, None)
        assert index.search(Identity("alice", "a"), [1, 0]) == []
        print("delete visible after seconds:", perf_counter() - started)
        assert index.apply("a", "doc", 2, "old", [1, 0]) is False
        assert index.generation("a") == (("doc", 3),)
        assert index.search(Identity("alice", "a"), [1, 0]) == []
    finally:
        index.close()
print("duplicate, conflict and out-of-order deletion passed")
PY
```

预期最后打印 `duplicate, conflict and out-of-order deletion passed`，另显示本次删除到查询不可见的实际耗时。该值包括本进程 SQLite 提交与查询，不是分布式索引刷新延迟。

## 本版检查点

v0 文件的 apply 与 generation 两个完整替换组成本版。下一版以 generation 作为查询缓存键的一部分，更新/删除后不命中旧结果。

需要对照时可阅读[本版参考源码](../../../reference/labs/operations/checkpoints/v1/index.py)。自己的检查必须在 `labs/` 上通过；参考答案不会更新个人进度。
