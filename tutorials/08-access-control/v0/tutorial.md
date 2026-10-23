# 权限与多租户 v0：身份决定可见语料

前置：02 v0、03 v3、04 v2。两个租户都叫自己的文档 `manual`；ID 相同不代表可以互相读取。本版将可信调用者提供的 Identity 与查询参数分开，先限定租户再做词项匹配。这里的 Identity 来自实验宿主，不实现登录或令牌验证；不能把用户提交的 tenant 直接当可信身份。

全部命令从仓库根目录执行，使用你自己的 `labs/`，沿用 `uv sync --locked` 安装的环境。检查通过后按[学习流程](../../../docs/learning-workflow.md)保存自己的版本。

## 1. 让每次检索都带可信身份

Identity 只含主体和租户，空值拒绝；ProtectedDocument 保存自己的租户。authorize 是可重复调用的规则，visible_documents 在缺失身份时抛 PermissionError。search 限制查询长度，再在可见集合里匹配词项。文本即使写着另一个租户名称，也不能修改 identity。

```bash
mkdir -p labs/access
touch labs/__init__.py labs/access/__init__.py
```

这两个 `__init__.py` 是空的包文件；已有文件保留，下面才开始实现本版行为。

`labs/access/control.py` — checkpoint：将这个文件完整写为下面的代码。

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class Identity:
    subject: str
    tenant: str

    def __post_init__(self):
        if not self.subject or not self.tenant:
            raise ValueError("trusted identity requires subject and tenant")


@dataclass(frozen=True)
class ProtectedDocument:
    id: str
    tenant: str
    text: str


def authorize(identity: Identity | None, document: ProtectedDocument) -> bool:
    return bool(identity and identity.tenant == document.tenant)


def visible_documents(identity: Identity | None, documents: Iterable[ProtectedDocument]) -> list[ProtectedDocument]:
    if identity is None:
        raise PermissionError("identity is required")
    return [document for document in documents if authorize(identity, document)]


def search(identity: Identity | None, documents: Iterable[ProtectedDocument], query: str) -> list[ProtectedDocument]:
    if not isinstance(query, str) or len(query) > 256:
        raise ValueError("query is invalid")
    terms = {term.lower() for term in query.split()}
    return [document for document in visible_documents(identity, documents)
            if terms <= set(document.text.lower().split())]
```

```bash
uv run python - <<'PY'
from labs.access.control import Identity, ProtectedDocument, search, visible_documents

alice = Identity("alice", "a")
docs = [ProtectedDocument("manual", "a", "release notes"),
        ProtectedDocument("manual", "b", "release secret")]
assert [(d.tenant, d.id) for d in search(alice, docs, "release")] == [("a", "manual")]
assert search(alice, docs, "secret") == []
try:
    visible_documents(None, docs)
except PermissionError:
    print("tenant boundary and missing identity passed")
else:
    raise AssertionError("anonymous access accepted")
PY
```

预期打印 `tenant boundary and missing identity passed`。查询 secret 不会扩大候选集，缺失身份也不会默认为公共租户。

## 本版检查点

本版 control.py 已实现可信身份到可见集合的完整调用。尚未区分同租户角色；下一版增加文档授权并在排序前和实际读取时检查。

需要对照时可阅读[本版参考源码](../../../reference/labs/access/checkpoints/v0/control.py)。自己的检查必须在 `labs/` 上通过；参考答案不会更新个人进度。
