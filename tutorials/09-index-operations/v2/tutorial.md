# 索引更新与运行成本 v2：有界且随版本失效的缓存

从自己的 v1 继续。热点问题重复执行相同查询有开销，但缓存也可能返回已删除的文档。本版增加一个进程内 LRU 缓存：身份作用域、来源世代、问题共同决定命中。模型/分块版本由一个 Index 实例固定，更换索引配置时创建新的 QueryCache。

全部命令从仓库根目录执行，使用你自己的 `labs/`，沿用 `uv sync --locked` 安装的环境。检查通过后按[学习流程](../../../docs/learning-workflow.md)保存自己的版本。

## 1. 把身份与世代放进缓存键

QueryCache.query 返回 `(value, hit)`，value 固定为 tuple。命中时移到最近使用位置；miss 调用 compute，只有成功返回才写缓存，超出 capacity 淘汰最旧项。tenant、subject、roles、policy_version 防止跨主体复用；generation 使来源更新可见。它不替代读时授权。

`labs/operations/index.py` — patch：在现有导入之后加入下面的导入；不要重复已有项。

```python
from collections import OrderedDict
from typing import Callable
```

`labs/operations/index.py` — patch：将下面的完整定义追加到文件末尾，已有定义保留。

```python
class QueryCache:
    def __init__(self, capacity: int = 32) -> None:
        if capacity < 1:
            raise ValueError("capacity must be positive")
        self.capacity = capacity
        self.entries = OrderedDict()

    def query(self, identity: Identity, generation: tuple, question: str, compute: Callable):
        key = (identity.tenant, identity.subject, tuple(sorted(identity.roles)), identity.policy_version, generation, question)
        if key in self.entries:
            self.entries.move_to_end(key)
            return self.entries[key], True
        value = tuple(compute())
        self.entries[key] = value
        self.entries.move_to_end(key)
        while len(self.entries) > self.capacity:
            self.entries.popitem(last=False)
        return value, False
```

```bash
uv run python - <<'PY'
from pathlib import Path
from tempfile import TemporaryDirectory
from labs.access.control import Identity
from labs.operations.index import Index, QueryCache

with TemporaryDirectory() as directory:
    index = Index(Path(directory) / "index.sqlite", "m1", "c1")
    try:
        alice, bob = Identity("alice", "a"), Identity("bob", "a")
        index.apply("a", "doc", 1, "hello", [1, 0])
        cache = QueryCache(1)
        calls = []
        def compute():
            calls.append(1)
            return index.search(alice, [1, 0])
        args = (alice, index.generation("a"), "hello")
        assert cache.query(*args, compute)[1] is False
        assert cache.query(*args, compute)[1] is True
        assert len(calls) == 1
        index.apply("a", "doc", 2, None)
        value, hit = cache.query(alice, index.generation("a"), "hello", compute)
        assert value == () and hit is False
        assert cache.query(bob, index.generation("a"), "hello", compute)[1] is False
        assert len(cache.entries) == 1
    finally:
        index.close()
print("cache reuse, deletion invalidation, scope and capacity passed")
PY
```

预期打印 `cache reuse, deletion invalidation, scope and capacity passed`。第二次查询没有再次计算，删除后即使问题没变也不会复用旧答案。

## 本版检查点

本版在 index.py 末尾新增 QueryCache。generation 枚举所有来源版本适合小语料，生产应使用可验证的索引世代标识；本版也没有跨进程缓存和并发 miss 合并。下一版限制同时工作和排队的请求数。

需要对照时可阅读[本版参考源码](../../../reference/labs/operations/checkpoints/v2/index.py)。自己的检查必须在 `labs/` 上通过；参考答案不会更新个人进度。
