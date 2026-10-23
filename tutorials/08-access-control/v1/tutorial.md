# 权限与多租户 v1：排序前过滤，读取时复核

从自己的 v0 继续。同租户的普通成员不能读财务材料，而且搜索后到读取前可能发生撤权。本版把租户与角色同时纳入授权，增加持有当前文档/ACL 状态的 Catalog。已完成的 04 BM25 只看到授权后的文本。

全部命令从仓库根目录执行，使用你自己的 `labs/`，沿用 `uv sync --locked` 安装的环境。检查通过后按[学习流程](../../../docs/learning-workflow.md)保存自己的版本。

## 1. 扩展身份和文档规则

Identity.roles 是拥有的角色，ProtectedDocument.roles 是要求全部满足的角色集合；空要求表示同租户即可。policy_version 是宿主发布权限策略的版本，后续缓存需要它。下方完整文件替换 v0，保留原 search 调用形状，授权表达式变为“同租户且要求角色是拥有角色的子集”。

`labs/access/control.py` — checkpoint：将这个文件完整写为下面的代码。

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class Identity:
    subject: str
    tenant: str
    roles: frozenset[str] = frozenset()
    policy_version: int = 1

    def __post_init__(self):
        if not self.subject or not self.tenant or self.policy_version < 1:
            raise ValueError("trusted identity requires subject, tenant and policy version")


@dataclass(frozen=True)
class ProtectedDocument:
    id: str
    tenant: str
    text: str
    roles: frozenset[str] = frozenset()


def authorize(identity: Identity | None, document: ProtectedDocument) -> bool:
    return bool(identity and identity.tenant == document.tenant and document.roles <= identity.roles)


def visible_documents(identity: Identity | None, documents: Iterable[ProtectedDocument]) -> list[ProtectedDocument]:
    if identity is None:
        raise PermissionError("identity is required")
    return [document for document in documents if authorize(identity, document)]


def search(identity: Identity | None, documents: Iterable[ProtectedDocument], query: str) -> list[ProtectedDocument]:
    if not isinstance(query, str) or len(query) > 256:
        raise ValueError("query is invalid")
    terms = {term.lower() for term in query.split()}
    return [document for document in visible_documents(identity, documents) if terms <= set(document.text.lower().split())]
```

```bash
uv run python - <<'PY'
from labs.access.control import Identity, ProtectedDocument, visible_documents

reader = Identity("alice", "a", frozenset({"reader"}))
finance = Identity("bob", "a", frozenset({"reader", "finance"}))
docs = [ProtectedDocument("public", "a", "release", frozenset({"reader"})),
        ProtectedDocument("finance", "a", "report", frozenset({"finance"}))]
assert [d.id for d in visible_documents(reader, docs)] == ["public"]
assert [d.id for d in visible_documents(finance, docs)] == ["public", "finance"]
print("document role rule passed")
PY
```

预期打印 `document role rule passed`。角色列表并非“任意一个满足”，这里明确采用全部要求满足的语义。

## 2. 通过当前目录检索和读取

Catalog 用 `(tenant, id)` 作键。replace 更新 ACL/内容并递增 revision；read 根据当前状态再次授权，记录主体、工具、ID 和允许结果。retrieve 先得到可见集合，再调用 BM25 或显式 ranker，并验证 ranker 没有返回集合外 ID。最后逐条调用 read，输出当前允许的文档。外部 ranker 不是授权裁决者。

`labs/access/control.py` — patch：将下面的完整定义追加到文件末尾，已有定义保留。

```python
class Catalog:
    """Authoritative document and ACL state for this version."""

    def __init__(self, documents: Iterable[ProtectedDocument]):
        self.documents = {(doc.tenant, doc.id): doc for doc in documents}
        self.revision = 1
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
```

```bash
uv run python - <<'PY'
from labs.access.control import Catalog, Identity, ProtectedDocument

alice = Identity("alice", "a", frozenset({"reader"}))
public = ProtectedDocument("public", "a", "release notes", frozenset({"reader"}))
private = ProtectedDocument("finance", "a", "release report", frozenset({"finance"}))
catalog = Catalog([public, private])
seen = []
def ranker(query, candidates):
    seen.extend(d.id for d in candidates)
    return [d.id for d in candidates]
assert [d.id for d in catalog.retrieve(alice, "release", ranker=ranker)] == ["public"]
assert seen == ["public"]
assert catalog.retrieve(alice, "release")[0].id == "public"
catalog.replace(ProtectedDocument("public", "a", "release notes", frozenset({"finance"})))
try:
    catalog.read(alice, "public")
except PermissionError:
    assert catalog.audit[-1]["allowed"] is False
else:
    raise AssertionError("revoked document read")
try:
    catalog.retrieve(alice, "q", ranker=lambda q, candidates: ["finance"])
except PermissionError:
    print("prefilter, revoked read and injected ID rejected")
else:
    raise AssertionError("ranker expanded scope")
PY
```

预期打印 `prefilter, revoked read and injected ID rejected`。测试实际进入 ranker 的数据与读取记录，而不依赖模型的拒答文本。

## 本版检查点

control.py 由扩展后的基础规则与 Catalog 组成。Catalog 是本专题声明的当前状态存储，当前仅在进程内；分布式 ACL 一致性与身份认证未实现。下一版允许安全复用检索 ID。

需要对照时可阅读[本版参考源码](../../../reference/labs/access/checkpoints/v1/control.py)。自己的检查必须在 `labs/` 上通过；参考答案不会更新个人进度。
