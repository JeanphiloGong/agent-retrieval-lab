# 权限与多租户 v2：缓存不能绕过授权

从自己的 v1 继续。管理员搜 finance 后，普通成员若命中同一个 query 缓存，会泄漏材料。本版缓存键包含主体、租户、角色、策略版本和目录版本；缓存只保存文档 ID，命中后仍走 read 复核。

全部命令从仓库根目录执行，使用你自己的 `labs/`，沿用 `uv sync --locked` 安装的环境。检查通过后按[学习流程](../../../docs/learning-workflow.md)保存自己的版本。

## 1. 定义作用域和有效期

ScopedCache.get 返回 ID 元组或 None，空元组表示已缓存的空结果，不能与 miss 混淆。TTL 使用 monotonic 计算进程内经过时间。put 将迭代器固定为 tuple，避免调用者之后修改列表。角色排序让集合的枚举顺序不影响键。

`labs/access/control.py` — patch：在现有导入之后加入下面的导入；不要重复已有项。

```python
import time
```

`labs/access/control.py` — patch：将下面的完整定义追加到文件末尾，已有定义保留。

```python
class ScopedCache:
    def __init__(self, ttl_seconds: float = 30.0) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl must be positive")
        self.ttl_seconds = ttl_seconds
        self._entries: dict[tuple, tuple[float, tuple[str, ...]]] = {}

    def get(self, identity: Identity, query: str) -> tuple[str, ...] | None:
        key = (identity.tenant, identity.subject, tuple(sorted(identity.roles)), identity.policy_version, query)
        entry = self._entries.get(key)
        if entry is None or time.monotonic() - entry[0] >= self.ttl_seconds:
            self._entries.pop(key, None)
            return None
        return entry[1]

    def put(self, identity: Identity, query: str, document_ids: Iterable[str]) -> None:
        key = (identity.tenant, identity.subject, tuple(sorted(identity.roles)), identity.policy_version, query)
        self._entries[key] = (time.monotonic(), tuple(document_ids))
```

```bash
uv run python - <<'PY'
from unittest.mock import patch
from labs.access.control import Identity, ScopedCache

admin = Identity("alice", "a", frozenset({"finance"}))
reader = Identity("alice", "a", frozenset())
cache = ScopedCache(ttl_seconds=10)
with patch("labs.access.control.time.monotonic", return_value=100):
    cache.put(admin, "finance", ["doc"])
    assert cache.get(admin, "finance") == ("doc",)
    assert cache.get(reader, "finance") is None
    assert cache.get(Identity("bob", "a", admin.roles), "finance") is None
    assert cache.get(Identity("alice", "a", admin.roles, 2), "finance") is None
with patch("labs.access.control.time.monotonic", return_value=110):
    assert cache.get(admin, "finance") is None
print("cache scope and exact expiry passed")
PY
```

预期打印 `cache scope and exact expiry passed`。这里只替换时钟，仍执行真实缓存方法；不需要 sleep 十秒。

## 2. 接回检索与当前授权状态

完整替换 Catalog：构造函数创建 ScopedCache，新增 cached_retrieve。缓存查询键前缀加上 revision，replace 后旧条目不会被复用；命中也逐条 read。其余授权与审计逻辑延续 v1。revision 机制覆盖本进程通过 replace 的更新；外部数据库修改需要自己的失效通知。

`labs/access/control.py` — patch：完整替换 `Catalog`，保留其他定义。

```python
class Catalog:
    """Authoritative document and ACL state for this version."""

    def __init__(self, documents: Iterable[ProtectedDocument]):
        self.documents = {(doc.tenant, doc.id): doc for doc in documents}
        self.revision = 1
        self.cache = ScopedCache()
        self.audit: list[dict] = []

    def replace(self, document: ProtectedDocument):
        self.documents[document.tenant, document.id] = document
        self.revision += 1

    def read(self, identity: Identity, doc_id: str) -> ProtectedDocument:
        document = self.documents.get((identity.tenant, doc_id))
        allowed = document is not None and authorize(identity, document)
        self.audit.append({"subject": identity.subject, "tool": "read", "id": doc_id, "allowed": allowed})
        if not allowed:
            raise PermissionError("document unavailable")
        return document

    def retrieve(self, identity: Identity, query: str, *, ranker=None) -> list[ProtectedDocument]:
        candidates = visible_documents(identity, self.documents.values())
        if ranker is None:
            from labs.hybrid.retrieval import Document, bm25_rank
            ranked = bm25_rank([Document(doc.id, doc.text) for doc in candidates], query)
            ids = [hit.document.id for hit in ranked]
        else:
            ids = list(ranker(query, candidates))
        allowed_ids = {doc.id for doc in candidates}
        if not set(ids) <= allowed_ids:
            raise PermissionError("ranker returned an unauthorized document")
        return [self.read(identity, doc_id) for doc_id in ids]

    def cached_retrieve(self, identity: Identity, query: str):
        key = f"{self.revision}:{query}"
        ids = self.cache.get(identity, key)
        if ids is None:
            documents = self.retrieve(identity, query)
            self.cache.put(identity, key, [doc.id for doc in documents])
            return documents
        return [self.read(identity, doc_id) for doc_id in ids]
```

```bash
uv run python - <<'PY'
from labs.access.control import Catalog, Identity, ProtectedDocument

identity = Identity("alice", "a", frozenset({"reader"}))
catalog = Catalog([ProtectedDocument("d", "a", "release notes", frozenset({"reader"}))])
assert catalog.cached_retrieve(identity, "release")[0].id == "d"
assert catalog.cached_retrieve(identity, "release")[0].id == "d"
assert len(catalog.audit) == 2
catalog.replace(ProtectedDocument("d", "a", "release notes", frozenset({"finance"})))
assert catalog.cached_retrieve(identity, "release") == []
assert catalog.cached_retrieve(identity, "release") == []
print("cache hits recheck reads; revocation invalidates results")
PY
```

预期打印 `cache hits recheck reads; revocation invalidates results`。两次命中仍产生读取审计，撤权后的结果为空。

## 本版检查点

ScopedCache 加上替换后的 Catalog 即为本版。未实现跨进程缓存或策略发布协议；下一版让工具调用与恶意文档经过相同授权边界。

需要对照时可阅读[本版参考源码](../../../reference/labs/access/checkpoints/v2/control.py)。自己的检查必须在 `labs/` 上通过；参考答案不会更新个人进度。
